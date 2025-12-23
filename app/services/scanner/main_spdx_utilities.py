"""
Main SPDX Utilities Module.

This module provides utility functions to extract and validate SPDX license identifiers
from ScanCode Toolkit JSON output. It includes logic to prioritize root files
and traverse nested dictionary structures to find valid license tags.
"""

from typing import List, Dict, Any, Optional, Tuple


def _is_valid(value: Optional[str]) -> bool:
    """
    Checks if a license string is a valid SPDX identifier.

    Args:
        value (Optional[str]): The license string to check.

    Returns:
        bool: True if the value is not None, not empty, and not "UNKNOWN".
    """
    return bool(value) and value != "UNKNOWN"


def _extract_first_valid_spdx(entry: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Retrieves the first valid SPDX identifier found in a ScanCode entry.

    It searches in the following order:
    1. Top-level detected license expression.
    2. 'license_detections' list.
    3. 'licenses' details list.

    Args:
        entry (Dict[str, Any]): A single file entry from the ScanCode JSON.

    Returns:
        Optional[Tuple[str, str]]: A tuple (spdx_expression, file_path) if found,
        otherwise None.
    """
    if not isinstance(entry, dict):
        return None

    path = entry.get("path") or ""

    # 1. Check the main detected license expression
    spdx = entry.get("detected_license_expression_spdx")
    if _is_valid(spdx):
        return spdx, path

    # 2. Check individual detections
    # Even if the root 'license_detections' is removed during post-processing,
    # this key often remains inside individual 'files' objects.
    detections = entry.get("license_detections", []) or []
    for detection in detections:
        det_spdx = detection.get("license_expression_spdx")
        if _is_valid(det_spdx):
            return det_spdx, path

    # 3. Check SPDX keys in detailed license list
    licenses = entry.get("licenses", []) or []
    for lic in licenses:
        spdx_key = lic.get("spdx_license_key")
        if _is_valid(spdx_key):
            return spdx_key, path

    return None


def _pick_best_spdx(entries: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """
    Selects the best license from a list of candidates, prioritizing root files.

    It sorts the entries based on directory depth (shallowest path first)
    and returns the first valid SPDX identifier found.

    Args:
        entries (List[Dict[str, Any]]): A list of ScanCode file entries.

    Returns:
        Optional[Tuple[str, str]]: A tuple (spdx_expression, file_path) if found,
        otherwise None.
    """
    if not entries:
        return None

    # Filter ensuring only dictionaries are processed
    valid_entries = [e for e in entries if isinstance(e, dict)]

    # Sort entries by path depth (number of slashes).
    # Files with fewer slashes are closer to the root and generally more authoritative
    # (e.g., ./LICENSE vs ./src/vendor/lib/LICENSE).
    sorted_entries = sorted(
        valid_entries,
        key=lambda e: (e.get("path", "") or "").count("/")
    )

    for entry in sorted_entries:
        result = _extract_first_valid_spdx(entry)
        if result:
            # result is already a tuple (spdx, path)
            return result

    return None
