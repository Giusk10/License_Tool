"""
Analysis Controller Module.

This module manages the API endpoints for repository analysis.
It includes functionality for GitHub OAuth authentication, repository cloning,
ZIP file uploads, license analysis execution, and report regeneration.
"""

from typing import Dict
import httpx
from fastapi import APIRouter, HTTPException, Body, UploadFile, Form, File
from fastapi.responses import RedirectResponse, FileResponse

from app.utility.config import CALLBACK_URL
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
# 1. CLONING FLOW
# ------------------------------------------------------------------

@router.post("/clone")
def clone_repository(payload: Dict[str, str] = Body(...)) -> Dict[str, str]:
    """
    Clones a GitHub repository.

    Args:
        payload (Dict[str, str]): JSON body containing "owner" and "repo".

    Returns:
        Dict[str, str]: A dictionary containing the cloning status and local path details.

    Raises:
        HTTPException:
            - 400: If cloning fails due to invalid parameters.
            - 500: For generic internal server errors during cloning.
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
# 2. FILE UPLOAD
# ------------------------------------------------------------------

@router.post("/zip")
def upload_zip(
        owner: str = Form(...),
        repo: str = Form(...),
        uploaded_file: UploadFile = File(...)
) -> Dict[str, str]:
    """
    Uploads a ZIP file containing source code as an alternative to Git cloning.

    Args:
        owner (str): The name/owner to assign to the uploaded project.
        repo (str): The repository name to assign.
        uploaded_file (UploadFile): The ZIP file containing the source code.

    Returns:
        Dict[str, str]: A dictionary containing the upload status and local path.

    Raises:
        HTTPException:
            - 400: If the file is invalid or processing fails.
            - 500: If an internal server error occurs.
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
        # Re-raise existing HTTP exceptions
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Error: {str(e)}") from e


# ------------------------------------------------------------------
# 3. ANALYSIS & REGENERATION
# ------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
def run_analysis(payload: Dict[str, str] = Body(...)) -> AnalyzeResponse:
    """
    Executes the initial license analysis on a prepared repository.

    The repository must have been previously cloned (via /auth/start) or
    uploaded (via /zip).

    Args:
        payload (Dict[str, str]): JSON body containing "owner" and "repo".

    Returns:
        AnalyzeResponse: The detailed analysis result.

    Raises:
        HTTPException:
            - 400: If parameters are missing or invalid.
            - 500: If the analysis fails.
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
    Regenerates the analysis based on previous results.

    This is typically used to apply LLM-based corrections or refine the
    compatibility check without re-scanning the entire file system.

    Args:
        previous_analysis (AnalyzeResponse): The result of the previous scan.

    Returns:
        AnalyzeResponse: The updated analysis result.

    Raises:
        HTTPException:
            - 400: If the repository format in the previous analysis is invalid.
            - 500: If regeneration fails.
    """
    try:
        # Extract owner and repo from the "owner/repo" string in the response object
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
    Generates and returns a downloadable ZIP archive of the repository.

    Args:
        payload (Dict[str, str]): JSON body containing "owner" and "repo".

    Returns:
        FileResponse: The ZIP file containing the repository.

    Raises:
        HTTPException:
            - 400: If parameters are missing.
            - 500: If the ZIP generation fails.
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
# 5. LICENSE SUGGESTION
# ------------------------------------------------------------------

@router.post("/suggest-license", response_model=LicenseSuggestionResponse)
def suggest_license(
    requirements: LicenseRequirementsRequest = Body(...)
) -> LicenseSuggestionResponse:
    """
    Suggests an appropriate license based on user requirements.

    This endpoint is used when no main license is detected or when there are
    unknown licenses. The user provides their requirements and constraints,
    and the AI suggests the most suitable license.

    Args:
        requirements (LicenseRequirementsRequest): User's license requirements and constraints.

    Returns:
        LicenseSuggestionResponse: The suggested license with explanation and alternatives.

    Raises:
        HTTPException:
            - 500: If the AI suggestion fails.
    """
    try:
        # Convert Pydantic model to dict for processing
        requirements_dict = requirements.model_dump()

        # Get AI suggestion
        suggestion = suggest_license_based_on_requirements(requirements_dict)

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



