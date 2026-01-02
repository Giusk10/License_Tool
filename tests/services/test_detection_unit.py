"""
License Detection Service Unit Test Module.

This module contains unit tests for the scanning and detection logic in
`app.services.scanner.detection`. It validates the integration with ScanCode
Toolkit, including process execution, output parsing, and the extraction
of primary and secondary licenses.

The suite is organized into three main categories:
1. ScanCode Execution: Managing subprocesses, exit codes, and ignore patterns.
2. Main License Detection: Identifying the primary project license.
3. File License Extraction: Aggregating detected licenses into SPDX expressions.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
from app.services.scanner.detection import (
    run_scancode,
    detect_main_license_scancode,
    extract_file_licenses
)


# ==================================================================================
#                          TEST CLASS: RUN SCANCODE
# ==================================================================================

class TestRunScancode:
    """
    Test suite for the 'run_scancode' function.

    Verifies subprocess execution, file I/O, ignore pattern loading,
    and error handling for various ScanCode exit codes.
    """

    def test_run_scancode_success_with_patterns(self, tmp_path):
        """
        Tests successful ScanCode execution with ignore patterns loaded.

        Validates that:
        - Ignore patterns are correctly loaded from patterns_to_ignore.json
        - ScanCode command is built with correct parameters
        - Output JSON is processed and optimized (license_detections removed)
        - Function returns parsed JSON data
        """
        # Setup
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        # Mock ignore patterns file
        patterns_data = {"ignored_patterns": ["*.pyc", "node_modules", "__pycache__"]}

        # Mock ScanCode output
        mock_scancode_output = {
            "headers": [{"tool_name": "scancode"}],
            "license_detections": [{"id": "detection1"}],  # Should be removed
            "files": [
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "MIT", "score": 100}
                    ]
                }
            ]
        }

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists") as mock_exists, \
             patch("builtins.open", mock_open(read_data=json.dumps(patterns_data))) as mock_file, \
             patch("json.load") as mock_json_load, \
             patch("json.dump") as mock_json_dump:

            # Setup mocks
            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # Mock file existence checks
            def exists_side_effect(path):
                if "patterns_to_ignore.json" in path:
                    return True
                if path.endswith("_scancode_output.json"):
                    return True
                return False
            mock_exists.side_effect = exists_side_effect

            # Mock JSON load/dump
            mock_json_load.return_value = mock_scancode_output.copy()

            # Execute
            result = run_scancode(repo_path)

            # Verify subprocess was called with correct parameters
            assert mock_popen.called
            cmd_args = mock_popen.call_args[0][0]
            assert "scancode" in cmd_args
            assert "--license" in cmd_args
            assert "--json-pp" in cmd_args
            assert repo_path in cmd_args

            # Verify JSON was processed (license_detections removed)
            assert mock_json_dump.called
            saved_data = mock_json_dump.call_args[0][0]
            assert "license_detections" not in saved_data
            assert "files" in saved_data

    def test_run_scancode_with_exit_code_1(self, tmp_path):
        """
        Tests ScanCode execution with exit code 1 (non-fatal warnings).

        Verifies that the function logs a warning but continues processing.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        mock_scancode_output = {
            "files": [{"path": "LICENSE", "license_detections": []}]
        }

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="{}")), \
             patch("json.load", return_value=mock_scancode_output), \
             patch("json.dump"):

            mock_process = MagicMock()
            mock_process.wait.return_value = 1  # Non-fatal error
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # Should not raise exception
            result = run_scancode(repo_path)
            assert result is not None
            assert "files" in result

    def test_run_scancode_critical_error(self, tmp_path):
        """
        Tests ScanCode execution with exit code > 1 (critical error).

        Verifies that a RuntimeError is raised with appropriate message.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists", return_value=False):

            mock_process = MagicMock()
            mock_process.wait.return_value = 2  # Critical error
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            with pytest.raises(RuntimeError) as exc_info:
                run_scancode(repo_path)

            assert "ScanCode error" in str(exc_info.value)
            assert "exit 2" in str(exc_info.value)

    def test_run_scancode_output_file_not_found(self, tmp_path):
        """
        Tests error handling when ScanCode doesn't generate output file.

        Verifies that a RuntimeError is raised when the expected JSON file
        is missing after ScanCode execution.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists", return_value=False):

            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            with pytest.raises(RuntimeError) as exc_info:
                run_scancode(repo_path)

            assert "did not generate the JSON file" in str(exc_info.value)

    def test_run_scancode_fallback_to_license_rules(self, tmp_path):
        """
        Tests fallback mechanism to license_rules.json when patterns_to_ignore.json
        is not available.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        rules_data = {"ignored_patterns": ["vendor", "test"]}
        mock_scancode_output = {"files": []}

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("builtins.open", mock_open(read_data=json.dumps(rules_data))), \
             patch("json.load", return_value=mock_scancode_output), \
             patch("json.dump"):

            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            def exists_side_effect(path):
                if "patterns_to_ignore.json" in path:
                    return False
                if "license_rules.json" in path:
                    return True
                if path.endswith("_scancode_output.json"):
                    return True
                return False

            with patch("os.path.exists", side_effect=exists_side_effect):
                result = run_scancode(repo_path)
                assert result is not None

    def test_run_scancode_invalid_json_in_patterns(self, tmp_path):
        """
        Tests handling of invalid JSON in ignore patterns file.

        Verifies that the function continues without patterns if JSON is malformed.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        mock_scancode_output = {"files": []}

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists") as mock_exists, \
             patch("builtins.open", mock_open(read_data="invalid json{")), \
             patch("json.load") as mock_json_load, \
             patch("json.dump"):

            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # First call to json.load raises JSONDecodeError for patterns file
            # Second call returns valid scancode output
            mock_json_load.side_effect = [
                json.JSONDecodeError("Invalid", "", 0),
                mock_scancode_output
            ]

            def exists_side_effect(path):
                if "patterns_to_ignore.json" in path:
                    return True
                if path.endswith("_scancode_output.json"):
                    return True
                return False
            mock_exists.side_effect = exists_side_effect

            # Should not raise exception, just log warning
            result = run_scancode(repo_path)
            assert result is not None

    def test_run_scancode_processing_error(self, tmp_path):
        """
        Tests error handling during JSON processing phase.

        Verifies that processing errors are caught and re-raised as RuntimeError.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists") as mock_exists:

            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            def exists_side_effect(path):
                if path.endswith("_scancode_output.json"):
                    return True
                return False
            mock_exists.side_effect = exists_side_effect

            # Simulate error during file reading
            with patch("builtins.open", side_effect=IOError("Disk error")):
                with pytest.raises(RuntimeError) as exc_info:
                    run_scancode(repo_path)

                assert "Failed to process ScanCode output" in str(exc_info.value)


# ==================================================================================
#                    TEST CLASS: DETECT MAIN LICENSE SCANCODE
# ==================================================================================

class TestDetectMainLicenseScancode:
    """
    Test suite for the 'detect_main_license_scancode' function.

    Validates the heuristic-based detection of the main project license,
    including package declarations, file depth scoring, and name-based weighting.
    """

    def test_detect_main_license_from_package(self):
        """
        Tests detection of main license from package declaration.

        When ScanCode detects a package with declared_license_expression,
        it should be prioritized as the most reliable source.
        """
        data = {
            "packages": [
                {
                    "declared_license_expression": "Apache-2.0",
                    "path": "package.json"
                }
            ],
            "files": []
        }

        result = detect_main_license_scancode(data)
        # When detecting from package, function returns only the license string
        assert result == "Apache-2.0"

    def test_detect_main_license_from_root_license_file(self):
        """
        Tests detection from LICENSE file at repository root.

        Root-level LICENSE files should receive the highest weight.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "MIT", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "MIT"
        assert path == "LICENSE"

    def test_detect_main_license_prefers_root_over_nested(self):
        """
        Tests that root-level licenses are preferred over nested ones.

        Files at depth 0 should win over identical licenses at greater depth.
        """
        data = {
            "files": [
                {
                    "path": "vendor/third_party/LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "BSD-3-Clause", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                },
                {
                    "path": "LICENSE.md",
                    "license_detections": [
                        {"license_expression_spdx": "MIT", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "MIT"
        assert path == "LICENSE.md"

    def test_detect_main_license_ignores_low_confidence(self):
        """
        Tests that low-confidence detections are filtered out.

        Files with percentage_of_license_text < 80% should be ignored.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "GPL-3.0", "score": 50}
                    ],
                    "percentage_of_license_text": 70.0  # Too low
                },
                {
                    "path": "COPYING",
                    "license_detections": [
                        {"license_expression_spdx": "MIT", "score": 100}
                    ],
                    "percentage_of_license_text": 90.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "MIT"

    def test_detect_main_license_from_manifest_files(self):
        """
        Tests detection from manifest files (package.json, setup.py, etc.).

        These files should receive high weight even without package declaration.
        """
        data = {
            "files": [
                {
                    "path": "package.json",
                    "license_detections": [
                        {"license_expression_spdx": "ISC", "score": 100}
                    ],
                    "percentage_of_license_text": 85.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "ISC"

    def test_detect_main_license_from_readme(self):
        """
        Tests detection from README files.

        README files should receive moderate weight as they often mention licenses.
        """
        data = {
            "files": [
                {
                    "path": "README.md",
                    "license_detections": [
                        {"license_expression_spdx": "Apache-2.0", "score": 90}
                    ],
                    "percentage_of_license_text": 85.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "Apache-2.0"

    def test_detect_main_license_ignores_blacklisted_dirs(self):
        """
        Tests that files in node_modules, vendor, test, docs are ignored.
        """
        data = {
            "files": [
                {
                    "path": "node_modules/package/LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "BSD-2-Clause", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                },
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "MIT", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "MIT"
        assert "node_modules" not in path

    def test_detect_main_license_returns_unknown_if_no_candidates(self):
        """
        Tests that UNKNOWN is returned when no valid licenses are found.
        """
        data = {
            "files": [
                {
                    "path": "test.py",
                    "license_detections": []
                }
            ]
        }

        result = detect_main_license_scancode(data)
        assert result == "UNKNOWN"

    def test_detect_main_license_with_license_text_match(self):
        """
        Tests that is_license_text flag increases weight appropriately.
        """
        data = {
            "files": [
                {
                    "path": "license_info.txt",
                    "license_detections": [
                        {
                            "license_expression_spdx": "MIT",
                            "score": 100,
                            "matched_rule": {"is_license_text": True}
                        }
                    ],
                    "percentage_of_license_text": 95.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "MIT"
        assert path == "license_info.txt"

    def test_detect_main_license_copying_file(self):
        """
        Tests that COPYING files are properly recognized.
        """
        data = {
            "files": [
                {
                    "path": "COPYING.txt",
                    "license_detections": [
                        {"license_expression_spdx": "GPL-2.0", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "GPL-2.0"
        assert path == "COPYING.txt"

    def test_detect_main_license_multiple_candidates_highest_weight_wins(self):
        """
        Tests that when multiple candidates exist, the one with highest
        cumulative weight is selected.
        """
        data = {
            "files": [
                {
                    "path": "src/utils/LICENSE",  # depth 2, name bonus
                    "license_detections": [
                        {"license_expression_spdx": "BSD-3-Clause", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                },
                {
                    "path": "LICENSE",  # depth 0, name bonus, should win
                    "license_detections": [
                        {"license_expression_spdx": "MIT", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                }
            ]
        }

        result, path = detect_main_license_scancode(data)
        assert result == "MIT"
        assert path == "LICENSE"


# ==================================================================================
#                    TEST CLASS: EXTRACT FILE LICENSES
# ==================================================================================

class TestExtractFileLicenses:
    """
    Test suite for the 'extract_file_licenses' function.

    Validates the extraction and aggregation of per-file license information
    into SPDX expressions.
    """

    def test_extract_file_licenses_single_match(self):
        """
        Tests extraction of a single license from a file.
        """
        data = {
            "files": [
                {
                    "path": "src/main.py",
                    "matches": [
                        {"license_spdx": "MIT"}
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        assert result == {"src/main.py": "MIT"}

    def test_extract_file_licenses_multiple_matches_or_operator(self):
        """
        Tests that multiple licenses in the same file are combined with OR.
        """
        data = {
            "files": [
                {
                    "path": "src/utils.py",
                    "matches": [
                        {"license_spdx": "MIT"},
                        {"license_spdx": "Apache-2.0"}
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        assert "src/utils.py" in result
        # Should contain both licenses with OR
        assert "MIT" in result["src/utils.py"]
        assert "Apache-2.0" in result["src/utils.py"]
        assert "OR" in result["src/utils.py"]

    def test_extract_file_licenses_no_matches(self):
        """
        Tests that files without license matches are excluded from results.
        """
        data = {
            "files": [
                {
                    "path": "src/test.py",
                    "matches": []
                }
            ]
        }

        result = extract_file_licenses(data)
        assert result == {}

    def test_extract_file_licenses_multiple_files(self):
        """
        Tests extraction across multiple files.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "matches": [{"license_spdx": "MIT"}]
                },
                {
                    "path": "src/main.py",
                    "matches": [{"license_spdx": "Apache-2.0"}]
                },
                {
                    "path": "tests/test.py",
                    "matches": []
                }
            ]
        }

        result = extract_file_licenses(data)
        assert len(result) == 2
        assert result["LICENSE"] == "MIT"
        assert result["src/main.py"] == "Apache-2.0"
        assert "tests/test.py" not in result

    def test_extract_file_licenses_null_license_spdx(self):
        """
        Tests that matches without license_spdx field are ignored.
        """
        data = {
            "files": [
                {
                    "path": "src/file.py",
                    "matches": [
                        {"license_spdx": None},
                        {"license_spdx": "MIT"}
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        assert result == {"src/file.py": "MIT"}

    def test_extract_file_licenses_empty_data(self):
        """
        Tests handling of empty ScanCode data.
        """
        data = {"files": []}

        result = extract_file_licenses(data)
        assert result == {}

    def test_extract_file_licenses_missing_files_key(self):
        """
        Tests handling of malformed data without 'files' key.
        """
        data = {}

        result = extract_file_licenses(data)
        assert result == {}

    def test_extract_file_licenses_deduplication(self):
        """
        Tests that duplicate SPDX identifiers in the same file are deduplicated.
        """
        data = {
            "files": [
                {
                    "path": "src/duplicate.py",
                    "matches": [
                        {"license_spdx": "MIT"},
                        {"license_spdx": "MIT"},  # Duplicate
                        {"license_spdx": "MIT"}   # Duplicate
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        # Should only contain MIT once, not "MIT OR MIT OR MIT"
        assert result["src/duplicate.py"] == "MIT"

    def test_extract_file_licenses_complex_scenario(self):
        """
        Tests a complex scenario with mixed file types and license patterns.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "matches": [{"license_spdx": "Apache-2.0"}]
                },
                {
                    "path": "src/main.py",
                    "matches": [
                        {"license_spdx": "Apache-2.0"},
                        {"license_spdx": "MIT"}
                    ]
                },
                {
                    "path": "vendor/lib.js",
                    "matches": [{"license_spdx": "BSD-3-Clause"}]
                },
                {
                    "path": "README.md",
                    "matches": []
                }
            ]
        }

        result = extract_file_licenses(data)
        assert len(result) == 3
        assert result["LICENSE"] == "Apache-2.0"
        assert "Apache-2.0" in result["src/main.py"]
        assert "MIT" in result["src/main.py"]
        assert result["vendor/lib.js"] == "BSD-3-Clause"
        assert "README.md" not in result

