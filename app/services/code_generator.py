from typing import Optional
from app.services.llm_helper import _call_ollama  # se vuoi rendere pubblico, spostalo

def regenerate_code(
    code_content: str,
    main_license: str,
    detected_license: str,
    language: str = "python"
) -> Optional[str]:
    """
    Chiede a Ollama di rigenerare un blocco di codice con licenza compatibile.
    """
    prompt = (
        f"Sei un esperto di licenze software e refactoring. "
        f"Il seguente codice è attualmente sotto licenza '{detected_license}', che è incompatibile con la licenza principale del progetto '{main_license}'.\n"
        f"Il tuo compito è riscrivere/rigenerare questo codice in modo che sia funzionalmente equivalente ma rilasciabile sotto una licenza compatibile con '{main_license}' (preferibilmente MIT o Apache-2.0, o la stessa '{main_license}').\n"
        f"Se il codice originale ha vincoli forti (es. copyleft forte), riscrivilo da zero usando algoritmi standard o logica pulita per evitare violazioni.\n"
        f"Dichiara esplicitamente la nuova licenza scelta nei commenti se necessario.\n\n"
        f"Ecco il codice originale:\n"
        f"```\n{code_content}\n```\n\n"
        f"Restituisci SOLO il codice rigenerato, senza markdown (```) e senza spiegazioni verbali extra. Il codice deve essere pronto per essere salvato su file."
    )
    try:
        return _call_ollama(prompt)
    except Exception:
        return None
