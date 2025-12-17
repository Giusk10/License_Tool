"""
Handles Git operations, specifically cloning repositories using OAuth tokens.
Includes Windows-specific handling for file permission errors during cleanup.
"""

import os
import stat
import shutil
from git import Repo, GitCommandError
from app.models.schemas import CloneResult
from app.utility.config import CLONE_BASE_DIR

def handle_remove_readonly(func, path, exc):
    """
    Forces file removal by changing permissions if a read-only error occurs.

    Args:
        func: The function that raised the exception.
        path: The file path that caused the exception.
        exc: The exception information.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)

def clone_repo(owner: str, repo: str, oauth_token: str) -> CloneResult:
    """
    Clones a GitHub repository using an OAuth token for authentication.

    Args:
        owner (str): The owner of the repository.
        repo (str): The name of the repository.
        oauth_token (str): The OAuth token for authentication.

    Returns:
        CloneResult: The result of the clone operation, including success status and path or error message.
    """
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)

    target_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    try:
        # Safe cleanup of existing directory for Windows
        if os.path.exists(target_path):
            shutil.rmtree(target_path, onerror=handle_remove_readonly)

        # Construct authenticated URL
        auth_url = f"https://x-access-token:{oauth_token}@github.com/{owner}/{repo}.git"

        Repo.clone_from(auth_url, target_path)
        return CloneResult(success=True, repo_path=target_path)

    except GitCommandError as e:
        safe_error = str(e).replace(oauth_token, "***")
        return CloneResult(success=False, error=safe_error)
    except OSError as e:
        return CloneResult(success=False, error=f"Filesystem error: {e}")
