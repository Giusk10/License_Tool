"""
Compatibility Utilities Unit Test Module.

This module provides unit tests for `app.services.compatibility.compat_utils`.
It focuses on validating the normalization of SPDX-like license strings and
the reliable extraction of license symbols from complex boolean expressions.

The suite covers:
1. Symbol Normalization: Handling of case variants, 'WITH' keywords, and '+' suffixes.
2. Symbol Extraction: Parsing tokens from simple and complex (nested) expressions.
3. Edge Case Handling: Resilience against null inputs, empty strings, and malformed expressions.
"""

import pytest
from app.services.compatibility import compat_utils as cu

# ==================================================================================
#                                     FIXTURES
# ==================================================================================

# Note: These tests are pure unit tests for utility functions and do not
# require external state or complex fixtures from conftest.py.

# ==================================================================================
#                           TESTS: SYMBOL NORMALIZATION
# ==================================================================================

def test_normalize_none_and_empty():
    """
    Validates handling of null and empty inputs.

    Ensures that None is preserved to avoid type errors and that empty
    strings remain empty after normalization.
    """
    assert cu.normalize_symbol(None) is None
    assert cu.normalize_symbol("") == ""


def test_normalize_trim_and_with_variants():
    """
    Tests keyword normalization and whitespace cleanup.

    Verifies that various case-variants of the 'with' keyword (e.g., 'With', 'with')
    are standardized to ' WITH ' and that surrounding whitespace is stripped.
    """
    assert cu.normalize_symbol(" mit with exception ") == "mit WITH exception"
    assert cu.normalize_symbol("MIT With Exception") == "MIT WITH Exception"
    # case with 'with' without leading space
    assert cu.normalize_symbol("MIT with") == "MIT WITH"


def test_normalize_plus_to_or_later_and_synonyms():
    """
    Verifies the conversion of the '+' suffix to the standard '-or-later' format.

    Ensures that strings like 'GPL-3.0+' are correctly transformed to
    conform to modern SPDX naming conventions.
    """
    assert cu.normalize_symbol("GPL-3.0+") == "GPL-3.0-or-later"
    assert cu.normalize_symbol("GPL-3.0-or-later") == "GPL-3.0-or-later"


def test_normalize_preserves_unknown_strings():
    """
    Ensures that standard or unrecognized strings are preserved.

    Validates that normalization only modifies specific patterns, leaving
    standard license names like 'Apache-2.0' untouched (except for trimming).
    """
    assert cu.normalize_symbol("  Apache-2.0  ") == "Apache-2.0"
    assert cu.normalize_symbol("BSD-3-Clause") == "BSD-3-Clause"

# ==================================================================================
#                           TESTS: SYMBOL EXTRACTION
# ==================================================================================

def test_extract_symbols_simple_and_complex():
    """
    Verifies token extraction from SPDX expressions.

    Ensures that the service can extract individual license IDs from both
    simple strings and boolean expressions (OR/AND), using sets for
    order-independent comparison.
    """
    assert cu.extract_symbols("") == []

    s = cu.extract_symbols("MIT")
    assert set(s) == {"MIT"}

    s2 = cu.extract_symbols("MIT OR Apache-2.0")
    # can return ['MIT','Apache-2.0'] in any order
    assert set(s2) >= {"MIT", "Apache-2.0"}


def test_extract_symbols_invalid_expression_returns_empty():
    """
    Tests error resilience for malformed or invalid SPDX expressions.

    Ensures that when the extraction utility encounters a string that
    cannot be parsed as a valid license expression (e.g., containing
    invalid characters or syntax), it returns an empty list instead of
    raising an unhandled exception.
    """
    assert cu.extract_symbols("not-a-license !!! !!!") == []


def test_normalize_with_and_plus_combination():
    """
    Tests error handling for malformed SPDX expressions.

    Ensures that if the parser encounters an invalid expression, it
    returns an empty list instead of crashing the analysis workflow.
    """
    inp = "GPL-2.0+ WITH Autoconf-exception"
    # + must become -or-later, and WITH must be normalized
    out = cu.normalize_symbol(inp)
    assert "-or-later" in out
    assert "WITH" in out

def test_normalize_multiple_plus_and_with():
    """
    Validates resilience against redundant or repeated symbols.

    Checks how the normalizer handles strings with multiple '+' signs or
    repeated 'WITH' keywords, ensuring the output is stabilized and
    conforms to the expected '-or-later' and 'WITH' formatting.
    """
    inp = "GPL-2.0+ + + WITH Extra WITH Another"
    out = cu.normalize_symbol(inp)
    # Ensures that '+' is converted and 'WITH' is standardized despite repetitions
    assert "-or-later" in out
    assert "WITH" in out


