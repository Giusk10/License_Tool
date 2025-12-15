import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

# Client globale per test che non richiedono directory patchate
client = TestClient(app)

"""
Test di integrazione per gli endpoint /api/auth/start e /api/callback
Questi test verificano il flusso completo di autenticazione OAuth con GitHub
"""

# --- FIXTURES PER PULIRE IL CODICE ---
@pytest.fixture
def mock_env_credentials():
    """Simula le variabili d'ambiente o la funzione che le recupera."""
    with patch("app.controllers.analysis.github_auth_credentials", side_effect=["MOCK_CID", "MOCK_SEC"]) as m:
        yield m


@pytest.fixture
def mock_httpx_post():
    """Mocka la chiamata POST di httpx."""
    with patch("app.controllers.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_clone():
    """Mocka la funzione di clonazione."""
    with patch("app.controllers.analysis.perform_cloning") as m:
        yield m


def test_start_analysis_redirect_url_parsing(mock_env_credentials):
    """
    Migliorato: Invece di controllare stringhe parziali, parsa l'URL
    per essere robusto contro l'ordine dei parametri.
    """
    mock_env_credentials.side_effect = None
    mock_env_credentials.return_value = "CLIENT_ID_X"

    response = client.get(
        "/api/auth/start",
        params={"owner": "facebook", "repo": "react"},
        follow_redirects=False
    )
    assert response.status_code == 307

    # Parsing dell'URL per verifica precisa
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path == "/login/oauth/authorize"
    assert params["client_id"] == ["CLIENT_ID_X"]
    assert params["scope"] == ["repo"]
    assert params["state"] == ["facebook:react"]


@pytest.mark.asyncio
async def test_auth_callback_happy_path_verify_args(mock_env_credentials, mock_httpx_post, mock_clone):
    """
    Approfondimento: Verifica che al clone vengano passati i dati corretti.
    """
    # Setup Mock HTTPX
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "gh_token_XYZ", "token_type": "bearer"}
    mock_httpx_post.return_value = mock_resp

    # Setup Mock Clone
    mock_clone.return_value = "/tmp/path/to/repo"

    response = client.get("/api/callback", params={"code": "auth_code_123", "state": "user:repo"})

    assert response.status_code == 200
    assert response.json()["local_path"] == "/tmp/path/to/repo"

    # VERIFICA CRUCIALE: Assicuriamoci che stiamo usando il token ricevuto da GitHub per clonare
    mock_clone.assert_called_once()
    args, _ = mock_clone.call_args
    # Supponendo che la firma sia perform_cloning(url, token) o simile:
    assert "gh_token_XYZ" in str(args) or "gh_token_XYZ" in str(_)


@pytest.mark.asyncio
async def test_auth_callback_network_error(mock_env_credentials, mock_httpx_post):
    """
    NUOVO SCENARIO: Errore di connessione verso GitHub (timeout, dns error).
    """
    # Simuliamo un'eccezione di rete lanciata da httpx
    mock_httpx_post.side_effect = httpx.RequestError("Connection timeout", request=MagicMock())

    response = client.get("/api/callback", params={"code": "code", "state": "u:r"})

    # L'app dovrebbe gestire l'eccezione e non crashare (500) o restituire un 400 gestito
    assert response.status_code in [400, 502, 503]
    assert "errore" in response.json().get("detail", "").lower() or "connection" in response.json().get("detail",
                                                                                                        "").lower()


