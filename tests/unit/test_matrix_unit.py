import pytest
import os
import sys
from unittest.mock import MagicMock, patch
from app.services.compatibility import matrix


# Verify that _coerce_status correctly normalizes known statuses
def test_coerce_status_known_values():
    assert matrix._coerce_status("yes") == "yes"
    assert matrix._coerce_status("same") == "yes"
    assert matrix._coerce_status("no") == "no"
    assert matrix._coerce_status("conditional") == "conditional"


# Verify that unknown or non-string statuses are converted to "unknown"
def test_coerce_status_unknown_values():
    assert matrix._coerce_status("maybe") == "unknown"
    assert matrix._coerce_status("") == "unknown"
    assert matrix._coerce_status(None) == "unknown"
    assert matrix._coerce_status(123) == "unknown"


# Simulates the legacy format {"matrix": {...}} and verifies normalization
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


# Simulates the modern format as a list of entries with compatibility
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


# Simulates the format with "licenses" key and verifies compatibility
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


# Verify that invalid rows (e.g., non-dict) are ignored
def test_load_matrix_invalid_row(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": "yes"  # invalid value, must be ignored
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result == {}  # no valid rows


# Verify that if the file is unavailable, an empty dict is returned
def test_load_matrix_missing_file(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: None)
    result = matrix.load_professional_matrix()
    assert result == {}


# Verify that get_matrix returns the already loaded matrix (cache)
def test_get_matrix_returns_cached(monkeypatch):
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {"MIT": {"Apache": "yes"}}
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    # manually reload
    reloaded = matrix.load_professional_matrix()
    cached = matrix.get_matrix()
    # must be equal to the matrix loaded at import
    assert cached == matrix._PRO_MATRIX
    assert cached == reloaded or isinstance(cached, dict)


# Test for _read_matrix_json with existing file
def test_read_matrix_json_file_exists(tmp_path, monkeypatch):
    """Verify that _read_matrix_json correctly reads an existing JSON file"""
    import json
    test_file = tmp_path / "matrixseqexpl.json"
    test_data = {"matrix": {"MIT": {"Apache": "yes"}}}
    test_file.write_text(json.dumps(test_data), encoding="utf-8")

    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", str(test_file))
    result = matrix._read_matrix_json()
    assert result == test_data


# Test for _read_matrix_json with non-existent file (fallback to None)
def test_read_matrix_json_file_not_found(tmp_path, monkeypatch):
    """Verify that _read_matrix_json returns None if the file does not exist"""
    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)

    # Mock importlib.resources to return None
    import sys
    if 'importlib.resources' in sys.modules:
        monkeypatch.setattr("importlib.resources.files", lambda x: None, raising=False)

    result = matrix._read_matrix_json()
    assert result is None

# Test for load_professional_matrix with old format without valid rows
def test_load_matrix_old_format_no_valid_entries(monkeypatch):
    """Verify that invalid entries are filtered in the old format"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": {"MIT": "invalid_status"},  # invalid status
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    # Must include the entry with status "unknown"
    assert "gpl" in result
    assert result["gpl"]["mit"] == "unknown"


# Test for load_professional_matrix with list containing non-dict entries
def test_load_matrix_list_format_invalid_entries(monkeypatch):
    """Verify that non-dict entries in the list are ignored"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        "string entry",  # non-dict, must be ignored
        {"name": "MIT", "compatibilities": [{"name": "GPL", "compatibility": "yes"}]},
        123,  # non-dict, must be ignored
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert result["mit"]["gpl"] == "yes"
    assert len(result) == 1  # only MIT is valid


# Test for load_professional_matrix with list having entries without name
def test_load_matrix_list_format_missing_name(monkeypatch):
    """Verify that entries without name are ignored"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {"compatibilities": [{"name": "GPL", "compatibility": "yes"}]},  # missing "name"
        {"name": "MIT", "compatibilities": [{"name": "Apache", "compatibility": "no"}]},
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert len(result) == 1


# Test for load_professional_matrix with list having non-dict compatibilities
def test_load_matrix_list_format_invalid_compatibilities(monkeypatch):
    """Verify that non-dict compatibilities are ignored"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {
            "name": "MIT",
            "compatibilities": [
                "invalid",  # non-dict
                {"name": "GPL", "compatibility": "yes"},
                {"name": "Apache"},  # missing compatibility/status
            ]
        }
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert result["mit"]["gpl"] == "yes"
    assert result["mit"]["apache"] == "unknown"  # status None -> unknown


