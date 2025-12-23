import pytest
import os
from unittest.mock import patch

"""
Shared helpers for tests: utility functions (e.g., _msg_matches) and common fixtures.
- `_msg_matches` fixture helper for language-independent comparison
- `_default_patches` autouse fixture that sets default patches for
  `normalize_symbol` and `get_matrix` in the main compatibility modules
  to reduce duplication in tests.
- fixtures `MockNode`, `MockLeaf`, `MockAnd`, `MockOr` that provide
  reusable mock classes in test suites.
"""

def msg_matches_helper(s: str, en: str, it: str) -> bool:
    """
    Returns True if `s` contains the English variant `en` or Italian variant `it`.
    Avoids duplicating the helper across multiple test files.
    """
    if s is None:
        return False
    return (en in s) or (it in s)

# Makes the function available as an optional fixture
@pytest.fixture
def _msg_matches():
    return msg_matches_helper


# Autouse fixture: default patches for normalize_symbol/get_matrix in target modules
@pytest.fixture(autouse=True)
def _default_patches(monkeypatch, complex_matrix_data):
    """
    Applies default patches for normalization functions and for the
    `get_matrix` function used by the code (returns `complex_matrix_data`).

    Tests can override these patches locally when needed.
    """
    # Default normalize: identity/strip to avoid repetition
    monkeypatch.setattr("app.services.compatibility.evaluator.normalize_symbol", lambda s: s.strip() if isinstance(s, str) else s)
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: s.strip() if isinstance(s, str) else s)
    monkeypatch.setattr("app.services.compatibility.parser_spdx.normalize_symbol", lambda s: s.strip() if isinstance(s, str) else s)

    # Default get_matrix: returns the complex_matrix_data fixture
    monkeypatch.setattr("app.services.compatibility.evaluator.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)

    yield


# 1. Mock environment variables (Session Scope: executed only once)
@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """Sets dummy environment variables to avoid configuration errors."""
    with patch.dict(os.environ, {
        "GITHUB_CLIENT_ID": "test_id",
        "GITHUB_CLIENT_SECRET": "test_secret",
        "CALLBACK_URL": "http://localhost:8000/callback",
        "OLLAMA_HOST": "http://mock-ollama:11434",
        # Set critical variables for Pydantic Settings
        "OLLAMA_URL": "http://mock-ollama:11434",
        "OLLAMA_CODING_MODEL": "test-model",
        "OLLAMA_GENERAL_MODEL": "test-model",
        "OLLAMA_HOST_VERSION": "http://mock-ollama:11434/version",
        "OLLAMA_HOST_TAGS": "http://mock-ollama:11434/tags",
        "SCANCODE_BIN": "scancode",
        "CLONE_BASE_DIR": "./test_clones",
        "OUTPUT_BASE_DIR": "./test_output",
        # Variables for MongoDB and encryption
        "MONGO_URI": "mongodb://test:27017",
        "DATABASE_NAME": "test_db",
        "COLLECTION_NAME": "test_collection",
        "ENCRYPTION_KEY": "test_encryption_key_32_bytes_long=="
    }):
        yield


# Direct patch of variables in config module (autouse to apply to all tests)
@pytest.fixture(autouse=True)
def patch_config_variables(tmp_path):
    """
    Direct patch of configuration variables in the config module and in all
    modules that import them directly.
    This is necessary because config.py loads environment variables at import,
    before mock_env_vars can intervene.
    """
    test_clone_dir = str(tmp_path / "test_clones")
    test_output_dir = str(tmp_path / "test_output")

    # Create test directories
    os.makedirs(test_clone_dir, exist_ok=True)
    os.makedirs(test_output_dir, exist_ok=True)

    # MongoDB and encryption configurations for tests
    test_mongo_uri = "mongodb://test:27017"
    test_db_name = "test_db"
    test_collection_name = "test_collection"
    from cryptography.fernet import Fernet
    test_encryption_key = Fernet.generate_key()

    # Patch in all modules that import CLONE_BASE_DIR directly
    with patch("app.utility.config.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.utility.config.OUTPUT_BASE_DIR", test_output_dir), \
         patch("app.utility.config.MONGO_URI", test_mongo_uri), \
         patch("app.utility.config.DATABASE_NAME", test_db_name), \
         patch("app.utility.config.COLLECTION_NAME", test_collection_name), \
         patch("app.utility.config.ENCRYPTION_KEY", test_encryption_key), \
         patch("app.services.analysis_workflow.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.services.llm.suggestion.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.services.github.encrypted_Auth_Info.MONGO_URI", test_mongo_uri), \
         patch("app.services.github.encrypted_Auth_Info.DATABASE_NAME", test_db_name), \
         patch("app.services.github.encrypted_Auth_Info.COLLECTION_NAME", test_collection_name), \
         patch("app.services.github.encrypted_Auth_Info.ENCRYPTION_KEY", test_encryption_key), \
         patch("app.services.downloader.download_service.CLONE_BASE_DIR", test_clone_dir):
        yield test_clone_dir

# 2. Mock Compatibility Matrix (Pure Data)
@pytest.fixture
def complex_matrix_data():
    """
    Returns a dictionary that simulates the JSON matrix.
    Covers the cases: YES, NO, CONDITIONAL.
    """
    return {
        "MIT": {
            "MIT": "yes",
            "Apache-2.0": "yes",
            "GPL-3.0": "no",            # MIT is permissive, but if you include GPL it becomes GPL
            "GPL-3.0-or-later": "no",
            "LGPL-2.1": "conditional",
            "Proprietary": "no"
        },
        "GPL-3.0": {
            "MIT": "yes",               # GPL can include MIT
            "GPL-3.0": "yes",
            "Apache-2.0": "no",         # Often incompatible v2 vs v3, set NO for test
            "Proprietary": "no"
        }
    }

# 3. Mock node classes as fixtures for reuse
@pytest.fixture
def MockNode():
    from app.services.compatibility import parser_spdx
    return parser_spdx.Node

@pytest.fixture
def MockLeaf():
    from app.services.compatibility import parser_spdx
    return parser_spdx.Leaf

@pytest.fixture
def MockAnd():
    from app.services.compatibility import parser_spdx
    return parser_spdx.And

@pytest.fixture
def MockOr():
    from app.services.compatibility import parser_spdx
    return parser_spdx.Or
