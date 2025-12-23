"""
Download Service Module.

This module handles the preparation of repository archives for download.
It provides functionality to compress cloned repository directories into
ZIP files, making them ready for client download.
"""

import os
import shutil
import logging

from app.utility.config import CLONE_BASE_DIR

logger = logging.getLogger(__name__)


def perform_download(owner: str, repo: str) -> str:
    """
    Archives a local repository folder into a ZIP file.

    It validates the existence of the repository in the clone directory,
    creates a ZIP archive, and returns the absolute path to the generated file.

    Args:
        owner (str): The username or organization name of the repository owner.
        repo (str): The name of the repository.

    Returns:
        str: The full file system path of the generated ZIP archive.

    Raises:
        ValueError: If the repository directory does not exist at the expected path.
        OSError: If there are permission issues or disk errors during archiving.
    """
    repo_dir_name = f"{owner}_{repo}"
    repo_path = os.path.join(CLONE_BASE_DIR, repo_dir_name)

    if not os.path.exists(repo_path):
        logger.error("Repository not found for download: %s", repo_path)
        raise ValueError(f"Repository not found at {repo_path}. Please clone it first.")

    # Define the output filename (shutil.make_archive appends the extension automatically)
    zip_base_name = os.path.join(CLONE_BASE_DIR, f"{repo_dir_name}_download")

    try:
        # Create the ZIP archive.
        # root_dir=CLONE_BASE_DIR and base_dir=repo_dir_name ensures the archive
        # contains the folder 'owner_repo/' at its root.
        zip_path = shutil.make_archive(
            base_name=zip_base_name,
            format="zip",
            root_dir=CLONE_BASE_DIR,
            base_dir=repo_dir_name
        )

        logger.info("Successfully created ZIP archive: %s", zip_path)
        return zip_path

    except Exception as e:
        logger.exception("Failed to create ZIP archive for %s/%s", owner, repo)
        raise OSError(f"Failed to create ZIP archive: {e}") from e
