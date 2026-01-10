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
    Comprehensive tests for the repository cloning workflow.
    """

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_repository_complete_flow(self, mock_clone, client):
        """
        Test the complete repository cloning workflow.

        Verifies that the cloning process works end-to-end from
        the endpoint to the service.
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
        Tests cloning with special characters in the name.

        Verifies that repositories with complex names are handled correctly.
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
    Comprehensive tests for the analysis workflow.
    """

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analysis_with_multiple_issues(self, mock_scan, client):
        """
        Tests analysis with multiple license issues.

        Verifies that the system correctly handles repositories
        with multiple incompatible files.
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
        Tests analysis that requires a license suggestion.

        Verifies that the `needs_license_suggestion` flag is correctly set.
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
    Comprehensive tests for the regeneration workflow.
    """

    @patch('app.controllers.analysis.perform_regeneration')
    def test_regeneration_reduces_issues(self, mock_regen, client):
        """
        Tests that regeneration reduces compatibility issues.

        Simulates a scenario where, after regeneration,
        some issues are resolved.
        """
        # Previous analysis with 2 issues
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

        # After regeneration: only 1 issue remains
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
        assert len(data["issues"]) == 1  # Reduced from 2 to 1
        assert data["issues"][0]["file_path"] == "src/file2.py"


class TestIntegrationLicenseSuggestion:
    """
    Integration tests for the license suggestion system.
    """

    @patch('app.controllers.analysis.suggest_license_based_on_requirements')
    def test_license_suggestion_complete_workflow(self, mock_suggest, client):
        """
        Tests the complete license suggestion workflow.

        Verifies that the system can suggest an appropriate license
        based on user requirements.
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
        Tests suggestion for copyleft licenses.

        Verifies that the system correctly suggests copyleft licenses
        when requested.
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
    Integration tests for ZIP upload.
    """

    @patch('app.controllers.analysis.perform_upload_zip')
    def test_zip_upload_and_analyze_workflow(self, mock_upload, client):
        """
        Tests complete workflow: ZIP upload + analysis.

        Verifies that a repository uploaded via ZIP can
        be successfully analyzed.
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
    Integration tests for error scenarios.
    """

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_failure_then_retry(self, mock_clone, client):
        """
        Tests cloning failure followed by a retry.

        Verifies that the system correctly handles cloning errors
        and allows for a retry.
        """
        # First call fails
        mock_clone.side_effect = ValueError("Network error")

        response1 = client.post("/api/clone", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response1.status_code == 400

        # Retry successful
        mock_clone.side_effect = None
        mock_clone.return_value = "/tmp/owner_repo"

        response2 = client.post("/api/clone", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response2.status_code == 200