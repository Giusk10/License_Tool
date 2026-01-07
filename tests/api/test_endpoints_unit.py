"""
Modulo di test di integrazione dei controller di analisi.

Questo modulo orchestra test di integrazione per gli endpoint del controller di analisi
definiti in `app.controllers.analysis`. Verifica il flusso di lavoro end-to-end,
garantendo che gli endpoint API rispondano correttamente e comunichino efficacemente
con i servizi backend mockati.

La suite copre:
1. Autenticazione OAuth GitHub (Redirect e Callback).
2. Gestione archivi ZIP (Caricamento e validazione).
3. Ciclo di vita dell'analisi (Scansione licenze e validazione schema).
4. Post-elaborazione (Rigenerazione codice e download artefatti).
"""

import pytest
import httpx
from fastapi import HTTPException
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from urllib.parse import urlparse, parse_qs
from app.main import app

client = TestClient(app)


# ==================================================================================
#                                     FIXTURE
# ==================================================================================

@pytest.fixture
def mock_creds():
    """
     Simula il recupero delle credenziali OAuth GitHub (CLIENT_ID, SECRET).
     Restituisce:
         MagicMock: Un oggetto mock che restituisce 'MOCK_CLIENT_ID'.
     """
    with patch("app.controllers.analysis.github_auth_credentials") as m:
        m.return_value = "MOCK_CLIENT_ID"
        yield m


