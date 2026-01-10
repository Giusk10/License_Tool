"""
ScanCode Detection Module.

Questo modulo gestisce l'esecuzione del toolkit ScanCode e il parsing dei suoi risultati
per rilevare le licenze all'interno di un repository.

Include funzionalità per:
- Eseguire ScanCode come sottoprocesso con configurazione ottimizzata.
- Identificare la licenza principale del progetto in base alla gerarchia dei file (LICENSE, COPYING).
- Estrarre e aggregare le licenze rilevate per i singoli file.
"""

import os
import json
import logging
import subprocess
import shlex
from typing import Dict, List, Any, Tuple

from app.utility.config import SCANCODE_BIN, OUTPUT_BASE_DIR

logger = logging.getLogger(__name__)


def run_scancode(repo_path: str) -> Dict[str, Any]:
    """
    Esegue ScanCode su uno specifico percorso di repository.

    Applica filtri avanzati, traccia l'avanzamento tramite logging e
    esegue il post-processing sul JSON di output per rimuovere dati ridondanti.

    Args:
        repo_path (str): Il percorso del file system del repository clonato.

    Returns:
        Dict[str, Any]: L'output JSON di ScanCode analizzato e ripulito.

    Raises:
        RuntimeError: Se ScanCode fallisce (exit code > 1) o non genera output.
    """
    # 1. Carica i pattern da ignorare (priorità a patterns_to_ignore.json, fallback a license_rules.json)
    base_dir = os.path.dirname(__file__)
    patterns_path = os.path.join(base_dir, 'patterns_to_ignore.json')
    rules_path = os.path.join(base_dir, 'license_rules.json')

    ignore_patterns: List[str] = []

    try:
        if os.path.exists(patterns_path):
            with open(patterns_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ignore_patterns = data.get("ignored_patterns", [])
        elif os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ignore_patterns = data.get("ignored_patterns", [])
    except json.JSONDecodeError:
        logger.warning("Failed to parse ignore patterns JSON. Proceeding without ignores.")

    # Normalizza i pattern e rimuove le stringhe vuote
    ignore_patterns = [str(x) for x in ignore_patterns if x]

    # Assicura che la directory di output esista
    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

    repo_name = os.path.basename(os.path.normpath(repo_path))
    output_file = os.path.join(OUTPUT_BASE_DIR, f"{repo_name}_scancode_output.json")

    # --- Rilevamento automatico file enormi ---
    MAX_FILE_SIZE_MB = 1  ## 1MB è più che sufficiente per i sorgenti
    limit_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

    logger.info("Pre-scanning for large files (>%d MB)...", MAX_FILE_SIZE_MB)

    for root, dirs, files in os.walk(repo_path):
        # Evita di entrare nelle cartelle già ignorate per velocizzare
        # (Nota: os.walk permette di modificare 'dirs' in-place)
        dirs[:] = [d for d in dirs if d not in ["node_modules", "vendor", ".git", "target"]]

        for filename in files:
            file_path = os.path.join(root, filename)
            try:
                # Se il file è troppo grande, aggiungilo agli ignore
                if os.path.getsize(file_path) > limit_bytes:
                    # Calcola il percorso relativo per l'ignore
                    rel_path = os.path.relpath(file_path, repo_path)
                    logger.warning(f"Auto-ignoring large file: {rel_path}")

                    # Usiamo shlex.quote per gestire spazi e parentesi in modo sicuro
                    safe_path = shlex.quote(rel_path)
                    ignore_patterns.append(safe_path)
                    # --------------------

            except OSError:
                pass  # File non accessibile, ignora errore
    # ------------------------------------------------------

    # 2. Costruisce il comando ScanCode
    cmd = [
        SCANCODE_BIN,
        # License Options
        "--license",
        "--license-text",
        "--filter-clues",
        "--license-clarity-score",
        # Statistics and Classification Options
        "--tallies",
        "--tallies-key-files",
        "--classify",
    ]

    # 3. Aggiunge pattern di ignore dinamici
    for pattern in ignore_patterns:
        cmd.extend(["--ignore", pattern])

    # 4. Aggiunge formato di output e percorso target
    cmd.extend([
        "--json-pp", output_file,
        repo_path,
    ])

    logger.info("Starting ScanCode analysis on: %s", repo_name)
    logger.debug("ScanCode Output File: %s", output_file)

    # Esegue il sottoprocesso
    # L'uso del context manager 'with' assicura che i descrittori di file vengano chiusi correttamente
    with subprocess.Popen(cmd) as process:
        returncode = process.wait()

    # Gestisce i codici di uscita secondo la documentazione di ScanCode
    if returncode > 1:
        logger.error("ScanCode failed with critical error (exit code %d)", returncode)
        raise RuntimeError(f"ScanCode error (exit {returncode})")

    if returncode == 1:
        logger.warning("ScanCode completed with non-fatal errors (exit code 1).")

    if not os.path.exists(output_file):
        logger.error("ScanCode output file not found at %s", output_file)
        raise RuntimeError("ScanCode did not generate the JSON file")

    # 5. Post-elaborazione dell'output JSON
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            scancode_data = json.load(f)

        # Rimuove "license_detections" dal livello superiore per ridurre l'impronta di memoria/dimensione file
        # poiché utilizziamo principalmente i dettagli a livello di file.
        scancode_data.pop("license_detections", None)

        # Salva il JSON ottimizzato su disco
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(scancode_data, f, indent=4, ensure_ascii=False)

        logger.info("ScanCode analysis completed and JSON processed successfully.")
        return scancode_data

    except Exception as e:
        logger.exception("Error during ScanCode output processing")
        raise RuntimeError(f"Failed to process ScanCode output: {e}") from e


def detect_main_license_scancode(data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Rileva la licenza principale usando euristiche basate su profondità, tipo di file e punteggio ScanCode.

    Args:
        data (Dict[str, Any]): L'output JSON di ScanCode analizzato.

    Returns:
        Tuple[str, str]: Una tupla contenente l'espressione SPDX della licenza principale e il percorso del file dove è stata rilevata.
        Restituisce ("UNKNOWN", None) se non viene trovata una licenza valida.
    """

    # 1. Verifica se ScanCode ha rilevato pacchetti (es. package.json, pom.xml)
    # Questa è spesso la licenza "Dichiarata" ed è molto affidabile.
    if "packages" in data and data["packages"]:
        # Prende il primo pacchetto trovato alla radice o vicino ad essa
        for pkg in data["packages"]:
            if pkg.get("declared_license_expression"):
                return pkg.get("declared_license_expression")

    candidates = []

    for entry in data.get("files", []):
        path = entry.get("path", "")
        licenses = entry.get("license_detections", [])

        if not licenses:
            continue

        # Ignora le corrispondenze con bassa confidenza
        if entry.get("percentage_of_license_text", 0) < 80.0:
            continue

        # Calcola la profondità del file (0 = radice)
        depth = path.count("/")
        filename = os.path.basename(path).lower()

        # --- EURISTICHE DI PUNTEGGIO ---

        # Filtro 1: Ignora directory inutili
        if any(x in path.lower() for x in ["node_modules", "vendor", "third_party", "test", "docs"]):
            continue

        for lic in licenses:

            spdx = lic.get("license_expression_spdx")
            if not spdx:
                continue

            weight = 0

            # BONUS 1: Posizione (La Radice è Regina)
            if depth == 0:
                weight += 100
            elif depth == 1:
                weight += 50
            else:
                weight += 0  # I file profondi valgono poco per la licenza principale

            # BONUS 2: Nome del file
            if filename in ["license", "license.txt", "license.md", "copying", "copying.txt"]:
                weight += 100
            elif filename.startswith("license") or filename.startswith("copying"):
                weight += 80
            elif filename in ["readme", "readme.md", "readme.txt"]:
                weight += 60  # La licenza è spesso menzionata nel README
            elif filename in ["package.json", "setup.py", "pom.xml", "cargo.toml"]:
                weight += 90  # File manifest

            # BONUS 3: Copertura della Corrispondenza (Quanto del file è licenza?)
            # Se un file è al 100% testo di licenza, è molto rilevante.
            # (ScanCode a volte fornisce match_coverage o start/end_line)
            if lic.get("matched_rule", {}).get("is_license_text"):
                weight += 40

            candidates.append({
                "spdx": spdx,
                "weight": weight,
                "path": path,
                "score": lic.get("score")
            })

    if not candidates:
        return "UNKNOWN"

    # Ordina i candidati per peso decrescente
    candidates.sort(key=lambda x: x["weight"], reverse=True)

    # Debug: Stampa i primi 3 candidati per capire cosa sta succedendo
    # for c in candidates[:3]:
    #     print(f"Candidate: {c['spdx']} | Weight: {c['weight']} | Path: {c['path']}")

    # Restituisce il vincitore
    # Return the winner
    return candidates[0]["spdx"], candidates[0]["path"]


def extract_file_licenses(scancode_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Estrae le espressioni di licenza per ogni file dai dati di ScanCode.

    Aggrega più corrispondenze all'interno di un singolo file usando 'AND'.

    Args:
        scancode_data (Dict[str, Any]): L'output JSON di ScanCode (filtrato).

    Returns:
        Dict[str, str]: Un dizionario che mappa i percorsi dei file alla loro espressione SPDX rilevata.
    """
    results = {}

    for file_entry in scancode_data.get("files", []):
        path = file_entry.get("path")
        matches = file_entry.get("matches", [])

        if not matches:
            continue

        # Raccoglie gli identificatori SPDX univoci trovati nel file
        unique_spdx = list({m.get("license_spdx") for m in matches if m.get("license_spdx")})

        if not unique_spdx:
            continue

        # Se vengono trovate più licenze nello stesso file, combinarle con AND
        if len(unique_spdx) == 1:
            results[path] = unique_spdx[0]
        else:
            results[path] = " OR ".join(unique_spdx)

    return results
