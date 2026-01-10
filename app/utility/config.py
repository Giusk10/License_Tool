"""
Application Configuration Module.

This module manages the loading of environment variables and the setup of
essential application directories. It defines configuration constants used
throughout the application for:
- Authentication (Callback URLs)
- AI Service integration (Ollama models and URLs)
- External tools (ScanCode)
- File system management (Clone, Output, and JSON directories)
"""

import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# AUTENTICAZIONE
# ==============================================================================
CALLBACK_URL = os.getenv("CALLBACK_URL")

# ==============================================================================
# URL API E MODELLI (OLLAMA)
# ==============================================================================
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_CODING_MODEL = os.getenv("OLLAMA_CODING_MODEL")
OLLAMA_GENERAL_MODEL = os.getenv("OLLAMA_GENERAL_MODEL")
OLLAMA_HOST_VERSION = os.getenv("OLLAMA_HOST_VERSION")
OLLAMA_HOST_TAGS = os.getenv("OLLAMA_HOST_TAGS")

# ==============================================================================
# STRUMENTI ESTERNI
# ==============================================================================
SCANCODE_BIN = os.getenv("SCANCODE_BIN")

# ==============================================================================
# GESTIONE DIRECTORY
# ==============================================================================

# Directory per i repository clonati (default alla temp di sistema se non impostata)
CLONE_BASE_DIR = os.getenv('CLONE_BASE_DIR') or os.path.join(tempfile.gettempdir(), 'clones')
os.makedirs(CLONE_BASE_DIR, exist_ok=True)

# Directory base per gli artefatti di output
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR", "./output")
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

# Definizione robusta di MINIMAL_JSON_BASE_DIR
# Se non definita in .env, viene creata dentro OUTPUT_BASE_DIR per garantire consistenza
MINIMAL_JSON_BASE_DIR = os.getenv("MINIMAL_JSON_BASE_DIR") or os.path.join(OUTPUT_BASE_DIR, "minimal_scans")
os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)