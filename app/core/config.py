import os
from dotenv import load_dotenv

load_dotenv()

# token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# api url and models
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_CODING_MODEL = os.getenv("OLLAMA_MODEL")
OLLAMA_GENERAL_MODEL = os.getenv("OLLAMA_GENERAL_MODEL")

# directories and scancode
SCANCODE_BIN = os.getenv("SCANCODE_BIN")
CLONE_BASE_DIR = os.getenv("CLONE_BASE_DIR")
OUTPUT_BASE_DIR = os.getenv("OUTPUT_BASE_DIR")

