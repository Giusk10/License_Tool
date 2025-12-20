"""
Compatibility Utilities Module.

This module provides utility functions for parsing and normalizing license symbols
to ensure consistency across the application. It acts as a helper layer before
complex SPDX evaluation.
"""

from typing import List, Dict
from license_expression import Licensing

# Initialize the licensing parser
licensing = Licensing()

# Map of common aliases/synonyms to the canonical forms used in the matrix
_SYNONYMS: Dict[str, str] = {
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-2.0+": "GPL-2.0-or-later",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
}


def normalize_symbol(sym: str) -> str:
    """
    Normalizes a single license string into a canonical format.

    This function performs several transformations to ensure consistent keys
    for matrix lookups, including:
    - Trimming whitespace.
    - Standardizing 'with' clauses to uppercase 'WITH'.
    - Converting '+' suffixes to '-or-later'.
    - resolving aliases via a predefined synonym list.

    Args:
        sym (str): The raw license symbol or expression string.

    Returns:
        str: The normalized license symbol. Returns the input unchanged if None.
    """
    if not sym:
        return sym

    s = sym.strip()

    # Normalize variations of 'with' to 'WITH'
    if " with " in s:
        s = s.replace(" with ", " WITH ")
    if " With " in s:
        s = s.replace(" With ", " WITH ")
    if " with" in s and " WITH" not in s:
        s = s.replace(" with", " WITH")

    # Normalize version indicators
    if "+" in s and "-or-later" not in s:
        s = s.replace("+", "-or-later")

    return _SYNONYMS.get(s, s)


def extract_symbols(expr: str) -> List[str]:
    """
    Extracts individual license symbols from an SPDX expression.

    This function uses the `license_expression` library to identify unique
    symbols within a complex string (ignoring logical operators like AND/OR).

    Args:
        expr (str): The SPDX license expression to parse.

    Returns:
        List[str]: A list of identified license symbols. Returns an empty list
        if parsing fails or the expression is empty.
    """
    if not expr:
        return []

    try:
        tree = licensing.parse(expr, strict=False)
        # The 'symbols' attribute contains the list of license identifiers found
        return [str(sym) for sym in getattr(tree, "symbols", [])]

    except Exception:  # pylint: disable=broad-exception-caught
        # Intentionally catch all exceptions to prevent parsing errors from
        # crashing the entire workflow. This is a helper utility, not a validator.
        return []
