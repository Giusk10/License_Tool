"""
test: tests/conftest.py

Shared configuration and fixtures for the pytest suite.

This module provides:
- Utility helpers (e.g., `_msg_matches` for flexible string assertion).
- Global environment variable mocking to isolate tests from local configuration.
- Default patches for complex service dependencies (like compatibility matrices).
- Reusable mock objects for SPDX parsing nodes (`MockNode`, `MockLeaf`, etc.).
"""

import pytest
import os
from unittest.mock import patch

# ==============================================================================
# GLOBAL MOCKS & PATCHES
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """
    Session-scoped fixture that mocks environment variables.
    Ensures that tests run with a consistent, isolated configuration
    and prevents accidental usage of real .env values.
    """
    with patch.dict(os.environ, {
        "GITHUB_CLIENT_ID": "test_id",
        "GITHUB_CLIENT_SECRET": "test_secret",
        "CALLBACK_URL": "http://localhost:8000/callback",
        "OLLAMA_HOST": "http://mock-ollama:11434",
        "OLLAMA_URL": "http://mock-ollama:11434",
        "OLLAMA_CODING_MODEL": "test-model",
        "OLLAMA_GENERAL_MODEL": "test-model",
        "OLLAMA_HOST_VERSION": "http://mock-ollama:11434/version",
        "OLLAMA_HOST_TAGS": "http://mock-ollama:11434/tags",
        "SCANCODE_BIN": "scancode",
        "CLONE_BASE_DIR": "./test_clones",
        "OUTPUT_BASE_DIR": "./test_output"
    }):
        yield


@pytest.fixture(autouse=True)
def patch_config_variables(tmp_path):
    """
    Autouse fixture that patches configuration variables in `app.utility.config`
    and dependent modules.

    This is necessary because `config.py` loads environment variables at import time.
    This fixture ensures that all modules use temporary test directories created
    via `tmp_path`.

    Args:
        tmp_path: Pytest fixture providing a temporary unique directory.

    Yields:
        str: The path to the temporary clone directory.
    """
    test_clone_dir = str(tmp_path / "test_clones")
    test_output_dir = str(tmp_path / "test_output")

    # Create test directories
    os.makedirs(test_clone_dir, exist_ok=True)
    os.makedirs(test_output_dir, exist_ok=True)

    # Patch modules that import CLONE_BASE_DIR directly
    with patch("app.utility.config.CLONE_BASE_DIR", test_clone_dir), \
            patch("app.utility.config.OUTPUT_BASE_DIR", test_output_dir), \
            patch("app.services.analysis_workflow.CLONE_BASE_DIR", test_clone_dir), \
            patch("app.services.llm.suggestion.CLONE_BASE_DIR", test_clone_dir), \
            patch("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir), \
            patch("app.services.downloader.download_service.CLONE_BASE_DIR", test_clone_dir):
        yield test_clone_dir


@pytest.fixture(autouse=True)
def _default_patches(monkeypatch, complex_matrix_data):
    """
    Autouse fixture applying default mocks for common service functions.

    It mocks `normalize_symbol` to be a simple pass-through/strip and
    `get_matrix` to return the test fixture data. This reduces boilerplate
    in individual unit tests.

    Args:
        monkeypatch: Pytest fixture for patching.
        complex_matrix_data: Fixture providing the mock compatibility matrix.
    """
    # Default normalize: identity/strip
    normalize_mock = lambda s: s.strip() if isinstance(s, str) else s

    monkeypatch.setattr("app.services.compatibility.evaluator.normalize_symbol", normalize_mock)
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", normalize_mock)
    monkeypatch.setattr("app.services.compatibility.parser_spdx.normalize_symbol", normalize_mock)

    # Default get_matrix: returns fixture data
    matrix_mock = lambda: complex_matrix_data

    monkeypatch.setattr("app.services.compatibility.evaluator.get_matrix", matrix_mock)
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", matrix_mock)

    yield


# ==============================================================================
# DATA FIXTURES
# ==============================================================================

@pytest.fixture
def complex_matrix_data():
    """
    Provides a mock compatibility matrix for testing evaluation logic.
    Covers 'yes', 'no', and 'conditional' scenarios.

    Returns:
        dict: A dictionary representing the compatibility matrix.
    """
    return {
        "MIT": {
            "MIT": "yes",
            "Apache-2.0": "yes",
            "GPL-3.0": "no",  # Permissive vs Strong Copyleft
            "GPL-3.0-or-later": "no",
            "LGPL-2.1": "conditional",
            "Proprietary": "no"
        },
        "GPL-3.0": {
            "MIT": "yes",  # GPL can include MIT
            "GPL-3.0": "yes",
            "Apache-2.0": "no",  # V2 vs V3 incompatibility simulation
            "Proprietary": "no"
        }
    }


# ==============================================================================
# MOCK NODE CLASSES (SPDX PARSER)
# ==============================================================================

@pytest.fixture
def MockNode():
    """Returns the Node class from the parser module."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.Node


@pytest.fixture
def MockLeaf():
    """Returns the Leaf class from the parser module."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.Leaf


@pytest.fixture
def MockAnd():
    """Returns the And class from the parser module."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.And


@pytest.fixture
def MockOr():
    """Returns the Or class from the parser module."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.Or