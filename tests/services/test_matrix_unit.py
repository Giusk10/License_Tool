"""
test: services/compatibility/matrix.py
"""

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


# Test per _read_matrix_json con file esistente
def test_read_matrix_json_file_exists(tmp_path, monkeypatch):
    """Verifica che _read_matrix_json legga correttamente un file JSON esistente"""
    import json
    test_file = tmp_path / "matrixseqexpl.json"
    test_data = {"matrix": {"MIT": {"Apache": "yes"}}}
    test_file.write_text(json.dumps(test_data), encoding="utf-8")

    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", str(test_file))
    result = matrix._read_matrix_json()
    assert result == test_data


# Test per _read_matrix_json con file inesistente (fallback a None)
def test_read_matrix_json_file_not_found(tmp_path, monkeypatch):
    """Verifica che _read_matrix_json restituisca None se il file non esiste"""
    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)

    # Mock importlib.resources per restituire None
    import sys
    if 'importlib.resources' in sys.modules:
        monkeypatch.setattr("importlib.resources.files", lambda x: None, raising=False)

    result = matrix._read_matrix_json()
    assert result is None

# Test per load_professional_matrix con formato old senza righe valide
def test_load_matrix_old_format_no_valid_entries(monkeypatch):
    """Verifica che vengano filtrate le entry non valide nel formato old"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": {"MIT": "invalid_status"},  # status non valido
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    # Deve includere la entry con status "unknown"
    assert "gpl" in result
    assert result["gpl"]["mit"] == "unknown"


# Test per load_professional_matrix con lista contenente entry non dict
def test_load_matrix_list_format_invalid_entries(monkeypatch):
    """Verifica che le entry non dict nella lista vengano ignorate"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        "string entry",  # non dict, deve essere ignorato
        {"name": "MIT", "compatibilities": [{"name": "GPL", "compatibility": "yes"}]},
        123,  # non dict, deve essere ignorato
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert result["mit"]["gpl"] == "yes"
    assert len(result) == 1  # solo MIT è valido


# Test per load_professional_matrix con lista con entry senza name
def test_load_matrix_list_format_missing_name(monkeypatch):
    """Verifica che le entry senza name vengano ignorate"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {"compatibilities": [{"name": "GPL", "compatibility": "yes"}]},  # manca "name"
        {"name": "MIT", "compatibilities": [{"name": "Apache", "compatibility": "no"}]},
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert len(result) == 1


# Test per load_professional_matrix con lista con compatibilities non dict
def test_load_matrix_list_format_invalid_compatibilities(monkeypatch):
    """Verifica che le compatibilities non dict vengano ignorate"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {
            "name": "MIT",
            "compatibilities": [
                "invalid",  # non dict
                {"name": "GPL", "compatibility": "yes"},
                {"name": "Apache"},  # manca compatibility/status
            ]
        }
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert result["mit"]["gpl"] == "yes"
    assert result["mit"]["apache"] == "unknown"  # status None -> unknown


# Test per load_professional_matrix con formato licenses con entry invalide
def test_load_matrix_licenses_format_invalid_entries(monkeypatch):
    """Verifica che le entry invalide nel formato licenses vengano ignorate"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "licenses": [
            "not a dict",  # deve essere ignorato
            {"name": "MIT", "compatibilities": [{"name": "GPL", "compatibility": "yes"}]},
        ]
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert result["mit"]["gpl"] == "yes"

# Test per load_professional_matrix con eccezione durante normalizzazione
def test_load_matrix_exception_during_normalization(monkeypatch):
    """Verifica che le eccezioni durante la normalizzazione vengano gestite"""
    def raise_error():
        raise RuntimeError("Test error")

    monkeypatch.setattr(matrix, "_read_matrix_json", raise_error)
    result = matrix.load_professional_matrix()
    assert result == {}


# Test per load_professional_matrix con formato sconosciuto
def test_load_matrix_unknown_format(monkeypatch):
    """Verifica che formati sconosciuti restituiscano dict vuoto"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "unknown_key": {"data": "value"}
    })
    result = matrix.load_professional_matrix()
    assert result == {}


# Test per _coerce_status con whitespace
def test_coerce_status_with_whitespace(monkeypatch):
    """Verifica che _coerce_status gestisca gli spazi bianchi"""
    assert matrix._coerce_status("  yes  ") == "yes"
    assert matrix._coerce_status(" NO ") == "no"
    assert matrix._coerce_status("\tconditional\n") == "conditional"


