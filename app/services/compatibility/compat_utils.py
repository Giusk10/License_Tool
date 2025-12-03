"""
Module `compat_utils` — parsing and normalization utilities.

Main functions:
- normalize_symbol(sym: str) -> str
    Normalizes an SPDX symbol by applying common transformations (e.g., '+' -> '-or-later')
    and mapping frequent aliases to canonical forms used in the matrix.

- extract_symbols(expr: str) -> List[str]
    Uses the `license_expression` library to extract symbols present in an SPDX expression.
    Returns a list of strings representing the identified symbols.

These utilities are intentionally simple; the more complex parser for AND/OR/WITH
logic is implemented in `parser_spdx.py`.
"""

from typing import List
from license_expression import Licensing

licensing = Licensing()

# Common aliases/synonyms -> canonical form used in the matrix
_SYNONYMS = {
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-2.0+": "GPL-2.0-or-later",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
}


def normalize_symbol(sym: str) -> str:
    """
    Normalizes a single license string.

    Transformations performed (non-exhaustive):
      - whitespace trimming
      - normalization of 'with' constructs -> 'WITH'
      - conversion of '+' to '-or-later'
      - mapping of common aliases via _SYNONYMS

    The goal is to obtain consistent keys for matrix lookup.
    """
    if not sym:
        return sym
    s = sym.strip()
    # Normalize multiple spaces around WITH
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
    Extracts the symbols (identifiers) present in an SPDX expression.

    Note: This function does not handle logical structure (AND/OR/WITH). It serves
    as a backward compatibility utility and for simple debugging/logging.
    """
    if not expr:
        return []
    try:
        tree = licensing.parse(expr, strict=False)
    except Exception:
        return []
    return [str(sym) for sym in getattr(tree, "symbols", [])]