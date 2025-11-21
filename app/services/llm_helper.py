import json
import requests
from typing import List, Dict
from app.core.config import OLLAMA_URL, OLLAMA_GENERAL_MODEL


def _call_ollama(prompt: str) -> str:
    """
    Chiamata semplice a Ollama (API locale).
    (Non usata direttamente in questa versione, ma pronta per usi futuri.)
    """
    payload = {
        "model": OLLAMA_GENERAL_MODEL,
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
    (Non usata direttamente in questa versione, ma pronta per usi futuri.)
    """
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
