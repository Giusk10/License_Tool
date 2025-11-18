import os
from git import Repo, GitCommandError
from app.models.schemas import CloneResult
from app.core.config import GITHUB_TOKEN, CLONE_BASE_DIR



def clone_repo(owner: str, repo: str) -> CloneResult:
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)

    target_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    if os.path.exists(target_path):
        # se vuoi sovrascrivere, puoi cancellare
        pass

    try:
        Repo.clone_from(
            f"https://{GITHUB_TOKEN}:x-oauth-basic@github.com/{owner}/{repo}.git",
            target_path
        )
        return CloneResult(success=True, repo_path=target_path)
    except GitCommandError as e:
        return CloneResult(success=False, error=str(e))
