"""
test: services/compatibility/checker.py
checker.py - Unit tests per la funzione `check_compatibility` nel modulo
`app.services.compatibility.checker`.
"""

from unittest.mock import MagicMock
from app.services.compatibility.checker import check_compatibility

"""
    Se la licenza principale normalizzata risulta vuota, la funzione deve
    indicare che la licenza principale non è stata rilevata e produrre un
    issue per ogni file analizzato (compatibile=False).

    Usa `monkeypatch` per forzare `normalize_symbol` a ritornare stringa vuota.
    """
def test_main_license_invalid_returns_issues(monkeypatch, _msg_matches):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "")
    res = check_compatibility("", {"a.py": "MIT"})
    assert res["main_license"] == "UNKNOWN"
    assert len(res["issues"]) == 1
    issue = res["issues"][0]
    assert issue["file_path"] == "a.py"
    assert issue["compatible"] is False
    assert _msg_matches(issue["reason"],
                        "Main license not found or invalid",
                        "Licenza principale non rilevata")

"""
    Quando la matrice non è disponibile, la funzione deve segnalare la
    mancanza della matrice professionale e restituire un issue descrittivo.

    Mocka `get_matrix` per ritornare None.
"""
def test_matrix_missing_or_license_not_in_matrix(monkeypatch, _msg_matches):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: None)
    res = check_compatibility("MIT", {"b.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1
    assert _msg_matches(res["issues"][0]["reason"],
                        "Matrix not available",
                        "Matrice professionale non disponibile")

"""
    Se `eval_node` ritorna ('yes', trace), l'issue generato deve essere
    marcato come compatibile e contenere la traccia nella reason.

    Usa la fixture `complex_matrix_data` come matrice e monkeypatch per isolare
    le chiamate interne.
"""
def test_eval_yes_marks_compatible_and_includes_trace(complex_matrix_data, monkeypatch):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("yes", ["direct match"]))
    res = check_compatibility("MIT", {"src/file.py": "MIT"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1
    issue = res["issues"][0]
    assert issue["file_path"] == "src/file.py"
    assert issue["compatible"] is True
    assert "direct match" in issue["reason"]

"""
    Se `eval_node` ritorna ('no', trace), l'issue deve essere marcato come
    non compatibile e includere la traccia nella reason.
"""
def test_eval_no_marks_incompatible_and_includes_trace(complex_matrix_data, monkeypatch):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "GPL-3.0")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("no", ["conflict detected"]))
    res = check_compatibility("GPL-3.0", {"lib/x.py": "Apache-2.0"})
    issue = res["issues"][0]
    assert issue["compatible"] is False
    assert "conflict detected" in issue["reason"]

"""
    Se `eval_node` ritorna ('conditional', trace), il reason deve contenere
    l'esito e la traccia; l'issue deve essere marcato non compatibile.
"""
def test_eval_conditional_returns_hint_in_reason_and_not_compatible(complex_matrix_data, monkeypatch):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    mock_parse = MagicMock(return_value="NODE")
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", mock_parse)
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("conditional", ["some clause"]))

    res = check_compatibility("MIT", {"folder/thing.py": "  LGPL-2.1  "})
    mock_parse.assert_called_with("LGPL-2.1")
    issue = res["issues"][0]
    assert issue["compatible"] is False
    assert "Esito: conditional" in issue["reason"]
    assert "some clause" in issue["reason"]

"""
    Verifica che, quando `eval_node` ritorna 'yes' per tutti i file,
    gli issue prodotti esistano ma siano tutti marcati come compatibili.

    Nota: la funzione corrente registra un entry per ogni file anche quando
    compatibile; il test verifica questo comportamento e l'indicazione di
    compatibilità.
"""
def test_all_files_compatible_returns_no_issues(complex_matrix_data, monkeypatch):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: s.strip())
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("yes", ["direct match"]))

    res = check_compatibility("MIT", {"file1.py": "MIT", "file2.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert isinstance(res["issues"], list)
    assert len(res["issues"]) == 2
    assert all(issue["compatible"] is True for issue in res["issues"])

"""
    Quando la matrice è presente ma non contiene la main license, la
    funzione deve comunque restituire un issue che segnala l'anomalia.
"""
def test_matrix_present_but_main_not_in_matrix(monkeypatch, _msg_matches):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: {"GPL-3.0": {"MIT": "no"}})
    res = check_compatibility("MIT", {"file.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1

    reason = res["issues"][0]["reason"].lower()
    assert _msg_matches(reason,
                        "main license not in",
                        "licenza principale non presente") or _msg_matches(reason,
                                                                       "matrix not available",
                                                                       "matrice professionale non disponibile")

"""
    Se `eval_node` restituisce uno status non previsto (es. 'weird'),
    la funzione deve marcare l'issue non compatibile e includere l'etichetta
    dello status nel reason.
"""
def test_eval_unknown_status_shows_unknown_hint(complex_matrix_data, monkeypatch):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("weird", ["trace info"]))
    res = check_compatibility("MIT", {"x.py": "Zlib"})
    issue = res["issues"][0]
    assert issue["compatible"] is False
    assert "Esito: unknown" in issue["reason"]

"""
    Quando la licenza rilevata è None, la funzione deve chiamare `parse_spdx`
    con stringa vuota e propagare il risultato (qui mockato) nell'issue.
"""
def test_empty_detected_license_calls_parse_with_empty(monkeypatch, complex_matrix_data):
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    mock_parse = MagicMock(return_value="NODE")
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", mock_parse)
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("no", ["no trace"]))
    res = check_compatibility("MIT", {"empty.py": None})
    mock_parse.assert_called_with("")
    issue = res["issues"][0]
    assert issue["detected_license"] == ""
    assert "no trace" in issue["reason"]

"""
    Valori speciali o non informativi della main license (UNKNOWN, NOASSERTION,
    NONE) devono essere trattati come mancanza di licenza principale.
"""
def test_main_license_special_values_treated_as_invalid(monkeypatch, _msg_matches):
    for val in ("UNKNOWN", "NOASSERTION", "NONE"):
        monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s, v=val: v)
        res = check_compatibility(val, {"a.py": "MIT"})
        assert res["main_license"] == val or res["main_license"] == val
        assert len(res["issues"]) == 1
        assert _msg_matches(res["issues"][0]["reason"],
                            "Main license not found or invalid",
                            "Licenza principale non rilevata") or ("non valida" in res["issues"][0]["reason"].lower())