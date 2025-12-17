"""
This module handles the preparation of repository archives for download.
It provides functionality to zip cloned repositories.
"""

import shutil
import os
from app.utility.config import CLONE_BASE_DIR

def perform_download(owner: str, repo: str) -> str:
    """
    Archives the repository folder into a ZIP file and returns the file path.

    Args:
        owner (str): The owner of the GitHub repository.
        repo (str): The repository name.

    Returns:
        str: The file system path of the generated ZIP archive.

    Raises:
        ValueError: If the repository directory does not exist.
    """
    repo_dir_name = f"{owner}_{repo}"
    repo_path = os.path.join(CLONE_BASE_DIR, repo_dir_name)

    if not os.path.exists(repo_path):
        raise ValueError(f"Repository not found at {repo_path}. Please clone it first.")

    # Defines the zip file name (without extension, as shutil adds it automatically)
    zip_base_name = os.path.join(CLONE_BASE_DIR, f"{repo_dir_name}_download")

    # Creates the archive.
    # Using root_dir=CLONE_BASE_DIR and base_dir=repo_dir_name ensures the ZIP
    # contains the top-level folder itself, keeping the structure organized.
    zip_path = shutil.make_archive(
        base_name=zip_base_name,
        format="zip",
        root_dir=CLONE_BASE_DIR,
        base_dir=repo_dir_name
    )

    return zip_path
