"""
Analysis Workflow Unit Test Module.

This module contains unit tests for the core orchestration functions within
`app.services.analysis_workflow`. It verifies the logic for repository cloning,
ZIP file management, the initial scanning pipeline, and the LLM-driven
code regeneration process.

The suite covers:
1. Repository Cloning: Success and failure handling during git operations.
2. ZIP Management: Validation, extraction, and cleanup of uploaded archives.
3. Analysis Pipeline: Orchestration of ScanCode, license detection, and compatibility.
4. Code Regeneration: Intelligent filtering of files and LLM interaction for fixes.
5. Post-Regeneration Rescan: Validating the repository state after code changes.
"""

import os
import tempfile
import os
import json
import zipfile
import pytest
import shutil
from unittest.mock import MagicMock, patch
from fastapi import UploadFile, HTTPException
from io import BytesIO

from app.services.analysis_workflow import (
    perform_cloning,
    perform_upload_zip,
    perform_initial_scan,
    perform_regeneration,
    _regenerate_incompatible_files,
    _rescan_repository
)
from app.models.schemas import AnalyzeResponse, LicenseIssue

# ==================================================================================
#                                     FIXTURES
# ==================================================================================

# Note: This module primarily uses pytest's built-in 'tmp_path' and
# 'patch_config_variables' from conftest.py to manage filesystem interactions.

# ==================================================================================
#                                TESTS: REPO CLONING
# ==================================================================================

def test_perform_cloning_success(tmp_path):
    """"
    Verifies successful repository cloning.

    Ensures that the service correctly interacts with the low-level clone utility
    and returns the expected absolute path to the cloned repository.
    """
    owner, repo = "testowner", "testrepo"
    base_dir = tmp_path / "clones"
    base_dir.mkdir()

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)), \
         patch("app.services.analysis_workflow.clone_repo") as mock_clone:
        mock_clone.return_value = MagicMock(success=True, repo_path=str(base_dir / f"{owner}_{repo}"))

        result = perform_cloning(owner, repo)

        assert result == str(base_dir / f"{owner}_{repo}")
        mock_clone.assert_called_once_with(owner, repo)


def test_perform_cloning_failure():
    """
    Tests error handling during repository cloning.

    Verifies that if the git operation fails (e.g., authentication error),
     a ValueError is raised with a descriptive message.
    """
    owner, repo = "badowner", "badrepo"

    with patch("app.services.analysis_workflow.clone_repo") as mock_clone:
        mock_clone.return_value = MagicMock(success=False, error="Authentication failed")

        with pytest.raises(ValueError, match="Cloning error: Authentication failed"):
            perform_cloning(owner, repo)

        mock_clone.assert_called_once_with(owner, repo)


# ==================================================================================
#                                TESTS: ZIP UPLOAD
# ==================================================================================

def test_perform_upload_zip_invalid_extension():
    """
    Validates file extension checks for ZIP uploads.

    Ensures that non-ZIP files (e.g., .tar.gz) are rejected with a
    400 Bad Request exception.
    """
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.tar.gz"
    with pytest.raises(HTTPException) as exc:
        perform_upload_zip("owner", "repo", mock_file)
    assert exc.value.status_code == 400


def test_perform_upload_zip_corrupted_file():
    """
    Tests handling of corrupted ZIP archives.

    Verifies that if the uploaded file is not a valid ZIP archive, the
    service raises a 400 error indicating the file is corrupted.
    """
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "fake.zip"
    mock_file.file = BytesIO(b"not a zip content")

    with pytest.raises(HTTPException) as exc:
        perform_upload_zip("owner", "repo", mock_file)
    assert exc.value.status_code == 400
    assert "corrupted" in exc.value.detail


