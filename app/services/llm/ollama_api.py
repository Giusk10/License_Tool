"""
Ollama API Integration Module.

This module provides low-level helper functions to interact with the Ollama LLM API.
It handles the lifecycle of the Ollama service (start, check status), model management
(check installation, pull), and executes prompts against specific models (coding vs general).
"""

import json
import os
import subprocess
import time
import logging
import requests

from app.utility.config import (
    OLLAMA_URL,
    OLLAMA_GENERAL_MODEL,
    OLLAMA_HOST_VERSION,
    OLLAMA_CODING_MODEL,
    OLLAMA_HOST_TAGS,
    MINIMAL_JSON_BASE_DIR
)

logger = logging.getLogger(__name__)


def _is_ollama_running(timeout: float = 2.0) -> bool:
    """
    Verifies if the Ollama service is active.

    Sends a GET request to the configured version endpoint.

    Args:
        timeout (float): The request timeout in seconds.

    Returns:
        bool: True if the service responds, False otherwise.
    """
    try:
        requests.get(f"{OLLAMA_HOST_VERSION}", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def _start_ollama(wait_seconds: float = 10.0) -> bool:
    """
    Attempts to start the Ollama server process.

    It spawns a subprocess for `ollama serve` and waits for the service
    to become responsive.

    Args:
        wait_seconds (float): Maximum duration to wait for the server to be ready.

    Returns:
        bool: True if started successfully and responsive, False otherwise.
    """
    try:
        # We intentionally use Popen without a context manager because the process
        # needs to keep running in the background (daemon-like) after this function returns.
        # pylint: disable=consider-using-with
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception("Failed to spawn Ollama process")
        return False

    # Polling loop to check when the server is ready
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _is_ollama_running(1.0):
            return True
        time.sleep(0.5)

    return False


def _is_model_installed(model_name: str) -> bool:
    """
    Checks if a specific model is already installed in the local Ollama registry.

    Args:
        model_name (str): The name of the model (e.g., "qwen2.5-coder").

    Returns:
        bool: True if installed, False otherwise.
    """
    try:
        # The endpoint usually returns a JSON with a "models" list
        res = requests.get(f"{OLLAMA_HOST_TAGS}", timeout=3).json()
        models = [m.get("name") for m in res.get("models", []) if m.get("name")]
        return model_name in models
    except (requests.RequestException, ValueError, KeyError):
        logger.warning("Failed to retrieve installed models via API")
        return False


def _pull_model(model_name: str, timeout: int = 600) -> None:
    """
    Executes the Ollama CLI command to pull a model.

    Args:
        model_name (str): The name of the model to download.
        timeout (int): Max time to wait for the download to complete.
    """
    try:
        # synchronous execution (blocking)
        subprocess.run(
            ["ollama", "pull", model_name],
            check=True,
            timeout=timeout
        )
    except subprocess.SubprocessError:
        logger.exception("Error pulling model: %s", model_name)


def ensure_ollama_ready(
        model_name: str,
        start_if_needed: bool = True,
        pull_if_needed: bool = True
) -> None:
    """
    Orchestrator to ensure Ollama is running and the required model is available.

    Args:
        model_name (str): The target model name.
        start_if_needed (bool): If True, attempts to start the server if down.
        pull_if_needed (bool): If True, attempts to pull the model if missing.

    Raises:
        RuntimeError: If the service cannot be started or the model is missing.
    """
    if not _is_ollama_running():
        if not start_if_needed or not _start_ollama():
            raise RuntimeError("Ollama is not running and could not be started.")

    if not _is_model_installed(model_name):
        if not pull_if_needed:
            raise RuntimeError(f"Model {model_name} is not installed.")
        _pull_model(model_name)


def call_ollama_qwen3_coder(prompt: str) -> str:
    """
    Executes a prompt against the coding-specific model (e.g., Qwen).

    Side Effects:
        Writes the raw API response to `MINIMAL_JSON_BASE_DIR/model_coding_output.json`
        for debugging purposes.

    Args:
        prompt (str): The code generation instructions.

    Returns:
        str: The generated text response.

    Raises:
        requests.HTTPError: If the API returns a 4xx/5xx status.
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

    # Save debug output
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_path = os.path.join(MINIMAL_JSON_BASE_DIR, "model_coding_output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return data.get("response", "")


def call_ollama_deepseek(prompt: str) -> str:
    """
    Executes a prompt against the general-purpose model (e.g., DeepSeek).

    It includes post-processing to strip Markdown code fences often used by
    LLMs when returning JSON data.

    Side Effects:
        Writes the raw API response to `MINIMAL_JSON_BASE_DIR/model_output.json`.

    Args:
        prompt (str): The input prompt.

    Returns:
        str: The cleaned response string.

    Raises:
        requests.HTTPError: If the API returns a 4xx/5xx status.
    """
    ensure_ollama_ready(model_name=OLLAMA_GENERAL_MODEL)

    payload = {
        "model": OLLAMA_GENERAL_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    # Higher timeout for general models which might be more verbose/slow
    resp = requests.post(OLLAMA_URL, json=payload, timeout=240)
    resp.raise_for_status()
    data = resp.json()

    # Save debug output
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_path = os.path.join(MINIMAL_JSON_BASE_DIR, "model_output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    response = data.get("response", "")

    # Basic cleaning of Markdown JSON fences if present
    data_clean = response.replace("```json", "").replace("```", "")

    return data_clean
