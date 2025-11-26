import os
import json
import subprocess
from typing import Dict
import requests
from copy import deepcopy
from app.core.config import SCANCODE_BIN, OLLAMA_URL, OUTPUT_BASE_DIR, OLLAMA_GENERAL_MODEL
from app.services.llm_helper import _call_ollama_gpt


#  ------------ FUNZIONE PRINCIPALE PER ESEGUIRE SCANCODE -----------------

def run_scancode(repo_path: str) -> dict:
    """
    Esegue ScanCode, mostra il progresso in tempo reale nel terminale
    e ritorna il JSON parsato.
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

    # ⬇ Stampa in tempo reale (NO capture_output)
    process = subprocess.Popen(cmd)

    # Attende la fine ed ottiene il return code
    returncode = process.wait()

    # Gestione errori secondo le regole reali di ScanCode
    if returncode > 1:
        raise RuntimeError(f"Errore ScanCode (exit {returncode})")

    if returncode == 1:
        print("⚠ ScanCode ha completato con errori non fatali (exit 1).")

    if not os.path.exists(output_file):
        raise RuntimeError("ScanCode non ha generato il file JSON")

    with open(output_file, "r", encoding="utf-8") as f:
        return json.load(f)

#  ------------ FUNZIONI PER FILTRARE I RISULTATI CON LLM -----------------

def filter_with_llm(scancode_data: dict) -> dict:
    # Trova la licenza principale dal report di ScanCode
    main_spdx = detect_main_license_scancode(scancode_data)

    # Lavora su una copia per non modificare l'originale
    data_to_filter = deepcopy(scancode_data)

    # Se abbiamo una main license valida, rimuovila dal JSON che mandiamo all'LLM
    if main_spdx and main_spdx != "UNKNOWN":
        data_to_filter = _remove_main_license_from_scancode(data_to_filter, main_spdx)

    minimal = build_minimal_json(data_to_filter)
    
    return ask_llm_to_filter_licenses(minimal)


def _remove_main_license_from_scancode(data: dict, main_spdx: str) -> dict:
    """
    Rimuove riferimenti alla licenza principale (main_spdx) dal JSON di ScanCode.

    Operazioni eseguite:
    - Filtra la top-level `license_detections` eliminando entry con `license_expression_spdx == main_spdx`.
    - Per ogni entry in `files`:
      - rimuove `detected_license_expression_spdx` se coincide con main_spdx
      - filtra `license_detections` interni con `license_expression_spdx == main_spdx`
      - filtra `licenses` dove `spdx_license_key == main_spdx`

    Restituisce una copia modificata di `data`.
    """

    # Protezione: se non ci sono dati, ritorna com'è
    if not isinstance(data, dict):
        return data

    # Filtra top-level license_detections
    if "license_detections" in data and isinstance(data["license_detections"], list):
        data["license_detections"] = [
            d for d in data["license_detections"]
            if (d.get("license_expression_spdx") or d.get("license_expression_spdx") is not None) and d.get("license_expression_spdx") != main_spdx
        ]

    # Processa le singole file entries
    files = data.get("files")
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict):
                continue

            # rimuovi campo detected_license_expression_spdx se è la main
            if entry.get("detected_license_expression_spdx") == main_spdx:
                entry.pop("detected_license_expression_spdx", None)

            # filtra license_detections nella singola file
            if "license_detections" in entry and isinstance(entry["license_detections"], list):
                entry["license_detections"] = [
                    d for d in entry["license_detections"]
                    if d.get("license_expression_spdx") != main_spdx
                ]

            # filtra la sezione licenses
            if "licenses" in entry and isinstance(entry["licenses"], list):
                entry["licenses"] = [
                    l for l in entry["licenses"]
                    if l.get("spdx_license_key") != main_spdx
                ]

    return data


def build_minimal_json(scancode_data: dict) -> dict:
    """
    Costruisce un JSON minimale raggruppato per file.
    Invece di usare la lista globale 'license_detections' (che richiede al LLM di raggruppare),
    iteriamo direttamente sui file e raccogliamo i loro match.
    """
    minimal = {"files": []}

    # Iteriamo sui file (che sono già stati filtrati da _remove_main_license_from_scancode)
    for file_entry in scancode_data.get("files", []):
        path = file_entry.get("path")
        if not path:
            continue

        file_matches = []
        
        # ScanCode file-level detections
        for det in file_entry.get("license_detections", []):
            spdx = det.get("license_expression_spdx")
            
            # 'matches' contiene i dettagli (start_line, end_line, matched_text)
            for match in det.get("matches", []):
                file_matches.append({
                    "license_spdx": spdx,
                    "matched_text": match.get("matched_text"),
                    "start_line": match.get("start_line"),
                    "end_line": match.get("end_line"),
                    "score": match.get("score")
                })

        if file_matches:
            minimal["files"].append({
                "path": path,
                "matches": file_matches
            })

    return minimal


def ask_llm_to_filter_licenses(minimal_json: dict) -> dict:
    """
    Manda il JSON ridotto al LLM e ritorna il JSON pulito
    (match filtrati).
    Analizza SOLO matched_text.
    """

    prompt = f"""
