import json
import requests
import subprocess
import time
from typing import List, Dict
from app.core.config import OLLAMA_URL, OLLAMA_GENERAL_MODEL, OLLAMA_HOST_VERSION, OLLAMA_CODING_MODEL

def _is_ollama_running(timeout: float = 2.0) -> bool:
    try:
        requests.get(f"{OLLAMA_HOST_VERSION}", timeout=timeout)
        return True
    except Exception:
        return False

def _start_ollama(wait_seconds: float = 10.0) -> bool:
    """
    Avvia `ollama serve` in background e attende che l'API risponda.
    """
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False

    # attende con retry
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _is_ollama_running(1.0):
            return True
        time.sleep(0.5)
    return False

def _is_model_installed(model_name: str) -> bool:
    try:
        res = requests.get(f"{OLLAMA_HOST_TAGS}", timeout=3).json()
        models = [m.get("name") for m in res.get("models", []) if m.get("name")]
        return model_name in models
    except Exception:
        return False

# FIXED: model_name (mandatory) must come before timeout (optional)
def _pull_model(model_name: str, timeout: int = 600) -> None:
    """
    Esegue `ollama pull MODEL_NAME` e aspetta che finisca.
    """
    p = subprocess.Popen(["ollama", "pull", model_name])
    p.wait(timeout=timeout)

# FIXED: model_name (mandatory) must come before boolean flags (optional)
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


def _call_ollama(prompt: str) -> str:
    """
    Chiamata semplice a Ollama (API locale).
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
    return data.get("response", "")


def _call_ollama_gpt(prompt: json) -> str:
    """
    Chiamata semplice a Ollama (API locale).
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
    return data.get("response", "")


def enrich_with_llm_suggestions(issues: List[Dict], regenerated_map: Dict[str, str] = None) -> List[Dict]:
    """
    Arricchisce ogni issue con un campo 'suggestion'.
    Se presente in regenerated_map, popola 'regenerated_code_path' con il codice.
    """
    if regenerated_map is None:
        regenerated_map = {}

    enriched = []

    for issue in issues:
        enriched.append({
            "file_path": issue["file_path"],
            "detected_license": issue["detected_license"],
            "compatible": issue["compatible"],
            "reason": issue["reason"],
            "suggestion": (
                f"Verifica la licenza {issue['detected_license']} nel file "
                f"{issue['file_path']} e assicurati che sia coerente con la policy del progetto."
            ),
            # Se il file è stato rigenerato, inseriamo il codice qui
            "regenerated_code_path": regenerated_map.get(issue["file_path"]),
        })

    return enriched