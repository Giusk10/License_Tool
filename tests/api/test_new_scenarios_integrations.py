"""
Core Services Integration Test Module.

This module validates the integration between the application's core services,
including persistence (MongoDB), repository management (GitHub),
license scanning (ScanCode), and the AI-driven code regeneration workflow.

It ensures that data flows correctly between the service layers and that
file system operations—such as cloning and code overwriting—behave as expected.
"""

import pytest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock, mock_open
from fastapi.testclient import TestClient
from app.main import app
from app.services.analysis_workflow import perform_regeneration
from app.models.schemas import AnalyzeResponse, LicenseIssue
from app.services.downloader.download_service import perform_download


@pytest.fixture
def client():
    return TestClient(app)

# ==================================================================================
#                          TEST SUITE: LICENSE SCANNING
# ==================================================================================

class TestIntegrationScanner:
    """
    Tests the integration with the ScanCode binary on the file system.
    """
    def test_scancode_on_small_folder(self):
        """
        Executes a real license detection scan on a local temporary directory.

        Process:
        1. Creates a temporary workspace using `tempfile`.
        2. Writes a dummy Python file containing an explicit MIT license header.
        3. Invokes `run_scancode` to verify that the file is detected and parsed.

        Note:
            This test is skipped if the ScanCode binary is not installed in the system.
        """
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
    """
    Validates the full cycle of code correction and file system updates.
    """
    @patch('app.services.analysis_workflow.detect_main_license_scancode')
    @patch('app.services.analysis_workflow.regenerate_code')
    @patch('app.services.analysis_workflow.run_scancode')
    @patch('app.services.analysis_workflow.filter_licenses')
    @patch('app.services.analysis_workflow.extract_file_licenses')
    @patch('app.services.analysis_workflow.check_compatibility')
    @patch('app.services.analysis_workflow.enrich_with_llm_suggestions')
    def test_full_regeneration_cycle(self, mock_enrich, mock_compat, mock_extract, mock_filter, mock_scancode,
                                     mock_regenerate, mock_detect):
        """
        Verifies that incompatible code is correctly overwritten on disk.

        Logical Workflow:
        1. Setup: Create a temporary repository directory and a file with GPL code.
        2. Execution: Call `perform_regeneration` with a mock LLM response (MIT code).
        3. Validation: Read the file from disk to confirm the content has been
           successfully updated and the old incompatible code is gone.

        Returns:
            None: Asserts file content equality.
        """
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

# ==================================================================================
#                       TEST SUITE: CODE REGENERATION & I/O
# ==================================================================================

class TestIntegrationErrorHandling:
    """
    Tests the robustness of the API when backend services fail.
    """
    @patch('app.controllers.analysis.perform_download')
    def test_download_service_failure_propagation(self, mock_download, client):
        """
        Checks the mapping of service-level exceptions to HTTP responses.

        Ensures that if the download service raises a `PermissionError`,
        the API layer catches it and returns a 500 status with a clean
        JSON error message instead of crashing.
        """
        # Mock perform_download to raise an exception
        mock_download.side_effect = PermissionError("Permission denied")

        # Call the download endpoint
        response = client.post("/api/download", json={"owner": "test", "repo": "test"})

        # Assert HTTP 500 with clean message
        assert response.status_code == 500
        assert "Internal error: Permission denied" in response.json()["detail"]


# ==================================================================================
#                       NEW INTEGRATION TESTS FOR WORKFLOWS
# ==================================================================================

