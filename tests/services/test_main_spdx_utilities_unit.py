"""
test: services/scanner/test_main_spdx_utilities_unit.py

Test unitari per le funzioni di utilità SPDX utilizzate nel servizio scanner.
Questi test verificano la logica per estrarre e prioritizzare espressioni di licenza SPDX valide
da strutture di output ScanCode, gestendo casi limite come percorsi mancanti, valori invalidi,
e prioritizzazione profondità directory.
"""

import pytest
from app.services.scanner import main_spdx_utilities as util


def test_extract_skips_invalid_spdx_values_before_falling_back():
    """
    Verifica che _extract_first_valid_spdx salti valori invalidi (come 'UNKNOWN' o stringhe vuote)
    nei campi prioritari e cada correttamente indietro a campi successivi (ad es., license_detections).
    """
    entry = {
        "path": "dist/LICENSE",
        # Should be skipped because it is 'UNKNOWN'
        "detected_license_expression_spdx": "UNKNOWN",
        "license_detections": [
            {"license_expression_spdx": ""},        # Should be skipped (empty)
            {"license_expression_spdx": "MPL-2.0"}  # Valid target
        ],
        "licenses": [{"spdx_license_key": "Apache-2.0"}]
    }
    assert util._extract_first_valid_spdx(entry) == ("MPL-2.0", "dist/LICENSE")


def test_pick_best_returns_none_for_empty_entries():
    """
    Verifica che _pick_best_spdx restituisca None quando la lista di input è vuota o None.
    """
    assert util._pick_best_spdx([]) is None
    assert util._pick_best_spdx(None) is None


def test_pick_best_skips_non_mapping_entries():
    """
    Verifica che _pick_best_spdx ignori voci che non sono dizionari (ad es., None, stringhe)
    e selezioni con successo una licenza valida dalle voci valide rimanenti.
    """
    entries = [
        None,
        "not-a-dict",
        # Valid entry but likely lower priority due to no explicit detected expression
        {"path": "LICENSE", "licenses": [{"spdx_license_key": "Apache-2.0"}]},
        # Another valid entry
        {"path": "components/lib/LICENSE", "detected_license_expression_spdx": "MIT"}
    ]
    # Expects Apache-2.0 because LICENSE (depth 0) is preferred over components/lib/LICENSE (depth 2)
    assert util._pick_best_spdx(entries) == ("Apache-2.0", "LICENSE")


def test_is_valid_filters_none_empty_unknown():
    """
    Verifica che _is_valid identifichi correttamente stringhe SPDX valide.
    Dovrebbe rifiutare None, stringhe vuote e 'UNKNOWN'.
    """
    assert util._is_valid("MIT") is True
    assert util._is_valid("UNKNOWN") is False
    assert util._is_valid("") is False
    assert util._is_valid(None) is False


def test_extract_returns_main_expression():
    """
    Verifica che _extract_first_valid_spdx restituisca l'espressione ad alta priorità
    'detected_license_expression_spdx' se contiene un valore valido.
    """
    entry = {
        "path": "LICENSE",
        "detected_license_expression_spdx": "Apache-2.0"
    }
    assert util._extract_first_valid_spdx(entry) == ("Apache-2.0", "LICENSE")


def test_extract_falls_back_to_license_detections():
    """
    Verifica logica di fallback: se l'espressione principale è mancante/invalida,
    controllare la lista 'license_detections' per un'espressione valida.
    """
    entry = {
        "path": "src/module/file.py",
        "license_detections": [
            {"license_expression_spdx": None},          # Invalid
            {"license_expression_spdx": "GPL-3.0-only"} # Valid
        ]
    }
    assert util._extract_first_valid_spdx(entry) == ("GPL-3.0-only", "src/module/file.py")


