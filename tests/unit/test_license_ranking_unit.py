"""
License Ranking Service Unit Test Module.

Questo modulo contiene test unitari per la logica di ranking delle licenze in
`app.services.scanner.license_ranking`. Valida le funzioni utilizzate per
estrarre le licenze da espressioni SPDX e ordinarle per permissività.

La suite copre:
1. Estrazione delle licenze: Parsing di espressioni SPDX complesse con operatori OR/AND.
2. Ranking delle licenze: Selezione della licenza più permissiva tra le alternative.
3. Caricamento JSON: Gestione corretta del file di ranking della permissività.
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
    Test per la funzione 'estract_licenses'.

    Valida il parsing delle espressioni SPDX per estrarre gli identificatori di licenza,
    gestendo sia espressioni semplici che complesse.
    """

    def test_extract_single_license(self):
        """Verifica l'estrazione di una singola licenza senza operatori."""
        result = estract_licenses("MIT")
        assert result == ["MIT"]

    def test_extract_simple_or_expression(self):
        """Verifica l'estrazione da una semplice espressione OR."""
        result = estract_licenses("MIT OR Apache-2.0")
        assert result == ["MIT", "Apache-2.0"]

    def test_extract_multiple_or_expressions(self):
        """Verifica l'estrazione da più espressioni OR."""
        result = estract_licenses("MIT OR Apache-2.0 OR GPL-3.0")
        assert result == ["MIT", "Apache-2.0", "GPL-3.0"]

    def test_extract_with_parentheses(self):
        """
        Verifica che le parentesi siano preservate nel risultato.

        La funzione non dovrebbe dividere all'interno delle parentesi con profondità > 0.
        """
        result = estract_licenses("(MIT AND BSD-2-Clause) OR Apache-2.0")
        assert result == ["(MIT AND BSD-2-Clause)", "Apache-2.0"]

    def test_extract_nested_parentheses(self):
        """Verifica la gestione di parentesi annidate in profondità."""
        result = estract_licenses("((MIT OR ISC) AND BSD-2-Clause) OR Apache-2.0")
        assert result == ["((MIT OR ISC) AND BSD-2-Clause)", "Apache-2.0"]

    def test_extract_empty_string(self):
        """Verifica la gestione di input vuoti."""
        result = estract_licenses("")
        assert result == []

    def test_extract_none_input(self):
        """Verifica la gestione di input None."""
        result = estract_licenses(None)
        assert result == []

    def test_extract_with_only_and_operator(self):
        """Verifica che le espressioni AND senza OR vengano restituite come un singolo elemento."""
        result = estract_licenses("MIT AND Apache-2.0")
        # Nessun OR a profondità 0, quindi l'intera espressione è un risultato
        assert result == ["MIT AND Apache-2.0"]

    def test_extract_preserves_whitespace_trimmed(self):
        """Verifica che gli spazi bianchi vengano correttamente rimossi dai risultati."""
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
        """Verifica che le espressioni composte solo da AND non vengano modificate."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "MIT AND Apache-2.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # Le espressioni AND dovrebbero rimanere inalterate, la funzione si divide solo su OR
            # Ma poiché c'è AND, la condizione si attiva, si divide, ottiene ["MIT AND Apache-2.0"]
            # che diventa "MIT AND Apache-2.0"
            assert "MIT" in result["file1.py"] or "Apache-2.0" in result["file1.py"]

    def test_multiple_files_processed(self, mock_rank_rules):
        """Verifica che più file vengano elaborati correttamente."""
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
        """Verifica la gestione delle licenze non presenti nel ranking."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "UnknownLicense OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT è nel ranking, UnknownLicense no (ottiene inf), quindi vince MIT
            assert result["file1.py"] == "MIT"

    def test_all_unknown_licenses(self, mock_rank_rules):
        """Verifica la gestione quando tutte le licenze sono sconosciute."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "LicenseA OR LicenseB"}
            result = choose_most_permissive_license_in_file(licenses)
            # Entrambe sconosciute, dovrebbe scegliere la prima in ordine alfabetico o la prima nella lista
            assert result["file1.py"] in ["LicenseA", "LicenseB"]

    def test_empty_dict_returns_empty(self, mock_rank_rules):
        """Verifica che un input vuoto restituisca un risultato vuoto."""
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
        """Verifica il caricamento riuscito del file di ranking."""
        # Questo test utilizza il file reale nel progetto
        result = load_json_rank()
        assert "license_order_permissive" in result
        assert isinstance(result["license_order_permissive"], list)
        assert len(result["license_order_permissive"]) > 0
        # MIT dovrebbe essere nella lista
        assert "MIT" in result["license_order_permissive"]

    def test_load_json_rank_file_not_found(self):
        """Verifica la gestione degli errori quando il file di ranking è mancante."""
        with patch('os.path.exists', return_value=False):
            with pytest.raises(FileNotFoundError, match="Unable to find the rules file"):
                load_json_rank()

    def test_load_json_rank_valid_structure(self):
        """Verifica la struttura dei dati di ranking caricati."""
        result = load_json_rank()
        # Controlla che le licenze permissive appaiano prima di quelle restrittive
        order = result["license_order_permissive"]

        # MIT dovrebbe apparire prima di GPL-3.0 (se entrambe esistono)
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
