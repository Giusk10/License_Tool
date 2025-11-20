"""
Modulo `compat_utils` — utilità di parsing e normalizzazione.

Funzioni principali:
- normalize_symbol(sym: str) -> str
    Normalizza uno symbol SPDX applicando trasformazioni comuni (es. '+' -> '-or-later') e
    mappando alcuni alias frequenti a forme canoniche usate nella matrice.

- extract_symbols(expr: str) -> List[str]
    Usa la libreria `license_expression` per estrarre i simboli presenti in una espressione SPDX.
    Restituisce una lista di stringhe rappresentanti i symbol identificati.

Queste utilità sono intenzionalmente semplici: il parser più complesso per AND/OR/WITH
è implementato in `parser_spdx.py`.
"""

from typing import List
from license_expression import Licensing

licensing = Licensing()

# Alias/sinonimi comuni -> forma canonica usata nella matrice
_SYNONYMS = {
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-2.0+": "GPL-2.0-or-later",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
}


def normalize_symbol(sym: str) -> str:
    """
    Normalizza una singola stringa di licenza.

    Trasformazioni eseguite (non esaustive):
      - trim degli spazi
      - normalizzazione di costrutti 'with' -> 'WITH'
      - conversione di '+' in '-or-later'
      - mappatura di alias comuni tramite _SYNONYMS

    L'obiettivo è ottenere chiavi consistenti da cercare nella matrice.
    """
    if not sym:
        return sym
    s = sym.strip()
    # normalizza spazi multipli attorno a WITH
    if " with " in s:
        s = s.replace(" with ", " WITH ")
    if " With " in s:
        s = s.replace(" With ", " WITH ")
    if " with" in s and " WITH" not in s:
        s = s.replace(" with", " WITH")
    if "+" in s and "-or-later" not in s:
        s = s.replace("+", "-or-later")
    return _SYNONYMS.get(s, s)


def extract_symbols(expr: str) -> List[str]:
    """
    Estrae i symbol (identificatori) presenti in una espressione SPDX.

    Nota: questa funzione non gestisce la struttura logica (AND/OR/WITH). Serve
    come utilità di retrocompatibilità e per semplici debug/log.
    """
    if not expr:
        return []
    try:
        tree = licensing.parse(expr, strict=False)
    except Exception:
        return []
    return [str(sym) for sym in getattr(tree, "symbols", [])]
