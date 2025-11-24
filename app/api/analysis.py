# app/api/analysis.py
import httpx
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import RedirectResponse, JSONResponse

from app.core.config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, CALLBACK_URL
from app.services.analysis_workflow import perform_initial_scan, perform_regeneration
from app.models.schemas import AnalyzeResponse

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
@router.get("/callback", response_model=AnalyzeResponse)
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
            raise HTTPException(status_code=400, detail="Login fallito: impossibile ottenere token")

    # 3. LANCIA L'ANALISI INIZIALE (Senza rigenerazione)
    try:
        result = perform_initial_scan(
            owner=target_owner,
            repo=target_repo,
            oauth_token=access_token
        )
        return result

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


# ------------------------------------------------------------------
# 3. REGENERATE: Endpoint per lanciare la rigenerazione
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