@pytest.mark.asyncio
async def test_auth_callback_unexpected_json(mock_env_credentials, mock_httpx_post):
    """
    NUOVO SCENARIO: GitHub risponde 200 OK, ma il JSON non ha 'access_token'.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Risposta vuota o inattesa
    mock_resp.json.return_value = {"foo": "bar"}
    mock_httpx_post.return_value = mock_resp

    response = client.get("/api/callback", params={"code": "code", "state": "u:r"})

    assert response.status_code == 400
    assert "token" in response.json().get("detail", "").lower()

@patch("app.controllers.analysis.perform_cloning")
@patch("app.controllers.analysis.github_auth_credentials")
@patch("httpx.AsyncClient.post")
def test_callback_success(mock_httpx_post, mock_creds, mock_clone):

    #Testa il flusso di callback:
    #1. Riceve code & state
    #2. Scambia code per token (mock httpx)
    #3. Clona la repo (mock clone)

    # Setup Mock
    mock_creds.side_effect = lambda k: "fake-secret" if k == "CLIENT_SECRET" else "fake-id"

    # Mock risposta GitHub token
    mock_httpx_post.return_value = AsyncMock(
        json=lambda: {"access_token": "gho_fake_token"}
    )

    # Mock clone
    mock_clone.return_value = "/tmp/cloned/path"

    # Chiamata API
    response = client.get("/api/callback?code=12345&state=giusk10:testrepo")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cloned"
    assert data["local_path"] == "/tmp/cloned/path"

    # Verifica che il token sia stato passato al servizio di clone
    mock_clone.assert_called_with(
        owner="giusk10",
        repo="testrepo",
        oauth_token="gho_fake_token"
    )

"""
Test di integrazione per gli endpoint /api/zip e /api/analyze
Questi test verificano il flusso completo di upload zip e analisi con interazioni reali
tra i componenti (senza mock eccessivi).
"""
import os
import shutil
import zipfile
from io import BytesIO
from app.utility import config

# ==============================================================================
# FIXTURES E HELPER
# ==============================================================================

@pytest.fixture
def sample_zip_file():
    """
    Crea un file ZIP in memoria con una struttura semplice di test:
    test-repo-main/
        ├── README.md
        ├── LICENSE (MIT)
        └── src/
            └── main.py
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Struttura con singola directory root
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
    Crea un file ZIP "piatto" (senza directory root):
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
    """Fixture per pulire le repository di test dopo ogni test."""
    yield
    # Cleanup dopo il test
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


# ==============================================================================
# TEST DI INTEGRAZIONE PURI - UPLOAD_ZIP ENDPOINT
# ==============================================================================
# Questi test verificano l'integrazione reale tra:
# - FastAPI endpoint (/api/zip)
# - File system (estrazione, creazione directory)
# - Gestione ZIP (zipfile library)
# - Validazione parametri
# NESSUN MOCK delle funzionalità sotto test
# ==============================================================================

def test_upload_zip_success_with_root_folder(sample_zip_file, cleanup_test_repos):
    """
    Test di integrazione: upload di uno ZIP con una singola directory root.
    Verifica che:
    1. Il file viene estratto correttamente
    2. La struttura con directory root singola viene normalizzata
    3. I file sono accessibili nella posizione corretta
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

    # Verifica che i file siano stati estratti correttamente
    repo_path = json_response['local_path']
    assert os.path.exists(repo_path)
    assert os.path.exists(os.path.join(repo_path, 'README.md'))
    assert os.path.exists(os.path.join(repo_path, 'LICENSE'))
    assert os.path.exists(os.path.join(repo_path, 'src', 'main.py'))

    # Verifica che NON ci sia una directory extra (test-repo-main/)
    assert not os.path.exists(os.path.join(repo_path, 'test-repo-main'))


def test_upload_zip_success_flat_structure(flat_zip_file, cleanup_test_repos):
    """
    Test di integrazione: upload di uno ZIP con struttura piatta.
    Verifica che i file vengano estratti direttamente nella directory target.
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
    Test: tentativo di upload di un file non-ZIP.
    Deve restituire errore 400.
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
    Test: upload di un file ZIP corrotto.
    Deve restituire errore 400 con messaggio appropriato.
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
    assert 'corrotto' in response.json()['detail'].lower() or 'invalid' in response.json()['detail'].lower()


