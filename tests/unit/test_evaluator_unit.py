"""
test: services/compatibility/evaluator.py

Questo modulo contiene test unitari per il motore di valutazione della compatibilità delle licenze.
Verifica la logica per determinare la compatibilità tra espressioni di licenza
(inclusi stringhe SPDX complesse con operatori AND/OR e eccezioni WITH)
rispetto alla licenza principale di un progetto.

- Il modulo `evaluator` viene testato in isolamento tramite il mocking delle dipendenze esterne
  come la matrice di compatibilità e le classi del parser SPDX.
- I dati di compatibilità sono iniettati tramite `conftest.py` per garantire scenari di test
  consistenti in tutta la suite.
- Test specifici coprono matrici vuote, licenze sconosciute e operatori logici annidati.
"""

import pytest
from unittest.mock import patch
from app.services.compatibility import evaluator

"""
Le seguenti classi sono definite qui per simulare il comportamento dei veri nodi del parser SPDX.
Sono necessarie perché `evaluator.py` esegue controlli `isinstance()` che devono avere esito positivo
nei test senza importare la logica reale da `parser_spdx`.
"""

def test_lookup_status_found():
    """
    Verifica che la funzione interna `_lookup_status` recuperi correttamente
    gli stati di compatibilità ('yes', 'no') dalla matrice simulata.
    """
    # Nota: Si basa sui dati definiti in `complex_matrix_data` (conftest.py)
    assert evaluator._lookup_status("MIT", "Apache-2.0") == "yes"
    assert evaluator._lookup_status("MIT", "Proprietary") == "no"

def test_lookup_status_unknown():
    """
    Verifica che `_lookup_status` restituisca 'unknown' per le licenze
    che non sono presenti nella matrice di compatibilità.
    """
    assert evaluator._lookup_status("MIT", "Unknown-License") == "unknown"
    assert evaluator._lookup_status("NonExistentMain", "MIT") == "unknown"

def test_eval_node_none():
    """
    Garantisce che passando `None` come nodo si ottenga uno stato 'unknown'
    e un messaggio di errore appropriato nel trace.
    """
    status, trace = evaluator.eval_node("MIT", None)
    assert status == "unknown"
    assert "Missing expression or not recognized" in trace[0]

def test_eval_leaf_simple(MockLeaf):
    """
    Testa la valutazione di un nodo Leaf semplice (singola licenza).
    Scenario: Controllo di 'Apache-2.0' contro 'MIT'.
    Atteso: Compatibile ('yes').
    """
    node = MockLeaf("Apache-2.0")

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "yes"
    assert "Apache-2.0 → yes with respect to MIT" in trace[0]

def test_eval_leaf_with_exception(MockLeaf):
    """
    Testa la gestione della clausola 'WITH'.
    Scenario: 'GPL-3.0 WITH Classpath-exception'.
    Logica: Il valutatore dovrebbe rimuovere l'eccezione e valutare la licenza di base ('GPL-3.0').
    Atteso: Compatibile ('yes'), con una nota di trace riguardante l'eccezione.
    """
    node = MockLeaf("GPL-3.0 WITH Classpath-exception")

    # In conftest, GPL-3.0 è compatibile con se stesso.
    status, trace = evaluator.eval_node("GPL-3.0", node)

    assert status == "yes"
    # Assicurati che il messaggio di errore NON sia presente
    assert "exception requires manual verification" not in trace[0]
    # Assicurati che il messaggio di successo/rilevamento SIA presente
    assert "Exception detected" in trace[0]

def test_eval_or_logic_optimistic(MockLeaf, MockOr):
    """
    Testa la logica dell'operatore 'OR'.
    Regola: Valutazione ottimistica. Se almeno un ramo è compatibile, il risultato è compatibile.
    Scenario: 'GPL-3.0 (incompatibile) OR Apache-2.0 (compatibile)' contro 'MIT'.
    Atteso: Compatibile ('yes').
    """
    node = MockOr(MockLeaf("GPL-3.0"), MockLeaf("Apache-2.0"))

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "yes"
    assert "OR ⇒ yes" in trace[-1]


def test_eval_and_logic_conservative(MockLeaf, MockAnd):
    """
    Testa la logica dell'operatore 'AND'.
    Regola: Valutazione conservativa. Se un ramo è incompatibile, il risultato è incompatibile.
    Scenario: 'MIT (compatibile) AND GPL-3.0 (incompatibile)' contro 'MIT'.
    Atteso: Incompatibile ('no').
    """
    node = MockAnd(MockLeaf("MIT"), MockLeaf("GPL-3.0"))

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "no"
    # Verifica che il trace contenga la valutazione di entrambi i rami
    assert len(trace) >= 2


