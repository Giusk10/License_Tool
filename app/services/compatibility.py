from typing import Dict, List

def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict:
    """
    Returns:
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

    # Semplice tabella di compatibilità demo (espandibile)
    COMPATIBILITY_MATRIX = {
        "MIT": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
        "Apache-2.0": ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"],
        "BSD-3-Clause": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
        "BSD-2-Clause": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
        "GPL-3.0": ["GPL-3.0"],  # molto restrittiva
    }

    # Se ScanCode non ha trovato nulla
    if main_license == "UNKNOWN":
        allowed = []
    else:
        allowed = COMPATIBILITY_MATRIX.get(main_license, [])

    for file_path, license_id in file_licenses.items():

        # Compatibilità
        if main_license == "UNKNOWN":
            compatible = False
            reason = "Licenza principale non rilevata"
        else:
            compatible = license_id in allowed
            if compatible:
                reason = f"{license_id} è compatibile con {main_license}"
            else:
                reason = f"{license_id} non è compatibile con {main_license}"

        issues.append({
            "file_path": file_path,
            "detected_license": license_id,
            "compatible": compatible,
            "reason": reason
        })

    return {
        "main_license": main_license,
        "issues": issues
    }
