"""
Download Service Unit Test Module.

Questo modulo contiene test unitari per `app.services.downloader.download_service`.
Garantisce che i repository clonati localmente possano essere correttamente archiviati in
file ZIP, gestendo vari scenari come directory mancanti, caratteri speciali
e sovrascrittura di archivi esistenti.

La suite si concentra su:
1. Creazione dell'archivio: Uso corretto di shutil per generare file ZIP validi.
2. Integrità del file system: Verifica dei percorsi e del contenuto all'interno dell'archivio.
3. Resilienza agli errori: Gestione di repository inesistenti e cartelle vuote.
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
    Test suite per la funzione 'perform_download'.

    Verifica che il servizio identifichi correttamente il percorso locale del repository
    e lo comprima in una struttura ZIP prevedibile.
    """

    def test_perform_download_success(self, tmp_path):
        """
        Valida l'archiviazione corretta di un repository standard.

        Garantisce che:
        - Il percorso ZIP generato sia corretto.
        - Il file ZIP fisico venga creato.
        - Il contenuto dell'archivio corrisponda alla struttura della directory sorgente.
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
        Testa la gestione degli errori per repository mancanti.

        Verifica che venga sollevato un ValueError con un messaggio descrittivo
        se la funzione viene chiamata per un repository non ancora clonato.
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
        Verifica la convenzione di denominazione per gli archivi generati.

        Garantisce che l'archivio segua il pattern '{owner}_{repo}_download.zip'
        per mantenere la coerenza nell'applicazione.
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
        Testa la resilienza contro caratteri non standard negli identificatori.

        Garantisce che punti, trattini e underscore nei nomi di owner o repository
        non compromettano le operazioni sul file system o la creazione dell'archivio.
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
        Garantisce che il servizio gestisca correttamente archivi esistenti (idempotenza).

        Valida che se esiste già uno ZIP con lo stesso nome, venga
        sovrascritto con un nuovo archivio valido invece di causare errori di scrittura o corruzione.
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
        Verifica il comportamento durante l'archiviazione di una directory vuota.

        Garantisce che il servizio possa comunque creare un file ZIP valido (anche se piccolo)
        per un repository senza file, mantenendo la coerenza dell'API.
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

    def test_perform_download_archive_failure(self, tmp_path):
        """
        Testa la gestione degli errori quando il processo di archiviazione fallisce.

        Verifica che se shutil.make_archive solleva un'eccezione (es. disco pieno,
        permessi), il servizio la intercetti, la logghi e la rilanci come OSError
        con un messaggio descrittivo.
        """
        clone_base_dir = str(tmp_path / "clones")
        os.makedirs(clone_base_dir, exist_ok=True)

        owner = "test_owner"
        repo = "test_repo"
        repo_dir_name = f"{owner}_{repo}"
        repo_path = os.path.join(clone_base_dir, repo_dir_name)

        # Ensure the repo directory exists so we pass the initial check
        os.makedirs(repo_path, exist_ok=True)

        # Mock CLONE_BASE_DIR and force shutil.make_archive to fail
        with patch("app.services.downloader.download_service.CLONE_BASE_DIR", clone_base_dir), \
                patch("shutil.make_archive", side_effect=OSError("Disk full")):
            with pytest.raises(OSError) as exc_info:
                perform_download(owner, repo)

            # Verify the exception message wraps the original error
            assert "Failed to create ZIP archive" in str(exc_info.value)
            assert "Disk full" in str(exc_info.value)

