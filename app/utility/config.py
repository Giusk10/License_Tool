import os
from dotenv import load_dotenv

load_dotenv()

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
CLONE_BASE_DIR = os.getenv("CLONE_BASE_DIR")
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR")
MINIMAL_JSON_BASE_DIR = os.getenv("MINIMAL_JSON_BASE_DIR")

# Database settings and encryption
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