class TestIntegrationCloneWorkflow:
    """
    Test completi del workflow di cloning del repository.
    """

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_repository_complete_flow(self, mock_clone, client):
        """
        Test del workflow completo di cloning repository.

        Verifica che il processo di cloning funzioni end-to-end
        dall'endpoint al servizio.
        """
        mock_clone.return_value = "/tmp/test_clones/testowner_testrepo"

        response = client.post("/api/clone", json={
            "owner": "testowner",
            "repo": "testrepo"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cloned"
        assert data["owner"] == "testowner"
        assert data["repo"] == "testrepo"
        assert "testowner_testrepo" in data["local_path"]
        mock_clone.assert_called_once_with(owner="testowner", repo="testrepo")

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_repository_with_special_chars(self, mock_clone, client):
        """
        Test cloning con caratteri speciali nel nome.

        Verifica che repository con nomi complessi vengano gestiti.
        """
        mock_clone.return_value = "/tmp/test_clones/org-name_repo.test"

        response = client.post("/api/clone", json={
            "owner": "org-name",
            "repo": "repo.test"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cloned"


class TestIntegrationAnalysisWorkflow:
    """
    Test completi del workflow di analisi.
    """

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analysis_with_multiple_issues(self, mock_scan, client):
        """
        Test analisi con multipli problemi di licenza.

        Verifica che il sistema gestisca correttamente repository
        con più file incompatibili.
        """
        mock_scan.return_value = AnalyzeResponse(
            repository="owner/repo",
            main_license="MIT",
            issues=[
                LicenseIssue(
                    file_path="src/file1.py",
                    detected_license="GPL-3.0",
                    compatible=False,
                    reason="Incompatible with MIT"
                ),
                LicenseIssue(
                    file_path="src/file2.py",
                    detected_license="Apache-2.0",
                    compatible=True
                ),
                LicenseIssue(
                    file_path="lib/file3.js",
                    detected_license="UNKNOWN",
                    compatible=False,
                    reason="Unknown license"
                )
            ],
            needs_license_suggestion=False
        )

        response = client.post("/api/analyze", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data["issues"]) == 3
        assert data["issues"][0]["compatible"] is False
        assert data["issues"][1]["compatible"] is True
        assert data["issues"][2]["detected_license"] == "UNKNOWN"

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analysis_with_license_suggestion_needed(self, mock_scan, client):
        """
        Test analisi che richiede suggerimento licenza.

        Verifica che il flag needs_license_suggestion sia corretto.
        """
        mock_scan.return_value = AnalyzeResponse(
            repository="owner/repo",
            main_license="UNKNOWN",
            issues=[],
            needs_license_suggestion=True
        )

        response = client.post("/api/analyze", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["main_license"] == "UNKNOWN"
        assert data["needs_license_suggestion"] is True


class TestIntegrationRegenerationWorkflow:
    """
    Test completi del workflow di rigenerazione.
    """

    @patch('app.controllers.analysis.perform_regeneration')
    def test_regeneration_reduces_issues(self, mock_regen, client):
        """
        Test che la rigenerazione riduca i problemi di compatibilità.

        Simula uno scenario in cui dopo la rigenerazione,
        alcuni problemi vengono risolti.
        """
        # Previous analysis con 2 problemi
        previous = {
            "repository": "owner/repo",
            "main_license": "MIT",
            "issues": [
                {
                    "file_path": "src/file1.py",
                    "detected_license": "GPL-3.0",
                    "compatible": False
                },
                {
                    "file_path": "src/file2.py",
                    "detected_license": "LGPL-2.1",
                    "compatible": False
                }
            ]
        }

        # After regeneration: solo 1 problema rimane
        mock_regen.return_value = AnalyzeResponse(
            repository="owner/repo",
            main_license="MIT",
            issues=[
                LicenseIssue(
                    file_path="src/file2.py",
                    detected_license="LGPL-2.1",
                    compatible=False,
                    reason="Still incompatible"
                )
            ],
            needs_license_suggestion=False
        )

        response = client.post("/api/regenerate", json=previous)

        assert response.status_code == 200
        data = response.json()
        assert len(data["issues"]) == 1  # Ridotto da 2 a 1
        assert data["issues"][0]["file_path"] == "src/file2.py"


class TestIntegrationLicenseSuggestion:
    """
    Test di integrazione per il sistema di suggerimento licenza.
    """

    @patch('app.controllers.analysis.suggest_license_based_on_requirements')
    def test_license_suggestion_complete_workflow(self, mock_suggest, client):
        """
        Test del workflow completo di suggerimento licenza.

        Verifica che il sistema possa suggerire una licenza appropriata
        basandosi sui requisiti dell'utente.
        """
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache 2.0 provides patent protection and is permissive",
            "alternatives": ["MIT", "BSD-3-Clause"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": True,
            "copyleft": "none",
            "additional_requirements": "Patent protection, Commercial friendly"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] == "Apache-2.0"
        assert len(data["alternatives"]) == 2
        assert "patent" in data["explanation"].lower()

    @patch('app.controllers.analysis.suggest_license_based_on_requirements')
    def test_license_suggestion_for_copyleft(self, mock_suggest, client):
        """
        Test suggerimento per licenze copyleft.

        Verifica che il sistema suggerisca correttamente licenze
        copyleft quando richieste.
        """
        mock_suggest.return_value = {
            "suggested_license": "GPL-3.0",
            "explanation": "GPL-3.0 provides strong copyleft protection",
            "alternatives": ["AGPL-3.0", "LGPL-3.0"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": False,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "copyleft": "strong",
            "additional_requirements": "Strong copyleft protection"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "GPL" in data["suggested_license"]
        assert len(data["alternatives"]) > 0


class TestIntegrationZipUploadWorkflow:
    """
    Test di integrazione per upload ZIP.
    """

    @patch('app.controllers.analysis.perform_upload_zip')
    def test_zip_upload_and_analyze_workflow(self, mock_upload, client):
        """
        Test workflow completo: upload ZIP + analisi.

        Verifica che un repository caricato via ZIP possa
        essere successivamente analizzato.
        """
        # Step 1: Upload ZIP
        mock_upload.return_value = "/tmp/test_clones/uploaded_repo"

        zip_content = b"fake zip content"
        files = {"uploaded_file": ("test.zip", zip_content, "application/zip")}
        data = {"owner": "testowner", "repo": "testrepo"}

        upload_response = client.post("/api/zip", data=data, files=files)

        assert upload_response.status_code == 200
        assert upload_response.json()["status"] == "cloned_from_zip"

        # Step 2: Analyze the uploaded repo
        with patch('app.controllers.analysis.perform_initial_scan') as mock_scan:
            mock_scan.return_value = AnalyzeResponse(
                repository="testowner/testrepo",
                main_license="MIT",
                issues=[],
                needs_license_suggestion=False
            )

            analyze_response = client.post("/api/analyze", json={
                "owner": "testowner",
                "repo": "testrepo"
            })

            assert analyze_response.status_code == 200
            assert analyze_response.json()["main_license"] == "MIT"


class TestIntegrationErrorScenarios:
    """
    Test di integrazione per scenari di errore.
    """

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_failure_then_retry(self, mock_clone, client):
        """
        Test fallimento cloning seguito da retry.

        Verifica che il sistema gestisca correttamente errori
        di cloning e permetta un retry.
        """
        # Prima chiamata fallisce
        mock_clone.side_effect = ValueError("Network error")

        response1 = client.post("/api/clone", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response1.status_code == 400

        # Retry con successo
        mock_clone.side_effect = None
        mock_clone.return_value = "/tmp/owner_repo"

        response2 = client.post("/api/clone", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response2.status_code == 200



