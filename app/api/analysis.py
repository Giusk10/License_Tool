from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, LicenseIssue
from app.services.github_client import clone_repo
from app.services.scancode_service import (
    run_scancode,
    detect_main_license_scancode,
    extract_file_licenses_scancode,
)
from app.services.compatibility import check_compatibility
from app.services.llm_helper import enrich_with_llm_suggestions
from app.services.report_service import generate_report


router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_repository(payload: AnalyzeRequest):
    # 1) Clona il repo
    clone_result = clone_repo(payload.owner, payload.repo)
    if not clone_result.success:
        raise HTTPException(
            status_code=400,
            detail=f"Errore clonazione: {clone_result.error}",
        )

    repo_path = clone_result.repo_path

    # 2) ScanCode su tutto il progetto
    scan_data = run_scancode(repo_path)

    # 3) Rileva licenza principale
    main_license = detect_main_license_scancode(scan_data)

    # 4) Estrai licenze per singolo file
    file_licenses = extract_file_licenses_scancode(scan_data)

    # 5) Verifica compatibilità
    compatibility = check_compatibility(main_license, file_licenses)

    # 6) Aggiungi suggerimenti AI
    enriched_issues = enrich_with_llm_suggestions(compatibility["issues"])

    # 7) Converti in oggetti Pydantic per report + risposta
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

    # 8) Genera report testo su disco
    report_path = generate_report(repo_path, main_license, license_issue_models)

    # 9) Risposta JSON
    return AnalyzeResponse(
        repository=f"{payload.owner}/{payload.repo}",
        main_license=main_license,
        issues=license_issue_models,
        report_path=report_path,
    )
