"""
This module handles the interaction with the ScanCode Toolkit CLI for raw license detection
and implements a post-processing layer using an LLM to filter false positives.
"""

import os
import json
import re
from app.utility.config import MINIMAL_JSON_BASE_DIR

def filter_licenses(scancode_data: dict, main_spdx: str, path: str) -> dict:
    """
    Filters ScanCode results using an LLM to remove false positives.

    It constructs a minimal JSON representation of the file matches and asks the LLM
    to validate the 'matched_text' against known license patterns.
    """
    minimal = build_minimal_json(scancode_data)
    #print(json.dumps(minimal, indent=4))
    scan_clean = remove_main_license(main_spdx, path, minimal)

    if main_spdx != "UNKNOWN":
        regex_filtered = regex_filter(scan_clean, detected_main_spdx=True)
    else:
        regex_filtered = regex_filter(scan_clean, detected_main_spdx=False)

    uniques = check_license_spdx_duplicates(regex_filtered)

    return uniques

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
        legal = file_entry.get("is_legal")
        key_file = file_entry.get("is_key_file")
        if not path:
            continue

        file_matches = []

        # ScanCode file-level detections
        for det in file_entry.get("license_detections", []):

            # 'matches' contains details (start_line, end_line, matched_text)
            for match in det.get("matches", []):

                if match.get("from_file") == path and "LicenseRef" not in match.get("license_expression_spdx"):

                    file_matches.append({
                        "license_spdx": match.get("license_expression_spdx"),
                        "matched_text": match.get("matched_text"),
                    })

        score = file_entry.get("percentage_of_license_text")

        if file_matches:
            minimal["files"].append({
                "path": path,
                "is_legal": legal,
                "is_key_file": key_file,
                "matches": file_matches,
                "score": score
            })


    # Ensures the folder exists and writes the minimal JSON instead of reading it
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_minimal = os.path.join(MINIMAL_JSON_BASE_DIR, "minimal_output.json")

    with open(output_minimal, "w", encoding="utf-8") as f:
        json.dump(minimal, f, indent=4, ensure_ascii=False)

    return minimal

def remove_main_license(main_spdx, path, scancode_data) -> dict:
    """
    Removes the main license from the ScanCode JSON,
    to prevent the LLM from considering it.
    """
    for file_entry in scancode_data.get("files", []):
        for det in file_entry.get("matches", []):
            if file_entry.get("path") == path and det.get("license_spdx") == main_spdx:
                try:
                    scancode_data["files"].remove(file_entry)
                except ValueError:
                    pass

    return scancode_data

