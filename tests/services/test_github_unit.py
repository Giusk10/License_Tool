"""
test: services/github/github_client.py
"""
import os
from unittest.mock import patch, MagicMock
from git import GitCommandError
from app.services.github.github_client import clone_repo, _handle_remove_readonly


class TestHandleRemoveReadonly:
    """Test per la funzione handle_remove_readonly"""

    def test_handle_remove_readonly_removes_readonly_flag(self, tmp_path):
        """Verifica che la funzione rimuova il flag ReadOnly e chiami la funzione di rimozione."""
        # Crea un file di test
        test_file = tmp_path / "readonly_file.txt"
        test_file.write_text("test content")

        # Rendi il file readonly
        os.chmod(test_file, 0o444)

        # Mock della funzione di rimozione
        mock_func = MagicMock()

        # Chiama handle_remove_readonly
        _handle_remove_readonly(mock_func, str(test_file), None)

        # Verifica che la funzione sia stata chiamata con il path
        mock_func.assert_called_once_with(str(test_file))


class TestCloneRepo:
    """Test per la funzione clone_repo"""

    def test_clone_repo_success(self, tmp_path, monkeypatch):
        """Test clone repository con successo"""
        # Configura il base directory di test
        test_clone_dir = str(tmp_path / "clones")
        os.makedirs(test_clone_dir, exist_ok=True)
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        # Mock di Repo.clone_from
        mock_repo = MagicMock()
        with patch("app.services.github.github_client.Repo.clone_from", return_value=mock_repo) as mock_clone:
            result = clone_repo("test_owner", "test_repo", "fake_token")

            # Verifica il risultato
            assert result.success is True
            assert result.error is None
            assert result.repo_path == os.path.join(test_clone_dir, "test_owner_test_repo")

            # Verifica che clone_from sia stato chiamato con i parametri corretti
            expected_url = "https://x-access-token:fake_token@github.com/test_owner/test_repo.git"
            mock_clone.assert_called_once_with(
                expected_url,
                os.path.join(test_clone_dir, "test_owner_test_repo")
            )

    def test_clone_repo_removes_existing_directory(self, tmp_path, monkeypatch):
        """Test che la directory esistente venga rimossa prima del clone"""
        test_clone_dir = str(tmp_path / "clones")
        os.makedirs(test_clone_dir, exist_ok=True)
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        # Crea una directory esistente
        existing_dir = os.path.join(test_clone_dir, "test_owner_test_repo")
        os.makedirs(existing_dir, exist_ok=True)
        test_file = os.path.join(existing_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("existing content")

        # Mock di Repo.clone_from
        with patch("app.services.github.github_client.Repo.clone_from") as mock_clone:
            result = clone_repo("test_owner", "test_repo", "fake_token")

            # Verifica che la directory sia stata ricreata
            assert result.success is True
            mock_clone.assert_called_once()

    def test_clone_repo_handles_git_command_error(self, tmp_path, monkeypatch):
        """Test gestione errore GitCommandError"""
        test_clone_dir = str(tmp_path / "clones")
        os.makedirs(test_clone_dir, exist_ok=True)
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        # Mock di Repo.clone_from che solleva GitCommandError
        error_message = "Repository not found with token fake_token"
        with patch("app.services.github.github_client.Repo.clone_from",
                   side_effect=GitCommandError("clone", error_message)):
            result = clone_repo("test_owner", "test_repo", "fake_token")

            # Verifica il risultato
            assert result.success is False
            assert result.repo_path is None
            # Verifica che il token sia stato mascherato nell'errore
            assert "fake_token" not in result.error
            assert "***" in result.error

    def test_clone_repo_handles_os_error(self, tmp_path, monkeypatch):
        """Test OSError handling"""
        test_clone_dir = str(tmp_path / "clones")
        os.makedirs(test_clone_dir, exist_ok=True)
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        # Mock shutil.rmtree that raises OSError
        with patch("app.services.github.github_client.shutil.rmtree",
                   side_effect=OSError("Permission denied")):
            # Create an existing directory to trigger rmtree
            existing_dir = os.path.join(test_clone_dir, "test_owner_test_repo")
            os.makedirs(existing_dir, exist_ok=True)

            result = clone_repo("test_owner", "test_repo", "fake_token")

            # Verify the result
            assert result.success is False
            assert result.repo_path is None
            assert "Filesystem error" in result.error

    def test_clone_repo_creates_base_directory_if_not_exists(self, tmp_path, monkeypatch):
        """Test che la directory base venga creata se non esiste"""
        test_clone_dir = str(tmp_path / "new_clones")
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        # Verifica che la directory non esista
        assert not os.path.exists(test_clone_dir)

        # Mock di Repo.clone_from
        with patch("app.services.github.github_client.Repo.clone_from"):
            result = clone_repo("test_owner", "test_repo", "fake_token")

            # Verifica che la directory base sia stata creata
            assert os.path.exists(test_clone_dir)
            assert result.success is True

    def test_clone_repo_token_masking_in_error(self, tmp_path, monkeypatch):
        """Test che il token venga sempre mascherato negli errori"""
        test_clone_dir = str(tmp_path / "clones")
        os.makedirs(test_clone_dir, exist_ok=True)
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        secret_token = "ghp_1234567890abcdefghijklmnop"
        error_with_token = f"Authentication failed for 'https://x-access-token:{secret_token}@github.com/'"

        with patch("app.services.github.github_client.Repo.clone_from",
                   side_effect=GitCommandError("clone", error_with_token)):
            result = clone_repo("test_owner", "test_repo", secret_token)

            # Verifica che il token sia mascherato
            assert result.success is False
            assert secret_token not in result.error
            assert "***" in result.error

    def test_clone_repo_correct_url_format(self, tmp_path, monkeypatch):
        """Test che l'URL del repository sia formattato correttamente"""
        test_clone_dir = str(tmp_path / "clones")
        os.makedirs(test_clone_dir, exist_ok=True)
        monkeypatch.setattr("app.services.github.github_client.CLONE_BASE_DIR", test_clone_dir)

        owner = "octocat"
        repo = "Hello-World"
        token = "test_token_123"

        with patch("app.services.github.github_client.Repo.clone_from") as mock_clone:
            clone_repo(owner, repo, token)

            # Verifica il formato dell'URL OAuth
            expected_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
            actual_call = mock_clone.call_args[0][0]
            assert actual_call == expected_url
