"""
test: services/downloader/test_download_unit.py

Unit tests for the download service module.
This module verifies the logic for creating ZIP archives of cloned repositories,
handling various scenarios including success, missing repositories, special characters,
overwriting existing archives, and empty repositories.
"""

import os
import shutil
from unittest.mock import patch
import pytest
from app.services.downloader.download_service import perform_download


class TestPerformDownload:
    """Tests for the perform_download function."""

    def test_perform_download_success(self, tmp_path):
        """Test successful download when the repository exists."""
        # Setup test directory
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create repository directory with some files
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

            # Verify that the zip file was created
            assert os.path.exists(result)

            # Verify that the zip contains the files (extract momentarily to check)
            extract_dir = str(tmp_path / "extract")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(result, extract_dir)

            # The zip should contain the repo_dir_name folder
            extracted_repo_path = os.path.join(extract_dir, repo_dir_name)
            assert os.path.exists(extracted_repo_path)
            assert os.path.exists(os.path.join(extracted_repo_path, "test.txt"))

    def test_perform_download_repository_not_found(self, tmp_path):
        """Test that raises ValueError when the repository does not exist."""
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
        """Test that the zip filename is correct."""
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

            # Verify the filename
            expected_name = f"{repo_dir_name}_download.zip"
            assert result.endswith(expected_name)
            assert os.path.basename(result) == expected_name

    def test_perform_download_handles_special_characters_in_names(self, tmp_path):
        """Test with special characters in owner/repo names."""
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

            # Verify it works with special characters too
            assert os.path.exists(result)
            assert f"{repo_dir_name}_download.zip" in result

    def test_perform_download_overwrites_existing_zip(self, tmp_path):
        """Test that it overwrites an existing zip file."""
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Create the repository directory
        os.makedirs(repo_path, exist_ok=True)

        # Create an existing zip with different content
        zip_path = os.path.join(clone_base_dir, f"{repo_dir_name}_download.zip")
        with open(zip_path, "w") as f:
            f.write("old zip content")

        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verify that the file was overwritten (it is now a valid zip)
            assert result == zip_path
            assert os.path.exists(result)

            # Verify that it is a valid zip file (try opening it)
            try:
                shutil.unpack_archive(result, str(tmp_path / "test_extract"))
            except shutil.ReadError:
                pytest.fail("The created file is not a valid zip archive")

    def test_perform_download_empty_repository(self, tmp_path):
        """Test download of an empty repository."""
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

            # Verify that the zip is created even for an empty repository
            assert os.path.exists(result)

            # Verify that the zip contains the empty folder
            extract_dir = str(tmp_path / "extract_empty")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(result, extract_dir)

            extracted_repo_path = os.path.join(extract_dir, repo_dir_name)
            assert os.path.exists(extracted_repo_path)
            assert os.path.isdir(extracted_repo_path)
            # Verify that it is empty
            assert len(os.listdir(extracted_repo_path)) == 0