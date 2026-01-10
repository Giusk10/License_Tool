"""
License Evaluator Module.

Questo modulo implementa un motore di valutazione ricorsivo per alberi di licenze SPDX.
Determina la compatibilità utilizzando una logica a tre stati (Sì | No | Condizionale/Sconosciuto).

Logica Chiave:
    - **Nodi Foglia**: Valutati direttamente rispetto alla matrice di compatibilità.
      Le eccezioni (clausole WITH) vengono analizzate e annotate nella traccia.
    - **Operatori AND**: Valutati in modo conservativo. Entrambi i rami devono essere compatibili.
      Inoltre, vengono eseguiti controlli incrociati tra i rami sinistro e destro
      per rilevare incompatibilità reciproche tra le dipendenze.
    - **Operatori OR**: Valutati in modo liberale. Se almeno un ramo è compatibile,
      il risultato è considerato compatibile.
"""

from typing import List, Optional, Tuple, Union
from .parser_spdx import Node, Leaf, And, Or
from .compat_utils import normalize_symbol
from .matrix import get_matrix

# Alias di tipo per chiarezza nelle docstring (valori: "yes", "no", "conditional", "unknown")
TriState = str


def _lookup_status(main_license: str, dep_license: str) -> TriState:
    """
    Cerca lo stato di compatibilità di una licenza di dipendenza rispetto alla licenza principale.

    Tenta di trovare una corrispondenza nella matrice utilizzando la stringa grezza, il simbolo
    normalizzato e la stringa pulita per garantire robustezza.

    Args:
        main_license (str): La licenza principale del progetto.
        dep_license (str): La licenza del file di dipendenza.

    Returns:
        TriState: 'yes', 'no', 'conditional', o 'unknown' se non trovata.
    """
    matrix = get_matrix()
    if not matrix:
        return "unknown"

    row = matrix.get(main_license)
    if not row:
        return "unknown"

    # Prova diverse varianti per trovare una corrispondenza nella matrice
    candidates = [dep_license, normalize_symbol(dep_license), dep_license.strip()]
    for c in candidates:
        status = row.get(c)
        if status in {"yes", "no", "conditional"}:
            return status

    return "unknown"


def _combine_and(a: TriState, b: TriState) -> TriState:
    """
    Combina due risultati per un operatore AND utilizzando regole conservative.

    Args:
        a (TriState): Stato del ramo sinistro.
        b (TriState): Stato del ramo destro.

    Returns:
        TriState: 'yes' solo se entrambi sono 'yes', 'no' se uno dei due è 'no', altrimenti 'conditional'.
    """
    if a == "no" or b == "no":
        return "no"
    if a == "yes" and b == "yes":
        return "yes"
    return "conditional"


def _combine_or(a: TriState, b: TriState) -> TriState:
    """
    Combina due risultati per un operatore OR utilizzando regole liberali.

    Args:
        a (TriState): Stato del ramo sinistro.
        b (TriState): Stato del ramo destro.

    Returns:
        TriState: 'yes' se uno dei due è 'yes', 'no' solo se entrambi sono 'no', altrimenti 'conditional'.
    """
    if a == "yes" or b == "yes":
        return "yes"
    if a == "no" and b == "no":
        return "no"
    return "conditional"


def _collect_leaves(node: Node) -> List[str]:
    """
    Estrae ricorsivamente tutti i valori di licenza foglia da un sottoalbero.

    Questo helper è utilizzato principalmente per l'analisi dei controlli incrociati nei nodi AND.
    Rimuove le clausole 'WITH' per restituire solo i simboli di licenza base.

    Args:
        node (Node): La radice del sottoalbero da cui raccogliere.

    Returns:
        List[str]: Un elenco di simboli di licenza normalizzati trovati nel sottoalbero.
    """
    vals: List[str] = []

    if isinstance(node, Leaf):
        v = node.value
        # Gestisce il formato "Licenza WITH Eccezione"
        if " WITH " in v:
            b, _ = v.split(" WITH ", 1)
            vals.append(normalize_symbol(b))
        else:
            vals.append(normalize_symbol(v))

    elif isinstance(node, (And, Or)):
        vals.extend(_collect_leaves(node.left))
        vals.extend(_collect_leaves(node.right))

    return vals


