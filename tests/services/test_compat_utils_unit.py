"""
test: services/compatibility/compat_utils.py
Unit tests per `app.services.compatibility.compat_utils`.
Verificano il comportamento di `normalize_symbol` e `extract_symbols` su casi normali e edge-case.
"""

import pytest
from app.services.compatibility import compat_utils as cu


def test_normalize_none_and_empty():
    """None deve essere restituito così com'è; stringa vuota rimane vuota."""
    assert cu.normalize_symbol(None) is None
    assert cu.normalize_symbol("") == ""


def test_normalize_trim_and_with_variants():
    """Diverse varianti di 'with' e spazi devono essere normalizzate in ' WITH '."""
    assert cu.normalize_symbol(" mit with exception ") == "mit WITH exception"
    assert cu.normalize_symbol("MIT With Exception") == "MIT WITH Exception"
    # caso con ' with' senza spazio iniziale
    assert cu.normalize_symbol("MIT with") == "MIT WITH"


def test_normalize_plus_to_or_later_and_synonyms():
    """Il + deve essere convertito in -or-later e le forme già -or-later rimangono."""
    assert cu.normalize_symbol("GPL-3.0+") == "GPL-3.0-or-later"
    assert cu.normalize_symbol("GPL-3.0-or-later") == "GPL-3.0-or-later"


def test_normalize_preserves_unknown_strings():
    """Stringhe che non richiedono trasformazioni devono essere restituite inalterate (salvo strip)."""
    assert cu.normalize_symbol("  Apache-2.0  ") == "Apache-2.0"
    assert cu.normalize_symbol("BSD-3-Clause") == "BSD-3-Clause"


def test_extract_symbols_simple_and_complex():
    """Estrazione di simboli da espressioni semplici e composte.
    L'ordine dei simboli non è garantito, quindi usiamo insiemi per la verifica.
    """
    assert cu.extract_symbols("") == []

    s = cu.extract_symbols("MIT")
    assert set(s) == {"MIT"}

    s2 = cu.extract_symbols("MIT OR Apache-2.0")
    # può restituire ['MIT','Apache-2.0'] in qualsiasi ordine
    assert set(s2) >= {"MIT", "Apache-2.0"}


def test_extract_symbols_invalid_expression_returns_empty():
    """Espressioni non valide o che generano eccezione devono ritornare lista vuota."""
    assert cu.extract_symbols("not-a-license !!! !!!") == []


def test_normalize_with_and_plus_combination():
    """Combinazioni di with e + devono essere gestite correttamente."""
    inp = "GPL-2.0+ WITH Autoconf-exception"
    # + deve diventare -or-later, e WITH deve essere normalizzato
    out = cu.normalize_symbol(inp)
    assert "-or-later" in out
    assert "WITH" in out

def test_normalize_multiple_plus_and_with():
    """Gestisce più segni + e più occorrenze di WITH. """
    inp = "GPL-2.0+ + + WITH Extra WITH Another"
    out = cu.normalize_symbol(inp)
    # aspettiamo che + diventino -or-later almeno sulla prima occorrenza
    assert "-or-later" in out
    assert "WITH" in out


def test_normalize_case_insensitive_synonyms():
    """Verifica che le sostituzioni siano case-insensitive per token noti."""
    assert cu.normalize_symbol("gpl-3.0+") == "gpl-3.0-or-later"
    assert cu.normalize_symbol("GPl-3.0+") == "GPl-3.0-or-later"


def test_extract_symbols_with_parenthesis_and_with():
    """Assicura che extract_symbols estragga anche token WITH e quelli tra parentesi."""
    expr = "(MIT OR GPL-2.0 WITH Exception) AND Apache-2.0"
    syms = cu.extract_symbols(expr)
    assert any("WITH" in s for s in syms) or any("GPL-2.0" in s for s in syms)

@pytest.mark.parametrize("inp,expected", [
    (None, None),
    ("", ""),
    (" mit with exception ", "mit WITH exception"),
    ("MIT With Exception", "MIT WITH Exception"),
    ("GPL-3.0+", "GPL-3.0-or-later"),
    ("gpl-3.0+", "gpl-3.0-or-later"),
    ("GPL-3.0-or-later", "GPL-3.0-or-later"),
])
def test_normalize_parametrized(inp, expected):
    assert cu.normalize_symbol(inp) == expected
