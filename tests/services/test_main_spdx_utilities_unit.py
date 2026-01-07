"""
test: services/scanner/test_main_spdx_utilities_unit.py

Unit tests for the SPDX utility functions used in the scanner service.
These tests verify the logic for extracting and prioritizing valid SPDX license expressions
from ScanCode output structures, handling edge cases like missing paths, invalid values,
and directory depth prioritization.
"""

import pytest
from app.services.scanner import main_spdx_utilities as util
from app.services.compatibility import parser_spdx as ps


def test_extract_skips_invalid_spdx_values_before_falling_back():
    """
    Verify that _extract_first_valid_spdx skips invalid values (like 'UNKNOWN' or empty strings)
    in priority fields and correctly falls back to subsequent fields (e.g., license_detections).
    """
    entry = {
        "path": "dist/LICENSE",
        # Should be skipped because it is 'UNKNOWN'
        "detected_license_expression_spdx": "UNKNOWN",
        "license_detections": [
            {"license_expression_spdx": ""},        # Should be skipped (empty)
            {"license_expression_spdx": "MPL-2.0"}  # Valid target
        ],
        "licenses": [{"spdx_license_key": "Apache-2.0"}]
    }
    assert util._extract_first_valid_spdx(entry) == ("MPL-2.0", "dist/LICENSE")


def test_pick_best_returns_none_for_empty_entries():
    """
    Verify that _pick_best_spdx returns None when the input list is empty or None.
    """
    assert util._pick_best_spdx([]) is None
    assert util._pick_best_spdx(None) is None


def test_pick_best_skips_non_mapping_entries():
    """
    Verify that _pick_best_spdx ignores entries that are not dictionaries (e.g., None, strings)
    and successfully picks a valid license from the remaining valid entries.
    """
    entries = [
        None,
        "not-a-dict",
        # Valid entry but likely lower priority due to no explicit detected expression
        {"path": "LICENSE", "licenses": [{"spdx_license_key": "Apache-2.0"}]},
        # Another valid entry
        {"path": "components/lib/LICENSE", "detected_license_expression_spdx": "MIT"}
    ]
    # Expects Apache-2.0 because LICENSE (depth 0) is preferred over components/lib/LICENSE (depth 2)
    assert util._pick_best_spdx(entries) == ("Apache-2.0", "LICENSE")


def test_is_valid_filters_none_empty_unknown():
    """
    Verify that _is_valid correctly identifies valid SPDX strings.
    It should reject None, empty strings, and 'UNKNOWN'.
    """
    assert util._is_valid("MIT") is True
    assert util._is_valid("UNKNOWN") is False
    assert util._is_valid("") is False
    assert util._is_valid(None) is False


def test_extract_returns_main_expression():
    """
    Verify that _extract_first_valid_spdx returns the high-priority
    'detected_license_expression_spdx' if it contains a valid value.
    """
    entry = {
        "path": "LICENSE",
        "detected_license_expression_spdx": "Apache-2.0"
    }
    assert util._extract_first_valid_spdx(entry) == ("Apache-2.0", "LICENSE")


def test_extract_falls_back_to_license_detections():
    """
    Verify fallback logic: if the main expression is missing/invalid,
    check the 'license_detections' list for a valid expression.
    """
    entry = {
        "path": "src/module/file.py",
        "license_detections": [
            {"license_expression_spdx": None},          # Invalid
            {"license_expression_spdx": "GPL-3.0-only"} # Valid
        ]
    }
    assert util._extract_first_valid_spdx(entry) == ("GPL-3.0-only", "src/module/file.py")


def test_extract_uses_license_list_when_needed():
    """
    Verify deep fallback: if both detected expression and detections list fail,
    fall back to the raw 'licenses' list (ScanCode standard key).
    """
    entry = {
        "path": "docs/NOTICE",
        "licenses": [
            {"spdx_license_key": None},          # Invalid
            {"spdx_license_key": "BSD-3-Clause"} # Valid
        ]
    }
    assert util._extract_first_valid_spdx(entry) == ("BSD-3-Clause", "docs/NOTICE")


def test_extract_returns_none_for_invalid_entry():
    """
    Verify that _extract_first_valid_spdx returns None if the entry structure
    is invalid (not a dict) or contains no recognized license fields.
    """
    assert util._extract_first_valid_spdx("not-a-dict") is None
    assert util._extract_first_valid_spdx({"path": "file"}) is None


