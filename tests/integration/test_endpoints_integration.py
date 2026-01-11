"""
Modulo di test di integrazione per i controller di analisi.

Questo modulo orchestra i test di integrazione sugli endpoint dei controller di analisi
definiti in `app.controllers.analysis`. Verifica il workflow end-to-end,
assicurando che gli endpoint API rispondano correttamente e comunichino in modo efficace
con i servizi di backend mockati.

La suite copre:
1. Autenticazione OAuth GitHub (Redirect e Callback).
2. Gestione archivi ZIP (upload e validazione).
3. Ciclo di analisi (scansione licenze e validazione schema).
4. Post-processing (rigenerazione codice e download artefatti).
5. Endpoint di clonazione (validazione ed esecuzione).
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
#                                     FIXTURES
# ==================================================================================

@pytest.fixture
def mock_creds():
    """
    Simula il recupero delle credenziali OAuth di GitHub (CLIENT_ID, SECRET).
    Restituisce:
        MagicMock: un oggetto mock che restituisce 'MOCK_CLIENT_ID'.
    """
    with patch("app.controllers.analysis.github_auth_credentials") as m:
        m.return_value = "MOCK_CLIENT_ID"
        yield m


@pytest.fixture
def mock_httpx_client():
    """
     Mock delle chiamate HTTP asincrone esterne.
     Usato principalmente per intercettare la richiesta di scambio token GitHub
     senza effettuare I/O di rete reale.
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
    """Mocka il processo di rigenerazione e correzione del codice tramite LLM."""
    with patch("app.controllers.analysis.perform_regeneration") as m:
        yield m


@pytest.fixture
def mock_zip_upload():
    """Mocka il servizio responsabile dell'upload e dell'estrazione dei file ZIP."""
    with patch("app.controllers.analysis.perform_upload_zip") as m:
        yield m


@pytest.fixture
def mock_download():
    """Mocka la preparazione finale del pacchetto ZIP per il download."""
    with patch("app.controllers.analysis.perform_download") as m:
        yield m


# Aliases for backward compatibility with existing tests
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
#                                   TESTS: ZIP
# ==================================================================================

def test_upload_zip_success(mock_zip_upload):
    """
    Verifica l'upload e la gestione corretta di un file ZIP.

    Assicura che il controller riceva correttamente dati binari e restituisca
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
    Testa la gestione degli errori per upload di file ZIP non validi o corrotti.

    Verifica che se il servizio ZIP sottostante solleva un ValueError (es.
    archivio corrotto o tipo file errato), il controller restituisca
    correttamente uno status 400 Bad Request con i dettagli dell'errore.
    """
    mock_zip_upload.side_effect = ValueError("Not a valid zip")

    files = {"uploaded_file": ("test.txt", b"text", "text/plain")}
    response = client.post("/api/zip", data={"owner": "u", "repo": "r"}, files=files)

    assert response.status_code == 400
    assert "Not a valid zip" in response.json()["detail"]


# ==================================================================================
#                                TESTS: ANALYSIS
# ==================================================================================

def test_analyze_success_correct_schema(mock_scan):
    """
    Valida l'endpoint /analyze rispetto allo schema AnalyzeResponse.

    Assicura che:
    - La risposta JSON contenga 'main_license' e 'issues'.
    - I campi non definiti (es. 'compatibility_score') siano esclusi dalla risposta.
    """
    # Mock aligned with AnalyzeResponse in schemas.py
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

    # Verify that fields not existing in the schema are not present
    assert "compatibility_score" not in data


def test_analyze_internal_error(mock_scan):
    """
    Verifica la resilienza dell'API contro errori inattesi dei servizi di backend.

    Assicura che se il servizio di scansione incontra un errore critico
    (es. errore di connessione al database o eccezione non gestita), il
    controller intercetti il crash e restituisca uno status 500 Internal Server Error
    invece di esporre dati di eccezione grezzi.
    """
    mock_scan.side_effect = Exception("Database error")

    response = client.post("/api/analyze", json={"owner": "u", "repo": "r"})

    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


# ==================================================================================
#                                TESTS: REGENERATE
# ==================================================================================

def test_regenerate_success(mock_regen):
    """
    Verifica la logica di rigenerazione del codice.

    Controlla che il controller suddivida correttamente la stringa 'repository'
    in 'owner' e 'repo' prima di chiamare il servizio.
    """
    # Simulate the input payload (which is a previous AnalyzeResponse)
    payload = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": [],
        "report_path": "path"
    }

    # The service returns an updated object
    mock_regen.return_value = payload

    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 200

    # Verify correct parameter passing (split owner/repo)
    mock_regen.assert_called_once()
    kwargs = mock_regen.call_args[1]
    assert kwargs["owner"] == "facebook"
    assert kwargs["repo"] == "react"


