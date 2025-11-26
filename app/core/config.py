import os
from dotenv import load_dotenv

load_dotenv()

# authentication
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
CALLBACK_URL = os.getenv("CALLBACK_URL", "http://localhost:8000/api/callback") # Nota il /api se usi il prefix

# api url and models
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_CODING_MODEL = os.getenv("OLLAMA_CODING_MODEL")
OLLAMA_GENERAL_MODEL = os.getenv("OLLAMA_GENERAL_MODEL")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

# directories and scancode
SCANCODE_BIN = os.getenv("SCANCODE_BIN")
CLONE_BASE_DIR = os.getenv("CLONE_BASE_DIR")
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR")

