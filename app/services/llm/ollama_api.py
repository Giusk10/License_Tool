"""
Ollama API Integration Module.

Questo modulo fornisce funzioni helper di basso livello per interagire con l'API LLM di Ollama.
Gestisce il ciclo di vita del servizio Ollama (avvio, controllo stato), la gestione dei modelli
(controllo installazione, pull) ed esegue prompt contro modelli specifici (coding vs general).
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
    Verifica se il servizio Ollama è attivo.

    Invia una richiesta GET all'endpoint di versione configurato.

    Args:
        timeout (float): Il timeout della richiesta in secondi.

    Returns:
        bool: True se il servizio risponde, False altrimenti.
    """
    try:
        requests.get(f"{OLLAMA_HOST_VERSION}", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def _start_ollama(wait_seconds: float = 10.0) -> bool:
    """
    Tenta di avviare il processo server di Ollama.

    Genera un sottoprocesso per `ollama serve` e attende che il servizio
    diventi reattivo.

    Args:
        wait_seconds (float): Durata massima di attesa affinché il server sia pronto.

    Returns:
        bool: True se avviato con successo e reattivo, False altrimenti.
    """
    try:
        # Usiamo intenzionalmente Popen senza un context manager perché il processo
        # deve continuare a funzionare in background (come demone) dopo il ritorno di questa funzione.
        # pylint: disable=consider-using-with
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception("Failed to spawn Ollama process")
        return False

    # Ciclo di polling per verificare quando il server è pronto
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _is_ollama_running(1.0):
            return True
        time.sleep(0.5)

    return False


def _is_model_installed(model_name: str) -> bool:
    """
    Controlla se un modello specifico è già installato nel registro locale di Ollama.

    Args:
        model_name (str): Il nome del modello (es. "qwen2.5-coder").

    Returns:
        bool: True se installato, False altrimenti.
    """
    try:
        # L'endpoint di solito restituisce un JSON con un elenco "models"
        res = requests.get(f"{OLLAMA_HOST_TAGS}", timeout=3).json()
        models = [m.get("name") for m in res.get("models", []) if m.get("name")]
        return model_name in models
    except (requests.RequestException, ValueError, KeyError):
        logger.warning("Failed to retrieve installed models via API")
        return False


def _pull_model(model_name: str, timeout: int = 600) -> None:
    """
    Esegue il comando CLI di Ollama per scaricare un modello.

    Args:
        model_name (str): Il nome del modello da scaricare.
        timeout (int): Tempo massimo di attesa per il completamento del download.
    """
    try:
        # esecuzione sincrona (bloccante)
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
    Orchestratore per garantire che Ollama sia in esecuzione e che il modello richiesto sia disponibile.

    Args:
        model_name (str): Il nome del modello di destinazione.
        start_if_needed (bool): Se True, tenta di avviare il server se non è attivo.
        pull_if_needed (bool): Se True, tenta di scaricare il modello se mancante.

    Raises:
        RuntimeError: Se il servizio non può essere avviato o il modello è mancante.
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
    Esegue un prompt contro il modello specifico per il coding (es. Qwen).

    Effetti Collaterali:
        Scrive la risposta grezza dell'API in `MINIMAL_JSON_BASE_DIR/model_coding_output.json`
        per scopi di debug.

    Args:
        prompt (str): Le istruzioni per la generazione del codice.

    Returns:
        str: La risposta di testo generata.

    Raises:
        requests.HTTPError: Se l'API restituisce uno stato 4xx/5xx.
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

    # Salva output di debug
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_path = os.path.join(MINIMAL_JSON_BASE_DIR, "model_coding_output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return data.get("response", "")


def call_ollama_deepseek(prompt: str) -> str:
    """
    Esegue un prompt contro il modello generico (es. DeepSeek).

    Include la post-elaborazione per rimuovere i blocchi di codice Markdown spesso utilizzati dagli
    LLM quando restituiscono dati JSON.

    Effetti Collaterali:
        Scrive la risposta grezza dell'API in `MINIMAL_JSON_BASE_DIR/model_output.json`.

    Args:
        prompt (str): Il prompt di input.

    Returns:
        str: La stringa di risposta pulita.

    Raises:
        requests.HTTPError: Se l'API restituisce uno stato 4xx/5xx.
    """
    ensure_ollama_ready(model_name=OLLAMA_GENERAL_MODEL)

    payload = {
        "model": OLLAMA_GENERAL_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    # Timeout più alto per modelli generali che potrebbero essere più prolissi/lenti
    resp = requests.post(OLLAMA_URL, json=payload, timeout=240)
    resp.raise_for_status()
    data = resp.json()

    # Salva output di debug
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_path = os.path.join(MINIMAL_JSON_BASE_DIR, "model_output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    response = data.get("response", "")

    # Pulizia di base dei blocchi JSON Markdown se presenti
    data_clean = response.replace("```json", "").replace("```", "")

    return data_clean
