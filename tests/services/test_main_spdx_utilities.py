# tests/services/scanner/test_main_spdx_utilities.py
import pytest

from app.services.scanner import main_spdx_utilities as util


def test_is_valid_filters_none_empty_unknown():
    assert util._is_valid("MIT") is True
    assert util._is_valid("UNKNOWN") is False
    assert util._is_valid("") is False
    assert util._is_valid(None) is False


def test_extract_returns_main_expression():
    entry = {
        "path": "LICENSE",
        "detected_license_expression_spdx": "Apache-2.0"
    }
    assert util._extract_first_valid_spdx(entry) == ("Apache-2.0", "LICENSE")


def test_extract_falls_back_to_license_detections():
    entry = {
        "path": "src/module/file.py",
        "license_detections": [
            {"license_expression_spdx": None},
            {"license_expression_spdx": "GPL-3.0-only"}
        ]
    }
    assert util._extract_first_valid_spdx(entry) == ("GPL-3.0-only", "src/module/file.py")


def test_extract_uses_license_list_when_needed():
    entry = {
        "path": "docs/NOTICE",
        "licenses": [
            {"spdx_license_key": None},
            {"spdx_license_key": "BSD-3-Clause"}
        ]
    }
    assert util._extract_first_valid_spdx(entry) == ("BSD-3-Clause", "docs/NOTICE")


def test_extract_returns_none_for_invalid_entry():
    assert util._extract_first_valid_spdx("not-a-dict") is None
    assert util._extract_first_valid_spdx({"path": "file"}) is None

def test_extract_returns_empty_path_when_missing():
    entry = {
        "detected_license_expression_spdx": "CC0-1.0"
    }
    assert util._extract_first_valid_spdx(entry) == ("CC0-1.0", "")

def test_extract_prefers_detected_expression_over_other_fields():
    entry = {
        "path": "component/LICENSE",
        "detected_license_expression_spdx": "AGPL-3.0-only",
        "license_detections": [{"license_expression_spdx": "MIT"}],
        "licenses": [{"spdx_license_key": "Apache-2.0"}]
    }
    assert util._extract_first_valid_spdx(entry) == ("AGPL-3.0-only", "component/LICENSE")



def test_pick_best_prefers_shallow_path():
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
    entries = [
        {"path": "file1", "detected_license_expression_spdx": None},
        {"path": "dir/file2", "licenses": [{"spdx_license_key": None}]}
    ]
    assert util._pick_best_spdx(entries) is None


def test_pick_best_handles_missing_path_values():
    entries = [
        {
            "path": None,
            "licenses": [{"spdx_license_key": "MPL-2.0"}]
        },
        {
            "path": "docs/LICENSES/license.txt",
            "detected_license_expression_spdx": "Apache-2.0"
        }
    ]
    assert util._pick_best_spdx(entries) == ("MPL-2.0", "")


def test_pick_best_keeps_order_for_same_depth():
    entries = [
        {"path": "A", "detected_license_expression_spdx": "EPL-2.0"},
        {"path": "B", "detected_license_expression_spdx": "LGPL-3.0"}
    ]
    assert util._pick_best_spdx(entries) == ("EPL-2.0", "A")