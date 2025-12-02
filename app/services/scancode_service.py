import os
import json
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import SCANCODE_BIN, OUTPUT_BASE_DIR
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

    # 1. Carica il JSON generato
    with open(output_file, "r", encoding="utf-8") as f:
        scancode_data = json.load(f)

    # ⬇ Rimuovi la chiave "license_detections" dal JSON di primo livello
    scancode_data.pop("license_detections", None)

    # 2. Sovrascrivi il file JSON con i dati modificati
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scancode_data, f, indent=4, ensure_ascii=False)

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

    return ask_llm_to_filter_licenses(scan_clean)

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
                "matches": file_matches,
                "score": score
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
