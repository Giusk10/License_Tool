import json
import os
import requests
import subprocess
import time
from app.utility.config import OLLAMA_URL, OLLAMA_GENERAL_MODEL, OLLAMA_HOST_VERSION, OLLAMA_CODING_MODEL, \
    OLLAMA_HOST_TAGS, MINIMAL_JSON_BASE_DIR

# Controlla se il servizio Ollama risponde entro il timeout indicato.
def _is_ollama_running(timeout: float = 2.0) -> bool:
    """
    Effettua una GET a `OLLAMA_HOST_VERSION` per verificare che l'API sia attiva.
    Ritorna True se la richiesta va a buon fine, False altrimenti.
    """
    try:
        requests.get(f"{OLLAMA_HOST_VERSION}", timeout=timeout)
        return True
    except Exception:
        return False

# Avvia il processo `ollama serve` in background e attende che l'API sia pronta.
def _start_ollama(wait_seconds: float = 10.0) -> bool:
    """
    Avvia `ollama serve` in background (stdout/stderr silenziati).
    Attende fino a `wait_seconds` che l'endpoint di versione risponda.
    Ritorna True se il servizio è pronto, False altrimenti.
    """
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False

    # retry loop fino alla scadenza
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _is_ollama_running(1.0):
            return True
        time.sleep(0.5)
    return False

# Verifica se un modello specifico è installato su Ollama.
def _is_model_installed(model_name: str) -> bool:
    """
    Interroga `OLLAMA_HOST_TAGS` per ottenere la lista dei modelli installati.
    Restituisce True se `model_name` è presente nella lista.
    """
    try:
        res = requests.get(f"{OLLAMA_HOST_TAGS}", timeout=3).json()
        models = [m.get("name") for m in res.get("models", []) if m.get("name")]
        return model_name in models
    except Exception:
        return False

# Scarica un modello usando `ollama pull` e attende il completamento.
def _pull_model(model_name: str, timeout: int = 600) -> None:
    """
    Esegue `ollama pull MODEL_NAME` e attende (blocking) fino a `timeout` secondi.
    Genera eccezione se il comando fallisce o scade il timeout.
    """
    p = subprocess.Popen(["ollama", "pull", model_name])
    p.wait(timeout=timeout)

# Garantisce che Ollama sia in esecuzione e che il modello richiesto sia presente.
def ensure_ollama_ready(model_name: str, start_if_needed: bool = True, pull_if_needed: bool = True) -> None:
    """
    Garantisce che Ollama sia in esecuzione e che il modello sia presente.
    Lancia RuntimeError se non è possibile rendere l'ambiente pronto.
    """
    if not _is_ollama_running():
        if not start_if_needed or not _start_ollama():
            raise RuntimeError("Ollama non è in esecuzione e non è stato possibile avviarlo.")
    if not _is_model_installed(model_name):
        if not pull_if_needed:
            raise RuntimeError(f"Modello {model_name} non installato.")
        _pull_model(model_name)

# Chiamata sincrona semplice all'API Ollama per uso "coding".
def call_ollama_qwen3_coder(prompt: str) -> str:
    """
    Effettua una chiamata POST a `OLLAMA_URL` usando il modello di coding.
    Ritorna la chiave 'response' dal JSON di risposta o stringa vuota.
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
    Effettua una chiamata POST a `OLLAMA_URL` usando il modello generale.
    Maggior timeout per risposte più lunghe.
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

    # Assicura che la cartella esista e scrive il JSON minimale invece di leggerlo
    os.makedirs(MINIMAL_JSON_BASE_DIR, exist_ok=True)
    output_minimal = os.path.join(MINIMAL_JSON_BASE_DIR, "model_output.json")

    with open(output_minimal, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    response = data.get("response", "")
    data_clean = response.replace("```json", "").replace("```", "")
    return data_clean
