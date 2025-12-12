import os
from typing import List, Dict

from app.services.llm_helper import _call_ollama_deepseek
from app.core.config import CLONE_BASE_DIR


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

    suggestion = _call_ollama_deepseek(prompt)

    return suggestion

def review_document(issue: dict , main_spdx: str, licenses: str ) -> str:

    file_path = issue["file_path"]
    abs_path = os.path.join(CLONE_BASE_DIR, file_path)
    with open(abs_path, "r", encoding="utf-8") as f:
        document_content = f.read()

    print(f"Reviewing document: {file_path}")

    """
    Chiede a Ollama di rivedere un documento di codice per problemi di licenza.
    """
    prompt = (
        f"Sei un esperto di licenze software. "
        f"Il seguente documento è attualmente sotto licenza '{issue['detected_license']}', che è incompatibile con la licenza principale del progetto '{main_spdx}'.\n"
        f"Il tuo compito è rivedere il testo e suggerire modifiche o alternative in modo che sia rilasciabile sotto una licenza compatibile con '{main_spdx}' tra queste: {licenses}.\n"
        f"Ecco il testo originale:\n"
        f"```\n{document_content}\n```\n\n"
        f"Rispondi esattamente con il seguente formato: '<tuo suggerimento qui>'."
        f"Restituisci SOLO il suggerimento, senza markdown (```) e senza spiegazioni verbali extra."
    )
    try:
        response = _call_ollama_deepseek(prompt)
        if not response:
            return None

        # Pulizia Markdown se presente
        clean_response = response.strip()
        if clean_response.startswith("```"):
            # Rimuove la prima riga (```python o simile)
            clean_response = clean_response.split("\n", 1)[1]
            # Rimuove l'ultima riga (```)
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]

        return clean_response.strip()
    except Exception:
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
            if not file_path.endswith(('.md', '.txt', '.rst')):
                licenses = ask_llm_for_suggestions(issue, main_spdx)

                enriched.append({
                    "file_path": issue["file_path"],
                    "detected_license": issue["detected_license"],
                    "compatible": issue["compatible"],
                    "reason": issue["reason"],
                    "suggestion": f"1. Valuta la possibilità di cambiare la licenza principale del progetto per adottare "
                                  f"la licenza '{detected_license}' (o una compatibile), così da risolvere il conflitto.\n"
                                  f"2. Cerca un componente alternativo o una libreria diversa che implementi la logica di "
                                  f"'{file_path}' ma che sia rilasciata con una licenza compatibile rispetto a quella attuale del progetto."
                                  f"\n3. Ecco alcune licenze alternative compatibili che potresti considerare: {licenses}",
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
                    "suggestion": f"1. Valuta la possibilità di cambiare la licenza principale del progetto per adottare "
                                  f"la licenza '{detected_license}' (o una compatibile), così da risolvere il conflitto.\n"
                                  f"2. Cerca un componente alternativo o una libreria diversa che implementi la logica di "
                                  f"'{file_path}' ma che sia rilasciata con una licenza compatibile rispetto a quella attuale del progetto."
                                  f"\n3. Ecco un suggerimento da adottare: {suggestion}",
                    # Se il file è stato rigenerato, inseriamo il codice qui
                    "licenses": licenses,
                    "regenerated_code_path": regenerated_map.get(issue["file_path"]),
                })

    return enriched