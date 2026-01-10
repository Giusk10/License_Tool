"""
Compatibility Checker Module.

Questo modulo funge da interfaccia pubblica per verificare la compatibilità delle licenze.
Orchestra il processo normalizzando i simboli delle licenze, caricando la matrice di compatibilità,
analizzando le espressioni SPDX dai file e valutandole rispetto alla licenza principale del progetto.
"""

from typing import Dict, Any, List

from .compat_utils import normalize_symbol
from .parser_spdx import parse_spdx
from .evaluator import eval_node
from .matrix import get_matrix


def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> Dict[str, Any]:
    """
    Valuta la compatibilità delle licenze a livello di file rispetto alla licenza principale del progetto.

    Il processo prevede:
    1. Normalizzazione del simbolo della licenza principale.
    2. Recupero della matrice di compatibilità.
    3. Iterazione su ogni espressione di licenza del file per:
        - Analizzare la stringa SPDX in un albero logico (Node).
        - Valutare l'albero usando `eval_node` per determinare lo stato (yes, no, conditional)
          e generare una traccia.

    Args:
        main_license (str): Il simbolo della licenza principale del progetto (es. "MIT").
        file_licenses (Dict[str, str]): Un dizionario che mappa i percorsi dei file alle loro
            espressioni di licenza rilevate (es. {"src/file.js": "MIT AND Apache-2.0"}).

    Returns:
        Dict[str, Any]: Un dizionario contenente:
            - "main_license" (str): L'identificatore della licenza principale normalizzato.
            - "issues" (List[Dict]): Un elenco di dizionari che rappresentano il risultato di compatibilità
              per ogni file. Ogni dizionario contiene:
                - file_path (str)
                - detected_license (str)
                - compatible (bool)
                - reason (str)
    """
    issues: List[Dict[str, Any]] = []
    main_license_n = normalize_symbol(main_license)
    matrix = get_matrix()

    # Caso 1: La licenza principale è mancante o non valida
    if not main_license_n or main_license_n in {"UNKNOWN", "NOASSERTION", "NONE"}:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": None,
                "reason": "Main license not detected or invalid (UNKNOWN/NOASSERTION/NONE)",
            })
        return {"main_license": main_license or "UNKNOWN", "issues": issues}

    # Caso 2: Matrice non disponibile o licenza principale non supportata nella matrice
    if not matrix or main_license_n not in matrix:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": None,
                "reason": (
                    "Professional matrix not available or "
                    "main license not present in the matrix"
                ),
            })
        return {"main_license": main_license_n, "issues": issues}

    # Caso 3: Valutazione standard
    for file_path, license_expr in file_licenses.items():
        license_expr = (license_expr or "").strip()

        # Analizza l'espressione SPDX in un albero logico
        node = parse_spdx(license_expr)

        # Valuta la compatibilità rispetto alla licenza principale
        status, trace = eval_node(main_license_n, node)

        compatible = False
        reason = ""

        if status == "yes":
            compatible = True
            reason = "; ".join(trace)
        elif status == "no":
            compatible = False
            reason = "; ".join(trace)
        else:
            # Gestisce stati "condizionali" o sconosciuti
            compatible = None
            hint = "conditional" if status == "conditional" else "unknown"
            reason = (
                f"{'; '.join(trace)}; "
                f"Outcome: {hint}. Requires compliance/manual verification."
            )

        issues.append({
            "file_path": file_path,
            "detected_license": license_expr,
            "compatible": compatible,
            "reason": reason,
        })

    return {"main_license": main_license_n, "issues": issues}
