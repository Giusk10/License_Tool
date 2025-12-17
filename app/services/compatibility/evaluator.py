"""
This module implements a recursive evaluation engine for SPDX license trees.
It uses a Tri-State logic (Yes | No | Conditional/Unknown) to determine compatibility.

Key Logic:
- **Leaf Nodes**: Looked up directly in the compatibility matrix. Exceptions (WITH clause)
  are noted in the trace.
- **AND Operators**: Evaluated conservatively. Both branches must be compatible.
  Cross-checks between left and right branches are performed to detect mutual incompatibilities.
- **OR Operators**: Evaluated such that if at least one branch is compatible,
  the result is compatible.
"""

from typing import List, Optional, Tuple
from .parser_spdx import Node, Leaf, And, Or
from .compat_utils import normalize_symbol
from .matrix import get_matrix

Tri = str


def _lookup_status(main_license: str, dep_license: str) -> Tri:
    """
    Looks up the compatibility status of `dep_license` against `main_license`
    in the compatibility matrix.
    """
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
    """
    Combines two results for the AND operator (conservative rule).
    """
    if a == "no" or b == "no":
        return "no"
    if a == "yes" and b == "yes":
        return "yes"
    return "conditional"


def _combine_or(a: Tri, b: Tri) -> Tri:
    """
    Combines two results for the OR operator (conservative rule).
    """
    if a == "yes" or b == "yes":
        return "yes"
    if a == "no" and b == "no":
        return "no"
    return "conditional"


def eval_node(main_license: str, node: Optional[Node]) -> Tuple[Tri, List[str]]:
    """
    Recursively evaluates an SPDX node against the `main_license`.

    Returns:
        Tuple[Tri, List[str]]:
            - Tri: The status ("yes", "no", "conditional", "unknown").
            - List[str]: A trace of strings explaining the derivation of the result,
              useful for reporting and debugging.
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
            """
            Extracts all leaf license values from a subtree (removes WITH parts).
            """
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
