"""
test: services/github/test_github_client_unit.py

Questo modulo contiene test unitari per il client GitHub custom.
Verifica la logica di clonazione dei repository e la gestione dei permessi di file ReadOnly
su diversi sistemi operativi, simulando errori di filesystem e di autenticazione Git.
"""
import os
import stat
import pytest
from unittest.mock import patch, MagicMock
from git import GitCommandError
from app.services.github.github_client import clone_repo, _handle_remove_readonly


class TestHandleRemoveReadonly:
    """
    Test per la funzione handle_remove_readonly.

    Verifica che la funzione rimuova il flag ReadOnly e chiami la funzione di rimozione.
    """

    def test_handle_remove_readonly_removes_readonly_flag(self, tmp_path):
        """
        Verifica che la funzione rimuova il flag ReadOnly e chiami la funzione di rimozione.
        """
        # Crea un file di test
        test_file = tmp_path / "readonly_file.txt"
        test_file.write_text("test content")

        # Rende il file di sola lettura (0o444 = sola lettura per tutti)
        os.chmod(test_file, 0o444)

        # Mock della funzione di rimozione (es. os.unlink)
        mock_func = MagicMock()

        # Verifica anche che os.chmod venga chiamato per rendere il file scrivibile
        with patch("os.chmod") as mock_chmod:
            # Chiama handle_remove_readonly
            _handle_remove_readonly(mock_func, str(test_file), None)

            # Verifica che os.chmod sia stato chiamato per aggiungere il permesso di scrittura
            mock_chmod.assert_called_with(str(test_file), stat.S_IWRITE)

        # Verifica che la funzione di rimozione originale sia stata chiamata
        mock_func.assert_called_once_with(str(test_file))


class TestCloneRepo:
    """
    Test per la funzione clone_repo.

    Verifica la logica di clonazione, la gestione delle directory esistenti,
    la pulizia e la gestione degli errori di Git e filesystem.
    """

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_success(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from):
        """
        Test di successo della funzione clone_repo (caso base).
        """
        # Scenario: la directory non esiste, la clonazione va a buon fine
        mock_exists.return_value = False
        mock_clone_from.return_value = None

        result = clone_repo("testowner", "testrepo")

        assert result.success is True
        # Verifica la costruzione del path
        assert result.repo_path.endswith(f"testowner_testrepo")

        # Verifica le chiamate
        mock_makedirs.assert_called_once()
        mock_clone_from.assert_called_once()
        # rmtree non deve essere chiamato se exists è False
        mock_rmtree.assert_not_called()

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_with_cleanup(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from):
        """
        Test che verifica la pulizia della directory esistente prima della clonazione.
        """
        # Scenario: la directory esiste, deve essere rimossa prima della clonazione
        mock_exists.return_value = True
        mock_clone_from.return_value = None

        result = clone_repo("testowner", "testrepo")

        assert result.success is True
        # Verifica che rmtree sia stato chiamato per la pulizia
        mock_rmtree.assert_called_once()
        mock_clone_from.assert_called_once()

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_git_error(self, mock_makedirs, mock_exists, mock_clone_from):
        """
        Test che verifica la gestione di GitCommandError.
        """
        mock_exists.return_value = False
        # Simula errore Git (es. autenticazione fallita)
        mock_clone_from.side_effect = GitCommandError("clone", "Authentication failed")

        result = clone_repo("testowner", "testrepo")

        assert result.success is False
        assert result.error is not None
        assert "Authentication failed" in result.error

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_filesystem_error(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from):
        """
        Test che verifica la gestione di OSError durante la pulizia della directory.
        """
        # Scenario: la directory esiste, ma rmtree fallisce con OSError
        mock_exists.return_value = True
        mock_rmtree.side_effect = OSError("Permission denied")

        result = clone_repo("testowner", "testrepo")

        assert result.success is False
        assert result.error is not None
        assert "Filesystem error" in result.error

    @patch("app.services.github.github_client.sys")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    @patch("app.services.github.github_client.Repo.clone_from")
    def test_clone_repo_cleanup_python_3_12(self, mock_clone, mock_makedirs, mock_exists, mock_rmtree, mock_sys):
        """
        Test della logica di pulizia simulando Python 3.12+ (deve usare 'onexc').
        """
        mock_exists.return_value = True
        # Simula ambiente Python 3.12
        mock_sys.version_info = (3, 12)

        clone_repo("owner", "repo")

        # Verifica che venga usato l'argomento 'onexc' (nuovo standard)
        args, kwargs = mock_rmtree.call_args
        assert "onexc" in kwargs
        assert kwargs["onexc"] == _handle_remove_readonly
        assert "onerror" not in kwargs

    @patch("app.services.github.github_client.sys")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    @patch("app.services.github.github_client.Repo.clone_from")
    def test_clone_repo_cleanup_legacy_python(self, mock_clone, mock_makedirs, mock_exists, mock_rmtree, mock_sys):
        """
        Test della logica di pulizia simulando Python < 3.12 (deve usare 'onerror').
        """
        mock_exists.return_value = True
        # Simula ambiente Python 3.11
        mock_sys.version_info = (3, 11)

        clone_repo("owner", "repo")

        # Verifica che venga usato l'argomento 'onerror' (metodo legacy)
        args, kwargs = mock_rmtree.call_args
        assert "onerror" in kwargs
        assert kwargs["onerror"] == _handle_remove_readonly
        assert "onexc" not in kwargs

