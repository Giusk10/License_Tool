"""
Modulo principale delle utilità SPDX.

Questo modulo fornisce funzioni di utilità per estrarre e convalidare gli identificatori di licenza SPDX
dall'output JSON di ScanCode Toolkit. Include la logica per assegnare priorità ai file radice
e attraversare strutture di dizionario nidificate per trovare tag di licenza validi.
"""

from typing import List, Dict, Any, Optional, Tuple


def _is_valid(value: Optional[str]) -> bool:
    """
    Verifica se una stringa di licenza è un identificatore SPDX valido.

    Argomenti:
    valore (facoltativo[str]): la stringa di licenza da verificare.

    Restituisce:
    bool: True se il valore non è None, non è vuoto e non è "UNKNOWN".
    """
    return bool(value) and value != "UNKNOWN"


def _extract_first_valid_spdx(entry: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Recupera il primo identificatore SPDX valido trovato in una voce ScanCode.

    La ricerca avviene nel seguente ordine:
    1. Espressione di licenza rilevata di primo livello.
    2. Elenco 'license_detections'.
    3. Elenco dei dettagli 'licenses'.

    Argomenti:
    entry (Dict[str, Any]): una singola voce di file dal JSON ScanCode.

    Restituisce:
    Optional[Tuple[str, str]]: una tupla (spdx_expression, file_path) se trovata,
    altrimenti nessuna.
    """
    if not isinstance(entry, dict):
        return None

    path = entry.get("path") or ""

    # 1. Controlla l'espressione principale della licenza rilevata
    spdx = entry.get("detected_license_expression_spdx")
    if _is_valid(spdx):
        return spdx, path

    # 2. Controllare i singoli rilevamenti
    # Anche se la chiave radice 'license_detections' viene rimossa durante la post-elaborazione,
    # questa chiave rimane spesso all'interno dei singoli oggetti 'files'.
    detections = entry.get("license_detections", []) or []
    for detection in detections:
        det_spdx = detection.get("license_expression_spdx")
        if _is_valid(det_spdx):
            return det_spdx, path

    # 3. Controlla le chiavi SPDX nell'elenco dettagliato delle licenze
    licenses = entry.get("licenses", []) or []
    for lic in licenses:
        spdx_key = lic.get("spdx_license_key")
        if _is_valid(spdx_key):
            return spdx_key, path

    return None


def _pick_best_spdx(entries: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """
    Seleziona la licenza migliore da un elenco di candidati, dando priorità ai file radice.

    Ordina le voci in base alla profondità della directory (percorso più superficiale per primo)
    e restituisce il primo identificatore SPDX valido trovato.

    Argomenti:
    voci (Elenco[Dict[str, Qualsiasi]]): un elenco di voci del file ScanCode.

    Restituisce:
    Opzionale[Tupla[str, str]]: una tupla (espressione_spdx, percorso_file) se trovata,
    altrimenti Nessuna.
    """
    if not entries:
        return None

    # Filtro che garantisce che vengano elaborati solo i dizionari
    valid_entries = [e for e in entries if isinstance(e, dict)]

    # Ordina le voci in base alla profondità del percorso (numero di barre).
    # I file con meno barre sono più vicini alla radice e generalmente più autorevoli
    # (ad esempio, ./LICENSE vs. ./src/vendor/lib/LICENSE).
    sorted_entries = sorted(
        valid_entries,
        key=lambda e: (e.get("path", "") or "").count("/")
    )

    for entry in sorted_entries:
        result = _extract_first_valid_spdx(entry)
        if result:
            # result is already a tuple (spdx, path)
            return result

    return None
