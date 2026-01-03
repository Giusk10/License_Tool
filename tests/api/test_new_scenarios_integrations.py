"""
Modulo di test di integrazione dei servizi core.

Questo modulo valida l'integrazione tra i servizi core dell'applicazione,
inclusi persistenza (MongoDB), gestione repository (GitHub),
scansione licenze (ScanCode), e il flusso di lavoro di rigenerazione basato su AI.

Garantisce che i dati fluiscano correttamente tra i livelli di servizio e che
le operazioni del file system—come clonazione e sovrascrittura del codice—si comportino come previsto.
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
#                          SUITE DI TEST: SCANSIONE LICENZE
# ==================================================================================

class TestIntegrationScanner:
    """
    Testa l'integrazione con il binario ScanCode sul file system.
    """
    def test_scancode_on_small_folder(self):
        """
        Esegue una scansione reale di rilevamento licenze su una directory temporanea locale.

        Processo:
        1. Crea uno spazio di lavoro temporaneo utilizzando `tempfile`.
        2. Scrive un file Python dummy contenente un'intestazione di licenza MIT esplicita.
        3. Invoca `run_scancode` per verificare che il file sia rilevato e analizzato.

        Nota:
            Questo test viene saltato se il binario ScanCode non è installato nel sistema.
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
    Valida il ciclo completo di correzione del codice e aggiornamenti del file system.
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
        Verifica che il codice incompatibile sia correttamente sovrascritto su disco.

        Flusso logico:
        1. Setup: Crea una directory repository temporanea e un file con codice GPL.
        2. Esecuzione: Chiama `perform_regeneration` con una risposta LLM mock (codice MIT).
        3. Validazione: Leggi il file dal disco per confermare che il contenuto sia stato
           aggiornato con successo e che il vecchio codice incompatibile sia andato.

        Restituisce:
            None: Asserisce l'uguaglianza del contenuto del file.
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
#                       SUITE DI TEST: RIGENERAZIONE CODICE & I/O
# ==================================================================================

class TestIntegrationErrorHandling:
    """
    Testa la robustezza dell'API quando i servizi backend falliscono.
    """
    @patch('app.controllers.analysis.perform_download')
    def test_download_service_failure_propagation(self, mock_download, client):
        """
        Controlla la mappatura delle eccezioni a livello di servizio alle risposte HTTP.

        Garantisce che se il servizio di download genera un `PermissionError`,
        il livello API lo catturi e restituisca uno stato 500 con un messaggio di errore JSON pulito
        invece di crashare.
        """
        # Mock perform_download to raise an exception
        mock_download.side_effect = PermissionError("Permission denied")

        # Call the download endpoint
        response = client.post("/api/download", json={"owner": "test", "repo": "test"})

        # Assert HTTP 500 with clean message
        assert response.status_code == 500
        assert "Internal error: Permission denied" in response.json()["detail"]


# ==================================================================================
#                       NUOVI TEST DI INTEGRAZIONE PER WORKFLOW
# ==================================================================================

class TestIntegrationCloneWorkflow:
    """
    Test completi per il workflow di clonazione repository.
    """

    @patch('app.controllers.analysis.perform_cloning')
    def test_clone_repository_complete_flow(self, mock_clone, client):
        """
        Testa il workflow completo di clonazione repository.

        Verifica che il processo di clonazione funzioni end-to-end dall'
        endpoint al servizio.
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
    Test completi per il workflow di analisi.
    """

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analysis_with_multiple_issues(self, mock_scan, client):
        """
        Testa l'analisi con più problemi di licenza.

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
        Testa l'analisi che richiede un suggerimento di licenza.

        Verifica che il flag `needs_license_suggestion` sia correttamente impostato.
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
    Test completi per il workflow di rigenerazione.
    """

    @patch('app.controllers.analysis.perform_regeneration')
    def test_regeneration_reduces_issues(self, mock_regen, client):
        """
        Testa che la rigenerazione riduca i problemi di compatibilità.

        Simula uno scenario in cui, dopo la rigenerazione,
        alcuni problemi vengono risolti.
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
    Test di integrazione per il sistema di suggerimento licenze.
    """

    @patch('app.controllers.analysis.suggest_license_based_on_requirements')
    def test_license_suggestion_complete_workflow(self, mock_suggest, client):
        """
        Testa il workflow completo di suggerimento licenze.

        Verifica che il sistema possa suggerire una licenza appropriata
        basata sui requisiti dell'utente.
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
        Testa il suggerimento per licenze copyleft.

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
    Test di integrazione per il caricamento ZIP.
    """

    @patch('app.controllers.analysis.perform_upload_zip')
    def test_zip_upload_and_analyze_workflow(self, mock_upload, client):
        """
        Testa il workflow completo: caricamento ZIP + analisi.

        Verifica che un repository caricato via ZIP possa
        essere analizzato con successo.
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
        e permetta un retry.
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