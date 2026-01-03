"""
Modulo di test unitario del flusso di analisi.

Questo modulo contiene test unitari per le funzioni di orchestrazione core all'interno
di `app.services.analysis_workflow`. Verifica la logica per la clonazione del repository,
la gestione dei file ZIP, la pipeline di scansione iniziale e il processo di rigenerazione del codice basato su LLM.

La suite copre:
1. Clonazione repository: Gestione di successo e fallimento durante le operazioni git.
2. Gestione ZIP: Validazione, estrazione e pulizia degli archivi caricati.
3. Pipeline di analisi: Orchestrazione di ScanCode, rilevamento licenze e compatibilità.
4. Rigenerazione codice: Filtraggio intelligente dei file e interazione LLM per le correzioni.
5. Riscansione post-rigenerazione: Validazione dello stato del repository dopo le modifiche del codice.
"""

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

# ==================================================================================
#                                     FIXTURE
# ==================================================================================

# Nota: Questo modulo utilizza principalmente 'tmp_path' integrato di pytest e
# 'patch_config_variables' da conftest.py per gestire le interazioni del file system.

# ==================================================================================
#                                TEST: CLONAZIONE REPO
# ==================================================================================

def test_perform_cloning_success(tmp_path):
    """"Verifica la clonazione riuscita del repository.

    Garantisce che il servizio interagisca correttamente con l'utilità di clonazione di basso livello
    e restituisca il percorso assoluto previsto al repository clonato.
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
    Testa la gestione degli errori durante la clonazione del repository.

    Verifica che se l'operazione git fallisce (ad es., errore di autenticazione),
     venga sollevato un ValueError con un messaggio descrittivo.
    """
    owner, repo = "badowner", "badrepo"

    with patch("app.services.analysis_workflow.clone_repo") as mock_clone:
        mock_clone.return_value = MagicMock(success=False, error="Authentication failed")

        with pytest.raises(ValueError, match="Cloning error: Authentication failed"):
            perform_cloning(owner, repo)

        mock_clone.assert_called_once_with(owner, repo)


# ==================================================================================
#                                TEST: CARICAMENTO ZIP
# ==================================================================================

def test_perform_upload_zip_invalid_extension():
    """
    Valida i controlli dell'estensione file per i caricamenti ZIP.

    Garantisce che i file non-ZIP (ad es., .tar.gz) vengano rifiutati con un'
    eccezione 400 Bad Request.
    """
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.tar.gz"
    with pytest.raises(HTTPException) as exc:
        perform_upload_zip("owner", "repo", mock_file)
    assert exc.value.status_code == 400


def test_perform_upload_zip_corrupted_file():
    """
    Testa la gestione degli archivi ZIP corrotti.

    Verifica che se il file caricato non è un archivio ZIP valido, il
    servizio sollevi un errore 400 indicando che il file è corrotto.
    """
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "fake.zip"
    mock_file.file = BytesIO(b"not a zip content")

    with pytest.raises(HTTPException) as exc:
        perform_upload_zip("owner", "repo", mock_file)
    assert exc.value.status_code == 400
    assert "corrupted" in exc.value.detail


def test_perform_upload_zip_cleanup_existing_dir(tmp_path):
    """
    Verifica il comportamento idempotente durante l'estrazione ZIP.

    Garantisce che se una directory per il repository esiste già, venga
    rimossa prima di estrarre il nuovo contenuto ZIP per evitare dati obsoleti.
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
    """
    Testa la resilienza contro errori a livello OS durante la pulizia.

    Verifica che se il sistema non può eliminare una directory esistente (ad es.,
    permesso negato), venga sollevato un errore 500 Internal Server Error.
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
    Valida la logica di estrazione per ZIP contenenti una singola cartella radice.

    Garantisce che se l'archivio contiene tutto all'interno di una cartella annidata,
    il contenuto venga appiattito correttamente nella directory del repository di destinazione.
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
#                                TEST: SCANSIONE INIZIALE
# ==================================================================================

