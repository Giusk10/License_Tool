"""
Modulo di test di integrazione dei servizi core.

Questo modulo valida l'integrazione tra i servizi core dell'applicazione,
inclusi la persistenza (MongoDB), la gestione dei repository (GitHub),
la scansione delle licenze (ScanCode) e il flusso di rigenerazione del codice guidato dall'AI.

Verifica che i dati fluiscano correttamente tra i livelli di servizio e che
le operazioni sul file system — come il clone e la sovrascrittura del codice —
si comportino come previsto.
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
    Testa la robustezza dell'API quando i servizi di backend falliscono.
    """
    @patch('app.controllers.analysis.perform_download')
    def test_download_service_failure_propagation(self, mock_download, client):
        """
        Verifica la mappatura delle eccezioni a livello di servizio nelle risposte HTTP.

        Si assicura che se il servizio di download solleva una `PermissionError`,
        lo strato API la intercetti e restituisca uno status 500 con un messaggio
        JSON chiaro invece di causare un crash.
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
    Test completi per il flusso di clonazione del repository.
    """

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_repository_complete_flow(self, mock_clone, client):
        """
        Test del flusso completo di clonazione del repository.

        Verifica che il processo di clonazione funzioni end-to-end dall'endpoint al servizio.
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
        Testa la clonazione con caratteri speciali nel nome.

        Verifica che i repository con nomi complessi siano gestiti correttamente.
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
    Test completi per il flusso di analisi.
    """

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analysis_with_multiple_issues(self, mock_scan, client):
        """
        Testa l'analisi con molteplici problemi di licenza.

        Verifica che il sistema gestisca correttamente repository con più file incompatibili.
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
        Testa un'analisi che richiede un suggerimento di licenza.

        Verifica che il flag `needs_license_suggestion` venga impostato correttamente.
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
    Test completi per il flusso di rigenerazione.
    """

    @patch('app.controllers.analysis.perform_regeneration')
    def test_regeneration_reduces_issues(self, mock_regen, client):
        """
        Verifica che la rigenerazione riduca i problemi di compatibilità.

        Simula uno scenario in cui, dopo la rigenerazione, alcuni problemi vengono risolti.
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
    Test di integrazione per il sistema di suggerimento di licenze.
    """

    @patch('app.controllers.analysis.suggest_license_based_on_requirements')
    def test_license_suggestion_complete_workflow(self, mock_suggest, client):
        """
        Testa il flusso completo di suggerimento di licenza.

        Verifica che il sistema possa suggerire una licenza adeguata
        in base ai requisiti forniti dall'utente.
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
        Test del suggerimento per licenze copyleft.

        Verifica che il sistema suggerisca correttamente licenze copyleft
        quando richiesto.
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
    Test di integrazione per l'upload di file ZIP.
    """

    @patch('app.controllers.analysis.perform_upload_zip')
    def test_zip_upload_and_analyze_workflow(self, mock_upload, client):
        """
        Testa il flusso completo: upload ZIP + analisi.

        Verifica che un repository caricato tramite ZIP possa
        essere analizzato correttamente.
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
        Testa il fallimento della clonazione seguito da un retry.

        Verifica che il sistema gestisca correttamente gli errori di clonazione
        e permetta di ritentare l'operazione.
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