def test_extract_uses_license_list_when_needed():
    """
    Verifica fallback profondo: se sia l'espressione rilevata che la lista detections falliscono,
    cadere indietro alla lista grezza 'licenses' (chiave standard ScanCode).
    """
    entry = {
        "path": "docs/NOTICE",
        "licenses": [
            {"spdx_license_key": None},          # Invalid
            {"spdx_license_key": "BSD-3-Clause"} # Valid
        ]
    }
    assert util._extract_first_valid_spdx(entry) == ("BSD-3-Clause", "docs/NOTICE")


def test_extract_returns_none_for_invalid_entry():
    """
    Verifica che _extract_first_valid_spdx restituisca None se la struttura della voce
    è invalida (non un dict) o contiene nessun campo di licenza riconosciuto.
    """
    assert util._extract_first_valid_spdx("not-a-dict") is None
    assert util._extract_first_valid_spdx({"path": "file"}) is None


def test_extract_returns_empty_path_when_missing():
    """
    Verifica che se la chiave 'path' è mancante nella voce, la funzione
    utilizzi come default una stringa vuota per la componente path del risultato.
    """
    entry = {
        "detected_license_expression_spdx": "CC0-1.0"
    }
    assert util._extract_first_valid_spdx(entry) == ("CC0-1.0", "")


def test_extract_prefers_detected_expression_over_other_fields():
    """
    Verifica l'ordine di priorità di estrazione:
    1. detected_license_expression_spdx
    2. license_detections
    3. licenses
    """
    entry = {
        "path": "component/LICENSE",
        "detected_license_expression_spdx": "AGPL-3.0-only", # Should be picked
        "license_detections": [{"license_expression_spdx": "MIT"}],
        "licenses": [{"spdx_license_key": "Apache-2.0"}]
    }
    assert util._extract_first_valid_spdx(entry) == ("AGPL-3.0-only", "component/LICENSE")


def test_pick_best_prefers_shallow_path():
    """
    Verifica che _pick_best_spdx prioritizzi file più vicini alla radice (profondità più bassa).
    'LICENSE' (profondità 0) dovrebbe battere 'nested/dir/COMPONENT' (profondità 2).
    """
    entries = [
        {
            "path": "nested/dir/COMPONENT",
            "license_detections": [{"license_expression_spdx": "MIT"}]
        },
        {
            "path": "LICENSE",
            "detected_license_expression_spdx": "Apache-2.0"
        }
    ]
    assert util._pick_best_spdx(entries) == ("Apache-2.0", "LICENSE")


def test_pick_best_returns_none_when_no_valid_spdx():
    """
    Verifica che _pick_best_spdx restituisca None se nessuna delle voci fornite
    contiene un'espressione SPDX valida.
    """
    entries = [
        {"path": "file1", "detected_license_expression_spdx": None},
        {"path": "dir/file2", "licenses": [{"spdx_license_key": None}]}
    ]
    assert util._pick_best_spdx(entries) is None


def test_pick_best_handles_missing_path_values():
    """
    Verifica come _pick_best_spdx gestisca voci dove 'path' è None.
    Dovrebbe gestirle con grazia senza crashare, potenzialmente trattandole come priorità alta (profondità -1 o equivalente 0).
    """
    entries = [
        {
            "path": None, # Treated as root/empty path
            "licenses": [{"spdx_license_key": "MPL-2.0"}]
        },
        {
            "path": "docs/LICENSES/license.txt",
            "detected_license_expression_spdx": "Apache-2.0"
        }
    ]
    assert util._pick_best_spdx(entries) == ("MPL-2.0", "")


def test_pick_best_keeps_order_for_same_depth():
    """
    Verifica che per voci alla stessa profondità di directory, l'ordine originale sia preservato
    (strategia di selezione stabile).
    """
    entries = [
        {"path": "A", "detected_license_expression_spdx": "EPL-2.0"},
        {"path": "B", "detected_license_expression_spdx": "LGPL-3.0"}
    ]
    assert util._pick_best_spdx(entries) == ("EPL-2.0", "A")