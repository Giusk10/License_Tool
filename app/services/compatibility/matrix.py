"""
Matrix Loading Module.

This module is responsible for loading and normalizing the license compatibility
matrix from the `matrixseqexpl.json` file. It transforms the JSON data into a
standardized nested dictionary format:
    {main_license: {dependency_license: status}}

where `status` is one of "yes", "no", or "conditional".

Key Features:
- Robust loading: Attempts to read from the filesystem first, falling back to
  package resources.
- Format agnostic: Supports multiple JSON schemas (legacy dictionary format,
  list of entries, or wrapped 'licenses' list) to ensure backward compatibility.
- Singleton pattern: The matrix is loaded once at import time.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional

# Attempt to import importlib.resources to support different Python versions/environments
try:
    from importlib import resources
except ImportError:
    resources = None

from .compat_utils import normalize_symbol

# Relative path to the matrix file within the package (used for filesystem read)
_MATRIXSEQEXPL_PATH = os.path.join(os.path.dirname(__file__), "matrixseqexpl.json")

logger = logging.getLogger(__name__)

# Type alias for the normalized matrix structure
CompatibilityMap = Dict[str, Dict[str, str]]


def _read_from_filesystem() -> Optional[Dict[str, Any]]:
    """
    Attempts to read the matrix JSON file directly from the filesystem.

    Returns:
        Optional[Dict[str, Any]]: The parsed JSON data if successful, None otherwise.
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
    Attempts to read the matrix JSON file using package resources.

    This is useful when the application is packaged (e.g., zipped) where standard
    filesystem paths might not work.

    Returns:
        Optional[Dict[str, Any]]: The parsed JSON data if successful, None otherwise.
    """
    if resources is None or not __package__:
        return None

    try:
        # pylint: disable=no-member
        # Use getattr to robustly handle cases where 'files' API does not exist
        # (Python < 3.9) or is None (mocks/tests).
        files_func = getattr(resources, "files", None)

        if files_func is not None:
            # Modern API (Python 3.9+)
            text = (
                files_func(__package__)
                .joinpath("matrixseqexpl.json")
                .read_text(encoding="utf-8")
            )
        else:
            # Older API: use open_text
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
    Orchestrates the reading strategy.

    1. Tries to read from the filesystem.
    2. Falls back to package resources if the file is not found.

    Returns:
        Optional[Dict[str, Any]]: The raw JSON data.
    """
    # 1. Try Filesystem
    data = _read_from_filesystem()
    if data:
        return data

    # 2. Fallback: Package Resource
    return _read_from_resources()


def _coerce_status(status_raw: Any) -> str:
    """
    Normalizes a raw status string into a canonical value.

    Args:
        status_raw (Any): The status value from the JSON (usually a string).

    Returns:
        str: One of 'yes', 'no', 'conditional', or 'unknown'.
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
    Parses the legacy dictionary structure.

    Format: {'matrix': { 'MIT': {'GPL': 'yes'} }}

    Args:
        matrix_data (Dict[str, Any]): The 'matrix' dictionary from JSON.

    Returns:
        CompatibilityMap: The normalized compatibility map.
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
    Parses the list-based structure (used in new formats and 'licenses' key).

    Expected Format: [{'name': 'MIT', 'compatibilities': [...]}, ...]

    Args:
        entries_list (List[Dict[str, Any]]): List of license entry objects.

    Returns:
        CompatibilityMap: The normalized compatibility map.
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
    Loads and normalizes the professional compatibility matrix.

    It handles loading from file/resource and parsing various JSON schemas.

    Returns:
        CompatibilityMap: A dictionary mapping {main_license -> {dep_license -> status}}.
        Returns an empty dict if the file cannot be loaded or parsed.
    """
    try:
        data = _read_matrix_json()
        if not data:
            logger.info(
                "File matrixseqexpl.json not found or empty. Path searched: %s",
                _MATRIXSEQEXPL_PATH
            )
            return {}

        # Case 1: Legacy structure {"matrix": {...}}
        if (isinstance(data, dict) and "matrix" in data and
                isinstance(data["matrix"], dict)):
            return _process_matrix_dict(data["matrix"])

        # Case 2: New structure (List of entries at root)
        if isinstance(data, list):
            return _process_entries_list(data)

        # Case 3: Structure with 'licenses' key containing a list
        if (isinstance(data, dict) and "licenses" in data and
                isinstance(data["licenses"], list)):
            return _process_entries_list(data["licenses"])

    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Error during compatibility matrix normalization")

    return {}


# Load the matrix once at module level (Singleton pattern)
_PRO_MATRIX = load_professional_matrix()


def get_matrix() -> CompatibilityMap:
    """
    Retrieves the pre-loaded compatibility matrix.

    Returns:
        CompatibilityMap: The normalized compatibility matrix.
    """
    return _PRO_MATRIX
