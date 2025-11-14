import requests
from typing import List, Dict
from app.core.config import OLLAMA_URL, OLLAMA_MODEL


def _call_ollama(prompt: str) -> str:
    """
    Chiamata semplice a Ollama (API locale).
    (Non usata direttamente in questa versione, ma pronta per usi futuri.)
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def enrich_with_llm_suggestions(issues: List[Dict]) -> List[Dict]:
    """
    Arricchisce ogni issue con un campo 'suggestion'.
    Per ora usiamo una frase statica, ma puoi sostituirla con _call_ollama(...)
    """

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
            # futuro: se rigeneri codice con LLM, salva qui il path
            "regenerated_code_path": issue.get("regenerated_code_path"),
        })

    return enriched
