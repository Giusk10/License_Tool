import requests
from typing import List
from app.core.config import OLLAMA_URL, OLLAMA_MODEL
from app.models.schemas import LicenseIssue

def _call_ollama(prompt: str) -> str:
    """
    Chiamata semplice a Ollama (API locale).
    Si aspetta compatibilità con endpoint /api/generate.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    # formato tipico: {"response": "..."}
    return data.get("response", "")

def enrich_with_llm_suggestions(issues):
    enriched = []

    for issue in issues:
        # issue è un dict → usare issue["campo"]
        compatible = issue["compatible"]
        reason = issue["reason"]
        file_path = issue["file"]
        license_id = issue["license"]

        # qui fai la tua logica LLM
        suggestion = f"Verifica la licenza {license_id} nel file {file_path}."

        enriched.append({
            "file": file_path,
            "license": license_id,
            "compatible": compatible,
            "reason": reason,
            "suggestion": suggestion
        })

    return enriched