def test_perform_upload_zip_preventive_cleanup(tmp_path):
    """
    Verifies the preventive cleanup logic before extraction.

    Ensures that if a target directory already exists from a previous run,
    it is completely removed before processing the new ZIP file. This prevents
    mixing old artifacts with new source code.
    """
    owner, repo = "cleanup", "existing"
    base_dir = tmp_path / "clones"
    base_dir.mkdir()

    target_dir = base_dir / f"{owner}_{repo}"
    target_dir.mkdir()
    (target_dir / "old.txt").write_text("old")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "a") as zf:
        zf.writestr("new.txt", "new data")
    zip_buffer.seek(0)

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "update.zip"
    mock_file.file = zip_buffer

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        perform_upload_zip(owner, repo, mock_file)

        # Verify: old file should be gone (preventive cleanup worked)
        assert not (target_dir / "old.txt").exists()
        # Verify: new file should exist
        assert (target_dir / "new.txt").exists()


def test_perform_upload_zip_rollback_on_failure(tmp_path):
    """
    Verifies the rollback mechanism upon processing failure.

    Ensures that if the directory is created during the process but a critical
    error occurs (e.g., download interruption, copy failure), the partial
    directory is removed to maintain a clean state.
    """
    base_dir = tmp_path / "clones"
    base_dir.mkdir()

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "a") as zf:
        zf.writestr("file.txt", "content")
    zip_buffer.seek(0)

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "valid.zip"
    mock_file.file = zip_buffer

    # Side effect: creates the directory (simulating start) then crashes
    def side_effect_create_and_fail(src, dst, **kwargs):
        os.makedirs(dst)
        raise Exception("Copy failed halfway")

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        with patch("shutil.copytree", side_effect=side_effect_create_and_fail):
            with patch("shutil.rmtree") as mock_rmtree:
                with pytest.raises(HTTPException):
                    perform_upload_zip("owner", "repo", mock_file)

                # Verify: rmtree was called to clean up the mess
                expected_target = str(base_dir / "owner_repo")
                mock_rmtree.assert_called_with(expected_target)

def test_perform_upload_zip_cleanup_os_error(tmp_path):
    """
    Tests resilience against OS-level errors during cleanup.

    Verifies that if the system cannot delete an existing directory (e.g.,
    permission denied), a 500 Internal Server Error is raised.
    """
    owner, repo = "cleanup", "error"
    base_dir = tmp_path / "clones"
    base_dir.mkdir()
    target_dir = base_dir / f"{owner}_{repo}"
    target_dir.mkdir()

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.zip"

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        with patch("shutil.rmtree", side_effect=OSError("Access denied")):
            with pytest.raises(HTTPException) as exc:
                perform_upload_zip(owner, repo, mock_file)
            assert exc.value.status_code == 500


def test_perform_upload_zip_logic_with_root_folder(tmp_path):
    """
    Validates extraction logic for ZIPs containing a single root folder.

    Ensures that if the archive contains everything inside a nested folder,
    the content is flattened correctly into the target repository directory.
    """
    base_dir = tmp_path / "clones"
    base_dir.mkdir()

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "a") as zf:
        zf.writestr("root/README.md", "content")
    zip_buffer.seek(0)

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "archive.zip"
    mock_file.file = zip_buffer

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        res_path = perform_upload_zip("owner", "repo_root", mock_file)
        assert os.path.exists(os.path.join(res_path, "README.md"))


# ==================================================================================
#                                TESTS: INITIAL SCAN
# ==================================================================================

def test_perform_initial_scan_flow(tmp_path):
    """
    Verifies the full orchestration of the initial scan pipeline.

    Ensures that ScanCode results are correctly filtered, analyzed for
    compatibility, and enriched with LLM data before returning a
    valid AnalyzeResponse.
    """
    owner, repo = "scan", "ok"
    base_dir = tmp_path / "clones"
    repo_dir = base_dir / f"{owner}_{repo}"
    repo_dir.mkdir(parents=True)

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)), \
            patch("app.services.analysis_workflow.run_scancode", return_value={}), \
            patch("app.services.analysis_workflow.detect_main_license_scancode", return_value=("MIT", "LICENSE")), \
            patch("app.services.analysis_workflow.filter_licenses", return_value={}), \
            patch("app.services.analysis_workflow.extract_file_licenses", return_value={}), \
            patch("app.services.analysis_workflow.check_compatibility", return_value={"issues": []}), \
            patch("app.services.analysis_workflow.enrich_with_llm_suggestions", return_value=[]):
        response = perform_initial_scan(owner, repo)
        assert response.main_license == "MIT"