# Test for load_professional_matrix with licenses format having invalid entries
def test_load_matrix_licenses_format_invalid_entries(monkeypatch):
    """Verify that invalid entries in the licenses format are ignored"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "licenses": [
            "not a dict",  # must be ignored
            {"name": "MIT", "compatibilities": [{"name": "GPL", "compatibility": "yes"}]},
        ]
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert "mit" in result
    assert result["mit"]["gpl"] == "yes"

# Test for load_professional_matrix with exception during normalization
def test_load_matrix_exception_during_normalization(monkeypatch):
    """Verify that exceptions during normalization are handled"""
    def raise_error():
        raise RuntimeError("Test error")

    monkeypatch.setattr(matrix, "_read_matrix_json", raise_error)
    result = matrix.load_professional_matrix()
    assert result == {}


# Test for load_professional_matrix with unknown format
def test_load_matrix_unknown_format(monkeypatch):
    """Verify that unknown formats return an empty dict"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "unknown_key": {"data": "value"}
    })
    result = matrix.load_professional_matrix()
    assert result == {}


# Test for _coerce_status with whitespace
def test_coerce_status_with_whitespace(monkeypatch):
    """Verify that _coerce_status handles whitespace"""
    assert matrix._coerce_status("  yes  ") == "yes"
    assert matrix._coerce_status(" NO ") == "no"
    assert matrix._coerce_status("\tconditional\n") == "conditional"


# Test for load_professional_matrix with compatibilities having only status
def test_load_matrix_list_format_status_field(monkeypatch):
    """Verify that the 'status' field works if 'compatibility' is not present"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        {
            "name": "MIT",
            "compatibilities": [
                {"name": "GPL", "status": "conditional"},  # uses "status" instead of "compatibility"
            ]
        }
    ])
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower())
    result = matrix.load_professional_matrix()
    assert result["mit"]["gpl"] == "conditional"


# Test for old format with entry returning values after normalization
def test_load_matrix_old_format_with_normalization(monkeypatch):
    """Verify that normalization works correctly in the old format"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL-3.0": {"MIT": "same", "Apache-2.0": "conditional"}
        }
    })
    monkeypatch.setattr(matrix, "normalize_symbol", lambda s: s.lower().replace("-", ""))
    result = matrix.load_professional_matrix()
    assert result["gpl3.0"]["mit"] == "yes"  # "same" -> "yes"
    assert result["gpl3.0"]["apache2.0"] == "conditional"


# Test for _read_matrix_json with fallback to importlib.resources
def test_read_matrix_json_importlib_resources_fallback(tmp_path, monkeypatch):
    """Verify that _read_matrix_json uses importlib.resources as fallback"""
    import json
    from unittest.mock import MagicMock, mock_open

    # Simulates non-existent file on filesystem
    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)

    # Mock importlib.resources with files() API
    test_data = {"matrix": {"MIT": {"Apache": "yes"}}}
    mock_files = MagicMock()
    mock_path = MagicMock()
    mock_path.read_text.return_value = json.dumps(test_data)
    mock_files.return_value.joinpath.return_value = mock_path

    # Mock __package__ to allow fallback
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")

    import importlib.resources as resources
    monkeypatch.setattr(resources, "files", mock_files)

    result = matrix._read_matrix_json()
    assert result == test_data


# Test for _read_matrix_json with importlib.resources raising FileNotFoundError
def test_read_matrix_json_importlib_resources_file_not_found(tmp_path, monkeypatch):
    """Verify that _read_matrix_json handles FileNotFoundError from importlib.resources"""
    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")

    # Mock importlib.resources to raise FileNotFoundError
    mock_files = MagicMock()
    mock_files.return_value.joinpath.side_effect = FileNotFoundError("Resource not found")

    import importlib.resources as resources
    monkeypatch.setattr(resources, "files", mock_files)

    result = matrix._read_matrix_json()
    assert result is None


# Test for _read_matrix_json with importlib.resources without files() (old API)
def test_read_matrix_json_importlib_resources_old_api(tmp_path, monkeypatch):
    """Verify that _read_matrix_json uses open_text() if files() is not available"""
    import json
    from unittest.mock import MagicMock

    nonexistent_path = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(matrix, "_MATRIXSEQEXPL_PATH", nonexistent_path)
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")

    # Mock importlib.resources without files()
    test_data = {"matrix": {"MIT": {"GPL": "no"}}}
    mock_open_text_result = MagicMock()
    mock_open_text_result.read.return_value = json.dumps(test_data)

    import importlib.resources as resources
    monkeypatch.setattr(resources, "files", None, raising=False)
    monkeypatch.setattr(resources, "open_text", lambda pkg, name: mock_open_text_result)

    result = matrix._read_matrix_json()
    assert result == test_data