def test_extract_returns_empty_path_when_missing():
    """
    Verify that if the 'path' key is missing in the entry, the function
    defaults to an empty string for the path component of the result.
    """
    entry = {
        "detected_license_expression_spdx": "CC0-1.0"
    }
    assert util._extract_first_valid_spdx(entry) == ("CC0-1.0", "")


def test_extract_prefers_detected_expression_over_other_fields():
    """
    Verify the priority order of extraction:
    1. detected_license_expression_spdx
    2. license_detections
    3. licenses
    """
    entry = {
        "path": "component/LICENSE",
        "detected_license_expression_spdx": "AGPL-3.0-only", # Should be picked
        "license_detections": [{"license_expression_spdx": "MIT"}],
        "licenses": [{"spdx_license_key": "Apache-2.0"}]
    }
    assert util._extract_first_valid_spdx(entry) == ("AGPL-3.0-only", "component/LICENSE")


def test_pick_best_prefers_shallow_path():
    """
    Verify that _pick_best_spdx prioritizes files closer to the root (shallower depth).
    'LICENSE' (depth 0) should beat 'nested/dir/COMPONENT' (depth 2).
    """
    entries = [
        {
            "path": "nested/dir/COMPONENT",
            "license_detections": [{"license_expression_spdx": "MIT"}]
        },
        {
            "path": "LICENSE",
            "detected_license_expression_spdx": "Apache-2.0"
        }
    ]
    assert util._pick_best_spdx(entries) == ("Apache-2.0", "LICENSE")


def test_pick_best_returns_none_when_no_valid_spdx():
    """
    Verify that _pick_best_spdx returns None if none of the provided entries
    contain a valid SPDX expression.
    """
    entries = [
        {"path": "file1", "detected_license_expression_spdx": None},
        {"path": "dir/file2", "licenses": [{"spdx_license_key": None}]}
    ]
    assert util._pick_best_spdx(entries) is None


def test_pick_best_handles_missing_path_values():
    """
    Verify how _pick_best_spdx handles entries where 'path' is None.
    It should handle them gracefully without crashing, potentially treating them as high priority (depth -1 or 0 equivalent).
    """
    entries = [
        {
            "path": None, # Treated as root/empty path
            "licenses": [{"spdx_license_key": "MPL-2.0"}]
        },
        {
            "path": "docs/LICENSES/license.txt",
            "detected_license_expression_spdx": "Apache-2.0"
        }
    ]
    assert util._pick_best_spdx(entries) == ("MPL-2.0", "")


def test_pick_best_keeps_order_for_same_depth():
    """
    Verify that for entries at the same directory depth, the original order is preserved
    (stable selection strategy).
    """
    entries = [
        {"path": "A", "detected_license_expression_spdx": "EPL-2.0"},
        {"path": "B", "detected_license_expression_spdx": "LGPL-3.0"}
    ]
    assert util._pick_best_spdx(entries) == ("EPL-2.0", "A")


def test_node_repr_methods(monkeypatch):
    """
    Verifies the __repr__ methods of the AST nodes (Leaf, And, Or).
    This covers the string representation logic which is useful for debugging.
    """
    # Mock normalize_symbol to return value as-is for predictable repr
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    # Test Leaf repr
    leaf = ps.Leaf("MIT")
    assert repr(leaf) == "Leaf(MIT)"

    # Test And repr
    and_node = ps.And(ps.Leaf("A"), ps.Leaf("B"))
    assert repr(and_node) == "And(Leaf(A), Leaf(B))"

    # Test Or repr
    or_node = ps.Or(ps.Leaf("X"), ps.Leaf("Y"))
    assert repr(or_node) == "Or(Leaf(X), Leaf(Y))"


def test_parse_primary_implicit_none(monkeypatch):
    """
    Forces the 'parse_primary' function to hit its final 'return None' statement.

    In normal operation, '_tokenize' never produces empty strings, so 'consume()'
    always returns a truthy value or None (caught by 'peek').
    We mock '_tokenize' to return an empty string to simulate a falsy token
    that bypasses the 'if val:' check.
    """
    # Mock tokenize to return a list containing an empty string
    monkeypatch.setattr(ps, "_tokenize", lambda s: [""])

    # This triggers parse_primary -> consume() returns "" (falsy)
    # -> if val: is False -> returns None
    result = ps.parse_spdx("dummy_input")

    assert result is None