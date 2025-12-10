from typing import List, Dict

def enrich_with_llm_suggestions(issues: List[Dict], regenerated_map: Dict[str, str] = None) -> List[Dict]:
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
                "regenerated_code_path": regenerated_map.get(issue["file_path"]),
            })  
        else:
            enriched.append({
                "file_path": issue["file_path"],
                "detected_license": issue["detected_license"],
                "compatible": issue["compatible"],
                "reason": issue["reason"],
                "suggestion": f"1. Valuta la possibilità di cambiare la licenza principale del progetto per adottare "
                              f"la licenza '{detected_license}' (o una compatibile), così da risolvere il conflitto.\n"
                              f"2. Cerca un componente alternativo o una libreria diversa che implementi la logica di "
                              f"'{file_path}' ma che sia rilasciata con una licenza compatibile rispetto a quella attuale del progetto.",
                # Se il file è stato rigenerato, inseriamo il codice qui
                "regenerated_code_path": regenerated_map.get(issue["file_path"]),
            })

    return enriched