def test_regenerate_bad_repo_string(mock_regen):
    """
    Valida la gestione di identificatori repository malformati durante la rigenerazione.

    L'endpoint di rigenerazione richiede che il campo 'repository' segua il formato
    'owner/repo'. Questo test assicura che, se viene fornita una stringa senza lo slash,
    l'API identifichi correttamente l'errore di formato e restituisca uno status 400.
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
#                                TESTS: DOWNLOAD
# ==================================================================================

def test_download_success(mock_download, tmp_path):
    """
    Verifica l'archiviazione e la consegna di progetti analizzati.

    Usa 'tmp_path' di pytest per creare un file fisico, assicurando che la FileResponse
    di FastAPI possa servire il contenuto senza errori.
    """
    # 1. Create a temporary physical file
    fake_zip = tmp_path / "archive.zip"
    fake_zip.write_bytes(b"DATA")

    # 2. The mock returns the path of this file
    mock_download.return_value = str(fake_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content == b"DATA"


def test_download_missing_repo(mock_download):
    """
    Valida la gestione degli errori per richieste di download di repository inesistenti.

    Assicura che se il servizio di download non trova il repository richiesto
    su disco (sollevando un ValueError), l'API risponda con uno status 400 Bad Request
    e fornisca un messaggio di errore chiaro nel dettaglio della risposta.
    """
    mock_download.side_effect = ValueError("Repo not cloned")

    response = client.post("/api/download", json={"owner": "ghost", "repo": "b"})

    assert response.status_code == 400
    assert "Repo not cloned" in response.json()["detail"]


def test_download_missing_params(mock_download):
    """
    Verifica la validazione degli input per l'endpoint /download.
    Se 'owner' o 'repo' mancano, deve restituire 400.
    """
    response = client.post("/api/download", json={"owner": "only_owner"})
    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


# ==================================================================================
#                       ADDITIONAL UNIT TESTS (NEWLY REQUESTED)
# ==================================================================================

def test_analyze_with_schema_validation(mock_scan):
    """
     Valida la risposta dell'endpoint di analisi rispetto allo schema AnalyzeResponse.

     Il test assicura che la risposta contenga i campi richiesti 'repository',
     'main_license' e la lista 'issues', seguendo rigorosamente lo schema Pydantic definito.

     Argomenti:
         mock_scan: mock per il servizio di scansione iniziale.
     """
    # Mock compliant with your schema (WITHOUT 'analysis', WITH 'main_license')
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
    Verifica che la mancanza di parametri obbligatori generi un errore di validazione.

    Se manca 'owner' o 'repo' nel body della richiesta,
    l'API deve restituire un errore 400.
    """
    response = client.post("/api/analyze", json={"owner": "solo_owner"})
    assert response.status_code == 400


def test_regenerate_with_payload_validation(mock_regen):
    """
       Verifica il flusso di rigenerazione con un payload di analisi valido.

       Questo test assicura che il controller possa processare un AnalyzeResponse
       generato in precedenza e passare i dettagli al servizio di rigenerazione LLM.

       Argomenti:
           mock_regen: mock per il servizio di rigenerazione del codice.
       """

    # Payload INPUT (Must have main_license, issues)
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
    Gestisce i casi in cui la stringa repository non contiene lo slash richiesto.

    Assicura che venga restituito un errore 400 quando l'identificatore repository
    è formattato in modo errato, anche se la struttura JSON è valida.
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
    Testa il recupero corretto del pacchetto ZIP analizzato.

    Valida gli header della risposta e assicura che il contenuto binario
    venga correttamente inviato al client.
    """
    dummy_zip = tmp_path / "fake.zip"
    dummy_zip.write_bytes(b"DATA")

    mock_download.return_value = str(dummy_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_error_handling(mock_download):
    """
    Verifica la gestione degli errori quando un pacchetto repository richiesto non esiste.

    Assicura che venga restituito un errore 400 se il servizio di download
    non trova il repository specificato su disco.
    """
    mock_download.side_effect = ValueError("Not found")
    response = client.post("/api/download", json={"owner": "u", "repo": "r"})
    assert response.status_code == 400


def test_upload_zip_with_file_validation(mock_upload_zip, tmp_path):
    """
     Verifica l'endpoint di upload ZIP con un file fisico temporaneo.

     Testa l'integrazione tra l'upload multipart e il servizio backend che estrae l'archivio.
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
#                            LICENSE SUGGESTION TESTS
# ==================================================================================