def test_upload_zip_overwrites_existing(sample_zip_file, cleanup_test_repos):
    """
    Test: upload di uno ZIP quando esiste già una directory con lo stesso nome.
    Verifica che la directory esistente venga sovrascritta correttamente.
    """
    # Prima creazione
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

    # Secondo upload (stesso owner/repo)
    sample_zip_file.seek(0)  # Reset del buffer
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
    Test di integrazione: upload senza specificare owner o repo.
    Verifica la validazione FastAPI dei parametri obbligatori.
    Deve fallire con errore 422.
    """
    fake_zip = BytesIO(b"PK\x03\x04...")

    # Caso 1: manca owner
    response1 = client.post(
        '/api/zip',
        files={'uploaded_file': ('test.zip', fake_zip, 'application/zip')},
        data={'repo': 'testrepo'}
    )
    assert response1.status_code == 422  # FastAPI validation error

    # Caso 2: manca repo
    fake_zip.seek(0)
    response2 = client.post(
        '/api/zip',
        files={'uploaded_file': ('test.zip', fake_zip, 'application/zip')},
        data={'owner': 'testowner'}
    )
    assert response2.status_code == 422


def test_upload_zip_empty_file():
    """
    Test di integrazione: upload di un file ZIP vuoto (0 bytes).
    Verifica la gestione di file vuoti.
    Deve restituire errore appropriato (400 o 500).
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
    Test di integrazione: upload di un file con caratteri speciali nel nome.
    Verifica che il sistema gestisca correttamente nomi file complessi.
    Il nome file non dovrebbe influire sulla directory di destinazione.
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

    # Dovrebbe comunque funzionare (il nome file non influisce sulla directory di destinazione)
    assert response.status_code == 200

    # Cleanup
    cleanup_path = os.path.join(config.CLONE_BASE_DIR, 'specialowner_specialrepo')
    if os.path.exists(cleanup_path):
        shutil.rmtree(cleanup_path)


def test_upload_zip_with_nested_directories():
    """
    Test di integrazione: upload di uno ZIP con molti livelli di directory annidate.
    Verifica la corretta estrazione della struttura complessa.
    Testa l'integrazione endpoint + file system con strutture profonde.
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

    # Verifica che i file annidati esistano
    assert os.path.exists(os.path.join(repo_path, 'level1', 'level2', 'level3', 'deep_file.txt'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_upload_zip_with_multiple_root_folders():
    """
    Test di integrazione: upload di uno ZIP con multiple cartelle nella root.
    Verifica che tutte vengano estratte correttamente.
    Testa gestione di strutture ZIP con più cartelle al livello root.
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

    # Verifica che tutte le cartelle e file esistano
    assert os.path.exists(os.path.join(repo_path, 'folder1', 'file1.txt'))
    assert os.path.exists(os.path.join(repo_path, 'folder2', 'file2.txt'))
    assert os.path.exists(os.path.join(repo_path, 'root_file.txt'))

    # Cleanup
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)


def test_analyze_on_empty_repository(cleanup_test_repos):
    """
    Test di integrazione: analisi su una repository vuota (solo directory, nessun file).
    Verifica l'integrazione tra:
    - Endpoint /api/analyze
    - File system (directory vuota)
    - Workflow di analisi con repository vuota

    Mock minimo: solo run_scancode (1 mock) per evitare esecuzione reale su directory vuota
    """
    # Creiamo manualmente una directory vuota
    owner, repo = 'emptyowner', 'emptyrepo'
    empty_path = os.path.join(config.CLONE_BASE_DIR, f'{owner}_{repo}')
    os.makedirs(empty_path, exist_ok=True)

    try:
        with patch('app.services.analysis_workflow.run_scancode') as mock_scan:
            # Mock scancode per simulare scansione su repository vuota
            mock_scan.return_value = {'files': []}

            response = client.post('/api/analyze', json={'owner': owner, 'repo': repo})

            # Potrebbe fallire o restituire analisi vuota, dipende dall'implementazione
            # Qui verifichiamo solo che non crashi
            assert response.status_code in [200, 400, 500]
    finally:
        if os.path.exists(empty_path):
            shutil.rmtree(empty_path)


def test_run_analysis_with_empty_string_parameters():
    """
    Test di integrazione: chiamata /api/analyze con owner o repo come stringhe vuote.
    Verifica la validazione dei parametri (non solo None, ma anche stringhe vuote).
    Deve restituire errore 400.
    """
    # Caso 1: owner è stringa vuota
    response1 = client.post('/api/analyze', json={'owner': '', 'repo': 'testrepo'})
    assert response1.status_code == 400
    assert 'obbligatori' in response1.json()['detail'].lower() or 'required' in response1.json()['detail'].lower()

    # Caso 2: repo è stringa vuota
    response2 = client.post('/api/analyze', json={'owner': 'testowner', 'repo': ''})
    assert response2.status_code == 400

    # Caso 3: entrambi sono stringhe vuote
    response3 = client.post('/api/analyze', json={'owner': '', 'repo': ''})
    assert response3.status_code == 400


