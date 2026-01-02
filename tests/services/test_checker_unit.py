"""
License Compatibility Checker Unit Test Module.

This module provides unit tests for the `check_compatibility` function located in
`app.services.compatibility.checker`. It validates the logic used to compare
a project's main license against individual file licenses using a professional
compatibility matrix and SPDX expression parsing.

The suite covers:
1. Main License Validation: Handling of missing, invalid, or special SPDX values.
2. Matrix Availability: Behavior when the compatibility matrix is missing or incomplete.
3. Evaluation Outcomes: Correct processing of 'yes', 'no', 'conditional', and 'unknown' statuses.
4. SPDX Integration: Verification of recursive parsing calls for complex expressions.
5. Bulk Processing: Ensuring all files in a repository are processed and reported correctly.
"""

from unittest.mock import MagicMock
from app.services.compatibility.checker import check_compatibility

# ==================================================================================
#                                     FIXTURES
# ==================================================================================

# Note: This module relies on global fixtures defined in conftest.py:
# - complex_matrix_data: Provides a standardized mock of the compatibility matrix.
# - _msg_matches: Helper for bilingual (IT/EN) assertion of error messages.

# ==================================================================================
#                           TESTS: VALIDATION & INITIALIZATION
# ==================================================================================


def test_main_license_invalid_returns_issues(monkeypatch, _msg_matches):
    """
    Verifies behavior when the main license is missing or fails normalization.

    Ensures that if no valid main license is detected, the system flags all
    files with a status indicating the main license is invalid, rather than
    attempting a compatibility check.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "")
    res = check_compatibility("", {"a.py": "MIT"})
    assert res["main_license"] == "UNKNOWN"
    assert len(res["issues"]) == 1
    issue = res["issues"][0]
    assert issue["file_path"] == "a.py"
    assert issue["compatible"] is None
    assert _msg_matches(issue["reason"],
                        "Main license not detected or invalid",
                        "Licenza principale non rilevata")


def test_matrix_missing_or_license_not_in_matrix(monkeypatch, _msg_matches):
    """
    Tests behavior when the professional compatibility matrix is unavailable.

    Ensures that if 'get_matrix' returns None, the system reports a specific
    error indicating the matrix is missing rather than failing silently.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: None)
    res = check_compatibility("MIT", {"b.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1
    assert _msg_matches(res["issues"][0]["reason"],
                        "Professional matrix not available",
                        "Matrice professionale non disponibile")


def test_eval_yes_marks_compatible_and_includes_trace(complex_matrix_data, monkeypatch):
    """
    Validates a successful 'yes' (Compatible) outcome.

    Verifies that when the evaluator confirms compatibility, the issue is
    marked as True and the specific trace (e.g., 'direct match') is included.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("yes", ["direct match"]))
    res = check_compatibility("MIT", {"src/file.py": "MIT"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1
    issue = res["issues"][0]
    assert issue["file_path"] == "src/file.py"
    assert issue["compatible"] is True
    assert "direct match" in issue["reason"]


def test_eval_no_marks_incompatible_and_includes_trace(complex_matrix_data, monkeypatch):
    """
    Validates a 'no' (Incompatible) outcome.

    Ensures that license conflicts are correctly identified, marking the
    issue as incompatible and providing the conflict trace in the reason.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "GPL-3.0")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("no", ["conflict detected"]))
    res = check_compatibility("GPL-3.0", {"lib/x.py": "Apache-2.0"})
    issue = res["issues"][0]
    assert issue["compatible"] is False
    assert "conflict detected" in issue["reason"]


def test_eval_conditional_returns_hint_in_reason_and_not_compatible(complex_matrix_data, monkeypatch):
    """
    Verifies processing of 'conditional' compatibility.

    Ensures that conditional outcomes are treated as indeterminate (None)
    for safety, while providing the user with the necessary clauses/hints.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    mock_parse = MagicMock(return_value="NODE")
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", mock_parse)
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("conditional", ["some clause"]))

    res = check_compatibility("MIT", {"folder/thing.py": "  LGPL-2.1  "})
    mock_parse.assert_called_with("LGPL-2.1")
    issue = res["issues"][0]
    # conditional and unknown statuses now return compatible=None (indeterminate)
    assert issue["compatible"] is None
    assert "Outcome: conditional" in issue["reason"]

# ==================================================================================
#                              TESTS: DATA EDGE CASES
# ==================================================================================


def test_all_files_compatible_returns_no_issues(complex_matrix_data, monkeypatch):
    """
    Ensures correct reporting when all files are compatible.

    Verifies that the service still returns entries for all analyzed files,
    correctly marking them as compatible without raising false alarms.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: s.strip())
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("yes", ["direct match"]))

    res = check_compatibility("MIT", {"file1.py": "MIT", "file2.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert isinstance(res["issues"], list)
    assert len(res["issues"]) == 2
    assert all(issue["compatible"] is True for issue in res["issues"])


def test_matrix_present_but_main_not_in_matrix(monkeypatch, _msg_matches):
    """
    Handles cases where the main license is not defined in the professional matrix.

    Verifies that if the project's primary license is missing from the
    compatibility data, the checker generates an issue alerting the user
    that the specific license combination cannot be professionally validated.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: {"GPL-3.0": {"MIT": "no"}})
    res = check_compatibility("MIT", {"file.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1

    reason = res["issues"][0]["reason"].lower()
    assert _msg_matches(reason,
                        "main license not in",
                        "licenza principale non presente") or _msg_matches(reason,
                                                                       "matrix not available",
                                                                       "matrice professionale non disponibile")


def test_eval_unknown_status_shows_unknown_hint(complex_matrix_data, monkeypatch):
    """
    Validates fallback for unexpected evaluation statuses.

    Ensures that if the node evaluator returns an unrecognized status code,
    the service defaults to marking the file as indeterminate (None).
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("weird", ["trace info"]))
    res = check_compatibility("MIT", {"x.py": "Zlib"})
    issue = res["issues"][0]
    # Unknown statuses now return compatible=None (indeterminate)
    assert issue["compatible"] is None
    assert "Outcome: unknown" in issue["reason"]


def test_empty_detected_license_calls_parse_with_empty(monkeypatch, complex_matrix_data):
    """
    Tests handling of 'None' or empty detected licenses.

    Ensures that if the scanner fails to detect a license (returning None),
    the checker passes an empty string to the SPDX parser to avoid crashes.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    mock_parse = MagicMock(return_value="NODE")
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", mock_parse)
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("no", ["no trace"]))
    res = check_compatibility("MIT", {"empty.py": None})
    mock_parse.assert_called_with("")
    issue = res["issues"][0]
    assert issue["detected_license"] == ""
    assert "no trace" in issue["reason"]


def test_main_license_special_values_treated_as_invalid(monkeypatch, _msg_matches):
    """
    Handles SPDX special keywords (UNKNOWN, NOASSERTION, NONE).

    Ensures that non-descriptive primary license values trigger an
    invalidation error, as compatibility cannot be determined against them.
    """
    for val in ("UNKNOWN", "NOASSERTION", "NONE"):
        monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s, v=val: v)
        res = check_compatibility(val, {"a.py": "MIT"})
        assert res["main_license"] == val or res["main_license"] == val
        assert len(res["issues"]) == 1
        assert _msg_matches(res["issues"][0]["reason"],
                            "Main license not detected or invalid",
                            "Licenza principale non rilevata") or ("invalid" in res["issues"][0]["reason"].lower())
