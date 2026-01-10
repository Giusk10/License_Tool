"""
test: services/github/test_github_client_unit.py
"""
import os
import stat
import pytest
from unittest.mock import patch, MagicMock
from git import GitCommandError
from app.services.github.github_client import clone_repo, _handle_remove_readonly


class TestHandleRemoveReadonly:
    """Tests for the handle_remove_readonly function."""

    def test_handle_remove_readonly_removes_readonly_flag(self, tmp_path):
        """Verify that the function removes the ReadOnly flag and calls the removal function."""
        # Create a test file
        test_file = tmp_path / "readonly_file.txt"
        test_file.write_text("test content")

        # Make the file readonly (0o444 = read only for everyone)
        os.chmod(test_file, 0o444)

        # Mock the removal function (e.g., os.unlink)
        mock_func = MagicMock()

        # We also verify that os.chmod is called inside the helper to make it writable
        with patch("os.chmod") as mock_chmod:
            # Call handle_remove_readonly
            _handle_remove_readonly(mock_func, str(test_file), None)

            # Verify that os.chmod was called to add Write permission
            mock_chmod.assert_called_with(str(test_file), stat.S_IWRITE)

        # Verify that the original removal function was called
        mock_func.assert_called_once_with(str(test_file))


class TestCloneRepo:
    """Tests for the clone_repo function."""

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_success(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from):
        """Test successful clone_repo (happy path)."""
        # Scenario: Directory does not exist, clone succeeds
        mock_exists.return_value = False
        mock_clone_from.return_value = None

        result = clone_repo("testowner", "testrepo")

        assert result.success is True
        # Verify the path construction
        assert result.repo_path.endswith(f"testowner_testrepo")

        # Verify calls
        mock_makedirs.assert_called_once()
        mock_clone_from.assert_called_once()
        # rmtree shouldn't be called if exists is False
        mock_rmtree.assert_not_called()

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.shutil.rmtree")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_with_cleanup(self, mock_makedirs, mock_exists, mock_rmtree, mock_clone_from):
        """Test clone_repo handles existing directory cleanup."""
        # Scenario: Directory exists, must be removed before cloning
        mock_exists.return_value = True
        mock_clone_from.return_value = None

        result = clone_repo("testowner", "testrepo")

        assert result.success is True
        # Verify rmtree was called to clean up
        mock_rmtree.assert_called_once()
        mock_clone_from.assert_called_once()

    @patch("app.services.github.github_client.Repo.clone_from")
    @patch("app.services.github.github_client.os.path.exists")
    @patch("app.services.github.github_client.os.makedirs")
    def test_clone_repo_git_error(self, mock_makedirs, mock_exists, mock_clone_from):
        """Test clone_repo handling of GitCommandError."""
        mock_exists.return_value = False
        # Simulate Git error (e.g. auth failed)
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
        """Test clone_repo handling of OSError."""
        # Scenario: Directory exists, but rmtree fails with OSError
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
        """Test cleanup logic simulating Python 3.12+ (should use 'onexc')."""
        mock_exists.return_value = True
        # Simulate Python 3.12 environment
        mock_sys.version_info = (3, 12)

        clone_repo("owner", "repo")

        # Verify that 'onexc' argument is used (new standard)
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
        """Test cleanup logic simulating Python < 3.12 (should use 'onerror')."""
        mock_exists.return_value = True
        # Simulate Python 3.11 environment
        mock_sys.version_info = (3, 11)

        clone_repo("owner", "repo")

        # Verify that 'onerror' argument is used (legacy method)
        args, kwargs = mock_rmtree.call_args
        assert "onerror" in kwargs
        assert kwargs["onerror"] == _handle_remove_readonly
        assert "onexc" not in kwargs