import os
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


# --- TESTS PER PERFORM_CLONING ---

# --- TESTS PER PERFORM_UPLOAD_ZIP ---

def test_perform_upload_zip_invalid_extension():
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.tar.gz"
    with pytest.raises(HTTPException) as exc:
        perform_upload_zip("owner", "repo", mock_file)
    assert exc.value.status_code == 400


def test_perform_upload_zip_corrupted_file():
    # Nota: non usiamo patch_config_variables se non serve esplicitamente,
    # ma se serve per CLONE_BASE_DIR, assicurati che la fixture sia in conftest.py
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "fake.zip"
    mock_file.file = BytesIO(b"not a zip content")

    with pytest.raises(HTTPException) as exc:
        perform_upload_zip("owner", "repo", mock_file)
    assert exc.value.status_code == 400
    assert "corrupted" in exc.value.detail


def test_perform_upload_zip_cleanup_existing_dir(tmp_path):
    """
    Usa tmp_path di pytest per evitare dipendenze globali.
    Patchiamo CLONE_BASE_DIR per puntare a una directory temporanea.
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

        assert not (target_dir / "old.txt").exists()
        assert (target_dir / "new.txt").exists()


def test_perform_upload_zip_cleanup_os_error(tmp_path):
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


# --- TESTS PER PERFORM_INITIAL_SCAN ---

def test_perform_initial_scan_flow(tmp_path):
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
    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(tmp_path)):
        with pytest.raises(ValueError, match="Repository not found"):
            perform_initial_scan("ghost", "repo")


# --- TESTS PER PERFORM_REGENERATION ---

def test_perform_regeneration_executes_correctly(tmp_path):
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
    owner, repo = "regen", "empty"
    base_dir = tmp_path / "clones"
    (base_dir / f"{owner}_{repo}").mkdir(parents=True)

    prev = AnalyzeResponse(repository="o/r", main_license="MIT", issues=[])

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        result = perform_regeneration(owner, repo, prev)
        assert result.issues == []


def test_perform_regeneration_llm_fails_short_code(tmp_path):
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


# --- TESTS PER _REGENERATE_INCOMPATIBLE_FILES ---

def test_regenerate_incompatible_files_success(tmp_path):
    """Test _regenerate_incompatible_files con rigenerazione di successo."""
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
    """Test _regenerate_incompatible_files ignora file di documentazione."""
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
    """Test _regenerate_incompatible_files con solo file compatibili."""
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()

    issues = [
        LicenseIssue(file_path="src/test.py", detected_license="MIT", compatible=True)
    ]

    result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    assert len(result) == 0


def test_regenerate_incompatible_files_io_error(tmp_path):
    """Test _regenerate_incompatible_files gestisce errori IO."""
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

    # Non deve sollevare eccezioni, ma restituire dict vuoto
    assert len(result) == 0


def test_regenerate_incompatible_files_short_code_rejected(tmp_path):
    """Test _regenerate_incompatible_files rifiuta codice troppo corto."""
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
    """Test _regenerate_incompatible_files usa licenze di default se None."""
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
            licenses=None  # Test con licenses=None
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="# new valid code\nprint('hello')") as mock_regen:
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

        # Verifica che sia stata chiamata con le licenze di default
        call_args = mock_regen.call_args
        assert "MIT, Apache-2.0, BSD-3-Clause" in str(call_args)


# --- TESTS PER _RESCAN_REPOSITORY ---

def test_rescan_repository_success(tmp_path):
    """Test _rescan_repository esegue correttamente la scansione."""
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
    """Test _rescan_repository gestisce licenza UNKNOWN."""
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
    """Test _rescan_repository con risultato tupla da detect_main_license."""
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
    """Test _rescan_repository con multipli problemi di compatibilità."""
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

