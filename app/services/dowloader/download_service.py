import shutil
import os
from app.utility.config import CLONE_BASE_DIR

def perform_download(owner: str, repo: str) -> str:
    """
    Zippa la cartella del repository e ritorna il path del file zip.
    """
    repo_dir_name = f"{owner}_{repo}"
    repo_path = os.path.join(CLONE_BASE_DIR, repo_dir_name)

    if not os.path.exists(repo_path):
        raise ValueError(f"Repository not found at {repo_path}. Please clone it first.")

    # Definiamo il nome del file zip (senza estensione, shutil la aggiunge)
    zip_base_name = os.path.join(CLONE_BASE_DIR, f"{repo_dir_name}_download")

    # Creiamo l'archivio
    # format="zip", root_dir=repo_path crea uno zip col contenuto della cartella
    # Se vogliamo che lo zip contenga la cartella stessa, usiamo root_dir=CLONE_BASE_DIR e base_dir=repo_dir_name
    # Ma di solito si vuole il contenuto. Facciamo che contiene la cartella per ordine.

    zip_path = shutil.make_archive(
        base_name=zip_base_name,
        format="zip",
        root_dir=CLONE_BASE_DIR,
        base_dir=repo_dir_name
    )

    return zip_path