def _eval_leaf(main_license: str, node: Leaf) -> Tuple[TriState, List[str]]:
    """
    Valuta un singolo nodo Foglia rispetto alla licenza principale.

    Gestisce le eccezioni 'WITH' controllando la licenza base e aggiungendo
    note esplicative alla traccia.

    Args:
        main_license (str): La licenza principale del progetto.
        node (Leaf): Il nodo foglia contenente la stringa della licenza.

    Returns:
        Tuple[TriState, List[str]]: Lo stato e la traccia di valutazione.
    """
    val = node.value

    # Gestisce la clausola WITH
    if " WITH " in val:
        base, exc = val.split(" WITH ", 1)
        base = normalize_symbol(base)
        exc = exc.strip()

        status = _lookup_status(main_license, base)

        reason = (
            f"{base} (with exception: {exc}) → {status} "
            f"with respect to {main_license}"
        )

        # aggiunge avvisi specifici riguardanti l'eccezione
        if exc:
            if status != "yes":
                reason += (
                    "; Note: exception presence requires "
                    "manual verification on exception impact"
                )
            else:
                reason += (
                    "; Exception detected: verify if the "
                    "exception alters compatibility"
                )
        return status, [reason]

    # Caso Standard (Nessuna clausola WITH)
    status = _lookup_status(main_license, val)
    reason = f"{val} → {status} with respect to {main_license}"
    return status, [reason]


def _eval_and(main_license: str, node: And) -> Tuple[TriState, List[str]]:
    """
    Valuta un nodo AND includendo controlli incrociati interni.

    Per un'espressione AND (es. "A AND B"), verifica:
    1. Compatibilità di A vs Licenza Principale.
    2. Compatibilità di B vs Licenza Principale.
    3. Compatibilità incrociata di A vs B (e viceversa).

    Args:
        main_license (str): La licenza principale del progetto.
        node (And): Il nodo AND da valutare.

    Returns:
        Tuple[TriState, List[str]]: Lo stato combinato e la traccia completa inclusi i controlli incrociati.
    """
    # 1. Valuta i rami individualmente rispetto alla licenza principale
    ls, ltrace = eval_node(main_license, node.left)
    rs, rtrace = eval_node(main_license, node.right)

    combined = _combine_and(ls, rs)

    # 2. Esegue controlli incrociati tra i rami sinistro e destro
    left_leaves = _collect_leaves(node.left)
    right_leaves = _collect_leaves(node.right)
    cross_checks: List[str] = []

    for left_lic in left_leaves:
        for right_lic in right_leaves:
            st_lr = _lookup_status(left_lic, right_lic)
            cross_checks.append(
                f"Cross compatibility: {left_lic} with respect to {right_lic} → {st_lr}"
            )

    trace = ltrace + rtrace + cross_checks
    return combined, trace


def _eval_or(main_license: str, node: Or) -> Tuple[TriState, List[str]]:
    """
    Valuta un nodo OR.

    Args:
        main_license (str): La licenza principale del progetto.
        node (Or): Il nodo OR da valutare.

    Returns:
        Tuple[TriState, List[str]]: Lo stato combinato e la traccia.
    """
    ls, ltrace = eval_node(main_license, node.left)
    rs, rtrace = eval_node(main_license, node.right)

    combined = _combine_or(ls, rs)
    trace = ltrace + rtrace + [f"OR ⇒ {combined}"]

    return combined, trace


def eval_node(main_license: str, node: Optional[Node]) -> Tuple[TriState, List[str]]:
    """
    Valuta ricorsivamente un nodo SPDX rispetto alla `main_license`.

    Questo è il punto di ingresso principale per la logica di valutazione. Invia
    la valutazione al gestore specifico in base al tipo di nodo.

    Args:
        main_license (str): Il simbolo della licenza principale del progetto.
        node (Optional[Node]): Il nodo radice dell'albero delle licenze da valutare.

    Returns:
        Tuple[str, List[str]]:
            - Lo stato di compatibilità ("yes", "no", "conditional", "unknown").
            - Un elenco di stringhe che spiegano la derivazione del risultato,
              utile per reportistica e debug.
    """
    if node is None:
        return "unknown", ["Missing expression or not recognized"]

    if isinstance(node, Leaf):
        return _eval_leaf(main_license, node)

    if isinstance(node, And):
        return _eval_and(main_license, node)

    if isinstance(node, Or):
        return _eval_or(main_license, node)

    return "unknown", ["Unrecognized node"]
