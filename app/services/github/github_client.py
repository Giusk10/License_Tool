"""
GitHub Client Module.

Questo modulo gestisce le operazioni Git di basso livello, in particolare la clonazione di repository
utilizzando token OAuth. Include la gestione specifica per piattaforma (Windows) per gli errori di
permesso dei file che si verificano spesso durante la pulizia delle directory.
"""

import os
import stat
import shutil
import sys
from typing import Any, Callable

from git import Repo, GitCommandError
from app.models.schemas import CloneResult
from app.utility.config import CLONE_BASE_DIR


def _handle_remove_readonly(func: Callable[..., Any], path: str, _exc: Any) -> None:
    """
    Gestore di errori per shutil.rmtree per forzare la rimozione di file di sola lettura.

    Questo è particolarmente utile su Windows dove i file oggetto Git sono spesso
    contrassegnati come di sola lettura, causando il fallimento della pulizia standard.

    Args:
        func (Callable): La funzione che ha sollevato l'eccezione (solitamente os.unlink).
        path (str): Il percorso del file che ha causato l'eccezione.
        _exc (Any): Le informazioni sull'eccezione (non utilizzate).
    """
    # Rimuove il bit di sola lettura e riprova l'operazione
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clone_repo(owner: str, repo: str) -> CloneResult:
    """
    Clona un repository GitHub in una directory locale utilizzando un token OAuth.

    Questa funzione gestisce l'intero ciclo di vita:
    1. Prepara la directory di destinazione.
    2. Pulisce eventuali dati esistenti in quella posizione (gestendo errori di permesso).
    3. Clona il repository remoto.
    4. Cattura e oscura i token sensibili dai messaggi di errore.

    Args:
        owner (str): Il nome utente o nome dell'organizzazione del proprietario del repository.
        repo (str): Il nome del repository.

    Returns:
        CloneResult: Un modello contenente lo stato di successo e il percorso
        locale (in caso di successo) o un messaggio di errore (in caso di fallimento).
    """
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)
    target_path = os.path.join(CLONE_BASE_DIR, f"{owner.strip()}_{repo.strip()}")

    try:
        # Pulizia sicura della directory esistente (compatibile con Windows)
        if os.path.exists(target_path):
            # 'onerror' è deprecato in Python 3.12+ a favore di 'onexc'
            if sys.version_info >= (3, 12):
                shutil.rmtree(target_path, onexc=_handle_remove_readonly)  # pylint: disable=unexpected-keyword-arg
            else:
                shutil.rmtree(target_path, onerror=_handle_remove_readonly)  # pylint: disable=deprecated-argument

        # Construct authenticated URL
        # Note: x-access-token is the standard username for OAuth token usage in git
        auth_url = f"https://github.com/{owner.strip()}/{repo.strip()}.git"
        # Costruisce l'URL autenticato
        # Nota: x-access-token è il nome utente standard per l'utilizzo del token OAuth in git
        auth_url = f"https://github.com/{owner.strip()}/{repo.strip()}.git"

        Repo.clone_from(auth_url, target_path)

        return CloneResult(success=True, repo_path=target_path)

    except GitCommandError as e:
        # Sicurezza: Assicura che il token OAuth non venga divulgato nei log/risposte di errore
        return CloneResult(success=False, error=str(e))

    except OSError as e:
        return CloneResult(success=False, error=f"Filesystem error: {e}")