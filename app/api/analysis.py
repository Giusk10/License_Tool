from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, LicenseIssue
from app.services.github_client import clone_repo
from app.services.scancode_service import run_scancode
from app.services.license_detector import detect_main_license_scancode, extract_file_licenses_scancode
from app.services.compatibility import check_compatibility
from app.services.llm_helper import enrich_with_llm_suggestions
from app.services.report_service import generate_report

router = APIRouter()

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_repository(payload: AnalyzeRequest):
    # 1) Clona il repo
    clone_result = clone_repo(payload.owner, payload.repo)
    if not clone_result.success:
        raise HTTPException(status_code=400, detail=f"Errore clonazione: {clone_result.error}")

    repo_path = clone_result.repo_path

    # 2) ScanCode su tutto il progetto
    sc_data = run_scancode(repo_path)

    # 3) Licenza principale
    main_license = detect_main_license_scancode(sc_data)

    # 4) Licenze file-per-file
    file_licenses = extract_file_licenses_scancode(sc_data)

    # 5) Compatibilità
    compatibility = check_compatibility(main_license, file_licenses)

    # 6) Aggiungi suggerimenti AI
    enriched_issues = enrich_with_llm_suggestions(compatibility["issues"])

    # 7) Output report su disco
    report_path = generate_report(repo_path, main_license, [
        LicenseIssue(
            file_path=i["file_path"],
            detected_license=i["detected_license"],
            compatible=i["compatible"],
            reason=i["reason"],
            suggestion=i.get("suggestion")
        )
        for i in enriched_issues
    ])

    # 8) Risposta finale JSON
    return AnalyzeResponse(
        repository=f"{payload.owner}/{payload.repo}",
        main_license=main_license,
        issues=[
            LicenseIssue(
                file_path=i["file_path"],
                detected_license=i["detected_license"],
                compatible=i["compatible"],
                reason=i["reason"],
                suggestion=i.get("suggestion")
            )
            for i in enriched_issues
        ],
        report_path=report_path
    )
