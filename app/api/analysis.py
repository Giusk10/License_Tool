# app/api/analysis.py
import httpx
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from app.core.config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, CALLBACK_URL
from app.services.analysis_workflow import perform_cloning, perform_initial_scan, perform_regeneration
from app.services.download_service import perform_download
from app.models.schemas import AnalyzeResponse, CloneResult

router = APIRouter()

# ------------------------------------------------------------------
# 1. START: Qui inserisci OWNER e REPO (come facevi nel JSON)
# ------------------------------------------------------------------
@router.get("/auth/start")
def start_analysis(owner: str, repo: str):
    """
    Esempio: /api/auth/start?owner=facebook&repo=react
    """
    # Impacchettiamo i due dati in una stringa unica per il viaggio
    state_data = f"{owner}:{repo}"

    scope = "repo" # Serve 'repo' anche per leggere repo pubbliche senza limiti severi

    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope={scope}"
        f"&state={state_data}"  # <--- Qui viaggiano owner e repo insieme
    )
    return RedirectResponse(github_url)


# ------------------------------------------------------------------
# 2. CALLBACK: GitHub torna qui dopo il login
# ------------------------------------------------------------------
@router.get("/callback")
async def auth_callback(code: str, state: str):
    """
    Riceve il codice e lo stato (che contiene "owner:repo").
    """
    # 1. SPACCHETTIAMO i dati originali
    try:
        target_owner, target_repo = state.split(":")
    except ValueError:
        raise HTTPException(status_code=400, detail="Stato non valido. Formato atteso 'owner:repo'")

    async with httpx.AsyncClient() as client:
        # 2. Otteniamo il Token dell'utente che sta facendo la richiesta
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code
            },
            headers={"Accept": "application/json"}
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")

        if not access_token:
            print(f"DEBUG: Token exchange failed. Response: {token_data}")
            raise HTTPException(status_code=400, detail=f"Login fallito: impossibile ottenere token. GitHub dice: {token_data.get('error_description', token_data)}")

    # 3. ESEGUE SOLO LA CLONAZIONE
    try:
        repo_path = perform_cloning(
            owner=target_owner,
            repo=target_repo,
            oauth_token=access_token
        )
        # Ritorniamo info di base per permettere al frontend di chiamare /analyze
        return {
            "status": "cloned",
            "owner": target_owner,
            "repo": target_repo,
            "local_path": repo_path
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


# ------------------------------------------------------------------
# 3. ANALYZE: Endpoint per lanciare l'analisi (dopo clonazione)
# ------------------------------------------------------------------
@router.post("/analyze", response_model=AnalyzeResponse)
def run_analysis(payload: dict = Body(...)):
    """
    Esegue l'analisi su una repo già clonata.
    Payload atteso: {"owner": "...", "repo": "..."}
    """
    owner = payload.get("owner")
    repo = payload.get("repo")

    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Owner e Repo obbligatori")

    try:
        result = perform_initial_scan(owner=owner, repo=repo)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


# ------------------------------------------------------------------
# 4. REGENERATE: Endpoint per lanciare la rigenerazione
# ------------------------------------------------------------------
@router.post("/regenerate", response_model=AnalyzeResponse)
def regenerate_analysis(previous_analysis: AnalyzeResponse = Body(...)):
    """
    Lancia la rigenerazione su una repo già clonata.
    Riceve il risultato della scansione precedente (AnalyzeResponse) per evitare di rifarla.
    """
    try:
        # Estraiamo owner e repo dalla stringa "owner/repo"
        if "/" not in previous_analysis.repository:
            raise ValueError("Formato repository non valido. Atteso 'owner/repo'")

        owner, repo = previous_analysis.repository.split("/", 1)

        result = perform_regeneration(owner=owner, repo=repo, previous_analysis=previous_analysis)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


# ------------------------------------------------------------------
# 5. DOWNLOAD: Endpoint per scaricare lo zip della repo
# ------------------------------------------------------------------
@router.post("/download")
def download_repo(payload: dict = Body(...)):
    """
    Scarica lo zip della repository clonata.
    Payload atteso: {"owner": "...", "repo": "..."}
    """
    owner = payload.get("owner")
    repo = payload.get("repo")

    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Owner e Repo obbligatori")

    try:
        zip_path = perform_download(owner=owner, repo=repo)

        # Ritorniamo il file. filename imposta il nome del file scaricato dal browser
        return FileResponse(
            path=zip_path,
            filename=f"{owner}_{repo}.zip",
            media_type='application/zip'
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")