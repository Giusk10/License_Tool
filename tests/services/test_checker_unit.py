"""
Modulo di test unitario del controllo compatibilità licenze.

Questo modulo fornisce test unitari per la funzione `check_compatibility` situata in
`app.services.compatibility.checker`. Valida la logica utilizzata per confrontare
una licenza principale del progetto con le licenze individuali dei file utilizzando una matrice
di compatibilità professionale e l'analisi delle espressioni SPDX.

La suite copre:
1. Validazione licenza principale: Gestione di valori SPDX mancanti, invalidi o speciali.
2. Disponibilità matrice: Comportamento quando la matrice di compatibilità è mancante o incompleta.
3. Risultati valutazione: Elaborazione corretta degli stati 'yes', 'no', 'conditional' e 'unknown'.
4. Integrazione SPDX: Verifica delle chiamate di analisi ricorsive per espressioni complesse.
5. Elaborazione bulk: Garantire che tutti i file in un repository siano elaborati e riportati correttamente.
"""

from unittest.mock import MagicMock
from app.services.compatibility.checker import check_compatibility

# ==================================================================================
#                                     FIXTURE
# ==================================================================================

# Nota: Questo modulo si basa su fixture globali definite in conftest.py:
# - complex_matrix_data: Fornisce un mock standardizzato della matrice di compatibilità.
# - _msg_matches: Helper per asserzione bilingue (IT/EN) dei messaggi di errore.

# ==================================================================================
#                           TEST: VALIDAZIONE & INIZIALIZZAZIONE
# ==================================================================================