def test_and_cross_compatibility_check(MockLeaf, MockAnd):
    """
    Verifica che la logica 'AND' esegua controlli incrociati di compatibilità tra gli operandi.
    Scenario: 'Apache-2.0 AND GPL-3.0'.
    Logica: Oltre a controllare rispetto alla licenza principale, il sistema deve verificare se
    Apache-2.0 è compatibile con GPL-3.0 (controllo incrociato da sinistra a destra).
    """
    node = MockAnd(MockLeaf("Apache-2.0"), MockLeaf("GPL-3.0"))

    # Non stiamo asserendo lo stato finale qui, ma piuttosto il *processo*.
    # Il trace deve registrare che è avvenuto un controllo incrociato.
    status, trace = evaluator.eval_node("GPL-3.0", node)

    trace_str = " ".join(trace)
    # Verifica che almeno un controllo di compatibilità incrociata sia registrato (da sinistra a destra)
    assert "Cross compatibility:" in trace_str

@pytest.mark.parametrize("a,b,expected", [
    ("yes", "yes", "yes"),
    ("yes", "no", "no"),
    ("conditional", "yes", "conditional"),
])
def test_combine_and_parametrized(a, b, expected):
    """
    Testa direttamente le funzioni helper per combinare valori di logica a tre stati.
    Verifica le tabelle di verità per le operazioni AND/OR con 'yes', 'no' e 'conditional'.
    """
    assert evaluator._combine_and(a, b) == expected


@pytest.mark.parametrize("a,b,expected", [
    ("yes", "no", "yes"),
    ("no", "no", "no"),
    ("conditional", "no", "conditional"),
])
def test_combine_or_parametrized(a, b, expected):
    """
    Testa direttamente le funzioni helper per combinare valori di logica a tre stati.
    Verifica le tabelle di verità per le operazioni AND/OR con 'yes', 'no' e 'conditional'.
    """
    assert evaluator._combine_or(a, b) == expected

def test_lookup_status_empty_matrix():
    """
    Caso limite: Testa il comportamento quando la matrice di compatibilità è None o vuota.
    Dovrebbe fallire in modo controllato restituendo 'unknown'.
    """
    # Sovrascrivi il patch globale specificamente per questo test
    with patch("app.services.compatibility.evaluator.get_matrix", return_value=None):
        assert evaluator._lookup_status("MIT", "MIT") == "unknown"

    with patch("app.services.compatibility.evaluator.get_matrix", return_value={}):
        assert evaluator._lookup_status("MIT", "MIT") == "unknown"

def test_eval_leaf_with_exception_fail(MockLeaf):
    """
    Testa una clausola di eccezione 'WITH' dove la licenza di base è intrinsecamente INCOMPATIBILE.
    Scenario: 'Proprietary WITH Some-Exception' contro 'GPL-3.0'.
    Atteso: Incompatibile ('no'). L'esistenza dell'eccezione non dovrebbe sovrascrivere l'incompatibilità di base.
    """
    # Proprietary -> NO per GPL-3.0 nei nostri dati mock
    node = MockLeaf("Proprietary WITH Some-Exception")

    status, trace = evaluator.eval_node("GPL-3.0", node)

    assert status == "no"
    assert "exception presence requires manual verification" in trace[0]

def test_combine_conditional_logic():
    """
    Testa combinazioni specifiche che portano a uno stato 'conditional'.
    Garantisce che 'conditional' si propaghi correttamente attraverso la logica booleana.
    """
    # AND: Se un lato è condizionale e l'altro è sì, il risultato è condizionale.
    assert evaluator._combine_and("yes", "conditional") == "conditional"
    assert evaluator._combine_and("conditional", "conditional") == "conditional"

    # OR: Se un lato è condizionale e l'altro è no, il risultato è condizionale
    # (perché il lato 'no' viene scartato nella logica OR).
    assert evaluator._combine_or("no", "conditional") == "conditional"
    assert evaluator._combine_or("conditional", "conditional") == "conditional"

def test_eval_node_unrecognized_type(MockNode):
    """
    Codifica difensiva: Testa la reazione del sistema a un tipo di nodo sconosciuto
    (ad esempio, se il parser è esteso ma il valutatore non è aggiornato).
    Atteso: Restituisce 'unknown'.
    """
    class UnknownNode(MockNode):
        pass

    status, trace = evaluator.eval_node("MIT", UnknownNode())
    assert status == "unknown"
    assert "Unrecognized node" in trace[0]

def test_and_nested_leaves_collection(MockLeaf, MockOr, MockAnd):
    """
    Test avanzato: Verifica la raccolta ricorsiva delle foglie per i controlli incrociati
    in strutture annidate.
    Struttura: '(MIT OR Apache-2.0) AND GPL-3.0'.
    Logica: Il sistema deve estrarre TUTTE le foglie dal lato sinistro (MIT, Apache)
    e controllarle rispetto al lato destro (GPL).
    """
    # Costruzione dell'albero: (MIT OR Apache) AND GPL
    left_node = MockOr(MockLeaf("MIT"), MockLeaf("Apache-2.0"))
    right_node = MockLeaf("GPL-3.0")
    root = MockAnd(left_node, right_node)

    status, trace = evaluator.eval_node("GPL-3.0", root)

    trace_str = " ".join(trace)

    # Verifica che i controlli incrociati siano stati eseguiti per TUTTE le foglie annidate
    assert "Cross compatibility:" in trace_str

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
    # Verifica che il trace contenga informazioni di valutazione per entrambi gli operandi
    assert len(trace) >= 2