@pytest.fixture
def mock_httpx_client():
    """
     Mocka le chiamate HTTP asincrone esterne.
     Utilizzato principalmente per intercettare la richiesta di scambio token GitHub
     senza eseguire I/O di rete effettivo.
     """
    with patch("app.controllers.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_cloning():
    """Mocka il servizio di clonazione repository (git clone)."""
    with patch("app.controllers.analysis.perform_cloning") as m:
        yield m


@pytest.fixture
def mock_scan():
    """Mocka il servizio di scansione iniziale (ScanCode + Analisi LLM)."""
    with patch("app.controllers.analysis.perform_initial_scan") as m:
        yield m


@pytest.fixture
def mock_regen():
    """Mocka il processo di rigenerazione e correzione codice via LLM."""
    with patch("app.controllers.analysis.perform_regeneration") as m:
        yield m


@pytest.fixture
def mock_zip_upload():
    """Mocka il servizio responsabile del caricamento e dell'estrazione dei file ZIP."""
    with patch("app.controllers.analysis.perform_upload_zip") as m:
        yield m


@pytest.fixture
def mock_download():
    """Mocka la preparazione finale del pacchetto ZIP per il download."""
    with patch("app.controllers.analysis.perform_download") as m:
        yield m


# Alias per compatibilità all'indietro con i test esistenti
@pytest.fixture
def mock_env_credentials(mock_creds):
    """Alias per mock_creds."""
    return mock_creds


@pytest.fixture
def mock_httpx_post(mock_httpx_client):
    """Alias per mock_httpx_client."""
    return mock_httpx_client


@pytest.fixture
def mock_clone(mock_cloning):
    """Alias per mock_cloning."""
    return mock_cloning


@pytest.fixture
def mock_upload_zip(mock_zip_upload):
    """Alias per mock_zip_upload."""
    return mock_zip_upload

# ==================================================================================
#                                   TEST: ZIP
# ==================================================================================

def test_upload_zip_success(mock_zip_upload):
    """
    Verifica il caricamento e l'elaborazione riuscita di un file ZIP.

    Garantisce che il controller riceva correttamente i dati binari e restituisca
    lo stato 'cloned_from_zip'.
    """
    mock_zip_upload.return_value = "/tmp/extracted_zip"

    files = {"uploaded_file": ("test.zip", b"fake-content", "application/zip")}
    data = {"owner": "user", "repo": "repo"}

    response = client.post("/api/zip", data=data, files=files)

    assert response.status_code == 200
    assert response.json()["status"] == "cloned_from_zip"
    mock_zip_upload.assert_called_once()


def test_upload_zip_bad_file(mock_zip_upload):
    """
    Testa la gestione degli errori per caricamenti di file ZIP non validi o corrotti.

    Verifica che se il servizio ZIP sottostante genera un ValueError (ad es.,
    a causa di un archivio corrotto o tipo di file errato), il controller
    restituisca correttamente uno stato 400 Bad Request con i dettagli dell'errore.
    """
    mock_zip_upload.side_effect = ValueError("Not a valid zip")

    files = {"uploaded_file": ("test.txt", b"text", "text/plain")}
    response = client.post("/api/zip", data={"owner": "u", "repo": "r"}, files=files)

    assert response.status_code == 400
    assert "Not a valid zip" in response.json()["detail"]


# ==================================================================================
#                                TEST: ANALISI
# ==================================================================================

def test_analyze_success_correct_schema(mock_scan):
    """
    Valida l'endpoint /analyze rispetto allo schema AnalyzeResponse.

    Garantisce che:
    - La risposta JSON contenga 'main_license' e 'issues'.
    - I campi non definiti (ad es., 'compatibility_score') siano esclusi dalla risposta.
    """
    # Mock allineato con AnalyzeResponse in schemas.py
    mock_scan.return_value = {
        "repository": "user/repo",
        "main_license": "MIT",
        "issues": [
            {
                "file_path": "src/bad.py",
                "detected_license": "GPL",
                "compatible": False,
                "reason": "Conflict"
            }
        ],
        "report_path": "/tmp/report.json"
    }

    response = client.post("/api/analyze", json={"owner": "user", "repo": "repo"})

    assert response.status_code == 200
    data = response.json()

    assert data["repository"] == "user/repo"
    assert data["main_license"] == "MIT"
    assert len(data["issues"]) == 1
    assert data["issues"][0]["detected_license"] == "GPL"

    # Verifica che i campi non esistenti nello schema non siano presenti
    assert "compatibility_score" not in data


def test_analyze_internal_error(mock_scan):
    """
    Verifica la resilienza dell'API contro fallimenti imprevisti del servizio backend.

    Garantisce che se il servizio di scansione incontra un errore critico
    (ad es., fallimento connessione database o eccezione non gestita), il
    controller catturi il crash e restituisca uno stato 500 Internal Server Error
    invece di esporre dati di eccezione grezzi.
    """
    mock_scan.side_effect = Exception("Database error")

    response = client.post("/api/analyze", json={"owner": "u", "repo": "r"})

    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


# ==================================================================================
#                                TEST: RIGENERA
# ==================================================================================

def test_regenerate_success(mock_regen):
    """
    Verifica la logica di rigenerazione del codice.

    Controlla che il controller divida correttamente la stringa 'repository'
    in 'owner' e 'repo' prima di chiamare il servizio.
    """
    # Simula il payload di input (che è un AnalyzeResponse precedente)
    payload = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": [],
        "report_path": "path"
    }

    # Il servizio restituisce un oggetto aggiornato
    mock_regen.return_value = payload

    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 200

    # Verifica il passaggio corretto dei parametri (split owner/repo)
    mock_regen.assert_called_once()
    kwargs = mock_regen.call_args[1]
    assert kwargs["owner"] == "facebook"
    assert kwargs["repo"] == "react"


def test_regenerate_bad_repo_string(mock_regen):
    """
    Valida la gestione di identificatori di repository malformati durante la rigenerazione.

    L'endpoint di rigenerazione richiede che il campo 'repository' segua il
    formato 'owner/repo' con slash. Questo test garantisce che se viene fornita una stringa senza
    slash, l'API identifichi correttamente l'errore di formato
    e restituisca uno stato 400 Bad Request.
    """
    payload = {
        "repository": "invalid-string",
        "main_license": "MIT",
        "issues": [],
        "report_path": "path"
    }

    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 400


# ==================================================================================
#                                TEST: DOWNLOAD
# ==================================================================================

