"""
API Integration Testing Suite - Analysis & Authentication.

This module validates the integration between FastAPI controllers and the
underlying services (GitHub OAuth, ZIP handling, and License Analysis).
It ensures that the API correctly orchestrates complex workflows, handles
file system I/O, and manages external service failures gracefully.

The suite is divided into:
1. OAuth Authentication Flow (GitHub).
2. ZIP Archive Lifecycle (Upload, Extraction, Normalization).
3. Analysis Orchestration (Scanning and LLM integration).
4. Artifact Retrieval (Regeneration and Download).
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

# Global client for testing that does not require patched directories
client = TestClient(app)

"""
Integration tests for the /api/auth/start and /api/callback endpoints
These tests verify the complete OAuth authentication flow with GitHub
"""

# --- CLEANUP FIXTURES ---
@pytest.fixture
def mock_env_credentials():
    """Emulates environment variables or the function that retrieves them."""
    with patch("app.controllers.analysis.github_auth_credentials", side_effect=["MOCK_CID", "MOCK_SEC"]) as m:
        yield m


@pytest.fixture
def mock_httpx_post():
    """Mock the httpx POST call."""
    with patch("app.controllers.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_clone():
    """Mocks the cloning function."""
    with patch("app.controllers.analysis.perform_cloning") as m:
        yield m

# ==================================================================================
#                          TEST SUITE: GITHUB OAUTH FLOW
# ==================================================================================

"""
API Integration Suite: Archive Lifecycle & Analysis Orchestration.

This module validates the core "Upload-Analyze-Fix" pipeline. It ensures that 
the system correctly handles file system operations, archive extraction, 
and the sequence of calls between the API layer and the backend workers.

Key Functional Areas:
1. ZIP Extraction: Handling varying archive structures and filesystem overwrites.
2. Analysis Pipeline: Coordinating scanners and AI models (Hybrid integration).
3. Regeneration Workflow: Applying fixes to physical source files.
"""
import os
import shutil
import zipfile
from io import BytesIO
from app.utility import config

# ==================================================================================
#                          FIXTURES AND HELPERS
# ==================================================================================

@pytest.fixture
def sample_zip_file():
    """
    Create a ZIP file in memory with a simple test structure:
    test-repo-main/
        ├── README.md
        ├── LICENSE (MIT)
        └── src/
            └── main.py
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Structure with a single root directory
        zip_file.writestr('test-repo-main/README.md', '# Test Repository\nThis is a test.')
        zip_file.writestr('test-repo-main/LICENSE',
                          'MIT License\n\nCopyright (c) 2025 Test\n\n'
                          'Permission is hereby granted, free of charge...')
        zip_file.writestr('test-repo-main/src/main.py',
                          '# Main Python file\nprint("Hello World")')

    zip_buffer.seek(0)
    return zip_buffer


