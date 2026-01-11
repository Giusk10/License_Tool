"""
License Detection Service Unit Test Module.

Questo modulo contiene test unitari per le funzioni di rilevamento licenze in
`app.services.scanner.detection`. Si concentra sulla validazione della logica di parsing,
sull'estrazione delle licenze dai file, sulla gestione di edge case e sulla robustezza
contro input malformati o casi limite.

La suite copre:
1. Parsing dei risultati di ScanCode: Verifica la corretta estrazione delle licenze dai risultati JSON.
2. Gestione di file senza licenza: Assicura che i file privi di licenza siano gestiti correttamente.
3. Edge case: Testa la robustezza contro input nulli, stringhe vuote, file non standard.
4. Parsing di espressioni SPDX complesse: Valida la corretta interpretazione di espressioni booleane.
5. Integrazione con la pipeline di analisi: Verifica che i risultati siano compatibili con il resto del sistema.
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
    Test suite per la funzione 'run_scancode'.

    Verifica l'esecuzione dei subprocess, il codice di uscita, il caricamento dei modelli di ignoramento,
    e la gestione degli errori per vari codici di uscita di ScanCode.
    """

    def test_run_scancode_success_with_patterns(self, tmp_path):
        """
        Testa l'esecuzione riuscita di ScanCode con i modelli di ignoramento caricati.

        Valida che:
        - I modelli di ignoramento siano caricati correttamente dal file patterns_to_ignore.json
        - Il comando ScanCode sia costruito con i parametri corretti
        - L'output JSON venga elaborato e ottimizzato (rimozione delle license_detections)
        - La funzione restituisca i dati JSON analizzati
        """
        # Setup
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        # Mock del file dei modelli di ignoramento
        patterns_data = {"ignored_patterns": ["*.pyc", "node_modules", "__pycache__"]}

        # Mock dell'output di ScanCode
        mock_scancode_output = {
            "headers": [{"tool_name": "scancode"}],
            "license_detections": [{"id": "detection1"}],  # Dovrebbe essere rimossa
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

            # Configurazione dei mock
            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # Mock per i controlli dell'esistenza dei file
            def exists_side_effect(path):
                if "patterns_to_ignore.json" in path:
                    return True
                if path.endswith("_scancode_output.json"):
                    return True
                return False
            mock_exists.side_effect = exists_side_effect

            # Mock per il caricamento/salvataggio dei JSON
            mock_json_load.return_value = mock_scancode_output.copy()

            # Esecuzione
            result = run_scancode(repo_path)

            # Verifica che il subprocess sia stato chiamato con i parametri corretti
            assert mock_popen.called
            cmd_args = mock_popen.call_args[0][0]
            assert "scancode" in cmd_args
            assert "--license" in cmd_args
            assert "--json-pp" in cmd_args
            assert repo_path in cmd_args

            # Verifica che il JSON sia stato elaborato correttamente (license_detections rimossa)
            assert mock_json_dump.called
            saved_data = mock_json_dump.call_args[0][0]
            assert "license_detections" not in saved_data
            assert "files" in saved_data

    def test_run_scancode_with_exit_code_1(self, tmp_path):
        """
        Testa l'esecuzione di ScanCode con codice di uscita 1 (avvisi non fatali).

        Verifica che la funzione registri un avviso ma continui l'elaborazione.
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
            mock_process.wait.return_value = 1  # Errore non fatale
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # Non dovrebbe sollevare eccezioni
            result = run_scancode(repo_path)
            assert result is not None
            assert "files" in result

    def test_run_scancode_critical_error(self, tmp_path):
        """
        Testa l'esecuzione di ScanCode con codice di uscita > 1 (errore critico).

        Verifica che venga sollevata una RuntimeError con il messaggio appropriato.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        output_dir = str(tmp_path / "output")

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
             patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("os.path.exists", return_value=False):

            mock_process = MagicMock()
            mock_process.wait.return_value = 2  # Errore critico
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

        Verifica che venga sollevata una RuntimeError quando il file JSON atteso
        è mancante dopo l'esecuzione di ScanCode.
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
        Testa la gestione di JSON non valido nel file dei modelli di ignoramento.

        Verifica che la funzione continui senza modelli se il JSON è malformato.
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

            # Prima chiamata a json.load solleva JSONDecodeError per il file dei modelli
            # Seconda chiamata restituisce un valido output di scancode
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

            # Non dovrebbe sollevare eccezioni, solo registrare un avviso
            result = run_scancode(repo_path)
            assert result is not None

    def test_run_scancode_processing_error(self, tmp_path):
        """
        Testa la gestione degli errori durante la fase di elaborazione del JSON.

        Verifica che gli errori di elaborazione vengano catturati e rilanciati come RuntimeError.
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

            # Simula un errore durante la lettura del file
            with patch("builtins.open", side_effect=IOError("Disk error")):
                with pytest.raises(RuntimeError) as exc_info:
                    run_scancode(repo_path)

                assert "Failed to process ScanCode output" in str(exc_info.value)

    def test_run_scancode_auto_ignore_large_files_and_oserror(self, tmp_path):
        """
        Testa la logica di auto-ignoramento per file di grandi dimensioni e la gestione degli errori durante la scansione dei file.

        Copre:
        - Il blocco 'if os.path.getsize > limit_bytes'.
        - Il blocco 'except OSError: pass'.
        """
        repo_path = str(tmp_path / "test_repo")
        os.makedirs(repo_path, exist_ok=True)

        # Crea file di prova
        (tmp_path / "test_repo" / "normal.py").touch()
        (tmp_path / "test_repo" / "large.bin").touch()
        (tmp_path / "test_repo" / "locked.bin").touch()

        output_dir = str(tmp_path / "output")

        with patch("app.services.scanner.detection.OUTPUT_BASE_DIR", output_dir), \
                patch("app.services.scanner.detection.SCANCODE_BIN", "scancode"), \
                patch("subprocess.Popen") as mock_popen, \
                patch("os.path.exists", return_value=True), \
                patch("json.dump"):  # Mock dump per evitare problemi di scrittura file

            # Configurazione del processo di successo
            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.__enter__ = MagicMock(return_value=mock_process)
            mock_process.__exit__ = MagicMock(return_value=False)
            mock_popen.return_value = mock_process

            # Mock di os.walk per restituire i nostri file
            # formato tupla: (root, dirs, files)
            walk_data = [
                (repo_path, [], ["normal.py", "large.bin", "locked.bin"])
            ]

            # Limite di 1MB in byte
            limit = 1 * 1024 * 1024

            # Definisci gli effetti collaterali per getsize:
            # - normal.py -> dimensione ridotta
            # - large.bin -> dimensione grande (> limite)
            # - locked.bin -> solleva OSError
            def getsize_side_effect(path):
                if "large.bin" in path:
                    return limit + 100  # Attiva ignoramento
                if "locked.bin" in path:
                    raise OSError("Permission denied")  # Attiva gestore eccezioni
                return 100  # File normale

            with patch("os.walk", return_value=walk_data), \
                    patch("os.path.getsize", side_effect=getsize_side_effect):

                # Dobbiamo mockare open/json.load affinché la parte di post-elaborazione abbia successo
                with patch("builtins.open", mock_open(read_data='{"files": []}')):
                    run_scancode(repo_path)

            # Verifica che il file di grandi dimensioni sia stato aggiunto alla lista di ignoramento negli argomenti del comando
            call_args = mock_popen.call_args[0][0]
            # "large.bin" dovrebbe essere passato dopo "--ignore"
            assert "large.bin" in call_args
            # "normal.py" NON dovrebbe essere ignorato
            assert "normal.py" not in call_args


# ==================================================================================
#                    TEST CLASS: DETECT MAIN LICENSE SCANCODE
# ==================================================================================

class TestDetectMainLicenseScancode:
    """
    Test suite per la funzione 'detect_main_license_scancode'.

    Valida il rilevamento basato su euristiche della licenza principale del progetto,
    comprese le dichiarazioni di pacchetto, il punteggio di profondità del file e il peso basato sul nome.
    """

    def test_detect_main_license_from_package(self):
        """
        Testa il rilevamento della licenza principale dalla dichiarazione del pacchetto.

        Quando ScanCode rileva un pacchetto con declared_license_expression,
        dovrebbe essere prioritizzato come la fonte più affidabile.
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
        # Quando si rileva da un pacchetto, la funzione restituisce solo la stringa della licenza
        assert result == "Apache-2.0"

    def test_detect_main_license_from_root_license_file(self):
        """
        Testa il rilevamento da un file LICENSE nella radice del repository.

        I file LICENSE a livello di root dovrebbero ricevere il peso maggiore.
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
        Testa che le licenze a livello di root siano preferite rispetto a quelle annidate.

        I file a profondità 0 dovrebbero avere la precedenza su licenze identiche a maggiore profondità.
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
        Testa che le rilevazioni a bassa confidenza siano filtrate.

        I file con percentage_of_license_text < 80% dovrebbero essere ignorati.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {"license_expression_spdx": "GPL-3.0", "score": 50}
                    ],
                    "percentage_of_license_text": 70.0  # Troppo basso
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
        Testa il rilevamento da file di manifesto (package.json, setup.py, ecc.).

        Questi file dovrebbero ricevere un alto peso anche senza dichiarazione di pacchetto.
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

        I file README dovrebbero ricevere un peso moderato in quanto spesso menzionano le licenze.
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
        Testa che venga restituito UNKNOWN quando non ci sono licenze valide trovate.
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
        Testa che i file COPYING siano riconosciuti correttamente.
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
        Testa che quando esistono più candidati, venga selezionato quello con il peso cumulativo più alto.
        """
        data = {
            "files": [
                {
                    "path": "src/utils/LICENSE",  # profondità 2, bonus nome
                    "license_detections": [
                        {"license_expression_spdx": "BSD-3-Clause", "score": 100}
                    ],
                    "percentage_of_license_text": 95.0
                },
                {
                    "path": "LICENSE",  # profondità 0, bonus nome, dovrebbe vincere
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
        Testa la gestione delle rilevazioni mancanti del campo 'license_expression_spdx'.

        Copre il controllo 'if not spdx: continue' all'interno del ciclo.
        """
        data = {
            "files": [
                {
                    "path": "LICENSE",
                    "license_detections": [
                        {
                            # Mancanza di 'license_expression_spdx'
                            "score": 100,
                            "matched_rule": {"is_license_text": True}
                        }
                    ],
                    "percentage_of_license_text": 90.0
                }
            ]
        }

        # Dovrebbe restituire UNKNOWN perché l'unico candidato manca di un ID SPDX
        result = detect_main_license_scancode(data)
        assert result == "UNKNOWN"

# ==================================================================================
#                    TEST CLASS: EXTRACT FILE LICENSES
# ==================================================================================

class TestExtractFileLicenses:
    """
    Test suite per la funzione 'extract_file_licenses'.

    Valida l'estrazione e l'aggregazione delle informazioni sulla licenza per file
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
        # Dovrebbe contenere entrambe le licenze con OR
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
        Testa l'estrazione su più file.
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
                        {"license_spdx": "MIT"},  # Duplicato
                        {"license_spdx": "MIT"}   # Duplicato
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        # Dovrebbe contenere solo MIT una volta, non "MIT OR MIT OR MIT"
        assert result["src/duplicate.py"] == "MIT"

    def test_extract_file_licenses_complex_scenario(self):
        """
        Testa uno scenario complesso con tipi di file misti e modelli di licenza.
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
        Testa il filtraggio quando esistono corrispondenze ma non contengono chiavi di licenza valide.

        Copre il blocco 'if not unique_spdx: continue'.
        """
        data = {
            "files": [
                {
                    "path": "file.c",
                    "matches": [
                        {"score": 90},  # Mancanza di license_spdx
                        {"license_spdx": ""}  # Stringa vuota
                    ]
                }
            ]
        }

        result = extract_file_licenses(data)
        # Dovrebbe essere vuoto perché non ci sono ID SPDX validi estratti
        assert result == {}

