"""
Matrix Loading Module.

Questo modulo è responsabile del caricamento e della normalizzazione della matrice di compatibilità
delle licenze dal file `matrixseqexpl.json`. Trasforma i dati JSON in un
formato di dizionario nidificato standardizzato:
    {main_license: {dependency_license: status}}

dove `status` è uno tra "yes", "no", o "conditional".

Caratteristiche Principali:
- Caricamento robusto: Tenta di leggere prima dal filesystem, ripiegando sulle
  risorse del pacchetto.
- Agnostico rispetto al formato: Supporta schemi JSON multipli (formato dizionario legacy,
  elenco di voci, o elenco 'licenses' avvolto) per garantire la retrocompatibilità.
- Pattern Singleton: La matrice viene caricata una volta al momento dell'importazione.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional

# Tenta di importare importlib.resources per supportare diverse versioni/ambienti Python
try:
    from importlib import resources
except ImportError:
    resources = None

from .compat_utils import normalize_symbol

# Percorso relativo al file della matrice all'interno del pacchetto (usato per la lettura dal filesystem)
_MATRIXSEQEXPL_PATH = os.path.join(os.path.dirname(__file__), "matrixseqexpl.json")

logger = logging.getLogger(__name__)

# Alias di tipo per la struttura della matrice normalizzata
CompatibilityMap = Dict[str, Dict[str, str]]


def _read_from_filesystem() -> Optional[Dict[str, Any]]:
    """
    Tenta di leggere il file JSON della matrice direttamente dal filesystem.

    Returns:
        Optional[Dict[str, Any]]: I dati JSON analizzati se l'operazione ha successo, None altrimenti.
    """
    try:
        if os.path.exists(_MATRIXSEQEXPL_PATH):
            with open(_MATRIXSEQEXPL_PATH, "r", encoding="utf-8") as file_handle:
                return json.load(file_handle)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "An error occurred trying to read %s from filesystem",
            _MATRIXSEQEXPL_PATH
        )
    return None


def _read_from_resources() -> Optional[Dict[str, Any]]:
    """
    Tenta di leggere il file JSON della matrice utilizzando le risorse del pacchetto.

    Questo è utile quando l'applicazione è pacchettizzata (es. zippata) dove i percorsi
    standard del filesystem potrebbero non funzionare.

    Returns:
        Optional[Dict[str, Any]]: I dati JSON analizzati se l'operazione ha successo, None altrimenti.
    """
    if resources is None or not __package__:
        return None

    try:
        # pylint: disable=no-member
        # Usa getattr per gestire in modo robusto i casi in cui l'API 'files' non esiste
        # (Python < 3.9) o è None (mock/test).
        files_func = getattr(resources, "files", None)

        if files_func is not None:
            # API Moderna (Python 3.9+)
            text = (
                files_func(__package__)
                .joinpath("matrixseqexpl.json")
                .read_text(encoding="utf-8")
            )
        else:
            # API precedente: usa open_text
            # pylint: disable=deprecated-method
            text = resources.open_text(__package__, "matrixseqexpl.json").read()

        return json.loads(text)

    except FileNotFoundError:
        return None
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Error reading matrixseqexpl.json as package resource from %s",
            __package__
        )
        return None


def _read_matrix_json() -> Optional[Dict[str, Any]]:
    """
    Orchestra la strategia di lettura.

    1. Tenta di leggere dal filesystem.
    2. Ripiega sulle risorse del pacchetto se il file non viene trovato.

    Returns:
        Optional[Dict[str, Any]]: I dati JSON grezzi.
    """
    # 1. Prova Filesystem
    data = _read_from_filesystem()
    if data:
        return data

    # 2. Fallback: Risorsa Pacchetto
    return _read_from_resources()


def _coerce_status(status_raw: Any) -> str:
    """
    Normalizza una stringa di stato grezza in un valore canonico.

    Args:
        status_raw (Any): Il valore di stato dal JSON (solitamente una stringa).

    Returns:
        str: Uno tra 'yes', 'no', 'conditional', o 'unknown'.
    """
    if not isinstance(status_raw, str):
        return "unknown"

    s = status_raw.strip().lower()

    if s in {"yes", "same"}:
        return "yes"
    if s == "no":
        return "no"
    if s == "conditional":
        return "conditional"

    return "unknown"


def _process_matrix_dict(matrix_data: Dict[str, Any]) -> CompatibilityMap:
    """
    Analizza la struttura del dizionario legacy.

    Formato: {'matrix': { 'MIT': {'GPL': 'yes'} }}

    Args:
        matrix_data (Dict[str, Any]): Il dizionario 'matrix' dal JSON.

    Returns:
        CompatibilityMap: La mappa di compatibilità normalizzata.
    """
    normalized: CompatibilityMap = {}

    for main, row in matrix_data.items():
        if not isinstance(row, dict):
            continue

        main_n = normalize_symbol(main)
        normalized[main_n] = {}

        for dep_license, status_val in row.items():
            coerced = _coerce_status(status_val)
            if coerced in {"yes", "no", "conditional", "unknown"}:
                normalized[main_n][normalize_symbol(dep_license)] = coerced

    return normalized


def _process_entries_list(entries_list: List[Dict[str, Any]]) -> CompatibilityMap:
    """
    Analizza la struttura basata su elenco (usata nei nuovi formati e nella chiave 'licenses').

    Formato Previsto: [{'name': 'MIT', 'compatibilities': [...]}, ...]

    Args:
        entries_list (List[Dict[str, Any]]): Elenco di oggetti voce licenza.

    Returns:
        CompatibilityMap: La mappa di compatibilità normalizzata.
    """
    normalized: CompatibilityMap = {}

    for entry in entries_list:
        if not isinstance(entry, dict):
            continue

        main = entry.get("name")
        compat_list = entry.get("compatibilities", [])

        if not main or not isinstance(compat_list, list):
            continue

        main_n = normalize_symbol(main)
        normalized[main_n] = {}

        for comp in compat_list:
            if not isinstance(comp, dict):
                continue

            dep = comp.get("name")
            status = comp.get("compatibility") or comp.get("status")

            v = _coerce_status(status)
            if dep:
                normalized[main_n][normalize_symbol(dep)] = v

    return normalized


def load_professional_matrix() -> CompatibilityMap:
    """
    Carica e normalizza la matrice di compatibilità professionale.

    Gestisce il caricamento da file/risorsa e l'analisi di vari schemi JSON.

    Returns:
        CompatibilityMap: Un dizionario che mappa {main_license -> {dep_license -> status}}.
        Restituisce un dizionario vuoto se il file non può essere caricato o analizzato.
    """
    try:
        data = _read_matrix_json()
        if not data:
            logger.info(
                "File matrixseqexpl.json not found or empty. Path searched: %s",
                _MATRIXSEQEXPL_PATH
            )
            return {}

        # Caso 1: Struttura legacy {"matrix": {...}}
        if (isinstance(data, dict) and "matrix" in data and
                isinstance(data["matrix"], dict)):
            return _process_matrix_dict(data["matrix"])

        # Caso 2: Nuova struttura (Elenco di voci alla radice)
        if isinstance(data, list):
            return _process_entries_list(data)

        # Caso 3: Struttura con chiave 'licenses' contenente un elenco
        if (isinstance(data, dict) and "licenses" in data and
                isinstance(data["licenses"], list)):
            return _process_entries_list(data["licenses"])

    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Error during compatibility matrix normalization")

    return {}


# Carica la matrice una volta a livello di modulo (Pattern Singleton)
_PRO_MATRIX = load_professional_matrix()


def get_matrix() -> CompatibilityMap:
    """
    Recupera la matrice di compatibilità pre-caricata.

    Returns:
        CompatibilityMap: La matrice di compatibilità normalizzata.
    """
    return _PRO_MATRIX
