"""
Module `matrix` — loading and normalization of the compatibility matrix.

This module looks for the `matrixseqexpl.json` file in the same package and transforms it
into a map {main_license: {dep_license: status}} where status is one of
"yes" | "no" | "conditional".

It supports different input formats to be robust against different versions
of the matrix (old format with "matrix" key, new list of entries, or structure with "licenses" key).

The main public function is `get_matrix()`, which returns the matrix already
normalized (loaded once at import).
"""

import os
import json
import logging
from typing import Dict
from .compat_utils import normalize_symbol

# Relative path to the matrix file within the package
_MATRIXSEQEXPL_PATH = os.path.join(os.path.dirname(__file__), "matrixseqexpl.json")

logger = logging.getLogger(__name__)


def _read_matrix_json() -> dict | None:
    """
    Attempts to read the JSON file from the filesystem location; otherwise,
    tries to load it as a package resource (importlib.resources).

    Returns the JSON content as dict/list or None if unavailable.
    """
    try:
        if os.path.exists(_MATRIXSEQEXPL_PATH):
            with open(_MATRIXSEQEXPL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.exception("An error occurred trying to read %s from filesystem", _MATRIXSEQEXPL_PATH)

    # Fallback: try loading the resource from the package
    try:
        try:
            # Python 3.9+
            import importlib.resources as resources
        except Exception:
            resources = None

        if resources is not None and __package__:
            try:
                # importlib.resources.files is preferred
                files = getattr(resources, "files", None)
                if files is not None:
                    text = files(__package__).joinpath("matrixseqexpl.json").read_text(encoding="utf-8")
                else:
                    # older API: use open_text
                    text = resources.open_text(__package__, "matrixseqexpl.json").read()
                return json.loads(text)
            except FileNotFoundError:
                # resource not present
                return None
            except Exception:
                logger.exception("Error reading matrixseqexpl.json as package resource %s", __package__)
                return None
    except Exception:
        # we never want to propagate exceptions here
        logger.exception("Unexpected error during fallback for matrix reading")

    return None


def _coerce_status(status_raw: str) -> str:
    """
    Normalizes the status from the file to 'yes'|'no'|'conditional'|'unknown'.
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


def load_professional_matrix() -> Dict[str, Dict[str, str]]:
    """
    Loads and normalizes the professional matrix into a map {main: {dep: status}}.
    """
    try:
        data = _read_matrix_json()
        if not data:
            logger.info("File matrixseqexpl.json not found or empty. Path searched: %s", _MATRIXSEQEXPL_PATH)
            return {}

        # old structure: {"matrix": {...}}
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

        # new structure: list of entries {name, compatibilities}
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

        # structure with 'licenses' key
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
        logger.exception("Error during compatibility matrix normalization")
    return {}


# Load only once
_PRO_MATRIX = load_professional_matrix()


def get_matrix() -> Dict[str, Dict[str, str]]:
    """
    Returns the normalized matrix (may be empty if the file is not present).
    """
    return _PRO_MATRIX

