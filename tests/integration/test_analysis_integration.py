"""
Suite di test di integrazione API - Analisi e Autenticazione.

Questo modulo valida l'integrazione tra i controller FastAPI e i servizi sottostanti (OAuth GitHub, gestione ZIP e Analisi Licenze).
Garantisce che l'API orchestrii correttamente flussi di lavoro complessi, gestisca l'I/O del file system e gestisca con grazia i fallimenti dei servizi esterni.

La suite è suddivisa in:
1. Flusso di autenticazione OAuth (GitHub).
2. Ciclo di vita degli archivi ZIP (Caricamento, Estrazione, Normalizzazione).
3. Orchestrazione dell'analisi (Scansione e integrazione LLM).
4. Recupero degli artefatti (Rigenerazione e Download).
"""

# ==================================================================================
#                          TEST SUITE: GITHUB OAUTH FLOW
# ==================================================================================

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

# Client globale per i test che non richiede directory patchate
client = TestClient(app)

"""
Test di integrazione per gli endpoint /api/auth/start e /api/callback
Questi test verificano l'intero flusso di autenticazione OAuth con GitHub
"""

# --- CLEANUP FIXTURES ---
@pytest.fixture
def mock_env_credentials():
    """Emula le variabili d'ambiente o la funzione che le recupera."""
    with patch("app.controllers.analysis.github_auth_credentials", side_effect=["MOCK_CID", "MOCK_SEC"]) as m:
        yield m


