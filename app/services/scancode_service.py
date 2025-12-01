"""
This module handles the interaction with the ScanCode Toolkit CLI for raw license detection
and implements a post-processing layer using an LLM to filter false positives.
"""

import os
import json
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import SCANCODE_BIN, OUTPUT_BASE_DIR
from app.services.llm_helper import _call_ollama_gpt


#  ------------ MAIN FUNCTION TO EXECUTE SCANCODE -----------------

def run_scancode(repo_path: str) -> dict:
    """
    Executes ScanCode on the target repository and parses the JSON output.

    Note: Real-time progress is printed to the standard output.

    Args:
        repo_path (str): The file system path to the target repository.

    Returns:
        dict: The parsed JSON data from ScanCode, with the top-level
              'license_detections' key removed to reduce payload size.
    """

    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

    repo_name = os.path.basename(os.path.normpath(repo_path))
    output_file = os.path.join(OUTPUT_BASE_DIR, f"{repo_name}_scancode_output.json")

    cmd = [
        SCANCODE_BIN,
        "--license",
        "--license-text",
        "--filter-clues",
        "--json-pp", output_file,
        repo_path,
    ]

    # Real-time output (NO capture_output)
    process = subprocess.Popen(cmd)

    # Wait for completion and get return code
    returncode = process.wait()

    # Error handling according to ScanCode rules
    if returncode > 1:
        raise RuntimeError(f"Errore ScanCode (exit {returncode})")

    if returncode == 1:
        print("⚠ ScanCode ha completato con errori non fatali (exit 1).")

    if not os.path.exists(output_file):
        raise RuntimeError("ScanCode non ha generato il file JSON")

    # 1. Load the generated JSON
    with open(output_file, "r", encoding="utf-8") as f:
        scancode_data = json.load(f)

    # Remove 'license_detections' key from top-level JSON
    scancode_data.pop("license_detections", None)

    # 2. Overwrite the file with modified data
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scancode_data, f, indent=4, ensure_ascii=False)

    # 3. Return modified data
    return scancode_data


#  ------------ FUNCTIONS TO FILTER RESULTS WITH LLM -----------------

def remove_main_license(main_spdx, path, scancode_data) -> dict:
    """
    Removes the main license from the ScanCode results for a specific file path.
    This prevents the LLM from being biased by the main license when filtering.
    """
    for file_entry in scancode_data.get("files", []):
        for det in file_entry.get("matches", []):
            if file_entry.get("path") == path and det.get("license_spdx") == main_spdx:
                scancode_data["files"].remove(file_entry)

    return scancode_data


def filter_with_llm(scancode_data: dict, main_spdx: str, path: str) -> dict:
    """
    Filters ScanCode results using an LLM to remove false positives.

    It constructs a minimal JSON representation of the file matches and asks the LLM
    to validate the 'matched_text' against known license patterns.
    """
    minimal = build_minimal_json(scancode_data)
    # print(json.dumps(minimal, indent=4))
    scan_clean = remove_main_license(main_spdx, path, minimal)

    return ask_llm_to_filter_licenses(scan_clean)


def build_minimal_json(scancode_data: dict) -> dict:
    """
    Builds a minimal JSON structure from the ScanCode data.
    Instead of using the global 'license_detections' list (which requires the LLM to group),
    we iterate directly over files and collect their matches.
    """
    minimal = {"files": []}

    # Iterate over files (which have already been filtered by remove_main_license)
    for file_entry in scancode_data.get("files", []):
        path = file_entry.get("path")
        if not path:
            continue

        file_matches = []

        # ScanCode file-level detections
        for det in file_entry.get("license_detections", []):

            # 'matches' contains details (start_line, end_line, matched_text)
            for match in det.get("matches", []):

                if match.get("from_file") == path:
                    file_matches.append({
                        "license_spdx": match.get("license_expression_spdx"),
                        "matched_text": match.get("matched_text"),
                    })

        score = file_entry.get("percentage_of_license_text")

        if file_matches:
            minimal["files"].append({
                "path": path,
                "matches": file_matches,
                "score": score
            })

    return minimal


def ask_llm_to_filter_licenses(minimal_json: dict) -> dict:
    """
    Sends the reduced JSON to the LLM and returns the clean JSON (matches filtered).
    Analyzes ONLY matched_text.
    """

    prompt = f"""
Sei un esperto di licenze open source.

Ti fornisco un JSON contenente una lista di FILE, ognuno con i suoi MATCH di licenza rilevati.
Il tuo compito è analizzare ogni match e decidere se è valido o meno.

ANALIZZA SOLO:
    matched_text  (per capire se è una licenza)
    license_spdx  (per validità del nome della licenza)

Gli altri campi (path, score) sono metadati.

────────────────────────────────────────
CRITERIO DI FILTRO (usa matched_text + license_spdx)
────────────────────────────────────────

SCARTA il match se matched_text è:

❌ un riferimento (es. "see LICENSE", "Apache License link")
❌ un link a licenze (https://opensource.org/licenses/…)
❌ una descrizione della licenza (non il testo reale)
❌ un frammento di documentazione / commento generico
❌ una citazione in changelog, tutorial, README, docstring
❌ un semplice nome della licenza senza header/testo
❌ un match ereditato da altri file (IGNORA from_file)
❌ testo troppo breve o non legal-formal (meno di ~20 caratteri)

TIENI il match SOLO se matched_text è:

✅ un testo reale di licenza (MIT, GPL, Apache, BSD, MPL, etc.)
✅ un header di licenza usato nei file sorgente
✅ un testo formale di licenza >= 20 caratteri
✓ uno SPDX tag valido (es. “SPDX-License-Identifier: Apache-2.0”)

────────────────────────────────────────
VALIDAZIONE DI license_spdx (nuova regola)
────────────────────────────────────────

1. Se `license_spdx` è il nome di una licenza *valida* (SPDX ufficiale):
   → tienilo così com'è.

2. Se `license_spdx` NON è valido:
   → analizza *solo* il `matched_text` e prova a riconoscere una licenza reale.
      - se il testo contiene una licenza riconoscibile
        (es. inizia con “Apache License Version 2.0”, “MIT License”, “GNU General Public License”, ecc.)
        → SOSTITUISCI license_spdx con l’identificatore SPDX corretto.
      - se dal testo NON si riesce a identificare alcuna licenza valida
        → SCARTA completamente il match.

────────────────────────────────────────
FORMATO RISPOSTA **OBBLIGATORIO**
────────────────────────────────────────

Rispondi SOLO con un JSON:

{{
  "files": [
    {{
      "path": "<path>",
      "matches": [
        {{
          "license_spdx": "<SPDX>"
        }}
      ]
      "score": <score>
    }}
  ]
}}

- includi solo i file che hanno almeno un match valido
- per ogni match tieni il license_spdx (eventualmente corretto)
- non inserire nulla che non rispetta i criteri sopra

────────────────────────────────────────

Ecco il JSON da analizzare:

{json.dumps(minimal_json, indent=2)}
"""

    llm_response = _call_ollama_gpt(prompt)

    try:
        return json.loads(llm_response)
    except json.JSONDecodeError:
        raise RuntimeError("Invalid response from model.")