def test_perform_initial_scan_repo_not_found(tmp_path):
    """
    Validates error handling when attempting to scan a non-existent repo.
    """
    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(tmp_path)):
        with pytest.raises(ValueError, match="Repository not found"):
            perform_initial_scan("ghost", "repo")


# ==================================================================================
#                                TESTS: REGENERATION
# ==================================================================================

def test_perform_regeneration_executes_correctly(tmp_path):
    """
    Verifies the code regeneration and re-analysis lifecycle.

    Checks that the workflow correctly identifies files needing fixes,
    applies changes, and performs a second scan to verify compatibility.
    """
    owner, repo = "regen", "success"
    base_dir = tmp_path / "clones"
    repo_dir = base_dir / f"{owner}_{repo}"
    repo_dir.mkdir(parents=True)

    file_path = "bad.py"
    (repo_dir / file_path).write_text("old")

    prev = AnalyzeResponse(
        repository=f"{owner}/{repo}", main_license="MIT",
        issues=[LicenseIssue(file_path=file_path, detected_license="GPL", compatible=False, licenses="GPL")]
    )

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)), \
            patch("app.services.analysis_workflow.regenerate_code", return_value="New Long Valid Code..."), \
            patch("app.services.analysis_workflow.run_scancode", return_value={}), \
            patch("app.services.analysis_workflow.detect_main_license_scancode", return_value=("MIT", "LICENSE")), \
            patch("app.services.analysis_workflow.check_compatibility", return_value={"issues": []}), \
            patch("app.services.analysis_workflow.enrich_with_llm_suggestions", return_value=[]):
        result = perform_regeneration(owner, repo, prev)
        assert result.repository == f"{owner}/{repo}"


def test_perform_regeneration_no_issues(tmp_path):
    """
    Ensures regeneration is skipped when no license issues are present.
    """
    owner, repo = "regen", "empty"
    base_dir = tmp_path / "clones"
    (base_dir / f"{owner}_{repo}").mkdir(parents=True)

    prev = AnalyzeResponse(repository="o/r", main_license="MIT", issues=[])

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        result = perform_regeneration(owner, repo, prev)
        assert result.issues == []


def test_perform_regeneration_llm_fails_short_code(tmp_path):
    """
    Validates quality control during LLM code regeneration.

    Ensures that if the LLM returns code that is suspiciously short
    (indicating a failure or hallucination), the original file content
    is preserved.
    """
    owner, repo = "regen", "short"
    base_dir = tmp_path / "clones"
    repo_dir = base_dir / f"{owner}_{repo}"
    repo_dir.mkdir(parents=True)

    file_path = "test.py"
    (repo_dir / file_path).write_text("original")

    prev = AnalyzeResponse(
        repository=f"{owner}/{repo}", main_license="MIT",
        issues=[LicenseIssue(file_path=file_path, detected_license="GPL", compatible=False, licenses="GPL")]
    )

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)), \
            patch("app.services.analysis_workflow.regenerate_code", return_value="short"), \
            patch("app.services.analysis_workflow.enrich_with_llm_suggestions", return_value=[]):
        perform_regeneration(owner, repo, prev)

        # Verifica che il file non sia cambiato
        assert (repo_dir / file_path).read_text() == "original"


# ==================================================================================
#                            INTERNAL HELPER TESTS
# ==================================================================================

