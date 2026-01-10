"""
Analysis Workflow Module.

Questo modulo gestisce i flussi di lavoro di analisi principali per l'applicazione.
Agisce come orchestratore per:
- Clonazione del repository (tramite GitHub).
- Caricamento ed estrazione di file ZIP.
- Scansione iniziale delle licenze e controllo della compatibilità.
- Il ciclo di rigenerazione del codice basato sull'intelligenza artificiale per risolvere i conflitti di licenza.
"""
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
    Esegue il processo di clonazione del repository.

    Questa funzione si affida al servizio client GitHub per clonare il repository
    remoto nel file system locale.

    Args:
        owner (str): Il proprietario del repository (nome utente o organizzazione).
        repo (str): Il nome del repository.

    Returns:
        str: Il percorso del file system locale del repository clonato.

    Raises:
        ValueError: Se l'operazione di clonazione fallisce.
    """
    clone_result = clone_repo(owner, repo)
    if not clone_result.success:
        raise ValueError(f"Cloning error: {clone_result.error}")

    return clone_result.repo_path


def perform_upload_zip(owner: str, repo: str, uploaded_file: UploadFile) -> str:
    """
    Gestisce il caricamento, l'estrazione e la normalizzazione di un file ZIP di codice sorgente.

    Garantisce che la directory di destinazione sia pulita, estrae lo zip e normalizza
    la struttura delle directory (es. gestendo singole cartelle root all'interno degli archivi).

    Args:
        owner (str): Il nome del proprietario da assegnare al progetto.
        repo (str): Il nome del repository da assegnare.
        uploaded_file (UploadFile): Il file ZIP caricato dall'utente.

    Returns:
        str: Il percorso locale assoluto dove è stato estratto il codice.

    Raises:
        HTTPException:
            - 400: Se il file non è uno zip o è corrotto.
            - 500: Se si verificano errori del filesystem durante la pulizia o l'estrazione.
    """
    target_dir = os.path.join(CLONE_BASE_DIR, f"{owner.strip()}_{repo.strip()}")

    # 1. Pulizia preventiva della directory esistente
    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir)
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error cleaning up existing directory: {e}"
            ) from e

    # Valida l'estensione del file
    if not uploaded_file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="The uploaded file must be a .zip archive")

    try:
        # 2. Usa una directory temporanea per l'estrazione
        with tempfile.TemporaryDirectory() as temp_dir:

            with zipfile.ZipFile(uploaded_file.file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            extracted_items = os.listdir(temp_dir)
            visible_items = [
                item for item in extracted_items
                if not item.startswith('__') and not item.startswith('.')
            ]

            source_to_move = temp_dir

            # CASO A: Lo zip contiene una singola cartella radice (es. 'my-repo-main')
            # Vogliamo spostare il *contenuto* di quella cartella, non la cartella stessa.
            if len(visible_items) == 1:
                potential_root = os.path.join(temp_dir, visible_items[0])
                if os.path.isdir(potential_root):
                    source_to_move = potential_root

            # CASO B: Sposta il contenuto nella directory di destinazione finale
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
    Esegue l'analisi iniziale su un repository già clonato/caricato.

    Passaggi:
    1. Esegue ScanCode per rilevare i dati grezzi della licenza.
    2. Identifica la licenza principale del progetto.
    3. Filtra i risultati di ScanCode utilizzando LLM e regole regex.
    4. Controlla la compatibilità tra le licenze dei file e la licenza principale.
    5. Arricchisce i problemi con suggerimenti generati dall'intelligenza artificiale.

    Args:
        owner (str): Il proprietario del repository.
        repo (str): Il nome del repository.

    Returns:
        AnalyzeResponse: Il risultato completo dell'analisi inclusi problemi e suggerimenti.

    Raises:
        ValueError: Se la directory del repository non esiste.
    """
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner.strip()}_{repo.strip()}")

    if not os.path.exists(repo_path):
        raise ValueError(f"Repository not found at {repo_path}. Please clone it first.")

    # 2) Esegue ScanCode
    scan_raw = run_scancode(repo_path)

    # 3) Rileva la Licenza Principale
    license_result = detect_main_license_scancode(scan_raw)

    # Gestisce entrambi i tipi di ritorno: tupla (licenza, percorso) o stringa "UNKNOWN"
    if isinstance(license_result, tuple):
        main_license, path_license = license_result
    else:
        main_license = license_result
        path_license = None

    # 4) Filtraggio
    llm_clean = filter_licenses(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses(llm_clean)

    remove_or_clauses = choose_most_permissive_license_in_file(file_licenses)

    # 5) Controllo Compatibilità
    compatibility = check_compatibility(main_license, remove_or_clauses)

    # 6) Suggerimenti AI
    enriched_issues = enrich_with_llm_suggestions(main_license, compatibility["issues"], {})

    # 7) Controlla se è necessario un suggerimento di licenza
    needs_suggestion = needs_license_suggestion(main_license, enriched_issues)

    # 8) Mappa ai Modelli Pydantic
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
    Esegue il flusso di lavoro di rigenerazione del codice su un repository già analizzato.

    Passaggi:
    1. Identifica i file incompatibili dall'analisi precedente.
    2. Chiama l'LLM per rigenerare codice conforme alla licenza principale.
    3. Riesegue la scansione del repository per verificare i miglioramenti.
    4. Restituisce i risultati dell'analisi aggiornati.

    Args:
        owner (str): Il proprietario del repository.
        repo (str): Il nome del repository.
        previous_analysis (AnalyzeResponse): Risultati dalla scansione iniziale.

    Returns:
        AnalyzeResponse: Il risultato dell'analisi aggiornato contenente i percorsi del codice rigenerato.

    Raises:
        ValueError: Se la directory del repository non esiste.
    """
    repo_path = os.path.join(CLONE_BASE_DIR, f"{owner}_{repo}")

    if not os.path.exists(repo_path):
        raise ValueError(f"Repository not found at {repo_path}. Please run initial scan first.")

    main_license = previous_analysis.main_license

    # 1. Identifica e rigenera i file incompatibili
    regenerated_files_map = _regenerate_incompatible_files(
        repo_path,
        main_license,
        previous_analysis.issues
    )

    # 2. Riesegue la scansione o Fallback
    if regenerated_files_map:
        print("Re-running post-regeneration scan...")
        current_issues_dicts = _rescan_repository(
            repo_path,
            main_license,
            regenerated_files_map
        )
    else:
        # Fallback: converti i modelli Pydantic esistenti in dict se non sono avvenuti cambiamenti
        current_issues_dicts = [i.model_dump() for i in previous_analysis.issues]

    # 3. Arricchimento Finale
    enriched_issues = enrich_with_llm_suggestions(
        main_license,
        current_issues_dicts,
        regenerated_files_map
    )

    # 4. Verifica se è ancora necessario un suggerimento di licenza dopo la rigenerazione
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
    Helper interno per identificare i file incompatibili e tentare la rigenerazione tramite LLM.

    Args:
        repo_path (str): Percorso del repository.
        main_license (str): La licenza di destinazione.
        issues (list[LicenseIssue]): Elenco dei problemi dalla scansione precedente.

    Returns:
        dict: Una mappa {file_path: new_content} dei file rigenerati con successo.
    """
    regenerated_map = {}

    # Filtra i file da ignorare (documenti, avvisi, ecc.)
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

        # Risolve il percorso assoluto
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

            # Assicura che licenses sia una stringa, non None
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
        # Ampia eccezione catturata intenzionalmente per evitare di interrompere il ciclo
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
    Helper interno per rieseguire ScanCode e i controlli di compatibilità.

    Args:
        repo_path (str): Percorso al repository.
        main_license (str): La licenza principale da verificare.
        regenerated_map (dict): Mappa dei file rigenerati (passata per contesto/future estensioni logiche).

    Returns:
        list[dict]: Un elenco di dizionari di problemi aggiornati.
    """
    # Previene l'avviso di argomento non utilizzato (mantenuto per debug o future estensioni logiche)
    _ = regenerated_map

    scan_raw = run_scancode(repo_path)

    # Rileva nuovamente il percorso della licenza per garantire l'accuratezza
    license_result = detect_main_license_scancode(scan_raw)

    # Gestisce entrambi i tipi di ritorno: tupla (license, path) o stringa "UNKNOWN"
    if isinstance(license_result, tuple):
        _, path_license = license_result
    else:
        path_license = None

    llm_clean = filter_licenses(scan_raw, main_license, path_license)
    file_licenses = extract_file_licenses(llm_clean)

    compatibility = check_compatibility(main_license, file_licenses)

    return compatibility["issues"]
