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

    # 1. Definizione degli ignore pattern
    ignore_path = os.path.join(os.path.dirname(__file__), 'license_rules.json')
    with open(ignore_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)
    ignore_patterns = rules.get("ignored_patterns", [])

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
                scancode_data["files"].remove(file_entry)

    return scancode_data

def filter_with_llm(scancode_data: dict, main_spdx: str, path: str) -> dict:
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

    post_regex_cleaning = remove_mainspdx_from_filespdx(regex_filtered, main_spdx)
    return post_regex_cleaning

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

                if match.get("from_file") == path:

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

Gli altri campi (path, score) sono metadati.

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
          "license_spdx": "<SPDX>"
        }}
      ]
      "score": <score>
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

            # --- FASE A: FILTRO PRELIMINARE SUL TESTO ---

            # 0. Check se è un LINK VALIDO a una licenza (RST, Markdown, URL diretto)
            # Questi link sono utili e NON devono essere scartati
            is_valid_license_link = False
            for pattern_re in valid_link_patterns:
                if pattern_re.search(matched_text):
                    is_valid_license_link = True
                    break

            # 1. Lunghezza minima (salvo se contiene SPDX tag esplicito o è un link valido)
            if len(matched_text) < min_text_length and "SPDX-License-Identifier" not in matched_text and not is_valid_license_link:
                continue

            # 2. Scarta Riferimenti/Link generici ("see LICENSE", "http://...")
            # MA NON scartare se è un link valido a licenza riconosciuto
            # Applichiamo questo filtro solo se il testo è breve (< 300 char).
            if len(matched_text) < 300 and not is_valid_license_link:
                if re_references.search(matched_text):
                    continue

            # 3. Scarta Linguaggio da Changelog/Docs (deprecate, switch to...)
            # MA NON scartare se è un link valido a licenza
            if not is_valid_license_link:
                if re_docs_changelog.search(matched_text):
                    continue

            # --- FASE B: VALIDAZIONE E CORREZIONE SPDX ---

            final_spdx = None
            is_valid_spdx = True

            # Verifica validità base dello scancode trovato
            if not spdx or "unknown" in spdx.lower() or "scancode" in spdx.lower():
                is_valid_spdx = False

            # --- FASE C: VERIFICA CHE IL TESTO SIA LEGALE EFFETTIVO ---

            # Check se il testo contiene frasi legali tipiche di licenze
            has_valid_legal_text = False

            # I link validi a licenze sono considerati testo legale valido
            if is_valid_license_link:
                has_valid_legal_text = True

            # Check pattern di testo legale
            if not has_valid_legal_text:
                for pattern_re in valid_license_patterns:
                    if pattern_re.search(matched_text):
                        has_valid_legal_text = True
                        break

            # Check per tag SPDX esplicito nel testo
            spdx_tag_match = re_spdx_tag.search(matched_text)
            if spdx_tag_match:
                has_valid_legal_text = True
                # Se troviamo un tag SPDX esplicito, usiamo quello come SPDX finale
                if not is_valid_spdx:
                    final_spdx = spdx_tag_match.group(1)

            # Se non è testo legale valido e non c'è tag SPDX, scarta
            if not has_valid_legal_text and not is_valid_spdx:
                continue

            # Determina SPDX finale
            if is_valid_spdx:
                final_spdx = spdx
            elif not final_spdx and has_valid_legal_text:
                # Testo legale valido ma nessun SPDX trovato - lo teniamo con SPDX originale o unknown
                final_spdx = spdx if spdx else "LicenseRef-scancode-unknown"

            # Se abbiamo trovato un SPDX valido (originale o recuperato) lo aggiungiamo
            if final_spdx:
                valid_matches.append({
                    "license_spdx": final_spdx,
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

def remove_mainspdx_from_filespdx(data: dict, main_spdx: str) -> dict:
    # Nota il [:] alla fine: stiamo iterando su una COPIA della lista
    for file_entry in data.get("files", [])[:]:

        matches = file_entry.get("matches", [])
        should_remove = True

        for m in matches:
            if m.get("license_spdx") != main_spdx:
                should_remove = False
                break  # Trovato un motivo per rimuovere, smettiamo di cercare nei match

        if should_remove:
            data["files"].remove(file_entry) # Rimuoviamo il file una volta sola

    return data

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
