import json
import os
import requests
import subprocess
import time
from app.utility.config import OLLAMA_URL, OLLAMA_GENERAL_MODEL, OLLAMA_HOST_VERSION, OLLAMA_CODING_MODEL, \
    OLLAMA_HOST_TAGS, MINIMAL_JSON_BASE_DIR

# Checks if the Ollama service responds within the specified timeout.
def _is_ollama_running(timeout: float = 2.0) -> bool:
    """
    Performs a GET request to `OLLAMA_HOST_VERSION` to verify that the API is active.
    Returns True if the request is successful, False otherwise.
    """
    try:
        requests.get(f"{OLLAMA_HOST_VERSION}", timeout=timeout)
        return True
    except Exception:
        return False

# Starts the `ollama serve` process in the background and waits for the API to be ready.
def _start_ollama(wait_seconds: float = 10.0) -> bool:
    """
    Starts `ollama serve` in the background (stdout/stderr silenced).
    Waits up to `wait_seconds` for the version endpoint to respond.
    Returns True if the service is ready, False otherwise.
    """
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False

    # retry loop until deadline
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _is_ollama_running(1.0):
            return True
        time.sleep(0.5)
    return False

# Verifies if a specific model is installed on Ollama.
def _is_model_installed(model_name: str) -> bool:
    """
    Queries `OLLAMA_HOST_TAGS` to get the list of installed models.
    Returns True if `model_name` is present in the list.
    """
    try:
        res = requests.get(f"{OLLAMA_HOST_TAGS}", timeout=3).json()
        models = [m.get("name") for m in res.get("models", []) if m.get("name")]
        return model_name in models
    except Exception:
        return False

# Downloads a model using `ollama pull` and waits for completion.
def _pull_model(model_name: str, timeout: int = 600) -> None:
    """
    Executes `ollama pull MODEL_NAME` and waits (blocking) up to `timeout` seconds.
    Raises an exception if the command fails or the timeout expires.
    """
    p = subprocess.Popen(["ollama", "pull", model_name])
    p.wait(timeout=timeout)

# Ensures that Ollama is running and that the requested model is present.
def ensure_ollama_ready(model_name: str, start_if_needed: bool = True, pull_if_needed: bool = True) -> None:
    """
    Ensures that Ollama is running and that the model is present.
    Raises RuntimeError if the environment cannot be made ready.
    """
    if not _is_ollama_running():
        if not start_if_needed or not _start_ollama():
            raise RuntimeError("Ollama is not running and could not be started.")
    if not _is_model_installed(model_name):
        if not pull_if_needed:
            raise RuntimeError(f"Model {model_name} not installed.")
        _pull_model(model_name)

# Simple synchronous call to the Ollama API for "coding" use.
def call_ollama_qwen3_coder(prompt: str) -> str:
    """
    Performs a POST request to `OLLAMA_URL` using the coding model.
    Returns the 'response' key from the response JSON or an empty string.
    """
    ensure_ollama_ready(model_name=OLLAMA_CODING_MODEL)
    payload = {
        "model": OLLAMA_CODING_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_minimal = os.path.join(MINIMAL_JSON_BASE_DIR, "model_coding_output.json")

    with open(output_minimal, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return data.get("response", "")

def call_ollama_deepseek(prompt: str) -> str:
    """
    Performs a POST request to `OLLAMA_URL` using the general model.
    Higher timeout for longer responses.
    """
    ensure_ollama_ready(model_name=OLLAMA_GENERAL_MODEL)
    payload = {
        "model": OLLAMA_GENERAL_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=240)
    resp.raise_for_status()
    data = resp.json()

    # Ensures the folder exists and writes the minimal JSON instead of reading it
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_minimal = os.path.join(MINIMAL_JSON_BASE_DIR, "model_output.json")

    with open(output_minimal, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    response = data.get("response", "")
    data_clean = response.replace("```json", "").replace("```", "")
    return data_clean
