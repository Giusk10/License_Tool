"""
Modulo `matrix` — caricamento e normalizzazione della matrice di compatibilità.

Questo modulo cerca il file `matrixseqexpl.json` nello stesso package e lo trasforma
in una mappa {main_license: {dep_license: status}} dove status è uno di
"yes" | "no" | "conditional".

Supporta diversi formati di input per essere robusto rispetto a versioni diverse
della matrice (vecchio formato con chiave "matrix", nuova lista di entry, o
struttura con chiave "licenses").

La funzione pubblica principale è `get_matrix()` che restituisce la matrice già
normalizzata (caricata una sola volta all'import).
"""

import os
import json
import logging
from typing import Dict
from .compat_utils import normalize_symbol

# path relativo della matrice dentro lo stesso package
_MATRIXSEQEXPL_PATH = os.path.join(os.path.dirname(__file__), "matrixseqexpl.json")

logger = logging.getLogger(__name__)


def _read_matrix_json() -> dict | None:
    """Prova a leggere il file JSON dalla posizione filesystem, altrimenti
    prova a caricarlo come risorsa del package (importlib.resources).

    Restituisce il contenuto JSON come dict/list o None se non è disponibile.
    """
    try:
        if os.path.exists(_MATRIXSEQEXPL_PATH):
            with open(_MATRIXSEQEXPL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.exception("Errore leggendo %s dal filesystem", _MATRIXSEQEXPL_PATH)

    # Fallback: proviamo a caricare la risorsa dal package
    try:
        try:
            # Python 3.9+
            import importlib.resources as resources
        except Exception:
            resources = None

        if resources is not None and __package__:
            try:
                # importlib.resources.files è preferibile
                files = getattr(resources, "files", None)
                if files is not None:
                    text = files(__package__).joinpath("matrixseqexpl.json").read_text(encoding="utf-8")
                else:
                    # older API: use open_text
                    text = resources.open_text(__package__, "matrixseqexpl.json").read()
                return json.loads(text)
            except FileNotFoundError:
                # risorsa non presente
                return None
            except Exception:
                logger.exception("Errore leggendo matrixseqexpl.json come risorsa di package %s", __package__)
                return None
    except Exception:
        # non vogliamo mai propagare eccezioni qui
        logger.exception("Errore inatteso durante il fallback per la lettura della matrice")

    return None


def _coerce_status(status_raw: str) -> str:
    """Normalizza lo status proveniente dal file verso 'yes'|'no'|'conditional'|'unknown'."""
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


def load_professional_matrix() -> Dict[str, Dict[str, str]]:
    """
    Carica e normalizza la matrice professionale in una mappa {main: {dep: status}}
    """
    try:
        data = _read_matrix_json()
        if not data:
            logger.info("File matrixseqexpl.json non trovato o vuoto. Path cercato: %s", _MATRIXSEQEXPL_PATH)
            return {}

        # struttura old: {"matrix": {...}}
        if isinstance(data, dict) and "matrix" in data and isinstance(data["matrix"], dict):
            matrix = data["matrix"]
            normalized = {}
            for main, row in matrix.items():
                if not isinstance(row, dict):
                    continue
                main_n = normalize_symbol(main)
                normalized[main_n] = {}
                for k, v in row.items():
                    coerced = _coerce_status(v)
                    if coerced in {"yes", "no", "conditional", "unknown"}:
                        normalized[main_n][normalize_symbol(k)] = coerced
            if normalized:
                return normalized

        # struttura nuova: lista di entry {name, compatibilities}
        elif isinstance(data, list):
            normalized = {}
            for entry in data:
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
            if normalized:
                return normalized

        # struttura con key 'licenses'
        elif isinstance(data, dict) and "licenses" in data and isinstance(data["licenses"], list):
            normalized = {}
            for entry in data["licenses"]:
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
            if normalized:
                return normalized

    except Exception:
        logger.exception("Errore durante la normalizzazione della matrice di compatibilità")
    return {}


# carica una sola volta
_PRO_MATRIX = load_professional_matrix()


def get_matrix() -> Dict[str, Dict[str, str]]:
    """
    Restituisce la matrice normalizzata (può essere vuota se il file non è presente).
    """
    return _PRO_MATRIX

