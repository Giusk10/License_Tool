"""
This module orchestrates the entire license analysis pipeline: it handles
the sequence of cloning, scanning, filtering, compatibility checking, and
code regeneration.
"""

import shutil
import tempfile
import zipfile
from fastapi import UploadFile, HTTPException
from app.models.schemas import AnalyzeResponse, LicenseIssue
from app.services.github_client import clone_repo
from app.services.scancode_service import (
    run_scancode,
    detect_main_license_scancode,
    extract_file_licenses_from_llm,
    filter_with_regex,
)
from app.services.compatibility import check_compatibility
from app.services.suggestion import enrich_with_llm_suggestions
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

def perform_upload_zip(owner: str, repo: str, uploaded_file: UploadFile) -> str:
    """
    Gestisce l'upload di uno zip, estrae i file e gestisce la struttura delle directory.
    Se lo zip contiene una singola cartella root (es. repo-main/), il contenuto viene
    spostato direttamente nella target_dir {owner}_{repo}, eliminando il livello extra.
    """
    target_dir = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    # 1. Pulizia preventiva: Rimuovi la directory di destinazione se esiste
    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir)
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Errore durante la pulizia della directory esistente: {e}"
            )

    # Validazione estensione
    if not uploaded_file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Il file caricato deve essere un archivio .zip")

    try:
        # 2. Uso di una directory temporanea per l'estrazione
        # Questo ci permette di analizzare la struttura PRIMA di decidere dove mettere i file definitivi
        with tempfile.TemporaryDirectory() as temp_dir:

            with zipfile.ZipFile(uploaded_file.file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Analisi del contenuto estratto
            extracted_items = os.listdir(temp_dir)

            # Filtriamo per ignorare file nascosti di sistema (es. __MACOSX o .DS_Store) che potrebbero falsare il conteggio
            visible_items = [item for item in extracted_items if not item.startswith('__') and not item.startswith('.')]

            source_to_move = temp_dir

            # CASO A: Lo zip contiene una singola cartella (es. 'my-repo-main')
            # Spostiamo quella cartella rinominandola in target_dir
            if len(visible_items) == 1:
                potential_root = os.path.join(temp_dir, visible_items[0])
                if os.path.isdir(potential_root):
                    source_to_move = potential_root

            # CASO B: Lo zip è "piatto" (file sparsi nella root)
            # Spostiamo tutto il contenuto di temp_dir in target_dir

            # shutil.move(src, dst) se dst non esiste, rinomina src in dst.
            # Poiché abbiamo cancellato target_dir all'inizio, questo è sicuro.
            shutil.copytree(source_to_move, target_dir)

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Il file fornito è un file zip corrotto o non valido.")
    except Exception as e:
        # Pulizia extra in caso di errore (se target_dir è stata creata parzialmente)
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        raise HTTPException(status_code=500, detail=f"Errore durante l'elaborazione dello zip: {str(e)}")
    finally:
        uploaded_file.file.close()

    return os.path.abspath(target_dir)

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

    # 4) Filters false positives using regex
    llm_clean = filter_with_regex(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses_from_llm(llm_clean)

    # 5) Checks license compatibility between the main license and file-level licenses
    compatibility = check_compatibility(main_license, file_licenses)

    # 6) Suggerimenti AI (senza rigenerazione per ora)
    # Passiamo una mappa vuota perché non abbiamo ancora rigenerato nulla
    enriched_issues = enrich_with_llm_suggestions(main_license, compatibility["issues"], {})

    # 7) Maps the issues to Pydantic models
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
            files_to_regenerate.append(issue)
            # Esempio filtro estensioni
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
                        detected_license=issue.detected_license,
                        licenses= issue.licenses
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

            main_license, path = detect_main_license_scancode(scan_raw) # Main license non dovrebbe cambiare

            llm_clean = filter_with_regex(scan_raw, main_license, path)

            file_licenses = extract_file_licenses_from_llm(llm_clean)
            compatibility = check_compatibility(main_license, file_licenses)

            # Aggiorniamo la lista di issues con i nuovi risultati
            # check_compatibility ritorna un dict con "issues": [dict, dict...]
            current_issues_dicts = compatibility["issues"]
        else:
            # If no files were actually regenerated, keep previous issues
            # We convert Pydantic models back to dicts for consistency with the enrichment function
            current_issues_dicts = [i.dict() for i in previous_analysis.issues]

    else:
        # If no incompatible files were found, keep previous issues
        current_issues_dicts = [i.dict() for i in previous_analysis.issues]

    # 6) Suggerimenti AI (con mappa rigenerati)
    # enrich_with_llm_suggestions si aspetta una lista di DICT
    enriched_issues = enrich_with_llm_suggestions(main_license, current_issues_dicts, regenerated_files_map)

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