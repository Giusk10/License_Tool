import os
import shutil
from git import Repo, GitCommandError
from app.models.schemas import CloneResult
from app.core.config import CLONE_BASE_DIR

# Aggiungi il parametro oauth_token
def clone_repo(owner: str, repo: str, oauth_token: str) -> CloneResult:
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)

    target_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    try:
        # PULIZIA: Fondamentale per OAuth (utenti diversi potrebbero clonare la stessa repo)
        if os.path.exists(target_path):
            shutil.rmtree(target_path)

        # Sintassi OAuth corretta
        auth_url = f"https://x-access-token:{oauth_token}@github.com/{owner}/{repo}.git"

        Repo.clone_from(auth_url, target_path)
        return CloneResult(success=True, repo_path=target_path)

    except GitCommandError as e:
        # Maschera il token per sicurezza nei log
        safe_error = str(e).replace(oauth_token, "***")
        return CloneResult(success=False, error=safe_error)
    except OSError as e:
        return CloneResult(success=False, error=f"Errore filesystem: {e}")