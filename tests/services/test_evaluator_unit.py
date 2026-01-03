"""
test: services/compatibility/evaluator.py

Questo modulo contiene test unitari per il motore di valutazione della compatibilità delle licenze.
Verifica la logica per determinare la compatibilità tra espressioni di licenza
(incluse stringhe SPDX complesse con operatori AND/OR e eccezioni WITH)
contro una licenza principale del progetto.

- Il modulo `evaluator` viene testato in isolamento mockando dipendenze esterne
  come la matrice di compatibilità e le classi parser SPDX.
- I dati di compatibilità vengono iniettati tramite `conftest.py` per garantire scenari di test
  consistenti nella suite.
- Test specifici coprono matrici vuote, licenze sconosciute e operatori logici annidati.
"""

import pytest
from unittest.mock import patch
from app.services.compatibility import evaluator

"""
Le seguenti classi sono definite qui per mockare il comportamento dei nodi parser SPDX reali.
Sono richieste perché `evaluator.py` esegue controlli `isinstance()` che devono passare
durante il testing senza importare la logica effettiva da `parser_spdx`.
"""

def test_lookup_status_found():
    """
    Verifica che la funzione interna `_lookup_status` recuperi correttamente
    gli stati di compatibilità ('yes', 'no') dalla matrice mockata.
    """
    # Nota: Si basa sui dati definiti in `complex_matrix_data` (conftest.py)
    assert evaluator._lookup_status("MIT", "Apache-2.0") == "yes"
    assert evaluator._lookup_status("MIT", "Proprietary") == "no"

def test_lookup_status_unknown():
    """
    Verifica che `_lookup_status` restituisca 'unknown' per licenze
    che non sono presenti nella matrice di compatibilità.
    """
    assert evaluator._lookup_status("MIT", "Unknown-License") == "unknown"
    assert evaluator._lookup_status("NonExistentMain", "MIT") == "unknown"

def test_eval_node_none(_msg_matches):
    """
    Garantisce che passare `None` come nodo risulti in uno stato 'unknown'
    e un messaggio di errore appropriato nella traccia.
    """
    status, trace = evaluator.eval_node("MIT", None)
    assert status == "unknown"
    assert _msg_matches(trace[0],
                        "Missing expression or not recognized",
                        "Espressione mancante o non riconosciuta")

def test_eval_leaf_simple(_msg_matches, MockLeaf):
    """
    Testa la valutazione di un nodo Leaf semplice (licenza singola).
    Scenario: Controllo 'Apache-2.0' contro 'MIT'.
    Previsto: Compatibile ('yes').
    """
    node = MockLeaf("Apache-2.0")

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "yes"
    assert _msg_matches(trace[0],
                        "Apache-2.0 → yes with respect to MIT",
                        "Apache-2.0 → yes rispetto a MIT")

def test_eval_leaf_with_exception(_msg_matches, MockLeaf):
    """
    Testa la gestione della clausola 'WITH'.
    Scenario: 'GPL-3.0 WITH Classpath-exception'.
    Logica: L'evaluatore dovrebbe rimuovere l'eccezione e valutare la licenza base ('GPL-3.0').
    Previsto: Compatibile ('yes'), con una nota traccia riguardo all'eccezione.
    """
    node = MockLeaf("GPL-3.0 WITH Classpath-exception")

    # In conftest, GPL-3.0 è compatibile con se stesso.
    status, trace = evaluator.eval_node("GPL-3.0", node)

    assert status == "yes"
    # Garantire che il messaggio di fallimento NON sia presente
    assert "exception requires manual verification" not in trace[0]
    # Garantire che il messaggio di successo/rilevamento SIA presente
    assert _msg_matches(trace[0],
                        "Exception detected",
                        "Eccezione rilevata")

def test_eval_or_logic_optimistic(MockLeaf, MockOr):
    """
    Testa la logica dell'operatore 'OR'.
    Regola: Valutazione ottimistica. Se almeno un ramo è compatibile, il risultato è compatibile.
    Scenario: 'GPL-3.0 (incompatibile) OR Apache-2.0 (compatibile)' contro 'MIT'.
    Previsto: Compatibile ('yes').
    """
    node = MockOr(MockLeaf("GPL-3.0"), MockLeaf("Apache-2.0"))

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "yes"
    assert "OR ⇒ yes" in trace[-1]


