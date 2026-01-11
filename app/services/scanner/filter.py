"""
Questo modulo gestisce l'interazione con la CLI di ScanCode Toolkit per il rilevamento delle licenze non elaborate
e implementa un livello di post-elaborazione utilizzando un LLM per filtrare i falsi positivi.
"""

import os
import json
import re
from app.utility.config import MINIMAL_JSON_BASE_DIR


def filter_licenses(scancode_data: dict, main_spdx: str, path: str) -> dict:
    """
    Filtra i risultati di ScanCode utilizzando un LLM per rimuovere i falsi positivi.

    Argomenti:
    scancode_data (dict): L'output grezzo di ScanCode.
    main_spdx (str): L'identificatore SPDX della licenza principale del progetto.
    path (str): Il percorso del file di licenza principale.

    Restituisce:
        dict: I dati della licenza filtrati e puliti.
    """
    minimal = build_minimal_json(scancode_data)
    scan_clean = remove_main_license(main_spdx, path, minimal)

    is_unknown = main_spdx == "UNKNOWN"
    regex_filtered = regex_filter(scan_clean, detected_main_spdx=not is_unknown)

    uniques = check_license_spdx_duplicates(regex_filtered)

    return uniques


def build_minimal_json(scancode_data: dict) -> dict:
    """
    Crea una struttura JSON minima dai dati ScanCode.

    Argomenti:
        scancode_data (dict): i dati grezzi di ScanCode.


    Restituisce:
        dict: un dizionario semplificato contenente solo informazioni rilevanti su file e corrispondenze.
    """
    minimal = {"files": []}

    for file_entry in scancode_data.get("files", []):
        path = file_entry.get("path")
        if not path:
            continue

        file_matches = []
        for det in file_entry.get("license_detections", []):
            for match in det.get("matches", []):
                is_correct_file = match.get("from_file") == path
                is_not_ref = "LicenseRef" not in match.get("license_expression_spdx")

                if is_correct_file and is_not_ref:
                    file_matches.append({
                        "license_spdx": match.get("license_expression_spdx"),
                        "matched_text": match.get("matched_text"),
                    })

        if file_matches:
            minimal["files"].append({
                "path": path,
                "is_legal": file_entry.get("is_legal"),
                "is_key_file": file_entry.get("is_key_file"),
                "matches": file_matches,
                "score": file_entry.get("percentage_of_license_text")
            })

    _save_to_json(minimal, "minimal_output.json")
    return minimal


def remove_main_license(main_spdx, path, scancode_data) -> dict:
    """
    Rimuove la licenza principale dal JSON ScanCode.

    Argomenti:
    main_spdx (str): Identificatore SPDX della licenza principale.
    path (str): Percorso del file di licenza principale.
    scancode_data (dict): Dati minimi ScanCode.

    Restituisce:
    dict: I dati con la licenza principale rimossa dalla voce di file specifica.
    """
    for file_entry in scancode_data.get("files", []):
        matches = file_entry.get("matches", [])
        should_remove = False
        for det in matches:
            if file_entry.get("path") == path and det.get("license_spdx") == main_spdx:
                should_remove = True
                break

        if should_remove:
            try:
                scancode_data["files"].remove(file_entry)
            except ValueError:
                pass

    return scancode_data


