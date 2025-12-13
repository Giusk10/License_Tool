# app/api/analysis.py
import httpx
from fastapi import APIRouter, HTTPException, Body, UploadFile, Form, File
from fastapi.responses import RedirectResponse, FileResponse
from app.utility.config import CALLBACK_URL
from app.services.analysis_workflow import perform_cloning, perform_initial_scan, perform_regeneration, perform_upload_zip
from app.services.dowloader.download_service import perform_download
from app.models.schemas import AnalyzeResponse
from app.services.github.Encrypted_Auth_Info import github_auth_credentials

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

    # Recupera le credenziali GitHub
    GITHUB_CLIENT_ID = github_auth_credentials("CLIENT_ID")

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

    # Recupera le credenziali GitHub
    GITHUB_CLIENT_ID = github_auth_credentials("CLIENT_ID")
    GITHUB_CLIENT_SECRET = github_auth_credentials("CLIENT_SECRET")

    try:
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
            raise HTTPException(status_code=400, detail=f"Failed login: couldn't get token. From GitHub: {token_data.get('error_description', token_data)}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"An error occurred while trying to reach GitHub: {str(exc)}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected GitHub error: {str(exc)}")

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
# 2.1 ZIP: Endpoint per testare lo zip (opzionale)
# ------------------------------------------------------------------
@router.post("/zip")
def upload_zip(
        # Form(...) è obbligatorio quando si usa File(...) nello stesso endpoint
        owner: str = Form(...),
        repo: str = Form(...),
        uploaded_file: UploadFile = File(...)
):
    try:
        repo_path = perform_upload_zip(
            owner=owner,
            repo=repo,
            uploaded_file=uploaded_file
        )

        return {
            "status": "cloned_from_zip",
            "owner": owner,
            "repo": repo,
            "local_path": repo_path,
        }

    except HTTPException:
        # Se perform_upload_zip lancia già un 400 o 500 specifico,
        # lo rilanciamo così com'è senza modificarlo.
        raise

    except ValueError as ve:
        # Se il service lancia ValueError (non gestito come HTTP), diventa un 400
        raise HTTPException(status_code=400, detail=str(ve))

    except Exception as e:
        # Solo gli errori imprevisti diventano 500
        print(f"Errore critico in upload_zip: {e}") # Logga l'errore vero per debug
        raise HTTPException(status_code=500, detail=f"Errore interno imprevisto: {str(e)}")
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