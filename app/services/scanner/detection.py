"""
ScanCode Detection Module.

This module manages the execution of the ScanCode toolkit and the parsing of its results
to detect licenses within a repository.

It includes functionality to:
- Execute ScanCode as a subprocess with optimized configuration.
- Identify the project's main license based on file hierarchy (LICENSE, COPYING).
- Extract and aggregate detected licenses for individual files.
"""

import os
import json
import logging
import subprocess
from typing import Dict, Tuple, Union, List, Any

from app.utility.config import SCANCODE_BIN, OUTPUT_BASE_DIR
from app.services.scanner.main_spdx_utilities import _pick_best_spdx

logger = logging.getLogger(__name__)


def run_scancode(repo_path: str) -> Dict[str, Any]:
    """
    Executes ScanCode on a specific repository path.

    It applies advanced filters, tracks progress via logging, and performs
    post-processing on the output JSON to remove redundant data.

    Args:
        repo_path (str): The file system path to the cloned repository.

    Returns:
        Dict[str, Any]: The parsed and cleaned ScanCode JSON output.

    Raises:
        RuntimeError: If ScanCode fails (exit code > 1) or does not generate output.
    """
    # 1. Load ignore patterns (prioritize patterns_to_ignore.json, fallback to license_rules.json)
    base_dir = os.path.dirname(__file__)
    patterns_path = os.path.join(base_dir, 'patterns_to_ignore.json')
    rules_path = os.path.join(base_dir, 'license_rules.json')

    ignore_patterns: List[str] = []

    try:
        if os.path.exists(patterns_path):
            with open(patterns_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ignore_patterns = data.get("ignored_patterns", [])
        elif os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ignore_patterns = data.get("ignored_patterns", [])
    except json.JSONDecodeError:
        logger.warning("Failed to parse ignore patterns JSON. Proceeding without ignores.")

    # Normalize patterns and remove empty strings
    ignore_patterns = [str(x) for x in ignore_patterns if x]

    # Ensure output directory exists
    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

    repo_name = os.path.basename(os.path.normpath(repo_path))
    output_file = os.path.join(OUTPUT_BASE_DIR, f"{repo_name}_scancode_output.json")

    # 2. Build the ScanCode command
    cmd = [
        SCANCODE_BIN,
        # License Options
        "--license",
        "--license-text",
        "--filter-clues",
        "--license-clarity-score",
        # Statistics and Classification Options
        "--tallies",
        "--tallies-key-files",
        "--classify",
    ]

    # 3. Add dynamic ignore patterns
    for pattern in ignore_patterns:
        cmd.extend(["--ignore", pattern])

    # 4. Add output format and target path
    cmd.extend([
        "--json-pp", output_file,
        repo_path,
    ])

    logger.info("Starting ScanCode analysis on: %s", repo_name)
    logger.debug("ScanCode Output File: %s", output_file)

    # Execute subprocess
    # Using 'with' context manager ensures file descriptors are closed properly
    with subprocess.Popen(cmd) as process:
        returncode = process.wait()

    # Handle exit codes according to ScanCode documentation
    if returncode > 1:
        logger.error("ScanCode failed with critical error (exit code %d)", returncode)
        raise RuntimeError(f"ScanCode error (exit {returncode})")

    if returncode == 1:
        logger.warning("ScanCode completed with non-fatal errors (exit code 1).")

    if not os.path.exists(output_file):
        logger.error("ScanCode output file not found at %s", output_file)
        raise RuntimeError("ScanCode did not generate the JSON file")

    # 5. Post-process the JSON output
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            scancode_data = json.load(f)

        # Remove "license_detections" from top-level to reduce memory footprint/filesize
        # as we mostly use file-level details.
        scancode_data.pop("license_detections", None)

        # Save the optimized JSON back to disk
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(scancode_data, f, indent=4, ensure_ascii=False)

        logger.info("ScanCode analysis completed and JSON processed successfully.")
        return scancode_data

    except Exception as e:
        logger.exception("Error during ScanCode output processing")
        raise RuntimeError(f"Failed to process ScanCode output: {e}") from e


def detect_main_license_scancode(data: Dict[str, Any]) -> Union[Tuple[str, str], str]:
    """
    Identifies the main license of the project from ScanCode results.

    Strategy:
    1. Prioritize files named 'LICENSE' or 'license'.
    2. Fallback to 'COPYING' files.
    3. Last resort: check other relevant files containing license keywords.

    Args:
        data (Dict[str, Any]): The ScanCode JSON data.

    Returns:
        Union[Tuple[str, str], str]: A tuple (spdx_expression, file_path) if found,
        otherwise the string "UNKNOWN".
    """
    license_candidates = []
    copying_candidates = []
    other_candidates = []

    for entry in data.get("files", []):
        path = entry.get("path") or ""
        if not path:
            continue

        lower_path = path.lower()
        basename = os.path.basename(lower_path)

        # Skip notice or copyright files for main license detection
        if basename.startswith("notice") or basename.startswith("copyright"):
            continue

        # Classify candidates
        if basename.startswith("license"):
            license_candidates.append(entry)
        elif basename.startswith("copying"):
            copying_candidates.append(entry)
        elif "license" in lower_path or "copying" in lower_path:
            other_candidates.append(entry)

    # 1. Attempt primary choice: LICENSE files
    result = _pick_best_spdx(license_candidates)
    if result:
        return result

    # 2. Attempt fallback: COPYING files
    result = _pick_best_spdx(copying_candidates)
    if result:
        return result

    # 3. Last resort: other relevant paths
    result = _pick_best_spdx(other_candidates)
    if result:
        return result

    return "UNKNOWN"


def extract_file_licenses(scancode_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Extracts license expressions for each file from the ScanCode data.

    It aggregates multiple matches within a single file using 'AND'.

    Args:
        scancode_data (Dict[str, Any]): The ScanCode JSON output (filtered).

    Returns:
        Dict[str, str]: A dictionary mapping file paths to their detected SPDX expression.
    """
    results = {}

    for file_entry in scancode_data.get("files", []):
        path = file_entry.get("path")
        matches = file_entry.get("matches", [])

        if not matches:
            continue

        # Collect unique SPDX identifiers found in the file
        unique_spdx = list({m.get("license_spdx") for m in matches if m.get("license_spdx")})

        if not unique_spdx:
            continue

        # If multiple licenses are found in the same file, combine them with AND
        if len(unique_spdx) == 1:
            results[path] = unique_spdx[0]
        else:
            results[path] = " OR ".join(unique_spdx)

    return results
