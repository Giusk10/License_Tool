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
    perform_regeneration
)
from app.models.schemas import AnalyzeResponse, LicenseIssue


# --- TESTS PER PERFORM_CLONING ---

def test_perform_cloning_success():
    with patch("app.services.analysis_workflow.clone_repo") as mock_clone:
        mock_clone.return_value = MagicMock(success=True, repo_path="/tmp/test_repo")
        path = perform_cloning("owner", "repo", "token")
        assert path == "/tmp/test_repo"


def test_perform_cloning_failure():
    """
    Testa che venga sollevato un ValueError se la clonazione fallisce.
    Il match controlla che il messaggio contenga 'Repo not found'.
    """
    with patch("app.services.analysis_workflow.clone_repo") as mock_clone:
        mock_clone.return_value = MagicMock(success=False, error="Repo not found")
        # Usiamo un match parziale per evitare errori su spazi/prefissi
        with pytest.raises(ValueError, match="Repo not found"):
            perform_cloning("owner", "repo", "token")


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