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
    """
    Ordina i file più vicini alla root (minore profondità del path) e
    ritorna la prima licenza SPDX valida trovata.

    Ritorna: (spdx_expression, path) o None.
    """
    if not entries:
        return None

    # Filtra solo le entry che sono dizionari
    entries = [e for e in entries if isinstance(e, dict)]

    # Ordina: usa la profondità del path (conteggio degli "/") come chiave
    # Più basso è il conteggio, più vicino è alla root.
    sorted_entries = sorted(entries, key=lambda e: (e.get("path", "") or "").count("/"))

    for entry in sorted_entries:
        res = _extract_first_valid_spdx(entry)
        if res:
            # res è già una tupla (spdx, path)
            return res

    return None
