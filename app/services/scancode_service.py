import os
import json
import subprocess
from typing import Dict


# Percorso al binario di ScanCode
SCANCODE_BIN = "/Users/gius03/tools/scancode-toolkit-v32.4.1/scancode"


def run_scancode(repo_path: str) -> dict:
    """
    Esegue ScanCode su una repo e ritorna il JSON già parsato.
    """

    output_dir = "/Users/gius03/pythonApp/json"
    os.makedirs(output_dir, exist_ok=True)

    repo_name = os.path.basename(os.path.normpath(repo_path))
    output_file = os.path.join(output_dir, f"{repo_name}_scancode_output.json")

    cmd = [
        SCANCODE_BIN,
        "--license",
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
