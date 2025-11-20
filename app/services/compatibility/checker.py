"""
Modulo `checker` — entry point pubblico per il controllo di compatibilità.

Funzione principale:
- check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict

Comportamento:
- Normalizza la licenza principale
- Carica la matrice professionale (tramite `matrix.get_matrix`)
- Per ogni file, parse dell'espressione SPDX tramite `parser_spdx.parse_spdx`
  e valutazione tramite `evaluator.eval_node`
- Produce una lista di issue con i seguenti campi per ogni file:
  - file_path: percorso del file
  - detected_license: stringa dell'espressione rilevata
  - compatible: booleano (True se esito finale è yes)
  - reason: stringa con la trace dettagliata (utile per report + LLM)

Nota: in caso di matrici non disponibili o licenza principale mancante, la funzione
restituisce un set di issues con reason esplicativo.
"""

from typing import Dict
from .compat_utils import normalize_symbol
from .parser_spdx import parse_spdx
from .evaluator import eval_node
from .matrix import get_matrix


def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict:
    issues = []
    main_license_n = normalize_symbol(main_license)
    matrix = get_matrix()

    if not main_license_n or main_license_n in {"UNKNOWN", "NOASSERTION", "NONE"}:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": "Licenza principale non rilevata o non valida (UNKNOWN/NOASSERTION/NONE)",
            })
        return {"main_license": main_license or "UNKNOWN", "issues": issues}

    if not matrix or main_license_n not in matrix:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": "Matrice professionale non disponibile o licenza principale non presente nella matrice",
            })
        return {"main_license": main_license_n, "issues": issues}

    for file_path, license_expr in file_licenses.items():
        license_expr = (license_expr or "").strip()
        node = parse_spdx(license_expr)
        status, trace = eval_node(main_license_n, node)

        if status == "yes":
            compatible = True
            reason = "; ".join(trace)
        elif status == "no":
            compatible = False
            reason = "; ".join(trace)
        else:
            compatible = False
            hint = "conditional" if status == "conditional" else "unknown"
            reason = "; ".join(trace) + f"; Esito: {hint}. Richiede verifica di conformità/manuale."

        issues.append({
            "file_path": file_path,
            "detected_license": license_expr,
            "compatible": compatible,
            "reason": reason,
        })

    return {"main_license": main_license_n, "issues": issues}
