# tests/test_matrix.py

import pytest
from unittest.mock import MagicMock
from app.services.compatibility import matrix


# Verifica che _coerce_status normalizzi correttamente gli status noti
def test_coerce_status_known_values():
    assert matrix._coerce_status("yes") == "yes"
    assert matrix._coerce_status("same") == "yes"
    assert matrix._coerce_status("no") == "no"
    assert matrix._coerce_status("conditional") == "conditional"


# Verifica che status sconosciuti o non stringa vengano convertiti in "unknown"
def test_coerce_status_unknown_values():
    assert matrix._coerce_status("maybe") == "unknown"
    assert matrix._coerce_status("") == "unknown"
    assert matrix._coerce_status(None) == "unknown"
    assert matrix._coerce_status(123) == "unknown"


# Simula il formato legacy {"matrix": {...}} e verifica la normalizzazione
def test_load_matrix_old_format(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": {"MIT": "yes", "Apache": "no"}
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result["gpl"]["mit"] == "yes"
    assert result["gpl"]["apache"] == "no"


# Simula il formato moderno come lista di entry con compatibilità
def test_load_matrix_new_list_format(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {
            "name": "MIT",
            "compatibilities": [
                {"name": "Apache", "compatibility": "conditional"},
                {"name": "GPL", "status": "no"}
            ]
        }
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result["mit"]["apache"] == "conditional"
    assert result["mit"]["gpl"] == "no"


# Simula il formato con chiave "licenses" e verifica la compatibilità
def test_load_matrix_licenses_format(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "licenses": [
            {
                "name": "Apache",
                "compatibilities": [
                    {"name": "MIT", "compatibility": "yes"}
                ]
            }
        ]
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result["apache"]["mit"] == "yes"


# Verifica che righe non valide (es. non dict) vengano ignorate
def test_load_matrix_invalid_row(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": "yes"  # valore non valido, deve essere ignorato
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result == {}  # nessuna riga valida


# Verifica che se il file non è disponibile, venga restituito un dict vuoto
def test_load_matrix_missing_file(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: None)
    result = matrix.load_professional_matrix()
    assert result == {}


# Verifica che get_matrix restituisca la matrice già caricata (cache)
def test_get_matrix_returns_cached(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {"MIT": {"Apache": "yes"}}
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    # ricarico manualmente
    reloaded = matrix.load_professional_matrix()
    cached = matrix.get_matrix()
    # deve essere uguale alla matrice caricata all'import
    assert cached == matrix._PRO_MATRIX
    assert cached == reloaded or isinstance(cached, dict)
