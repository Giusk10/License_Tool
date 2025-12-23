"""
test: services/scanner/detection.py
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


class TestRunScancode:
    """Test per la funzione run_scancode"""

    @pytest.fixture
    def mock_scancode_deps(self, tmp_path):
        """
        Fixture per i path e subprocess.
        Usa tmp_path per garantire compatibilità con Windows.
        """
        # Crea un path temporaneo valido per il sistema operativo corrente
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
        """Test esecuzione corretta di ScanCode"""
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

        # Verifiche
        assert result == {"files": []} # license_detections rimosso
        mock_popen.assert_called_once()
        process_mock.wait.assert_called_once()

    @patch("app.services.scanner.detection.subprocess.Popen")
    @patch("app.services.scanner.detection.os.path.exists")
    def test_run_scancode_error_exit_code(self, mock_exists, mock_popen, mock_scancode_deps):
        """Test errore critico di ScanCode (exit code > 1)"""
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
        """Test fallimento se il file di output non viene generato"""
        process_mock = MagicMock()
        process_mock.wait.return_value = 0

        mock_popen.return_value.__enter__.return_value = process_mock
        mock_popen.return_value.__exit__.return_value = None

        # Simula: patterns esiste (True), output file NON esiste (False)
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
        """Test che i pattern di ignore vengano caricati e passati al comando"""
        process_mock = MagicMock()
        process_mock.wait.return_value = 0
        mock_popen.return_value.__enter__.return_value = process_mock

        mock_exists.return_value = True
        mock_load.side_effect = [
            {"ignored_patterns": ["*.tmp"]}, # Prima chiamata: regole ignore
            {"files": []} # Seconda chiamata: output scancode
        ]

        run_scancode("/path/to/repo")

        # Verifica che --ignore *.tmp sia nel comando
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
        """Test esecuzione senza file di ignore"""
        process_mock = MagicMock()
        process_mock.wait.return_value = 0
        mock_popen.return_value.__enter__.return_value = process_mock

        # Nessun file di ignore esiste, ma l'output directory sì (simulato)
        def exists_side_effect(path):
            if "json" in path and "scancode_output" not in path: # ignore/rules files
                return False
            return True # output dir/file

        mock_exists.side_effect = exists_side_effect
        mock_load.return_value = {"files": []}

        run_scancode("/path/to/repo")

        args, _ = mock_popen.call_args
        cmd_list = args[0]
        # Verifica che non ci siano flag --ignore
        assert "--ignore" not in cmd_list


class TestDetectMainLicense:
    """Test per la funzione detect_main_license_scancode"""

    def test_detect_license_file(self):
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
        data = {"files": [{"path": "random.txt"}]}
        with patch("app.services.scanner.detection._pick_best_spdx", return_value=None):
            result = detect_main_license_scancode(data)
            assert result == "UNKNOWN"


class TestExtractFileLicenses:
    """Test per la funzione extract_file_licenses"""

    def test_extract_single_license(self):
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
        # L'ordine del set non è garantito, controlliamo la presenza
        assert "MIT" in result["file1.py"]
        assert "Apache-2.0" in result["file1.py"]
        assert " AND " in result["file1.py"]

    def test_extract_no_matches(self):
        data = {
            "files": [
                {"path": "file1.py", "matches": []}
            ]
        }
        result = extract_file_licenses(data)
        assert "file1.py" not in result