from typing import List, Dict

from app.services.llm_helper import _call_ollama_deepseek

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

    return enriched