import pytest
import os
from unittest.mock import patch

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