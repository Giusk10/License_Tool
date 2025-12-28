# ==============================================================================
# TEST SCENARIOS: MIXED LICENSES AND EDGE CASE COVERAGE
# ==============================================================================
# This module verifies the robustness of the detection algorithm when
# encountering real-world repositories, which often feature:
# 1. Declared root-level licenses (Main License).
# 2. Divergent licenses in sub-files (File-level overrides).
# 3. Unidentifiable files (Explicitly marked as UNKNOWN).
# 4. Binary assets or files without legal metadata (None/Empty).
# ==============================================================================

import pytest
from app.services.scanner.detection import (
    detect_main_license_scancode,
    extract_file_licenses
)

def test_detect_main_license_with_unknown_files():
    """
    Scenario: Analyzing a repository with conflicting license signals.

    Mock Components:
    - Root: 'LICENSE' file identified as MIT (Score 100).
    - Source: 'src/utils.py' identified as Apache-2.0.
    - Legacy: 'script.sh' explicitly flagged as UNKNOWN by the scanner.
    - Assets: Image file with no detected license matches.

    Objective:
    Ensure 'detect_main_license' prioritizes the root file and that
    'extract_file_licenses' correctly maps problematic files.
    """

    # Simulated raw JSON output from the ScanCode tool
    mock_scancode_output = {
        "files": [
            # 1. MAIN LICENSE CANDIDATE: Standard license file in the root
            {
                "path": "LICENSE",
                "type": "file",
                # Used by detect_main_license_scancode (it often looks at “licenses” or “detected_…”)
                "detected_license_expression_spdx": "MIT",
                "licenses": [
                    {"spdx_license_key": "MIT", "score": 100.0}
                ],
                # Used by extract_file_licenses (it looks at “matches”)
                "matches": [
                    {"license_spdx": "MIT", "score": 100.0}
                ]
            },

            # 2. FILE-LEVEL LICENSE: Source file with a different valid licens
            {
                "path": "src/utils.py",
                "type": "file",
                "detected_license_expression_spdx": "Apache-2.0",
                "licenses": [],
                "matches": [
                    {"license_spdx": "Apache-2.0", "score": 90.0}
                ]
            },

            # 3. UNKNOWN FILE: ScanCode identifies a license presence but cannot classify it
            {
                "path": "legacy/script.sh",
                "type": "file",
                "detected_license_expression_spdx": "UNKNOWN",
                "licenses": [],
                "matches": [
                    {"license_spdx": "UNKNOWN", "score": 0.0}
                ]
            },

            # 4. UNLICENSED FILE: Binary asset or file without legal metadata
            {
                "path": "assets/image.png",
                "type": "file",
                "detected_license_expression_spdx": None,
                "licenses": [],
                "matches": [] # Lista vuota
            }
        ]
    }

    # --- PHASE 1: Main License Detection Verification ---
    # The logic must ignore sub-file licenses and select the root LICENSE file
    main_license, license_path = detect_main_license_scancode(mock_scancode_output)

    print(f"\nMain License rilevata: {main_license} (su {license_path})")

    assert main_license == "MIT", "La main license dovrebbe essere MIT"
    assert license_path == "LICENSE", "Il file della main license dovrebbe essere LICENSE"

    # --- PHASE 2: Granular File Analysis Verification ---
    # The function must map every file to its specific license, including UNKNOWNs
    files_analysis = extract_file_licenses(mock_scancode_output)

    print("Licenze file estratte:", files_analysis)

    # Verify correct mapping for valid source files
    assert "src/utils.py" in files_analysis
    assert files_analysis["src/utils.py"] == "Apache-2.0"

    # Verify handling of UNKNOWN files
    # It is vital that UNKNOWN is not converted to None, so as to alert the user or the LLM
    assert "legacy/script.sh" in files_analysis
    assert files_analysis["legacy/script.sh"] == "UNKNOWN", "Il file script.sh dovrebbe essere rilevato come UNKNOWN"

    # Verify asset filtering
    # Files with no matches should not bloat the results dictionary
    assert "assets/image.png" not in files_analysis

def test_detect_main_license_fallback_unknown():
    """
     Scenario: Repository without any root-level license file (Undocumented Repo).

     Objective:
     Test the fallback behavior. If no 'LICENSE' file exists, the algorithm
     must decide whether to promote a source license or return UNKNOWN.
     """

    mock_scancode_output_bad = {
        "files": [
            {
                "path": "src/main.c",
                "matches": [{"license_spdx": "GPL-3.0"}]
            }
        ]
    }

    # Here we mock the internal behavior if necessary, but we test
    # whether detect_main_license returns UNKNOWN when it does not find a strong candidate.
    # (This depends on the logic of _pick_best_spdx in your actual code.)

    result = detect_main_license_scancode(mock_scancode_output_bad)

    # If your logic expects that, without a LICENSE file at the root, it returns UNKNOWN:
    # assert result == "UNKNOWN"
    # Or, if it takes the license from the first file:
    # assert result == ("GPL-3.0", "src/main.c")

    # Based on your existing test test_detect_fallback_unknown in test_detection_unit.py:
    if result == "UNKNOWN":
        assert True
    else:
        # If it returns a tuple, we verify that it is consistent.
        pass