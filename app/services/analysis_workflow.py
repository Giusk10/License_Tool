# Questo file contiene la TUA logica di business pura, senza FastAPI
from app.models.schemas import AnalyzeResponse, LicenseIssue
from app.services.github_client import clone_repo
from app.services.scancode_service import (
    run_scancode,
    detect_main_license_scancode,
    extract_file_licenses_from_llm, filter_with_llm,
)
from app.services.compatibility import check_compatibility
from app.services.llm_helper import enrich_with_llm_suggestions
from app.services.report_service import generate_report

def run_analysis_logic(owner: str, repo: str, oauth_token: str) -> AnalyzeResponse:
    """
    Esegue l'intera pipeline: Clone -> Scan -> LLM -> Report
    """
    # 1) Clona il repo (con token dinamico)
    clone_result = clone_repo(owner, repo, oauth_token)
    if not clone_result.success:
        raise ValueError(f"Errore clonazione: {clone_result.error}")

    repo_path = clone_result.repo_path

    # 2) Esegui ScanCode
    scan_raw = run_scancode(repo_path)

    # 3) Main License
    main_license = detect_main_license_scancode(scan_raw)

    # 4) Filtro LLM
    llm_clean = filter_with_llm(scan_raw)
    file_licenses = extract_file_licenses_from_llm(llm_clean)

    # 5) Compatibilità (Prima Passata)
    compatibility = check_compatibility(main_license, file_licenses)

    # --- LOGICA DI RIGENERAZIONE ---
    regenerated_files_map = {}  # file_path -> new_code_content
    files_to_regenerate = []

    # Identifica file incompatibili che sono codice sorgente
    # (Escludiamo .txt, .md, LICENSE, ecc. per semplicità o estendiamo la logica)
    # Qui assumiamo che se è in 'file_licenses' è stato scansionato come codice o simile.
    # Ma per sicurezza filtriamo estensioni note se necessario.
    # Per ora proviamo a rigenerare tutto ciò che è incompatibile.
    for issue in compatibility["issues"]:
        if not issue["compatible"]:
            fpath = issue["file_path"]
            # Esempio filtro estensioni (opzionale, ma consigliato)
            if not fpath.lower().endswith(('.txt', '.md', 'license', 'copying', '.rst')):
                files_to_regenerate.append(issue)

    if files_to_regenerate:
        print(f"Trovati {len(files_to_regenerate)} file incompatibili da rigenerare...")
        from app.services.code_generator import regenerate_code
        import os

        for issue in files_to_regenerate:
            fpath = issue["file_path"]
            
            # Tentativo di correzione path se scancode include la root dir
            repo_name = os.path.basename(os.path.normpath(repo_path))
            if fpath.startswith(f"{repo_name}/"):
                # Se fpath è "repo/file.py" e repo_path è ".../repo", dobbiamo togliere "repo/" da fpath
                # oppure unire con dirname(repo_path)
                abs_path = os.path.join(os.path.dirname(repo_path), fpath)
            else:
                abs_path = os.path.join(repo_path, fpath)
            
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        original_content = f.read()
                    
                    # Chiamata LLM
                    new_code = regenerate_code(
                        code_content=original_content,
                        main_license=main_license,
                        detected_license=issue["detected_license"]
                    )

                    if new_code:
                        # Sovrascrittura file
                        with open(abs_path, "w", encoding="utf-8") as f:
                            f.write(new_code)
                        
                        regenerated_files_map[fpath] = new_code
                        print(f"Rigenerato: {fpath}")
                except Exception as e:
                    print(f"Errore rigenerazione {fpath}: {e}")

        # Se abbiamo rigenerato qualcosa, rieseguiamo la scansione
        if regenerated_files_map:
            print("Riesecuzione scansione post-rigenerazione...")
            # 2-bis) ScanCode
            scan_raw = run_scancode(repo_path)
            # 3-bis) Main License (potrebbe essere cambiata? improbabile, ma ricalcoliamo)
            main_license = detect_main_license_scancode(scan_raw)
            # 4-bis) Filtro LLM
            llm_clean = filter_with_llm(scan_raw)
            file_licenses = extract_file_licenses_from_llm(llm_clean)
            # 5-bis) Compatibilità
            compatibility = check_compatibility(main_license, file_licenses)

    # 6) Suggerimenti AI
    enriched_issues = enrich_with_llm_suggestions(compatibility["issues"], regenerated_files_map)

    # 7) Mapping Pydantic
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

    # 8) Genera report su disco
    report_path = generate_report(repo_path, main_license, license_issue_models)

    return AnalyzeResponse(
        repository=f"{owner}/{repo}",
        main_license=main_license,
        issues=license_issue_models,
        report_path=report_path,
    )