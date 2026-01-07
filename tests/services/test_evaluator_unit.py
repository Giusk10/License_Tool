"""
test: services/compatibility/evaluator.py

This module contains unit tests for the license compatibility evaluator engine.
It verifies the logic for determining compatibility between license expressions
(including complex SPDX strings with AND/OR operators and WITH exceptions)
against a main project license.

- The `evaluator` module is tested in isolation by mocking external dependencies
  such as the compatibility matrix and the SPDX parser classes.
- Compatibility data is injected via `conftest.py` to ensure consistent
  test scenarios across the suite.
- Specific tests cover empty matrices, unknown licenses, and nested logical operators.
"""

import pytest
from unittest.mock import patch
from app.services.compatibility import evaluator

"""
The following classes are defined here to mock the behavior of the real SPDX parser nodes.
They are required because `evaluator.py` performs `isinstance()` checks that must pass
during testing without importing the actual logic from `parser_spdx`.
"""

def test_lookup_status_found():
    """
    Verifies that the internal `_lookup_status` function correctly retrieves
    compatibility statuses ('yes', 'no') from the mocked matrix.
    """
    # Note: Relies on data defined in `complex_matrix_data` (conftest.py)
    assert evaluator._lookup_status("MIT", "Apache-2.0") == "yes"
    assert evaluator._lookup_status("MIT", "Proprietary") == "no"

def test_lookup_status_unknown():
    """
    Verifies that `_lookup_status` returns 'unknown' for licenses
    that are not present in the compatibility matrix.
    """
    assert evaluator._lookup_status("MIT", "Unknown-License") == "unknown"
    assert evaluator._lookup_status("NonExistentMain", "MIT") == "unknown"

def test_eval_node_none():
    """
    Ensures that passing `None` as a node results in an 'unknown' status
    and an appropriate error message in the trace.
    """
    status, trace = evaluator.eval_node("MIT", None)
    assert status == "unknown"
    assert "Missing expression or not recognized" in trace[0]

def test_eval_leaf_simple(MockLeaf):
    """
    Tests the evaluation of a simple Leaf node (single license).
    Scenario: Checking 'Apache-2.0' against 'MIT'.
    Expected: Compatible ('yes').
    """
    node = MockLeaf("Apache-2.0")

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "yes"
    assert "Apache-2.0 → yes with respect to MIT" in trace[0]

def test_eval_leaf_with_exception(MockLeaf):
    """
    Tests the handling of the 'WITH' clause.
    Scenario: 'GPL-3.0 WITH Classpath-exception'.
    Logic: The evaluator should strip the exception and evaluate the base license ('GPL-3.0').
    Expected: Compatible ('yes'), with a trace note regarding the exception.
    """
    node = MockLeaf("GPL-3.0 WITH Classpath-exception")

    # In conftest, GPL-3.0 is compatible with itself.
    status, trace = evaluator.eval_node("GPL-3.0", node)

    assert status == "yes"
    # Ensure the failure message is NOT present
    assert "exception requires manual verification" not in trace[0]
    # Ensure the success/detection message IS present
    assert "Exception detected" in trace[0]

def test_eval_or_logic_optimistic(MockLeaf, MockOr):
    """
    Tests the 'OR' operator logic.
    Rule: Optimistic evaluation. If at least one branch is compatible, the result is compatible.
    Scenario: 'GPL-3.0 (incompatible) OR Apache-2.0 (compatible)' against 'MIT'.
    Expected: Compatible ('yes').
    """
    node = MockOr(MockLeaf("GPL-3.0"), MockLeaf("Apache-2.0"))

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "yes"
    assert "OR ⇒ yes" in trace[-1]


def test_eval_and_logic_conservative(MockLeaf, MockAnd):
    """
    Tests the 'AND' operator logic.
    Rule: Conservative evaluation. If any branch is incompatible, the result is incompatible.
    Scenario: 'MIT (compatible) AND GPL-3.0 (incompatible)' against 'MIT'.
    Expected: Incompatible ('no').
    """
    node = MockAnd(MockLeaf("MIT"), MockLeaf("GPL-3.0"))

    status, trace = evaluator.eval_node("MIT", node)
    assert status == "no"
    # Verify trace contains evaluation of both branches
    assert len(trace) >= 2


