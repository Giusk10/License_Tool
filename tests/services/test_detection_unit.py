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
#                       TEST CLASS: SCANCODE EXECUTION
# ==================================================================================

class TestRunScancode:
    """
    Tests for the 'run_scancode' function.

    Focuses on the interaction with the operating system, validating that the
    ScanCode binary is called with correct arguments and that its output
    is safely ingested.
    """


    @pytest.fixture
    def mock_scancode_deps(self, tmp_path):
        """
        Provides cross-platform temporary paths for scanning tests.

        Ensures that output directories and binary paths are mocked correctly
        regardless of the host operating system (Windows/Linux).
        """
        # Create a temporary path valid for the current operating system
        temp_output_dir = tmp_path / "output"

        with patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("app.services.scanner.detection.OUTPUT_BASE_DIR", str(temp_output_dir)):
            yield

    @patch("app.services.scanner.detection.subprocess.Popen")
    @patch("app.services.scanner.detection.os.path.exists")
    @patch("app.services.scanner.detection.open")
    @patch("app.services.scanner.detection.json.load")
    @patch("app.services.scanner.detection.json.dump")


    def test_run_scancode_success(self, mock_json_dump, mock_json_load, mock_open_func, mock_exists, mock_popen, mock_scancode_deps):
        """
         Validates a successful ScanCode execution flow.

         Ensures that when ScanCode exits with code 0, the service correctly
         parses the resulting JSON and strips unnecessary metadata before
         returning the file list.
         """
        # Setup Mock Process
        process_mock = MagicMock()
        process_mock.wait.return_value = 0

        # Configure context manager (__enter__ returns the process_mock)
        mock_popen.return_value.__enter__.return_value = process_mock
        mock_popen.return_value.__exit__.return_value = None

        # Mock filesystem
        mock_exists.side_effect = lambda path: True  # Tutto esiste (rules, output)
        mock_json_load.return_value = {"files": [], "license_detections": []} # Fake output

        result = run_scancode("/path/to/repo")

        # Checks
        assert result == {"files": []} # license_detections rimosso
        mock_popen.assert_called_once()
        process_mock.wait.assert_called_once()

    @patch("app.services.scanner.detection.subprocess.Popen")
    @patch("app.services.scanner.detection.os.path.exists")


    def test_run_scancode_error_exit_code(self, mock_exists, mock_popen, mock_scancode_deps):
        """
         Tests handling of ScanCode process failures.

         Verifies that if ScanCode returns a critical error code (e.g., code 2),
          the service raises a RuntimeError with a descriptive message.
         """
        process_mock = MagicMock()
        process_mock.wait.return_value = 2

        mock_popen.return_value.__enter__.return_value = process_mock
        mock_popen.return_value.__exit__.return_value = None

        # Mock ignore file existence to avoid unrelated errors
        mock_exists.return_value = True

        with pytest.raises(RuntimeError, match="ScanCode error"):
            run_scancode("/path/to/repo")

    @patch("app.services.scanner.detection.subprocess.Popen")
    @patch("app.services.scanner.detection.os.path.exists")


    def test_run_scancode_no_output_file(self, mock_exists, mock_popen, mock_scancode_deps):
        """
         Verifies behavior when ScanCode fails to generate an output file.

         Ensures that if the binary finishes but the expected JSON result is
         missing, the service detects the inconsistency and raises an error.
         """
        process_mock = MagicMock()
        process_mock.wait.return_value = 0

        mock_popen.return_value.__enter__.return_value = process_mock
        mock_popen.return_value.__exit__.return_value = None


        # Simulation: ignore rules file exists (True), but output file DOES NOT (False)
        def side_effect(path):
            if "scancode_output.json" in path:
                return False
            return True

        mock_exists.side_effect = side_effect

        with pytest.raises(RuntimeError, match="did not generate the JSON file"):
            run_scancode("/path/to/repo")

    @patch("app.services.scanner.detection.subprocess.Popen")
    @patch("app.services.scanner.detection.os.path.exists")
    @patch("app.services.scanner.detection.open", new_callable=mock_open, read_data='{"ignored_patterns": ["*.tmp"]}')
    @patch("app.services.scanner.detection.json.load")
    @patch("app.services.scanner.detection.json.dump")


    def test_run_scancode_with_license_rules(self, mock_dump, mock_load, mock_file, mock_exists, mock_popen, mock_scancode_deps):
        """
        Tests the application of 'ignore' patterns during scanning.

        Ensures that patterns defined in 'license_rules.json' are correctly
        passed to the ScanCode CLI via the '--ignore' flag.
        """
        process_mock = MagicMock()
        process_mock.wait.return_value = 0
        mock_popen.return_value.__enter__.return_value = process_mock

        mock_exists.return_value = True
        mock_load.side_effect = [
            {"ignored_patterns": ["*.tmp"]}, # First call: rules ignore
            {"files": []} # Second call: scancode output
        ]

        run_scancode("/path/to/repo")

        # Make sure --ignore *.tmp is in the command
        args, _ = mock_popen.call_args
        cmd_list = args[0]
        assert "--ignore" in cmd_list
        assert "*.tmp" in cmd_list

    @patch("app.services.scanner.detection.subprocess.Popen")
    @patch("app.services.scanner.detection.os.path.exists")
    @patch("app.services.scanner.detection.open", new_callable=mock_open)
    @patch("app.services.scanner.detection.json.load")
    @patch("app.services.scanner.detection.json.dump")


    def test_run_scancode_no_ignore_files(self, mock_dump, mock_load, mock_file, mock_exists, mock_popen, mock_scancode_deps):
        """
        Tests the execution flow when no ignore configuration is present.

        Verifies that if the 'license_rules.json' file (or any ignore-related
        config) is missing from the file system, the service proceeds with
        a standard scan without appending the '--ignore' flag to the
        ScanCode command.
        """
        process_mock = MagicMock()
        process_mock.wait.return_value = 0
        mock_popen.return_value.__enter__.return_value = process_mock

        # Side effect: Rules/Ignore files do not exist, but output infra does.
        def exists_side_effect(path):
            if "json" in path and "scancode_output" not in path: # ignore/rules files
                return False
            return True # output dir/file

        mock_exists.side_effect = exists_side_effect
        mock_load.return_value = {"files": []}

        run_scancode("/path/to/repo")

        # Command Line verification
        args, _ = mock_popen.call_args
        cmd_list = args[0]

        # Ensures that the command is clean and doesn't contain orphan --ignore flags
        assert "--ignore" not in cmd_list