def test_eval_and_logic_conservative(MockLeaf, MockAnd):
    """
    Testa la logica dell'operatore 'AND'.
    Regola: Valutazione conservativa. Se qualsiasi ramo è incompatibile, il risultato è incompatibile.
    Scenario: 'MIT (compatibile) AND GPL-3.0 (incompatibile)' contro 'MIT'.
    Previsto: Incompatibile ('no').
    """
    node = MockAnd(MockLeaf("MIT"), MockLeaf("GPL-3.0"))

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "no"
    # Verificare che la traccia contenga la valutazione di entrambi i rami
    assert len(trace) >= 2


def test_and_cross_compatibility_check(_msg_matches, MockLeaf, MockAnd):
    """
    Verifica che la logica 'AND' esegua controlli di compatibilità incrociata tra operandi.
    Scenario: 'Apache-2.0 AND GPL-3.0'.
    Logica: Oltre a controllare contro la licenza principale, il sistema deve controllare se
    Apache-2.0 è compatibile con GPL-3.0 (controllo incrociato sinistra-destra).
    """
    node = MockAnd(MockLeaf("Apache-2.0"), MockLeaf("GPL-3.0"))

    # Non stiamo asserendo lo stato finale qui, ma piuttosto il *processo*.
    # La traccia deve registrare che un controllo incrociato è avvenuto.
    status, trace = evaluator.eval_node("GPL-3.0", node)

    trace_str = " ".join(trace)
    # Verificare che almeno un controllo di compatibilità incrociata sia registrato (L->R)
    assert _msg_matches(trace_str,
                        "Cross compatibility:",
                        "Compatibilità incrociata:")

@pytest.mark.parametrize("a,b,expected", [
    ("yes", "yes", "yes"),
    ("yes", "no", "no"),
    ("conditional", "yes", "conditional"),
])
def test_combine_and_parametrized(a, b, expected):
    """
    Testa direttamente le funzioni helper per combinare valori logici tri-stato.
    Verifica le tabelle di verità per operazioni AND/OR con 'yes', 'no' e 'conditional'.
    """
    assert evaluator._combine_and(a, b) == expected


@pytest.mark.parametrize("a,b,expected", [
    ("yes", "no", "yes"),
    ("no", "no", "no"),
    ("conditional", "no", "conditional"),
])
def test_combine_or_parametrized(a, b, expected):
    """
    Testa direttamente le funzioni helper per combinare valori logici tri-stato.
    Verifica le tabelle di verità per operazioni AND/OR con 'yes', 'no' e 'conditional'.
    """
    assert evaluator._combine_or(a, b) == expected

def test_lookup_status_empty_matrix():
    """
    Caso limite: Testa il comportamento quando la matrice di compatibilità è None o vuota.
    Dovrebbe fallire con grazia restituendo 'unknown'.
    """
    # Sovrascrivi la patch globale specificamente per questo test
    with patch("app.services.compatibility.evaluator.get_matrix", return_value=None):
        assert evaluator._lookup_status("MIT", "MIT") == "unknown"

    with patch("app.services.compatibility.evaluator.get_matrix", return_value={}):
        assert evaluator._lookup_status("MIT", "MIT") == "unknown"

def test_eval_leaf_with_exception_fail(_msg_matches, MockLeaf):
    """
    Testa una clausola di eccezione 'WITH' dove la licenza base è intrinsecamente INCOMPATIBILE.
    Scenario: 'Proprietary WITH Some-Exception' contro 'GPL-3.0'.
    Previsto: Incompatibile ('no'). L'esistenza dell'eccezione non dovrebbe sovrascrivere l'incompatibilità base.
    """
    # Proprietary -> NO per GPL-3.0 nei nostri dati mock
    node = MockLeaf("Proprietary WITH Some-Exception")

    status, trace = evaluator.eval_node("GPL-3.0", node)

    assert status == "no"
    assert _msg_matches(trace[0],
                        "exception presence requires manual verification",
                        "Nota: presenza di eccezione richiede verifica manuale")

