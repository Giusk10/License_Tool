"""
Analysis Workflow Module.

This module manages the core analysis workflows for the application.
It acts as the orchestrator for:
- Repository cloning (via GitHub).
- ZIP file uploads and extraction.
- Initial license scanning and compatibility checking.
- The AI-based code regeneration loop to fix license conflicts.
"""
import json
import os
import shutil
import tempfile
import zipfile

from fastapi import UploadFile, HTTPException
from app.models.schemas import AnalyzeResponse, LicenseIssue
from app.services.github.github_client import clone_repo
from app.services.scanner.detection import (
    run_scancode,
    detect_main_license_scancode,
    extract_file_licenses
)
from app.services.scanner.filter import filter_licenses
from app.services.compatibility import check_compatibility
from app.services.llm.suggestion import enrich_with_llm_suggestions
from app.services.llm.license_recommender import needs_license_suggestion
from app.services.scanner.license_ranking import choose_most_permissive_license_in_file
from app.utility.config import CLONE_BASE_DIR
from app.services.llm.code_generator import regenerate_code


def perform_cloning(owner: str, repo: str) -> str:
    """
    Executes the repository cloning process.

    This function relies on the GitHub client service to clone the remote
    repository to the local file system.

    Args:
        owner (str): The repository owner (username or organization).
        repo (str): The repository name.
        oauth_token (str): The OAuth token for authentication.

    Returns:
        str: The local file system path of the cloned repository.

    Raises:
        ValueError: If the cloning operation fails.
    """
    clone_result = clone_repo(owner, repo)
    if not clone_result.success:
        raise ValueError(f"Cloning error: {clone_result.error}")

    return clone_result.repo_path


def perform_upload_zip(owner: str, repo: str, uploaded_file: UploadFile) -> str:
    """
    Handles the upload, extraction, and normalization of a source code ZIP file.

    It ensures the target directory is clean, extracts the zip, and normalizes
    the directory structure (e.g., handling single root folders inside archives).

    Args:
        owner (str): The owner name to assign to the project.
        repo (str): The repository name to assign.
        uploaded_file (UploadFile): The ZIP file uploaded by the user.

    Returns:
        str: The absolute local path where the code has been extracted.

    Raises:
        HTTPException:
            - 400: If the file is not a zip or is corrupted.
            - 500: If filesystem errors occur during cleanup or extraction.
    """
    target_dir = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    # 1. Preventive cleanup of existing directory
    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir)
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error cleaning up existing directory: {e}"
            ) from e

    # Validate file extension
    if not uploaded_file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="The uploaded file must be a .zip archive")

    try:
        # 2. Use a temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:

            with zipfile.ZipFile(uploaded_file.file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            extracted_items = os.listdir(temp_dir)
            visible_items = [
                item for item in extracted_items
                if not item.startswith('__') and not item.startswith('.')
            ]

            source_to_move = temp_dir

            # CASE A: Zip contains a single root folder (e.g., 'my-repo-main')
            # We want to move the *content* of that folder, not the folder itself.
            if len(visible_items) == 1:
                potential_root = os.path.join(temp_dir, visible_items[0])
                if os.path.isdir(potential_root):
                    source_to_move = potential_root

            # CASE B: Move contents to the final target_dir
            shutil.copytree(source_to_move, target_dir)

    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=400,
            detail="The provided file is corrupted or not a valid zip file."
        ) from exc
    except Exception as e:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        raise HTTPException(
            status_code=500,
            detail=f"Error while processing zip file: {str(e)}"
        ) from e
    finally:
        uploaded_file.file.close()

    return os.path.abspath(target_dir)


