"""
Modulo di test unitario del servizio di ranking delle licenze.

Questo modulo contiene test unitari per la logica di ranking delle licenze in
`app.services.scanner.license_ranking`. Valida le funzioni utilizzate per
estrarre licenze da espressioni SPDX e rankarle per permissività.

La suite copre:
1. Estrazione licenze: Analisi di espressioni SPDX complesse con operatori OR/AND.
2. Ranking licenze: Selezione della licenza più permissiva tra alternative.
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
#                     CLASSE DI TEST: ESTRAZIONE LICENZE
# ==================================================================================

class TestExtractLicenses:
    """
    Test per la funzione 'estract_licenses'.

    Valida l'analisi delle espressioni SPDX per estrarre identificatori di licenza individuali,
    gestendo sia espressioni semplici che complesse.
    """

    def test_extract_single_license(self):
        """Verifica l'estrazione di una singola licenza senza operatori."""
        result = estract_licenses("MIT")
        assert result == ["MIT"]

    def test_extract_simple_or_expression(self):
        """Verifica l'estrazione da un'espressione OR semplice."""
        result = estract_licenses("MIT OR Apache-2.0")
        assert result == ["MIT", "Apache-2.0"]

    def test_extract_multiple_or_expressions(self):
        """Verifica l'estrazione da più espressioni OR."""
        result = estract_licenses("MIT OR Apache-2.0 OR GPL-3.0")
        assert result == ["MIT", "Apache-2.0", "GPL-3.0"]

    def test_extract_with_parentheses(self):
        """
        Verifica che le parentesi siano preservate nel risultato.

        La funzione non dovrebbe dividere dentro parentesi a profondità > 0.
        """
        result = estract_licenses("(MIT AND BSD-2-Clause) OR Apache-2.0")
        assert result == ["(MIT AND BSD-2-Clause)", "Apache-2.0"]

    def test_extract_nested_parentheses(self):
        """Verifica la gestione di parentesi profondamente annidate."""
        result = estract_licenses("((MIT OR ISC) AND BSD-2-Clause) OR Apache-2.0")
        assert result == ["((MIT OR ISC) AND BSD-2-Clause)", "Apache-2.0"]

    def test_extract_empty_string(self):
        """Verifica la gestione di input vuoto."""
        result = estract_licenses("")
        assert result == []

    def test_extract_none_input(self):
        """Verifica la gestione di input None."""
        result = estract_licenses(None)
        assert result == []

    def test_extract_with_only_and_operator(self):
        """Verifica che espressioni AND senza OR restituiscano come singolo elemento."""
        result = estract_licenses("MIT AND Apache-2.0")
        # No OR at depth 0, so entire expression is one result
        assert result == ["MIT AND Apache-2.0"]

    def test_extract_preserves_whitespace_trimmed(self):
        """Verifica che gli spazi bianchi siano correttamente rimossi dai risultati."""
        result = estract_licenses("  MIT   OR   Apache-2.0  ")
        assert result == ["MIT", "Apache-2.0"]


# ==================================================================================
#                     CLASSE DI TEST: SCEGLI LICENZA PIÙ PERMISSIVA
# ==================================================================================

