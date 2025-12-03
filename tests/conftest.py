'''
NON SERVE PIU PERCHE' HO INSERITO IL FILE .ini
from pathlib import Path
import sys

# Inserisce la root del progetto all'inizio di sys.path così "import app.*" funziona
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

# Questo file serve per poter scrivere solo pytest nella root del progetto.
# python -m pytest tests -q (potevo usare anche solo questo comando)

'''
import unittest

# TODO: Questo file serve per le configurazioni globali e Mock condivisi tra test
# ESEMPIO MINIMALE
import pytest
import os
from unittest.mock import MagicMock, patch


# 1. Mock delle variabili d'ambiente per TUTTI i test
@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """Mocka le variabili d'ambiente critiche."""
    with patch.dict(os.environ, {
        "GITHUB_CLIENT_ID": "test_id",
        "GITHUB_CLIENT_SECRET": "test_secret",
        "CALLBACK_URL": "http://localhost:8000/callback",
        "OLLAMA_HOST": "http://mock-ollama:11434",
        "ENCRYPTION_KEY": "a" * 32  # Chiave valida per Fernet (32 bytes)
    }):
        yield

# 2. Mock della Matrice di Compatibilità (per non dipendere dal JSON su disco)
@pytest.fixture
def complex_matrix_data():
    """
    Matrice complessa per testare:
    - YES: Compatibilità piena
    - NO: Incompatibilità
    - CONDITIONAL: Compatibile con clausole
    - UNKNOWN: Non presente (implicito nel codice se manca chiave)
    """
    return {
        "MIT": {
            "MIT": "yes",
            "Apache-2.0": "yes",
            "GPL-3.0": "no",          # MIT include GPL, ma GPL "infetta" MIT -> qui semplifichiamo
            "GPL-3.0-or-later": "no",
            "LGPL-2.1": "conditional" # Caso ipotetico per testare "conditional"
        },
        "GPL-3.0": {
            "MIT": "yes",             # GPL può includere codice MIT
            "GPL-3.0": "yes",
            "Apache-2.0": "no"        # Spesso incompatibili (GPLv3 vs Apache2 è ok, ma testiamo "no")
        }
    }