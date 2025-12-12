import sys
import os
import pytest
import httpx
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

# ==============================================================================
# 🚑 FIX PERCORSI BLINDATO
# ==============================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, root_dir)

# --- IMPORTAZIONI ---
try:
    from app.api.analysis import router
except ImportError as e:
    raise ImportError(f"Errore Import: {e}. Assicurati di aver creato 'router_base.py' e sistemato gli import circolari!")

# --- SETUP APP ---
app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ==============================================================================
# 🛠️ FIXTURES (Setup pulito e riutilizzabile)
# ==============================================================================

@pytest.fixture
def mock_creds():
    with patch("app.api.analysis.github_auth_credentials") as m:
        m.return_value = "MOCK_CLIENT_ID"
        yield m

@pytest.fixture
def mock_httpx_post():
    with patch("app.api.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m

@pytest.fixture
def mock_clone():
    with patch("app.api.analysis.perform_cloning") as m:
        yield m

@pytest.fixture
def mock_scan():
    with patch("app.api.analysis.perform_initial_scan") as m:
        yield m

@pytest.fixture
def mock_regen():
    with patch("app.api.analysis.perform_regeneration") as m:
        yield m

@pytest.fixture
def mock_download():
    with patch("app.api.analysis.perform_download") as m:
        yield m

@pytest.fixture
def mock_upload_zip():
    with patch("app.api.analysis.perform_upload_zip") as m:
        yield m


# ==============================================================================
# 🔐 TEST AUTH & CALLBACK
# ==============================================================================

def test_start_analysis_redirect(mock_creds):
    """Verifica che l'URL di redirect sia costruito correttamente."""
    response = client.get(
        "/auth/start",
        params={"owner": "facebook", "repo": "react"},
        follow_redirects=False  # <--- CORRETTO (era allow_redirects)
    )

    assert response.status_code in [302, 307]

    # Parsing robusto dell'URL
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)

    assert parsed.netloc == "github.com"
    assert params["client_id"] == ["MOCK_CLIENT_ID"]
    assert params["state"] == ["facebook:react"]


@pytest.mark.asyncio
async def test_callback_success(mock_creds, mock_httpx_post, mock_clone):
    """Verifica il flusso completo di callback."""
    # Mock risposta GitHub
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "gh_token_123"}
    mock_httpx_post.return_value = mock_resp

    # Mock Clone
    mock_clone.return_value = "/tmp/cloned/facebook/react"

    response = client.get("/callback", params={"code": "123", "state": "facebook:react"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cloned"
    assert data["local_path"] == "/tmp/cloned/facebook/react"

    # Verifica che il token sia passato al clone
    mock_clone.assert_called_once()
    assert mock_clone.call_args[1]['oauth_token'] == "gh_token_123"


def test_callback_invalid_state():
    """Errore se lo stato non ha i due punti."""
    response = client.get("/callback", params={"code": "123", "state": "invalid_state"})
    assert response.status_code == 400
    assert "Stato non valido" in response.json()["detail"]


# ==============================================================================
# 📊 TEST ANALYZE (Initial Scan)
# ==============================================================================

def test_analyze_success(mock_scan):
    """Testa l'analisi usando lo schema corretto (AnalyzeResponse)."""
    # Mock conforme al tuo schema (SENZA 'analysis', CON 'main_license')
    mock_res = {
        "repository": "test/repo",
        "main_license": "MIT",
        "issues": [],
        "report_path": "/tmp/report.md"
    }
    mock_scan.return_value = mock_res

    response = client.post("/analyze", json={"owner": "test", "repo": "repo"})

    assert response.status_code == 200
    data = response.json()

    assert data["repository"] == "test/repo"
    assert data["main_license"] == "MIT"
    assert isinstance(data["issues"], list)

    mock_scan.assert_called_with(owner="test", repo="repo")


def test_analyze_missing_params():
    response = client.post("/analyze", json={"owner": "solo_owner"})
    assert response.status_code == 400


# ==============================================================================
# 🔄 TEST REGENERATE
# ==============================================================================

def test_regenerate_success(mock_regen):
    """Verifica rigenerazione con payload corretto."""

    # Payload INPUT (Deve avere main_license, issues, report_path)
    payload = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": [],
        "report_path": "old/path"
    }

    # Mock OUTPUT
    mock_res = {
        "repository": "facebook/react",
        "main_license": "MIT",
        "issues": [],
        "report_path": "new/path"
    }
    mock_regen.return_value = mock_res

    response = client.post("/regenerate", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["repository"] == "facebook/react"
    assert data["report_path"] == "new/path"

    mock_regen.assert_called_once()
    assert mock_regen.call_args[1]['owner'] == "facebook"


def test_regenerate_bad_format():
    """Input valido per schema, ma repository senza slash."""
    payload = {
        "repository": "noslash",
        "main_license": "N/A",
        "issues": [],
        "report_path": "path"
    }
    response = client.post("/regenerate", json=payload)

    assert response.status_code == 400
    assert "Formato repository non valido" in response.json()["detail"]


# ==============================================================================
# 📦 TEST DOWNLOAD & UPLOAD
# ==============================================================================

def test_download_success(mock_download, tmp_path):
    """Verifica download zip."""
    dummy_zip = tmp_path / "fake.zip"
    dummy_zip.write_bytes(b"DATA")

    mock_download.return_value = str(dummy_zip)

    response = client.post("/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_error(mock_download):
    mock_download.side_effect = ValueError("Non trovata")
    response = client.post("/download", json={"owner": "u", "repo": "r"})
    assert response.status_code == 400


def test_upload_zip_success(mock_upload_zip, tmp_path):
    fake_zip = tmp_path / "test.zip"
    fake_zip.write_bytes(b"content")

    mock_upload_zip.return_value = "/tmp/uploaded/path"

    with open(fake_zip, "rb") as f:
        response = client.post(
            "/zip",
            data={"owner": "u", "repo": "r"},
            files={"uploaded_file": ("test.zip", f, "application/zip")}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "cloned_from_zip"