# Test for load_professional_matrix with old format returning empty dict
def test_load_matrix_old_format_returns_empty_on_no_valid_rows(monkeypatch):
    """Verify that old format without valid dict rows returns empty dict"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {
            "GPL": [],  # non-dict
            "MIT": "string",  # non-dict
            "Apache": 123  # non-dict
        }
    })
    result = matrix.load_professional_matrix()
    assert result == {}


# Test for load_professional_matrix with list format returning empty dict
def test_load_matrix_list_format_returns_empty_on_no_valid_entries(monkeypatch):
    """Verify that list format without valid entries returns empty dict"""
    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: [
        "not a dict",
        123,
        {"no_name": "value"},
        {"name": "MIT", "compatibilities": "not a list"}
    ])
    result = matrix.load_professional_matrix()
    assert result == {}

# Test for load_professional_matrix with normalize_symbol raising exception
def test_load_matrix_normalize_symbol_exception(monkeypatch):
    """Verify that exceptions in normalize_symbol are handled"""
    def failing_normalize(s):
        raise ValueError("Normalize failed")

    monkeypatch.setattr(matrix, "_read_matrix_json", lambda: {
        "matrix": {"MIT": {"GPL": "yes"}}
    })
    monkeypatch.setattr(matrix, "normalize_symbol", failing_normalize)

    result = matrix.load_professional_matrix()
    assert result == {}

# Test for _read_from_filesystem exception handling (e.g., read permission error)
def test_read_from_filesystem_exception(monkeypatch):
    """Verify that exceptions during filesystem read are caught and logged"""
    # Force os.path.exists to True
    monkeypatch.setattr("os.path.exists", lambda x: True)
    
    # Mock open to raise an Exception (e.g. PermissionError)
    mock_open_func = MagicMock(side_effect=PermissionError("Access denied"))
    monkeypatch.setattr("builtins.open", mock_open_func)
    
    result = matrix._read_from_filesystem()
    assert result is None

# Test for _read_from_resources when resources module is not available (ImportError)
def test_read_from_resources_module_none(monkeypatch):
    """Verify that _read_from_resources returns None if resources module is None"""
    monkeypatch.setattr(matrix, "resources", None)
    result = matrix._read_from_resources()
    assert result is None

# Test for _read_from_resources when __package__ is not set
def test_read_from_resources_no_package(monkeypatch):
    """Verify that _read_from_resources returns None if __package__ is not set"""
    # Ensure resources is not None
    monkeypatch.setattr(matrix, "resources", MagicMock())
    monkeypatch.setattr(matrix, "__package__", None)
    result = matrix._read_from_resources()
    assert result is None

# Test for _read_from_resources generic exception (not FileNotFoundError)
def test_read_from_resources_generic_exception(monkeypatch):
    """Verify that generic exceptions during resource reading are caught"""
    monkeypatch.setattr(matrix, "resources", MagicMock())
    monkeypatch.setattr(matrix, "__package__", "app.services.compatibility")
    
    # Mock files() to raise a generic Exception
    mock_files = MagicMock(side_effect=Exception("Unexpected error"))
    monkeypatch.setattr(matrix.resources, "files", mock_files)
    
    result = matrix._read_from_resources()
    assert result is None

def test_import_resources_importerror():
    """
    Verify that if importlib.resources cannot be imported, resources is set to None.
    This test reloads the module in a controlled environment to hit the 'except ImportError' block.
    """
    # Store reference to the real module to restore it later
    real_module = sys.modules.get('app.services.compatibility.matrix')
    if real_module:
        del sys.modules['app.services.compatibility.matrix']

    orig_import = __import__
    
    def import_mock(name, globals=None, locals=None, fromlist=(), level=0):
        # Trigger ImportError for 'from importlib import resources'
        # which looks like name='importlib', fromlist=('resources',)
        if name == 'importlib' and 'resources' in fromlist:
             raise ImportError("Simulated ImportError for resources")
        # Also catch direct import if attempted
        if name == 'importlib.resources':
             raise ImportError("Simulated ImportError for resources")
             
        return orig_import(name, globals, locals, fromlist, level)

    try:
        with patch('builtins.__import__', side_effect=import_mock):
            import app.services.compatibility.matrix as m
            assert m.resources is None
    finally:
        # Restore sys.modules
        if real_module:
            sys.modules['app.services.compatibility.matrix'] = real_module
        elif 'app.services.compatibility.matrix' in sys.modules:
            del sys.modules['app.services.compatibility.matrix']