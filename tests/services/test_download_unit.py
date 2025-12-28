"""
Download Service Unit Test Module.

This module contains unit tests for `app.services.downloader.download_service`.
It ensures that locally cloned repositories can be correctly archived into
ZIP files, handling various scenarios such as missing directories, special
characters, and existing archive overwrites.

The suite focuses on:
1. Archive Creation: Correct use of shutil to generate valid ZIP files.
2. File System Integrity: Verification of paths and content within the archive.
3. Error Resilience: Handling of non-existent repositories and empty folders.
"""

import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import pytest
from app.services.downloader.download_service import perform_download

# ==================================================================================
#                          TEST CLASS: PERFORM DOWNLOAD
# ==================================================================================

class TestPerformDownload:
    """
    Test suite for the 'perform_download' function.

    Verifies that the service correctly identifies the local repository path
    and compresses it into a predictable ZIP structure.
    """

    def test_perform_download_success(self, tmp_path):
        """
        Validates the successful archival of a standard repository.

        Ensures that:
        - The generated ZIP path is correct.
        - The physical ZIP file is created.
        - The archive contents match the source directory structure.
        """
        # Setup test directory
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create the repository directory with some files
        os.makedirs(repo_path, exist_ok=True)
        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        # Mock CLONE_BASE_DIR
        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verify that the zip path is correct
            expected_zip_base = os.path.join(clone_base_dir, f"{repo_dir_name}_download")
            expected_zip_path = expected_zip_base + ".zip"
            assert result == expected_zip_path

            # Verify that the zip file has been created
            assert os.path.exists(result)

            # Verify that the zip contains the files (we temporarily extract it to check)
            extract_dir = str(tmp_path / "extract")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(result, extract_dir)

            # The zip should contain the repo_dir_name folder
            extracted_repo_path = os.path.join(extract_dir, repo_dir_name)
            assert os.path.exists(extracted_repo_path)
            assert os.path.exists(os.path.join(extracted_repo_path, "test.txt"))


    def test_perform_download_repository_not_found(self, tmp_path):
        """
        Tests the error handling for missing repositories.

        Verifies that a ValueError is raised with a descriptive message
        if the function is called for a repository that hasn't been cloned yet.
        """
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "nonexistent_repo"

        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            with pytest.raises(ValueError) as exc_info:
                perform_download(owner, repo)

            expected_error = f"Repository not found at {os.path.join(clone_base_dir, f'{owner}_{repo}')}. Please clone it first."
            assert str(exc_info.value) == expected_error


    def test_perform_download_creates_zip_with_correct_name(self, tmp_path):
        """
        Verifies the naming convention for the generated archives.

        Ensures the archive follows the pattern '{owner}_{repo}_download.zip'
        to maintain consistency across the application.
        """
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "octocat"
        repo = "Hello-World"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create the repository directory
        os.makedirs(repo_path, exist_ok=True)

        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verify the file name
            expected_name = f"{repo_dir_name}_download.zip"
            assert result.endswith(expected_name)
            assert os.path.basename(result) == expected_name


    def test_perform_download_handles_special_characters_in_names(self, tmp_path):
        """
        Tests resilience against non-standard characters in identifiers.

        Ensures that dots, dashes, and underscores in owner or repository
        names do not break the file system operations or archive creation.
        """
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test-owner_123"
        repo = "repo.with.dots"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create the repository directory
        os.makedirs(repo_path, exist_ok=True)

        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verify that it also works with special characters
            assert os.path.exists(result)
            assert f"{repo_dir_name}_download.zip" in result


    def test_perform_download_overwrites_existing_zip(self, tmp_path):
        """
        Ensures the service handles existing archives correctly (Idempotency).

        Validates that if a ZIP with the same name already exists, it is
        overwritten with a fresh, valid archive instead of causing a
        WriteError or corruption.
        """
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create the repository directory
        os.makedirs(repo_path, exist_ok=True)

        # Create an existing zip file with different content
        zip_path = os.path.join(clone_base_dir, f"{repo_dir_name}_download.zip")
        with open(zip_path, "w") as f:
            f.write("old zip content")

        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verify that the file has been overwritten (it is now a real zip)
            assert result == zip_path
            assert os.path.exists(result)

            # Verify that it is a valid zip file (try opening it)
            try:
                shutil.unpack_archive(result, str(tmp_path / "test_extract"))
            except shutil.ReadError:
                pytest.fail("Il file creato non è un archivio zip valido")


    def test_perform_download_empty_repository(self, tmp_path):
        """
        Checks behavior when archiving an empty directory.

        Ensures that the service can still create a valid (though small) ZIP
        file for a repository that contains no files, maintaining
        API consistency.
        """
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "empty_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create empty repository directory
        os.makedirs(repo_path, exist_ok=True)

        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Make sure the zip is created even for an empty repository
            assert os.path.exists(result)

            # Make sure the zip contains the empty folder
            extract_dir = str(tmp_path / "extract_empty")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(result, extract_dir)

            extracted_repo_path = os.path.join(extract_dir, repo_dir_name)
            assert os.path.exists(extracted_repo_path)
            assert os.path.isdir(extracted_repo_path)
            # Check that it is empty
            assert len(os.listdir(extracted_repo_path)) == 0