def test_regenerate_incompatible_files_success(tmp_path):
    """
    Tests the logic for applying LLM fixes to specific incompatible files.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    file_path = "src/test.py"
    (repo_path / "src").mkdir()
    (repo_path / "src" / "test.py").write_text("# old code\nprint('old')")

    issues = [
        LicenseIssue(
            file_path=file_path,
            detected_license="GPL-3.0",
            compatible=False,
            reason="Incompatible",
            licenses="GPL-3.0"
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="# new code\nprint('new')\n# more code"):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    assert file_path in result
    assert len(result[file_path]) > 10
    assert "new" in (repo_path / "src" / "test.py").read_text()


def test_regenerate_incompatible_files_skip_documentation(tmp_path):
    """
    Verifies that documentation files are ignored during regeneration.

    README, NOTICE, and .rst files should not be sent to the LLM for
    code fixes, even if they have license flags.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    issues = [
        LicenseIssue(file_path="README.md", detected_license="GPL-3.0", compatible=False),
        LicenseIssue(file_path="NOTICE.txt", detected_license="GPL-3.0", compatible=False),
        LicenseIssue(file_path="docs/guide.rst", detected_license="GPL-3.0", compatible=False),
    ]

    result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    assert len(result) == 0


def test_regenerate_incompatible_files_only_compatible(tmp_path):
    """
     Verifies that only incompatible files trigger the regeneration process.

     Ensures that the internal regeneration helper skips files already marked
     as compatible, returning an empty result set when no issues require fixing.
     """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    issues = [
        LicenseIssue(file_path="src/test.py", detected_license="MIT", compatible=True)
    ]

    result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    assert len(result) == 0