def test_download_success(mock_download, tmp_path):
    """
    Verifica l'archiviazione e la consegna di progetti analizzati.

    Utilizza 'tmp_path' di pytest per creare un file fisico, garantendo che FastAPI's
    FileResponse possa servire il contenuto senza errori.
    """
    # 1. Crea un file fisico temporaneo
    fake_zip = tmp_path / "archive.zip"
    fake_zip.write_bytes(b"DATA")

    # 2. Il mock restituisce il percorso di questo file
    mock_download.return_value = str(fake_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content == b"DATA"


def test_download_missing_repo(mock_download):
    """
    Valida la gestione degli errori per richieste di download di repository non esistenti.

    Garantisce che se il servizio di download non riesce a trovare il repository richiesto
    su disco (generando un ValueError), l'API risponda con uno stato 400 Bad Request
    e fornisca un messaggio di errore chiaro nel dettaglio della risposta.
    """
    mock_download.side_effect = ValueError("Repo not cloned")

    response = client.post("/api/download", json={"owner": "ghost", "repo": "b"})

    assert response.status_code == 400
    assert "Repo not cloned" in response.json()["detail"]


def test_download_missing_params(mock_download):
    """
    Verifies input validation for the /download endpoint.
    If 'owner' or 'repo' are missing, it should return 400.
    """
    response = client.post("/api/download", json={"owner": "only_owner"})
    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


# ==================================================================================
#                       TEST UNITARI AGGIUNTIVI (NUOVAMENTE RICHIESTI)
# ==================================================================================

def test_analyze_with_schema_validation(mock_scan):
    """
     Valida la risposta dell'endpoint di analisi rispetto allo schema AnalyzeResponse.

     Il test garantisce che la risposta contenga i campi richiesti 'repository',
     'main_license' e la lista 'issues', seguendo rigorosamente lo schema Pydantic definito.

     Argomenti:
         mock_scan: Mock per il servizio di scansione iniziale.
     """
    # Mock conforme al tuo schema (SENZA 'analysis', CON 'main_license')
    mock_res = {
        "repository": "test/repo",
        "main_license": "MIT",
        "issues": []
    }
    mock_scan.return_value = mock_res

    response = client.post("/api/analyze", json={"owner": "test", "repo": "repo"})

    assert response.status_code == 200
    data = response.json()

    assert data["repository"] == "test/repo"
    assert data["main_license"] == "MIT"
    assert isinstance(data["issues"], list)

    mock_scan.assert_called_with(owner="test", repo="repo")


def test_analyze_missing_required_params():
    """
    Verifica che i parametri obbligatori mancanti attivino un errore di validazione.

    Se 'owner' o 'repo' mancano dal corpo della richiesta,
    l'API deve restituire un errore 400.
    """
    response = client.post("/api/analyze", json={"owner": "solo_owner"})
    assert response.status_code == 400


def test_regenerate_with_payload_validation(mock_regen):
    """
       Verifica il flusso di rigenerazione con un payload di analisi valido.

       Questo test garantisce che il controller possa elaborare un AnalyzeResponse
       generato in precedenza e passare i dettagli al servizio di rigenerazione LLM.

       Argomenti:
           mock_regen: Mock per il servizio di rigenerazione codice.
       """

    # Payload INPUT (Deve avere main_license, issues)
    payload = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": []
    }

    # Mock OUTPUT
    mock_res = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": []
    }
    mock_regen.return_value = mock_res

    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["repository"] == "facebook/react"
    assert data["main_license"] == "MIT"

    mock_regen.assert_called_once()
    assert mock_regen.call_args[1]['owner'] == "facebook"


def test_regenerate_invalid_format():
    """
    Gestisce i casi in cui la stringa repository manca dello slash richiesto.

    Garantisce che venga restituito un errore 400 quando l'identificatore repository
    è formattato in modo improprio, anche se la struttura JSON è valida.
    """
    payload = {
        "repository": "noslash",
        "main_license": "N/A",
        "issues": []
    }

    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 400
    assert "Invalid repository format" in response.json()["detail"]


