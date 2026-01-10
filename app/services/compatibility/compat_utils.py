"""
Compatibility Utilities Module.

Questo modulo fornisce funzioni di utilità per il parsing e la normalizzazione dei simboli di licenza
per garantire coerenza in tutta l'applicazione. Agisce come livello di supporto prima
della valutazione SPDX complessa.
"""

from typing import List, Dict
from license_expression import Licensing

# Inizializza il parser delle licenze
licensing = Licensing()

# Mappa di alias/sinonimi comuni alle forme canoniche utilizzate nella matrice
_SYNONYMS: Dict[str, str] = {
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-2.0+": "GPL-2.0-or-later",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
    "AGPL-3.0+": "AGPL-3.0-or-later",
    "MPL-2.0+": "MPL-2.0-or-later",
    "Apache-2.0+": "Apache-2.0-or-later",
    "MIT+": "MIT-or-later",
    "BSD-3-Clause+": "BSD-3-Clause-or-later",
    "BSD-2-Clause+": "BSD-2-Clause-or-later",
    "CDDL-1.0+": "CDDL-1.0-or-later",
    "EPL-2.0+": "EPL-2.0-or-later",
}


def normalize_symbol(sym: str) -> str:
    """
    Normalizza una singola stringa di licenza in un formato canonico.

    Questa funzione esegue diverse trasformazioni per garantire chiavi coerenti
    per le ricerche nella matrice, tra cui:
    - Rimozione degli spazi bianchi.
    - Standardizzazione delle clausole 'with' in maiuscolo 'WITH'.
    - Conversione dei suffissi '+' in '-or-later'.
    - Risoluzione degli alias tramite un elenco di sinonimi predefinito.

    Args:
        sym (str): Il simbolo della licenza grezzo o la stringa dell'espressione.

    Returns:
        str: Il simbolo della licenza normalizzato. Restituisce l'input invariato se None.
    """
    if not sym:
        return sym

    s = sym.strip()

    # Normalizza le variazioni di 'with' in 'WITH'
    if " with " in s:
        s = s.replace(" with ", " WITH ")
    if " With " in s:
        s = s.replace(" With ", " WITH ")
    if " with" in s and " WITH" not in s:
        s = s.replace(" with", " WITH")

    # Normalizza gli indicatori di versione
    if "+" in s and "-or-later" not in s:
        s = s.replace("+", "-or-later")

    return _SYNONYMS.get(s, s)


def extract_symbols(expr: str) -> List[str]:
    """
    Estrae i singoli simboli di licenza da un'espressione SPDX.

    Questa funzione utilizza la libreria `license_expression` per identificare simboli
    univoci all'interno di una stringa complessa (ignorando operatori logici come AND/OR).

    Args:
        expr (str): L'espressione di licenza SPDX da analizzare.

    Returns:
        List[str]: Un elenco di simboli di licenza identificati. Restituisce un elenco vuoto
        se il parsing fallisce o l'espressione è vuota.
    """
    if not expr:
        return []

    try:
        tree = licensing.parse(expr, strict=False)
        # L'attributo 'symbols' contiene l'elenco degli identificatori di licenza trovati
        return [str(sym) for sym in getattr(tree, "symbols", [])]

    except Exception:  # pylint: disable=broad-exception-caught
        # Cattura intenzionalmente tutte le eccezioni per prevenire che errori di parsing
        # blocchino l'intero flusso di lavoro. Questa è un'utility di supporto, non un validatore.
        return []
