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
from app.models.schemas import AnalyzeResponse
from app.services.github.encrypted_Auth_Info import github_auth_credentials

router = APIRouter()


# ------------------------------------------------------------------
# 1. AUTHENTICATION FLOW
# ------------------------------------------------------------------

@router.get("/auth/start")
def start_analysis(owner: str, repo: str) -> RedirectResponse:
    """
    Initiates the OAuth authentication flow with GitHub.

    Constructs the GitHub authorization URL using the client ID and requested
    repository details, then redirects the user to GitHub to approve access.

    Args:
        owner (str): The username or organization name of the repository owner.
        repo (str): The name of the repository.

    Returns:
        RedirectResponse: A redirection to the GitHub OAuth login page.
    """
    # Pack data into a single string to pass through the OAuth 'state' parameter
    state_data = f"{owner.strip()}:{repo.strip()}"

    github_client_id = github_auth_credentials("CLIENT_ID")
    scope = "repo"  # 'repo' scope is needed even for public repos to avoid rate limits

    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={github_client_id}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope={scope}"
        f"&state={state_data}"
    )
    return RedirectResponse(github_url)


@router.get("/callback")
async def auth_callback(code: str, state: str) -> Dict[str, str]:
    """
    Handles the GitHub OAuth callback.

    Exchanges the temporary authorization code for an access token, then
    triggers the cloning of the specified repository.

    Args:
        code (str): The temporary authorization code returned by GitHub.
        state (str): The state parameter containing "owner:repo" passed during initiation.

    Returns:
        Dict[str, str]: A dictionary containing the cloning status and local path details.

    Raises:
        HTTPException:
            - 400: If the state format is invalid or token exchange fails.
            - 502/503: If there are communication errors with GitHub.
            - 500: For generic internal server errors during cloning.
    """
    # 1. Unpack original data
    try:
        target_owner, target_repo = state.split(":")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid state. Expected format 'owner:repo'"
        ) from exc

    github_client_id = github_auth_credentials("CLIENT_ID")
    github_client_secret = github_auth_credentials("CLIENT_SECRET")

    # 2. Exchange Code for Access Token
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": github_client_id,
                    "client_secret": github_client_secret,
                    "code": code
                },
                headers={"Accept": "application/json"}
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")

        if not access_token:
            error_desc = token_data.get('error_description', token_data)
            raise HTTPException(
                status_code=400,
                detail=f"Failed login: couldn't get token. From GitHub: {error_desc}"
            )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"An error occurred while trying to reach GitHub: {str(exc)}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected GitHub error: {str(exc)}"
        ) from exc

    # 3. Perform Cloning
    try:
        repo_path = perform_cloning(
            owner=target_owner,
            repo=target_repo,
            oauth_token=access_token
        )

        return {
            "status": "cloned",
            "owner": target_owner,
            "repo": target_repo,
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
