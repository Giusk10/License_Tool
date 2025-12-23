"""
Analysis Controllers Integration Test Module.

This module orchestrates integration tests for the analysis controller endpoints
defined in `app.controllers.analysis`. It verifies the end-to-end workflow,
ensuring that API endpoints respond correctly and communicate effectively
with mocked backend services.

The suite covers:
1. GitHub OAuth Authentication (Redirect and Callback).
2. ZIP Archive Management (Upload and validation).
3. Analysis Lifecycle (License scanning and schema validation).
4. Post-processing (Code regeneration and artifact download).
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
    """
     Simulates the retrieval of GitHub OAuth credentials (CLIENT_ID, SECRET).
     Returns:
         MagicMock: A mock object returning 'MOCK_CLIENT_ID'.
     """
    with patch("app.controllers.analysis.github_auth_credentials") as m:
        m.return_value = "MOCK_CLIENT_ID"
        yield m


@pytest.fixture
def mock_httpx_client():
    """
     Mocks external asynchronous HTTP calls.
     Primarily used to intercept the GitHub token exchange request
     without performing actual network I/O.
     """
    with patch("app.controllers.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_cloning():
    """Mocks the repository cloning service (git clone)."""
    with patch("app.controllers.analysis.perform_cloning") as m:
        yield m


@pytest.fixture
def mock_scan():
    """Mocks the initial scanning service (ScanCode + LLM Analysis)."""
    with patch("app.controllers.analysis.perform_initial_scan") as m:
        yield m


@pytest.fixture
def mock_regen():
    """Mocks the code regeneration and correction process via LLM."""
    with patch("app.controllers.analysis.perform_regeneration") as m:
        yield m


@pytest.fixture
def mock_zip_upload():
    """Mocks the service responsible for uploading and extracting ZIP files."""
    with patch("app.controllers.analysis.perform_upload_zip") as m:
        yield m


@pytest.fixture
def mock_download():
    """Mocks the final ZIP package preparation for download."""
    with patch("app.controllers.analysis.perform_download") as m:
        yield m


# Aliases for backward compatibility with existing tests
@pytest.fixture
def mock_env_credentials(mock_creds):
    """Alias for mock_creds."""
    return mock_creds


@pytest.fixture
def mock_httpx_post(mock_httpx_client):
    """Alias for mock_httpx_client."""
    return mock_httpx_client


@pytest.fixture
def mock_clone(mock_cloning):
    """Alias for mock_cloning."""
    return mock_cloning


@pytest.fixture
def mock_upload_zip(mock_zip_upload):
    """Alias for mock_zip_upload."""
    return mock_zip_upload


# ==================================================================================
#                                   TESTS: AUTH
# ==================================================================================

def test_start_analysis_redirect(mock_env_credentials):
    """
     Verifies that the /auth/start endpoint correctly redirects to GitHub.

     Checks:
     - Status code 307 (Temporary Redirect).
     - Presence of 'client_id' and 'state' (owner:repo) in the Location header.
     """
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
    """
     Tests the Happy Path for the OAuth callback.
     Process:
     1. GitHub returns a code.
     2. API exchanges code for an access token (mocked).
     3. API triggers the repository cloning process.
     """
    # 1. Setup Mock GitHub (Token)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "gh_token_ABC"}
    mock_httpx_client.return_value = mock_resp

    # 2. Setup Mock Clonazione
    mock_cloning.return_value = "/tmp/repos/facebook/react"

    # 3. Call
    response = client.get("/api/callback", params={"code": "12345", "state": "facebook:react"})

    # 4. Asserzioni
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cloned"
    assert data["local_path"] == "/tmp/repos/facebook/react"

    # Verify that the token has been passed
    mock_cloning.assert_called_once_with(owner="facebook", repo="react", oauth_token="gh_token_ABC")


@pytest.mark.asyncio
async def test_auth_callback_network_error(mock_env_credentials, mock_httpx_client):
    """
    Robustness Test: Simulates a timeout/network error to GitHub.
    It should return 503 Service Unavailable (thanks to the added try/except).
    """
    mock_httpx_client.side_effect = httpx.RequestError("Connection timeout")

    response = client.get("/api/callback", params={"code": "123", "state": "u:r"})

    assert response.status_code == 503
    assert "An error occurred" in response.json()["detail"]


def test_auth_callback_invalid_state():
    """
     Validates the error handling for an improperly formatted state parameter.

     The API expects the 'state' query parameter to follow the 'owner:repo'
     format. This test ensures that providing a string without the required
     colon delimiter results in a 400 Bad Request error.
     """
    response = client.get("/api/callback", params={"code": "123", "state": "invalid_format"})
    assert response.status_code == 400
    assert "Invalid state" in response.json()["detail"]


# ==================================================================================
#                                   TESTS: ZIP
# ==================================================================================

def test_upload_zip_success(mock_zip_upload):
    """
    Verifies successful ZIP file upload and processing.

    Ensures the controller correctly receives binary data and returns
    the 'cloned_from_zip' status.
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
    Tests error handling for invalid or corrupt ZIP file uploads.

    Verifies that if the underlying ZIP service raises a ValueError (e.g.,
    due to a corrupt archive or incorrect file type), the controller
    correctly returns a 400 Bad Request status with the error details.
    """
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
    Validates the /analyze endpoint against the AnalyzeResponse schema.

    Ensures that:
    - The JSON response contains 'main_license' and 'issues'.
    - Undefined fields (e.g., 'compatibility_score') are excluded from the response.
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
    """
    Verifies API resilience against unexpected backend service failures.

    Ensures that if the scanning service encounters a critical error
    (e.g., database connection failure or unhandled exception), the
    controller catches the crash and returns a 500 Internal Server Error
    status instead of exposing raw exception data.
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
    Verifies the code regeneration logic.

    Checks that the controller correctly splits the 'repository' string
    into 'owner' and 'repo' before calling the service.
    """
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
    """
    Validates the handling of malformed repository identifiers during regeneration.

    The regeneration endpoint requires the 'repository' field to follow the
    'owner/repo' slash format. This test ensures that if a string without
    a slash is provided, the API correctly identifies the format error
    and returns a 400 Bad Request status.
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
    Verifies the archival and delivery of analyzed projects.

    Uses pytest's 'tmp_path' to create a physical file, ensuring FastAPI's
    FileResponse can serve the content without errors.
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
    """
    Validates error handling for download requests of non-existent repositories.

    Ensures that if the download service cannot find the requested repository
    on disk (raising a ValueError), the API responds with a 400 Bad Request
    status and provides a clear error message in the response detail.
    """
    mock_download.side_effect = ValueError("Repo non clonata")

    response = client.post("/api/download", json={"owner": "ghost", "repo": "b"})

    assert response.status_code == 400
    assert "Repo non clonata" in response.json()["detail"]


