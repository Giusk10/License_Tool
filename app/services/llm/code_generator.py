"""
LLM Code Generator Module.

Questo modulo interagisce con l'LLM configurato (tramite Ollama) per riscrivere il codice sorgente
che è stato segnalato come violazione della compatibilità della licenza. Costruisce prompt specifici
per garantire che il codice generato sia funzionalmente equivalente ma conforme
alla licenza del progetto di destinazione.
"""

import logging
from typing import Optional
from app.services.llm.ollama_api import call_ollama_qwen3_coder

logger = logging.getLogger(__name__)


def regenerate_code(
    code_content: str,
    main_license: str,
    detected_license: str,
    licenses: str
) -> Optional[str]:
    """
    Richiede all'LLM di rigenerare un blocco di codice sotto una licenza compatibile.

    Il prompt istruisce il modello a:
    1. Analizzare il codice originale e la sua licenza incompatibile.
    2. Riscrivere la logica per essere funzionalmente equivalente ma conforme alla
       `main_license` (preferendo licenze permissive come MIT/Apache-2.0).
    3. Assicurarsi che nessun codice originale limitato (copyleft forte) sia copiato
       parola per parola per evitare problemi di licenza.

    Args:
        code_content (str): Il codice sorgente originale che viola la compatibilità della licenza.
        main_license (str): La licenza principale del progetto (es. "MIT").
        detected_license (str): La licenza rilevata nel codice originale (es. "GPL-3.0").
        licenses (str): Una stringa che elenca le licenze compatibili da utilizzare come target.

    Returns:
        Optional[str]: La stringa del codice sorgente pulita ed estratta pronta per essere salvata,
        o None se la generazione fallisce.
    """
    # Construct the prompt split across multiple lines for readability and PEP8 compliance
    prompt = (
        f"You are a software licensing and refactoring expert. "
        f"The following code is currently under the license '{detected_license}', "
        f"which is incompatible with the project's main license '{main_license}'.\n"
        f"Your task is to find a component that is functionally equivalent but "
        f"can be released under a license compatible with '{main_license}' among these: "
        f"{licenses}.\n"
        f"If the component does not exist, regenerate it from scratch while maintaining "
        f"the same functionality but ensuring it is under a license compatible with "
        f"one of these: {licenses}.\n"
        f"Ensure that the regenerated code does not contain parts copied from the "
        f"original code to avoid licensing issues.\n\n"
        f"Here is the original code:\n"
        f"```\n{code_content}\n```\n\n"
        f"Return ONLY the regenerated code, without markdown (```) and without "
        f"extra verbal explanations. The code must be ready to be saved to a file."
    )

    try:
        response = call_ollama_qwen3_coder(prompt)
        if not response:
            return None

        # Post-elaborazione: Pulisce la formattazione Markdown se presente
        clean_response = response.strip()

        if clean_response.startswith("```"):
            # Divide per nuova riga per rimuovere la prima riga (es. ```python)
            parts = clean_response.split("\n", 1)
            if len(parts) > 1:
                clean_response = parts[1]

            # Rimuove i backtick di chiusura se presenti alla fine
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]

        clean_response = clean_response.strip()

        # Valida il codice generato
        if not validate_generated_code(clean_response):
            logger.warning("Generated code failed validation")
            return None

        return clean_response

    except Exception:  # pylint: disable=broad-exception-caught
        # La cattura ampia è intenzionale qui: agisce come fail-safe per prevenire
        # che errori imprevedibili dell'LLM o di rete blocchino l'intero flusso di lavoro di analisi.
        logger.exception("Error during code regeneration via LLM")
        return None


def validate_generated_code(code: str) -> bool:
    """
    Valida il codice generato per assicurarsi che non sia vuoto e non troppo corto.

    Args:
        code (str): La stringa del codice generato.

    Returns:
        bool: True se il codice supera la validazione, False altrimenti.
    """
    if not code or not isinstance(code, str):
        return False

    stripped = code.strip()
    if len(stripped) <= 10:  # Evita risposte molto brevi o vuote
        return False

    return True