def regex_filter(data: dict, detected_main_spdx: bool) -> dict:
    """
    Filters ScanCode results using rules loaded from an external JSON file.
    """

    # --- 1. LOADING AND COMPILING RULES ---

    rules_path = os.path.join(os.path.dirname(__file__), 'license_rules.json')

    if not os.path.exists(rules_path):
        raise FileNotFoundError(f"Unable to find the rules file: {rules_path}")

    with open(rules_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    # Compile exclusion lists into a single optimized regex with OR logic (|)
    # This is much faster than looping over each string.
    re_references = re.compile("|".join(rules.get("ignore_patterns", [])), re.IGNORECASE)
    re_docs_changelog = re.compile("|".join(rules.get("changelog_patterns", [])), re.IGNORECASE)

    # Compile the regex for the SPDX tag
    re_spdx_tag = re.compile(rules.get("spdx_tag_pattern", ""), re.IGNORECASE)

    # Compile patterns to recognize ACTUAL LEGAL TEXT of licenses
    valid_license_patterns = []
    for pattern in rules.get("valid_license_text_patterns", []):
        try:
            valid_license_patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass  # Skip invalid patterns

    # Compile patterns to recognize VALID LINKS to licenses (RST, Markdown, URL)
    valid_link_patterns = []
    for pattern in rules.get("valid_license_link_patterns", []):
        try:
            valid_link_patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass  # Skip invalid patterns

    # Minimum text length
    min_text_length = rules.get("min_matched_text_length", 20)

    filtered_files = {"files": []}

    # --- 2. PROCESSING ---

    files = data.get('files', [])

    for file_obj in files:
        file_path = file_obj.get('path')
        matches = file_obj.get('matches', [])
        file_score = file_obj.get('score', 0)
        legal = file_obj.get('is_legal')
        key_file = file_obj.get('is_key_file')

        if legal is True:
            filtered_files["files"].append({
                "path": file_path,
                "matches": file_obj.get('matches', []),
                "score": file_score
            })
            continue
        elif legal is False and detected_main_spdx is True and key_file is True:
            continue

        valid_matches = []

        for match in matches:
            matched_text = match.get('matched_text', '').strip()
            spdx = match.get('license_spdx', '')

            # -----------------------------------------------------------------
            # 1. POSITIVE VALIDATION (WHITELIST) - Done FIRST!
            # -----------------------------------------------------------------

            is_valid_declaration = False
            match_source = None

            # A. Explicit SPDX Tag Check (Highest Priority)
            spdx_tag_hit = re_spdx_tag.search(matched_text)
            if spdx_tag_hit:
                is_valid_declaration = True
                match_source = "SPDX-TAG"

            # B. Boilerplate Legal Text Check (e.g., "Permission hereby granted...")
            elif not is_valid_declaration:
                for pattern_re in valid_license_patterns:
                    if pattern_re.search(matched_text):
                        is_valid_declaration = True
                        match_source = "LEGAL-TEXT"
                        break

            # C. Valid Link Check (e.g., links to LICENSE files or gnu.org URLs)
            is_valid_license_link = False
            if not is_valid_declaration:
                for pattern_re in valid_link_patterns:
                    if pattern_re.search(matched_text):
                        is_valid_license_link = True
                        is_valid_declaration = True
                        match_source = "VALID-LINK"
                        break

            # -----------------------------------------------------------------
            # 2. NEGATIVE FILTERING (BLACKLIST) - Only if not already validated
            # -----------------------------------------------------------------

            # If the text is ALREADY recognized as valid (e.g., License :: OSI Approved),
            # SKIP the ignore checks.
            if not is_valid_declaration:

                # Minimum length
                if len(matched_text) < min_text_length:
                    continue

                # Discard generic references/links
                if len(matched_text) < 300:
                    if re_references.search(matched_text):
                        continue

                # Discard Changelog Language
                if re_docs_changelog.search(matched_text):
                    continue

            # -----------------------------------------------------------------
            # 3. FINAL FILTER ("Zero Trust")
            # -----------------------------------------------------------------

            # If after all this it is not a valid declaration, discard it.
            if not is_valid_declaration:
                continue

            # -----------------------------------------------------------------
            # 4. FINAL SPDX ID ASSIGNMENT
            # -----------------------------------------------------------------

            final_spdx = None

            # Check formal validity of Scancode ID
            scancode_id_ok = False
            if spdx and "unknown" not in spdx.lower() and "scancode" not in spdx.lower():
                scancode_id_ok = True

            # Case 1: Explicit SPDX Tag
            if spdx_tag_hit:
                final_spdx = spdx_tag_hit.group(1) or spdx_tag_hit.group(3)

            # Case 2: Valid Scancode ID
            if not final_spdx and scancode_id_ok:
                final_spdx = spdx

            # Case 3: Fallback
            if not final_spdx:
                final_spdx = "LicenseRef-scancode-unknown"

            if final_spdx:
                valid_matches.append({
                    "license_spdx": final_spdx.strip(),
                    "matched_text": matched_text
                })

        # Save if there are valid matches and sufficient score
        if valid_matches:
            filtered_files["files"].append({
                "path": file_path,
                "matches": valid_matches,
                "score": file_score
            })


    # --- 3. OUTPUT FILE ---
    # Define MINIMAL_JSON_BASE_DIR in your global code or pass it as an argument if needed
    # Here I assume it exists in the context or use a local default
    base_dir = globals().get('MINIMAL_JSON_BASE_DIR', './output')
    os.makedirs(base_dir, exist_ok=True)
    output_minimal = os.path.join(base_dir, "filtered_output.json")

    with open(output_minimal, "w", encoding="utf-8") as f:
        json.dump(filtered_files, f, indent=4, ensure_ascii=False)

    return filtered_files

def check_license_spdx_duplicates(licenses: dict) -> dict:
    """
    Controlla se ci sono duplicati di licenze SPDX nel JSON di ScanCode.
    Ritorna il dizionario delle licenze senza duplicati.
    """
    uniques = {"files": []}

    for file_entry in licenses.get("files", []):
        seen_spdx = set()
        spdx_counts = []

        for match in file_entry.get("matches", []):
            raw_spdx = match.get("license_spdx")

            if not raw_spdx:
                continue

            # Normalizza per il confronto (strip e lower)
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
    Rimuove un elemento dalla lista se il suo 'license_spdx' è contenuto
    interamente nel 'license_spdx' di un altro elemento.

    Esempio: Se ho [{'license_spdx': 'MIT'}, {'license_spdx': 'Apache-2.0 AND MIT'}],
    rimuove l'elemento che contiene solo 'MIT'.
    """
    n = len(spdx_items)
    to_remove = set()

    for i in range(n):
        # Otteniamo la licenza dell'elemento corrente (il candidato ad essere rimosso)
        item_i = spdx_items[i]
        spdx_i = str(item_i.get("license_spdx", "")).strip()

        # Se la stringa è vuota o l'abbiamo già marcata per la rimozione, saltiamo
        if not spdx_i or i in to_remove:
            continue

        for j in range(n):
            if i == j:
                continue

            # Otteniamo la licenza dell'elemento di confronto (il contenitore)
            item_j = spdx_items[j]
            spdx_j = str(item_j.get("license_spdx", "")).strip()

            # Logica: Se spdx_i è più corto di spdx_j, controlliamo se è contenuto dentro
            if len(spdx_i) < len(spdx_j):
                # Regex boundary: assicura che matchiamo "MIT" ma non "LIMIT" o "SMITH"
                # (?<!...) è un negative lookbehind, (?!...) è un negative lookahead
                # Includiamo ., - e alfanumerici nei boundary per gestire versioni (es. GPL-3.0)
                pattern = r"(?<![a-zA-Z0-9.\-])" + re.escape(spdx_i) + r"(?![a-zA-Z0-9.\-])"

                if re.search(pattern, spdx_j, re.IGNORECASE):
                    to_remove.add(i)
                    break # Abbiamo trovato un contenitore, inutile controllare altri j

    # Ritorna la lista filtrata
    return [item for k, item in enumerate(spdx_items) if k not in to_remove]

