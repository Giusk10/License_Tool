from typing import Optional
from app.services.llm_helper import _call_ollama  # se vuoi rendere pubblico, spostalo

def regenerate_code(description: str, language: str = "python") -> Optional[str]:
    """
    Chiede a Ollama di rigenerare un blocco di codice con licenza permissiva.
    Qui lo teniamo come funzione generica, potrai integrarla sui singoli file.
    """
    prompt = (
        f"Rigenera un'implementazione {language} con licenza permissiva (MIT) "
        f"per il seguente componente, mantenendo la stessa funzionalità:\n\n"
        f"{description}\n\n"
        "Non includere testo di licenza nel codice, solo il codice."
    )
    try:
        return _call_ollama(prompt)
    except Exception:
        return None