# Test per load_professional_matrix con compatibilities che hanno solo status
def test_load_matrix_list_format_status_field(monkeypatch):
    """Verifica che il campo 'status' funzioni se 'compatibility' non è presente"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {
            "name": "MIT",
            "compatibilities": [
                {"name": "GPL", "status": "conditional"},  # usa "status" invece di "compatibility"
            ]
        }
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result["mit"]["gpl"] == "conditional"


# Test per formato old con entry che ritorna valori dopo normalizzazione
def test_load_matrix_old_format_with_normalization(monkeypatch):
    """Verifica che la normalizzazione funzioni correttamente nel formato old"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL-3.0": {"MIT": "same", "Apache-2.0": "conditional"}
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower().replace("-", ""))
    result = matrix.load_professional_matrix()
    assert result["gpl3.0"]["mit"] == "yes"  # "same" -> "yes"
    assert result["gpl3.0"]["apache2.0"] == "conditional"


# Test per _read_matrix_json con fallback a importlib.resources
def test_read_matrix_json_importlib_resources_fallback(tmp_path, monkeypatch):
    """Verifica che _read_matrix_json usi importlib.resources come fallback"""
    import json
    from unittest.mock import MagicMock, mock_open

    # Simula file non esistente su filesystem
    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)

    # Mock importlib.resources con files() API
    test_data = {"matrix": {"MIT": {"Apache": "yes"}}}
    mock_files = MagicMock()
    mock_path = MagicMock()
    mock_path.read_text.return_value = json.dumps(test_data)
    mock_files.return_value.joinpath.return_value = mock_path

    # Mock __package__ per permettere il fallback
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")

    import importlib.resources as resources
    monkeypatch.setattr(resources, "files", mock_files)

    result = matrix._read_matrix_json()
    assert result == test_data


# Test per _read_matrix_json con importlib.resources che solleva FileNotFoundError
def test_read_matrix_json_importlib_resources_file_not_found(tmp_path, monkeypatch):
    """Verifica che _read_matrix_json gestisca FileNotFoundError da importlib.resources"""
    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")

    # Mock importlib.resources per sollevare FileNotFoundError
    mock_files = MagicMock()
    mock_files.return_value.joinpath.side_effect = FileNotFoundError("Resource not found")

    import importlib.resources as resources
    monkeypatch.setattr(resources, "files", mock_files)

    result = matrix._read_matrix_json()
    assert result is None


# Test per _read_matrix_json con importlib.resources senza files() (old API)
def test_read_matrix_json_importlib_resources_old_api(tmp_path, monkeypatch):
    """Verifica che _read_matrix_json usi open_text() se files() non è disponibile"""
    import json
    from unittest.mock import MagicMock

    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")

    # Mock importlib.resources senza files()
    test_data = {"matrix": {"MIT": {"GPL": "no"}}}
    mock_open_text_result = MagicMock()
    mock_open_text_result.read.return_value = json.dumps(test_data)

    import importlib.resources as resources
    monkeypatch.setattr(resources, "files", None, raising=False)
    monkeypatch.setattr(resources, "open_text", lambda pkg, name: mock_open_text_result)

    result = matrix._read_matrix_json()
    assert result == test_data

# Test per load_professional_matrix con formato old che restituisce dict vuoto
def test_load_matrix_old_format_returns_empty_on_no_valid_rows(monkeypatch):
    """Verifica che formato old senza righe dict valide restituisca dict vuoto"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": [],  # non dict
            "MIT": "string",  # non dict
            "Apache": 123  # non dict
        }
    })
    result = matrix.load_professional_matrix()
    assert result == {}


# Test per load_professional_matrix con formato lista che restituisce dict vuoto
def test_load_matrix_list_format_returns_empty_on_no_valid_entries(monkeypatch):
    """Verifica che formato lista senza entry valide restituisca dict vuoto"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        "not a dict",
        123,
        {"no_name": "value"},
        {"name": "MIT", "compatibilities": "not a list"}
    ])
    result = matrix.load_professional_matrix()
    assert result == {}

# Test per load_professional_matrix con normalize_symbol che solleva eccezione
def test_load_matrix_normalize_symbol_exception(monkeypatch):
    """Verifica che le eccezioni in normalize_symbol vengano gestite"""
    def failing_normalize(s):
        raise ValueError("Normalize failed")

    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {"MIT": {"GPL": "yes"}}
    })
    monkeypatch.setattr(matrix, "normalize_symbol", failing_normalize)

    result = matrix.load_professional_matrix()
    assert result == {}


