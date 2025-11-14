import os
import json
import subprocess
from typing import Dict
import requests

# Percorso al binario di ScanCode
SCANCODE_BIN = "/Users/gius03/tools/scancode-toolkit-v32.4.1/scancode"

def run_scancode(repo_path: str) -> dict:
    """
    Esegue ScanCode su una repo e ritorna il JSON già parsato e PULITO.
    """

    output_dir = "/Users/gius03/pythonApp/json"
    os.makedirs(output_dir, exist_ok=True)

    repo_name = os.path.basename(os.path.normpath(repo_path))
    output_file = os.path.join(output_dir, f"{repo_name}_scancode_output.json")

    cmd = [
        SCANCODE_BIN,
        "--license",
        "--license-text",
        "--filter-clues",
        "--json-pp", output_file,
        repo_path,
    ]

    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        raise RuntimeError(f"Errore avvio ScanCode: {e}")

    if not os.path.exists(output_file):
        raise RuntimeError("ScanCode non ha generato il file JSON")

    with open(output_file, "r", encoding="utf-8") as f:
        return json.load(f)

def filter_with_llm(scancode_data: dict) -> dict:
    minimal = build_minimal_json(scancode_data)
    return ask_llm_to_filter_licenses(minimal)

def build_minimal_json(scancode_data: dict) -> dict:
    """
    Costruisce un JSON minimale per il modello LLM,
    rimuovendo completamente la sezione 'files'.
    Mantiene SOLO:
    - headers
    - license_detections (con reference_matches → matched_text)
    """

    minimal = {
        "headers": scancode_data.get("headers", []),
        "license_detections": []
    }

    for det in scancode_data.get("license_detections", []):
        new_det = {
            "identifier": det.get("identifier"),
            "license_expression_spdx": det.get("license_expression_spdx"),
            "reference_matches": []
        }

        for rm in det.get("reference_matches", []):
            new_det["reference_matches"].append({
                "from_file": rm.get("from_file"),
                "start_line": rm.get("start_line"),
                "end_line": rm.get("end_line"),
                "matched_text": rm.get("matched_text"),
                "license_spdx": rm.get("license_expression_spdx")
            })

        minimal["license_detections"].append(new_det)

    return minimal


def _call_ollama_gpt(prompt: json) -> str:
    """
    Chiamata semplice a Ollama (API locale).
    (Non usata direttamente in questa versione, ma pronta per usi futuri.)
    """
    payload = {
        "model": "gpt-oss:120b-cloud",
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")



#TODO: il prompt deve analizzare solo il matched_text e bisogna fare attenzione all'putput JSON perchè è diverso dal JSON di scancode
def ask_llm_to_filter_licenses(minimal_json: dict) -> dict:
    """
    Manda il JSON ridotto al LLM e ritorna il JSON pulito
    (match filtrati).
    Analizza SOLO matched_text.
    """

    prompt = f"""
Sei un esperto di licenze open source.

Ti fornisco un JSON che contiene vari match rilevati da ScanCode.
Ogni match ha vari campi, ma tu devi analizzare SOLO:

    matched_text

I campi:
- license_spdx
- start_line
- end_line
- path
servono solo come metadati e NON influenzano la decisione.

────────────────────────────────────────
CRITERIO DI FILTRO (usa SOLO matched_text)
────────────────────────────────────────

SCARTA il match se matched_text è:

❌ un riferimento (es. "see LICENSE", "Apache License link")
❌ un link a licenze (es. https://opensource.org/licenses/…)
❌ una descrizione della licenza (non il testo reale)
❌ un frammento di documentazione
❌ una citazione in un changelog, tutorial, README, docstring
❌ un semplice nome della licenza senza header vero
❌ un match ereditato da altri file (IGNORA completamente il campo from_file)

TIENI il match SOLO se matched_text è:

✅ un vero blocco di licenza copiato (>= 20 caratteri e contiene testo formale)
✅ un header di licenza (MIT header, Apache header, BSD header, ecc.)
✅ un testo di licenza ufficiale lungo e con formule legali
✅ uno SPDX tag VERO (stringa esatta: "SPDX-License-Identifier: …")

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
          "license_spdx": "<SPDX>",
          "start_line": 0,
          "end_line": 0
        }}
      ]
    }}
  ]
}}

- usa solo i match che hai deciso di TENERE
- se un file non ha match validi → NON includerlo nella risposta

────────────────────────────────────────

Ecco il JSON da analizzare:

{json.dumps(minimal_json, indent=2)}
"""

    llm_response = _call_ollama_gpt(prompt)

    try:
        return json.loads(llm_response)
    except json.JSONDecodeError:
        raise RuntimeError("Il modello ha restituito una risposta non valida")



def detect_main_license_scancode(data: dict) -> str:
    """
    Individua la licenza principale del progetto dai risultati di ScanCode.

    Strategia:
    - cerca prima file di licenza tipici (LICENSE, COPYING, ecc.) nella root
    - poi in sottocartelle
    - per ogni file candidato:
      - usa `detected_license_expression_spdx`
      - altrimenti `license_detections[*].license_expression_spdx`
      - altrimenti `licenses[*].spdx_license_key`
    """

    LICENSE_BASENAMES = (
        "license",
        "license.txt",
        "license.md",
        "copying",
        "copying.txt",
    )

    candidates = []

    for entry in data.get("files", []):
        path = entry.get("path", "") or ""
        lower = path.lower()
        basename = os.path.basename(lower)

        # file chiaramente di licenza
        if basename in LICENSE_BASENAMES or "license" in lower or "copying" in lower:
            candidates.append(entry)

    if not candidates:
        return "UNKNOWN"

    # Ordina: prima quelli più vicini alla root (meno "/")
    candidates.sort(key=lambda e: (e.get("path", "") or "").count("/"))

    for entry in candidates:
        # 1) campo diretto SPDX
        spdx = entry.get("detected_license_expression_spdx")
        if spdx:
            return spdx

        # 2) license_detections
        detections = entry.get("license_detections", [])
        if detections:
            first = detections[0]
            det_spdx = first.get("license_expression_spdx")
            if det_spdx:
                return det_spdx

        # 3) licenses[*].spdx_license_key
        licenses = entry.get("licenses", [])
        if licenses:
            first_lic = licenses[0]
            spdx_key = first_lic.get("spdx_license_key")
            if spdx_key:
                return spdx_key

    return "UNKNOWN"


def extract_file_licenses_from_llm(llm_data: dict) -> Dict[str, str]:
    """
    Estrae la licenza per ogni file a partire dal JSON filtrato dall’LLM.
    llm_data ha un formato diverso dal JSON ScanCode originale.
    """

    results = {}

    for f in llm_data.get("files", []):
        path = f.get("path")
        matches = f.get("matches", [])

        if not matches:
            continue

        # Se ci sono più match, li combiniamo in OR (come fa ScanCode)
        unique_spdx = list({m.get("license_spdx") for m in matches if m.get("license_spdx")})

        if not unique_spdx:
            continue

        if len(unique_spdx) == 1:
            results[path] = unique_spdx[0]
        else:
            results[path] = " OR ".join(unique_spdx)

    return results