class TestDetectMainLicense:
    """
    Tests for the 'detect_main_license_scancode' function.

    Validates the heuristic used to identify the project's primary license
    from the bulk scan data.
    """


    def test_detect_license_file(self):
        """
        Verifies detection of the primary license from root-level files.

        Ensures that if a standard LICENSE file is found, its license key
        is prioritized as the project's main license.
        """
        data = {
            "files": [
                {"path": "LICENSE", "licenses": [{"spdx_license_key": "MIT"}]},
                {"path": "src/main.py", "licenses": []}
            ]
        }

        with patch("app.services.scanner.detection._pick_best_spdx") as mock_pick:
            mock_pick.return_value = ("MIT", "LICENSE")
            result = detect_main_license_scancode(data)
            assert result == ("MIT", "LICENSE")


    def test_detect_fallback_unknown(self):
        """
        Ensures a safe fallback when no main license is detected.

        Validates that if the scanning data contains no obvious project
        license, the service returns "UNKNOWN" instead of failing.
        """
        data = {"files": [{"path": "random.txt"}]}
        with patch("app.services.scanner.detection._pick_best_spdx", return_value=None):
            result = detect_main_license_scancode(data)
            assert result == "UNKNOWN"

# ==================================================================================
#                     TEST CLASS: FILE LICENSE EXTRACTION
# ==================================================================================

class TestExtractFileLicenses:
    """
    Tests for the 'extract_file_licenses' function.

    Verifies the transformation of ScanCode's raw file-level matches into
    consolidated SPDX expressions.
    """


    def test_extract_single_license(self):
        """Checks simple extraction for files with exactly one license."""
        data = {
            "files": [
                {
                    "path": "file1.py",
                    "matches": [{"license_spdx": "MIT"}]
                }
            ]
        }
        result = extract_file_licenses(data)
        assert result["file1.py"] == "MIT"


    def test_extract_multiple_licenses_combined(self):
        """
        Validates merging of multiple licenses for a single file.

        Ensures that if a file contains multiple licenses, they are combined
        using the ' OR ' operator into a single SPDX expression.
        """
        data = {
            "files": [
                {
                    "path": "file1.py",
                    "matches": [
                        {"license_spdx": "MIT"},
                        {"license_spdx": "Apache-2.0"}
                    ]
                }
            ]
        }
        result = extract_file_licenses(data)
        # The order of the set is not guaranteed, we check the presence
        assert "MIT" in result["file1.py"]
        assert "Apache-2.0" in result["file1.py"]
        # Multiple licenses are now joined with OR (not AND)
        assert " OR " in result["file1.py"]


    def test_extract_no_matches(self):
        """Ensures files with no detected licenses are skipped from the result map."""
        data = {
            "files": [
                {"path": "file1.py", "matches": []}
            ]
        }
        result = extract_file_licenses(data)
        assert "file1.py" not in result