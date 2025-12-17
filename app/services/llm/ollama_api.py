"""
This module provides helper functions to interact with the Ollama LLM API.
"""

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
    Verifies if Ollama is running by making a GET request to the version endpoint.

    Args:
        timeout (float): The timeout for the request in seconds.

    Returns:
        bool: True if Ollama is running, False otherwise.
    """
    try:
        requests.get(f"{OLLAMA_HOST_VERSION}", timeout=timeout)
        return True
    except Exception:
        return False

# Starts the `ollama serve` process in the background and waits for the API to be ready.
def _start_ollama(wait_seconds: float = 10.0) -> bool:
    """
    Starts the Ollama server process and waits until it's running or timeout occurs.

    Args:
        wait_seconds (float): Maximum time to wait for the server to become ready.

    Returns:
        bool: True if Ollama started successfully, False otherwise.
    """
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False

    # Retry loop until the deadline is reached
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _is_ollama_running(1.0):
            return True
        time.sleep(0.5)
    return False

# Verifies if a specific model is installed on Ollama.
def _is_model_installed(model_name: str) -> bool:
    """
    Checks if the specified model is installed in Ollama.

    Args:
        model_name (str): The name of the model to check.

    Returns:
        bool: True if the model is installed, False otherwise.
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
    Executes the command to pull the specified model using Ollama CLI.

    Args:
        model_name (str): The name of the model to pull.
        timeout (int): The maximum time to wait for the pull command to complete.
    """
    p = subprocess.Popen(["ollama", "pull", model_name])
    p.wait(timeout=timeout)

# Ensures that Ollama is running and that the requested model is present.
def ensure_ollama_ready(model_name: str, start_if_needed: bool = True, pull_if_needed: bool = True) -> None:
    """
    Ensures that Ollama is running and the specified model is installed.

    Args:
        model_name (str): The name of the model to ensure is installed.
        start_if_needed (bool): Whether to start Ollama if it's not running.
        pull_if_needed (bool): Whether to pull the model if it's not installed.

    Raises:
        RuntimeError: If Ollama is not running or the model is not installed.
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
    Local Ollama API call for coding tasks.

    Args:
        prompt (str): The prompt to send to the model.

    Returns:
        str: The response from the model.
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
