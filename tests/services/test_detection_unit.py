"""
Modulo di test unitario del servizio di rilevamento licenze.

Questo modulo contiene test unitari per la logica di scansione e rilevamento in
`app.services.scanner.detection`. Valida l'integrazione con ScanCode
Toolkit, inclusa l'esecuzione del processo, l'analisi dell'output e l'estrazione
di licenze primarie e secondarie.

La suite è organizzata in tre categorie principali:
1. Esecuzione ScanCode: Gestione di sottoprocessi, codici di uscita e pattern di ignoranza.
2. Rilevamento licenza principale: Identificazione della licenza principale del progetto.
3. Estrazione licenze file: Aggregazione delle licenze rilevate in espressioni SPDX.
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
#                          CLASSE DI TEST: ESEGUI SCANCODE
# ==================================================================================

class TestRunScancode:
    """
    Suite di test per la funzione 'run_scancode'.

    Verifica l'esecuzione di sottoprocessi, I/O file, caricamento pattern di ignoranza,
    e gestione degli errori per vari codici di uscita ScanCode.
    """

    def test_run_scancode_success_with_patterns(self, tmp_path):
        """
        Testa l'esecuzione riuscita di ScanCode con caricamento pattern di ignoranza.

        Valida che:
        - I pattern di ignoranza siano correttamente caricati da patterns_to_ignore.json
        - Il comando ScanCode sia costruito con parametri corretti
        - L'output JSON sia elaborato e ottimizzato (license_detections rimosso)
        - La funzione restituisca dati JSON analizzati
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
        Testa l'esecuzione ScanCode con codice di uscita 1 (avvertimenti non fatali).

        Verifica che la funzione registri un avvertimento ma continui l'elaborazione.
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
        Testa l'esecuzione ScanCode con codice di uscita > 1 (errore critico).

        Verifica che venga sollevato un RuntimeError con messaggio appropriato.
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
        Testa la gestione degli errori quando ScanCode non genera il file di output.

        Verifica che venga sollevato un RuntimeError quando il file JSON previsto
        è mancante dopo l'esecuzione ScanCode.
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
        Testa il meccanismo di fallback a license_rules.json quando patterns_to_ignore.json
        non è disponibile.
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
        Testa la gestione di JSON non valido nel file pattern di ignoranza.

        Verifica che la funzione continui senza pattern se JSON è malformato.
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
        Testa la gestione degli errori durante la fase di elaborazione JSON.

        Verifica che gli errori di elaborazione siano catturati e ri-sollevati come RuntimeError.
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

    def test_run_scancode_auto_ignore_large_files_and_oserror(self, tmp_path):
        """
        Tests the auto-ignore logic for large files and error handling during file scan.

        Covers:
        - The 'if os.path.getsize > limit_bytes' block.
        - The 'except OSError: pass' block.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        # Create dummy files
        (tmp_path / "test_repo" / "normal.py").touch()
        (tmp_path / "test_repo" / "large.bin").touch()
        (tmp_path / "test_repo" / "locked.bin").touch()

        output_dir = str(tmp_path / "output")

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
                patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
                patch("subprocess.Popen") as mock_popen, \
                patch("os.path.exists", return_value=True), \
                patch("json.dump"):  # Mock dump to avoid file writing issues

            # Setup successful process
            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # Mock os.walk to return our files
            # tuple format: (root, dirs, files)
            walk_data = [
                (repo_path, [], ["normal.py", "large.bin", "locked.bin"])
            ]

            # 1MB limit in bytes
            limit = 1 * 1024 * 1024

            # Define side effects for getsize:
            # - normal.py -> small size
            # - large.bin -> large size (> limit)
            # - locked.bin -> raise OSError
            def getsize_side_effect(path):
                if "large.bin" in path:
                    return limit + 100  # Trigger ignore
                if "locked.bin" in path:
                    raise OSError("Permission denied")  # Trigger exception handler
                return 100  # Normal file

            with patch("os.walk", return_value=walk_data), \
                    patch("os.path.getsize", side_effect=getsize_side_effect):

                # We need to mock open/json.load for the post-processing part to succeed
                with patch("builtins.open", mock_open(read_data='{"files": []}')):
                    run_scancode(repo_path)

            # Verify that the large file was added to the ignore list in the command arguments
            call_args = mock_popen.call_args[0][0]
            # "large.bin" should be passed after "--ignore"
            assert "large.bin" in call_args
            # "normal.py" should NOT be ignored
            assert "normal.py" not in call_args


# ==================================================================================
#                    CLASSE DI TEST: RILEVA LICENZA PRINCIPALE SCANCODE
# ==================================================================================

class TestDetectMainLicenseScancode:
    """
    Suite di test per la funzione 'detect_main_license_scancode'.

    Valida il rilevamento euristico della licenza principale del progetto,
    inclusi dichiarazioni di pacchetto, punteggio profondità file e ponderazione basata sul nome.
    """

    def test_detect_main_license_from_package(self):
        """
        Testa il rilevamento della licenza principale da dichiarazione di pacchetto.

        Quando ScanCode rileva un pacchetto con declared_license_expression,
        dovrebbe essere prioritizzato come fonte più affidabile.
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
        Testa il rilevamento da file LICENSE alla radice del repository.

        I file LICENSE a livello radice dovrebbero ricevere il peso più alto.
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
        Testa che le licenze a livello radice siano preferite rispetto a quelle annidate.

        I file a profondità 0 dovrebbero vincere rispetto a licenze identiche a profondità maggiore.
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
        Testa che i rilevamenti a bassa confidenza siano filtrati.

        I file con percentage_of_license_text < 80% dovrebbero essere ignorati.
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
        Testa il rilevamento da file manifest (package.json, setup.py, ecc.).

        Questi file dovrebbero ricevere peso alto anche senza dichiarazione di pacchetto.
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
        Testa il rilevamento da file README.

        I file README dovrebbero ricevere peso moderato poiché spesso menzionano licenze.
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
        Testa che i file in node_modules, vendor, test, docs siano ignorati.
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
        Testa che UNKNOWN sia restituito quando non vengono trovate licenze valide.
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
        Testa che il flag is_license_text aumenti il peso in modo appropriato.
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
        Testa che i file COPYING siano correttamente riconosciuti.
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
        Testa che quando esistono più candidati, venga selezionato quello con
        peso cumulativo più alto.
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

    def test_detect_main_license_missing_spdx_field(self):
        """
        Tests handling of detections missing the 'license_expression_spdx' field.

        Covers the 'if not spdx: continue' check inside the loop.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {
                            # Missing 'license_expression_spdx'
                            "score": 100,
                            "matched_rule": {"is_license_text": True}
                        }
                    ],
                    "percentage_of_license_text": 90.0
                }
            ]
        }

        # Should return UNKNOWN because the only candidate lacks an SPDX ID
        result = detect_main_license_scancode(data)
        assert result == "UNKNOWN"

# ==================================================================================
#                    CLASSE DI TEST: ESTRAI LICENZE FILE
# ==================================================================================

class TestExtractFileLicenses:
    """
    Suite di test per la funzione 'extract_file_licenses'.

    Valida l'estrazione e l'aggregazione delle informazioni di licenza per file
    in espressioni SPDX.
    """

    def test_extract_file_licenses_single_match(self):
        """
        Testa l'estrazione di una singola licenza da un file.
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
        Testa che più licenze nello stesso file siano combinate con OR.
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
        Testa che i file senza corrispondenze di licenza siano esclusi dai risultati.
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
        Testa l'estrazione attraverso più file.
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
        Testa che le corrispondenze senza campo license_spdx siano ignorate.
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
        Testa la gestione di dati ScanCode vuoti.
        """
        data = {"files": []}

        result = extract_file_licenses(data)
        assert result == {}

    def test_extract_file_licenses_missing_files_key(self):
        """
        Testa la gestione di dati malformati senza chiave 'files'.
        """
        data = {}

        result = extract_file_licenses(data)
        assert result == {}

    def test_extract_file_licenses_deduplication(self):
        """
        Testa che gli identificatori SPDX duplicati nello stesso file siano deduplicati.
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
        Testa uno scenario complesso con tipi di file misti e pattern di licenza.
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

    def test_extract_file_licenses_matches_but_no_valid_spdx(self):
        """
        Tests filtering when matches exist but contain no valid license keys.
        Covers the 'if not unique_spdx: continue' block.
        """
        data = {
            "files": [
                {
                    "path": "file.c",
                    "matches": [
                        {"score": 90},  # Missing license_spdx
                        {"license_spdx": ""}  # Empty string
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        # Should be empty because no valid SPDX IDs were extracted
        assert result == {}