def test_download_zip_success(mock_download, tmp_path):
    """
    Testa il recupero riuscito del pacchetto ZIP analizzato.

    Valida le intestazioni di risposta e garantisce che il contenuto binario
    sia trasmesso correttamente al client.
    """
    dummy_zip = tmp_path / "fake.zip"
    dummy_zip.write_bytes(b"DATA")

    mock_download.return_value = str(dummy_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_error_handling(mock_download):
    """
    Verifica la gestione degli errori quando un pacchetto repository richiesto è mancante.

    Garantisce che venga restituito un errore 400 se il servizio di download
    non riesce a trovare il repository specificato su disco.
    """
    mock_download.side_effect = ValueError("Not found")
    response = client.post("/api/download", json={"owner": "u", "repo": "r"})
    assert response.status_code == 400


def test_upload_zip_with_file_validation(mock_upload_zip, tmp_path):
    """
     Verifica l'endpoint di caricamento ZIP con un file fisico temporaneo.

     Testa l'integrazione tra il caricamento multipart del file e
     il servizio backend che estrae l'archivio.
     """
    fake_zip = tmp_path / "test.zip"
    fake_zip.write_bytes(b"content")

    mock_upload_zip.return_value = "/tmp/uploaded/path"

    with open(fake_zip, "rb") as f:
        response = client.post(
            "/api/zip",
            data={"owner": "u", "repo": "r"},
            files={"uploaded_file": ("test.zip", f, "application/zip")}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "cloned_from_zip"


# ==================================================================================
#                            TEST SUGGERIMENTO LICENZA
# ==================================================================================

def test_suggest_license_success():
    """
    Test dell'endpoint suggest_license con successo.

    Verifica che l'endpoint /api/suggest-license restituisca
    un suggerimento di licenza valido basato sui requisiti forniti.
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "patent_grant": True,
        "trademark_use": False,
        "liability": False,
        "copyleft": "none",
        "additional_requirements": "Need patent protection"
    }

    mock_suggestion = {
        "suggested_license": "Apache-2.0",
        "explanation": "Apache 2.0 is a permissive license with patent protection",
        "alternatives": ["MIT", "BSD-3-Clause"]
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements", return_value=mock_suggestion):
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_license"] == "Apache-2.0"
    assert "explanation" in data
    assert "alternatives" in data
    assert len(data["alternatives"]) == 2


def test_suggest_license_minimal_requirements():
    """
    Test suggest_license con requisiti minimi.

    Verifica che l'endpoint funzioni anche con requisiti minimi (solo campi richiesti).
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo"
    }

    mock_suggestion = {
        "suggested_license": "MIT",
        "explanation": "MIT is a simple permissive license",
        "alternatives": []
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements", return_value=mock_suggestion):
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_license"] == "MIT"


def test_suggest_license_with_constraints():
    """
    Test suggest_license con vincoli specifici.

    Verifica che i vincoli personalizzati siano elaborati correttamente
    dal sistema di suggerimento.
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "patent_grant": True,
        "copyleft": "strong",
        "additional_requirements": "Strong copyleft with network use = distribution"
    }

    mock_suggestion = {
        "suggested_license": "AGPL-3.0",
        "explanation": "AGPL-3.0 provides strong copyleft including network use",
        "alternatives": ["GPL-3.0"]
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements", return_value=mock_suggestion):
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_license"] == "AGPL-3.0"
    assert "GPL-3.0" in data["alternatives"]


def test_suggest_license_error_handling():
    """
    Test suggest_license con un errore del servizio AI.

    Verifica che gli errori del servizio di suggerimento
    siano gestiti correttamente e restituiscano un errore 500.
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo",
        "commercial_use": True,
        "patent_grant": False
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements",
               side_effect=Exception("AI service unavailable")):
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 500
    assert "Failed to generate license suggestion" in response.json()["detail"]


def test_suggest_license_invalid_payload():
    """
    Test suggest_license con payload non valido.

    Verifica che l'endpoint rifiuti payload malformati
    con validazione Pydantic.
    """
    payload = {
        "owner": "testowner"
        # Mancante repo obbligatorio
    }

    response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 422  # Unprocessable Entity (validazione Pydantic)


def test_suggest_license_with_detected_licenses():
    """
    Test suggest_license con detected_licenses fornite.

    Verifica che l'endpoint elabori correttamente le licenze rilevate
    e le passi al suggeritore.
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "copyleft": "none",
        "detected_licenses": ["MIT", "Apache-2.0"]
    }

    mock_suggestion = {
        "suggested_license": "Apache-2.0",
        "explanation": "Apache-2.0 is compatible with detected MIT and Apache-2.0 licenses",
        "alternatives": ["MIT"]
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements", return_value=mock_suggestion) as mock_suggest:
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_license"] == "Apache-2.0"
    assert "compatible" in data["explanation"].lower()

    # Verifica che detected_licenses sia stato passato alla funzione
    mock_suggest.assert_called_once()
    call_args, call_kwargs = mock_suggest.call_args
    assert "detected_licenses" in call_kwargs
    assert call_kwargs["detected_licenses"] == ["MIT", "Apache-2.0"]


def test_suggest_license_with_empty_detected_licenses():
    """
    Test suggest_license con detected_licenses vuoto.

    Verifica che una lista detected_licenses vuota sia gestita correttamente.
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo",
        "commercial_use": True,
        "detected_licenses": []
    }

    mock_suggestion = {
        "suggested_license": "MIT",
        "explanation": "MIT is a simple permissive license",
        "alternatives": ["BSD-3-Clause"]
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements", return_value=mock_suggestion) as mock_suggest:
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_license"] == "MIT"

    # Verifica che la lista vuota sia stata passata
    call_kwargs = mock_suggest.call_args[1]
    assert call_kwargs["detected_licenses"] == []


def test_suggest_license_without_detected_licenses():
    """
    Test suggest_license senza detected_licenses (campo omesso).

    Verifica che l'endpoint funzioni correttamente quando detected_licenses
    non è fornito nel payload.
    """
    payload = {
        "owner": "testowner",
        "repo": "testrepo",
        "commercial_use": True,
        "copyleft": "weak"
    }

    mock_suggestion = {
        "suggested_license": "LGPL-3.0",
        "explanation": "LGPL-3.0 provides weak copyleft protection",
        "alternatives": ["MPL-2.0"]
    }

    with patch("app.controllers.analysis.suggest_license_based_on_requirements", return_value=mock_suggestion) as mock_suggest:
        response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_license"] == "LGPL-3.0"

    # Verifica che None sia stato passato quando il campo è omesso
    call_kwargs = mock_suggest.call_args[1]
    assert call_kwargs["detected_licenses"] is None


def test_clone_success(mock_cloning):
    """
    Verifies the repository cloning endpoint success path.
    """
    mock_cloning.return_value = "/tmp/cloned/repo"

    response = client.post("/api/clone", json={"owner": "test", "repo": "repo"})

    assert response.status_code == 200
    assert response.json()["status"] == "cloned"
    assert response.json()["local_path"] == "/tmp/cloned/repo"


def test_clone_missing_params():
    """
    Verifies validation for missing parameters in clone endpoint.
    """
    response = client.post("/api/clone", json={"owner": "test"})  # Missing repo
    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_value_error(mock_cloning):
    """
    Verifies handling of ValueError during cloning (e.g., repo not found).
    """
    mock_cloning.side_effect = ValueError("Git error")
    response = client.post("/api/clone", json={"owner": "t", "repo": "r"})
    assert response.status_code == 400
    assert "Git error" in response.json()["detail"]


def test_clone_internal_error(mock_cloning):
    """
    Verifies 500 handling for unexpected errors during cloning.
    """
    mock_cloning.side_effect = Exception("System failure")
    response = client.post("/api/clone", json={"owner": "t", "repo": "r"})
    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


def test_download_internal_error(mock_download):
    """
    Verifies that generic exceptions in download_repo are caught and returned as 500.
    """
    mock_download.side_effect = Exception("Disk failure")
    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


def test_upload_zip_http_exception_reraise(mock_upload_zip):
    """
    Verifies that HTTPExceptions raised by the service are re-raised transparently.
    This covers the 'except HTTPException: raise' block in upload_zip.
    """
    # Simulate a specific HTTP error from the service layer
    mock_upload_zip.side_effect = HTTPException(status_code=418, detail="I'm a teapot")

    files = {"uploaded_file": ("test.zip", b"content", "application/zip")}
    response = client.post("/api/zip", data={"owner": "u", "repo": "r"}, files=files)

    assert response.status_code == 418
    assert "I'm a teapot" in response.json()["detail"]


def test_upload_zip_internal_error(mock_upload_zip):
    """
    Verifies 500 handling for unexpected errors during zip upload.
    """
    mock_upload_zip.side_effect = Exception("Extraction failed")

    files = {"uploaded_file": ("test.zip", b"content", "application/zip")}
    response = client.post("/api/zip", data={"owner": "u", "repo": "r"}, files=files)

    assert response.status_code == 500
    assert "Internal Error" in response.json()["detail"]


# ==================================================================================
#                                ROOT ENDPOINT TEST
# ==================================================================================

def test_root_endpoint():
    """
    Test the root endpoint ("/") to ensure the API is running.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "License Checker Backend is running"}