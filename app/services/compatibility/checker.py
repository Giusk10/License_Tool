"""
Compatibility Checker Module.

This module serves as the public interface for verifying license compatibility.
It orchestrates the process by normalizing license symbols, loading the compatibility
matrix, parsing SPDX expressions from files, and evaluating them against the
project's main license.
"""

from typing import Dict, Any, List

from .compat_utils import normalize_symbol
from .parser_spdx import parse_spdx
from .evaluator import eval_node
from .matrix import get_matrix


def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> Dict[str, Any]:
    """
    Evaluates the compatibility of file-level licenses against the main project license.

    The process involves:
    1. Normalizing the main license symbol.
    2. Retrieving the compatibility matrix.
    3. Iterating over each file's license expression to:
        - Parse the SPDX string into a logical tree (Node).
        - Evaluate the tree using `eval_node` to determine status (yes, no, conditional)
          and generate a trace.

    Args:
        main_license (str): The main license symbol of the project (e.g., "MIT").
        file_licenses (Dict[str, str]): A dictionary mapping file paths to their
            detected license expressions (e.g., {"src/file.js": "MIT AND Apache-2.0"}).

    Returns:
        Dict[str, Any]: A dictionary containing:
            - "main_license" (str): The normalized main license identifier.
            - "issues" (List[Dict]): A list of dictionaries representing the compatibility
              result for each file. Each dictionary contains:
                - file_path (str)
                - detected_license (str)
                - compatible (bool)
                - reason (str)
    """
    issues: List[Dict[str, Any]] = []
    main_license_n = normalize_symbol(main_license)
    matrix = get_matrix()

    # Case 1: Main license is missing or invalid
    if not main_license_n or main_license_n in {"UNKNOWN", "NOASSERTION", "NONE"}:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": None,
                "reason": "Main license not detected or invalid (UNKNOWN/NOASSERTION/NONE)",
            })
        return {"main_license": main_license or "UNKNOWN", "issues": issues}

    # Case 2: Matrix unavailable or main license not supported in matrix
    if not matrix or main_license_n not in matrix:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": None,
                "reason": (
                    "Professional matrix not available or "
                    "main license not present in the matrix"
                ),
            })
        return {"main_license": main_license_n, "issues": issues}

    # Case 3: Standard evaluation
    for file_path, license_expr in file_licenses.items():
        license_expr = (license_expr or "").strip()

        # Parse the SPDX expression into a logical tree
        node = parse_spdx(license_expr)

        # Evaluate compatibility against the main license
        status, trace = eval_node(main_license_n, node)

        compatible = False
        reason = ""

        if status == "yes":
            compatible = True
            reason = "; ".join(trace)
        elif status == "no":
            compatible = False
            reason = "; ".join(trace)
        else:
            # Handle "conditional" or unknown statuses
            compatible = False
            hint = "conditional" if status == "conditional" else "unknown"
            reason = (
                f"{'; '.join(trace)}; "
                f"Outcome: {hint}. Requires compliance/manual verification."
            )

        issues.append({
            "file_path": file_path,
            "detected_license": license_expr,
            "compatible": compatible,
            "reason": reason,
        })

    return {"main_license": main_license_n, "issues": issues}
