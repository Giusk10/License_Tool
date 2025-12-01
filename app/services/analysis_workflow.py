"""
This module orchestrates the entire license analysis pipeline: it handles
the sequence of cloning, scanning, filtering, compatibility checking, and
code regeneration.
"""

from app.models.schemas import AnalyzeResponse, LicenseIssue
from app.services.github_client import clone_repo
from app.services.scancode_service import (
    run_scancode,
    detect_main_license_scancode,
    extract_file_licenses_from_llm,
    filter_with_llm,
)
from app.services.compatibility import check_compatibility
from app.services.llm_helper import enrich_with_llm_suggestions
from app.services.report_service import generate_report
from app.core.config import CLONE_BASE_DIR
import os


def perform_cloning(owner: str, repo: str, oauth_token: str) -> str:
    """
    Executes the repository cloning process only.

    Args:
        owner (str): The owner of the GitHub repository.
        repo (str): The repository name.
        oauth_token (str): The OAuth token for authentication.

    Returns:
        str: The local file system path of the cloned repository.

    Raises:
        ValueError: If the cloning process fails.
    """
    clone_result = clone_repo(owner, repo, oauth_token)
    if not clone_result.success:
        raise ValueError(f"An error occurred while cloning the repository: {clone_result.error}")

    return clone_result.repo_path


def perform_initial_scan(owner: str, repo: str) -> AnalyzeResponse:
    """
    Performs the initial analysis on an already cloned repository.

    Args:
        owner (str): The owner of the GitHub repository.
        repo (str): The repository name.

    Returns:
        AnalyzeResponse: An object containing the analysis results, issues, and report path.
    """
    # 1) Locates the repository (assuming it was cloned previously)
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    if not os.path.exists(repo_path):
        raise ValueError(f"Couldn't find the specified repository in {repo_path}. Try cloning first.")

    # 2) Runs ScanCode to detect raw license data
    scan_raw = run_scancode(repo_path)

    # 3) Identifies the main project license
    main_license, path_license = detect_main_license_scancode(scan_raw)

    # 4) Filters false positives using an LLM
    llm_clean = filter_with_llm(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses_from_llm(llm_clean)

    # 5) Checks license compatibility between the main license and file-level licenses
    compatibility = check_compatibility(main_license, file_licenses)

    # 6) Generates AI-based suggestions for issues
    # At this stage, no files have been regenerated yet, so we pass an empty map
    enriched_issues = enrich_with_llm_suggestions(compatibility["issues"], {})

    # 7) Maps the issues to Pydantic models
    license_issue_models = [
        LicenseIssue(
            file_path=i["file_path"],
            detected_license=i["detected_license"],
            compatible=i["compatible"],
            reason=i.get("reason"),
            suggestion=i.get("suggestion"),
            regenerated_code_path=i.get("regenerated_code_path"),
        )
        for i in enriched_issues
    ]

    # 8) Creates a persistent report on disk
    report_path = generate_report(repo_path, main_license, license_issue_models)

    return AnalyzeResponse(
        repository=f"{owner}/{repo}",
        main_license=main_license,
        issues=license_issue_models,
        report_path=report_path,
    )


def perform_regeneration(owner: str, repo: str, previous_analysis: AnalyzeResponse) -> AnalyzeResponse:
    """
    Executes the code regeneration workflow for incompatible files.

    This function iterates through identified issues in the `previous_analysis`.
    If a file is marked as incompatible, it invokes the LLM to rewrite the code
    to be compliant with the main license.

    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        previous_analysis (AnalyzeResponse): The result of the initial scan.

    Returns:
        AnalyzeResponse: Updated analysis results reflecting the regeneration attempts.
    """
    # Locates the repository
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")
    print("\n\n")
    print(repo_path)
    print("\n\n")

    if not os.path.exists(repo_path):
        raise ValueError(f"Couldn't find the specified repository in {repo_path}. Try running the initial scan first.")

    # Retrieves data from the previous analysis
    main_license = previous_analysis.main_license

    # --- REGENERATION LOGIC ---
    regenerated_files_map = {}  # file_path -> new_code_content
    files_to_regenerate = []

    # Identifies incompatible files, excluding non-code files
    for issue in previous_analysis.issues:
        if not issue.compatible:
            fpath = issue.file_path
            if not fpath.lower().endswith(('.txt', '.md', 'license', 'copying', '.rst')):
                files_to_regenerate.append(issue)

    # Processes each incompatible file for regeneration
    if files_to_regenerate:
        print(f"Found {len(files_to_regenerate)} incompatible files that have to be regenerated...")
        from app.services.code_generator import regenerate_code

        for issue in files_to_regenerate:
            fpath = issue.file_path

            # Path normalization check to handle potential inconsistencies between
            # relative and absolute paths
            repo_name = os.path.basename(os.path.normpath(repo_path))
            if fpath.startswith(f"{repo_name}/"):
                abs_path = os.path.join(os.path.dirname(repo_path), fpath)
            else:
                abs_path = os.path.join(repo_path, fpath)

            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        original_content = f.read()

                    # Calls the LLM to regenerate the code
                    new_code = regenerate_code(
                        code_content=original_content,
                        main_license=main_license,
                        detected_license=issue.detected_license
                    )

                    # Validates and writes back the regenerated code
                    if new_code and len(new_code.strip()) > 10:
                        with open(abs_path, "w", encoding="utf-8") as f:
                            f.write(new_code)

                        regenerated_files_map[fpath] = new_code
                        print(f"Regenerated code: {fpath} (Length: {len(new_code)})")
                    else:
                        print(f"Failed regeneration or invalid code for {fpath}")
                except Exception as e:
                    print(f"An error occurred while regenerating {fpath}: {e}")

        # Partial re-scan is needed to update the compatibility status
        if regenerated_files_map:
            print("Performing the scan again after regeneration...")
            scan_raw = run_scancode(repo_path)
            main_license, path = detect_main_license_scancode(scan_raw)  # Should be unchanged
            llm_clean = filter_with_llm(scan_raw, main_license, path)
            print("\n\n")
            print(llm_clean)
            file_licenses = extract_file_licenses_from_llm(llm_clean)
            compatibility = check_compatibility(main_license, file_licenses)

            print("\n\n")
            print(compatibility)

            # Updates the current issues with the new compatibility results
            current_issues_dicts = compatibility["issues"]
        else:
            # If no files were actually regenerated, keep previous issues
            # We convert Pydantic models back to dicts for consistency with the enrichment function
            current_issues_dicts = [i.dict() for i in previous_analysis.issues]

    else:
        # If no incompatible files were found, keep previous issues
        current_issues_dicts = [i.dict() for i in previous_analysis.issues]

    # Enriches issues with LLM suggestions based on the regeneration results
    enriched_issues = enrich_with_llm_suggestions(current_issues_dicts, regenerated_files_map)

    # Maps issues to Pydantic models
    license_issue_models = [
        LicenseIssue(
            file_path=i["file_path"],
            detected_license=i["detected_license"],
            compatible=i["compatible"],
            reason=i.get("reason"),
            suggestion=i.get("suggestion"),
            regenerated_code_path=i.get("regenerated_code_path"),
        )
        for i in enriched_issues
    ]

    # Generates a new report reflecting the updated analysis
    report_path = generate_report(repo_path, main_license, license_issue_models)

    return AnalyzeResponse(
        repository=f"{owner}/{repo}",
        main_license=main_license,
        issues=license_issue_models,
        report_path=report_path,
    )