def test_suggest_license_success():
    """
    Testa con successo l'endpoint suggest_license.

    Verifica che l'endpoint /api/suggest-license restituisca
    un suggerimento di licenza valido in base ai requisiti forniti.
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
    Testa suggest_license con requisiti minimi.

    Verifica che l'endpoint funzioni anche con i soli campi obbligatori.
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
    Testa suggest_license con vincoli specifici.

    Verifica che i vincoli personalizzati vengano processati
    correttamente dal sistema di suggerimento.
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
    Testa suggest_license con un errore del servizio AI.

    Verifica che gli errori del servizio di suggerimento
    vengano gestiti correttamente e restituiscano un errore 500.
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
    Testa suggest_license con payload non valido.

    Verifica che l'endpoint rifiuti payload malformati
    tramite la validazione Pydantic.
    """
    payload = {
        "owner": "testowner"
        # Missing mandatory repo
    }

    response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 422  # Unprocessable Entity (Pydantic validation)


def test_suggest_license_with_detected_licenses():
    """
    Testa suggest_license con detected_licenses forniti.

    Verifica che l'endpoint processi correttamente le licenze rilevate
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

    # Verify detected_licenses was passed to the function
    mock_suggest.assert_called_once()
    call_args, call_kwargs = mock_suggest.call_args
    assert "detected_licenses" in call_kwargs
    assert call_kwargs["detected_licenses"] == ["MIT", "Apache-2.0"]


def test_suggest_license_with_empty_detected_licenses():
    """
    Testa suggest_license con una lista detected_licenses vuota.

    Verifica che una lista vuota venga gestita correttamente.
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

    # Verify empty list was passed
    call_kwargs = mock_suggest.call_args[1]
    assert call_kwargs["detected_licenses"] == []


def test_suggest_license_without_detected_licenses():
    """
    Testa suggest_license senza detected_licenses (campo omesso).

    Verifica che l'endpoint funzioni correttamente quando detected_licenses
    non è presente nel payload.
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

    # Verify None was passed when field is omitted
    call_kwargs = mock_suggest.call_args[1]
    assert call_kwargs["detected_licenses"] is None


def test_clone_success(mock_cloning):
    """
    Verifica il percorso di successo dell'endpoint di clonazione repository.
    """
    mock_cloning.return_value = "/tmp/cloned/repo"

    response = client.post("/api/clone", json={"owner": "test", "repo": "repo"})

    assert response.status_code == 200
    assert response.json()["status"] == "cloned"
    assert response.json()["local_path"] == "/tmp/cloned/repo"


def test_clone_missing_params():
    """
    Verifica la validazione dei parametri mancanti nell'endpoint di clonazione.
    """
    response = client.post("/api/clone", json={"owner": "test"})  # Missing repo
    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_value_error(mock_cloning):
    """
    Verifica la gestione di ValueError durante la clonazione (es. repo non trovato).
    """
    mock_cloning.side_effect = ValueError("Git error")
    response = client.post("/api/clone", json={"owner": "t", "repo": "r"})
    assert response.status_code == 400
    assert "Git error" in response.json()["detail"]


def test_clone_internal_error(mock_cloning):
    """
    Verifica la gestione di errori 500 per errori inattesi durante la clonazione.
    """
    mock_cloning.side_effect = Exception("System failure")
    response = client.post("/api/clone", json={"owner": "t", "repo": "r"})
    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


def test_download_internal_error(mock_download):
    """
    Verifica che eccezioni generiche in download_repo vengano intercettate e restituite come 500.
    """
    mock_download.side_effect = Exception("Disk failure")
    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


def test_upload_zip_http_exception_reraise(mock_upload_zip):
    """
    Verifica che le HTTPException sollevate dal servizio vengano rilanciate trasparentemente.
    Copre il blocco 'except HTTPException: raise' in upload_zip.
    """
    # Simulate a specific HTTP error from the service layer
    mock_upload_zip.side_effect = HTTPException(status_code=418, detail="I'm a teapot")

    files = {"uploaded_file": ("test.zip", b"content", "application/zip")}
    response = client.post("/api/zip", data={"owner": "u", "repo": "r"}, files=files)

    assert response.status_code == 418
    assert "I'm a teapot" in response.json()["detail"]


def test_upload_zip_internal_error(mock_upload_zip):
    """
    Verifica la gestione di errori 500 per errori inattesi durante l'upload ZIP.
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
    Testa l'endpoint root ("/") per assicurarsi che l'API sia attiva.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "License Checker Backend is running"}