def perform_initial_scan(owner: str, repo: str) -> AnalyzeResponse:
    """
    Executes the initial analysis on an already cloned/uploaded repository.

    Steps:
    1. Runs ScanCode to detect raw license data.
    2. Identifies the project's main license.
    3. Filters ScanCode results using LLM and regex rules.
    4. Checks compatibility between file licenses and the main license.
    5. Enriches issues with AI-generated suggestions.

    Args:
        owner (str): The repository owner.
        repo (str): The repository name.

    Returns:
        AnalyzeResponse: The complete analysis result including issues and suggestions.

    Raises:
        ValueError: If the repository directory does not exist.
    """
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    if not os.path.exists(repo_path):
        raise ValueError(f"Repository not found at {repo_path}. Please clone it first.")

    # 2) Execute ScanCode
    scan_raw = run_scancode(repo_path)

    # 3) Detect Main License
    license_result = detect_main_license_scancode(scan_raw)

    # Handle both return types: tuple (license, path) or string "UNKNOWN"
    if isinstance(license_result, tuple):
        main_license, path_license = license_result
    else:
        main_license = license_result
        path_license = None

    # 4) Filtering
    llm_clean = filter_licenses(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses(llm_clean)

    print(json.dumps(file_licenses, indent=2))

    remove_or_clauses = choose_most_permissive_license_in_file(file_licenses)

    # 5) Compatibility Check
    compatibility = check_compatibility(main_license, remove_or_clauses)

    # 6) AI Suggestions
    enriched_issues = enrich_with_llm_suggestions(main_license, compatibility["issues"], {})

    # 7) Check if license suggestion is needed
    needs_suggestion = needs_license_suggestion(main_license, enriched_issues)

    # 8) Map to Pydantic Models
    license_issue_models = [
        LicenseIssue(
            file_path=i["file_path"],
            detected_license=i["detected_license"],
            compatible=i["compatible"],
            reason=i.get("reason"),
            suggestion=i.get("suggestion"),
            licenses=i.get("licenses"),
            regenerated_code_path=i.get("regenerated_code_path"),
        )
        for i in enriched_issues
    ]

    return AnalyzeResponse(
        repository=f"{owner}/{repo}",
        main_license=main_license,
        issues=license_issue_models,
        needs_license_suggestion=needs_suggestion,
    )


def perform_regeneration(
    owner: str,
    repo: str,
    previous_analysis: AnalyzeResponse
) -> AnalyzeResponse:
    """
    Executes the code regeneration workflow on an already analyzed repository.

    Steps:
    1. Identifies incompatible files from the previous analysis.
    2. Calls the LLM to regenerate code compliant with the main license.
    3. Re-scans the repository to verify improvements.
    4. Returns updated analysis results.

    Args:
        owner (str): The repository owner.
        repo (str): The repository name.
        previous_analysis (AnalyzeResponse): Results from the initial scan.

    Returns:
        AnalyzeResponse: The updated analysis result containing regenerated code paths.

    Raises:
        ValueError: If the repository directory does not exist.
    """
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    if not os.path.exists(repo_path):
        raise ValueError(f"Repository not found at {repo_path}. Please run initial scan first.")

    main_license = previous_analysis.main_license

    # 1. Identify and regenerate incompatible files
    regenerated_files_map = _regenerate_incompatible_files(
        repo_path,
        main_license,
        previous_analysis.issues
    )

    # 2. Rescan or Fallback
    if regenerated_files_map:
        print("Re-running post-regeneration scan...")
        current_issues_dicts = _rescan_repository(
            repo_path,
            main_license,
            regenerated_files_map
        )
    else:
        # Fallback: convert existing Pydantic models to dicts if no changes occurred
        current_issues_dicts = [i.model_dump() for i in previous_analysis.issues]

    # 3. Final Enrichment
    enriched_issues = enrich_with_llm_suggestions(
        main_license,
        current_issues_dicts,
        regenerated_files_map
    )

    # 4. Check if license suggestion is still needed after regeneration
    needs_suggestion = needs_license_suggestion(main_license, enriched_issues)

    license_issue_models = [
        LicenseIssue(
            file_path=i["file_path"],
            detected_license=i["detected_license"],
            compatible=i["compatible"],
            reason=i.get("reason"),
            suggestion=i.get("suggestion"),
            licenses=i.get("licenses"),
            regenerated_code_path=i.get("regenerated_code_path"),
        )
        for i in enriched_issues
    ]

    return AnalyzeResponse(
        repository=f"{owner}/{repo}",
        main_license=main_license,
        issues=license_issue_models,
        needs_license_suggestion=needs_suggestion,
    )


def _regenerate_incompatible_files(
    repo_path: str,
    main_license: str,
    issues: list[LicenseIssue]
) -> dict:
    """
    Internal helper to identify incompatible files and attempt regeneration via LLM.

    Args:
        repo_path (str): Path to the repository.
        main_license (str): The target license.
        issues (list[LicenseIssue]): List of issues from previous scan.

    Returns:
        dict: A map {file_path: new_content} of successfully regenerated files.
    """
    regenerated_map = {}

    # Filter files to ignore (docs, notices, etc.)
    ignore_suffixes = ('.md', '.txt', '.rst', 'THIRD-PARTY-NOTICE', 'NOTICE')

    files_to_process = [
        issue for issue in issues
        if not issue.compatible and not issue.file_path.endswith(ignore_suffixes)
    ]

    if not files_to_process:
        return {}

    print(f"Found {len(files_to_process)} incompatible files to regenerate...")

    for issue in files_to_process:
        fpath = issue.file_path

        # Resolve absolute path
        repo_name = os.path.basename(os.path.normpath(repo_path))
        if fpath.startswith(f"{repo_name}/"):
            abs_path = os.path.join(os.path.dirname(repo_path), fpath)
        else:
            abs_path = os.path.join(repo_path, fpath)

        if not os.path.exists(abs_path):
            continue

        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()

            # Ensure licenses is a string, not None
            licenses_str = issue.licenses if issue.licenses else "MIT, Apache-2.0, BSD-3-Clause"

            new_code = regenerate_code(
                code_content=original_content,
                main_license=main_license,
                detected_license=issue.detected_license,
                licenses=licenses_str
            )

            if new_code and len(new_code.strip()) > 10:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(new_code)

                regenerated_map[fpath] = new_code
                print(f"Regenerated: {fpath} (Length: {len(new_code)})")
            else:
                print(f"Regeneration failed or invalid code for {fpath}")

        except OSError as e:
            print(f"IO Error regenerating {fpath}: {e}")
        # Broad exception caught intentionally to prevent stopping the loop
        # pylint: disable=broad-exception-caught
        except Exception as e:
            print(f"Unexpected error regenerating {fpath}: {e}")

    return regenerated_map


def _rescan_repository(
    repo_path: str,
    main_license: str,
    regenerated_map: dict
) -> list[dict]:
    """
    Internal helper to re-run ScanCode and compatibility checks.

    Args:
        repo_path (str): Path to the repository.
        main_license (str): The main license to check against.
        regenerated_map (dict): Map of regenerated files (passed for context/future use).

    Returns:
        list[dict]: A list of updated issue dictionaries.
    """
    # Prevent unused argument warning (kept for debugging or future logic extensions)
    _ = regenerated_map

    scan_raw = run_scancode(repo_path)

    # Detect license path again to ensure accuracy
    license_result = detect_main_license_scancode(scan_raw)

    # Handle both return types: tuple (license, path) or string "UNKNOWN"
    if isinstance(license_result, tuple):
        _, path_license = license_result
    else:
        path_license = None

    llm_clean = filter_licenses(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses(llm_clean)

    compatibility = check_compatibility(main_license, file_licenses)

    return compatibility["issues"]
