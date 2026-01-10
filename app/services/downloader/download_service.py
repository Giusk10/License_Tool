"""
Download Service Module.

Questo modulo gestisce la preparazione degli archivi dei repository per il download.
Fornisce funzionalità per comprimere le directory dei repository clonati in
file ZIP, rendendoli pronti per il download da parte del client.
"""

import os
import shutil
import logging

from app.utility.config import CLONE_BASE_DIR

logger = logging.getLogger(__name__)


def perform_download(owner: str, repo: str) -> str:
    """
    Archivia una cartella di repository locale in un file ZIP.

    Valida l'esistenza del repository nella directory di clonazione,
    crea un archivio ZIP e restituisce il percorso assoluto del file generato.

    Args:
        owner (str): Il nome utente o nome dell'organizzazione del proprietario del repository.
        repo (str): Il nome del repository.

    Returns:
        str: Il percorso completo del file system dell'archivio ZIP generato.

    Raises:
        ValueError: Se la directory del repository non esiste nel percorso previsto.
        OSError: Se ci sono problemi di permessi o errori del disco durante l'archiviazione.
    """
    repo_dir_name = f"{owner}_{repo}"
    repo_path = os.path.join(CLONE_BASE_DIR, repo_dir_name)

    if not os.path.exists(repo_path):
        logger.error("Repository not found for download: %s", repo_path)
        raise ValueError(f"Repository not found at {repo_path}. Please clone it first.")

    # Definisce il nome del file di output (shutil.make_archive aggiunge automaticamente l'estensione)
    zip_base_name = os.path.join(CLONE_BASE_DIR, f"{repo_dir_name}_download")

    try:
        # Crea l'archivio ZIP.
        # root_dir=CLONE_BASE_DIR e base_dir=repo_dir_name assicurano che l'archivio
        # contenga la cartella 'owner_repo/' alla sua radice.
        zip_path = shutil.make_archive(
            base_name=zip_base_name,
            format="zip",
            root_dir=CLONE_BASE_DIR,
            base_dir=repo_dir_name
        )

        logger.info("Successfully created ZIP archive: %s", zip_path)
        return zip_path

    except Exception as e:
        logger.exception("Failed to create ZIP archive for %s/%s", owner, repo)
        raise OSError(f"Failed to create ZIP archive: {e}") from e