# ==================================================================================
#                       ADDITIONAL UNIT TESTS (NUOVI RICHIESTI)
# ==================================================================================

def test_start_redirect_with_url_parsing(mock_creds):
    """
    Verifies the GitHub redirect URL construction using robust parsing.

    This test ensures that the generated 'Location' header is a valid URL
    and contains the expected query parameters (client_id and state)
    in the correct format.

    Args:
        mock_creds: Fixture simulating the retrieval of client credentials.
    """
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
    """
    Verifies the full OAuth callback flow with token passing verification.

    This test confirms that:
    1. The API successfully exchanges the code for a GitHub token.
    2. The retrieved token is correctly passed to the cloning service.

    Args:
        mock_creds: Fixture for client credentials.
        mock_httpx_post: Async mock for the token exchange request.
        mock_clone: Mock for the cloning service.
    """
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
    """
    Validates error handling for an invalid state format.

    The state parameter must follow the 'owner:repo' format. This test
    ensures that a 400 Bad Request is returned if the colon is missing.
    """
    response = client.get("/api/callback", params={"code": "123", "state": "invalid_state"})
    assert response.status_code == 400
    assert "Invalid state" in response.json()["detail"]


def test_analyze_with_schema_validation(mock_scan):
    """
     Validates the analysis endpoint response against the AnalyzeResponse schema.

     The test ensures that the response contains the required 'repository',
     'main_license', and 'issues' list, strictly following the defined Pydantic schema.

     Args:
         mock_scan: Mock for the initial scanning service.
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
    Verifies that missing required parameters trigger a validation error.

    If either 'owner' or 'repo' is missing from the request body,
    the API must return a 400 error.
    """
    response = client.post("/api/analyze", json={"owner": "solo_owner"})
    assert response.status_code == 400


def test_regenerate_with_payload_validation(mock_regen):
    """
       Verifies the regeneration flow with a valid analysis payload.

       This test ensures that the controller can process a previously
       generated AnalyzeResponse and pass the details back to the LLM
       regeneration service.

       Args:
           mock_regen: Mock for the code regeneration service.
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
    Handles cases where the repository string lacks the required slash.

    Ensures a 400 error is returned when the repository identifier
    is improperly formatted, even if the JSON structure is valid.
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
    Tests successful retrieval of the analyzed ZIP package.

    Validates the response headers and ensures the binary content
    is correctly streamed to the client.
    """
    dummy_zip = tmp_path / "fake.zip"
    dummy_zip.write_bytes(b"DATA")

    mock_download.return_value = str(dummy_zip)

    response = client.post("/api/download", json={"owner": "u", "repo": "r"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_error_handling(mock_download):
    """
    Verifies error handling when a requested repository package is missing.

    Ensures that a 400 error is returned if the download service
    cannot find the specified repository on disk.
    """
    mock_download.side_effect = ValueError("Non trovata")
    response = client.post("/api/download", json={"owner": "u", "repo": "r"})
    assert response.status_code == 400


def test_upload_zip_with_file_validation(mock_upload_zip, tmp_path):
    """
     Verifies the ZIP upload endpoint with a temporary physical file.

     Tests the integration between the multipart file upload and
     the backend service that extracts the archive.
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
