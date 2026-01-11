"""
test: tests/conftest.py

Configurazione condivisa e fixtures per la suite di test pytest.

Questo modulo fornisce:
- Helper di utilità (es. `_msg_matches` per asserzioni di stringhe flessibili).
- Mocking delle variabili d'ambiente globali per isolare i test dalla configurazione locale.
- Patch di default per dipendenze di servizi complessi (come le matrici di compatibilità).
- Oggetti mock riutilizzabili per i nodi di parsing SPDX (`MockNode`, `MockLeaf`, ecc.).
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
    Fixture a livello di sessione che simula (mock) le variabili d'ambiente.
    Garantisce che i test vengano eseguiti con una configurazione coerente e isolata
    e previene l'uso accidentale delle reali variabili presenti nel file .env.
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
    Fixture "autouse" che sostituisce (patcha) le variabili di configurazione in
    `app.utility.config` e nei moduli dipendenti.

    Questo è necessario perché `config.py` carica le variabili d'ambiente al momento
    dell'importazione. Questa fixture garantisce che tutti i moduli usino directory
    temporanee per i test create tramite `tmp_path`.

    Argomenti:
        tmp_path: fixture di pytest che fornisce una directory temporanea unica.

    Restituisce:
        str: Il percorso alla directory temporanea per i clone.
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
    Fixture "autouse" che applica patch/mocking di default per funzioni comuni dei servizi.

    Mocka `normalize_symbol` come semplice pass-through/strip e `get_matrix` per restituire i dati
    della fixture di test. Questo riduce il codice ripetuto (boilerplate) nei singoli test unitari.

    Argomenti:
        monkeypatch: fixture di pytest per applicare patch.
        complex_matrix_data: fixture che fornisce la matrice di compatibilità di test.
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
    Fornisce una matrice di compatibilità mock per testare la logica di valutazione.
    Copre scenari 'yes', 'no' e 'conditional'.

    Restituisce:
        dict: Un dizionario che rappresenta la matrice di compatibilità.
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
    """Restituisce la classe `Node` dal modulo parser_spdx."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.Node


@pytest.fixture
def MockLeaf():
    """Restituisce la classe `Leaf` dal modulo parser_spdx."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.Leaf


@pytest.fixture
def MockAnd():
    """Restituisce la classe `And` dal modulo parser_spdx."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.And


@pytest.fixture
def MockOr():
    """Restituisce la classe `Or` dal modulo parser_spdx."""
    from app.services.compatibility import parser_spdx
    return parser_spdx.Or

