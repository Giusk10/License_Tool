"""
This module provides the public interface for verifying license compatibility.

Main Responsibility:
- Orchestrates the normalization of the main license.
- Loads the compatibility matrix.
- Parses SPDX expressions for each file into an evaluation tree.
- Evaluates the tree against the matrix to determine compliance.
Behavior:
- Normalizes the main license
- Loads the professional matrix (via `matrix.get_matrix`)
- For each file, parses the SPDX expression via `parser_spdx.parse_spdx`
  and evaluates via `evaluator.eval_node`
- Produces a list of issues with the following fields for each file:
  - file_path: file path
  - detected_license: detected expression string
  - compatible: boolean (True if final outcome is yes)
  - reason: string with detailed trace (useful for report + LLM)

Note: in case of unavailable matrices or missing main license, the function
returns a set of issues with explanatory reason.
"""

from typing import Dict
from .compat_utils import normalize_symbol
from .parser_spdx import parse_spdx
from .evaluator import eval_node
from .matrix import get_matrix


def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict:
    """
    Evaluates the compatibility of file-level licenses against the main project license.

    Process:
    1. Normalizes the main license symbol.
    2. Retrieves the compatibility matrix.
    3. Iterates over each file's license expression:
       - Parses the SPDX string into a logical tree (Node).
       - Evaluates the tree using `eval_node` to get a status (yes/no/conditional) and a trace.

    Args:
        main_license (str): The main license symbol of the project.
        file_licenses (Dict[str, str]): A dictionary mapping file paths to their detected license expressions.

    Returns:
        dict: A dictionary containing the normalized main license and a list of 'issues'
              (compatibility results for each file).
    """
    issues = []
    main_license_n = normalize_symbol(main_license)
    matrix = get_matrix()

    if not main_license_n or main_license_n in {"UNKNOWN", "NOASSERTION", "NONE"}:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": "Main license not detected or invalid (UNKNOWN/NOASSERTION/NONE)",
            })
        return {"main_license": main_license or "UNKNOWN", "issues": issues}

    if not matrix or main_license_n not in matrix:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": "Professional matrix not available or main license not present in the matrix",
            })
        return {"main_license": main_license_n, "issues": issues}

    for file_path, license_expr in file_licenses.items():
        license_expr = (license_expr or "").strip()
        node = parse_spdx(license_expr)
        status, trace = eval_node(main_license_n, node)

        if status == "yes":
            compatible = True
            reason = "; ".join(trace)
        elif status == "no":
            compatible = False
            reason = "; ".join(trace)
        else:
            compatible = False
            hint = "conditional" if status == "conditional" else "unknown"
            reason = "; ".join(trace) + f"; Outcome: {hint}. Requires compliance/manual verification."

        issues.append({
            "file_path": file_path,
            "detected_license": license_expr,
            "compatible": compatible,
            "reason": reason,
        })

    return {"main_license": main_license_n, "issues": issues}
