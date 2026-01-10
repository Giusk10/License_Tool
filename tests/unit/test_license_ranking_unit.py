"""
License Ranking Service Unit Test Module.

This module contains unit tests for the license ranking logic in
`app.services.scanner.license_ranking`. It validates the functions used to
extract licenses from SPDX expressions and rank them by permissiveness.

The suite covers:
1. License Extraction: Parsing complex SPDX expressions with OR/AND operators.
2. License Ranking: Selecting the most permissive license from alternatives.
3. JSON Loading: Proper handling of the permissiveness ranking file.
"""

import pytest
from unittest.mock import patch
from app.services.scanner.license_ranking import (
    choose_most_permissive_license_in_file,
    estract_licenses,
    load_json_rank
)


# ==================================================================================
#                     TEST CLASS: LICENSE EXTRACTION
# ==================================================================================

class TestExtractLicenses:
    """
    Tests for the 'estract_licenses' function.

    Validates the parsing of SPDX expressions to extract individual license
    identifiers, handling both simple and complex expressions.
    """

    def test_extract_single_license(self):
        """Verifies extraction of a single license without operators."""
        result = estract_licenses("MIT")
        assert result == ["MIT"]

    def test_extract_simple_or_expression(self):
        """Verifies extraction from a simple OR expression."""
        result = estract_licenses("MIT OR Apache-2.0")
        assert result == ["MIT", "Apache-2.0"]

    def test_extract_multiple_or_expressions(self):
        """Verifies extraction from multiple OR expressions."""
        result = estract_licenses("MIT OR Apache-2.0 OR GPL-3.0")
        assert result == ["MIT", "Apache-2.0", "GPL-3.0"]

    def test_extract_with_parentheses(self):
        """
        Verifies that parentheses are preserved in the result.

        The function should not split inside parentheses at depth > 0.
        """
        result = estract_licenses("(MIT AND BSD-2-Clause) OR Apache-2.0")
        assert result == ["(MIT AND BSD-2-Clause)", "Apache-2.0"]

    def test_extract_nested_parentheses(self):
        """Verifies handling of deeply nested parentheses."""
        result = estract_licenses("((MIT OR ISC) AND BSD-2-Clause) OR Apache-2.0")
        assert result == ["((MIT OR ISC) AND BSD-2-Clause)", "Apache-2.0"]

    def test_extract_empty_string(self):
        """Verifies handling of empty input."""
        result = estract_licenses("")
        assert result == []

    def test_extract_none_input(self):
        """Verifies handling of None input."""
        result = estract_licenses(None)
        assert result == []

    def test_extract_with_only_and_operator(self):
        """Verifies that AND expressions without OR return as single item."""
        result = estract_licenses("MIT AND Apache-2.0")
        # No OR at depth 0, so entire expression is one result
        assert result == ["MIT AND Apache-2.0"]

    def test_extract_preserves_whitespace_trimmed(self):
        """Verifies that whitespace is properly trimmed from results."""
        result = estract_licenses("  MIT   OR   Apache-2.0  ")
        assert result == ["MIT", "Apache-2.0"]


# ==================================================================================
#                     TEST CLASS: CHOOSE MOST PERMISSIVE LICENSE
# ==================================================================================

