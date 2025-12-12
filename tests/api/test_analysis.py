import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# --- FIXTURES PER PULIRE IL CODICE ---
@pytest.fixture
def mock_env_credentials():
    """Simula le variabili d'ambiente o la funzione che le recupera."""
    with patch("app.api.analysis.github_auth_credentials", side_effect=["MOCK_CID", "MOCK_SEC"]) as m:
        yield m


@pytest.fixture
def mock_httpx_post():
    """Mocka la chiamata POST di httpx."""
    with patch("app.api.analysis.httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_clone():
    """Mocka la funzione di clonazione."""
    with patch("app.api.analysis.perform_cloning") as m:
        yield m


# ------------------------------------------------------------------
# TEST MIGLIORATI
# ------------------------------------------------------------------

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