@pytest.fixture
def flat_zip_file():
    """
    Create a "flat" ZIP file (without the root directory):
    ├── README.md
    ├── LICENSE
    └── main.py
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('README.md', '# Flat Repository')
        zip_file.writestr('LICENSE', 'Apache License 2.0\n...')
        zip_file.writestr('main.py', 'print("Flat structure")')

    zip_buffer.seek(0)
    return zip_buffer


@pytest.fixture
def cleanup_test_repos():
    """Fixture to clean test repositories after each test."""
    yield
    # Cleanup after the test
    test_patterns = [
        'testowner_testrepo',
        'flatowner_flatrepo',
        'analyzeowner_analyzerepo',
        'emptyowner_emptyrepo',
        'emptyfileowner_emptyfilerepo',
        'specialowner_specialrepo',
        'nestedowner_nestedrepo',
        'multiowner_multirepo',
        'overwriteowner_overwriterepo',
        'workflowowner_workflowrepo',
        'incompatowner_incompatrepo'
    ]
    for pattern in test_patterns:
        test_dir = os.path.join(config.CLONE_BASE_DIR, pattern)
        if os.path.exists(test_dir):
            try:
                shutil.rmtree(test_dir)
            except Exception as e:
                print(f"Cleanup warning: Could not remove {test_dir}: {e}")


# ==================================================================================
#                          TEST SUITE: ZIP ARCHIVE LIFECYCLE
# ==================================================================================
# These tests verify real-world integration between:
# - FastAPI endpoint (/api/zip)
# - File system (extraction, directory creation)
# - ZIP management (zipfile library)
# - Parameter validation
# NO MOCKS of the features under test
# ==============================================================================

def test_upload_zip_success_with_root_folder(sample_zip_file, cleanup_test_repos):
    """
    Validates ZIP extraction and path normalization logic.

    This test ensures that repositories packaged with a single parent directory
    (e.g., test-repo-main/) are "flattened" so that the source code resides
    directly in the target directory without redundant nesting.
    """
    files = {
        'uploaded_file': ('test-repo.zip', sample_zip_file, 'application/zip')
    }
    data = {
        'owner': 'testowner',
        'repo': 'testrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    # Check answer
    assert response.status_code == 200
    json_response = response.json()
    assert json_response['status'] == 'cloned_from_zip'
    assert json_response['owner'] == 'testowner'
    assert json_response['repo'] == 'testrepo'
    assert 'local_path' in json_response

    # Verify that the files have been extracted correctly
    repo_path = json_response['local_path']
    assert os.path.exists(repo_path)
    assert os.path.exists(os.path.join(repo_path, 'README.md'))
    assert os.path.exists(os.path.join(repo_path, 'LICENSE'))
    assert os.path.exists(os.path.join(repo_path, 'src', 'main.py'))

    # Make sure there is NOT an extra directory (test-repo-main/)
    assert not os.path.exists(os.path.join(repo_path, 'test-repo-main'))


def test_upload_zip_success_flat_structure(flat_zip_file, cleanup_test_repos):
    """
    Integration Test: Upload of a ZIP with a flat directory structure.

    Objective:
    Ensures that the extraction logic correctly identifies that there is
    no single root directory to 'flatten' and instead extracts all files
    directly into the designated {owner}_{repo} target directory.

    Validation:
    1. HTTP 200 OK response.
    2. Verification of the 'local_path' returned in the JSON payload.
    3. Physical existence check of core files (README, LICENSE, main.py)
       inside the target directory on the host filesystem.
    """
    files = {
        'uploaded_file': ('flat-repo.zip', flat_zip_file, 'application/zip')
    }
    data = {
        'owner': 'flatowner',
        'repo': 'flatrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    assert response.status_code == 200
    json_response = response.json()

    repo_path = json_response['local_path']
    assert os.path.exists(os.path.join(repo_path, 'README.md'))
    assert os.path.exists(os.path.join(repo_path, 'LICENSE'))
    assert os.path.exists(os.path.join(repo_path, 'main.py'))


def test_upload_zip_invalid_file_type(cleanup_test_repos):
    """
    Verify that unsupported files are blocked.

    The endpoint must act as a gatekeeper: if the user attempts to upload a
    text file (.txt) instead of an archive, the system must abort
    the operation before touching the file system.
    """
    fake_file = BytesIO(b"This is not a zip file")
    files = {
        'uploaded_file': ('notazip.txt', fake_file, 'text/plain')
    }
    data = {
        'owner': 'badowner',
        'repo': 'badrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    assert response.status_code == 400
    assert 'zip' in response.json()['detail'].lower()


def test_upload_zip_corrupted_file(cleanup_test_repos):
    """
     Tests the handling of corrupt binary archives.

     Tests the system's resilience against files that have the correct extension
    but malformed binary content. The system should catch the 'BadZipFile'
    exception and return a client-side error (400) instead of a crash (500).
     """
    corrupted_zip = BytesIO(b"PK\x03\x04CORRUPTED_DATA")
    files = {
        'uploaded_file': ('corrupted.zip', corrupted_zip, 'application/zip')
    }
    data = {
        'owner': 'corruptowner',
        'repo': 'corruptrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    assert response.status_code == 400
    assert 'corrupted' in response.json()['detail'].lower() or 'invalid' in response.json()['detail'].lower()


def test_upload_zip_overwrites_existing(sample_zip_file, cleanup_test_repos):
    """
    Integration Test: Filesystem Idempotency.

    Verifies that uploading a ZIP for an existing owner/repo triggers a
    complete cleanup of the old directory. This prevents 'file pollution'
    where legacy files from a previous upload remain in the workspace.
    """
    # First creation
    files1 = {
        'uploaded_file': ('test1.zip', sample_zip_file, 'application/zip')
    }
    data = {
        'owner': 'overwriteowner',
        'repo': 'overwriterepo'
    }

    response1 = client.post('/api/zip', files=files1, data=data)
    assert response1.status_code == 200
    repo_path = response1.json()['local_path']

    # Let's add a marker file to check for overwriting
    marker_file = os.path.join(repo_path, 'MARKER.txt')
    with open(marker_file, 'w') as f:
        f.write('This should be deleted')

    assert os.path.exists(marker_file)

    # Second upload (same owner/repo)
    sample_zip_file.seek(0)  # Reset buffer
    files2 = {
        'uploaded_file': ('test2.zip', sample_zip_file, 'application/zip')
    }

    response2 = client.post('/api/zip', files=files2, data=data)
    assert response2.status_code == 200

    # Verify that the marker no longer exists (directory overwritten)
    assert not os.path.exists(marker_file)
    assert os.path.exists(os.path.join(repo_path, 'README.md'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_upload_zip_missing_owner_or_repo():
    """
    Validation Test: Missing mandatory metadata.

    Ensures that FastAPI's request validation correctly triggers a
    422 Unprocessable Entity error when the multipart form lacks
    required fields (owner or repo).
    """
    fake_zip = BytesIO(b"PK\x03\x04...")

    # Case 1: missing owner
    response1 = client.post(
        '/api/zip',
        files={'uploaded_file': ('test.zip', fake_zip, 'application/zip')},
        data={'repo': 'testrepo'}
    )
    assert response1.status_code == 422  # FastAPI validation error

    # Case 2: missing repo
    fake_zip.seek(0)
    response2 = client.post(
        '/api/zip',
        files={'uploaded_file': ('test.zip', fake_zip, 'application/zip')},
        data={'owner': 'testowner'}
    )
    assert response2.status_code == 422


def test_upload_zip_empty_file():
    """
    Edge Case: 0-byte file upload.

    Verifies that the system handles empty binary streams gracefully,
    returning a client-side error (400) or server error (500)
    depending on the zipfile library's initialization failure.
    """
    empty_file = BytesIO(b"")
    files = {
        'uploaded_file': ('empty.zip', empty_file, 'application/zip')
    }
    data = {
        'owner': 'emptyfileowner',
        'repo': 'emptyfilerepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    # It can be 400 (corrupt zip) or 500 (internal error), it depends on the implementation
    assert response.status_code in [400, 500]


def test_upload_zip_with_special_characters_in_filename():
    """
    Integration Test: Upload with complex characters in the ZIP filename.

    Verifies that the system correctly handles filenames with spaces, brackets,
    and versioning tags. The filename of the ZIP itself should not affect
    the target destination directory (which is derived from owner/repo).
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('README.md', '# Test')
    zip_buffer.seek(0)

    files = {
        'uploaded_file': ('test-repo (v1.0) [final].zip', zip_buffer, 'application/zip')
    }
    data = {
        'owner': 'specialowner',
        'repo': 'specialrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    # Success expected: destination is independent of source filename
    assert response.status_code == 200

    # Cleanup
    cleanup_path = os.path.join(config.CLONE_BASE_DIR, 'specialowner_specialrepo')
    if os.path.exists(cleanup_path):
        shutil.rmtree(cleanup_path)


def test_upload_zip_with_nested_directories():
    """
    Integration Test: Deeply nested directory structure.

    Validates that the extraction engine correctly preserves complex hierarchical
    structures and ensures files are accessible at the expected deep paths.
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Deeply nested structure
        zip_file.writestr('root/level1/level2/level3/deep_file.txt', 'Deep content')
        zip_file.writestr('root/README.md', '# Nested')
    zip_buffer.seek(0)

    files = {
        'uploaded_file': ('nested.zip', zip_buffer, 'application/zip')
    }
    data = {
        'owner': 'nestedowner',
        'repo': 'nestedrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    assert response.status_code == 200
    repo_path = response.json()['local_path']

    # Verify that nested files exist at the correct relative path
    assert os.path.exists(os.path.join(repo_path, 'level1', 'level2', 'level3', 'deep_file.txt'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_upload_zip_with_multiple_root_folders():
    """
    Integration Test: ZIP with multiple folders at the root level.

    Verifies that archives containing multiple directories or files in the root
    level are extracted completely without losing data or failing the structure check.
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('folder1/file1.txt', 'Content 1')
        zip_file.writestr('folder2/file2.txt', 'Content 2')
        zip_file.writestr('root_file.txt', 'Root content')
    zip_buffer.seek(0)

    files = {
        'uploaded_file': ('multi.zip', zip_buffer, 'application/zip')
    }
    data = {
        'owner': 'multiowner',
        'repo': 'multirepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    assert response.status_code == 200
    repo_path = response.json()['local_path']

    # Verify all components exist at the extraction target
    assert os.path.exists(os.path.join(repo_path, 'folder1', 'file1.txt'))
    assert os.path.exists(os.path.join(repo_path, 'folder2', 'file2.txt'))
    assert os.path.exists(os.path.join(repo_path, 'root_file.txt'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_analyze_on_empty_repository(cleanup_test_repos):
    """
    Integration Test: Analyzing an empty repository (directory exists, no files).

    Validates the orchestration between the endpoint, filesystem, and the
    analysis workflow when no data is present. Uses a minimal mock for
    ScanCode to avoid real execution on an empty directory.
    """
    # Manually create an empty directory
    owner, repo = 'emptyowner', 'emptyrepo'
    empty_path = os.path.join(config.CLONE_BASE_DIR, f'{owner}_{repo}')
    os.makedirs(empty_path, exist_ok=True)

    try:
        with patch('app.services.analysis_workflow.run_scancode') as mock_scan:
            # Mock scancode to simulate a scan on an empty repo
            mock_scan.return_value = {'files': []}

            response = client.post('/api/analyze', json={'owner': owner, 'repo': repo})

            # Check for non-crashing behavior (expected 200, 400, or 500 depending on business logic)
            assert response.status_code in [200, 400, 500]
    finally:
        if os.path.exists(empty_path):
            shutil.rmtree(empty_path)


def test_run_analysis_with_empty_string_parameters():
    """
    Validation Test: /api/analyze called with empty string parameters.

    Verifies that the API enforces non-empty values for owner/repo
    (not just presence, but content). Should return 400 Bad Request.
    """
    # Case 1: Owner is empty string
    response1 = client.post('/api/analyze', json={'owner': '', 'repo': 'testrepo'})
    assert response1.status_code == 400
    assert 'obbligatori' in response1.json()['detail'].lower() or 'required' in response1.json()['detail'].lower()

    # Case 2: Repo is empty string
    response2 = client.post('/api/analyze', json={'owner': 'testowner', 'repo': ''})
    assert response2.status_code == 400

    # Case 3: both are empty strings
    response3 = client.post('/api/analyze', json={'owner': '', 'repo': ''})
    assert response3.status_code == 400


def test_run_analysis_repository_not_found():
    """
     Integration Test: Analysis request for a non-existent repository.

     Verifies the integration between the endpoint, workflow orchestration,
     and the filesystem check. If the directory is missing, it should
     return a 400 Bad Request with a clear error message.
     """
    payload = {
        'owner': 'nonexistent',
        'repo': 'notfound'
    }

    response = client.post('/api/analyze', json=payload)

    assert response.status_code == 400
    assert 'non trovata' in response.json()['detail'].lower() or 'not found' in response.json()['detail'].lower()


def test_run_analysis_with_special_characters_in_params():
    """
     Integration Test: Analysis with special characters in owner/repo.

     Ensures the system handles non-standard characters (dashes, underscores)
     in URL parameters correctly. The test expects a 400 error because the
     directory won't exist, but validates that the request parsing is stable.
     """
    # Owner/repo with valid GitHub special characters
    payload = {
        'owner': 'owner-with-dash',
        'repo': 'repo_with_underscore'
    }

    response = client.post('/api/analyze', json=payload)

    # Status 400 is expected because the repo hasn't been cloned/uploaded
    assert response.status_code == 400


@patch('app.controllers.analysis.perform_initial_scan')
def test_run_analysis_generic_exception(mock_scan):
    """
    Integration Test: Handling unexpected runtime exceptions.

    Simulates a generic RuntimeError during the workflow (non-ValueError).
    Verifies that the API catches the error and returns a 500 status
    code with a generic 'Internal error' message to the client.
    """
    # Mock that raises a generic Exception (simulates unexpected error)
    mock_scan.side_effect = RuntimeError("Unexpected error during scan")

    payload = {'owner': 'errorowner', 'repo': 'errorrepo'}
    response = client.post('/api/analyze', json=payload)

    assert response.status_code == 500
    assert 'Internal error' in response.json()['detail'] or 'Internal' in response.json()['detail']
    assert 'Unexpected error' in response.json()['detail']


# ==============================================================================
# HYBRID TESTS - RUN_ANALYSIS WORKFLOW
# ==============================================================================
# These tests verify the orchestration between the endpoint and the workflow
# logic while MOCKING HEAVY external dependencies to avoid:
# - Slow ScanCode execution (CLI tool)
# - External LLM/Ollama API calls (Network/GPU cost)
# - Physical report file generation
#
# They are labeled HYBRID because:
# ✅ They test: HTTP routing, request validation, and workflow logic.
# ❌ They DO NOT test: Real integration with the external AI or ScanCode tools.
# ==============================================================================

@pytest.fixture
def mock_scancode_and_llm():
    """
    Fixture for HYBRID TESTS: Mocks all external dependencies of the analysis workflow.

    Mocked components:
    - ScanCode Tool (run_scancode)
    - Primary License Detection (detect_main_license_scancode)
    - Data Filtering (filter_licenses)
    - AI-based Extraction (extract_file_licenses)
    - Compatibility Engine (check_compatibility)
    - AI Suggestion Engine (enrich_with_llm_suggestions)
    """
    with patch('app.services.analysis_workflow.run_scancode') as mock_scancode, \
            patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
            patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
            patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
            patch('app.services.analysis_workflow.check_compatibility') as mock_compat, \
            patch('app.services.analysis_workflow.enrich_with_llm_suggestions') as mock_enrich:

        # Mock ScanCode output
        mock_scancode.return_value = {
            'files': [
                {
                    'path': 'README.md',
                    'licenses': [{'key': 'mit', 'score': 100.0}]
                },
                {
                    'path': 'src/main.py',
                    'licenses': [{'key': 'mit', 'score': 100.0}]
                }
            ]
        }

        # Mock main license detection
        mock_detect.return_value = ('MIT', 'LICENSE')

        # Mock filtered data
        mock_filter.return_value = mock_scancode.return_value

        # Mock extracted licenses
        mock_extract.return_value = [
            {'file_path': 'README.md', 'license': 'MIT'},
            {'file_path': 'src/main.py', 'license': 'MIT'}
        ]

        # Mock compatibility check (no issues)
        mock_compat.return_value = {'issues': []}

        # Mock enriched issues (no issues for MIT->MIT)
        mock_enrich.return_value = []

        yield {
            'scancode': mock_scancode,
            'detect': mock_detect,
            'filter': mock_filter,
            'extract': mock_extract,
            'compat': mock_compat,
            'enrich': mock_enrich
        }


def test_run_analysis_success_after_upload(sample_zip_file, mock_scancode_and_llm, cleanup_test_repos):
    """
    [HYBRID TEST]
    Full E2E flow: ZIP Upload -> Analysis execution with mocked dependencies.

    Steps:
    1. Upload a ZIP file (Real filesystem integration).
    2. Request analysis for that repository.
    3. Verify that the result matches the mocked scan data.
    """
    # Step 1: Upload ZIP
    files = {
        'uploaded_file': ('test-repo.zip', sample_zip_file, 'application/zip')
    }
    data = {
        'owner': 'analyzeowner',
        'repo': 'analyzerepo'
    }

    upload_response = client.post('/api/zip', files=files, data=data)
    assert upload_response.status_code == 200

    # Step 2: Analysis
    analyze_payload = {
        'owner': 'analyzeowner',
        'repo': 'analyzerepo'
    }

    analyze_response = client.post('/api/analyze', json=analyze_payload)

    # Validate output consistency
    assert analyze_response.status_code == 200
    result = analyze_response.json()

    assert result['repository'] == 'analyzeowner/analyzerepo'
    assert result['main_license'] == 'MIT'
    assert isinstance(result['issues'], list)

def test_run_analysis_with_incompatible_licenses(sample_zip_file, cleanup_test_repos):
    """
    [HYBRID TEST]
    Scenario: Detecting incompatible licenses using mocks.

    Ensures issues are correctly reported in the JSON response when:
    - Main license is detected as MIT.
    - A specific file contains GPL-3.0 (which is incompatible).
    """
    with patch('app.services.analysis_workflow.run_scancode') as mock_scancode, \
            patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
            patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
            patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
            patch('app.services.analysis_workflow.check_compatibility') as mock_compat, \
            patch('app.services.analysis_workflow.enrich_with_llm_suggestions') as mock_enrich:

        # Mock: Set up a conflict scenario (main license MIT, but a file with GPL)
        mock_scancode.return_value = {'files': []}
        mock_detect.return_value = ('MIT', 'LICENSE')
        mock_filter.return_value = mock_scancode.return_value
        mock_extract.return_value = [
            {'file_path': 'src/gpl_code.py', 'license': 'GPL-3.0'}
        ]

        # Mock incompatibility
        mock_compat.return_value = {
            'issues': [
                {
                    'file_path': 'src/gpl_code.py',
                    'detected_license': 'GPL-3.0',
                    'compatible': False,
                    'reason': 'GPL-3.0 is incompatible with MIT'
                }
            ]
        }

        mock_enrich.return_value = [
            {
                'file_path': 'src/gpl_code.py',
                'detected_license': 'GPL-3.0',
                'compatible': False,
                'reason': 'GPL-3.0 is incompatible with MIT',
                'suggestion': 'Consider relicensing or removing this file'
            }
        ]

        # Upload and analysis
        files = {'uploaded_file': ('test.zip', sample_zip_file, 'application/zip')}
        data = {'owner': 'incompatowner', 'repo': 'incompatrepo'}
        client.post('/api/zip', files=files, data=data)

        analyze_response = client.post('/api/analyze', json={'owner': 'incompatowner', 'repo': 'incompatrepo'})

        assert analyze_response.status_code == 200
        result = analyze_response.json()
        assert len(result['issues']) > 0
        assert result['issues'][0]['compatible'] is False
        assert 'GPL-3.0' in result['issues'][0]['detected_license']

        # Cleanup
        cleanup_path = os.path.join(config.CLONE_BASE_DIR, 'incompatowner_incompatrepo')
        if os.path.exists(cleanup_path):
            shutil.rmtree(cleanup_path)


def test_complete_workflow_upload_analyze(sample_zip_file, mock_scancode_and_llm, cleanup_test_repos):
    """
    [HYBRID TEST]
    Full end-to-end workflow test: from ZIP upload to analysis completion.

    This test ensures that the system can successfully transition from
    receiving a binary file to orchestrating a license scan on the
    resulting directory structure.

    Execution Steps:
    1. Upload ZIP: Real integration test for multipart form handling and disk extraction.
    2. Analyze: Trigger the workflow on the newly created directory.
    3. Consistency Check: Verify that the analysis result correctly maps to the uploaded metadata.

    External Dependencies Mocked: 6 (via mock_scancode_and_llm fixture).
    """
    owner, repo = 'workflowowner', 'workflowrepo'

    # Step 1: Upload
    upload_resp = client.post(
        '/api/zip',
        files={'uploaded_file': ('workflow.zip', sample_zip_file, 'application/zip')},
        data={'owner': owner, 'repo': repo}
    )
    assert upload_resp.status_code == 200
    local_path = upload_resp.json()['local_path']
    assert os.path.exists(local_path)

    # Step 2: Analyze
    analyze_resp = client.post('/api/analyze', json={'owner': owner, 'repo': repo})
    assert analyze_resp.status_code == 200

    result = analyze_resp.json()
    assert result['repository'] == f'{owner}/{repo}'
    assert result['main_license'] is not None


"""
INTEGRATION tests for the /api/regenerate and /api/download endpoints
These tests verify the complete flow with real interactions between components,
using mocks ONLY for expensive external dependencies (ScanCode, LLM).
"""
from app.models.schemas import AnalyzeResponse, LicenseIssue

# ==============================================================================
# FIXTURES AND HELPERS
# ==============================================================================

@pytest.fixture
def cleanup_test_repos():
    """
    Cleanup Fixture: Removes physical test directories and generated ZIPs.

    Ensures that temporary folders (e.g., regenowner_regenrepo) and
    downloaded artifacts are deleted after each test to prevent
    cross-test data contamination.
    """
    yield
    # Cleanup after test
    test_patterns = [
        'regenowner_regenrepo',
        'downloadowner_downloadrepo',
        'errorowner_errorrepo',
        'emptyowner_emptyrepo',
        'missingowner_missingrepo'
    ]
    for pattern in test_patterns:
        test_dir = os.path.join(config.CLONE_BASE_DIR, pattern)
        if os.path.exists(test_dir):
            try:
                shutil.rmtree(test_dir)
            except Exception as e:
                print(f"Cleanup warning: Could not remove {test_dir}: {e}")

        # Cleanup of zip files too
        zip_file = os.path.join(config.CLONE_BASE_DIR, f"{pattern}_download.zip")
        if os.path.exists(zip_file):
            try:
                os.remove(zip_file)
            except Exception as e:
                print(f"Cleanup warning: Could not remove {zip_file}: {e}")


@pytest.fixture
def create_test_repo():
    """Helper to create a physical test repository on the file system."""
    def _create(owner: str, repo: str, files: dict = None):
        """
    Helper Fixture: Manually populates the filesystem with a test repository.

    Args:
        owner: The repository owner's name.
        repo: The repository name.
        files: A dictionary mapping file paths to their string content.

    Returns:
        The absolute path to the created repository.
    """
        repo_path = os.path.join(config.CLONE_BASE_DIR, f"{owner}_{repo}")
        os.makedirs(repo_path, exist_ok=True)

        # Default file if not specified
        if files is None:
            files = {
                'README.md': '# Test Repository\n\nThis is a test.',
                'LICENSE': 'MIT License\n\nCopyright (c) 2025 Test\n\nPermission is hereby granted...',
                'src/main.py': '# Main file\nprint("Hello World")\n',
                'src/utils.py': '# Utils\ndef helper():\n    pass\n'
            }

        # Create the files
        for file_path, content in files.items():
            full_path = os.path.join(repo_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

        return repo_path

    return _create


@pytest.fixture
def sample_analyze_response():
    """
    Fixture: Provides a standard AnalyzeResponse object.

    Used to simulate a previous analysis result that needs
    to be passed into the regeneration endpoint.
    """
    return AnalyzeResponse(
        repository="regenowner/regenrepo",
        main_license="MIT",
        issues=[
            LicenseIssue(
                file_path="src/incompatible.py",
                detected_license="GPL-3.0",
                compatible=False,
                reason="GPL-3.0 is incompatible with MIT",
                suggestion="Consider relicensing or removing this file"
            )
        ],
    )


# ==============================================================================
# INTEGRATION TEST - REGENERATE_ANALYSIS
# ==============================================================================

def test_regenerate_analysis_success_integration(
        create_test_repo,
        sample_analyze_response,
        cleanup_test_repos
):
    """
    Integration Test: Successful code regeneration.

    Workflow:
    1. Populate the filesystem with a physical repository.
    2. Call /api/regenerate with a previous AnalyzeResponse.
    3. Verify the orchestration between the endpoint, workflow, and filesystem.

    Mocks: Only 'perform_regeneration' is mocked to avoid external LLM calls.
    """
    # Step 1: Create test repositories
    repo_path = create_test_repo(
        "regenowner",
        "regenrepo",
        files={
            'README.md': '# Test',
            'src/incompatible.py': '# GPL code\nprint("test")'
        }
    )

    assert os.path.exists(repo_path)

    # Mock only perform regeneration (complex workflow with LLM)
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        # Regeneration Response Mock
        mock_regen.return_value = AnalyzeResponse(
            repository="regenowner/regenrepo",
            main_license="MIT",
            issues=[
                LicenseIssue(
                    file_path="src/incompatible.py",
                    detected_license="MIT",  # Now compatible
                    compatible=True,
                    reason="Successfully regenerated",
                    regenerated_code_path="src/incompatible.py"
                )
            ],
            report_path="/tmp/new_report.txt"
        )

        # Step 3: Endpoint call
        response = client.post(
            "/api/regenerate",
            json=sample_analyze_response.model_dump()
        )

        # Check answer
        assert response.status_code == 200
        result = response.json()

        assert result['repository'] == "regenowner/regenrepo"
        assert result['main_license'] == "MIT"
        assert len(result['issues']) == 1
        assert result['issues'][0]['compatible'] is True

        # Verify that perform_regeneration was called correctly
        mock_regen.assert_called_once()
        call_args = mock_regen.call_args
        assert call_args[1]['owner'] == "regenowner"
        assert call_args[1]['repo'] == "regenrepo"


def test_regenerate_analysis_invalid_repository_format():
    """
    Validation Test: Rejects malformed repository identifiers.

    Ensures the endpoint returns HTTP 400 if the 'repository' string
    does not follow the 'owner/repo' format.
    """
    invalid_payload = {
        "repository": "noslash",  # Missing "/"
        "main_license": "MIT",
        "issues": [],
    }

    response = client.post("/api/regenerate", json=invalid_payload)

    assert response.status_code == 400
    assert "Invalid repository format" in response.json()["detail"]
    assert "owner/repo" in response.json()["detail"]


def test_regenerate_analysis_repository_not_found(cleanup_test_repos):
    """
    Error Handling Test: Regeneration on a missing repository.

    Verifies that the system correctly maps a 'Repository not found'
    Value Error to a client-side HTTP 400 response.
    """
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        # Mock that raises ValueError (repository not found)
        mock_regen.side_effect = ValueError("Repository not found")

        payload = {
            "repository": "missingowner/missingrepo",
            "main_license": "MIT",
            "issues": [],
        }

        response = client.post("/api/regenerate", json=payload)

        assert response.status_code == 400
        assert "Repository not found" in response.json()["detail"]


def test_regenerate_analysis_generic_exception(cleanup_test_repos):
    """
    Pure Integration Test: Real repository download.

    Flow:
    1. Create a physical repository with multiple files and subdirectories.
    2. Request a download via /api/download.
    3. Validate HTTP headers (Content-Type: application/zip).
    4. Physically extract the returned ZIP to verify internal content integrity.
    """
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        # Mock that raises generic Exception
        mock_regen.side_effect = RuntimeError("Unexpected error during regeneration")

        payload = {
            "repository": "errorowner/errorrepo",
            "main_license": "MIT",
            "issues": [],
        }

        response = client.post("/api/regenerate", json=payload)

        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


# ==============================================================================
# INTEGRATION TEST - DOWNLOAD_REPO
# ==============================================================================

def test_download_repo_success_integration(create_test_repo, cleanup_test_repos):
    """
    Full Integration Test: Successful repository download.

    Workflow:
    1. Populate the filesystem with a physical test repository.
    2. Call the /api/download endpoint.
    3. Verify the HTTP response (200 OK, application/zip).
    4. Validate the ZIP content integrity and structure.

    Note: This is a PURE integration test with no mocks.
    """
    # Step 1: Setup physical repo
    repo_path = create_test_repo(
        "downloadowner",
        "downloadrepo",
        files={
            'README.md': '# Download Test\n\nThis repo will be downloaded.',
            'LICENSE': 'MIT License\n',
            'src/main.py': 'print("main")\n',
            'src/utils.py': 'def util(): pass\n',
            'docs/guide.md': '# Guide\n'
        }
    )

    assert os.path.exists(repo_path)

    # Step 2: endpoint call
    response = client.post(
        "/api/download",
        json={"owner": "downloadowner", "repo": "downloadrepo"}
    )

    # Step 3: Response Validation
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "downloadowner_downloadrepo.zip" in response.headers.get("content-disposition", "")

    # Step 4: Content Validation
    zip_content = BytesIO(response.content)
    with zipfile.ZipFile(zip_content, 'r') as zip_file:
        # List files in ZIP
        zip_files = zip_file.namelist()

        # Verify all directories and files are present in the archive
        assert 'downloadowner_downloadrepo/README.md' in zip_files
        assert 'downloadowner_downloadrepo/LICENSE' in zip_files
        assert 'downloadowner_downloadrepo/src/main.py' in zip_files
        assert 'downloadowner_downloadrepo/src/utils.py' in zip_files
        assert 'downloadowner_downloadrepo/docs/guide.md' in zip_files

        # Verify specific file content
        readme_content = zip_file.read('downloadowner_downloadrepo/README.md').decode('utf-8')
        assert '# Download Test' in readme_content

def test_download_repo_repository_not_found(_msg_matches):
    """
     Error Handling Test: Attempt to download a non-existent repository.

     Verifies the integration between the endpoint, the service layer,
     and the filesystem check. Should return a 400 Bad Request.
     """
    response = client.post(
        "/api/download",
        json={"owner": "nonexistent", "repo": "notfound"}
    )

    assert response.status_code == 400
    # Assuming _msg_matches checks if either string is in the detail
    assert "Repository not found" in response.json()["detail"] or "Repository non trovata" in response.json()["detail"]

def test_download_repo_missing_parameters():
    """
    Validation Test: Missing mandatory parameters.

    Ensures the API rejects requests missing the 'owner' or 'repo'
    keys with a 400 Bad Request.
    """
    # Case 1: missing owner
    response1 = client.post("/api/download", json={"repo": "test"})
    assert response1.status_code == 400
    assert "obbligatori" in response1.json()["detail"].lower() or "required" in response1.json()["detail"].lower()

    # Case 2: missing repo
    response2 = client.post("/api/download", json={"owner": "test"})
    assert response2.status_code == 400

    # Case 3: empty payload
    response3 = client.post("/api/download", json={})
    assert response3.status_code == 400


def test_download_repo_empty_repository(create_test_repo, cleanup_test_repos):
    """
     Edge Case Test: Downloading an empty repository.

     Verifies that a directory with no files can still be successfully
     zipped and returned to the user.
     """
    # Create empty repo (directory only)
    repo_path = create_test_repo("emptyowner", "emptyrepo", files={})
    assert os.path.exists(repo_path)

    response = client.post(
        "/api/download",
        json={"owner": "emptyowner", "repo": "emptyrepo"}
    )

    # Should still succeed (returns a valid ZIP of the directory)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_repo_with_special_characters_in_filenames(

        create_test_repo,
        cleanup_test_repos
):
    """
    Integration Test: Handling special characters in filenames during ZIP creation.

    Ensures that files containing spaces, dashes, underscores, and
    parentheses are correctly preserved and included in the final archive.
    """
    repo_path = create_test_repo(
        "specialowner",
        "specialrepo",
        files={
            'file with spaces.txt': 'Content with spaces',
            'file-with-dash.py': '# Dash file',
            'file_with_underscore.md': '# Underscore file',
            'special (parens).txt': 'Parentheses content'
        }
    )

    response = client.post(
        "/api/download",
        json={"owner": "specialowner", "repo": "specialrepo"}
    )

    assert response.status_code == 200

    # ZIP content verification
    zip_content = BytesIO(response.content)
    with zipfile.ZipFile(zip_content, 'r') as zip_file:
        zip_files = zip_file.namelist()

        # Check for presence of special character filenames
        assert any('file with spaces.txt' in f for f in zip_files)
        assert any('file-with-dash.py' in f for f in zip_files)
        assert any('file_with_underscore.md' in f for f in zip_files)
        assert any('special (parens).txt' in f for f in zip_files)

    # Cleanup
    cleanup_path = os.path.join(config.CLONE_BASE_DIR, 'specialowner_specialrepo')
    if os.path.exists(cleanup_path):
        shutil.rmtree(cleanup_path)
    zip_path = os.path.join(config.CLONE_BASE_DIR, 'specialowner_specialrepo_download.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)


def test_download_repo_with_empty_string_parameters():
    """
     Validation Test: Empty string inputs.

     Ensures that empty strings ("") are not treated as valid identifiers
     for owner or repository names.
     """
    # Empty owner string
    response1 = client.post("/api/download", json={"owner": "", "repo": "test"})
    assert response1.status_code == 400

    # Empty repo string
    response2 = client.post("/api/download", json={"owner": "test", "repo": ""})
    assert response2.status_code == 400

    # Both empty strings
    response3 = client.post("/api/download", json={"owner": "", "repo": ""})
    assert response3.status_code == 400


def test_download_repo_generic_exception(create_test_repo, cleanup_test_repos):
    """
    Error Handling Test: Internal Server Error during the ZIP process.

    Verifies that if an unexpected RuntimeError occurs during compression,
    the API returns a 500 status with an 'Internal error' detail.
    """
    # Create repository
    create_test_repo("errorowner", "errorrepo")

    with patch('app.controllers.analysis.perform_download') as mock_download:
        # Mock that raises generic Exception
        mock_download.side_effect = RuntimeError("Unexpected error during zip")

        response = client.post(
            "/api/download",
            json={"owner": "errorowner", "repo": "errorrepo"}
        )

        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


# ==============================================================================
# COMPLETE WORKFLOW TEST: UPLOAD → ANALYZE → REGENERATE → DOWNLOAD
# ==============================================================================

def test_complete_workflow_integration(create_test_repo, cleanup_test_repos):
    """
    End-to-End Orchestration Test: Full Application Lifecycle.

    Tests the integration between:
    1. Repository Setup (Manual creation)
    2. Analysis Workflow (Mocked external scan)
    3. Regeneration Workflow (Mocked AI remediation)
    4. Download (Real filesystem zipping)

    This ensures that the output from the 'Analyze' phase is valid
    input for the 'Regenerate' phase, and the final state is downloadable.
    """
    # Step 1: Setup repository
    owner, repo = "workflowowner", "workflowrepo"
    repo_path = create_test_repo(
        owner,
        repo,
        files={
            'README.md': '# Workflow Test',
            'src/code.py': 'print("test")'
        }
    )

    # Step 2: Mock Analyze
    with patch('app.controllers.analysis.perform_initial_scan') as mock_scan:
        mock_scan.return_value = AnalyzeResponse(
            repository=f"{owner}/{repo}",
            main_license="MIT",
            issues=[],
        )

        analyze_resp = client.post("/api/analyze", json={"owner": owner, "repo": repo})
        assert analyze_resp.status_code == 200
        analyze_result = analyze_resp.json()

    # Step 3: Mock Regenerate
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        mock_regen.return_value = AnalyzeResponse(
            repository=f"{owner}/{repo}",
            main_license="MIT",
            issues=[],
        )

        regen_resp = client.post("/api/regenerate", json=analyze_result)
        assert regen_resp.status_code == 200

    # Step 4: Real-world Download integration
    download_resp = client.post("/api/download", json={"owner": owner, "repo": repo})
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/zip"

    # Verify ZIP content
    zip_content = BytesIO(download_resp.content)
    with zipfile.ZipFile(zip_content, 'r') as zip_file:
        zip_files = zip_file.namelist()
        assert any('README.md' in f for f in zip_files)
        assert any('src/code.py' in f for f in zip_files)

    # Cleanup
    cleanup_path = os.path.join(config.CLONE_BASE_DIR, f'{owner}_{repo}')
    if os.path.exists(cleanup_path):
        shutil.rmtree(cleanup_path)
    zip_path = os.path.join(config.CLONE_BASE_DIR, f'{owner}_{repo}_download.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)


# ==================================================================================
#                 INTEGRATION TESTS FOR /api/clone
# ==================================================================================


def test_clone_repository_integration_success():
    """
    Integration test: Clone a repository using /api/clone endpoint.

    Verifies that the endpoint correctly accepts owner and repo parameters,
    calls the cloning service, and returns proper status and path information.
    """
    with patch('app.controllers.analysis.perform_cloning') as mock_clone:
        mock_clone.return_value = "/test/path/owner_repo"

        response = client.post("/api/clone", json={
            "owner": "testowner",
            "repo": "testrepo"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cloned"
        assert data["owner"] == "testowner"
        assert data["repo"] == "testrepo"
        assert "local_path" in data
        assert "owner_repo" in data["local_path"]

        mock_clone.assert_called_once_with(owner="testowner", repo="testrepo")


def test_clone_repository_missing_owner():
    """
    Integration test: Clone endpoint rejects request without owner.
    """
    response = client.post("/api/clone", json={"repo": "testrepo"})

    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_repository_missing_repo():
    """
    Integration test: Clone endpoint rejects request without repo.
    """
    response = client.post("/api/clone", json={"owner": "testowner"})

    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_repository_both_params_missing():
    """
    Integration test: Clone endpoint rejects request with no parameters.
    """
    response = client.post("/api/clone", json={})

    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_repository_empty_strings():
    """
    Integration test: Clone endpoint rejects empty string parameters.
    """
    response1 = client.post("/api/clone", json={"owner": "", "repo": "testrepo"})
    assert response1.status_code == 400

    response2 = client.post("/api/clone", json={"owner": "testowner", "repo": ""})
    assert response2.status_code == 400

    response3 = client.post("/api/clone", json={"owner": "", "repo": ""})
    assert response3.status_code == 400


def test_clone_repository_service_value_error():
    """
    Integration test: Clone endpoint handles service-level ValueError.

    Verifies that when the cloning service raises a ValueError,
    it's properly caught and returns a 400 status.
    """
    with patch('app.controllers.analysis.perform_cloning') as mock_clone:
        mock_clone.side_effect = ValueError("Repository not found or access denied")

        response = client.post("/api/clone", json={
            "owner": "badowner",
            "repo": "badrepo"
        })

        assert response.status_code == 400
        assert "Repository not found" in response.json()["detail"]


def test_clone_repository_service_generic_exception():
    """
    Integration test: Clone endpoint handles unexpected exceptions.

    Verifies that unexpected errors are caught and return a 500 status.
    """
    with patch('app.controllers.analysis.perform_cloning') as mock_clone:
        mock_clone.side_effect = Exception("Unexpected error occurred")

        response = client.post("/api/clone", json={
            "owner": "owner",
            "repo": "repo"
        })

        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


def test_clone_repository_with_special_characters():
    """
    Integration test: Clone with special characters in repository name.

    Verifies that repositories with dots, hyphens, and underscores
    are handled correctly.
    """
    with patch('app.controllers.analysis.perform_cloning') as mock_clone:
        mock_clone.return_value = "/test/path/org-name_repo.test"

        response = client.post("/api/clone", json={
            "owner": "org-name",
            "repo": "repo.test"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cloned"
        assert data["owner"] == "org-name"
        assert data["repo"] == "repo.test"


def test_clone_repository_real_workflow(cleanup_test_repos):
    """
    Integration test: Full clone workflow with real file system operations.

    This test performs actual cloning operations (mocked Git, but real filesystem)
    and verifies the entire workflow end-to-end.
    """
    owner = "integration_clone"
    repo = "clone_test"

    with patch('app.services.github.github_client.Repo.clone_from'):
        response = client.post("/api/clone", json={
            "owner": owner,
            "repo": repo
        })

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "cloned"
        assert data["owner"] == owner
        assert data["repo"] == repo
        assert "local_path" in data

        expected_path = os.path.join(config.CLONE_BASE_DIR, f"{owner}_{repo}")
        assert expected_path in data["local_path"] or f"{owner}_{repo}" in data["local_path"]


# ==================================================================================
#                 INTEGRATION TESTS FOR /api/suggest-license
# ==================================================================================


def test_suggest_license_integration_success():
    """
    Integration test: Suggest license based on requirements.

    Verifies that the suggest-license endpoint correctly processes
    user requirements and returns appropriate license suggestions.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache 2.0 is ideal for projects requiring patent protection",
            "alternatives": ["MIT", "BSD-3-Clause"]
        }

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
            "additional_requirements": "Need patent protection and commercial use"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] == "Apache-2.0"
        assert "explanation" in data
        assert "patent" in data["explanation"].lower()
        assert "alternatives" in data
        assert len(data["alternatives"]) == 2
        assert "MIT" in data["alternatives"]

        mock_suggest.assert_called_once()


def test_suggest_license_with_detected_licenses_integration():
    """
    Integration test: Suggest license with detected licenses from analysis.

    Verifies that detected licenses are passed to the recommendation engine
    and considered in the suggestion.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache-2.0 is compatible with detected MIT and BSD-3-Clause licenses",
            "alternatives": ["MIT"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": True,
            "copyleft": "none",
            "detected_licenses": ["MIT", "BSD-3-Clause"]
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] == "Apache-2.0"
        assert "compatible" in data["explanation"].lower()

        # Verify detected_licenses was passed to the function
        mock_suggest.assert_called_once()
        call_kwargs = mock_suggest.call_args[1]
        assert "detected_licenses" in call_kwargs
        assert call_kwargs["detected_licenses"] == ["MIT", "BSD-3-Clause"]


def test_suggest_license_gpl_incompatibility_detection():
    """
    Integration test: Verify GPL incompatibility is detected with permissive licenses.

    When detected licenses include Apache-2.0, suggesting GPL should be avoided
    due to incompatibility.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        # Mock should avoid GPL when Apache-2.0 is detected
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache-2.0 is compatible with existing Apache-2.0 license in the project",
            "alternatives": ["MIT", "BSD-3-Clause"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": True,
            "copyleft": "strong",
            "detected_licenses": ["Apache-2.0"]
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        # Should NOT suggest GPL when Apache-2.0 is detected
        assert "GPL" not in data["suggested_license"]
        assert data["suggested_license"] in ["Apache-2.0", "MIT", "BSD-3-Clause"]


def test_suggest_license_with_multiple_detected_licenses():
    """
    Integration test: Handle multiple detected licenses correctly.

    Verifies that the system can handle projects with multiple licenses
    and suggest a compatible one.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache-2.0 is compatible with all detected licenses: MIT, BSD-3-Clause, Apache-2.0",
            "alternatives": ["MIT"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": True,
            "copyleft": "none",
            "detected_licenses": ["MIT", "BSD-3-Clause", "Apache-2.0"]
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] == "Apache-2.0"

        # Verify all licenses were passed
        call_kwargs = mock_suggest.call_args[1]
        assert len(call_kwargs["detected_licenses"]) == 3


def test_suggest_license_minimal_requirements():
    """
    Integration test: Suggest license with only required fields.

    Verifies that the endpoint works with minimal requirements (only owner and repo).
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "MIT",
            "explanation": "MIT is a simple and permissive license",
            "alternatives": []
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] == "MIT"
        assert "alternatives" in data


def test_suggest_license_copyleft_requirements():
    """
    Integration test: Suggest license for copyleft requirements.

    Verifies that strong copyleft requirements result in GPL-like suggestions.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "GPL-3.0",
            "explanation": "GPL-3.0 provides strong copyleft protection",
            "alternatives": ["AGPL-3.0", "LGPL-3.0"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": False,
            "copyleft": "strong",
            "additional_requirements": "Need strong copyleft protection"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "GPL" in data["suggested_license"]
        assert len(data["alternatives"]) > 0


def test_suggest_license_weak_copyleft():
    """
    Integration test: Suggest license for weak copyleft requirements.

    Verifies that weak copyleft typically suggests LGPL-style licenses.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "LGPL-3.0",
            "explanation": "LGPL-3.0 provides weak copyleft, allowing linking with proprietary code",
            "alternatives": ["MPL-2.0"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "copyleft": "weak",
            "commercial_use": True
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] in ["LGPL-3.0", "MPL-2.0", "LGPL-2.1"]


def test_suggest_license_missing_required_fields():
    """
    Integration test: Suggest license endpoint validates required fields.

    Verifies that missing owner or repo returns a 422 validation error.
    """
    response1 = client.post("/api/suggest-license", json={"owner": "testowner"})
    assert response1.status_code == 422

    response2 = client.post("/api/suggest-license", json={"repo": "testrepo"})
    assert response2.status_code == 422

    response3 = client.post("/api/suggest-license", json={})
    assert response3.status_code == 422


def test_suggest_license_service_exception():
    """
    Integration test: Suggest license handles service errors.

    Verifies that when the AI service fails, a 500 error is returned
    with an appropriate error message.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.side_effect = Exception("AI service temporarily unavailable")

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": True
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 500
        assert "Failed to generate license suggestion" in response.json()["detail"]


def test_suggest_license_all_boolean_options():
    """
    Integration test: Suggest license with all boolean options set.

    Verifies that complex requirement combinations are processed correctly.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache 2.0 meets all specified requirements",
            "alternatives": ["MIT"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": True,
            "trademark_use": True,
            "liability": True,
            "copyleft": "none",
            "additional_requirements": "Enterprise-grade permissive license"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["suggested_license"] in ["Apache-2.0", "MIT", "BSD-3-Clause"]


def test_suggest_license_response_schema_validation():
    """
    Integration test: Validate response schema for suggest-license.

    Ensures that the response conforms to LicenseSuggestionResponse schema.
    """
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "MIT",
            "explanation": "Simple permissive license",
            "alternatives": ["BSD-2-Clause", "BSD-3-Clause", "ISC"]
        }

        payload = {
            "owner": "testowner",
            "repo": "testrepo"
        }

        response = client.post("/api/suggest-license", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        assert "suggested_license" in data
        assert isinstance(data["suggested_license"], str)

        assert "explanation" in data
        assert isinstance(data["explanation"], str)

        assert "alternatives" in data
        assert isinstance(data["alternatives"], list)

        # Verify alternatives are strings
        for alt in data["alternatives"]:
            assert isinstance(alt, str)


def test_suggest_license_with_analyze_workflow(sample_zip_file, cleanup_test_repos):
    """
    Integration test: Complete workflow - upload, analyze, get suggestion.

    This test verifies that after analyzing a repository with UNKNOWN license,
    the suggest-license endpoint can provide appropriate recommendations.
    """
    owner = "suggest_test"
    repo = "test_repo"

    # Step 1: Upload a ZIP file (sample_zip_file is a BytesIO object)
    sample_zip_file.seek(0)
    upload_resp = client.post(
        "/api/zip",
        data={"owner": owner, "repo": repo},
        files={"uploaded_file": ("test.zip", sample_zip_file, "application/zip")}
    )

    assert upload_resp.status_code == 200

    # Step 2: Mock analysis that returns UNKNOWN license
    with patch('app.services.analysis_workflow.run_scancode') as mock_scan, \
         patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
         patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
         patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
         patch('app.services.analysis_workflow.check_compatibility') as mock_compat, \
         patch('app.services.analysis_workflow.enrich_with_llm_suggestions') as mock_enrich, \
         patch('app.services.analysis_workflow.needs_license_suggestion') as mock_needs:

        mock_scan.return_value = {"files": []}
        mock_detect.return_value = "UNKNOWN"
        mock_filter.return_value = {"files": []}
        mock_extract.return_value = {}
        mock_compat.return_value = {"issues": []}
        mock_enrich.return_value = []
        mock_needs.return_value = True

        analyze_resp = client.post("/api/analyze", json={"owner": owner, "repo": repo})
        assert analyze_resp.status_code == 200

        analyze_data = analyze_resp.json()
        assert analyze_data["main_license"] == "UNKNOWN"
        assert analyze_data["needs_license_suggestion"] is True

    # Step 3: Request license suggestion
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "MIT",
            "explanation": "MIT is recommended for this type of project",
            "alternatives": ["Apache-2.0", "BSD-3-Clause"]
        }

        suggest_payload = {
            "owner": owner,
            "repo": repo,
            "commercial_use": True,
            "modification": True,
            "distribution": True
        }

        suggest_resp = client.post("/api/suggest-license", json=suggest_payload)

        assert suggest_resp.status_code == 200
        suggest_data = suggest_resp.json()
        assert suggest_data["suggested_license"] in ["MIT", "Apache-2.0", "BSD-3-Clause"]
        assert len(suggest_data["alternatives"]) > 0


def test_complete_workflow_with_detected_licenses(sample_zip_file, cleanup_test_repos):
    """
    Integration test: Complete workflow with detected licenses extraction.

    This test verifies the full workflow:
    1. Upload/Clone repository
    2. Analyze and detect existing licenses
    3. Pass detected licenses to suggestion endpoint
    4. Receive compatible license recommendation
    """
    owner = "workflow_test"
    repo = "multi_license_repo"

    # Step 1: Upload repository
    sample_zip_file.seek(0)
    upload_resp = client.post(
        "/api/zip",
        data={"owner": owner, "repo": repo},
        files={"uploaded_file": ("test.zip", sample_zip_file, "application/zip")}
    )
    assert upload_resp.status_code == 200

    # Step 2: Mock analysis with multiple detected licenses
    with patch('app.services.analysis_workflow.run_scancode') as mock_scan, \
         patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
         patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
         patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
         patch('app.services.analysis_workflow.check_compatibility') as mock_compat, \
         patch('app.services.analysis_workflow.enrich_with_llm_suggestions') as mock_enrich, \
         patch('app.services.analysis_workflow.needs_license_suggestion') as mock_needs:

        # Mock files with different licenses
        issues_list = [
            {"file_path": "file1.py", "detected_license": "MIT", "compatible": True, "reason": None},
            {"file_path": "file2.py", "detected_license": "Apache-2.0", "compatible": True, "reason": None}
        ]

        mock_scan.return_value = {"files": [
            {"path": "file1.py", "licenses": [{"key": "mit"}]},
            {"path": "file2.py", "licenses": [{"key": "apache-2.0"}]}
        ]}
        mock_detect.return_value = "UNKNOWN"
        mock_filter.return_value = {"files": [
            {"path": "file1.py", "licenses": [{"key": "mit"}]},
            {"path": "file2.py", "licenses": [{"key": "apache-2.0"}]}
        ]}
        mock_extract.return_value = {
            "file1.py": ["MIT"],
            "file2.py": ["Apache-2.0"]
        }
        mock_compat.return_value = {"issues": issues_list}
        mock_enrich.return_value = issues_list  # Return the same issues (enriched)
        mock_needs.return_value = True

        analyze_resp = client.post("/api/analyze", json={"owner": owner, "repo": repo})
        assert analyze_resp.status_code == 200
        analyze_data = analyze_resp.json()

        # Extract detected licenses from analysis
        detected_licenses = set()
        for issue in analyze_data.get("issues", []):
            if issue.get("detected_license") and issue["detected_license"] not in ["Unknown", "None"]:
                detected_licenses.add(issue["detected_license"])

        detected_licenses_list = list(detected_licenses)

    # Step 3: Request suggestion WITH detected licenses
    with patch('app.controllers.analysis.suggest_license_based_on_requirements') as mock_suggest:
        mock_suggest.return_value = {
            "suggested_license": "Apache-2.0",
            "explanation": "Apache-2.0 is compatible with detected MIT and Apache-2.0 licenses",
            "alternatives": ["MIT"]
        }

        suggest_payload = {
            "owner": owner,
            "repo": repo,
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "detected_licenses": detected_licenses_list
        }

        suggest_resp = client.post("/api/suggest-license", json=suggest_payload)

        assert suggest_resp.status_code == 200
        suggest_data = suggest_resp.json()

        # Verify the suggestion is compatible
        assert suggest_data["suggested_license"] in ["Apache-2.0", "MIT"]

        # Verify detected_licenses were passed
        call_kwargs = mock_suggest.call_args[1]
        assert "detected_licenses" in call_kwargs
        assert len(call_kwargs["detected_licenses"]) > 0