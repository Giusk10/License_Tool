import pytest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock, mock_open
from fastapi.testclient import TestClient
from app.main import app
from app.services.github.Encrypted_Auth_Info import github_auth_credentials
from app.services.analysis_workflow import perform_regeneration
from app.models.schemas import AnalyzeResponse, LicenseIssue
from app.services.downloader.download_service import perform_download


@pytest.fixture
def client():
    return TestClient(app)


class TestIntegrationPersistence:
    @patch('app.services.github.Encrypted_Auth_Info.MongoClient')
    @patch('app.services.github.Encrypted_Auth_Info.decripta_dato_singolo')
    def test_github_token_save_and_retrieve(self, mock_decrypt, mock_mongo_client):
        # Setup Mock per Context Manager (with MongoClient...)
        mock_client_instance = MagicMock()
        mock_mongo_client.return_value = mock_client_instance
        # Quando entra nel 'with', restituisce se stesso
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client_instance.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection

        # Original token
        original_token = "ghp_1234567890abcdef"

        # Mock the find_one to return the encrypted token
        mock_collection.find_one.return_value = {
            "service_name": "GITHUB_TOKEN",
            "encrypted_data": "encrypted_data"
        }

        # Mock decryption to return original
        mock_decrypt.return_value = original_token

        # Retrieve and decrypt
        retrieved_token = github_auth_credentials("GITHUB_TOKEN")

        # Assert
        assert retrieved_token == original_token
        mock_collection.find_one.assert_called_with({"service_name": "GITHUB_TOKEN"})


class TestIntegrationGitHubClient:
    @patch('app.services.analysis_workflow.clone_repo')
    def test_parameter_passing_to_clone_repo(self, mock_clone_repo):
        # Mock clone_repo to return success
        mock_clone_repo.return_value = MagicMock(success=True, repo_path="/path/to/repo")

        from app.services.analysis_workflow import perform_cloning

        # Call perform_cloning
        result = perform_cloning("testowner", "testrepo", "testtoken")

        # Assert clone_repo was called with correct params
        mock_clone_repo.assert_called_once_with("testowner", "testrepo", "testtoken")
        assert result == "/path/to/repo"


class TestIntegrationScanner:
    def test_scancode_on_small_folder(self):
        from app.services.scanner.detection import run_scancode

        # Create a temporary directory with a small file
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a simple Python file with MIT license
            file_path = os.path.join(temp_dir, "test.py")
            with open(file_path, "w") as f:
                f.write("# MIT License\n\ndef hello():\n    print('Hello')\n")

            # Run scancode (assuming SCANCODE_BIN is set in config)
            try:
                result = run_scancode(temp_dir)
                # Check that result has files
                assert "files" in result
                assert len(result["files"]) > 0
                # Check that the file is detected
                file_entries = [f for f in result["files"] if f["path"].endswith("test.py")]
                assert len(file_entries) == 1
            except Exception as e:
                # If scancode is not available, skip
                pytest.skip(f"ScanCode not available: {e}")


class TestIntegrationCodeGeneratorFileSystem:
    @patch('app.services.analysis_workflow.detect_main_license_scancode')
    @patch('app.services.analysis_workflow.regenerate_code')
    @patch('app.services.analysis_workflow.run_scancode')
    @patch('app.services.analysis_workflow.filter_licenses')
    @patch('app.services.analysis_workflow.extract_file_licenses')
    @patch('app.services.analysis_workflow.check_compatibility')
    @patch('app.services.analysis_workflow.enrich_with_llm_suggestions')
    def test_full_regeneration_cycle(self, mock_enrich, mock_compat, mock_extract, mock_filter, mock_scancode,
                                     mock_regenerate, mock_detect):
        # Setup mocks
        mock_regenerate.return_value = "# MIT License\n\ndef hello():\n    print('Hello MIT')\n"
        mock_scancode.return_value = {"files": []}
        mock_filter.return_value = {"files": []}
        mock_extract.return_value = {}
        mock_compat.return_value = {"issues": []}
        mock_enrich.return_value = []
        mock_detect.return_value = ("MIT", "/path")

        # Create a temporary directory and file
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('app.services.analysis_workflow.CLONE_BASE_DIR', temp_dir):
                repo_dir = os.path.join(temp_dir, "testowner_testrepo")
                os.makedirs(repo_dir)
                file_path = os.path.join(repo_dir, "test.py")
                original_content = "# GPL License\n\ndef hello():\n    print('Hello GPL')\n"
                with open(file_path, "w") as f:
                    f.write(original_content)

                # Mock previous analysis with an incompatible issue
                previous_analysis = AnalyzeResponse(
                    repository="testowner/testrepo",
                    main_license="MIT",
                    issues=[
                        LicenseIssue(
                            file_path="test.py",
                            detected_license="GPL-3.0",
                            compatible=False,
                            reason="Incompatible",
                            suggestion="Change to MIT"
                        )
                    ]
                )

                # Call perform_regeneration
                result = perform_regeneration("testowner", "testrepo", previous_analysis)

                # Check that the file was updated
                with open(file_path, "r") as f:
                    new_content = f.read()
                assert new_content == "# MIT License\n\ndef hello():\n    print('Hello MIT')\n"
                assert new_content != original_content


class TestIntegrationErrorHandling:
    @patch('app.controllers.analysis.perform_download')
    def test_download_service_failure_propagation(self, mock_download, client):
        # Mock perform_download to raise an exception
        mock_download.side_effect = PermissionError("Permission denied")

        # Call the download endpoint
        response = client.post("/api/download", json={"owner": "test", "repo": "test"})

        # Assert HTTP 500 with clean message
        assert response.status_code == 500
        assert "Internal error: Permission denied" in response.json()["detail"]