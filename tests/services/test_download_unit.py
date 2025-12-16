"""
test: services/dowloader/download_service.py
"""
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import pytest
from app.services.dowloader.download_service import perform_download


class TestPerformDownload:
    """Test per la funzione perform_download"""

    def test_perform_download_success(self, tmp_path):
        """Test download riuscito quando il repository esiste"""
        # Setup directory di test
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Crea la directory del repository con alcuni file
        os.makedirs(repo_path, exist_ok=True)
        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        # Mock CLONE_BASE_DIR
        with patch("app.services.dowloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verifica che il path dello zip sia corretto
            expected_zip_base = os.path.join(clone_base_dir, f"{repo_dir_name}_download")
            expected_zip_path = expected_zip_base + ".zip"
            assert result == expected_zip_path

            # Verifica che il file zip sia stato creato
            assert os.path.exists(result)

            # Verifica che lo zip contenga i file (estraiamo temporaneamente per controllare)
            extract_dir = str(tmp_path / "extract")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(result, extract_dir)

            # Lo zip dovrebbe contenere la cartella repo_dir_name
            extracted_repo_path = os.path.join(extract_dir, repo_dir_name)
            assert os.path.exists(extracted_repo_path)
            assert os.path.exists(os.path.join(extracted_repo_path, "test.txt"))

    def test_perform_download_repository_not_found(self, tmp_path):
        """Test that raises ValueError when the repository does not exist"""
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "nonexistent_repo"

        with patch("app.services.dowloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            with pytest.raises(ValueError) as exc_info:
                perform_download(owner, repo)

            expected_error = f"Repository not found at {os.path.join(clone_base_dir, f'{owner}_{repo}')}. Please clone it first."
            assert str(exc_info.value) == expected_error

    def test_perform_download_creates_zip_with_correct_name(self, tmp_path):
        """Test che il nome del file zip sia corretto"""
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "octocat"
        repo = "Hello-World"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Crea la directory del repository
        os.makedirs(repo_path, exist_ok=True)

        with patch("app.services.dowloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verifica il nome del file
            expected_name = f"{repo_dir_name}_download.zip"
            assert result.endswith(expected_name)
            assert os.path.basename(result) == expected_name

    def test_perform_download_handles_special_characters_in_names(self, tmp_path):
        """Test con caratteri speciali nei nomi owner/repo"""
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test-owner_123"
        repo = "repo.with.dots"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Crea la directory del repository
        os.makedirs(repo_path, exist_ok=True)

        with patch("app.services.dowloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verifica che funzioni anche con caratteri speciali
            assert os.path.exists(result)
            assert f"{repo_dir_name}_download.zip" in result

    def test_perform_download_overwrites_existing_zip(self, tmp_path):
        """Test che sovrascrive un file zip esistente"""
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Crea la directory del repository
        os.makedirs(repo_path, exist_ok=True)

        # Crea un file zip esistente con contenuto diverso
        zip_path = os.path.join(clone_base_dir, f"{repo_dir_name}_download.zip")
        with open(zip_path, "w") as f:
            f.write("old zip content")

        with patch("app.services.dowloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verifica che il file sia stato sovrascritto (ora è un vero zip)
            assert result == zip_path
            assert os.path.exists(result)

            # Verifica che sia un file zip valido (prova ad aprirlo)
            try:
                shutil.unpack_archive(result, str(tmp_path / "test_extract"))
            except shutil.ReadError:
                pytest.fail("Il file creato non è un archivio zip valido")

    def test_perform_download_empty_repository(self, tmp_path):
        """Test download di un repository vuoto"""
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "empty_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Crea la directory vuota del repository
        os.makedirs(repo_path, exist_ok=True)

        with patch("app.services.dowloader.download_service.CLONE_BASE_DIR", clone_base_dir):
            result = perform_download(owner, repo)

            # Verifica che lo zip sia creato anche per repository vuoto
            assert os.path.exists(result)

            # Verifica che lo zip contenga la cartella vuota
            extract_dir = str(tmp_path / "extract_empty")
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(result, extract_dir)

            extracted_repo_path = os.path.join(extract_dir, repo_dir_name)
            assert os.path.exists(extracted_repo_path)
            assert os.path.isdir(extracted_repo_path)
            # Verifica che sia vuota
            assert len(os.listdir(extracted_repo_path)) == 0

