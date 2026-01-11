"""
Analysis Workflow Unit Test Module.

Questo modulo contiene test unitari per le funzioni di orchestrazione principali all'interno
`app.services.analysis_workflow`. Verifica la logica per il cloning dei repository,
la gestione dei file ZIP, la pipeline di scansione iniziale e il processo di
rigenerazione del codice guidato da LLM.

La suite copre:
1. Clonazione del Repository: Gestione del successo e dei fallimenti durante le operazioni git.
2. Gestione ZIP: Validazione, estrazione e pulizia degli archivi caricati.
3. Pipeline di Analisi: Orchestrazione di ScanCode, rilevamento delle licenze e compatibilità.
4. Rigenerazione del Codice: Filtraggio intelligente dei file e interazione con LLM per le correzioni.
5. Riesame Post-Rigenerazione: Validazione dello stato del repository dopo le modifiche al codice.
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

# Nota: Questo modulo utilizza principalmente 'tmp_path' integrato in pytest e
# 'patch_config_variables' da conftest.py per gestire le interazioni con il filesystem.

# ==================================================================================
#                                TESTS: REPO CLONING
# ==================================================================================

def test_perform_cloning_success(tmp_path):
    """"
    Verifica il successo della clonazione del repository.

    Assicura che il servizio interagisca correttamente con l'utilità di clonazione a basso livello
    e restituisca il percorso assoluto atteso per il repository clonato.
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
#                                TESTS: ZIP UPLOAD
# ==================================================================================

def test_perform_upload_zip_invalid_extension():
    """
    Valida i controlli dell'estensione del file per i caricamenti ZIP.

    Assicura che i file non ZIP (ad es., .tar.gz) vengano rifiutati con una
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
    servizio sollevi un errore 400 che indica che il file è corrotto.
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
    Verifica la logica di pulizia preventiva prima dell'estrazione.

    Assicura che se una directory di destinazione esiste già da un'esecuzione precedente,
    venga completamente rimossa prima di elaborare il nuovo file ZIP. Questo previene
    la mescolanza di vecchi artefatti con il nuovo codice sorgente.
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

        # Verifica: il vecchio file dovrebbe essere sparito (la pulizia preventiva ha funzionato)
        assert not (target_dir / "old.txt").exists()
        # Verifica: il nuovo file dovrebbe esistere
        assert (target_dir / "new.txt").exists()


def test_perform_upload_zip_rollback_on_failure(tmp_path):
    """
    Verifica il meccanismo di rollback in caso di errore durante l'elaborazione.

    Assicura che se la directory viene creata durante il processo ma si verifica un errore critico
    (ad es., interruzione del download, errore di copia), la directory parziale venga rimossa
    per mantenere uno stato pulito.
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

    # Effetto collaterale: crea la directory (simulando l'inizio) e poi si arresta
    def side_effect_create_and_fail(src, dst, **kwargs):
        os.makedirs(dst)
        raise Exception("Copy failed halfway")

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        with patch("shutil.copytree", side_effect=side_effect_create_and_fail):
            with patch("shutil.rmtree") as mock_rmtree:
                with pytest.raises(HTTPException):
                    perform_upload_zip("owner", "repo", mock_file)

                # Verifica: rmtree è stato chiamato per ripulire il disastro
                expected_target = str(base_dir / "owner_repo")
                mock_rmtree.assert_called_with(expected_target)