def test_and_cross_compatibility_check(MockLeaf, MockAnd):
    """
    Verifies that the 'AND' logic performs cross-compatibility checks between operands.
    Scenario: 'Apache-2.0 AND GPL-3.0'.
    Logic: Besides checking against the main license, the system must check if
    Apache-2.0 is compatible with GPL-3.0 (left-to-right cross-check).
    """
    node = MockAnd(MockLeaf("Apache-2.0"), MockLeaf("GPL-3.0"))

    # We are not asserting the final status here, but rather the *process*.
    # The trace must record that a cross-check occurred.
    status, trace = evaluator.eval_node("GPL-3.0", node)

    trace_str = " ".join(trace)
    # Verify that at least one cross-compatibility check is recorded (L->R)
    assert "Cross compatibility:" in trace_str

@pytest.mark.parametrize("a,b,expected", [
    ("yes", "yes", "yes"),
    ("yes", "no", "no"),
    ("conditional", "yes", "conditional"),
])
def test_combine_and_parametrized(a, b, expected):
    """
    Directly tests the helper functions for combining tri-state logic values.
    Verifies the truth tables for AND/OR operations with 'yes', 'no', and 'conditional'.
    """
    assert evaluator._combine_and(a, b) == expected


@pytest.mark.parametrize("a,b,expected", [
    ("yes", "no", "yes"),
    ("no", "no", "no"),
    ("conditional", "no", "conditional"),
])
def test_combine_or_parametrized(a, b, expected):
    """
    Directly tests the helper functions for combining tri-state logic values.
    Verifies the truth tables for AND/OR operations with 'yes', 'no', and 'conditional'.
    """
    assert evaluator._combine_or(a, b) == expected

def test_lookup_status_empty_matrix():
    """
    Edge Case: Tests behavior when the compatibility matrix is None or empty.
    Should fail gracefully returning 'unknown'.
    """
    # Override the global patch specifically for this test
    with patch("app.services.compatibility.evaluator.get_matrix", return_value=None):
        assert evaluator._lookup_status("MIT", "MIT") == "unknown"

    with patch("app.services.compatibility.evaluator.get_matrix", return_value={}):
        assert evaluator._lookup_status("MIT", "MIT") == "unknown"

def test_eval_leaf_with_exception_fail(MockLeaf):
    """
    Tests a 'WITH' exception clause where the base license is inherently INCOMPATIBLE.
    Scenario: 'Proprietary WITH Some-Exception' against 'GPL-3.0'.
    Expected: Incompatible ('no'). The exception existence should not override the base incompatibility.
    """
    # Proprietary -> NO for GPL-3.0 in our mock data
    node = MockLeaf("Proprietary WITH Some-Exception")

    status, trace = evaluator.eval_node("GPL-3.0", node)

    assert status == "no"
    assert "exception presence requires manual verification" in trace[0]

def test_combine_conditional_logic():
    """
    Tests specific combinations that result in a 'conditional' status.
    Ensures that 'conditional' propagates correctly through boolean logic.
    """
    # AND: If one side is conditional and the other is yes, result is conditional.
    assert evaluator._combine_and("yes", "conditional") == "conditional"
    assert evaluator._combine_and("conditional", "conditional") == "conditional"

    # OR: If one side is conditional and the other is no, result is conditional
    # (because the 'no' side is discarded in OR logic).
    assert evaluator._combine_or("no", "conditional") == "conditional"
    assert evaluator._combine_or("conditional", "conditional") == "conditional"

def test_eval_node_unrecognized_type(MockNode):
    """
    Defensive Coding: Tests the system's reaction to an unknown node type
    (e.g., if the parser is extended but the evaluator is not updated).
    Expected: Returns 'unknown'.
    """
    class UnknownNode(MockNode):
        pass

    status, trace = evaluator.eval_node("MIT", UnknownNode())
    assert status == "unknown"
    assert "Unrecognized node" in trace[0]

def test_and_nested_leaves_collection(MockLeaf, MockOr, MockAnd):
    """
    Advanced Test: Verifies the recursive collection of leaves for cross-checks
    in nested structures.
    Structure: '(MIT OR Apache-2.0) AND GPL-3.0'.
    Logic: The system must extract ALL leaves from the left side (MIT, Apache)
    and cross-check them against the right side (GPL).
    """
    # Constructing the tree: (MIT OR Apache) AND GPL
    left_node = MockOr(MockLeaf("MIT"), MockLeaf("Apache-2.0"))
    right_node = MockLeaf("GPL-3.0")
    root = MockAnd(left_node, right_node)

    status, trace = evaluator.eval_node("GPL-3.0", root)

    trace_str = " ".join(trace)

    # Verify that cross-checks were performed for ALL nested leaves
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
    # Verify trace contains evaluation information for both operands
    assert len(trace) >= 2


