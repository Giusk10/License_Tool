import os
import json
import re
from app.utility.config import MINIMAL_JSON_BASE_DIR

def filter_licenses(scancode_data: dict, main_spdx: str, path: str) -> dict:
    """
    Filtra i risultati di ScanCode usando un LLM per rimuovere
    i falsi positivi basati sul testo della licenza rilevata.
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
    Costruisce un JSON minimale raggruppato per file.
    Invece di usare la lista globale 'license_detections' (che richiede al LLM di raggruppare),
    iteriamo direttamente sui file e raccogliamo i loro match.
    """
    minimal = {"files": []}

    # Iteriamo sui file (che sono già stati filtrati da _remove_main_license_from_scancode)
    for file_entry in scancode_data.get("files", []):
        path = file_entry.get("path")
        legal = file_entry.get("is_legal")
        key_file = file_entry.get("is_key_file")
        if not path:
            continue

        file_matches = []

        # ScanCode file-level detections
        for det in file_entry.get("license_detections", []):

            # 'matches' contiene i dettagli (start_line, end_line, matched_text)
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


    # Assicura che la cartella esista e scrive il JSON minimale invece di leggerlo
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_minimal = os.path.join(MINIMAL_JSON_BASE_DIR, "minimal_output.json")

    with open(output_minimal, "w", encoding="utf-8") as f:
        json.dump(minimal, f, indent=4, ensure_ascii=False)

    return minimal

def remove_main_license(main_spdx, path, scancode_data) -> dict:
    """
    Rimuove la licenza principale dal JSON di ScanCode,
    per evitare che il LLM le consideri.
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
    Filtra i risultati di Scancode usando regole caricate da un file JSON esterno.
    """

    # --- 1. CARICAMENTO E COMPILAZIONE REGOLE ---

    rules_path = os.path.join(os.path.dirname(__file__), 'license_rules.json')

    if not os.path.exists(rules_path):
        raise FileNotFoundError(f"Impossibile trovare il file di regole: {rules_path}")

    with open(rules_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    # Compiliamo le liste di esclusione in un'unica regex ottimizzata con OR logic (|)
    # Questo è molto più veloce di fare un loop su ogni stringa.
    re_references = re.compile("|".join(rules.get("ignore_patterns", [])), re.IGNORECASE)
    re_docs_changelog = re.compile("|".join(rules.get("changelog_patterns", [])), re.IGNORECASE)

    # Compiliamo la regex per il tag SPDX
    re_spdx_tag = re.compile(rules.get("spdx_tag_pattern", ""), re.IGNORECASE)

    # Compiliamo i pattern per riconoscere TESTO LEGALE EFFETTIVO delle licenze
    valid_license_patterns = []
    for pattern in rules.get("valid_license_text_patterns", []):
        try:
            valid_license_patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass  # Skip pattern non validi

    # Compiliamo i pattern per riconoscere LINK VALIDI a licenze (RST, Markdown, URL)
    valid_link_patterns = []
    for pattern in rules.get("valid_license_link_patterns", []):
        try:
            valid_link_patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass  # Skip pattern non validi

    # Lunghezza minima del testo
    min_text_length = rules.get("min_matched_text_length", 20)

    filtered_files = {"files": []}

    # --- 2. ELABORAZIONE ---

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
            # 1. VALIDAZIONE POSITIVA (WHITELIST) - La facciamo PRIMA!
            # -----------------------------------------------------------------

            is_valid_declaration = False
            match_source = None

            # A. Controllo Tag SPDX Esplicito (Priorità Massima)
            spdx_tag_hit = re_spdx_tag.search(matched_text)
            if spdx_tag_hit:
                is_valid_declaration = True
                match_source = "SPDX-TAG"

            # B. Controllo Testo Legale Boilerplate (Es. "Permission hereby granted...")
            elif not is_valid_declaration:
                for pattern_re in valid_license_patterns:
                    if pattern_re.search(matched_text):
                        is_valid_declaration = True
                        match_source = "LEGAL-TEXT"
                        break

            # C. Controllo Link Validi (Es. link a file LICENSE o URL gnu.org)
            is_valid_license_link = False
            if not is_valid_declaration:
                for pattern_re in valid_link_patterns:
                    if pattern_re.search(matched_text):
                        is_valid_license_link = True
                        is_valid_declaration = True
                        match_source = "VALID-LINK"
                        break

            # -----------------------------------------------------------------
            # 2. FILTRO NEGATIVO (BLACKLIST) - Solo se non è già validato
            # -----------------------------------------------------------------

            # Se il testo è GIA' riconosciuto come valido (es. License :: OSI Approved),
            # SALTIAMO i controlli di ignoranza.
            if not is_valid_declaration:

                # Lunghezza minima
                if len(matched_text) < min_text_length:
                    continue

                # Scarta Riferimenti/Link generici
                # Qui è dove "License ::" veniva ucciso dal regex "^license:"
                if len(matched_text) < 300:
                    if re_references.search(matched_text):
                        continue

                # Scarta Linguaggio da Changelog
                if re_docs_changelog.search(matched_text):
                    continue

            # -----------------------------------------------------------------
            # 3. FILTRO FINALE ("Zero Trust")
            # -----------------------------------------------------------------

            # Se dopo tutto questo non è una dichiarazione valida, scarta.
            if not is_valid_declaration:
                continue

                # -----------------------------------------------------------------
            # 4. ASSEGNAZIONE ID SPDX FINALE
            # -----------------------------------------------------------------

            final_spdx = None

            # Verifica validità formale ID Scancode
            scancode_id_ok = False
            if spdx and "unknown" not in spdx.lower() and "scancode" not in spdx.lower():
                scancode_id_ok = True

            # Caso 1: Tag SPDX Esplicito
            if spdx_tag_hit:
                final_spdx = spdx_tag_hit.group(1) or spdx_tag_hit.group(3)

            # Caso 2: Scancode ID valido
            if not final_spdx and scancode_id_ok:
                final_spdx = spdx

            # Caso 3: Fallback
            if not final_spdx:
                final_spdx = "LicenseRef-scancode-unknown"

            if final_spdx:
                valid_matches.append({
                    "license_spdx": final_spdx.strip(),
                    "matched_text": matched_text
                })

        # Salvataggio se ci sono match validi e score sufficiente
        if valid_matches:
            filtered_files["files"].append({
                "path": file_path,
                "matches": valid_matches,
                "score": file_score
            })


    # --- 3. OUTPUT FILE ---
    # Definisci MINIMAL_JSON_BASE_DIR nel tuo codice globale o passalo come argomento se serve
    # Qui assumo esista nel contesto o uso una default locale
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