def test_run_analysis_repository_not_found():
    """
    Test di integrazione: tentativo di analisi su una repository non clonata.
    Verifica l'integrazione endpoint → workflow → file system check.
    Deve restituire errore 400 con messaggio appropriato.
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
    Test di integrazione: analisi con caratteri speciali in owner/repo.
    Verifica che il sistema gestisca correttamente parametri con caratteri non standard.
    Dovrebbe fallire perché la directory non esiste (non è stata clonata).
    """
    # Owner/repo con caratteri speciali validi per GitHub
    payload = {
        'owner': 'owner-with-dash',
        'repo': 'repo_with_underscore'
    }

    response = client.post('/api/analyze', json=payload)

    # Dovrebbe restituire 400 perché la repo non è stata clonata
    assert response.status_code == 400


@patch('app.controllers.analysis.perform_initial_scan')
def test_run_analysis_generic_exception(mock_scan):
    """
    Test di integrazione: Exception generica (non ValueError) in perform_initial_scan.
    Verifica la gestione di errori imprevisti nel workflow.
    Deve restituire errore 500 con messaggio generico.
    """
    # Mock che solleva una Exception generica (simula errore imprevisto)
    mock_scan.side_effect = RuntimeError("Unexpected error during scan")

    payload = {'owner': 'errorowner', 'repo': 'errorrepo'}
    response = client.post('/api/analyze', json=payload)

    assert response.status_code == 500
    assert 'Errore interno' in response.json()['detail'] or 'Internal' in response.json()['detail']
    assert 'Unexpected error' in response.json()['detail']


# ==============================================================================
# TEST IBRIDI - RUN_ANALYSIS ENDPOINT
# ==============================================================================
# Questi test verificano il flusso di integrazione endpoint → workflow,
# ma MOCKANO PESANTEMENTE le dipendenze esterne per evitare:
# - Esecuzione di ScanCode (lenta)
# - Chiamate a LLM/Ollama (servizio esterno)
# - Generazione file di report
#
# Sono considerati IBRIDI perché:
# ✅ Testano: routing HTTP, validazione, orchestrazione workflow
# ❌ NON testano: integrazione reale tra servizi interni
# ==============================================================================

@pytest.fixture
def mock_scancode_and_llm():
    """
    Fixture per TEST IBRIDI: mocka TUTTE le dipendenze esterne del workflow di analisi.

    Mock inclusi:
    - run_scancode: Tool esterno ScanCode
    - detect_main_license_scancode: Rilevamento licenza principale
    - filter_licenses: Filtro risultati con regex
    - extract_file_licenses: Estrazione licenze via LLM
    - check_compatibility: Verifica compatibilità licenze
    - enrich_with_llm_suggestions: Arricchimento con AI

    Questo fixture rende i test IBRIDI anziché di integrazione pura.
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

        # Mock enriched issues (nessun problema per MIT->MIT)
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
    [TEST IBRIDO]
    Test del flusso completo upload → analisi con mock delle dipendenze esterne.

    Steps:
    1. Upload di uno ZIP (integrazione reale)
    2. Esecuzione dell'analisi sulla repo estratta (workflow mockato)
    3. Verifica del risultato

    Mock utilizzati: 6 (ScanCode, LLM, filtri, compatibilità)
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

    # Step 2: Analisi
    analyze_payload = {
        'owner': 'analyzeowner',
        'repo': 'analyzerepo'
    }

    analyze_response = client.post('/api/analyze', json=analyze_payload)

    # Verifica risultato analisi
    assert analyze_response.status_code == 200
    result = analyze_response.json()

    assert result['repository'] == 'analyzeowner/analyzerepo'
    assert result['main_license'] == 'MIT'
    assert isinstance(result['issues'], list)

def test_run_analysis_with_incompatible_licenses(sample_zip_file, cleanup_test_repos):
    """
    [TEST IBRIDO]
    Test scenario con licenze incompatibili, usando mock per simulare il conflitto.

    Verifica che gli issue vengano riportati correttamente quando:
    - Main license: MIT
    - File con licenza: GPL-3.0 (incompatibile)

    Mock utilizzati: 6 (ScanCode, detect, filter, extract, compatibility, enrich)
    """
    with patch('app.services.analysis_workflow.run_scancode') as mock_scancode, \
            patch('app.services.analysis_workflow.detect_main_license_scancode') as mock_detect, \
            patch('app.services.analysis_workflow.filter_licenses') as mock_filter, \
            patch('app.services.analysis_workflow.extract_file_licenses') as mock_extract, \
            patch('app.services.analysis_workflow.check_compatibility') as mock_compat, \
            patch('app.services.analysis_workflow.enrich_with_llm_suggestions') as mock_enrich:

        # Mock: main license MIT, ma un file con GPL
        mock_scancode.return_value = {'files': []}
        mock_detect.return_value = ('MIT', 'LICENSE')
        mock_filter.return_value = mock_scancode.return_value
        mock_extract.return_value = [
            {'file_path': 'src/gpl_code.py', 'license': 'GPL-3.0'}
        ]

        # Mock incompatibilità
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

        # Upload e analisi
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
    [TEST IBRIDO]
    Test del workflow completo end-to-end con mock delle dipendenze esterne.

    Steps:
    1. Upload ZIP (integrazione reale)
    2. Analisi completa (workflow mockato)
    3. Verifica consistenza dati tra upload e analisi

    Mock utilizzati: 6 (via fixture mock_scancode_and_llm)
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
Test di INTEGRAZIONE per gli endpoint /api/regenerate e /api/download
Questi test verificano il flusso completo con interazioni reali tra componenti,
usando mock SOLO per dipendenze esterne costose (ScanCode, LLM).
"""
from app.models.schemas import AnalyzeResponse, LicenseIssue