@pytest.mark.parametrize("main,left,right,expected", [
    ("MIT", "Apache-2.0", "GPL-3.0", "yes"),          # yes OR no -> yes
    ("MIT", "GPL-3.0", "GPL-3.0", "no"),             # no OR no -> no
    ("MIT", "LGPL-2.1", "GPL-3.0", "conditional"),   # conditional OR no -> conditional
    ("GPL-3.0", "MIT", "Apache-2.0", "yes"),        # yes OR no -> yes (licenza principale diversa)
])
def test_eval_or_parametrized(MockOr, MockLeaf, main, left, right, expected):
    node = MockOr(MockLeaf(left), MockLeaf(right))
    status, trace = evaluator.eval_node(main, node)
    assert status == expected
    assert any(f"OR ⇒ {expected}" in line for line in trace)


def test_collect_leaves_with_unknown_node(MockAnd, MockLeaf, MockNode):
    """
    Verifica che `_collect_leaves` gestisca i tipi di nodo non riconosciuti in modo controllato
    (restituendo un elenco vuoto), garantendo una copertura del 100% del percorso di fallback implicito.
    """

    class UnknownNode(MockNode):
        pass

    # Crea una struttura: UnknownNode AND MIT
    # Questo attiva _collect_leaves su UnknownNode durante la fase di controllo incrociato di _eval_and
    node = MockAnd(UnknownNode(), MockLeaf("MIT"))

    # La valutiamo per attivare il flusso
    status, trace = evaluator.eval_node("MIT", node)

    # Verifica il flusso di esecuzione:
    # 1. UnknownNode viene valutato come 'unknown' (già coperto)
    # 2. _collect_leaves viene chiamato su UnknownNode -> restituisce []
    # 3. Il ciclo di controlli incrociati viene eseguito 0 volte per il lato sinistro

    # Poiché un ramo è 'unknown' e l'altro è 'yes', il risultato dovrebbe essere 'conditional'
    assert status == "conditional"

    # Assicurati che non siano stati registrati controlli di compatibilità incrociata (perché UnknownNode ha prodotto nessuna foglia)
    assert not any("Cross compatibility:" in line for line in trace)


def test_collect_leaves_with_unknown_node(MockAnd, MockLeaf, MockNode):
    """
    Verifica che `_collect_leaves` gestisca i tipi di nodo non riconosciuti in modo controllato
    (restituendo un elenco vuoto).

    Questo test mira alla dichiarazione di ritorno implicita alla fine di `_collect_leaves`.
    Annidando un UnknownNode all'interno di un nodo And, attiviamo `_collect_leaves`
    durante la fase di controllo di compatibilità incrociata.
    """

    # Definisci un tipo di nodo che non è né Leaf né And/Or
    class UnknownNode(MockNode):
        pass

    # Struttura: UnknownNode AND MIT
    # _eval_and chiamerà _collect_leaves(node.left) che è il nostro UnknownNode
    node = MockAnd(UnknownNode(), MockLeaf("MIT"))

    # Valuta contro una licenza principale fittizia
    status, trace = evaluator.eval_node("MIT", node)

    # Verifica il flusso di esecuzione:
    # 1. eval_node(UnknownNode) -> restituisce "unknown"
    # 2. _collect_leaves(UnknownNode) -> restituisce []
    # 3. Il ciclo di controllo incrociato non viene eseguito perché left_leaves è vuoto.

    # Il risultato dovrebbe essere 'conditional' perché abbiamo "unknown AND yes"
    assert status == "conditional"

    # Verifica che il nodo sconosciuto non abbia interrotto la logica di controllo incrociato
    assert not any("Cross compatibility:" in line for line in trace)


def test_collect_leaves_with_exception_in_and(MockAnd, MockLeaf):
    """
    Verifica che `_collect_leaves` analizzi correttamente le licenze con eccezioni 'WITH'
    quando appaiono all'interno di una struttura AND.

    Questo copre il ramo 'if " WITH " in v:' all'interno di `_collect_leaves`, che viene
    attivato solo durante la fase di controllo di compatibilità incrociata di un nodo AND.
    """
    # Scenario: (GPL-3.0 WITH Classpath-exception) AND MIT
    # Questo costringe _collect_leaves a essere eseguito sul nodo sinistro, dividendo la stringa.
    node = MockAnd(
        MockLeaf("GPL-3.0 WITH Classpath-exception"),
        MockLeaf("MIT")
    )

    # Valuta contro una licenza principale fittizia
    status, trace = evaluator.eval_node("MIT", node)

    # Verifichiamo che il controllo incrociato abbia utilizzato il nome della licenza di base ("GPL-3.0")
    # invece della stringa completa. Questo conferma che la logica di divisione in
    # _collect_leaves è stata eseguita.

    trace_str = " ".join(trace)

    # Il trace dovrebbe mostrare un controllo incrociato tra GPL-3.0 (ripulito) e MIT
    assert "Cross compatibility: GPL-3.0 with respect to MIT" in trace_str