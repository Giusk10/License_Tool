import os
import json
import subprocess
from typing import Dict, Optional, Tuple
from app.utility.config import SCANCODE_BIN, OUTPUT_BASE_DIR
from app.services.scanner.main_spdx_utilities import _pick_best_spdx


#  ------------ FUNZIONE PRINCIPALE PER ESEGUIRE SCANCODE -----------------

def run_scancode(repo_path: str) -> dict:
    """
    Esegue ScanCode con filtri avanzati, mostra il progresso in tempo reale
    e ritorna il JSON parsato e pulito.
    """

    # 1. Definizione degli ignore pattern (legge prima patterns_to_ignore.json)
    patterns_path = os.path.join(os.path.dirname(__file__), 'patterns_to_ignore.json')
    rules_path = os.path.join(os.path.dirname(__file__), 'license_rules.json')

    ignore_patterns = []
    if os.path.exists(patterns_path):
        with open(patterns_path, 'r', encoding='utf-8') as f:
            p = json.load(f)
        ignore_patterns = p.get("ignored_patterns", []) or []
    elif os.path.exists(rules_path):
        with open(rules_path, 'r', encoding='utf-8') as f:
            r = json.load(f)
        ignore_patterns = r.get("ignored_patterns", []) or []

    # normalizza e rimuove valori falsy
    ignore_patterns = [str(x) for x in ignore_patterns if x]

    # Assicuriamoci che la directory di output esista
    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

    repo_name = os.path.basename(os.path.normpath(repo_path))
    output_file = os.path.join(OUTPUT_BASE_DIR, f"{repo_name}_scancode_output.json")

    # 2. Costruzione del comando base
    cmd = [
        SCANCODE_BIN,
        # Opzioni Licenza
        "--license",
        "--license-text",
        "--filter-clues",
        "--license-clarity-score",

        # Opzioni Statistiche e Classificazione
        "--tallies",
        "--tallies-key-files",
        "--classify",
    ]

    # 3. Aggiunta dinamica degli ignore pattern
    for pattern in ignore_patterns:
        cmd.extend(["--ignore", pattern])

    # 4. Aggiunta output e target
    cmd.extend([
        "--json-pp", output_file,
        repo_path,
    ])

    print(f"🚀 Avvio ScanCode su: {repo_name}")
    print(f"📂 Output su: {output_file}")

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

    # 1. Carica il JSON generato
    with open(output_file, "r", encoding="utf-8") as f:
        scancode_data = json.load(f)

    # ⬇ Rimuovi la chiave "license_detections" dal JSON di primo livello
    # (Nota: license_detections a volte è pesante e ridondante se usi i dettagli dei file)
    scancode_data.pop("license_detections", None)

    # 2. Sovrascrivi il file JSON con i dati modificati
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scancode_data, f, indent=4, ensure_ascii=False)

    print("✅ ScanCode completato e JSON processato.")

    # 3. Ritorna i dati modificati
    return scancode_data

def detect_main_license_scancode(data: dict) -> Optional[Tuple[str, str]] | str:
    """
    Individua la licenza principale del progetto dai risultati di ScanCode.

    Strategia:
    1. Cerca nei candidati di licenza più probabili (es. file LICENSE/license).
    2. Usa COPYING come fallback.
    3. Come ultima risorsa considera gli altri percorsi rilevanti.

    Ritorna: (spdx_expression, path) o "UNKNOWN" (che non è una tupla, quindi
             il tipo di ritorno è leggermente semplificato qui per un caso speciale).
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

        # Ignora NOTICE/COPYRIGHT
        if basename.startswith("notice") or basename.startswith("copyright"):
            continue

        # Classificazione dei candidati
        if basename.startswith("license"):
            license_candidates.append(entry)
        elif basename.startswith("copying"):
            copying_candidates.append(entry)
        # Se non è già un candidato primario e contiene 'license' o 'copying'
        elif "license" in lower or "copying" in lower:
            other_candidates.append(entry)

    # 1. Tenta la prima scelta: file LICENSE
    result = _pick_best_spdx(license_candidates)
    if result:
        return result

    # 2. Tenta il fallback: file COPYING
    result = _pick_best_spdx(copying_candidates)
    if result:
        return result

    # 3. Tenta l'ultima risorsa: altri percorsi rilevanti
    result = _pick_best_spdx(other_candidates)
    if result:
        return result

    return "UNKNOWN"

def extract_file_licenses(llm_data: dict) -> Dict[str, str]:
    """
    Estrae le licenze per file dal JSON filtrato dai regex.
    :param llm_data:
    :return:
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
            results[path] = " AND ".join(unique_spdx)

    return results
