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
5. Cloning Endpoint (Validation and execution).
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
    Validates the /analyze endpoint against the AnalyzeResponse schema.

    Ensures that:
    - The JSON response contains 'main_license' and 'issues'.
    - Undefined fields (e.g., 'compatibility_score') are excluded from the response.
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
    Validates error handling for download requests of non-existent repositories.

    Ensures that if the download service cannot find the requested repository
    on disk (raising a ValueError), the API responds with a 400 Bad Request
    status and provides a clear error message in the response detail.
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
#                       ADDITIONAL UNIT TESTS (NEWLY REQUESTED)
# ==================================================================================

def test_analyze_with_schema_validation(mock_scan):
    """
     Validates the analysis endpoint response against the AnalyzeResponse schema.

     The test ensures that the response contains the required 'repository',
     'main_license', and 'issues' list, strictly following the defined Pydantic schema.

     Args:
         mock_scan: Mock for the initial scanning service.
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
    mock_download.side_effect = ValueError("Not found")
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


# ==================================================================================
#                            LICENSE SUGGESTION TESTS
# ==================================================================================

def test_suggest_license_success():
    """
    Testing the suggest_license endpoint successfully.

    Verify that the /api/suggest-license endpoint returned
    a valid license suggestion based on the requirements provided.
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
    Test suggest_license with minimum requirements.

    Verify that the endpoint works even with minimum requirements (required fields only).
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
    Test suggest_license with specific constraints.

    Verify that custom constraints are correctly processed
    by the suggestion system.
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
    Test suggest_license with an AI service error.

    Verify that suggestion service errors
    are handled correctly and return a 500 error.
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
    Test suggest_license with invalid payload.

    Verify that the endpoint rejects malformed payloads
    with Pydantic validation.
    """
    payload = {
        "owner": "testowner"
        # Missing mandatory repo
    }

    response = client.post("/api/suggest-license", json=payload)

    assert response.status_code == 422  # Unprocessable Entity (Pydantic validation)


def test_suggest_license_with_detected_licenses():
    """
    Test suggest_license with the provided detected_licenses.

    Verify that the endpoint correctly processes detected licenses
    and passes them to the suggester.
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
    Test suggest_license with an empty detected_licenses.

    Verify that an empty detected_licenses list is handled correctly.
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
    Test suggest_license without detected_licenses (field omitted).

    Verify that the endpoint works correctly when detected_licenses
    is not provided in the payload.
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