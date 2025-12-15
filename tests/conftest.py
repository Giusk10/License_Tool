import pytest
import os
from unittest.mock import patch

"""
Helper condivisi per i test: funzioni di utilità (es. _msg_matches) e fixture comuni.
- `_msg_matches` fixture helper per confronto lingua-indipendente
- `_default_patches` autouse fixture che imposta patch di default per
  `normalize_symbol` e `get_matrix` nei moduli principali della compatibilità
  per ridurre duplicazione nei test.
- fixture `MockNode`, `MockLeaf`, `MockAnd`, `MockOr` che forniscono classi
  mock riutilizzabili nelle suite di test.
"""

def msg_matches_helper(s: str, en: str, it: str) -> bool:
    """
    Restituisce True se `s` contiene la variante inglese `en` oppure italiana `it`.
    Evita duplicazione dell'helper in più file di test.
    """
    if s is None:
        return False
    return (en in s) or (it in s)

# Rende disponibile la funzione come fixture opzionale
@pytest.fixture
def _msg_matches():
    return msg_matches_helper


# Autouse fixture: patch di default per normalize_symbol/get_matrix in moduli target
@pytest.fixture(autouse=True)
def _default_patches(monkeypatch, complex_matrix_data):
    """
    Applica patch di default per le funzioni di normalizzazione e per la
    funzione `get_matrix` usata dal codice (restituisce `complex_matrix_data`).

    I test possono sovrascrivere questi patch localmente quando necessario.
    """
    # Default normalize: identity/strip per evitare ripetizione
    monkeypatch.setattr("app.services.compatibility.evaluator.normalize_symbol", lambda s: s.strip() if isinstance(s, str) else s)
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: s.strip() if isinstance(s, str) else s)
    monkeypatch.setattr("app.services.compatibility.parser_spdx.normalize_symbol", lambda s: s.strip() if isinstance(s, str) else s)

    # Default get_matrix: restituisce la fixture complex_matrix_data
    monkeypatch.setattr("app.services.compatibility.evaluator.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)

    yield


# 1. Mock delle variabili d'ambiente (Session Scope: eseguito una volta sola)
@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """Imposta variabili d'ambiente fittizie per evitare errori di configurazione."""
    with patch.dict(os.environ, {
        "GITHUB_CLIENT_ID": "test_id",
        "GITHUB_CLIENT_SECRET": "test_secret",
        "CALLBACK_URL": "http://localhost:8000/callback",
        "OLLAMA_HOST": "http://mock-ollama:11434",
        # Imposta variabili critiche per Pydantic Settings
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


# Patch diretto delle variabili nel modulo config (autouse per applicarlo a tutti i test)
@pytest.fixture(autouse=True)
def patch_config_variables(tmp_path):
    """
    Patch diretto delle variabili di configurazione nel modulo config e in tutti
    i moduli che le importano direttamente.
    Questo è necessario perché config.py carica le variabili d'ambiente all'import,
    prima che mock_env_vars possa intervenire.
    """
    test_clone_dir = str(tmp_path / "test_clones")
    test_output_dir = str(tmp_path / "test_output")

    # Crea le directory di test
    os.makedirs(test_clone_dir, exist_ok=True)
    os.makedirs(test_output_dir, exist_ok=True)

    # Patch in tutti i moduli che importano CLONE_BASE_DIR direttamente
    with patch("app.utility.config.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.utility.config.OUTPUT_BASE_DIR", test_output_dir), \
         patch("app.services.analysis_workflow.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.services.llm.suggestion.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir), \
         patch("app.services.dowloader.download_service.CLONE_BASE_DIR", test_clone_dir):
        yield test_clone_dir

# 2. Mock della Matrice di Compatibilità (Dati puri)
@pytest.fixture
def complex_matrix_data():
    """
    Restituisce un dizionario che simula la matrice JSON.
    Copre le casistiche: YES, NO, CONDITIONAL.
    """
    return {
        "MIT": {
            "MIT": "yes",
            "Apache-2.0": "yes",
            "GPL-3.0": "no",            # MIT è permissiva, ma se includi GPL diventa GPL
            "GPL-3.0-or-later": "no",
            "LGPL-2.1": "conditional",
            "Proprietary": "no"
        },
        "GPL-3.0": {
            "MIT": "yes",               # GPL può includere MIT
            "GPL-3.0": "yes",
            "Apache-2.0": "no",         # Spesso incompatibili v2 vs v3, mettiamo NO per test
            "Proprietary": "no"
        }
    }

# 3. Mock node classes come fixture per riuso
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
