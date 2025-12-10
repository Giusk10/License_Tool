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
    filter_with_llm,
)
from app.services.compatibility import check_compatibility
from app.services.suggestion import enrich_with_llm_suggestions
from app.services.report_service import generate_report
from app.core.config import CLONE_BASE_DIR
import os

def perform_cloning(owner: str, repo: str, oauth_token: str) -> str:
    """
    Esegue SOLO la clonazione del repository.
    Ritorna il path locale della repo clonata.
    """
    clone_result = clone_repo(owner, repo, oauth_token)
    if not clone_result.success:
        raise ValueError(f"Errore clonazione: {clone_result.error}")
    
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
    Esegue la scansione su una repo GIÀ clonata (da perform_cloning).
    """
    # Ricostruiamo il path (assumendo che la repo sia lì)
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")
    
    if not os.path.exists(repo_path):
        raise ValueError(f"Repository non trovata in {repo_path}. Esegui prima la clonazione.")

    # 2) Esegui ScanCode
    scan_raw = run_scancode(repo_path)
    

    # 3) Main License
    main_license, path_license = detect_main_license_scancode(scan_raw)

    # 4) Filtro LLM
    llm_clean = filter_with_llm(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses_from_llm(llm_clean)


    # 5) Compatibilità (Prima Passata)
    compatibility = check_compatibility(main_license, file_licenses)
   

    # 6) Suggerimenti AI (senza rigenerazione per ora)
    # Passiamo una mappa vuota perché non abbiamo ancora rigenerato nulla
    # TODO: pass empty regenerated map for now (nessuna AI presente)
    enriched_issues = enrich_with_llm_suggestions(compatibility["issues"], {})

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

def perform_regeneration(owner: str, repo: str, previous_analysis: AnalyzeResponse) -> AnalyzeResponse:
    """
    Esegue la logica di rigenerazione su una repo GIÀ clonata.
    Usa 'previous_analysis' per sapere quali file sono incompatibili, SENZA rifare la scansione iniziale.
    """
    # Ricostruiamo il path (assumendo che la repo sia lì)
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")
    
    if not os.path.exists(repo_path):
        raise ValueError(f"Repository non trovata in {repo_path}. Esegui prima la scansione iniziale.")

    # Recuperiamo i dati dalla scansione precedente passata dal frontend
    main_license = previous_analysis.main_license
    # previous_analysis.issues è una lista di oggetti LicenseIssue (Pydantic)
    # La logica sotto si aspetta spesso dei dict o oggetti accessibili.
    # Se 'issues' sono oggetti Pydantic, possiamo accedervi con .attribute
    
    # --- LOGICA DI RIGENERAZIONE ---
    regenerated_files_map = {}  # file_path -> new_code_content
    files_to_regenerate = []

    for issue in previous_analysis.issues:
        # issue è un oggetto LicenseIssue
        if not issue.compatible:
            fpath = issue.file_path
            # Esempio filtro estensioni
            if not fpath.lower().endswith(('.txt', '.md', 'license', 'copying', '.rst')):
                files_to_regenerate.append(issue)

    if files_to_regenerate:
        print(f"Trovati {len(files_to_regenerate)} file incompatibili da rigenerare...")
        from app.services.code_generator import regenerate_code

        for issue in files_to_regenerate:
            fpath = issue.file_path
            
            # Tentativo di correzione path
            repo_name = os.path.basename(os.path.normpath(repo_path))
            if fpath.startswith(f"{repo_name}/"):
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
                        detected_license=issue.detected_license
                    )

                    if new_code and len(new_code.strip()) > 10:
                        # Sovrascrittura file
                        with open(abs_path, "w", encoding="utf-8") as f:
                            f.write(new_code)
                        
                        regenerated_files_map[fpath] = new_code
                        print(f"Rigenerato: {fpath} (Length: {len(new_code)})")
                    else:
                        print(f"Rigenerazione fallita o codice non valido per {fpath}")
                except Exception as e:
                    print(f"Errore rigenerazione {fpath}: {e}")

        # Se abbiamo rigenerato qualcosa, rieseguiamo la scansione finale
        if regenerated_files_map:
            print("Riesecuzione scansione post-rigenerazione...")
            scan_raw = run_scancode(repo_path)

            main_license, path = detect_main_license_scancode(scan_raw) # Main license non dovrebbe cambiare

            llm_clean = filter_with_llm(scan_raw, main_license, path)

            file_licenses = extract_file_licenses_from_llm(llm_clean)

            compatibility = check_compatibility(main_license, file_licenses)
            
            # Aggiorniamo la lista di issues con i nuovi risultati
            # check_compatibility ritorna un dict con "issues": [dict, dict...]
            current_issues_dicts = compatibility["issues"]
        else:
            # Se non abbiamo rigenerato nulla (es. errore o nessun file adatto),
            # potremmo voler restituire le issue originali o rifare scan?
            # Per coerenza, se non cambia nulla, teniamo quelle di prima ma convertite in dict se serve
            # Ma qui sotto ci aspettiamo di dover chiamare enrich_with_llm_suggestions che vuole LISTA DI DICT
            # Quindi convertiamo i Pydantic in dict
            current_issues_dicts = [i.dict() for i in previous_analysis.issues]

    else:
        # Nessun file da rigenerare
        current_issues_dicts = [i.dict() for i in previous_analysis.issues]

    # 6) Suggerimenti AI (con mappa rigenerati)
    # enrich_with_llm_suggestions si aspetta una lista di DICT
    enriched_issues = enrich_with_llm_suggestions(current_issues_dicts, regenerated_files_map)

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