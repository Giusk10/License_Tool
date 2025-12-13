from typing import Optional
from app.services.llm.ollama_api import call_ollama_qwen3_coder  # se vuoi rendere pubblico, spostalo

def regenerate_code(
    code_content: str,
    main_license: str,
    detected_license: str,
    licenses: str
) -> Optional[str]:
    """
    Chiede a Ollama di rigenerare un blocco di codice con licenza compatibile.
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
        response = call_ollama_qwen3_coder(prompt)
        if not response:
            return None
            
        # Pulizia Markdown se presente
        clean_response = response.strip()
        if clean_response.startswith("```"):
            # Rimuove la prima riga (```python o simile)
            clean_response = clean_response.split("\n", 1)[1]
            # Rimuove l'ultima riga (```)
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]
        
        return clean_response.strip()
    except Exception:
        return None