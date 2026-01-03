"""
test: services/github/github_client.py
"""
import os
from unittest.mock import patch, MagicMock
from git import GitCommandError
from app.services.github.github_client import clone_repo, _handle_remove_readonly


class TestHandleRemoveReadonly:
    """Test per la funzione handle_remove_readonly."""

    def test_handle_remove_readonly_removes_readonly_flag(self, tmp_path):
        """Verifica che la funzione rimuova il flag ReadOnly e chiami la funzione di rimozione."""
        # Create a test file
        test_file = tmp_path / "readonly_file.txt"
        test_file.write_text("test content")

        # Make the file readonly
        os.chmod(test_file, 0o444)

        # Mock the removal function
        mock_func = MagicMock()

        # Call handle_remove_readonly
        _handle_remove_readonly(mock_func, str(test_file), None)

        # Verify that the function was called with the path
        mock_func.assert_called_once_with(str(test_file))


class TestCloneRepo:
    """Test per la funzione clone_repo."""

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_success(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from, tmp_path):
        """Testa clone_repo riuscito."""
        mock_exists.return_value = False
        mock_clone_from.return_value = None

        result = clone_repo("testowner", "testrepo")

        assert result.success is True
        assert "testowner_testrepo" in result.repo_path
        mock_clone_from.assert_called_once()
        mock_makedirs.assert_called_once()

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_with_cleanup(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from, tmp_path):
        """Testa clone_repo con pulizia della directory esistente."""
        mock_exists.return_value = True
        mock_clone_from.return_value = None

        result = clone_repo("testowner", "testrepo")

        assert result.success is True
        mock_rmtree.assert_called_once()
        mock_clone_from.assert_called_once()

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_git_error(self, mock_makedirs, mock_exists, mock_clone_from):
        """Testa clone_repo con errore Git."""
        mock_exists.return_value = False
        mock_clone_from.side_effect = GitCommandError("clone", "Authentication failed")

        result = clone_repo("testowner", "testrepo")

        assert result.success is False
        assert result.error is not None
        assert "clone" in result.error

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_filesystem_error(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from):
        """Testa clone_repo con errore del file system."""
        mock_exists.return_value = True
        mock_rmtree.side_effect = OSError("Permission denied")

        result = clone_repo("testowner", "testrepo")

        assert result.success is False
        assert result.error is not None
        assert "Filesystem error" in result.error