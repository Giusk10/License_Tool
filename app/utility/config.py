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
# AUTHENTICATION
# ==============================================================================
CALLBACK_URL = os.getenv("CALLBACK_URL")

# ==============================================================================
# API URL AND MODELS (OLLAMA)
# ==============================================================================
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_CODING_MODEL = os.getenv("OLLAMA_CODING_MODEL")
OLLAMA_GENERAL_MODEL = os.getenv("OLLAMA_GENERAL_MODEL")
OLLAMA_HOST_VERSION = os.getenv("OLLAMA_HOST_VERSION")
OLLAMA_HOST_TAGS = os.getenv("OLLAMA_HOST_TAGS")

# ==============================================================================
# EXTERNAL TOOLS
# ==============================================================================
SCANCODE_BIN = os.getenv("SCANCODE_BIN")

# ==============================================================================
# DIRECTORY MANAGEMENT
# ==============================================================================

# Directory for cloned repositories (defaults to system temp if not set)
CLONE_BASE_DIR = os.getenv('CLONE_BASE_DIR') or os.path.join(tempfile.gettempdir(), 'clones')
os.makedirs(CLONE_BASE_DIR, exist_ok=True)

# Base directory for output artifacts
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR", "./output")
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

# Robust definition of MINIMAL_JSON_BASE_DIR
# If not defined in .env, it is created inside OUTPUT_BASE_DIR to ensure consistency
MINIMAL_JSON_BASE_DIR = os.getenv("MINIMAL_JSON_BASE_DIR") or os.path.join(OUTPUT_BASE_DIR, "minimal_scans")
os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)