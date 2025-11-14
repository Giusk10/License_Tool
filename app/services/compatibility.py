from typing import Dict, List
from license_expression import Licensing


licensing = Licensing()

# Tabella di compatibilità SEMPLIFICATA
# chiave = licenza principale del progetto
# valore = licenze che consideriamo compatibili con quella principale
COMPATIBILITY_MATRIX = {
    "MIT": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "Apache-2.0": ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"],
    "BSD-3-Clause": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "BSD-2-Clause": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "GPL-3.0-only": ["GPL-3.0-only", "GPL-3.0-or-later"],
    "GPL-3.0-or-later": ["GPL-3.0-only", "GPL-3.0-or-later"],
}


def _extract_symbols(expr: str) -> List[str]:
    """
    Restituisce i singoli identificatori di licenza da una espressione SPDX.

    Esempio:
      "LGPL-2.0-or-later AND MIT" -> ["LGPL-2.0-or-later", "MIT"]
    """
    if not expr:
        return []

    try:
        tree = licensing.parse(expr, strict=False)
    except Exception:
        return []

    return [str(sym) for sym in tree.symbols]


def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict:
    """
    Calcola la compatibilità tra la licenza principale e le licenze dei singoli file.

    Restituisce:
    {
        "main_license": <spdx>,
        "issues": [
            {
                "file_path": "...",
                "detected_license": "...",
                "compatible": True/False,
                "reason": "..."
            }
        ]
    }
    """

    issues = []

    # Caso 1: nessuna licenza principale trovata
    if not main_license or main_license == "UNKNOWN":
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": "Licenza principale non rilevata (UNKNOWN)",
            })
        return {
            "main_license": "UNKNOWN",
            "issues": issues,
        }

    # Prendiamo la lista di licenze compatibili con la principale
    allowed = COMPATIBILITY_MATRIX.get(main_license)
    if not allowed:
        # Licenza principale non gestita nella nostra matrice
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": f"Licenza principale {main_license} non gestita dalla matrice di compatibilità",
            })
        return {
            "main_license": main_license,
            "issues": issues,
        }

    allowed_set = set(allowed)

    for file_path, license_expr in file_licenses.items():
        symbols = _extract_symbols(license_expr)

        # Nessun simbolo estratto → prova a trattare l'espressione come singola licenza
        if not symbols:
            compatible = license_expr in allowed_set
            if compatible:
                reason = f"{license_expr} è compatibile con {main_license}"
            else:
                reason = f"{license_expr} non è compatibile con {main_license} (o espressione non riconosciuta)"
        else:
            # Strategia semplice: tutte le licenze presenti devono essere consentite
            incompatible_syms = [s for s in symbols if s not in allowed_set]
            compatible = len(incompatible_syms) == 0

            if compatible:
                if len(symbols) == 1:
                    reason = f"{symbols[0]} è compatibile con {main_license}"
                else:
                    reason = (
                        f"Tutte le licenze {', '.join(symbols)} sono compatibili con {main_license}"
                    )
            else:
                reason = (
                    f"Le seguenti licenze non sono compatibili con {main_license}: "
                    f"{', '.join(incompatible_syms)}"
                )

        issues.append({
            "file_path": file_path,
            "detected_license": license_expr,
            "compatible": compatible,
            "reason": reason,
        })

    return {
        "main_license": main_license,
        "issues": issues,
    }
