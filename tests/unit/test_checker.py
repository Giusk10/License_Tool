#TESTA checker.py

import pytest
from unittest.mock import patch
from app.services.compatibility.checker import check_compatibility

# Dati di mock per la matrice di compatibilità
# Simuliamo che MIT sia compatibile con MIT, ma GPL-3.0 no.
MOCK_MATRIX = {
    "MIT": {
        "MIT": "yes",
        "GPL-3.0": "no",
        "APACHE-2.0": "yes"
    }
}

@pytest.fixture
def mock_matrix():
    """Mocka la funzione get_matrix per non dipendere dal file JSON reale"""
    with patch("app.services.compatibility.checker.get_matrix", return_value=MOCK_MATRIX):
        yield

@pytest.fixture
def mock_parser():
    """Mocka il parser e l'evaluator per semplificare il test"""
    # Nota: Qui stiamo assumendo che parser ed evaluator funzionino.
    # In un test reale potresti voler testare anche loro, o mockarli come qui per isolare 'checker'
    with patch("app.services.compatibility.checker.parse_spdx") as mock_p, \
            patch("app.services.compatibility.checker.eval_node") as mock_e:
        yield mock_p, mock_e

def test_check_compatibility_success(mock_matrix, mock_parser):
    mock_p, mock_e = mock_parser

    # Setup del comportamento del mock evaluator
    # Se la licenza è MIT, restituisce "yes", se GPL "no"
    def side_effect_eval(main, node):
        if node == "GPL-3.0": return "no", ["Conflict"]
        return "yes", ["OK"]

    mock_e.side_effect = side_effect_eval
    # Mockiamo che il parser restituisca semplicemente la stringa (semplificazione)
    mock_p.side_effect = lambda x: x

    file_licenses = {
        "file1.py": "MIT",
        "file2.py": "GPL-3.0"
    }

    result = check_compatibility("MIT", file_licenses)

    assert result["main_license"] == "MIT"
    assert len(result["issues"]) == 2

    # Verifica file compatibile
    issue_mit = next(i for i in result["issues"] if i["file_path"] == "file1.py")
    assert issue_mit["compatible"] is True

    # Verifica file incompatibile
    issue_gpl = next(i for i in result["issues"] if i["file_path"] == "file2.py")
    assert issue_gpl["compatible"] is False
    assert issue_gpl["reason"] == "Conflict"

def test_check_compatibility_missing_main_license(mock_matrix):
    """Testa il caso in cui la licenza principale non è definita"""
    file_licenses = {"file1.py": "MIT"}

    # Passiamo None o UNKNOWN come main_license
    result = check_compatibility("UNKNOWN", file_licenses)

    assert result["main_license"] == "UNKNOWN"
    issue = result["issues"][0]
    assert issue["compatible"] is False
    assert "non rilevata" in issue["reason"]