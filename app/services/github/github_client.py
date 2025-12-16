import os
import stat
import shutil
from git import Repo, GitCommandError
from app.models.schemas import CloneResult
from app.utility.config import CLONE_BASE_DIR

def handle_remove_readonly(func, path, exc):
    """Forza la rimozione su Windows togliendo il flag ReadOnly."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

def clone_repo(owner: str, repo: str, oauth_token: str) -> CloneResult:
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)

    target_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    try:
        # PULIZIA PIÙ ROBUSTA SU WINDOWS
        if os.path.exists(target_path):
            shutil.rmtree(target_path, onerror=handle_remove_readonly)

        # Sintassi OAuth corretta
        auth_url = f"https://x-access-token:{oauth_token}@github.com/{owner}/{repo}.git"

        Repo.clone_from(auth_url, target_path)
        return CloneResult(success=True, repo_path=target_path)

    except GitCommandError as e:
        safe_error = str(e).replace(oauth_token, "***")
        return CloneResult(success=False, error=safe_error)
    except OSError as e:
        return CloneResult(success=False, error=f"Filesystem error: {e}")
