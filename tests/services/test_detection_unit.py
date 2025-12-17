import pytest
import json
import os
from unittest.mock import patch, mock_open, MagicMock
from app.services.scanner.detection import run_scancode, detect_main_license_scancode, extract_file_licenses


class TestRunScancode:
    @patch('app.services.scanner.detection.subprocess.Popen')
    @patch('app.services.scanner.detection.os.path.exists')
    @patch('app.services.scanner.detection.json.load')
    @patch('app.services.scanner.detection.json.dump')
    @patch('app.services.scanner.detection.os.makedirs')
    @patch('app.services.scanner.detection.os.path.join')
    @patch('app.services.scanner.detection.os.path.basename')
    @patch('app.services.scanner.detection.os.path.normpath')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_scancode_success(self, mock_file, mock_normpath, mock_basename, mock_join, mock_makedirs, mock_dump, mock_load, mock_exists, mock_popen):
        # Setup mocks
        mock_normpath.return_value = '/path/to/repo'
        mock_basename.return_value = 'repo'
        mock_join.side_effect = lambda *args: '/'.join(args)  # Simple join for paths
        mock_exists.return_value = True  # patterns_to_ignore.json exists
        mock_load.return_value = {"ignored_patterns": ["*.txt", "*.md"]}
        mock_popen.return_value.wait.return_value = 0
        mock_exists.side_effect = [True, True]  # First for patterns, second for output file
        mock_load.side_effect = [{"ignored_patterns": ["*.txt", "*.md"]}, {"files": [], "license_detections": "removed"}]
        mock_dump.return_value = None

        # Call function
        result = run_scancode('/path/to/repo')

        # Assertions
        assert result == {"files": []}
        mock_popen.assert_called_once()
        mock_dump.assert_called_once()

    @patch('app.services.scanner.detection.subprocess.Popen')
    @patch('app.services.scanner.detection.os.path.exists')
    def test_run_scancode_error_exit_code(self, mock_exists, mock_popen):
        mock_popen.return_value.wait.return_value = 2
        with pytest.raises(RuntimeError, match="ScanCode error \\(exit 2\\)"):
            run_scancode('/path/to/repo')

    @patch('app.services.scanner.detection.subprocess.Popen')
    @patch('app.services.scanner.detection.os.path.exists')
    @patch('app.services.scanner.detection.json.load')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_scancode_no_output_file(self, mock_file, mock_load, mock_exists, mock_popen):
        mock_popen.return_value.wait.return_value = 0
        mock_exists.return_value = False  # Output file not exists
        with pytest.raises(RuntimeError, match="ScanCode did not generate the JSON file"):
            run_scancode('/path/to/repo')

    @patch('app.services.scanner.detection.subprocess.Popen')
    @patch('app.services.scanner.detection.os.path.exists')
    @patch('app.services.scanner.detection.json.load')
    @patch('app.services.scanner.detection.json.dump')
    @patch('app.services.scanner.detection.os.makedirs')
    @patch('app.services.scanner.detection.os.path.join')
    @patch('app.services.scanner.detection.os.path.basename')
    @patch('app.services.scanner.detection.os.path.normpath')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_scancode_with_license_rules(self, mock_file, mock_normpath, mock_basename, mock_join, mock_makedirs, mock_dump, mock_load, mock_exists, mock_popen):
        # Setup mocks for case where patterns_to_ignore.json does not exist, but license_rules.json does
        mock_normpath.return_value = '/path/to/repo'
        mock_basename.return_value = 'repo'
        mock_join.side_effect = lambda *args: '/'.join(args)
        mock_exists.side_effect = [False, True, True]  # patterns_path False, rules_path True, output_file True
        mock_load.side_effect = [{"ignored_patterns": ["*.log", "*.tmp"]}, {"files": [], "license_detections": "removed"}]
        mock_popen.return_value.wait.return_value = 0
        mock_dump.return_value = None

        # Call function
        result = run_scancode('/path/to/repo')

        # Assertions
        assert result == {"files": []}
        mock_popen.assert_called_once()
        # Verify that --ignore was added for the patterns
        cmd = mock_popen.call_args[0][0]
        assert "--ignore" in cmd
        assert "*.log" in cmd
        assert "*.tmp" in cmd

    @patch('app.services.scanner.detection.subprocess.Popen')
    @patch('app.services.scanner.detection.os.path.exists')
    @patch('app.services.scanner.detection.json.load')
    @patch('app.services.scanner.detection.json.dump')
    @patch('app.services.scanner.detection.os.makedirs')
    @patch('app.services.scanner.detection.os.path.join')
    @patch('app.services.scanner.detection.os.path.basename')
    @patch('app.services.scanner.detection.os.path.normpath')
    @patch('builtins.open', new_callable=mock_open)
    def test_run_scancode_no_ignore_files(self, mock_file, mock_normpath, mock_basename, mock_join, mock_makedirs, mock_dump, mock_load, mock_exists, mock_popen):
        # Setup mocks for case where neither patterns_to_ignore.json nor license_rules.json exist
        mock_normpath.return_value = '/path/to/repo'
        mock_basename.return_value = 'repo'
        mock_join.side_effect = lambda *args: '/'.join(args)
        mock_exists.side_effect = [False, False, True]  # patterns_path False, rules_path False, output_file True
        mock_load.return_value = {"files": [], "license_detections": "removed"}
        mock_popen.return_value.wait.return_value = 0
        mock_dump.return_value = None

        # Call function
        result = run_scancode('/path/to/repo')

        # Assertions
        assert result == {"files": []}
        mock_popen.assert_called_once()
        # Verify no --ignore in cmd since no patterns
        cmd = mock_popen.call_args[0][0]
        assert "--ignore" not in cmd