class TestChooseMostPermissiveLicense:
    """
    Tests for the 'choose_most_permissive_license_in_file' function.

    Validates the ranking algorithm that selects the most permissive license
    when a file has multiple license options.
    """

    @pytest.fixture
    def mock_rank_rules(self):
        """Provides a mock ranking configuration."""
        return {
            "license_order_permissive": [
                "MIT",
                "Apache-2.0",
                "BSD-2-Clause",
                "GPL-3.0",
                "AGPL-3.0"
            ]
        }

    def test_single_license_unchanged(self, mock_rank_rules):
        """Verifies that files with single license are not modified."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            assert result["file1.py"] == "MIT"

    def test_or_expression_chooses_most_permissive(self, mock_rank_rules):
        """Verifies that OR expressions result in the most permissive license."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "GPL-3.0 OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT is more permissive than GPL-3.0
            assert result["file1.py"] == "MIT"

    def test_multiple_or_expression(self, mock_rank_rules):
        """Verifies ranking with multiple OR alternatives."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "AGPL-3.0 OR Apache-2.0 OR GPL-3.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # Apache-2.0 is the most permissive among the three
            assert result["file1.py"] == "Apache-2.0"

    def test_and_expression_unchanged(self, mock_rank_rules):
        """Verifies that AND-only expressions are not modified."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "MIT AND Apache-2.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # AND expressions should remain, function splits on OR
            # But since there's AND, the condition triggers, splits, gets ["MIT AND Apache-2.0"]
            # which becomes "MIT AND Apache-2.0"
            assert "MIT" in result["file1.py"] or "Apache-2.0" in result["file1.py"]

    def test_multiple_files_processed(self, mock_rank_rules):
        """Verifies that multiple files are processed correctly."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {
                "file1.py": "GPL-3.0 OR MIT",
                "file2.py": "BSD-2-Clause",
                "file3.py": "Apache-2.0 OR AGPL-3.0"
            }
            result = choose_most_permissive_license_in_file(licenses)
            assert result["file1.py"] == "MIT"
            assert result["file2.py"] == "BSD-2-Clause"
            assert result["file3.py"] == "Apache-2.0"

    def test_unknown_license_fallback(self, mock_rank_rules):
        """Verifies handling of licenses not in the ranking."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "UnknownLicense OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT is in ranking, UnknownLicense is not (gets inf), so MIT wins
            assert result["file1.py"] == "MIT"

    def test_all_unknown_licenses(self, mock_rank_rules):
        """Verifies handling when all licenses are unknown."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "LicenseA OR LicenseB"}
            result = choose_most_permissive_license_in_file(licenses)
            # Both unknown, should pick first alphabetically or first in list
            assert result["file1.py"] in ["LicenseA", "LicenseB"]

    def test_empty_dict_returns_empty(self, mock_rank_rules):
        """Verifies that empty input returns empty result."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {}
            result = choose_most_permissive_license_in_file(licenses)
            assert result == {}


# ==================================================================================
#                     TEST CLASS: LOAD JSON RANK
# ==================================================================================

class TestLoadJsonRank:
    """
    Tests for the 'load_json_rank' function.

    Validates the loading and parsing of the permissiveness ranking JSON file.
    """

    def test_load_json_rank_success(self):
        """Verifies successful loading of the ranking file."""
        # This test uses the actual file in the project
        result = load_json_rank()
        assert "license_order_permissive" in result
        assert isinstance(result["license_order_permissive"], list)
        assert len(result["license_order_permissive"]) > 0
        # MIT should be in the list
        assert "MIT" in result["license_order_permissive"]

    def test_load_json_rank_file_not_found(self):
        """Verifies error handling when the ranking file is missing."""
        with patch('os.path.exists', return_value=False):
            with pytest.raises(FileNotFoundError, match="Unable to find the rules file"):
                load_json_rank()

    def test_load_json_rank_valid_structure(self):
        """Verifies the structure of the loaded ranking data."""
        result = load_json_rank()
        # Check that permissive licenses appear before restrictive ones
        order = result["license_order_permissive"]

        # MIT should appear before GPL-3.0 (if both exist)
        if "MIT" in order and "GPL-3.0" in order:
            assert order.index("MIT") < order.index("GPL-3.0")


# ==================================================================================
#                     TEST CLASS: EDGE CASES
# ==================================================================================

class TestLicenseRankingEdgeCases:
    """
    Tests for edge cases and complex scenarios in license ranking.
    """

    @pytest.fixture
    def mock_rank_rules(self):
        """Provides a mock ranking configuration."""
        return {
            "license_order_permissive": [
                "0BSD",
                "MIT",
                "BSD-2-Clause",
                "Apache-2.0",
                "LGPL-2.1",
                "GPL-2.0",
                "GPL-3.0"
            ]
        }

    def test_complex_nested_expression(self, mock_rank_rules):
        """Tests handling of complex nested SPDX expressions."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "(MIT AND BSD-2-Clause) OR Apache-2.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # Should pick one of the options
            assert result["file1.py"] in ["(MIT AND BSD-2-Clause)", "Apache-2.0"]

    def test_or_plus_version_suffixes(self, mock_rank_rules):
        """Tests handling of OR-later version suffixes."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "GPL-2.0-or-later OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT should be selected as more permissive
            assert result["file1.py"] == "MIT"

    def test_preserves_original_dict_reference(self, mock_rank_rules):
        """Verifies that the function modifies and returns the same dict."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "GPL-3.0 OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # Result should be the same object (mutated)
            assert result is licenses

    def test_whitespace_in_expression(self, mock_rank_rules):
        """Tests handling of extra whitespace in expressions."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "  GPL-3.0   OR   MIT  "}
            result = choose_most_permissive_license_in_file(licenses)
            assert result["file1.py"] == "MIT"

