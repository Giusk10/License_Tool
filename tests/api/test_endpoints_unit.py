"""
test: controllers/analysis.py
"""

import pytest
import httpx
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
    """Simula il recupero delle credenziali (CLIENT_ID, SECRET)."""
    with patch("app.controllers.analysis.github_auth_credentials") as m:
        m.return_value = "MOCK_CLIENT_ID"
        yield m


@pytest.fixture
def mock_httpx_client():
    """Mocka le chiamate HTTP esterne (es. verso GitHub per il token)."""
    with patch("app.controllers.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_cloning():
    """Mocka il servizio di clonazione (git clone)."""
    with patch("app.controllers.analysis.perform_cloning") as m:
        yield m


@pytest.fixture
def mock_scan():
    """Mocka il servizio di scansione iniziale (ScanCode + LLM)."""
    with patch("app.controllers.analysis.perform_initial_scan") as m:
        yield m


@pytest.fixture
def mock_regen():
    """Mocka il servizio di rigenerazione codice."""
    with patch("app.controllers.analysis.perform_regeneration") as m:
        yield m


@pytest.fixture
def mock_zip_upload():
    """Mocka il servizio di gestione upload ZIP."""
    with patch("app.controllers.analysis.perform_upload_zip") as m:
        yield m


@pytest.fixture
def mock_download():
    """Mocka il servizio di creazione pacchetto ZIP per il download."""
    with patch("app.controllers.analysis.perform_download") as m:
        yield m


# Alias per compatibilità con test esistenti
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
#                                   TESTS: AUTH
# ==================================================================================

def test_start_analysis_redirect(mock_env_credentials):
    """Verifica che /auth/start ridiriga correttamente a GitHub."""
    mock_env_credentials.return_value = "MY_CLIENT_ID"

    response = client.get(
        "/api/auth/start",
        params={"owner": "facebook", "repo": "react"},
        follow_redirects=False  # Fondamentale per controllare il 307
    )

    assert response.status_code == 307
    location = response.headers["location"]

    # Verifica parametri URL
    assert "github.com/login/oauth/authorize" in location
    assert "client_id=MY_CLIENT_ID" in location
    assert "state=facebook:react" in location
    assert "scope=repo" in location


@pytest.mark.asyncio
async def test_auth_callback_success(mock_env_credentials, mock_httpx_client, mock_cloning):
    """Happy Path: Login GitHub OK -> Token ottenuto -> Clonazione OK."""
    # 1. Setup Mock GitHub (Token)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "gh_token_ABC"}
    mock_httpx_client.return_value = mock_resp

    # 2. Setup Mock Clonazione
    mock_cloning.return_value = "/tmp/repos/facebook/react"

    # 3. Chiamata
    response = client.get("/api/callback", params={"code": "12345", "state": "facebook:react"})

    # 4. Asserzioni
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cloned"
    assert data["local_path"] == "/tmp/repos/facebook/react"

    # Verifica che il token sia stato passato
    mock_cloning.assert_called_once_with(owner="facebook", repo="react", oauth_token="gh_token_ABC")


@pytest.mark.asyncio
async def test_auth_callback_network_error(mock_env_credentials, mock_httpx_client):
    """
    Test di Robustezza: Simula timeout/errore di rete verso GitHub.
    Deve restituire 503 Service Unavailable (grazie al try/except aggiunto).
    """
    mock_httpx_client.side_effect = httpx.RequestError("Connection timeout")

    response = client.get("/api/callback", params={"code": "123", "state": "u:r"})

    assert response.status_code == 503
    assert "An error occurred" in response.json()["detail"]


def test_auth_callback_invalid_state():
    """Tests invalid state format."""
    response = client.get("/api/callback", params={"code": "123", "state": "invalid_format"})
    assert response.status_code == 400
    assert "Invalid state" in response.json()["detail"]


# ==================================================================================
#                                   TESTS: ZIP
# ==================================================================================

def test_upload_zip_success(mock_zip_upload):
    """Verifica upload e gestione corretta dello ZIP."""
    mock_zip_upload.return_value = "/tmp/extracted_zip"

    files = {"uploaded_file": ("test.zip", b"fake-content", "application/zip")}
    data = {"owner": "user", "repo": "repo"}

    response = client.post("/api/zip", data=data, files=files)

    assert response.status_code == 200
    assert response.json()["status"] == "cloned_from_zip"
    mock_zip_upload.assert_called_once()


def test_upload_zip_bad_file(mock_zip_upload):
    """Se il servizio ZIP lancia errore (es. file corrotto), API torna 400."""
    mock_zip_upload.side_effect = ValueError("Non è uno zip valido")

    files = {"uploaded_file": ("test.txt", b"text", "text/plain")}
    response = client.post("/api/zip", data={"owner": "u", "repo": "r"}, files=files)

    assert response.status_code == 400
    assert "Non è uno zip valido" in response.json()["detail"]


# ==================================================================================
#                                TESTS: ANALYSIS
# ==================================================================================

def test_analyze_success_correct_schema(mock_scan):
    """
    Verifica /analyze usando lo schema corretto da schemas.py.
    (Senza 'compatibility_score', con 'issues').
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

    # Verifica che fields non esistenti nello schema non siano presenti
    assert "compatibility_score" not in data


def test_analyze_internal_error(mock_scan):
    """If the scan service crashes, API returns 500."""
    mock_scan.side_effect = Exception("Database error")

    response = client.post("/api/analyze", json={"owner": "u", "repo": "r"})

    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


# ==================================================================================
#                                TESTS: REGENERATE
# ==================================================================================

def test_regenerate_success(mock_regen):
    """Verifica la rigenerazione del codice."""
    # Simuliamo il payload di input (che è una AnalyzeResponse precedente)
    payload = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": [],
        "report_path": "path"
    }

    # Il servizio ritorna un oggetto aggiornato
    mock_regen.return_value = payload

    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 200

    # Verifica passaggio parametri corretti (split owner/repo)
    mock_regen.assert_called_once()
    kwargs = mock_regen.call_args[1]
    assert kwargs["owner"] == "facebook"
    assert kwargs["repo"] == "react"


def test_regenerate_bad_repo_string(mock_regen):
    """Se 'repository' non ha lo slash, torna 400."""
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
    Testa il download file.
    Usa 'tmp_path' di pytest per creare un file reale, altrimenti
    FileResponse di FastAPI fallisce con RuntimeError.
    """
    # 1. Creiamo un file fisico temporaneo
    fake_zip = tmp_path / "archive.zip"
    fake_zip.write_bytes(b"DATA")

    # 2. Il mock ritorna il path di questo file
    mock_download.return_value = str(fake_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content == b"DATA"


def test_download_missing_repo(mock_download):
    """Se la repo non esiste su disco, torna 400."""
    mock_download.side_effect = ValueError("Repo non clonata")

    response = client.post("/api/download", json={"owner": "ghost", "repo": "b"})

    assert response.status_code == 400
    assert "Repo non clonata" in response.json()["detail"]


# ==================================================================================
#                       ADDITIONAL UNIT TESTS (NUOVI RICHIESTI)
# ==================================================================================

def test_start_redirect_with_url_parsing(mock_creds):
    """Verifica che l'URL di redirect sia costruito correttamente con parsing robusto."""
    response = client.get(
        "/api/auth/start",
        params={"owner": "facebook", "repo": "react"},
        follow_redirects=False
    )

    assert response.status_code in [302, 307]

    # Parsing robusto dell'URL
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)

    assert parsed.netloc == "github.com"
    assert params["client_id"] == ["MOCK_CLIENT_ID"]
    assert params["state"] == ["facebook:react"]


@pytest.mark.asyncio
async def test_callback_with_token_verification(mock_creds, mock_httpx_post, mock_clone):
    """Verifica il flusso completo di callback con verifica token."""
    # Mock risposta GitHub
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "gh_token_123"}
    mock_httpx_post.return_value = mock_resp

    # Mock Clone
    mock_clone.return_value = "/tmp/cloned/facebook/react"

    response = client.get("/api/callback", params={"code": "123", "state": "facebook:react"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cloned"
    assert data["local_path"] == "/tmp/cloned/facebook/react"

    # Verifica che il token sia passato al clone
    mock_clone.assert_called_once()
    assert mock_clone.call_args[1]['oauth_token'] == "gh_token_123"


def test_callback_invalid_state_no_slash():
    """Error if state does not have colon."""
    response = client.get("/api/callback", params={"code": "123", "state": "invalid_state"})
    assert response.status_code == 400
    assert "Invalid state" in response.json()["detail"]


def test_analyze_with_schema_validation(mock_scan):
    """Testa l'analisi usando lo schema corretto (AnalyzeResponse)."""
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
    """Verifica che parametri mancanti restituiscano 400."""
    response = client.post("/api/analyze", json={"owner": "solo_owner"})
    assert response.status_code == 400


def test_regenerate_with_payload_validation(mock_regen):
    """Verifica rigenerazione con payload corretto."""

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
    """Valid input for schema, but repository without slash."""
    payload = {
        "repository": "noslash",
        "main_license": "N/A",
        "issues": []
    }
    response = client.post("/api/regenerate", json=payload)

    assert response.status_code == 400
    assert "Invalid repository format" in response.json()["detail"]


def test_download_zip_success(mock_download, tmp_path):
    """Verifica download zip con validazione contenuto."""
    dummy_zip = tmp_path / "fake.zip"
    dummy_zip.write_bytes(b"DATA")

    mock_download.return_value = str(dummy_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_error_handling(mock_download):
    """Verifica gestione errori durante download."""
    mock_download.side_effect = ValueError("Non trovata")
    response = client.post("/api/download", json={"owner": "u", "repo": "r"})
    assert response.status_code == 400


def test_upload_zip_with_file_validation(mock_upload_zip, tmp_path):
    """Verifica upload zip con validazione file."""
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