def _load_rules_patterns():
    """
    Funzione di supporto per caricare e compilare modelli regex dal file delle regole.

    Restituisce:
    dict: un dizionario contenente modelli regex compilati per tag, licenze e link.

    Genera:
    FileNotFoundError: se il file delle regole non esiste.
    """
    rules_path = os.path.join(os.path.dirname(__file__), 'license_rules.json')
    if not os.path.exists(rules_path):
        raise FileNotFoundError(f"Unable to find the rules file: {rules_path}")

    with open(rules_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    patterns = {
        "re_spdx_tag": re.compile(
            rules.get("spdx_tag_pattern", ""), re.IGNORECASE
        ),
        "valid_license_patterns": [],
        "valid_link_patterns": []
    }

    for pattern in rules.get("valid_license_text_patterns", []):
        try:
            patterns["valid_license_patterns"].append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass

    for pattern in rules.get("valid_license_link_patterns", []):
        try:
            patterns["valid_link_patterns"].append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass

    return patterns


def _is_valid_match(matched_text: str, patterns: dict) -> tuple[bool, object]:
    """
    Convalida una singola corrispondenza di testo rispetto ai pattern della whitelist.

    Argomenti:
    matched_text (str): Il testo trovato da ScanCode.
    patterns (dict): Il dizionario dei pattern regex compilati.

    Restituisce:
    tuple[bool, object]: Una tupla contenente un valore booleano che indica la validità
    e l'oggetto della corrispondenza regex se è stato trovato un tag SPDX (o Nessuno).
    """
    # 1. Controllo esplicito del tag SPDX
    spdx_tag_hit = patterns["re_spdx_tag"].search(matched_text)
    if spdx_tag_hit:
        return True, spdx_tag_hit

    # 2. Controllo del testo legale standard
    for pattern_re in patterns["valid_license_patterns"]:
        if pattern_re.search(matched_text):
            return True, None

    # 3. Controllo collegamento valido
    for pattern_re in patterns["valid_link_patterns"]:
        if pattern_re.search(matched_text):
            return True, None

    return False, None


def _save_to_json(data: dict, filename: str):
    """
    Helper per salvare l'output JSON.

    Argomenti:
    data (dict): il dizionario da salvare.
    filename (str): il nome del file di destinazione.
    """
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_path = os.path.join(MINIMAL_JSON_BASE_DIR, filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def regex_filter(data: dict, detected_main_spdx: bool) -> dict:
    """
    Filtra i risultati di ScanCode utilizzando regole caricate da un file JSON esterno.

    Argomenti:
    data (dict): I dati di ScanCode da filtrare.
    detective_main_spdx (bool): Flag che indica se è stata rilevata una licenza principale.

    Restituisce:
    dict: I dati filtrati contenenti solo corrispondenze valide.
    """
    patterns = _load_rules_patterns()
    filtered_files = {"files": []}
    files = data.get('files', [])

    for file_obj in files:
        legal = file_obj.get('is_legal')

        if legal is True:
            filtered_files["files"].append({
                "path": file_obj.get('path'),
                "matches": file_obj.get('matches', []),
                "score": file_obj.get('score', 0)
            })
            continue

        if detected_main_spdx is True and file_obj.get('is_key_file') is True:
            continue

        valid_matches = []

        for match in file_obj.get('matches', []):
            matched_text = match.get('matched_text', '').strip()

            is_valid_declaration, spdx_tag_hit = _is_valid_match(matched_text, patterns)

            if not is_valid_declaration:
                continue

            # Resolve SPDX ID inline
            raw_spdx = match.get('license_spdx', '')
            final_spdx = "LicenseRef-scancode-unknown"

            # FIX C0301: Line too long
            scancode_id_ok = (
                    raw_spdx and
                    "unknown" not in raw_spdx.lower() and
                    "scancode" not in raw_spdx.lower()
            )

            if spdx_tag_hit:
                final_spdx = spdx_tag_hit.group(1) or spdx_tag_hit.group(3)
            elif scancode_id_ok:
                final_spdx = raw_spdx.strip()

            if final_spdx:
                valid_matches.append({
                    "license_spdx": final_spdx,
                    "matched_text": matched_text
                })

        if valid_matches:
            filtered_files["files"].append({
                "path": file_obj.get('path'),
                "matches": valid_matches,
                "score": file_obj.get('score', 0)
            })

    _save_to_json(filtered_files, "filtered_output.json")
    return filtered_files


def check_license_spdx_duplicates(licenses: dict) -> dict:
    """
    Controlla e rimuove i duplicati delle licenze SPDX nell'output JSON di ScanCode.

    Argomenti:
    licenze (dict): il dizionario contenente i dati delle licenze del file.

    Restituisce:
    dict: i dati con i duplicati rimossi.
    """
    uniques = {"files": []}

    for file_entry in licenses.get("files", []):
        seen_spdx = set()
        spdx_counts = []

        for match in file_entry.get("matches", []):
            raw_spdx = match.get("license_spdx")
            if not raw_spdx:
                continue

            spdx_clean = str(raw_spdx).strip()
            spdx_key = spdx_clean.lower()

            if spdx_key not in seen_spdx:
                seen_spdx.add(spdx_key)
                spdx_counts.append({
                    "license_spdx": spdx_clean,
                    "matched_text": match.get("matched_text")
                })

        spdx_uniques = filter_contained_licenses(spdx_counts)

        if spdx_uniques:
            uniques["files"].append({
                "path": file_entry.get("path"),
                "matches": spdx_uniques,
                "score": file_entry.get("score")
            })

    return uniques


def filter_contained_licenses(spdx_items: list[dict]) -> list[dict]:
    """
    Rimuove un elemento dall'elenco se il suo 'license_spdx' è interamente contenuto
    all'interno del 'license_spdx' di un altro elemento.

    Argomenti:
    spdx_items (list[dict]): Elenco dei dizionari di corrispondenza delle licenze.

    Restituisce:
    list[dict]: Elenco filtrato con le licenze delle sottostringhe ridondanti rimosse.
    """
    n = len(spdx_items)
    to_remove = set()

    for i in range(n):
        item_i = spdx_items[i]
        spdx_i = str(item_i.get("license_spdx", "")).strip()

        if not spdx_i or i in to_remove:
            continue

        for j in range(n):
            if i == j:
                continue

            item_j = spdx_items[j]
            spdx_j = str(item_j.get("license_spdx", "")).strip()

            if len(spdx_i) < len(spdx_j):
                pattern = r"(?<![a-zA-Z0-9.\-])" + re.escape(spdx_i) + r"(?![a-zA-Z0-9.\-])"

                if re.search(pattern, spdx_j, re.IGNORECASE):
                    to_remove.add(i)
                    break

    return [item for k, item in enumerate(spdx_items) if k not in to_remove]

