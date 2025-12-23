"""
License Evaluator Module.

This module implements a recursive evaluation engine for SPDX license trees.
It determines compatibility using a Tri-State logic (Yes | No | Conditional/Unknown).

Key Logic:
    - **Leaf Nodes**: Evaluated directly against the compatibility matrix.
      Exceptions (WITH clauses) are parsed and noted in the trace.
    - **AND Operators**: Evaluated conservatively. Both branches must be compatible.
      Additionally, cross-checks between left and right branches are performed
      to detect mutual incompatibilities between dependencies.
    - **OR Operators**: Evaluated liberally. If at least one branch is compatible,
      the result is considered compatible.
"""

from typing import List, Optional, Tuple, Union
from .parser_spdx import Node, Leaf, And, Or
from .compat_utils import normalize_symbol
from .matrix import get_matrix

# Type alias for clarity in docstrings (values: "yes", "no", "conditional", "unknown")
TriState = str


def _lookup_status(main_license: str, dep_license: str) -> TriState:
    """
    Looks up the compatibility status of a dependency license against the main license.

    It attempts to find a match in the matrix using the raw string, the normalized
    symbol, and the stripped string to ensure robustness.

    Args:
        main_license (str): The project's main license.
        dep_license (str): The license of the dependency file.

    Returns:
        TriState: 'yes', 'no', 'conditional', or 'unknown' if not found.
    """
    matrix = get_matrix()
    if not matrix:
        return "unknown"

    row = matrix.get(main_license)
    if not row:
        return "unknown"

    # Try multiple variations to find a match in the matrix
    candidates = [dep_license, normalize_symbol(dep_license), dep_license.strip()]
    for c in candidates:
        status = row.get(c)
        if status in {"yes", "no", "conditional"}:
            return status

    return "unknown"


def _combine_and(a: TriState, b: TriState) -> TriState:
    """
    Combines two results for an AND operator using conservative rules.

    Args:
        a (TriState): Status of the left branch.
        b (TriState): Status of the right branch.

    Returns:
        TriState: 'yes' only if both are 'yes', 'no' if either is 'no', else 'conditional'.
    """
    if a == "no" or b == "no":
        return "no"
    if a == "yes" and b == "yes":
        return "yes"
    return "conditional"


def _combine_or(a: TriState, b: TriState) -> TriState:
    """
    Combines two results for an OR operator using liberal rules.

    Args:
        a (TriState): Status of the left branch.
        b (TriState): Status of the right branch.

    Returns:
        TriState: 'yes' if either is 'yes', 'no' only if both are 'no', else 'conditional'.
    """
    if a == "yes" or b == "yes":
        return "yes"
    if a == "no" and b == "no":
        return "no"
    return "conditional"


def _collect_leaves(node: Node) -> List[str]:
    """
    Recursively extracts all leaf license values from a subtree.

    This helper is used primarily for cross-check analysis in AND nodes.
    It strips 'WITH' clauses to return only the base license symbols.

    Args:
        node (Node): The root of the subtree to collect from.

    Returns:
        List[str]: A list of normalized license symbols found in the subtree.
    """
    vals: List[str] = []

    if isinstance(node, Leaf):
        v = node.value
        # Handle "License WITH Exception" format
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
    Evaluates a single Leaf node against the main license.

    Handles 'WITH' exceptions by checking the base license and adding
    explanatory notes to the trace.

    Args:
        main_license (str): The project's main license.
        node (Leaf): The leaf node containing the license string.

    Returns:
        Tuple[TriState, List[str]]: The status and the evaluation trace.
    """
    val = node.value

    # Handle WITH clause
    if " WITH " in val:
        base, exc = val.split(" WITH ", 1)
        base = normalize_symbol(base)
        exc = exc.strip()

        status = _lookup_status(main_license, base)

        reason = (
            f"{base} (with exception: {exc}) → {status} "
            f"with respect to {main_license}"
        )

        # append specific warnings regarding the exception
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

    # Standard Case (No WITH clause)
    status = _lookup_status(main_license, val)
    reason = f"{val} → {status} with respect to {main_license}"
    return status, [reason]


def _eval_and(main_license: str, node: And) -> Tuple[TriState, List[str]]:
    """
    Evaluates an AND node including internal cross-checks.

    For an AND expression (e.g., "A AND B"), this checks:
    1. Compatibility of A vs Main License.
    2. Compatibility of B vs Main License.
    3. Cross-compatibility of A vs B (and vice versa).

    Args:
        main_license (str): The project's main license.
        node (And): The AND node to evaluate.

    Returns:
        Tuple[TriState, List[str]]: The combined status and the full trace including cross-checks.
    """
    # 1. Evaluate branches individually against main license
    ls, ltrace = eval_node(main_license, node.left)
    rs, rtrace = eval_node(main_license, node.right)

    combined = _combine_and(ls, rs)

    # 2. Perform cross-checks between left and right branches
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
    Evaluates an OR node.

    Args:
        main_license (str): The project's main license.
        node (Or): The OR node to evaluate.

    Returns:
        Tuple[TriState, List[str]]: The combined status and trace.
    """
    ls, ltrace = eval_node(main_license, node.left)
    rs, rtrace = eval_node(main_license, node.right)

    combined = _combine_or(ls, rs)
    trace = ltrace + rtrace + [f"OR ⇒ {combined}"]

    return combined, trace


def eval_node(main_license: str, node: Optional[Node]) -> Tuple[TriState, List[str]]:
    """
    Recursively evaluates an SPDX node against the `main_license`.

    This is the main entry point for the evaluation logic. It dispatches
    the evaluation to the specific handler based on the node type.

    Args:
        main_license (str): The project's main license symbol.
        node (Optional[Node]): The root node of the license tree to evaluate.

    Returns:
        Tuple[str, List[str]]:
            - The compatibility status ("yes", "no", "conditional", "unknown").
            - A list of strings explaining the derivation of the result,
              useful for reporting and debugging.
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
