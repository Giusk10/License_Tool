import os
import re
from typing import List, Dict
from app.services.llm.ollama_api import call_ollama_deepseek
from app.utility.config import CLONE_BASE_DIR


def ask_llm_for_suggestions(issue: dict , main_spdx: str) -> str:

    prompt = (
        f"Sei un esperto di licenze software. Un file nel progetto presenta un conflitto di licenza.\n"
        f"Il file '{issue['file_path']}' è rilasciato sotto la licenza '{issue['detected_license']}', "
        f"che è incompatibile con la licenza {main_spdx}.\n"
        f"Motivo del conflitto: {issue['reason']}\n\n"
        f"Fornisci **SOLO** le licenze alternative compatibili con la licenza {main_spdx} che potrebbero essere adottate per risolvere il conflitto. "
        f"**NON** fornire analisi, spiegazioni, intestazioni o testo aggiuntivo. "
        f"Rispondi esattamente con il seguente formato: 'Licenza1, Licenza2, Licenza3'"
    )

    suggestion = call_ollama_deepseek(prompt)

    return suggestion

def review_document(issue: dict, main_spdx: str, licenses: str) -> str:
    file_path = issue["file_path"]
    # Assicurati che CLONE_BASE_DIR sia definito globalmente o passato come argomento
    abs_path = os.path.join(CLONE_BASE_DIR, file_path)

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            document_content = f.read()
    except Exception as e:
        print(f"Errore lettura file {file_path}: {e}")
        return None

    print(f"Reviewing document: {file_path}")

    prompt = (
        "### RUOLO\n"
        "Agisci come un Senior Open Source Compliance Officer.\n\n"

        "### DATI\n"
        f"1. Licenza Rilevata (Incompatibile): '{issue['detected_license']}'\n"
        f"2. Licenza del Progetto (Target): '{main_spdx}'\n"
        f"3. Licenze alternative accettate: {licenses}\n"
        f"4. Contenuto/Snippet sotto esame:\n'''\n{document_content}\n'''\n\n"

        "### OBIETTIVO\n"
        "Analizzare il conflitto legale e fornire una raccomandazione strategica per risolverlo.\n\n"

        "### ISTRUZIONI\n"
        "1. NON riscrivere il codice o il testo del documento.\n"
        "2. Spiega sinteticamente l'azione necessaria per risolvere l'incompatibilità (es. 'Richiedere dual-licensing all'autore', 'Isolare il componente', 'Rilasciare sotto licenza X invece di Y').\n"
        "3. Sii diretto e pragmatico.\n\n"

        "### FORMATO DI OUTPUT (OBBLIGATORIO)\n"
        "La tua risposta deve essere STRETTAMENTE in questo formato, senza markdown (```) e senza altro testo:\n"
        "<advice>Il tuo suggerimento operativo qui.</advice>"
    )

    try:
        response = call_ollama_deepseek(prompt)

        if not response:
            return None

        # --- LOGICA DI ESTRAZIONE MIGLIORATA (REGEX) ---
        # Cerca tutto ciò che è compreso tra <advice> e </advice>.
        # re.DOTALL permette al punto (.) di includere anche le nuove righe.
        # re.IGNORECASE rende il tag case-insensitive (es. <Advice>).
        match = re.search(r"<advice>(.*?)</advice>", response, re.DOTALL | re.IGNORECASE)

        if match:
            # Restituisce solo il contenuto pulito dentro i tag
            return match.group(1).strip()
        else:
            # Fallback: Se il modello non usa i tag, prova a restituire tutto pulito
            # o None se vuoi essere severo. Qui logghiamo l'errore per debug.
            print(f"Warning: Formato <advice> non trovato nella risposta per {file_path}")
            return None

    except Exception as e:
        print(f"Errore durante la chiamata LLM: {e}")
        return None

def enrich_with_llm_suggestions(main_spdx : str, issues: List[Dict], regenerated_map: Dict[str, str] = None) -> List[Dict]:
    """
    Per ogni issue ritorna un dizionario con campi:
      - file_path, detected_license, compatible, reason
      - suggestion: testo suggerito
      - regenerated_code_path: codice rigenerato se presente in `regenerated_map`
    `regenerated_map` è opzionale.
    """
    if regenerated_map is None:
        regenerated_map = {}

    enriched = []

    licenses = ""

    for issue in issues:
        file_path = issue["file_path"]
        detected_license = issue["detected_license"]
        
        if issue.get("compatible"):
            enriched.append({
                "file_path": issue["file_path"],
                "detected_license": issue["detected_license"],
                "compatible": issue["compatible"],
                "reason": issue["reason"],
                "suggestion": "Il file è compatibile con la licenza principale del progetto. Nessuna azione necessaria.",
                # Se il file è stato rigenerato, inseriamo il codice qui
                licenses:"",
                "regenerated_code_path": regenerated_map.get(issue["file_path"]),
            })
        else:
            if not file_path.endswith(('.md', '.txt', '.rst', 'THIRD-PARTY-NOTICE', 'NOTICE')):
                licenses = ask_llm_for_suggestions(issue, main_spdx)

                enriched.append({
                    "file_path": issue["file_path"],
                    "detected_license": issue["detected_license"],
                    "compatible": issue["compatible"],
                    "reason": issue["reason"],
                    "suggestion": f"1) Valuta la possibilità di cambiare la licenza principale del progetto per adottare "
                                  f"la licenza '{detected_license}' (o una compatibile), così da risolvere il conflitto.\n"
                                  f"2) Cerca un componente alternativo o una libreria diversa che implementi la logica di "
                                  f"'{file_path}' ma che sia rilasciata con una licenza compatibile rispetto a quella attuale del progetto."
                                  f"\n3) Ecco alcune licenze alternative compatibili che potresti considerare: {licenses}",
                    # Se il file è stato rigenerato, inseriamo il codice qui
                    "licenses": licenses,
                    "regenerated_code_path": regenerated_map.get(issue["file_path"]),
                })

            else:

                suggestion = review_document(issue, main_spdx, licenses)

                enriched.append({
                    "file_path": issue["file_path"],
                    "detected_license": issue["detected_license"],
                    "compatible": issue["compatible"],
                    "reason": issue["reason"],
                    "suggestion": f"1) Valuta la possibilità di cambiare la licenza principale del progetto per adottare "
                                  f"la licenza '{detected_license}' (o una compatibile), così da risolvere il conflitto.\n"
                                  f"2) Cerca un componente alternativo o una libreria diversa che implementi la logica di "
                                  f"'{file_path}' ma che sia rilasciata con una licenza compatibile rispetto a quella attuale del progetto."
                                  f"\n3){suggestion}",
                    # Se il file è stato rigenerato, inseriamo il codice qui
                    "licenses": licenses,
                    "regenerated_code_path": regenerated_map.get(issue["file_path"]),
                })

    return enriched