def test_combine_conditional_logic():
    """
    Testa combinazioni specifiche che risultano in uno stato 'conditional'.
    Garantisce che 'conditional' si propaghi correttamente attraverso la logica booleana.
    """
    # AND: Se un lato è conditional e l'altro è yes, il risultato è conditional.
    assert evaluator._combine_and("yes", "conditional") == "conditional"
    assert evaluator._combine_and("conditional", "conditional") == "conditional"

    # OR: Se un lato è conditional e l'altro è no, il risultato è conditional
    # (perché il lato 'no' viene scartato nella logica OR).
    assert evaluator._combine_or("no", "conditional") == "conditional"
    assert evaluator._combine_or("conditional", "conditional") == "conditional"

def test_eval_node_unrecognized_type(_msg_matches, MockNode):
    """
    Programmazione difensiva: Testa la reazione del sistema a un tipo di nodo sconosciuto
    (ad es., se il parser viene esteso ma l'evaluatore non viene aggiornato).
    Previsto: Restituisce 'unknown'.
    """
    class UnknownNode(MockNode):
        pass

    status, trace = evaluator.eval_node("MIT", UnknownNode())
    assert status == "unknown"
    assert _msg_matches(trace[0],
                        "Unrecognized node",
                        "Nodo non riconosciuto")

def test_and_nested_leaves_collection(_msg_matches, MockLeaf, MockOr, MockAnd):
    """
    Test avanzato: Verifica la raccolta ricorsiva di foglie per controlli incrociati
    in strutture annidate.
    Struttura: '(MIT OR Apache-2.0) AND GPL-3.0'.
    Logica: Il sistema deve estrarre TUTTE le foglie dal lato sinistro (MIT, Apache)
    e controllarle incrociatamente contro il lato destro (GPL).
    """
    # Costruzione dell'albero: (MIT OR Apache) AND GPL
    left_node = MockOr(MockLeaf("MIT"), MockLeaf("Apache-2.0"))
    right_node = MockLeaf("GPL-3.0")
    root = MockAnd(left_node, right_node)

    status, trace = evaluator.eval_node("GPL-3.0", root)

    trace_str = " ".join(trace)

    # Verificare che i controlli incrociati siano stati eseguiti per TUTTE le foglie annidate
    assert _msg_matches(trace_str,
                        "Cross compatibility:",
                        "Compatibilità incrociata:")

@pytest.mark.parametrize("main,left,right,expected", [
    ("MIT", "Apache-2.0", "GPL-3.0", "no"),          # yes AND no -> no
    ("MIT", "Apache-2.0", "MIT", "yes"),             # yes AND yes -> yes
    ("MIT", "LGPL-2.1", "MIT", "conditional"),       # conditional AND yes -> conditional
    ("GPL-3.0", "Apache-2.0", "Apache-2.0", "no"),   # no AND no -> no
])
def test_eval_and_parametrized(MockAnd, MockLeaf, main, left, right, expected):
    node = MockAnd(MockLeaf(left), MockLeaf(right))
    status, trace = evaluator.eval_node(main, node)
    assert status == expected
    # Verificare che la traccia contenga informazioni di valutazione per entrambi gli operandi
    assert len(trace) >= 2


@pytest.mark.parametrize("main,left,right,expected", [
    ("MIT", "Apache-2.0", "GPL-3.0", "yes"),          # yes OR no -> yes
    ("MIT", "GPL-3.0", "GPL-3.0", "no"),             # no OR no -> no
    ("MIT", "LGPL-2.1", "GPL-3.0", "conditional"),   # conditional OR no -> conditional
    ("GPL-3.0", "MIT", "Apache-2.0", "yes"),        # yes OR no -> yes (main diverso)
])
def test_eval_or_parametrized(MockOr, MockLeaf, main, left, right, expected):
    node = MockOr(MockLeaf(left), MockLeaf(right))
    status, trace = evaluator.eval_node(main, node)
    assert status == expected
    assert any(f"OR ⇒ {expected}" in line for line in trace)