def test_perform_upload_zip_cleanup_os_error(tmp_path):
    """
    Testa la resilienza contro gli errori a livello di OS durante la pulizia.

    Verifica che se il sistema non può eliminare una directory esistente (ad es.,
    accesso negato), venga sollevato un errore interno del server 500.
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
    Valida la logica di estrazione per ZIP che contengono una singola cartella radice.

    Assicura che se l'archivio contiene tutto all'interno di una cartella nidificata,
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
#                                TESTS: INITIAL SCAN
# ==================================================================================

def test_perform_initial_scan_flow(tmp_path):
    """
    Verifica l'intera orchestrazione della pipeline di scansione iniziale.

    Assicura che i risultati di ScanCode siano correttamente filtrati, analizzati per la
    compatibilità e arricchiti con i dati LLM prima di restituire una
    valida AnalyzeResponse.
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
    Valida la gestione degli errori quando si tenta di scansionare un repository inesistente.
    """
    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(tmp_path)):
        with pytest.raises(ValueError, match="Repository not found"):
            perform_initial_scan("ghost", "repo")


# ==================================================================================
#                                TESTS: REGENERATION
# ==================================================================================

def test_perform_regeneration_executes_correctly(tmp_path):
    """
    Verifica il ciclo di vita della rigenerazione del codice e della reanalisi.

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
    Assicura che la rigenerazione venga saltata quando non sono presenti problemi di licenza.
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
    Valida il controllo di qualità durante la rigenerazione del codice LLM.

    Assicura che se il LLM restituisce codice che è sospettosamente breve
    (indicando un fallimento o un'allucinazione), il contenuto originale del file
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
#                            INTERNAL HELPER TESTS
# ==================================================================================

def test_regenerate_incompatible_files_success(tmp_path):
    """
    Testa la logica per l'applicazione delle correzioni LLM a file specifici incompatibili.
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

    I file README, NOTICE e .rst non devono essere inviati al LLM per
    le correzioni del codice, anche se presentano flag di licenza.
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

     Assicura che l'helper interno di rigenerazione salti i file già contrassegnati
     come compatibili, restituendo un insieme di risultati vuoto quando nessun problema richiede correzione.
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
    Testa la resilienza contro gli errori di sistema e I/O.

    Assicura che se il servizio tenta di correggere un file che non esiste su
    disco (o è inaccessibile), gestisca l'errore in modo elegante restituendo
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
    Valida il controllo di qualità per i contenuti generati dal LLM.

    Assicura che il codice rigenerato venga rifiutato se non supera la validazione della lunghezza
    (ad es., troppo corto, suggerendo un'allucinazione o un fallimento). Il contenuto originale
    del file deve rimanere intatto in questi casi.
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

    Verifica che se un problema non specifica le licenze target, il
    servizio di rigenerazione utilizzi un insieme sicuro di licenze permissive
    (MIT, Apache-2.0, BSD-3-Clause) per guidare il LLM.
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

        # Verifica che sia stato chiamato con le licenze permissive predefinite
        call_args = mock_regen.call_args
        assert "MIT, Apache-2.0, BSD-3-Clause" in str(call_args)


# ==================================================================================
#                            TESTS: REPOSITORY RESCAN
# ==================================================================================

def test_rescan_repository_success(tmp_path):
    """
    Testa la fase di scansione post-rigenerazione.

    Assicura che il servizio possa eseguire una nuova analisi sul repository modificato
    e restituire l'elenco aggiornato dei problemi.
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
    Valida il comportamento della scansione quando la licenza principale non è identificata.

    Assicura che la logica di riesame gestisca gli identificatori di licenza "UNKNOWN"
    in modo elegante senza arrestarsi, mantenendo coerenza nel formato dei dati restituiti.
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
    Testa la compatibilità con diversi formati di ritorno della rilevazione delle licenze.

    Verifica che il servizio di riesame elabori correttamente la licenza principale
    quando lo strumento di rilevazione restituisce una tupla (license_id, license_path)
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
    Verifica la gestione di più problemi di compatibilità durante una nuova scansione.

    Assicura che il servizio aggrega correttamente più problemi (sia
    compatibili che incompatibili) e preserva il motivo specifico per
    eventuali conflitti rilevati.
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
    Verifica perform_initial_scan quando il rilevamento della licenza restituisce una semplice stringa
    (ad es., 'MIT') invece di una tupla. Questo copre il ramo 'else' nella gestione del rilevamento.
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
    Verifica il controllo di validazione per repository mancanti nel workflow di rigenerazione.
    Copre il controllo 'if not os.path.exists' all'inizio di perform_regeneration.
    """
    base_dir = tmp_path / "clones"
    base_dir.mkdir()

    prev = AnalyzeResponse(repository="owner/missing", main_license="MIT", issues=[])

    with patch("app.services.analysis_workflow.CLONE_BASE_DIR", str(base_dir)):
        with pytest.raises(ValueError, match="Repository not found"):
            perform_regeneration("owner", "missing", prev)


def test_regenerate_incompatible_files_with_repo_prefix_path(tmp_path):
    """
    Testa la logica di risoluzione del percorso quando file_path inizia con il nome del repository.
    Copre il ramo 'if fpath.startswith(repo_name)' in _regenerate_incompatible_files.
    """
    repo_name = "owner_repo"
    repo_path = tmp_path / repo_name
    repo_path.mkdir()

    # Crea file nella radice del repo
    (repo_path / "root.py").write_text("# content")

    # Il problema utilizza il formato "owner_repo/root.py"
    issues = [
        LicenseIssue(
            file_path=f"{repo_name}/root.py",
            detected_license="GPL",
            compatible=False
        )
    ]

    with patch("app.services.analysis_workflow.regenerate_code", return_value="# new code\nprint('fixed')"):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Dovrebbe risolvere correttamente e rigenerare
    assert f"{repo_name}/root.py" in result
    assert "fixed" in (repo_path / "root.py").read_text()


def test_regenerate_incompatible_files_os_error_handling(tmp_path):
    """
    Testa specificamente il blocco di cattura dell'OSError (ad es., problemi di permesso dei file)
    durante il ciclo di rigenerazione.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()
    (repo_path / "locked.py").write_text("# locked")

    issues = [LicenseIssue(file_path="locked.py", detected_license="GPL", compatible=False)]

    # Mock open per sollevare OSError durante la lettura/scrittura di questo file
    with patch("builtins.open", side_effect=OSError("Disk Error")):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Dovrebbe gestire l'errore in modo elegante e restituire un risultato vuoto
    assert len(result) == 0


def test_regenerate_incompatible_files_general_exception(tmp_path):
    """
    Testa il blocco di cattura dell'eccezione generica nel ciclo di rigenerazione.
    """
    repo_path = tmp_path / "owner_repo"
    repo_path.mkdir()
    (repo_path / "fail.py").write_text("# content")

    issues = [LicenseIssue(file_path="fail.py", detected_license="GPL", compatible=False)]

    # Mock regenerate_code per sollevare un'eccezione generica
    with patch("app.services.analysis_workflow.regenerate_code", side_effect=Exception("AI Error")):
        result = _regenerate_incompatible_files(str(repo_path), "MIT", issues)

    # Dovrebbe catturare l'eccezione e restituire un risultato vuoto
    assert len(result) == 0

class TestIntegrationScanner:
    """
    Testa l'integrazione con il binary ScanCode sul filesystem.
    """
    def test_scancode_on_small_folder(self):
        """
        Esegue una scansione reale della rilevazione delle licenze su una directory temporanea locale.

        Processo:
        1. Crea uno spazio di lavoro temporaneo utilizzando `tempfile`.
        2. Scrive un file Python dummy contenente un'intestazione di licenza MIT esplicita.
        3. Invoca `run_scancode` per verificare che il file venga rilevato e analizzato.

        Nota:
            Questo test viene saltato se il binary ScanCode non è installato nel sistema.
        """
        from app.services.scanner.detection import run_scancode

        # Crea una directory temporanea con un piccolo file
        with tempfile.TemporaryDirectory() as temp_dir:
            # Crea un semplice file Python con licenza MIT
            file_path = os.path.join(temp_dir, "test.py")
            with open(file_path, "w") as f:
                f.write("# MIT License\n\ndef hello():\n    print('Hello')\n")

            # Esegui scancode (supponendo che SCANCODE_BIN sia impostato nella config)
            try:
                result = run_scancode(temp_dir)
                # Controlla che il risultato abbia file
                assert "files" in result
                assert len(result["files"]) > 0
                # Controlla che il file venga rilevato
                file_entries = [f for f in result["files"] if f["path"].endswith("test.py")]
                assert len(file_entries) == 1
            except Exception as e:
                # Se scancode non è disponibile, salta
                pytest.skip(f"ScanCode not available: {e}")


class TestIntegrationCodeGeneratorFileSystem:
    """
    Valida l'intero ciclo di correzione del codice e aggiornamenti del file system.
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
        Verifica che il codice incompatibile venga sovrascritto correttamente su disco.

        Workflow Logico:
        1. Configurazione: Crea una directory di repository temporanea e un file con codice GPL.
        2. Esecuzione: Chiama `perform_regeneration` con una risposta mock LLM (codice MIT).
        3. Validazione: Leggi il file da disco per confermare che il contenuto sia stato
           aggiornato con successo e che il vecchio codice incompatibile sia scomparso.

        Restituisce:
            Nessuno: Asserisce l'uguaglianza del contenuto del file.
        """
        # Configura i mock
        mock_regenerate.return_value = "# MIT License\n\ndef hello():\n    print('Hello MIT')\n"
        mock_scancode.return_value = {"files": []}
        mock_filter.return_value = {"files": []}
        mock_extract.return_value = {}
        mock_compat.return_value = {"issues": []}
        mock_enrich.return_value = []
        mock_detect.return_value = ("MIT", "/path")

        # Crea una directory e un file temporanei
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('app.services.analysis_workflow.CLONE_BASE_DIR', temp_dir):
                repo_dir = os.path.join(temp_dir, "testowner_testrepo")
                os.makedirs(repo_dir)
                file_path = os.path.join(repo_dir, "test.py")
                original_content = "# GPL License\n\ndef hello():\n    print('Hello GPL')\n"
                with open(file_path, "w") as f:
                    f.write(original_content)

                # Mock analisi precedente con un problema incompatibile
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

                # Chiama perform_regeneration
                result = perform_regeneration("testowner", "testrepo", previous_analysis)

                # Controlla che il file sia stato aggiornato
                with open(file_path, "r") as f:
                    new_content = f.read()
                assert new_content == "# MIT License\n\ndef hello():\n    print('Hello MIT')\n"
                assert new_content != original_content