#  ------------ FUNCTIONS TO DETECT MAIN LICENSE FROM SCANCODE JSON -----------------

def _is_valid(value: Optional[str]) -> bool:
    """Verifies if a string is a valid SPDX and not None/empty/UNKNOWN."""
    return bool(value) and value != "UNKNOWN"


def _extract_first_valid_spdx(entry: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Returns the first valid SPDX found in the ScanCode entry,
    searching in the detected expression, license_detections, and finally in licenses.

    Returns: (spdx_expression, path) or None.
    """
    if not isinstance(entry, dict):
        return None

    path = entry.get("path") or ""

    # 1. Check main detected license expression
    spdx = entry.get("detected_license_expression_spdx")
    if _is_valid(spdx):
        return spdx, path

    # 2. Check individual detections
    # Although the root output 'license_detections' may be removed,
    # this key is still present inside each 'files' object.
    for detection in entry.get("license_detections", []) or []:
        det_spdx = detection.get("license_expression_spdx")
        if _is_valid(det_spdx):
            return det_spdx, path

    # 3. Check SPDX keys in detailed licenses
    for lic in entry.get("licenses", []) or []:
        spdx_key = lic.get("spdx_license_key")
        if _is_valid(spdx_key):
            return spdx_key, path

    return None


def _pick_best_spdx(entries: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """
    Sorts files closest to root (lower path depth) and
    returns the first valid SPDX license found.

    Returns: (spdx_expression, path) or None.
    """
    if not entries:
        return None

    # Sort: use path depth (count of "/") as key
    # Lower count means closer to root.
    sorted_entries = sorted(entries, key=lambda e: (e.get("path", "") or "").count("/"))

    for entry in sorted_entries:
        res = _extract_first_valid_spdx(entry)
        if res:
            # res is already a tuple (spdx, path)
            return res

    return None


def detect_main_license_scancode(data: dict) -> Optional[Tuple[str, str]] | str:
    """
    Identifies the main license of the project based on ScanCode results.

    Strategy:
    1. Search in most likely license candidates (e.g., LICENSE/license files).
    2. Use COPYING as fallback.
    3. Use other relevant paths as last resort.

    Returns: (spdx_expression, path) or "UNKNOWN" (simplified return type for this special case).
    """

    license_candidates = []
    copying_candidates = []
    other_candidates = []

    for entry in data.get("files", []):
        path = entry.get("path") or ""
        if not path:
            continue

        lower = path.lower()
        basename = os.path.basename(lower)

        # Ignore NOTICE/COPYRIGHT
        if basename.startswith("notice") or basename.startswith("copyright"):
            continue

        # Classification of candidates
        if basename.startswith("license"):
            license_candidates.append(entry)
        elif basename.startswith("copying"):
            copying_candidates.append(entry)
        # If not already a primary candidate and contains 'license' or 'copying'
        elif "license" in lower or "copying" in lower:
            other_candidates.append(entry)

    # 1. Try first choice: LICENSE file
    result = _pick_best_spdx(license_candidates)
    if result:
        return result

    # 2. Try fallback: COPYING file
    result = _pick_best_spdx(copying_candidates)
    if result:
        return result

    # 3. Try last resort: other relevant paths
    result = _pick_best_spdx(other_candidates)
    if result:
        return result

    return "UNKNOWN"


#  ------------ FUNCTIONS TO EXTRACT RESULTS FROM FILTERED LLM JSON -----------------

def extract_file_licenses_from_llm(llm_data: dict) -> Dict[str, str]:
    """
    Extracts the license for each file starting from the LLM-filtered JSON.
    llm_data has a different format than the original ScanCode JSON.
    """

    results = {}

    for f in llm_data.get("files", []):
        path = f.get("path")
        matches = f.get("matches", [])

        if not matches:
            continue

        # If there are multiple matches, combine them with AND (like ScanCode tool)
        unique_spdx = list({m.get("license_spdx") for m in matches if m.get("license_spdx")})

        if not unique_spdx:
            continue

        if len(unique_spdx) == 1:
            results[path] = unique_spdx[0]
        else:
            results[path] = " AND ".join(unique_spdx)

    return results
