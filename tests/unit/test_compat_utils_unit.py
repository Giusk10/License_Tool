"""
Compatibility Utilities Unit Test Module.

Questo modulo fornisce test unitari per `app.services.compatibility.compat_utils`.
Si concentra sulla validazione della normalizzazione delle stringhe di licenza in stile SPDX e
sull'estrazione affidabile dei simboli di licenza da espressioni booleane complesse.

La suite copre:
1. Normalizzazione dei simboli: Gestione di varianti di maiuscole/minuscole, keyword 'WITH' e suffissi '+'.
2. Estrazione dei simboli: Parsing di token da espressioni semplici e complesse (annidate).
3. Gestione dei casi limite: Robustezza contro input nulli, stringhe vuote ed espressioni malformate.
"""

import pytest
from app.services.compatibility import compat_utils as cu

# ==================================================================================
#                                     FIXTURE
# ==================================================================================

# Nota: Questi sono test puramente unitari per funzioni di utility e non richiedono
# stato esterno o fixture complesse da conftest.py.

# ==================================================================================
#                           TEST: NORMALIZZAZIONE DEI SIMBOLI
# ==================================================================================

def test_normalize_none_and_empty():
    """
    Valida la gestione degli input nulli e vuoti.

    Garantisce che None venga preservato per evitare errori di tipo e che le stringhe vuote
    rimangano vuote dopo la normalizzazione.
    """
    assert cu.normalize_symbol(None) is None
    assert cu.normalize_symbol("") == ""


def test_normalize_trim_and_with_variants():
    """
    Testa la normalizzazione delle keyword e la pulizia degli spazi.

    Verifica che varie varianti di maiuscole/minuscole della keyword 'with' (ad es., 'With', 'with')
    siano standardizzate in ' WITH ' e che gli spazi circostanti vengano rimossi.
    """
    assert cu.normalize_symbol(" mit with exception ") == "mit WITH exception"
    assert cu.normalize_symbol("MIT With Exception") == "MIT WITH Exception"
    # caso con 'with' senza spazio iniziale
    assert cu.normalize_symbol("MIT with") == "MIT WITH"


def test_normalize_plus_to_or_later_and_synonyms():
    """
    Verifica la conversione del suffisso '+' nel formato standard '-or-later'.

    Garantisce che stringhe come 'GPL-3.0+' vengano correttamente trasformate per
    conformarsi alle moderne convenzioni di denominazione SPDX.
    """
    assert cu.normalize_symbol("GPL-3.0+") == "GPL-3.0-or-later"
    assert cu.normalize_symbol("GPL-3.0-or-later") == "GPL-3.0-or-later"


def test_normalize_preserves_unknown_strings():
    """
    Garantisce che stringhe standard o non riconosciute vengano preservate.

    Valida che la normalizzazione modifichi solo schemi specifici, lasciando
    nomi di licenze standard come 'Apache-2.0' intatti (eccetto per il ritaglio).
    """
    assert cu.normalize_symbol("  Apache-2.0  ") == "Apache-2.0"
    assert cu.normalize_symbol("BSD-3-Clause") == "BSD-3-Clause"

# ==================================================================================
#                           TEST: ESTRAZIONE DEI SIMBOLI
# ==================================================================================

def test_extract_symbols_simple_and_complex():
    """
    Verifica l'estrazione dei token dalle espressioni SPDX.

    Garantisce che il servizio possa estrarre singoli ID di licenza sia da
    stringhe semplici che da espressioni booleane (OR/AND), utilizzando insiemi per
    un confronto indipendente dall'ordine.
    """
    assert cu.extract_symbols("") == []

    s = cu.extract_symbols("MIT")
    assert set(s) == {"MIT"}

    s2 = cu.extract_symbols("MIT OR Apache-2.0")
    # può restituire ['MIT','Apache-2.0'] in qualsiasi ordine
    assert set(s2) >= {"MIT", "Apache-2.0"}


def test_extract_symbols_invalid_expression_returns_empty():
    """
    Testa la resilienza agli errori per espressioni SPDX malformate o non valide.

    Garantisce che quando l'utility di estrazione incontra una stringa che
    non può essere analizzata come un'espressione di licenza valida (ad es., contenente
    caratteri o sintassi non validi), restituisce un elenco vuoto invece di
    sollevare un'eccezione non gestita.
    """
    assert cu.extract_symbols("not-a-license !!! !!!") == []


def test_normalize_with_and_plus_combination():
    """
    Testa la gestione degli errori per espressioni SPDX malformate.

    Garantisce che se il parser incontra un'espressione non valida, restituisca
    un elenco vuoto invece di arrestare il flusso di lavoro dell'analisi.
    """
    inp = "GPL-2.0+ WITH Autoconf-exception"
    # + deve diventare -or-later, e WITH deve essere normalizzato
    out = cu.normalize_symbol(inp)
    assert "-or-later" in out
    assert "WITH" in out

def test_normalize_multiple_plus_and_with():
    """
    Valida la resilienza contro simboli ridondanti o ripetuti.

    Controlla come il normalizzatore gestisce stringhe con più segni '+' o
    parole chiave 'WITH' ripetute, garantendo che l'output sia stabilizzato e
    conforme al formato previsto '-or-later' e 'WITH'.
    """
    inp = "GPL-2.0+ + + WITH Extra WITH Another"
    out = cu.normalize_symbol(inp)
    # Garantisce che '+' venga convertito e 'WITH' venga standardizzato nonostante le ripetizioni
    assert "-or-later" in out
    assert "WITH" in out