class TestDetectMainLicenseScancode:
    @patch('app.services.scanner.detection._pick_best_spdx')
    def test_detect_main_license_license_file(self, mock_pick):
        mock_pick.side_effect = [('MIT', '/path/LICENSE'), None, None]
        data = {"files": [{"path": "/path/LICENSE"}]}
        result = detect_main_license_scancode(data)
        assert result == ('MIT', '/path/LICENSE')
        mock_pick.assert_called()

    @patch('app.services.scanner.detection._pick_best_spdx')
    def test_detect_main_license_copying_file(self, mock_pick):
        mock_pick.side_effect = [None, ('GPL-3.0', '/path/COPYING'), None]
        data = {"files": [{"path": "/path/COPYING"}]}
        result = detect_main_license_scancode(data)
        assert result == ('GPL-3.0', '/path/COPYING')

    @patch('app.services.scanner.detection._pick_best_spdx')
    def test_detect_main_license_other_file(self, mock_pick):
        mock_pick.side_effect = [None, None, ('Apache-2.0', '/path/some/license.txt')]
        data = {"files": [{"path": "/path/some/license.txt"}]}
        result = detect_main_license_scancode(data)
        assert result == ('Apache-2.0', '/path/some/license.txt')

    @patch('app.services.scanner.detection._pick_best_spdx')
    def test_detect_main_license_unknown(self, mock_pick):
        mock_pick.return_value = None
        data = {"files": []}
        result = detect_main_license_scancode(data)
        assert result == "UNKNOWN"

    def test_detect_main_license_ignore_notice(self):
        data = {"files": [{"path": "/path/NOTICE"}, {"path": "/path/LICENSE"}]}
        with patch('app.services.scanner.detection._pick_best_spdx') as mock_pick:
            mock_pick.return_value = ('MIT', '/path/LICENSE')
            result = detect_main_license_scancode(data)
            assert result == ('MIT', '/path/LICENSE')


class TestExtractFileLicenses:
    def test_extract_file_licenses_single_match(self):
        llm_data = {
            "files": [
                {"path": "file1.py", "matches": [{"license_spdx": "MIT"}]},
                {"path": "file2.py", "matches": []}
            ]
        }
        result = extract_file_licenses(llm_data)
        assert result == {"file1.py": "MIT"}

    def test_extract_file_licenses_multiple_matches(self):
        llm_data = {
            "files": [
                {"path": "file1.py", "matches": [{"license_spdx": "MIT"}, {"license_spdx": "Apache-2.0"}]}
            ]
        }
        result = extract_file_licenses(llm_data)
        # Since set order is not guaranteed, check that both licenses are present
        assert "MIT" in result["file1.py"]
        assert "Apache-2.0" in result["file1.py"]
        assert "AND" in result["file1.py"]

    def test_extract_file_licenses_no_matches(self):
        llm_data = {"files": [{"path": "file1.py", "matches": []}]}
        result = extract_file_licenses(llm_data)
        assert result == {}

    def test_extract_file_licenses_no_spdx(self):
        llm_data = {
            "files": [
                {"path": "file1.py", "matches": [{"license_spdx": None}]}
            ]
        }
        result = extract_file_licenses(llm_data)
        assert result == {}
