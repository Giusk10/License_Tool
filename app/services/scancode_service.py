import os
import json
import subprocess
import re
from re import match
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import SCANCODE_BIN, OUTPUT_BASE_DIR, MINIMAL_JSON_BASE_DIR
from app.services.llm_helper import _call_ollama_gpt

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

#  ------------ FUNZIONI PER FILTRARE I RISULTATI CON LLM -----------------

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

def filter_with_regex(scancode_data: dict, main_spdx: str, path: str) -> dict:
    """
    Filtra i risultati di ScanCode usando un LLM per rimuovere
    i falsi positivi basati sul testo della licenza rilevata.
    """
    minimal = build_minimal_json(scancode_data)
    #print(json.dumps(minimal, indent=4))
    scan_clean = remove_main_license(main_spdx, path, minimal)

    if main_spdx != "UNKNOWN":
        regex_filtered = filter_license_data(scan_clean, detected_main_spdx=True)
    else:
        regex_filtered = filter_license_data(scan_clean, detected_main_spdx=False)

    #post_regex_cleaning = remove_mainspdx_from_filespdx(regex_filtered, main_spdx)
    #return post_regex_cleaning
    return regex_filtered

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

def filter_license_data(data: dict, detected_main_spdx: bool) -> dict:
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

#  ------------ FUNZIONI PER RILEVARE LA LICENZA PRINCIPALE DAL JSON SCANCODE -----------------

def _is_valid(value: Optional[str]) -> bool:
    """Verifica se una stringa è un SPDX valido e non None/vuota/UNKNOWN."""
    return bool(value) and value != "UNKNOWN"

def _extract_first_valid_spdx(entry: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Ritorna il primo SPDX valido trovato nell'entry ScanCode,
    cercando nell'espressione rilevata, nelle license_detections e infine nelle licenses.

    Ritorna: (spdx_expression, path) o None.
    """
    if not isinstance(entry, dict):
        return None

    path = entry.get("path") or ""

    # 1. Controlla l'espressione di licenza principale
    spdx = entry.get("detected_license_expression_spdx")
    if _is_valid(spdx):
        return spdx, path

    # 2. Controlla le singole detections
    # Sebbene l'output root 'license_detections' possa essere rimosso,
    # questa chiave è ancora presente all'interno di ogni oggetto 'files'.
    for detection in entry.get("license_detections", []) or []:
        det_spdx = detection.get("license_expression_spdx")
        if _is_valid(det_spdx):
            return det_spdx, path

    # 3. Controlla le chiavi SPDX nelle licenze dettagliate
    for lic in entry.get("licenses", []) or []:
        spdx_key = lic.get("spdx_license_key")
        if _is_valid(spdx_key):
            return spdx_key, path

    return None

def _pick_best_spdx(entries: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """
    Ordina i file più vicini alla root (minore profondità del path) e
    ritorna la prima licenza SPDX valida trovata.

    Ritorna: (spdx_expression, path) o None.
    """
    if not entries:
        return None

    # Ordina: usa la profondità del path (conteggio degli "/") come chiave
    # Più basso è il conteggio, più vicino è alla root.
    sorted_entries = sorted(entries, key=lambda e: (e.get("path", "") or "").count("/"))

    for entry in sorted_entries:
        res = _extract_first_valid_spdx(entry)
        if res:
            # res è già una tupla (spdx, path)
            return res

    return None

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
            results[path] = " AND ".join(unique_spdx)

    return results
