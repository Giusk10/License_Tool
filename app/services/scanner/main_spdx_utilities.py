from typing import List, Dict, Any, Optional, Tuple

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
    if not entries:
        return None

    valid_entries = [entry for entry in entries if isinstance(entry, dict)]
    if not valid_entries:
        return None

    sorted_entries = sorted(
        valid_entries,
        key=lambda e: (e.get("path", "") or "").count("/")
    )

    for entry in sorted_entries:
        res = _extract_first_valid_spdx(entry)
        if res:
            return res

    return None