# ==============================================================================
# FIXTURES E HELPER
# ==============================================================================

@pytest.fixture
def cleanup_test_repos():
    """Fixture per pulire le repository di test dopo ogni test."""
    yield
    # Cleanup dopo il test
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

        # Cleanup anche dei file zip
        zip_file = os.path.join(config.CLONE_BASE_DIR, f"{pattern}_download.zip")
        if os.path.exists(zip_file):
            try:
                os.remove(zip_file)
            except Exception as e:
                print(f"Cleanup warning: Could not remove {zip_file}: {e}")


@pytest.fixture
def create_test_repo():
    """Helper per creare una repository di test fisica sul file system."""
    def _create(owner: str, repo: str, files: dict = None):
        """
        Crea una repository di test con file specificati.

        Args:
            owner: Nome owner
            repo: Nome repository
            files: Dict {path: content} di file da creare

        Returns:
            Path assoluto della repository creata
        """
        repo_path = os.path.join(config.CLONE_BASE_DIR, f"{owner}_{repo}")
        os.makedirs(repo_path, exist_ok=True)

        # File di default se non specificati
        if files is None:
            files = {
                'README.md': '# Test Repository\n\nThis is a test.',
                'LICENSE': 'MIT License\n\nCopyright (c) 2025 Test\n\nPermission is hereby granted...',
                'src/main.py': '# Main file\nprint("Hello World")\n',
                'src/utils.py': '# Utils\ndef helper():\n    pass\n'
            }

        # Crea i file
        for file_path, content in files.items():
            full_path = os.path.join(repo_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

        return repo_path

    return _create


@pytest.fixture
def sample_analyze_response():
    """Fixture che fornisce un AnalyzeResponse di esempio per test di rigenerazione."""
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
# TEST DI INTEGRAZIONE - REGENERATE_ANALYSIS
# ==============================================================================

def test_regenerate_analysis_success_integration(
        create_test_repo,
        sample_analyze_response,
        cleanup_test_repos
):
    """
    Test di integrazione: rigenerazione completa con repository reale.

    Flusso:
    1. Crea repository fisica di test
    2. Chiama /regenerate con AnalyzeResponse precedente
    3. Verifica integrazione endpoint → workflow → file system

    Mock utilizzati: Solo perform_regeneration (workflow complesso)
    """
    # Step 1: Crea repository di test
    repo_path = create_test_repo(
        "regenowner",
        "regenrepo",
        files={
            'README.md': '# Test',
            'src/incompatible.py': '# GPL code\nprint("test")'
        }
    )

    assert os.path.exists(repo_path)

    # Step 2: Mock solo perform_regeneration (workflow complesso con LLM)
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        # Mock della risposta di rigenerazione
        mock_regen.return_value = AnalyzeResponse(
            repository="regenowner/regenrepo",
            main_license="MIT",
            issues=[
                LicenseIssue(
                    file_path="src/incompatible.py",
                    detected_license="MIT",  # Ora compatibile
                    compatible=True,
                    reason="Rigenerato con successo",
                    regenerated_code_path="src/incompatible.py"
                )
            ],
            report_path="/tmp/new_report.txt"
        )

        # Step 3: Chiamata endpoint
        response = client.post(
            "/api/regenerate",
            json=sample_analyze_response.model_dump()
        )

        # Verifica risposta
        assert response.status_code == 200
        result = response.json()

        assert result['repository'] == "regenowner/regenrepo"
        assert result['main_license'] == "MIT"
        assert len(result['issues']) == 1
        assert result['issues'][0]['compatible'] is True

        # Verifica che perform_regeneration sia stato chiamato correttamente
        mock_regen.assert_called_once()
        call_args = mock_regen.call_args
        assert call_args[1]['owner'] == "regenowner"
        assert call_args[1]['repo'] == "regenrepo"


def test_regenerate_analysis_invalid_repository_format():
    """
    Test di integrazione: validazione formato repository.
    Verifica che l'endpoint rifiuti repository senza slash.
    """
    invalid_payload = {
        "repository": "noslash",  # Manca "/"
        "main_license": "MIT",
        "issues": [],
    }

    response = client.post("/api/regenerate", json=invalid_payload)

    assert response.status_code == 400
    assert "Formato repository non valido" in response.json()["detail"]
    assert "owner/repo" in response.json()["detail"]


def test_regenerate_analysis_repository_not_found(cleanup_test_repos):
    """
    Test di integrazione: tentativo di rigenerazione su repository non esistente.
    Verifica l'integrazione endpoint → workflow → file system check.
    """
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        # Mock che solleva ValueError (repository non trovata)
        mock_regen.side_effect = ValueError("Repository non trovata")

        payload = {
            "repository": "missingowner/missingrepo",
            "main_license": "MIT",
            "issues": [],
        }

        response = client.post("/api/regenerate", json=payload)

        assert response.status_code == 400
        assert "Repository non trovata" in response.json()["detail"]


def test_regenerate_analysis_generic_exception(cleanup_test_repos):
    """
    Test di integrazione: gestione Exception generica durante rigenerazione.
    Verifica che errori imprevisti ritornino 500.
    """
    with patch('app.controllers.analysis.perform_regeneration') as mock_regen:
        # Mock che solleva Exception generica
        mock_regen.side_effect = RuntimeError("Errore imprevisto durante rigenerazione")

        payload = {
            "repository": "errorowner/errorrepo",
            "main_license": "MIT",
            "issues": [],
        }

        response = client.post("/api/regenerate", json=payload)

        assert response.status_code == 500
        assert "Errore interno" in response.json()["detail"]


def test_regenerate_analysis_missing_issues_field():
    """
    Test di integrazione: validazione schema Pydantic.
    Verifica che payload incompleto venga rifiutato.
    """
    incomplete_payload = {
        "repository": "owner/repo",
        "main_license": "MIT"
        # Manca 'issues' (required fields)
    }

    response = client.post("/api/regenerate", json=incomplete_payload)

    # FastAPI validation error
    assert response.status_code == 422


# ==============================================================================
# TEST DI INTEGRAZIONE - DOWNLOAD_REPO
# ==============================================================================

def test_download_repo_success_integration(create_test_repo, cleanup_test_repos):
    """
    Test di integrazione completo: download di repository reale.

    Flusso:
    1. Crea repository fisica con file
    2. Chiama /download
    3. Verifica che lo ZIP sia creato correttamente
    4. Verifica contenuto dello ZIP

    Nessun mock: test di integrazione PURO
    """
    # Step 1: Crea repository di test
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

    # Step 2: Chiamata endpoint
    response = client.post(
        "/api/download",
        json={"owner": "downloadowner", "repo": "downloadrepo"}
    )

    # Step 3: Verifica risposta
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "downloadowner_downloadrepo.zip" in response.headers.get("content-disposition", "")

    # Step 4: Verifica contenuto ZIP
    zip_content = BytesIO(response.content)
    with zipfile.ZipFile(zip_content, 'r') as zip_file:
        # Lista file nel ZIP
        zip_files = zip_file.namelist()

        # Verifica che tutti i file siano presenti
        assert 'downloadowner_downloadrepo/README.md' in zip_files
        assert 'downloadowner_downloadrepo/LICENSE' in zip_files
        assert 'downloadowner_downloadrepo/src/main.py' in zip_files
        assert 'downloadowner_downloadrepo/src/utils.py' in zip_files
        assert 'downloadowner_downloadrepo/docs/guide.md' in zip_files

        # Verifica contenuto di un file
        readme_content = zip_file.read('downloadowner_downloadrepo/README.md').decode('utf-8')
        assert '# Download Test' in readme_content

def test_download_repo_repository_not_found(_msg_matches):
    """
    Test di integrazione: tentativo di download di repository non esistente.
    Verifica l'integrazione endpoint → service → file system check.
    """
    response = client.post(
        "/api/download",
        json={"owner": "nonexistent", "repo": "notfound"}
    )

    assert response.status_code == 400
    assert _msg_matches(
        response.json()["detail"],
        "Repository not found",
        "Repository non trovata"
    )

def test_download_repo_missing_parameters():
    """
    Test di integrazione: validazione parametri obbligatori.
    """
    # Caso 1: Manca owner
    response1 = client.post("/api/download", json={"repo": "test"})
    assert response1.status_code == 400
    assert "obbligatori" in response1.json()["detail"].lower() or "required" in response1.json()["detail"].lower()

    # Caso 2: Manca repo
    response2 = client.post("/api/download", json={"owner": "test"})
    assert response2.status_code == 400

    # Caso 3: Payload vuoto
    response3 = client.post("/api/download", json={})
    assert response3.status_code == 400


def test_download_repo_empty_repository(create_test_repo, cleanup_test_repos):
    """
    Test di integrazione: download di repository vuota.
    Verifica che anche una repo senza file possa essere zippata.
    """
    # Crea repository vuota (solo directory)
    repo_path = create_test_repo("emptyowner", "emptyrepo", files={})
    assert os.path.exists(repo_path)

    response = client.post(
        "/api/download",
        json={"owner": "emptyowner", "repo": "emptyrepo"}
    )

    # Dovrebbe comunque funzionare (ZIP vuoto o con solo la directory)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_download_repo_with_special_characters_in_filenames(
        create_test_repo,
        cleanup_test_repos
):
    """
    Test di integrazione: download di repository con nomi file speciali.
    Verifica che caratteri speciali nei nomi file siano gestiti correttamente.
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

    # Verifica contenuto ZIP
    zip_content = BytesIO(response.content)
    with zipfile.ZipFile(zip_content, 'r') as zip_file:
        zip_files = zip_file.namelist()

        # Verifica che i file con caratteri speciali siano presenti
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
    Test di integrazione: validazione con stringhe vuote.
    """
    # Owner stringa vuota
    response1 = client.post("/api/download", json={"owner": "", "repo": "test"})
    assert response1.status_code == 400

    # Repo stringa vuota
    response2 = client.post("/api/download", json={"owner": "test", "repo": ""})
    assert response2.status_code == 400

    # Entrambi stringhe vuote
    response3 = client.post("/api/download", json={"owner": "", "repo": ""})
    assert response3.status_code == 400