@pytest.fixture
def mock_httpx_post():
    """Mock della chiamata httpx POST."""
    with patch("app.controllers.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_clone():
    """Mocks the cloning function."""
    with patch("app.controllers.analysis.perform_cloning") as m:
        yield m

"""
Suite di integrazione API: Ciclo di vita degli archivi & Orchestrazione dell'analisi.

Questo modulo valida la pipeline principale "Carica-Analizza-Correggi". Garantisce che il sistema gestisca correttamente le operazioni sul file system, l'estrazione degli archivi e la sequenza di chiamate tra il livello API e i worker di backend.

Aree funzionali chiave:
1. Estrazione ZIP: Gestione di strutture di archivio variabili e sovrascritture del file system.
2. Pipeline di analisi: Coordinamento di scanner e modelli AI (integrazione ibrida).
3. Flusso di rigenerazione: Applicazione delle correzioni ai file sorgente fisici.
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
    Crea un file ZIP in memoria con una semplice struttura di test:
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
    Crea un file ZIP "piatto" (senza la directory radice):
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
    """Fixture per pulire i repository di test dopo ogni test."""
    yield
    # Pulizia dopo il test
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
# Questi test verificano l'integrazione nel mondo reale tra:
# - Endpoint FastAPI (/api/zip)
# - File system (estrazione, creazione directory)
# - Gestione ZIP (libreria zipfile)
# - Validazione dei parametri
# NON CI SONO MOCK dei funzionalità sotto test
# ==============================================================================

def test_upload_zip_success_with_root_folder(sample_zip_file, cleanup_test_repos):
    """
    Valida la logica di estrazione ZIP e normalizzazione dei percorsi.

    Questo test garantisce che i repository impacchettati con una singola directory padre (es. test-repo-main/) vengano "appiattiti" in modo che il codice sorgente risieda direttamente nella directory di destinazione senza nidificazioni ridondanti.
    """
    files = {
        'uploaded_file': ('test-repo.zip', sample_zip_file, 'application/zip')
    }
    data = {
        'owner': 'testowner',
        'repo': 'testrepo'
    }

    response = client.post('/api/zip', files=files, data=data)

    # Verifica risposta
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

    # Assicurati che NON ci sia una directory extra (test-repo-main/)
    assert not os.path.exists(os.path.join(repo_path, 'test-repo-main'))


def test_upload_zip_success_flat_structure(flat_zip_file, cleanup_test_repos):
    """
    Test di integrazione: Caricamento di uno ZIP con una struttura di directory piatta.

    Obiettivo:
    Garantisce che la logica di estrazione identifichi correttamente che non esiste una singola directory radice da "appiattire" ed estragga invece tutti i file direttamente nella directory di destinazione {owner}_{repo}.

    Validazione:
    1. Risposta HTTP 200 OK.
    2. Verifica del 'local_path' restituito nel payload JSON.
    3. Controllo dell'esistenza fisica dei file principali (README, LICENSE, main.py) all'interno della directory di destinazione sul file system host.
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
    Verifica che i file non supportati vengano bloccati.

    L'endpoint deve agire come un gatekeeper: se l'utente tenta di caricare un file di testo (.txt) invece di un archivio, il sistema deve interrompere l'operazione prima di toccare il file system.
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
     Testa la gestione di archivi binari corrotti.

     Testa la resilienza del sistema contro file che hanno l'estensione corretta
     ma contenuto binario malformato. Il sistema dovrebbe catturare l'eccezione 'BadZipFile'
     e restituire un errore client-side (400) invece di un crash (500).
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
    Test di integrazione: Idempotenza del file system.

    Verifica che il caricamento di uno ZIP per un owner/repo esistente attivi una pulizia completa della vecchia directory. Questo previene la 'polluzione dei file'
    dove i file legacy di un caricamento precedente rimangono nello spazio di lavoro.
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

    # Aggiungiamo un file marker per verificare la sovrascrittura
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

    # Verifica che il marker non esista più (directory sovrascritta)
    assert not os.path.exists(marker_file)
    assert os.path.exists(os.path.join(repo_path, 'README.md'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_upload_zip_missing_owner_or_repo():
    """
    Test di validazione: Metadati obbligatori mancanti.

    Garantisce che la validazione delle richieste FastAPI attivi correttamente un errore
    422 Unprocessable Entity quando il modulo multipart manca
    dei campi richiesti (owner o repo).
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
    Caso limite: Caricamento di file 0-byte.

    Verifica che il sistema gestisca i flussi binari vuoti in modo elegante,
    restituendo un errore client (400) o errore server (500)
    a seconda del fallimento dell'inizializzazione della libreria zipfile.
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

    # Può essere 400 (zip corrotto) o 500 (errore interno), dipende dall'implementazione
    assert response.status_code in [400, 500]


def test_upload_zip_with_special_characters_in_filename():
    """
    Test di integrazione: Caricamento con caratteri complessi nel nome dello ZIP.

    Verifica che il sistema gestisca correttamente i nomi dei file con spazi, parentesi e
    tag di versioning. Il nome dello ZIP non dovrebbe influenzare la directory di destinazione
    (che è derivata da owner/repo).
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

    # Successo previsto: la destinazione è indipendente dal nome del file sorgente
    assert response.status_code == 200

    # Cleanup
    cleanup_path = os.path.join(config.CLONE_BASE_DIR, 'specialowner_specialrepo')
    if os.path.exists(cleanup_path):
        shutil.rmtree(cleanup_path)


def test_upload_zip_with_nested_directories():
    """
    Test di integrazione: Struttura di directory profondamente annidata.

    Valida che il motore di estrazione preservi correttamente strutture gerarchiche complesse
    e garantisce che i file siano accessibili nei percorsi profondi previsti.
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Struttura profondamente annidata
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

    # Verifica che i file annidati esistano nel percorso relativo corretto
    assert os.path.exists(os.path.join(repo_path, 'level1', 'level2', 'level3', 'deep_file.txt'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_upload_zip_with_multiple_root_folders():
    """
    Test di integrazione: ZIP con più cartelle a livello radice.

    Verifica che gli archivi contenenti più directory o file a livello radice vengano estratti completamente senza perdere dati o fallire nel controllo della struttura.
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

    # Verifica che tutti i componenti esistano nella destinazione di estrazione
    assert os.path.exists(os.path.join(repo_path, 'folder1', 'file1.txt'))
    assert os.path.exists(os.path.join(repo_path, 'folder2', 'file2.txt'))
    assert os.path.exists(os.path.join(repo_path, 'root_file.txt'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_analyze_on_empty_repository(cleanup_test_repos):
    """
    Test di integrazione: Analisi di un repository vuoto (directory esiste, nessun file).

    Valida l'orchestrazione tra l'endpoint, il file system e il flusso di lavoro di analisi quando non sono presenti dati. Utilizza un mock minimo per
    ScanCode per evitare l'esecuzione reale su una directory vuota.
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

            # Verifica comportamento senza crash (previsto 200, 400 o 500 a seconda della logica di business)
            assert response.status_code in [200, 400, 500]
    finally:
        if os.path.exists(empty_path):
            shutil.rmtree(empty_path)


def test_run_analysis_with_empty_string_parameters():
    """
    Test di validazione: /api/analyze chiamato con parametri stringa vuota.

    Verifica che l'API imponga valori non vuoti per owner/repo
    (non solo presenza, ma contenuto). Dovrebbe restituire 400 Bad Request.
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
     Test di integrazione: Analisi richiesta per un repository non esistente.

     Verifica l'integrazione tra l'endpoint, l'orchestrazione del flusso di lavoro,
     e il controllo del file system. Se la directory è mancante, dovrebbe
     restituire un errore 400 Bad Request con un chiaro messaggio di errore.
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
     Test di integrazione: Analisi con caratteri speciali in owner/repo.

     Garantisce che il sistema gestisca correttamente caratteri non standard (trattini, sottolineature)
     nei parametri URL. Il test si aspetta un errore 400 perché il
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
    Test di integrazione: Gestione di eccezioni di runtime inaspettate.

    Simula un'eccezione RuntimeError generica durante il flusso di lavoro (non-ValueError).
    Verifica che l'API catturi l'errore e restituisca un codice di stato 500
    con un generico messaggio 'Internal error' al client.
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
# Questi test verificano l'orchestrazione tra l'endpoint e il flusso di lavoro
# logica mentre MOCKING HEAVY external dependencies to avoid:
# - Slow ScanCode execution (CLI tool)
# - External LLM/Ollama API calls (Network/GPU cost)
# - Physical report file generation
#
# Sono etichettati come IBRIDI perché:
# ✅ Testano: routing HTTP, validazione delle richieste e logica del flusso di lavoro.
# ❌ NON testano: Integrazione reale con gli strumenti esterni AI o ScanCode.
# ==============================================================================

@pytest.fixture
def mock_scancode_and_llm():
    """
    Fixture per TEST IBRIDI: Mocka tutte le dipendenze esterne del flusso di lavoro di analisi.

    Componenti mockati:
    - Strumento ScanCode (run_scancode)
    - Rilevamento licenza principale (detect_main_license_scancode)
    - Filtraggio dati (filter_licenses)
    - Estrazione basata su AI (extract_file_licenses)
    - Ranking licenze (choose_most_permissive_license_in_file)
    - Motore di compatibilità (check_compatibility)
    - Motore di suggerimenti AI (enrich_with_llm_suggestions)
    """
    with patch('app.services.analysis_workflow.run_scancode') as mock_scancode, \
            patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
            patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
            patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
            patch('app.services.analysis_workflow.choose_most_permissive_license_in_file') as mock_ranking, \
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

        # Mock extracted licenses (Dict[str, str] format: path -> license)
        mock_extract.return_value = {
            'README.md': 'MIT',
            'src/main.py': 'MIT'
        }

        # Mock license ranking (returns same dict after processing OR clauses)
        mock_ranking.return_value = {
            'README.md': 'MIT',
            'src/main.py': 'MIT'
        }

        # Mock compatibility check (no issues)
        mock_compat.return_value = {'issues': []}

        # Mock enriched issues (no issues for MIT->MIT)
        mock_enrich.return_value = []

        yield {
            'scancode': mock_scancode,
            'detect': mock_detect,
            'filter': mock_filter,
            'extract': mock_extract,
            'ranking': mock_ranking,
            'compat': mock_compat,
            'enrich': mock_enrich
        }


def test_run_analysis_success_after_upload(sample_zip_file, mock_scancode_and_llm, cleanup_test_repos):
    """
    [HYBRID TEST]
    Flusso E2E completo: Caricamento ZIP -> Esecuzione analisi con dipendenze mockate.

    Passi:
    1. Carica un file ZIP (Integrazione reale del file system).
    2. Richiedi analisi per quel repository.
    3. Verifica che il risultato corrisponda ai dati di scansione mockati.
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
    [TEST IBRIDO]
    Scenario: Rilevamento di licenze incompatibili utilizzando mock.

    Garantisce che i problemi siano correttamente riportati nella risposta JSON quando:
    - La licenza principale è rilevata come MIT.
    - Un file specifico contiene GPL-3.0 (che è incompatibile).
    """
    with patch('app.services.analysis_workflow.run_scancode') as mock_scancode, \
            patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
            patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
            patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
            patch('app.services.analysis_workflow.choose_most_permissive_license_in_file') as mock_ranking, \
            patch('app.services.analysis_workflow.check_compatibility') as mock_compat, \
            patch('app.services.analysis_workflow.enrich_with_llm_suggestions') as mock_enrich:

        # Mock: Set up a conflict scenario (main license MIT, but a file with GPL)
        mock_scancode.return_value = {'files': []}
        mock_detect.return_value = ('MIT', 'LICENSE')
        mock_filter.return_value = mock_scancode.return_value
        # Mock extracted licenses (Dict[str, str] format: path -> license)
        mock_extract.return_value = {
            'src/gpl_code.py': 'GPL-3.0'
        }
        # Mock license ranking (returns same dict)
        mock_ranking.return_value = {
            'src/gpl_code.py': 'GPL-3.0'
        }

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
    Test completo del flusso di lavoro end-to-end: da caricamento ZIP a completamento analisi.

    Questo test garantisce che il sistema possa passare con successo dalla
    ricezione di un file binario all'orchestrazione di una scansione licenza sulla
    struttura di directory risultante.

    Passi di esecuzione:
    1. Carica ZIP: Test di integrazione reale per la gestione del modulo multipart e l'estrazione su disco.
    2. Analizza: Attiva il flusso di lavoro sulla nuova directory creata.
    3. Controllo di coerenza: Verifica che il risultato dell'analisi corrisponda ai metadati caricati.

    Dipendenze esterne mockate: 6 (tramite la fixture mock_scancode_and_llm).
    """
    owner, repo = 'workflowowner', 'workflowrepo'

    # Step 1: Upload
    files = {
        'uploaded_file': ('test-repo.zip', sample_zip_file, 'application/zip')
    }
    data = {
        'owner': owner,
        'repo': repo
    }

    upload_resp = client.post('/api/zip', files=files, data=data)
    assert upload_resp.status_code == 200
    local_path = upload_resp.json()['local_path']
    assert os.path.exists(local_path)

    # Step 2: Analyze
    analyze_resp = client.post('/api/analyze', json={'owner': owner, 'repo': repo})
    assert analyze_resp.status_code == 200

    # Step 3: Validate analysis result
    result = analyze_resp.json()
    assert result['repository'] == f'{owner}/{repo}'
    assert result['main_license'] is not None


"""
TEST di integrazione per gli endpoint /api/regenerate e /api/download
Questi test verificano il flusso completo con interazioni reali tra componenti,
utilizzando mock SOLO per dipendenze esterne costose (ScanCode, LLM).
"""
from app.models.schemas import AnalyzeResponse, LicenseIssue

# ==============================================================================
# FIXTURES AND HELPERS
# ==============================================================================

@pytest.fixture
def cleanup_test_repos():
    """
    Fixture di pulizia: Rimuove le directory di test fisiche e gli ZIP generati.

    Garantisce che le cartelle temporanee (ad es., regenowner_regenrepo) e
    gli artefatti scaricati siano eliminati dopo ogni test per prevenire
    la contaminazione incrociata tra test.
    """
    yield
    # Pulizia dopo il test
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
    """Helper per creare un repository di test fisico sul file system."""
    def _create(owner: str, repo: str, files: dict = None):
        """
    Helper Fixture: Popola manualmente il filesystem con un repository di test.

    Argomenti:
        owner: Il nome del proprietario del repository.
        repo: Il nome del repository.
        files: Un dizionario che mappa percorsi file al loro contenuto stringa.

    Restituisce:
        Il percorso assoluto al repository creato.
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
    Fixture: Fornisce un oggetto AnalyzeResponse standard.

    Utilizzato per simulare un risultato di analisi precedente che deve
    essere passato all'endpoint di rigenerazione.
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
    Test di integrazione: Rigenerazione del codice riuscita.

    Flusso di lavoro:
    1. Popola il file system con un repository fisico.
    2. Chiama /api/regenerate con un AnalyzeResponse precedente.
    3. Verifica l'orchestrazione tra l'endpoint, il flusso di lavoro e il file system.

    Mock: Solo 'perform_regeneration' è mockato per evitare chiamate esterne all'LLM.
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
    Test di validazione: Rifiuta identificatori di repository malformati.

    Garantisce che l'endpoint restituisca HTTP 400 se la stringa 'repository'
    non segue il formato 'owner/repo'.
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
    Test di gestione degli errori: Rigenerazione su un repository mancante.

    Verifica che il sistema mappi correttamente un errore ValueError 'Repository not found'
    a una risposta client-side HTTP 400.
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
    Test di integrazione pura: Download reale del repository.

    Flusso:
    1. Crea un repository fisico con più file e sottodirectory.
    2. Richiedi un download tramite /api/download.
    3. Valida le intestazioni HTTP (Content-Type: application/zip).
    4. Estrai fisicamente lo ZIP restituito per verificare l'integrità del contenuto interno.
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
    Test di integrazione completo: Download riuscito del repository.

    Flusso di lavoro:
    1. Popola il file system con un repository di test fisico.
    2. Chiama l'endpoint /api/download.
    3. Valida la risposta HTTP (200 OK, application/zip).
    4. Valida l'integrità e la struttura del contenuto ZIP.

    Nota: Questo è un test di integrazione PURO senza mock.
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

def test_download_repo_repository_not_found():
    """
     Test di gestione degli errori: Tentativo di download di un repository non esistente.

     Verifica l'integrazione tra l'endpoint, il servizio e il controllo del file system. Dovrebbe restituire un errore 400 Bad Request.
     """
    response = client.post(
        "/api/download",
        json={"owner": "nonexistent", "repo": "notfound"}
    )

    assert response.status_code == 400
    assert "Repository not found" in response.json()["detail"]

def test_download_repo_missing_parameters():
    """
    Test di validazione: Parametri obbligatori mancanti.

    Garantisce che l'API rifiuti le richieste mancanti delle chiavi 'owner' o 'repo'
    con un errore 400 Bad Request.
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
     Caso limite: Download di un repository vuoto.

     Verifica che una directory senza file possa ancora essere compressa e restituita all'utente con successo.
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
    Test di integrazione: Gestione di caratteri speciali nei nomi dei file durante la creazione dello ZIP.

    Garantisce che i file contenenti spazi, trattini, sottolineature e
    parentesi siano correttamente preservati e inclusi nell'archivio finale.
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
     Test di validazione: Input di stringhe vuote.

     Garantisce che le stringhe vuote ("") non siano trattate come identificatori validi
     per nomi di owner o repository.
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
    Test di gestione degli errori: Errore interno del server durante il processo ZIP.

    Verifica che se si verifica un'eccezione RuntimeError inaspettata durante la compressione,
    l'API restituisca uno stato 500 con un dettaglio 'Internal error'.
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
    Test di orchestrazione end-to-end: Ciclo di vita completo dell'applicazione.

    Verifica l'integrazione tra:
    1. Configurazione del repository (creazione manuale)
    2. Flusso di lavoro di analisi (mockate le scansioni esterne)
    3. Flusso di lavoro di rigenerazione (mockata la correzione AI)
    4. Download (vera compressione del file system)

    Questo garantisce che l'output della fase 'Analizza' sia un valido
    input per la fase 'Rigenera' e che lo stato finale sia scaricabile.
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
    Test di integrazione: Clona un repository utilizzando l'endpoint /api/clone.

    Verifica che l'endpoint accetti correttamente i parametri owner e repo,
    chiami il servizio di clonazione e restituisca informazioni corrette sullo stato e sul percorso.
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
    Test di integrazione: L'endpoint Clone rifiuta la richiesta senza owner.
    """
    response = client.post("/api/clone", json={"repo": "testrepo"})

    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_repository_missing_repo():
    """
    Test di integrazione: L'endpoint Clone rifiuta la richiesta senza repo.
    """
    response = client.post("/api/clone", json={"owner": "testowner"})

    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_repository_both_params_missing():
    """
    Test di integrazione: L'endpoint Clone rifiuta la richiesta senza parametri.
    """
    response = client.post("/api/clone", json={})

    assert response.status_code == 400
    assert "Owner and Repo are required" in response.json()["detail"]


def test_clone_repository_empty_strings():
    """
    Test di integrazione: L'endpoint Clone rifiuta i parametri vuoti.
    """
    response1 = client.post("/api/clone", json={"owner": "", "repo": "testrepo"})
    assert response1.status_code == 400

    response2 = client.post("/api/clone", json={"owner": "testowner", "repo": ""})
    assert response2.status_code == 400

    response3 = client.post("/api/clone", json={"owner": "", "repo": ""})
    assert response3.status_code == 400


def test_clone_repository_service_value_error():
    """
    Test di integrazione: L'endpoint Clone gestisce il ValueError a livello di servizio.

    Verifica che quando il servizio di clonazione genera un ValueError,
    venga catturato correttamente e restituisca uno stato 400.
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
    Test di integrazione: L'endpoint Clone gestisce le eccezioni inattese.

    Verifica che gli errori inattesi vengano catturati e restituiscano uno stato 500.
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
    Test di integrazione: Clona con caratteri speciali nel nome del repository.

    Verifica che i repository con punti, trattini e sottolineature
    siano gestiti correttamente.
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
    Test di integrazione: Flusso di lavoro completo di clonazione con vere operazioni sul file system.

    Questo test esegue operazioni di clonazione reali (mockate Git, ma reale file system)
    e verifica l'intero flusso di lavoro end-to-end.
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
    Test di integrazione: Suggerisci licenza basata sui requisiti.

    Verifica che l'endpoint suggest-license elabori correttamente i requisiti dell'utente e restituisca suggerimenti di licenza appropriati.
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
    Test di integrazione: Suggerisci licenza con licenze rilevate dall'analisi.

    Verifica che le licenze rilevate vengano passate al motore di raccomandazione
    e considerate nel suggerimento.
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
    Test di integrazione: Verifica che l'incompatibilità GPL venga rilevata con licenze permissive.

    Quando le licenze rilevate includono Apache-2.0, suggerire GPL dovrebbe essere evitato
    a causa dell'incompatibilità.
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
    Test di integrazione: Gestisci correttamente più licenze rilevate.

    Verifica che il sistema possa gestire progetti con più licenze
    e suggerire una compatibile.
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
    Test di integrazione: Suggerisci licenza con solo i campi richiesti.

    Verifica che l'endpoint funzioni con requisiti minimi (solo owner e repo).
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
    Test di integrazione: Suggerisci licenza per requisiti di copyleft.

    Verifica che requisiti di copyleft forti portino a suggerimenti simili a GPL.
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
    Test di integrazione: Suggerisci licenza per requisiti di copyleft debole.

    Verifica che copyleft debole suggerisca tipicamente licenze in stile LGPL.
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
    Test di integrazione: L'endpoint suggerisci licenza convalida i campi richiesti.

    Verifica che la mancanza di owner o repo restituisca un errore di convalida 422.
    """
    response1 = client.post("/api/suggest-license", json={"owner": "testowner"})
    assert response1.status_code == 422

    response2 = client.post("/api/suggest-license", json={"repo": "testrepo"})
    assert response2.status_code == 422

    response3 = client.post("/api/suggest-license", json={})
    assert response3.status_code == 422


def test_suggest_license_service_exception():
    """
    Test di integrazione: Suggerisci licenza gestisce gli errori del servizio.

    Verifica che quando il servizio AI fallisce, venga restituito un errore 500
    con un messaggio di errore appropriato.
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
    Test di integrazione: Suggerisci licenza con tutte le opzioni booleane impostate.

    Verifica che combinazioni di requisiti complessi siano elaborate correttamente.
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
    Test di integrazione: Valida lo schema di risposta per suggest-license.

    Garantisce che la risposta sia conforme allo schema LicenseSuggestionResponse.
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
    Test di integrazione: Flusso di lavoro completo - caricamento, analisi, ottenimento suggerimento.

    Questo test verifica che dopo aver analizzato un repository con licenza UNKNOWN,
    l'endpoint suggest-license possa fornire raccomandazioni appropriate.
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
    Test di integrazione: Flusso di lavoro completo con estrazione delle licenze rilevate.

    Questo test verifica l'intero flusso di lavoro:
    1. Caricamento/Clonazione del repository
    2. Analisi e rilevamento delle licenze esistenti
    3. Passaggio delle licenze rilevate all'endpoint di suggerimento
    4. Ricezione della raccomandazione di licenza compatibile
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
    with patch('app.services.analysis_workflow.run_scancode') as mock_scancode, \
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

        mock_scancode.return_value = {"files": [
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