class TestChooseMostPermissiveLicense:
    """
    Test per la funzione 'choose_most_permissive_license_in_file'.

    Valida l'algoritmo di ranking che seleziona la licenza più permissiva
    quando un file ha più opzioni di licenza.
    """

    @pytest.fixture
    def mock_rank_rules(self):
        """Fornisce una configurazione di ranking mock."""
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
        """Verifica che i file con licenza singola non siano modificati."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            assert result["file1.py"] == "MIT"

    def test_or_expression_chooses_most_permissive(self, mock_rank_rules):
        """Verifica che espressioni OR risultino nella licenza più permissiva."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "GPL-3.0 OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT is more permissive than GPL-3.0
            assert result["file1.py"] == "MIT"

    def test_multiple_or_expression(self, mock_rank_rules):
        """Verifica il ranking con più alternative OR."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "AGPL-3.0 OR Apache-2.0 OR GPL-3.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # Apache-2.0 is the most permissive among the three
            assert result["file1.py"] == "Apache-2.0"

    def test_and_expression_unchanged(self, mock_rank_rules):
        """Verifica che espressioni solo AND non siano modificate."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "MIT AND Apache-2.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # AND expressions should remain, function splits on OR
            # But since there's AND, the condition triggers, splits, gets ["MIT AND Apache-2.0"]
            # which becomes "MIT AND Apache-2.0"
            assert "MIT" in result["file1.py"] or "Apache-2.0" in result["file1.py"]

    def test_multiple_files_processed(self, mock_rank_rules):
        """Verifica che più file siano elaborati correttamente."""
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
        """Verifica la gestione di licenze non nel ranking."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "UnknownLicense OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT is in ranking, UnknownLicense is not (gets inf), so MIT wins
            assert result["file1.py"] == "MIT"

    def test_all_unknown_licenses(self, mock_rank_rules):
        """Verifica la gestione quando tutte le licenze sono sconosciute."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "LicenseA OR LicenseB"}
            result = choose_most_permissive_license_in_file(licenses)
            # Both unknown, should pick first alphabetically or first in list
            assert result["file1.py"] in ["LicenseA", "LicenseB"]

    def test_empty_dict_returns_empty(self, mock_rank_rules):
        """Verifica che input vuoto restituisca risultato vuoto."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {}
            result = choose_most_permissive_license_in_file(licenses)
            assert result == {}


# ==================================================================================
#                     CLASSE DI TEST: CARICA JSON RANK
# ==================================================================================

class TestLoadJsonRank:
    """
    Test per la funzione 'load_json_rank'.

    Valida il caricamento e l'analisi del file JSON di ranking della permissività.
    """

    def test_load_json_rank_success(self):
        """Verifica il caricamento riuscito del file di ranking."""
        # This test uses the actual file in the project
        result = load_json_rank()
        assert "license_order_permissive" in result
        assert isinstance(result["license_order_permissive"], list)
        assert len(result["license_order_permissive"]) > 0
        # MIT should be in the list
        assert "MIT" in result["license_order_permissive"]

    def test_load_json_rank_file_not_found(self):
        """Verifica la gestione degli errori quando il file di ranking è mancante."""
        with patch('os.path.exists', return_value=False):
            with pytest.raises(FileNotFoundError, match="Unable to find the rules file"):
                load_json_rank()

    def test_load_json_rank_valid_structure(self):
        """Verifica la struttura dei dati di ranking caricati."""
        result = load_json_rank()
        # Check that permissive licenses appear before restrictive ones
        order = result["license_order_permissive"]

        # MIT should appear before GPL-3.0 (if both exist)
        if "MIT" in order and "GPL-3.0" in order:
            assert order.index("MIT") < order.index("GPL-3.0")


# ==================================================================================
#                     CLASSE DI TEST: CASI LIMITE
# ==================================================================================

class TestLicenseRankingEdgeCases:
    """
    Test per casi limite e scenari complessi nel ranking delle licenze.
    """

    @pytest.fixture
    def mock_rank_rules(self):
        """Fornisce una configurazione di ranking mock."""
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
        """Testa la gestione di espressioni SPDX annidate complesse."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "(MIT AND BSD-2-Clause) OR Apache-2.0"}
            result = choose_most_permissive_license_in_file(licenses)
            # Should pick one of the options
            assert result["file1.py"] in ["(MIT AND BSD-2-Clause)", "Apache-2.0"]

    def test_or_plus_version_suffixes(self, mock_rank_rules):
        """Testa la gestione di suffissi di versione OR-later."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "GPL-2.0-or-later OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # MIT should be selected as more permissive
            assert result["file1.py"] == "MIT"

    def test_preserves_original_dict_reference(self, mock_rank_rules):
        """Verifica che la funzione modifichi e restituisca lo stesso dict."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "GPL-3.0 OR MIT"}
            result = choose_most_permissive_license_in_file(licenses)
            # Result should be the same object (mutated)
            assert result is licenses

    def test_whitespace_in_expression(self, mock_rank_rules):
        """Testa la gestione di spazi bianchi extra nelle espressioni."""
        with patch('app.services.scanner.license_ranking.load_json_rank', return_value=mock_rank_rules):
            licenses = {"file1.py": "  GPL-3.0   OR   MIT  "}
            result = choose_most_permissive_license_in_file(licenses)
            assert result["file1.py"] == "MIT"