def test_main_license_invalid_returns_issues(monkeypatch, _msg_matches):
    """
    Verifica il comportamento quando la licenza principale è mancante o fallisce la normalizzazione.

    Garantisce che se non viene rilevata alcuna licenza principale valida, il sistema segnali tutti
    i file con uno stato che indica che la licenza principale è invalida, piuttosto che
    tentare un controllo di compatibilità.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "")
    res = check_compatibility("", {"a.py": "MIT"})
    assert res["main_license"] == "UNKNOWN"
    assert len(res["issues"]) == 1
    issue = res["issues"][0]
    assert issue["file_path"] == "a.py"
    assert issue["compatible"] is None
    assert _msg_matches(issue["reason"],
                        "Main license not detected or invalid",
                        "Licenza principale non rilevata")


def test_matrix_missing_or_license_not_in_matrix(monkeypatch, _msg_matches):
    """
    Testa il comportamento quando la matrice di compatibilità professionale non è disponibile.

    Garantisce che se 'get_matrix' restituisce None, il sistema riporti un errore specifico
    che indica che la matrice è mancante piuttosto che fallire silenziosamente.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: None)
    res = check_compatibility("MIT", {"b.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert len(res["issues"]) == 1
    assert _msg_matches(res["issues"][0]["reason"],
                        "Professional matrix not available",
                        "Matrice professionale non disponibile")


def test_eval_yes_marks_compatible_and_includes_trace(complex_matrix_data, monkeypatch):
    """
    Valida un risultato positivo 'yes' (Compatibile).

    Verifica che quando l'evaluatore conferma la compatibilità, il problema sia
    marcato come True e la traccia specifica (ad es., 'direct match') sia inclusa.
    """
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


def test_eval_no_marks_incompatible_and_includes_trace(complex_matrix_data, monkeypatch):
    """
    Valida un risultato 'no' (Incompatibile).

    Garantisce che i conflitti di licenza siano correttamente identificati, marcando il
    problema come incompatibile e fornendo la traccia del conflitto nella ragione.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "GPL-3.0")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("no", ["conflict detected"]))
    res = check_compatibility("GPL-3.0", {"lib/x.py": "Apache-2.0"})
    assert res["main_license"] == "GPL-3.0"
    assert len(res["issues"]) == 1
    issue = res["issues"][0]
    assert issue["file_path"] == "lib/x.py"
    assert issue["compatible"] is False
    assert "conflict detected" in issue["reason"]


def test_eval_conditional_returns_hint_in_reason_and_not_compatible(complex_matrix_data, monkeypatch):
    """
    Verifica l'elaborazione della compatibilità 'conditional'.

    Garantisce che i risultati condizionali siano trattati come indeterminati (None)
    per sicurezza, fornendo all'utente le clausole/hint necessarie.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    mock_parse = MagicMock(return_value="NODE")
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", mock_parse)
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("conditional", ["some clause"]))

    res = check_compatibility("MIT", {"folder/thing.py": "  LGPL-2.1  "})
    mock_parse.assert_called_with("LGPL-2.1")
    issue = res["issues"][0]
    # conditional and unknown statuses now return compatible=None (indeterminate)
    assert issue["compatible"] is None
    assert "Outcome: conditional" in issue["reason"]

# ==================================================================================
#                              TEST: CASI LIMITE DATI
# ==================================================================================


def test_all_files_compatible_returns_no_issues(complex_matrix_data, monkeypatch):
    """
    Garantisce la corretta segnalazione quando tutti i file sono compatibili.

    Verifica che il servizio restituisca ancora voci per tutti i file analizzati,
    marcandoli correttamente come compatibili senza sollevare falsi allarmi.
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: s.strip())
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("yes", ["direct match"]))

    res = check_compatibility("MIT", {"file1.py": "MIT", "file2.py": "Apache-2.0"})
    assert res["main_license"] == "MIT"
    assert isinstance(res["issues"], list)
    assert len(res["issues"]) == 2
    assert all(issue["compatible"] is True for issue in res["issues"])


def test_matrix_present_but_main_not_in_matrix(monkeypatch, _msg_matches):
    """
    Gestisce i casi in cui la licenza principale non è definita nella matrice professionale.

    Verifica che se la licenza primaria del progetto è mancante dai
    dati di compatibilità, il checker generi un problema che avverte l'utente
    che la combinazione di licenze specifica non può essere validata professionalmente.
    """
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


def test_eval_unknown_status_shows_unknown_hint(complex_matrix_data, monkeypatch):
    """
    Valida il fallback per stati di valutazione imprevisti.

    Garantisce che se l'evaluatore del nodo restituisce un codice di stato non riconosciuto,
    il servizio utilizzi come default la marcatura del file come indeterminato (None).
    """
    monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s: "MIT")
    monkeypatch.setattr("app.services.compatibility.checker.get_matrix", lambda: complex_matrix_data)
    monkeypatch.setattr("app.services.compatibility.checker.parse_spdx", lambda s: "NODE")
    monkeypatch.setattr("app.services.compatibility.checker.eval_node", lambda *_: ("weird", ["trace info"]))
    res = check_compatibility("MIT", {"x.py": "Zlib"})
    issue = res["issues"][0]
    # Unknown statuses now return compatible=None (indeterminate)
    assert issue["compatible"] is None
    assert "Outcome: unknown" in issue["reason"]


def test_empty_detected_license_calls_parse_with_empty(monkeypatch, complex_matrix_data):
    """
    Testa la gestione di licenze rilevate 'None' o vuote.

    Garantisce che se lo scanner fallisce nel rilevare una licenza (restituendo None),
    il checker passi una stringa vuota al parser SPDX per evitare crash.
    """
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


def test_main_license_special_values_treated_as_invalid(monkeypatch, _msg_matches):
    """
    Gestisce le parole chiave speciali SPDX (UNKNOWN, NOASSERTION, NONE).

    Garantisce che valori di licenza primaria non descrittivi attivino un
    errore di invalidazione, poiché la compatibilità non può essere determinata rispetto a essi.
    """
    for val in ("UNKNOWN", "NOASSERTION", "NONE"):
        monkeypatch.setattr("app.services.compatibility.checker.normalize_symbol", lambda s, v=val: v)
        res = check_compatibility(val, {"a.py": "MIT"})
        assert res["main_license"] == val or res["main_license"] == val
        assert len(res["issues"]) == 1
        assert _msg_matches(res["issues"][0]["reason"],
                            "Main license not detected or invalid",
                            "Licenza principale non rilevata") or ("invalid" in res["issues"][0]["reason"].lower())