Sei un esperto di licenze open source.

Ti fornisco un JSON contenente una lista di FILE, ognuno con i suoi MATCH di licenza rilevati.
Il tuo compito è analizzare ogni match e decidere se è valido o meno.

ANALIZZA SOLO:
    matched_text  (per capire se è una licenza)
    license_spdx  (per validità del nome della licenza)

Gli altri campi (start_line, end_line, path) sono metadati.

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
          "license_spdx": "<SPDX>",
          "start_line": 0,
          "end_line": 0
        }}
      ]
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
        raise RuntimeError("Il modello ha restituito una risposta non valida")



#  ------------ FUNZIONI PER RILEVARE LA LICENZA PRINCIPALE DAL JSON SCANCODE -----------------

def detect_main_license_scancode(data: dict) -> str:
    """
    Individua la licenza principale del progetto dai risultati di ScanCode.

    Strategia:
    - privilegia file LICENSE con licenze valide
    - usa COPYING come fallback se LICENSE non c'è o non contiene una licenza
    - ignora NOTICE/COPYRIGHT
    - come ultima risorsa considera altri percorsi che menzionano license/copying
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

        if basename.startswith("notice") or basename.startswith("copyright"):
            continue

        if basename.startswith("license"):
            license_candidates.append(entry)
        elif basename.startswith("copying"):
            copying_candidates.append(entry)
        elif "license" in lower or "copying" in lower:
            other_candidates.append(entry)

    main_spdx = _pick_best_spdx(license_candidates)
    if main_spdx:
        return main_spdx

    main_spdx = _pick_best_spdx(copying_candidates)
    if main_spdx:
        return main_spdx

    main_spdx = _pick_best_spdx(other_candidates)
    if main_spdx:
        return main_spdx

    return "UNKNOWN"

def _extract_first_valid_spdx(entry: dict):
    # Ritorna il primo SPDX valido trovato nell'entry ScanCode
    if not isinstance(entry, dict):
        return None

    def _is_valid(value: str | None) -> bool:
        return bool(value) and value != "UNKNOWN"

    spdx = entry.get("detected_license_expression_spdx")
    if _is_valid(spdx):
        return spdx

    for detection in entry.get("license_detections", []) or []:
        det_spdx = detection.get("license_expression_spdx")
        if _is_valid(det_spdx):
            return det_spdx

    for lic in entry.get("licenses", []) or []:
        spdx_key = lic.get("spdx_license_key")
        if _is_valid(spdx_key):
            return spdx_key

    return None


def _pick_best_spdx(entries: list[dict]) -> str | None:
    # Ordina i file più vicini alla root e ritorna la prima licenza valida
    if not entries:
        return None

    sorted_entries = sorted(entries, key=lambda e: (e.get("path", "") or "").count("/"))
    for entry in sorted_entries:
        spdx = _extract_first_valid_spdx(entry)
        if spdx:
            return spdx
    return None

#  ------------ FUNZIONI PER ESTRAZIONE RISULTATI DAL JSON LLM FILTRATO -----------------

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

        # Se ci sono più match, li combiniamo in OR (come fa il tool ScanCode)
        unique_spdx = list({m.get("license_spdx") for m in matches if m.get("license_spdx")})

        if not unique_spdx:
            continue

        if len(unique_spdx) == 1:
            results[path] = unique_spdx[0]
        else:
            results[path] = " OR ".join(unique_spdx)

    return results