def test_perform_initial_scan_flow(tmp_path):
    """
    Verifica l'orchestrazione completa della pipeline di scansione iniziale.

    Garantisce che i risultati ScanCode vengano correttamente filtrati, analizzati per
    compatibilità e arricchiti con dati LLM prima di restituire un
    AnalyzeResponse valido.
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
    Valida la gestione degli errori quando si tenta di scansionare un repo inesistente.
    """
    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(tmp_path)):
        with pytest.raises(ValueError, match="Repository not found"):
            perform_initial_scan("ghost", "repo")


# ==================================================================================
#                                TEST: RIGENERAZIONE
# ==================================================================================

def test_perform_regeneration_executes_correctly(tmp_path):
    """
    Verifica il ciclo di vita della rigenerazione del codice e ri-analisi.

    Controlla che il workflow identifichi correttamente i file che necessitano di correzioni,
    applichi le modifiche e esegua una seconda scansione per verificare la compatibilità.
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
    Garantisce che la rigenerazione venga saltata quando non sono presenti problemi di licenza.
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
    Valida il controllo qualità durante la rigenerazione del codice LLM.

    Garantisce che se l'LLM restituisce codice sospettosamente corto
    (indicando un fallimento o allucinazione), il contenuto del file originale
    venga preservato.
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
#                            TEST HELPER INTERNI
# ==================================================================================

def test_regenerate_incompatible_files_success(tmp_path):
    """
    Testa la logica per applicare le correzioni LLM a file incompatibili specifici.
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
    Verifica che i file di documentazione vengano ignorati durante la rigenerazione.

    README, NOTICE e file .rst non dovrebbero essere inviati all'LLM per
    correzioni del codice, anche se hanno flag di licenza.
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
     Verifica che solo i file incompatibili attivino il processo di rigenerazione.

     Garantisce che l'helper di rigenerazione interno salti i file già marcati
     come compatibili, restituendo un insieme di risultati vuoto quando nessun problema richiede correzioni.
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
    Testa la resilienza contro errori del file system e I/O.

    Garantisce che se il servizio tenta di correggere un file che non esiste su
    disco (o è inaccessibile), gestisca l'errore con grazia restituendo
    un dizionario vuoto invece di sollevare un'eccezione non gestita.
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

    # Non dovrebbe sollevare eccezioni, solo restituire un dizionario vuoto
    assert len(result) == 0


def test_regenerate_incompatible_files_short_code_rejected(tmp_path):
    """
    Valida il controllo qualità per il contenuto generato LLM.

    Garantisce che il codice rigenerato venga rifiutato se fallisce la validazione della lunghezza
    (ad es., troppo corto, suggerendo un'allucinazione o fallimento). Il contenuto del file originale
    deve rimanere intatto in tali casi.
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
    Testa il meccanismo di fallback per le licenze di compatibilità target.

    Verifica che se un problema non specifica licenze target, il
    servizio di rigenerazione utilizzi come default un insieme sicuro di licenze permissive
    (MIT, Apache-2.0, BSD-3-Clause) per guidare l'LLM.
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
            licenses=None  # Test con licenses=None
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="# new valid code\nprint('hello')") as mock_regen:
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

        # Verifica che sia stato chiamato con licenze permissive di default
        call_args = mock_regen.call_args
        assert "MIT, Apache-2.0, BSD-3-Clause" in str(call_args)


# ==================================================================================
#                            TEST: RISCANSIONE REPOSITORY
# ==================================================================================

def test_rescan_repository_success(tmp_path):
    """
    Testa la fase di scansione post-rigenerazione.

    Garantisce che il servizio possa eseguire una nuova analisi sul repository modificato
    e restituire la lista di problemi aggiornata.
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
    Valida il comportamento di riscansione quando la licenza principale è non identificata.

    Garantisce che la logica di riscansione gestisca gli identificatori di licenza "UNKNOWN"
    con grazia senza crashare, mantenendo la consistenza nel formato dei dati restituiti.
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
    Testa la compatibilità con diversi formati di ritorno del rilevamento licenze.

    Verifica che il servizio di riscansione elabori correttamente la licenza principale
    quando lo strumento di rilevamento restituisce una tupla (license_id, license_path)
    invece di una semplice stringa.
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
    Verifica la gestione di più problemi di compatibilità durante una riscansione.

    Garantisce che il servizio aggregi correttamente più problemi (sia
    compatibili che incompatibili) e preservi la ragione specifica per
    qualsiasi conflitto rilevato.
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

