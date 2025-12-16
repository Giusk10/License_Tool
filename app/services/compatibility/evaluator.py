"""
Modulo `evaluator` — valutazione ricorsiva dell'albero SPDX.

Questo modulo implementa la valutazione tri-stato (Tri = "yes" | "no" | "conditional" | "unknown")
contro la matrice professionale fornita dal modulo `matrix`.

Comportamento chiave:
- Leaf: se il valore contiene "WITH" viene considerata la licenza base per il lookup
  (l'eccezione viene annotata nella trace).
- AND: valuta i due rami e combina gli esiti con una regola conservativa; inoltre esegue
  controlli incrociati tra le leaves dei due rami (L->R e R->L) per rilevare incompatibilità
  reciproche.
- OR: se almeno un ramo è 'yes' allora il risultato finale è 'yes', altrimenti se entrambi
  sono 'no' restituisce 'no', altrimenti 'conditional'.

La funzione pubblica principale è `eval_node(main_license, node)` che restituisce
una tupla (stato, traccia) dove traccia è una lista di stringhe descrittive per report.
"""

from typing import List, Optional, Tuple
from .parser_spdx import Node, Leaf, And, Or
from .compat_utils import normalize_symbol
from .matrix import get_matrix

Tri = str


def _lookup_status(main_license: str, dep_license: str) -> Tri:
    """Effettua il lookup della compatibilità nella matrice considerata (tri-state)."""
    matrix = get_matrix()
    if not matrix:
        return "unknown"
    row = matrix.get(main_license)
    if not row:
        return "unknown"
    candidates = [dep_license, normalize_symbol(dep_license), dep_license.strip()]
    for c in candidates:
        status = row.get(c)
        if status in {"yes", "no", "conditional"}:
            return status
    return "unknown"


def _combine_and(a: Tri, b: Tri) -> Tri:
    """Combina due risultati tri-stato per l'operatore AND usando una regola conservativa."""
    if a == "no" or b == "no":
        return "no"
    if a == "yes" and b == "yes":
        return "yes"
    return "conditional"


def _combine_or(a: Tri, b: Tri) -> Tri:
    """Combina due risultati per l'operatore OR (regola conservativa)."""
    if a == "yes" or b == "yes":
        return "yes"
    if a == "no" and b == "no":
        return "no"
    return "conditional"


def eval_node(main_license: str, node: Optional[Node]) -> Tuple[Tri, List[str]]:
    """
    Valuta ricorsivamente `node` rispetto alla licenza principale `main_license`.

    Restituisce (status, trace) dove trace è una lista di stringhe che spiegano i passaggi
    della valutazione (utile per report e debugging manuale).
    """
    if node is None:
        return "unknown", ["Missing expression or not recognized"]

    if isinstance(node, Leaf):
        val = node.value
        if " WITH " in val:
            base, exc = val.split(" WITH ", 1)
            base = normalize_symbol(base)
            exc = exc.strip()
            status = _lookup_status(main_license, base)
            reason = f"{base} (with exception: {exc}) → {status} with respect to {main_license}"
            if exc:
                if status != "yes":
                    reason += "; Note: exception presence requires manual verification on exception impact"
                else:
                    reason += "; Exception detected: verify if the exception alters compatibility"
            return status, [reason]
        else:
            status = _lookup_status(main_license, val)
            reason = f"{val} → {status} with respect to {main_license}"
            return status, [reason]

    if isinstance(node, And):
        ls, ltrace = eval_node(main_license, node.left)
        rs, rtrace = eval_node(main_license, node.right)
        combined = _combine_and(ls, rs)

        def _collect_leaves(n: Node) -> List[str]:
            """Extracts base licenses from a sub-tree (removes the WITH part if present)."""
            vals: List[str] = []
            if isinstance(n, Leaf):
                v = n.value
                if " WITH " in v:
                    b, _ = v.split(" WITH ", 1)
                    vals.append(normalize_symbol(b))
                else:
                    vals.append(normalize_symbol(v))
            elif isinstance(n, And) or isinstance(n, Or):
                vals.extend(_collect_leaves(n.left))
                vals.extend(_collect_leaves(n.right))
            return vals

        left_leaves = _collect_leaves(node.left)
        right_leaves = _collect_leaves(node.right)
        cross_checks: List[str] = []
        for L in left_leaves:
            for R in right_leaves:
                st_lr = _lookup_status(L, R)
                cross_checks.append(f"Cross compatibility: {L} with respect to {R} → {st_lr}")

        trace = ltrace + rtrace + cross_checks
        return combined, trace

    if isinstance(node, Or):
        ls, ltrace = eval_node(main_license, node.left)
        rs, rtrace = eval_node(main_license, node.right)
        combined = _combine_or(ls, rs)
        trace = ltrace + rtrace + [f"OR ⇒ {combined}"]
        return combined, trace

    return "unknown", ["Unrecognized node"]