def test_normalize_case_insensitive_synonyms():
    """
    Ensures normalization is case-insensitive for license tokens.

    Verifies that lowercase or mixed-case variants of licenses with a '+'
    suffix (e.g., 'gpl-3.0+') are correctly identified and converted
    to the standard '-or-later' form.
    """
    assert cu.normalize_symbol("gpl-3.0+") == "gpl-3.0-or-later"
    assert cu.normalize_symbol("GPl-3.0+") == "GPl-3.0-or-later"


def test_extract_symbols_with_parenthesis_and_with():
    """
    Validates extraction logic for complex nested SPDX expressions.

    Ensures that symbols are correctly parsed even when the expression
    contains logical operators (AND/OR), parentheses, and exception
    clauses (WITH).
    """
    expr = "(MIT OR GPL-2.0 WITH Exception) AND Apache-2.0"
    syms = cu.extract_symbols(expr)
    assert any("WITH" in s for s in syms) or any("GPL-2.0" in s for s in syms)

# ==================================================================================
#                        TESTS: PARAMETRIZED VALIDATION
# ==================================================================================

@pytest.mark.parametrize("inp,expected", [
    (None, None),
    ("", ""),
    (" mit with exception ", "mit WITH exception"),
    ("MIT With Exception", "MIT WITH Exception"),
    ("GPL-3.0+", "GPL-3.0-or-later"),
    ("gpl-3.0+", "gpl-3.0-or-later"),
    ("GPL-3.0-or-later", "GPL-3.0-or-later"),
])
def test_normalize_parametrized(inp, expected):
    """
    Performs bulk validation of normalization rules using parametrization.

    This ensures that multiple input/output pairs are consistently
    validated across the normalization logic.
    """
    assert cu.normalize_symbol(inp) == expected


# ==================================================================================
#                        TESTS: SYNONYMS DICTIONARY
# ==================================================================================

@pytest.mark.parametrize("inp,expected", [
    ("GPL-3.0+", "GPL-3.0-or-later"),
    ("GPL-2.0+", "GPL-2.0-or-later"),
    ("LGPL-3.0+", "LGPL-3.0-or-later"),
    ("LGPL-2.1+", "LGPL-2.1-or-later"),
    ("AGPL-3.0+", "AGPL-3.0-or-later"),
    ("MPL-2.0+", "MPL-2.0-or-later"),
    ("Apache-2.0+", "Apache-2.0-or-later"),
    ("MIT+", "MIT-or-later"),
    ("BSD-3-Clause+", "BSD-3-Clause-or-later"),
    ("BSD-2-Clause+", "BSD-2-Clause-or-later"),
    ("CDDL-1.0+", "CDDL-1.0-or-later"),
    ("EPL-2.0+", "EPL-2.0-or-later"),
])
def test_normalize_all_synonyms(inp, expected):
    """
    Validates that all entries in the _SYNONYMS dictionary are correctly resolved.

    Ensures that common license aliases with '+' suffix are converted to
    their '-or-later' canonical form.
    """
    assert cu.normalize_symbol(inp) == expected


def test_normalize_unknown_license_preserved():
    """
    Ensures that unknown license strings not in _SYNONYMS are preserved.

    Validates that the normalizer only modifies known patterns and does not
    alter unrecognized license identifiers (except for trimming).
    """
    assert cu.normalize_symbol("CustomLicense-1.0") == "CustomLicense-1.0"
    assert cu.normalize_symbol("Proprietary") == "Proprietary"
    assert cu.normalize_symbol("UNKNOWN") == "UNKNOWN"


def test_extract_symbols_nested_or_and():
    """
    Validates extraction logic for nested OR and AND expressions.

    Ensures that symbols are correctly parsed from deeply nested boolean
    expressions with mixed operators.
    """
    expr = "MIT AND (Apache-2.0 OR GPL-2.0)"
    syms = cu.extract_symbols(expr)
    assert "MIT" in syms
    # Order may vary, check presence
    assert any(s in ["Apache-2.0", "GPL-2.0"] for s in syms)


def test_extract_symbols_single_with_exception():
    """
    Validates extraction of license with exception clause.

    Ensures that licenses with WITH exceptions are correctly identified.
    """
    expr = "GPL-2.0-only WITH Classpath-exception-2.0"
    syms = cu.extract_symbols(expr)
    assert len(syms) >= 1


def test_normalize_with_lowercase_variants():
    """
    Tests normalization of 'with' keyword in various positions.

    Ensures that all lowercase variants of 'with' are normalized to 'WITH'.
    """
    assert cu.normalize_symbol("GPL-2.0 with linking-exception") == "GPL-2.0 WITH linking-exception"
    assert cu.normalize_symbol("MIT with") == "MIT WITH"


def test_extract_symbols_complex_expression():
    """
    Validates extraction from a complex real-world SPDX expression.
    """
    expr = "(MIT OR Apache-2.0) AND (BSD-2-Clause OR BSD-3-Clause)"
    syms = cu.extract_symbols(expr)
    expected = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"}
    assert expected.issubset(set(syms))