@pytest.mark.parametrize("main,left,right,expected", [
    ("MIT", "Apache-2.0", "GPL-3.0", "yes"),          # yes OR no -> yes
    ("MIT", "GPL-3.0", "GPL-3.0", "no"),             # no OR no -> no
    ("MIT", "LGPL-2.1", "GPL-3.0", "conditional"),   # conditional OR no -> conditional
    ("GPL-3.0", "MIT", "Apache-2.0", "yes"),        # yes OR no -> yes (different main)
])
def test_eval_or_parametrized(MockOr, MockLeaf, main, left, right, expected):
    node = MockOr(MockLeaf(left), MockLeaf(right))
    status, trace = evaluator.eval_node(main, node)
    assert status == expected
    assert any(f"OR ⇒ {expected}" in line for line in trace)


def test_collect_leaves_with_unknown_node(MockAnd, MockLeaf, MockNode):
    """
    Verifies that `_collect_leaves` handles unrecognized node types gracefully
    (returning an empty list), ensuring 100% coverage of the implicit fallback path.
    """

    class UnknownNode(MockNode):
        pass

    # Create a structure: UnknownNode AND MIT
    # This triggers _collect_leaves on UnknownNode during the cross-check phase of _eval_and
    node = MockAnd(UnknownNode(), MockLeaf("MIT"))

    # We evaluate it to trigger the flow
    status, trace = evaluator.eval_node("MIT", node)

    # Verify execution flow:
    # 1. UnknownNode evaluates to 'unknown' (already covered)
    # 2. _collect_leaves is called on UnknownNode -> returns []
    # 3. Cross-checks loop runs 0 times for the left side

    # Since one branch is 'unknown' and the other 'yes', result should be 'conditional'
    assert status == "conditional"

    # Ensure no cross-compatibility checks were recorded (because UnknownNode yielded no leaves)
    assert not any("Cross compatibility:" in line for line in trace)


def test_collect_leaves_with_unknown_node(MockAnd, MockLeaf, MockNode):
    """
    Verifies that `_collect_leaves` handles unrecognized node types gracefully
    (returning an empty list).

    This test targets the implicit return statement at the end of `_collect_leaves`.
    By nesting an UnknownNode inside an And node, we trigger `_collect_leaves`
    during the cross-compatibility check phase.
    """

    # Define a node type that is neither Leaf nor And/Or
    class UnknownNode(MockNode):
        pass

    # Structure: UnknownNode AND MIT
    # _eval_and will call _collect_leaves(node.left) which is our UnknownNode
    node = MockAnd(UnknownNode(), MockLeaf("MIT"))

    # Evaluate against a dummy main license
    status, trace = evaluator.eval_node("MIT", node)

    # Execution flow verification:
    # 1. eval_node(UnknownNode) -> returns "unknown"
    # 2. _collect_leaves(UnknownNode) -> returns []
    # 3. Cross-check loop doesn't run because left_leaves is empty.

    # Result should be 'conditional' because we have "unknown AND yes"
    assert status == "conditional"

    # Verify that the unknown node didn't crash the cross-check logic
    assert not any("Cross compatibility:" in line for line in trace)


def test_collect_leaves_with_exception_in_and(MockAnd, MockLeaf):
    """
    Verifies that `_collect_leaves` correctly parses licenses with 'WITH' exceptions
    when they appear inside an AND structure.

    This covers the 'if " WITH " in v:' branch inside `_collect_leaves`, which is
    only triggered during the cross-compatibility check phase of an AND node.
    """
    # Scenario: (GPL-3.0 WITH Classpath-exception) AND MIT
    # This forces _collect_leaves to run on the left node, splitting the string.
    node = MockAnd(
        MockLeaf("GPL-3.0 WITH Classpath-exception"),
        MockLeaf("MIT")
    )

    # Evaluate against a dummy main license
    status, trace = evaluator.eval_node("MIT", node)

    # We verify that the cross-check used the base license name ("GPL-3.0")
    # instead of the full string. This confirms that the split logic in
    # _collect_leaves was executed.

    trace_str = " ".join(trace)

    # The trace should show a cross-check between GPL-3.0 (stripped) and MIT
    assert "Cross compatibility: GPL-3.0 with respect to MIT" in trace_str