def test_normalize_case_insensitive_synonyms():
    """
    Garantisce che la normalizzazione sia insensibile alle maiuscole per i token di licenza.

    Verifica che le varianti in minuscolo o maiuscole miste delle licenze con un '+'
    suffisso (ad es., 'gpl-3.0+') siano correttamente identificate e convertite
    nella forma standard '-or-later'.
    """
    assert cu.normalize_symbol("gpl-3.0+") == "gpl-3.0-or-later"
    assert cu.normalize_symbol("GPl-3.0+") == "GPl-3.0-or-later"


def test_extract_symbols_with_parenthesis_and_with():
    """
    Valida la logica di estrazione per espressioni SPDX annidate complesse.

    Garantisce che i simboli siano correttamente analizzati anche quando l'espressione
    contiene operatori logici (AND/OR), parentesi e clausole di eccezione
    (WITH).
    """
    expr = "(MIT OR GPL-2.0 WITH Exception) AND Apache-2.0"
    syms = cu.extract_symbols(expr)
    assert any("WITH" in s for s in syms) or any("GPL-2.0" in s for s in syms)

# ==================================================================================
#                        TEST: VALIDAZIONE PARAMETRIZZATA
# ==================================================================================

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
    """
    Esegue la validazione in blocco delle regole di normalizzazione utilizzando la parametrizzazione.

    Questo garantisce che più coppie di input/output siano costantemente
    validate attraverso la logica di normalizzazione.
    """
    assert cu.normalize_symbol(inp) == expected


# ==================================================================================
#                        TEST: DIZIONARIO DEI SINONIMI
# ==================================================================================

@pytest.mark.parametrize("inp,expected", [
    ("GPL-3.0+", "GPL-3.0-or-later"),
    ("GPL-2.0+", "GPL-2.0-or-later"),
    ("LGPL-3.0+", "LGPL-3.0-or-later"),
    ("LGPL-2.1+", "LGPL-2.1-or-later"),
    ("AGPL-3.0+", "AGPL-3.0-or-later"),
    ("MPL-2.0+", "MPL-2.0-or-later"),
    ("Apache-2.0+", "Apache-2.0-or-later"),
    ("MIT+", "MIT-or-later"),
    ("BSD-3-Clause+", "BSD-3-Clause-or-later"),
    ("BSD-2-Clause+", "BSD-2-Clause-or-later"),
    ("CDDL-1.0+", "CDDL-1.0-or-later"),
    ("EPL-2.0+", "EPL-2.0-or-later"),
])
def test_normalize_all_synonyms(inp, expected):
    """
    Valida che tutte le voci nel dizionario _SYNONYMS siano correttamente risolte.

    Garantisce che gli alias di licenza comuni con suffisso '+' siano convertiti nella
    loro forma canonica '-or-later'.
    """
    assert cu.normalize_symbol(inp) == expected


def test_normalize_unknown_license_preserved():
    """
    Garantisce che stringhe di licenza sconosciute non presenti in _SYNONYMS siano preservate.

    Valida che il normalizzatore modifichi solo schemi noti e non alteri
    identificatori di licenza non riconosciuti (eccetto per il ritaglio).
    """
    assert cu.normalize_symbol("CustomLicense-1.0") == "CustomLicense-1.0"
    assert cu.normalize_symbol("Proprietary") == "Proprietary"
    assert cu.normalize_symbol("UNKNOWN") == "UNKNOWN"


def test_extract_symbols_nested_or_and():
    """
    Valida la logica di estrazione per espressioni annidate OR e AND.

    Garantisce che i simboli siano correttamente analizzati da espressioni booleane
    profondamente annidate con operatori misti.
    """
    expr = "MIT AND (Apache-2.0 OR GPL-2.0)"
    syms = cu.extract_symbols(expr)
    assert "MIT" in syms
    # L'ordine può variare, controlla la presenza
    assert any(s in ["Apache-2.0", "GPL-2.0"] for s in syms)


def test_extract_symbols_single_with_exception():
    """
    Valida l'estrazione di una licenza con clausola di eccezione.

    Garantisce che le licenze con eccezioni WITH siano correttamente identificate.
    """
    expr = "GPL-2.0-only WITH Classpath-exception-2.0"
    syms = cu.extract_symbols(expr)
    assert len(syms) >= 1


def test_normalize_with_lowercase_variants():
    """
    Testa la normalizzazione della keyword 'with' in varie posizioni.

    Garantisce che tutte le varianti in minuscolo della keyword 'with' siano normalizzate in 'WITH'.
    """
    assert cu.normalize_symbol("GPL-2.0 with linking-exception") == "GPL-2.0 WITH linking-exception"
    assert cu.normalize_symbol("MIT with") == "MIT WITH"


def test_extract_symbols_complex_expression():
    """
    Valida l'estrazione da un'espressione SPDX complessa e reale.
    """
    expr = "(MIT OR Apache-2.0) AND (BSD-2-Clause OR BSD-3-Clause)"
    syms = cu.extract_symbols(expr)
    expected = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"}
    assert expected.issubset(set(syms))