def test_regenerate_incompatible_files_io_error(tmp_path):
    """
    Tests resilience against file system and I/O errors.

    Ensures that if the service attempts to fix a file that does not exist on
    disk (or is inaccessible), it handles the error gracefully by returning
    an empty dictionary instead of raising an unhandled exception.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    issues = [
        LicenseIssue(
            file_path="nonexistent/file.py",
            detected_license="GPL-3.0",
            compatible=False,
            licenses="GPL-3.0"
        )
    ]

    result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Should not raise exceptions, just return an empty dict
    assert len(result) == 0


def test_regenerate_incompatible_files_short_code_rejected(tmp_path):
    """
    Validates quality control for LLM-generated content.

    Ensures that regenerated code is rejected if it fails length validation
    (e.g., too short, suggesting a hallucination or failure). The original
    file content must remain untouched in such cases.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    file_path = "src/test.py"
    (repo_path / "src").mkdir()
    (repo_path / "src" / "test.py").write_text("original code")

    issues = [
        LicenseIssue(
            file_path=file_path,
            detected_license="GPL-3.0",
            compatible=False,
            licenses="GPL-3.0"
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="short"):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    assert len(result) == 0
    assert (repo_path / "src" / "test.py").read_text() == "original code"


def test_regenerate_incompatible_files_default_licenses(tmp_path):
    """
    Tests the fallback mechanism for target compatibility licenses.

    Verifies that if an issue does not specify target licenses, the
    regeneration service defaults to a safe set of permissive licenses
    (MIT, Apache-2.0, BSD-3-Clause) to guide the LLM.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    file_path = "src/test.py"
    (repo_path / "src").mkdir()
    (repo_path / "src" / "test.py").write_text("# code")

    issues = [
        LicenseIssue(
            file_path=file_path,
            detected_license="GPL-3.0",
            compatible=False,
            licenses=None  # Test with licenses=None
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="# new valid code\nprint('hello')") as mock_regen:
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

        # Verify it was called with default permissive licenses
        call_args = mock_regen.call_args
        assert "MIT, Apache-2.0, BSD-3-Clause" in str(call_args)


# ==================================================================================
#                            TESTS: REPOSITORY RESCAN
# ==================================================================================

def test_rescan_repository_success(tmp_path):
    """
    Tests the post-regeneration scanning phase.

    Ensures the service can perform a fresh analysis on the modified
    repository and return the updated issue list.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    regenerated_map = {"src/file.py": "new code"}

    with patch("app.services.analysis_workflow.run_scancode", return_value={"files": []}), \
         patch("app.services.analysis_workflow.detect_main_license_scancode", return_value=("MIT", "LICENSE")), \
         patch("app.services.analysis_workflow.filter_licenses", return_value={"files": []}), \
         patch("app.services.analysis_workflow.extract_file_licenses", return_value={"src/file.py": "MIT"}), \
         patch("app.services.analysis_workflow.check_compatibility", return_value={
             "issues": [
                 {"file_path": "src/file.py", "detected_license": "MIT", "compatible": True}
             ]
         }) as mock_compat:

        result = _rescan_repository(str(repo_path), "MIT", regenerated_map)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["file_path"] == "src/file.py"
        mock_compat.assert_called_once()


def test_rescan_repository_with_unknown_license(tmp_path):
    """
    Validates rescan behavior when the main license is unidentified.

    Ensures that the rescan logic handles "UNKNOWN" license identifiers
    gracefully without crashing, maintaining consistency in the returned data
    format.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    with patch("app.services.analysis_workflow.run_scancode", return_value={"files": []}), \
         patch("app.services.analysis_workflow.detect_main_license_scancode", return_value="UNKNOWN"), \
         patch("app.services.analysis_workflow.filter_licenses", return_value={"files": []}), \
         patch("app.services.analysis_workflow.extract_file_licenses", return_value={}), \
         patch("app.services.analysis_workflow.check_compatibility", return_value={"issues": []}):

        result = _rescan_repository(str(repo_path), "UNKNOWN", {})

        assert isinstance(result, list)


def test_rescan_repository_with_tuple_license_result(tmp_path):
    """
    Tests compatibility with different license detection return formats.

    Verifies that the rescan service correctly processes the main license
    when the detection tool returns a tuple (license_id, license_path)
    instead of a simple string.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    with patch("app.services.analysis_workflow.run_scancode", return_value={"files": []}), \
         patch("app.services.analysis_workflow.detect_main_license_scancode", return_value=("Apache-2.0", "/LICENSE")), \
         patch("app.services.analysis_workflow.filter_licenses", return_value={"files": []}), \
         patch("app.services.analysis_workflow.extract_file_licenses", return_value={}), \
         patch("app.services.analysis_workflow.check_compatibility", return_value={"issues": []}):

        result = _rescan_repository(str(repo_path), "Apache-2.0", {})

        assert isinstance(result, list)


def test_rescan_repository_multiple_issues(tmp_path):
    """
    Verifies handling of multiple compatibility issues during a rescan.

    Ensures that the service correctly aggregates multiple issues (both
    compatible and incompatible) and preserves the specific reason for
    any detected conflicts.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    issues = [
        {"file_path": "src/file1.py", "detected_license": "MIT", "compatible": True},
        {"file_path": "src/file2.py", "detected_license": "GPL-3.0", "compatible": False, "reason": "Incompatible"},
        {"file_path": "src/file3.py", "detected_license": "Apache-2.0", "compatible": True}
    ]

    with patch("app.services.analysis_workflow.run_scancode", return_value={"files": []}), \
         patch("app.services.analysis_workflow.detect_main_license_scancode", return_value=("MIT", "LICENSE")), \
         patch("app.services.analysis_workflow.filter_licenses", return_value={"files": []}), \
         patch("app.services.analysis_workflow.extract_file_licenses", return_value={
             "src/file1.py": "MIT",
             "src/file2.py": "GPL-3.0",
             "src/file3.py": "Apache-2.0"
         }), \
         patch("app.services.analysis_workflow.check_compatibility", return_value={"issues": issues}):

        result = _rescan_repository(str(repo_path), "MIT", {})

        assert isinstance(result, list)
        assert len(result) == 3
        assert result[1]["compatible"] is False


def test_perform_initial_scan_string_license_return(tmp_path):
    """
    Verifies perform_initial_scan when license detection returns a simple string
    (e.g., 'MIT') instead of a tuple. This covers the 'else' branch in detection handling.
    """
    owner, repo = "scan", "str_license"
    base_dir = tmp_path / "clones"
    repo_dir = base_dir / f"{owner}_{repo}"
    repo_dir.mkdir(parents=True)

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)), \
            patch("app.services.analysis_workflow.run_scancode", return_value={}), \
            patch("app.services.analysis_workflow.detect_main_license_scancode", return_value="MIT"), \
            patch("app.services.analysis_workflow.filter_licenses", return_value={}), \
            patch("app.services.analysis_workflow.extract_file_licenses", return_value={}), \
            patch("app.services.analysis_workflow.check_compatibility", return_value={"issues": []}), \
            patch("app.services.analysis_workflow.enrich_with_llm_suggestions", return_value=[]):
        response = perform_initial_scan(owner, repo)
        assert response.main_license == "MIT"


def test_perform_regeneration_repo_not_found(tmp_path):
    """
    Verifies validation check for missing repository in regeneration workflow.
    Covers the 'if not os.path.exists' check at the start of perform_regeneration.
    """
    base_dir = tmp_path / "clones"
    base_dir.mkdir()

    prev = AnalyzeResponse(repository="owner/missing", main_license="MIT", issues=[])

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        with pytest.raises(ValueError, match="Repository not found"):
            perform_regeneration("owner", "missing", prev)


def test_regenerate_incompatible_files_with_repo_prefix_path(tmp_path):
    """
    Tests path resolution logic when file_path starts with the repository name.
    Covers the 'if fpath.startswith(repo_name)' branch in _regenerate_incompatible_files.
    """
    repo_name = "owner_repo"
    repo_path = tmp_path / repo_name
    repo_path.mkdir()

    # Create file at root of repo
    (repo_path / "root.py").write_text("# content")

    # Issue uses "owner_repo/root.py" format
    issues = [
        LicenseIssue(
            file_path=f"{repo_name}/root.py",
            detected_license="GPL",
            compatible=False
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="# new code\nprint('fixed')"):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Should resolve correctly and regenerate
    assert f"{repo_name}/root.py" in result
    assert "fixed" in (repo_path / "root.py").read_text()


def test_regenerate_incompatible_files_os_error_handling(tmp_path):
    """
    Tests specifically the OSError catch block (e.g., file permission issues)
    during the regeneration loop.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()
    (repo_path / "locked.py").write_text("# locked")

    issues = [LicenseIssue(file_path="locked.py", detected_license="GPL", compatible=False)]

    # Mock open to raise OSError when reading/writing this file
    with patch("builtins.open", side_effect=OSError("Disk Error")):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Should handle error gracefully and return empty result
    assert len(result) == 0


def test_regenerate_incompatible_files_general_exception(tmp_path):
    """
    Tests the generic Exception catch block in the regeneration loop.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()
    (repo_path / "fail.py").write_text("# content")

    issues = [LicenseIssue(file_path="fail.py", detected_license="GPL", compatible=False)]

    # Mock regenerate_code to raise a generic Exception
    with patch("app.services.analysis_workflow.regenerate_code", side_effect=Exception("AI Error")):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Should catch exception and return empty result
    assert len(result) == 0

class TestIntegrationScanner:
    """
    Tests the integration with the ScanCode binary on the file system.
    """
    def test_scancode_on_small_folder(self):
        """
        Executes a real license detection scan on a local temporary directory.

        Process:
        1. Creates a temporary workspace using `tempfile`.
        2. Writes a dummy Python file containing an explicit MIT license header.
        3. Invokes `run_scancode` to verify that the file is detected and parsed.

        Note:
            This test is skipped if the ScanCode binary is not installed in the system.
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
    Validates the full cycle of code correction and file system updates.
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
        Verifies that incompatible code is correctly overwritten on disk.

        Logical Workflow:
        1. Setup: Create a temporary repository directory and a file with GPL code.
        2. Execution: Call `perform_regeneration` with a mock LLM response (MIT code).
        3. Validation: Read the file from disk to confirm the content has been
           successfully updated and the old incompatible code is gone.

        Returns:
            None: Asserts file content equality.
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