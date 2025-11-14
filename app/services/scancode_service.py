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
        raw_data = json.load(f)

    # 🔥 Pulisce falsi positivi
    cleaned_data = get_llm_clean_license_results(raw_data)

    return cleaned_data

def get_llm_clean_license_results(scancode_data: dict) -> dict:
    """
    Pipeline:
    1. costruisce JSON semplice
    2. manda al LLM
    3. ritorna JSON filtrato
    """

    minimal = build_minimal_scancode_json(scancode_data)

    cleaned_by_llm = ask_llm_to_filter_licenses(minimal)

    return cleaned_by_llm

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

def build_minimal_scancode_json(data: dict) -> dict:
    """
    Produci un JSON minimalista per il LLM:
    - solo path, spdx, match brevi
    - nessun campo inutile
    """
    minimal = {"files": []}

    for f in data.get("files", []):
        if f.get("type") != "file":
            continue

        mf = {
            "path": f.get("path"),
            "detected_spdx": f.get("detected_license_expression_spdx"),
            "matches": []
        }

        for det in f.get("license_detections", []):
            for m in det.get("matches", []):
                mf["matches"].append({
                    "license_spdx": m.get("license_expression_spdx"),
                    "from_file": m.get("from_file"),
                    "start_line": m.get("start_line"),
                    "end_line": m.get("end_line"),
                    "matched_length": m.get("matched_length"),
                    "matched_text": (m.get("matched_text") or "")[:200],  # max 200 caratteri
                })

        minimal["files"].append(mf)

    return minimal

#TODO: il propt deve analizzare solo il matched_text e bisogna fare attenzione all'putput JSON perchè è diverso dal JSON di scancode
def ask_llm_to_filter_licenses(minimal_json: dict) -> dict:
    """
    Manda il JSON ridotto al LLM e ritorna il JSON pulito
    (match filtrati).
    """
    prompt = f"""
Sei un esperto di licenze open source.

Ti fornisco un JSON con match di licenze trovati da ScanCode.

Devi rimuovere TUTTI i match falsi, cioè:
- citazioni della licenza dentro testo descrittivo
- link a licenze (es: https://opensource.org/licenses)
- riferimenti a "see LICENSE"
- match ereditati da LICENSE (campo from_file diverso dal path)
- header non di licenza
- match con lunghezza troppo corta (inferiore a 20 caratteri)
- match che NON contengono una reale dichiarazione di licenza

Mantieni SOLO:
- SPDX tag reali
- header di licenza
- blocchi di testo copiati da licenza reale
- vera licenza nel file

RISPONDI con SOLO un JSON nel formato:

{{
  "files": [
    {{
      "path": "...",
      "matches": [
        {{
          "license_spdx": "...",
          "start_line": 0,
          "end_line": 0
        }}
      ]
    }}
  ]
}}

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


def extract_file_licenses_scancode(data: dict) -> Dict[str, str]:
    """
    Estrae per OGNI file la licenza (o espressione di licenza) in formato SPDX.

    Restituisce:
        { "path/del/file": "Apache-2.0" }
        { "path/del/file2": "LGPL-2.0-or-later AND MIT" }
    """

    results: Dict[str, str] = {}

    for entry in data.get("files", []):
        file_path = entry.get("path")
        if not file_path or entry.get("type") != "file":
            continue

        # 1) Campo diretto più affidabile
        spdx = entry.get("detected_license_expression_spdx")
        if spdx:
            results[file_path] = spdx
            continue

        # 2) Campo generico
        expr = entry.get("detected_license_expression")
        if expr:
            results[file_path] = expr.upper()
            continue

        # 3) Lista detection dettagliate
        detections = entry.get("license_detections", [])
        if detections:
            first = detections[0]
            det_spdx = first.get("license_expression_spdx")
            if det_spdx:
                results[file_path] = det_spdx
                continue

        # 4) Campo "licenses"
        licenses = entry.get("licenses", [])
        if licenses:
            lic = licenses[0]
            spdx_key = lic.get("spdx_license_key")
            if spdx_key:
                results[file_path] = spdx_key
                continue

    return results