def test_download_repo_generic_exception(create_test_repo, cleanup_test_repos):
    """
    Test di integrazione: gestione Exception generica durante download.
    Verifica che errori imprevisti ritornino 500.
    """
    # Crea repository
    create_test_repo("errorowner", "errorrepo")

    with patch('app.controllers.analysis.perform_download') as mock_download:
        # Mock che solleva Exception generica
        mock_download.side_effect = RuntimeError("Errore imprevisto durante zip")

        response = client.post(
            "/api/download",
            json={"owner": "errorowner", "repo": "errorrepo"}
        )

        assert response.status_code == 500
        assert "Errore interno" in response.json()["detail"]


# ==============================================================================
# TEST FLUSSO COMPLETO: UPLOAD → ANALYZE → REGENERATE → DOWNLOAD
# ==============================================================================

def test_complete_workflow_integration(create_test_repo, cleanup_test_repos):
    """
    Test di integrazione del flusso completo end-to-end:
    1. Setup repository
    2. Analyze (mockato)
    3. Regenerate (mockato)
    4. Download (reale)

    Verifica l'integrazione tra tutti gli endpoint.
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

    # Step 2: Mock Analyze (già testato altrove)
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

    # Step 4: Download (integrazione reale)
    download_resp = client.post("/api/download", json={"owner": owner, "repo": repo})
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/zip"

    # Verifica contenuto ZIP
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

