import os
from dotenv import load_dotenv
import tempfile

load_dotenv()

# Authentication
CALLBACK_URL = os.getenv("CALLBACK_URL")

# API URL and models
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_CODING_MODEL = os.getenv("OLLAMA_CODING_MODEL")
OLLAMA_GENERAL_MODEL = os.getenv("OLLAMA_GENERAL_MODEL")
OLLAMA_HOST_VERSION = os.getenv("OLLAMA_HOST_VERSION")
OLLAMA_HOST_TAGS = os.getenv("OLLAMA_HOST_TAGS")

# Directories and Scancode
SCANCODE_BIN = os.getenv("SCANCODE_BIN")

# Directory per i cloni (con fallback su temp)
CLONE_BASE_DIR = os.getenv('CLONE_BASE_DIR') or os.path.join(tempfile.gettempdir(), 'clones')
os.makedirs(CLONE_BASE_DIR, exist_ok=True)

# Directory base per l'output
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR", "./output")
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

# SOLUZIONE: Definizione robusta di MINIMAL_JSON_BASE_DIR
# Se non è definita in .env, la creiamo dentro OUTPUT_BASE_DIR
MINIMAL_JSON_BASE_DIR = os.getenv("MINIMAL_JSON_BASE_DIR") or os.path.join(OUTPUT_BASE_DIR, "minimal_scans")
os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)

# Database settings and encryption
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")