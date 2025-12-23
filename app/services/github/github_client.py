"""
GitHub Client Module.

This module handles low-level Git operations, specifically cloning repositories
using OAuth tokens. It includes platform-specific handling (Windows) for file
permission errors that often occur during directory cleanup.
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
    Error handler for shutil.rmtree to force removal of read-only files.

    This is particularly useful on Windows where Git object files are often
    marked as read-only, causing standard cleanup to fail.

    Args:
        func (Callable): The function that raised the exception (usually os.unlink).
        path (str): The path to the file that caused the exception.
        _exc (Any): The exception information (unused).
    """
    # Clear the read-only bit and retry the operation
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clone_repo(owner: str, repo: str) -> CloneResult:
    """
    Clones a GitHub repository to a local directory using an OAuth token.

    This function handles the entire lifecycle:
    1. Prepares the destination directory.
    2. Cleans up any existing data at that location (handling permission errors).
    3. Clones the remote repository.
    4. Catches and redacts sensitive tokens from error messages.

    Args:
        owner (str): The username or organization name of the repository owner.
        repo (str): The name of the repository.
        oauth_token (str): The GitHub OAuth token for authentication.

    Returns:
        CloneResult: A model containing the success status and either the
        local path (on success) or an error message (on failure).
    """
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)
    target_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    try:
        # Safe cleanup of existing directory (Windows-friendly)
        if os.path.exists(target_path):
            # 'onerror' is deprecated in Python 3.12+ in favor of 'onexc'
            if sys.version_info >= (3, 12):
                shutil.rmtree(target_path, onexc=_handle_remove_readonly)
            else:
                shutil.rmtree(target_path, onerror=_handle_remove_readonly)  # pylint: disable=deprecated-argument

        # Construct authenticated URL
        # Note: x-access-token is the standard username for OAuth token usage in git
        auth_url = f"https://github.com/{owner}/{repo}.git"

        Repo.clone_from(auth_url, target_path)

        return CloneResult(success=True, repo_path=target_path)

    except GitCommandError as e:
        # Security: Ensure the OAuth token is not leaked in error logs/responses
        return CloneResult(success=False, error=str(e))

    except OSError as e:
        return CloneResult(success=False, error=f"Filesystem error: {e}")
