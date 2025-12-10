"""
This module interacts with the LLM (Ollama) to rewrite source code that violates
license compatibility.
"""

from typing import Optional
from app.services.llm_helper import _call_ollama  # se vuoi rendere pubblico, spostalo

def regenerate_code(
    code_content: str,
    main_license: str,
    detected_license: str,
    licenses: str
) -> Optional[str]:
    """
    Requests the LLM to regenerate a code block under a compatible license.

    The prompt instructs the model to:
    1. Analyze the original code and its incompatible license.
    2. Rewrite the logic to be functionally equivalent but compliant with the `main_license`
       (preferring permissive licenses like MIT/Apache-2.0 if possible).
    3. Ensure no original restricted code (strong copyleft) is verbatim copied if it violates terms.

    Args:
        code_content (str): The original source code that violates license compatibility.
        main_license (str): The primary license of the project (e.g., "MIT", "Apache-2.0").
        detected_license (str): The license detected in the original code (e.g., "GPL-3.0").
        language (str): The programming language of the code snippet (default is "python").

    Returns:
        Optional[str]: The clean, extracted source code string, or None if generation fails.
    """
    prompt = (
        f"Sei un esperto di licenze software e refactoring. "
        f"Il seguente codice è attualmente sotto licenza '{detected_license}', che è incompatibile con la licenza principale del progetto '{main_license}'.\n"
        f"Il tuo compito è ricercare un componente in modo che sia funzionalmente equivalente ma rilasciabile sotto una licenza compatibile con '{main_license} tra queste: {licenses}'.\n"
        f"Se il componente non esiste, rigeneralo da zero mantenendo la stessa funzionalità ma con una licenza compatibile tra queste: {licenses}.\n"
        f"Assicurati che il codice rigenerato non contenga parti copiate dal codice originale per evitare problemi di licenza.\n\n"
        f"Ecco il codice originale:\n"
        f"```\n{code_content}\n```\n\n"
        f"Restituisci SOLO il codice rigenerato, senza markdown (```) e senza spiegazioni verbali extra. Il codice deve essere pronto per essere salvato su file."
    )
    try:
        response = _call_ollama(prompt)
        if not response:
            return None

        # Clean up the response to remove markdown formatting if present
        clean_response = response.strip()
        if clean_response.startswith("```"):
            # Remove the first line (```)
            clean_response = clean_response.split("\n", 1)[1]
            # Removes the last line if it ends with ```
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]

        return clean_response.strip()
    except Exception:
        return None
