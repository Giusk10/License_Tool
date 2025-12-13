import os
from dotenv import load_dotenv
from pathlib import Path
import tempfile

# Costruisci il percorso assoluto verso il file .env
# __file__ è il percorso di config.py
# .parent è 'utility'
# .parent.parent è 'app', dove si trova il file .env
env_path = Path(__file__).resolve().parent.parent / '.env'

# Carica il file .env specificando il percorso
load_dotenv(dotenv_path=env_path)
#load_dotenv()
# authentication
CALLBACK_URL = os.getenv("CALLBACK_URL") # Nota il /api se usi il prefix

# api url and models
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_CODING_MODEL = os.getenv("OLLAMA_CODING_MODEL")
OLLAMA_GENERAL_MODEL = os.getenv("OLLAMA_GENERAL_MODEL")
OLLAMA_HOST_VERSION = os.getenv("OLLAMA_HOST_VERSION")
OLLAMA_HOST_TAGS = os.getenv("OLLAMA_HOST_TAGS")

# directories and scancode
SCANCODE_BIN = os.getenv("SCANCODE_BIN")
# Fallback sicuro se la variabile d'ambiente non è impostata
CLONE_BASE_DIR = os.environ.get('CLONE_BASE_DIR') or os.path.join(tempfile.gettempdir(), 'clones')
# Assicura che la directory esista all'avvio
os.makedirs(CLONE_BASE_DIR, exist_ok=True)
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR", "./output")
MINIMAL_JSON_BASE_DIR = os.getenv("MINIMAL_JSON_BASE_DIR")

# Database settings and encryption
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
