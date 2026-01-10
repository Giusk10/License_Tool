"""
Analysis Controller Module.

Questo modulo gestisce gli endpoint API per l'analisi dei repository.
Include funzionalità per l'autenticazione GitHub OAuth, clonazione di repository,
upload di file ZIP, esecuzione dell'analisi delle licenze e rigenerazione dei report.
"""

from typing import Dict
from fastapi import APIRouter, HTTPException, Body, UploadFile, Form, File
from fastapi.responses import RedirectResponse, FileResponse

from app.services.analysis_workflow import (
    perform_cloning,
    perform_initial_scan,
    perform_regeneration,
    perform_upload_zip
)
from app.services.downloader.download_service import perform_download
from app.models.schemas import (
    AnalyzeResponse,
    LicenseRequirementsRequest,
    LicenseSuggestionResponse
)
from app.services.llm.license_recommender import suggest_license_based_on_requirements

router = APIRouter()

# ------------------------------------------------------------------
# 1. FLUSSO DI CLONAZIONE
# ------------------------------------------------------------------

@router.post("/clone")
def clone_repository(payload: Dict[str, str] = Body(...)) -> Dict[str, str]:
    """
    Clona un repository GitHub.

    Args:
        payload (Dict[str, str]): Corpo JSON contenente "owner" e "repo".

    Returns:
        Dict[str, str]: Un dizionario contenente lo stato della clonazione e i dettagli del percorso locale.

    Raises:
        HTTPException:
            - 400: Se la clonazione fallisce a causa di parametri non validi.
            - 500: Per errori interni generici del server durante la clonazione.
    """
    owner = payload.get("owner")
    repo = payload.get("repo")

    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Owner and Repo are required")

    try:
        repo_path = perform_cloning(
            owner=owner,
            repo=repo,
        )

        return {
            "status": "cloned",
            "owner": owner,
            "repo": repo,
            "local_path": str(repo_path)
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


# ------------------------------------------------------------------
# 2. CARICAMENTO FILE
# ------------------------------------------------------------------

@router.post("/zip")
def upload_zip(
        owner: str = Form(...),
        repo: str = Form(...),
        uploaded_file: UploadFile = File(...)
) -> Dict[str, str]:
    """
    Carica un file ZIP contenente codice sorgente come alternativa alla clonazione Git.

    Args:
        owner (str): Il nome/proprietario da assegnare al progetto caricato.
        repo (str): Il nome del repository da assegnare.
        uploaded_file (UploadFile): Il file ZIP contenente il codice sorgente.

    Returns:
        Dict[str, str]: Un dizionario contenente lo stato del caricamento e il percorso locale.

    Raises:
        HTTPException:
            - 400: Se il file non è valido o l'elaborazione fallisce.
            - 500: Se si verifica un errore interno del server.
    """
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
            "local_path": str(repo_path),
        }

    except HTTPException:
        # Rilancia le eccezioni HTTP esistenti
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Error: {str(e)}") from e


# ------------------------------------------------------------------
# 3. ANALISI & RIGENERAZIONE
# ------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
def run_analysis(payload: Dict[str, str] = Body(...)) -> AnalyzeResponse:
    """
    Esegue l'analisi iniziale delle licenze su un repository preparato.

    Il repository deve essere stato precedentemente clonato (tramite /auth/start) o
    caricato (tramite /zip).

    Args:
        payload (Dict[str, str]): Corpo JSON contenente "owner" e "repo".

    Returns:
        AnalyzeResponse: Il risultato dettagliato dell'analisi.

    Raises:
        HTTPException:
            - 400: Se i parametri mancano o non sono validi.
            - 500: Se l'analisi fallisce.
    """
    owner = payload.get("owner")
    repo = payload.get("repo")

    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Owner and Repo are required")

    try:
        result = perform_initial_scan(owner=owner, repo=repo)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


@router.post("/regenerate", response_model=AnalyzeResponse)
def regenerate_analysis(previous_analysis: AnalyzeResponse = Body(...)) -> AnalyzeResponse:
    """
    Rigenera l'analisi basandosi sui risultati precedenti.

    Questo viene tipicamente utilizzato per applicare correzioni basate su LLM o affinare il
    controllo di compatibilità senza riscansionare l'intero file system.

    Args:
        previous_analysis (AnalyzeResponse): Il risultato della scansione precedente.

    Returns:
        AnalyzeResponse: Il risultato dell'analisi aggiornato.

    Raises:
        HTTPException:
            - 400: Se il formato del repository nell'analisi precedente non è valido.
            - 500: Se la rigenerazione fallisce.
    """
    try:
        # Estrae owner e repo dalla stringa "owner/repo" nell'oggetto di risposta
        if "/" not in previous_analysis.repository:
            raise ValueError("Invalid repository format. Expected 'owner/repo'")

        owner, repo = previous_analysis.repository.split("/", 1)

        result = perform_regeneration(
            owner=owner,
            repo=repo,
            previous_analysis=previous_analysis
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


# ------------------------------------------------------------------
# 4. DOWNLOAD
# ------------------------------------------------------------------

@router.post("/download")
def download_repo(payload: Dict[str, str] = Body(...)) -> FileResponse:
    """
    Genera e restituisce un archivio ZIP scaricabile del repository.

    Args:
        payload (Dict[str, str]): Corpo JSON contenente "owner" e "repo".

    Returns:
        FileResponse: Il file ZIP contenente il repository.

    Raises:
        HTTPException:
            - 400: Se mancano i parametri.
            - 500: Se la generazione dello ZIP fallisce.
    """
    owner = payload.get("owner")
    repo = payload.get("repo")

    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Owner and Repo are required")

    try:
        zip_path = perform_download(owner=owner, repo=repo)

        return FileResponse(
            path=zip_path,
            filename=f"{owner}_{repo}.zip",
            media_type='application/zip'
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}") from e


# ------------------------------------------------------------------
# 5. SUGGERIMENTO LICENZA
# ------------------------------------------------------------------

@router.post("/suggest-license", response_model=LicenseSuggestionResponse)
def suggest_license(
    requirements: LicenseRequirementsRequest = Body(...)
) -> LicenseSuggestionResponse:
    """
    Suggerisce una licenza appropriata basandosi sui requisiti dell'utente.

    Questo endpoint viene utilizzato quando non viene rilevata alcuna licenza principale o quando ci sono
    licenze sconosciute. L'utente fornisce i propri requisiti e vincoli,
    e l'AI suggerisce la licenza più adatta.

    Args:
        requirements (LicenseRequirementsRequest): Requisiti e vincoli delle licenze dell'utente.

    Returns:
        LicenseSuggestionResponse: La licenza suggerita con spiegazione e alternative.

    Raises:
        HTTPException:
            - 500: Se il suggerimento dell'AI fallisce.
    """
    try:
        # Converte il modello Pydantic in dict per l'elaborazione
        requirements_dict = requirements.model_dump()

        # Estrae le licenze rilevate dai requisiti
        detected_licenses = requirements_dict.pop("detected_licenses", None)

        # Ottiene il suggerimento dell'AI con le licenze rilevate
        suggestion = suggest_license_based_on_requirements(
            requirements_dict,
            detected_licenses=detected_licenses
        )

        return LicenseSuggestionResponse(
            suggested_license=suggestion["suggested_license"],
            explanation=suggestion["explanation"],
            alternatives=suggestion.get("alternatives", [])
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate license suggestion: {str(e)}"
        ) from e



