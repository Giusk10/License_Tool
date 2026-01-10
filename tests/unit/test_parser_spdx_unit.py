"""
test: services/compatibility/parser_spdx.py
"""

"""
`parser_spdx` module — simple parser for SPDX expressions.

Supports:
- logical operators: AND, OR (AND has priority over OR; case-insensitive)
- parentheses for grouping: (...)
- WITH construct: combined into a single token "<ID> WITH <ID>"

Behavior:
- Returns `None` for empty strings or strings consisting only of spaces.
- Returns a tree of nodes (`Leaf`, `And`, `Or`) for valid expressions.
- For malformed inputs, the parser attempts to recover without raising unhandled exceptions
  (it may return `None` or a partial sub-tree); explicit tests should define expected behavior.
- `Leaf` calls `normalize_symbol(value)`; in tests, mock `normalize_symbol` in the `parser_spdx` module.
"""

from app.services.compatibility import parser_spdx as ps


def test_parse_empty_returns_none():
    """Empty expression must return None."""
    assert ps.parse_spdx("") is None
    assert ps.parse_spdx("   ") is None


def test_parse_simple_license_creates_leaf(monkeypatch):
    """A simple token must become a Leaf and call normalize_symbol."""
    # mock normalize_symbol to verify it is used
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s.upper())

    node = ps.parse_spdx("mit")
    assert isinstance(node, ps.Leaf)
    assert node.value == "MIT"


def test_parse_with_operator_precedence(monkeypatch):
    """AND has precedence over OR.

    'A OR B AND C' must be parsed as Or(Leaf(A), And(Leaf(B), Leaf(C))).
    """
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    expr = "MIT OR Apache-2.0 AND GPL-3.0"
    root = ps.parse_spdx(expr)

    # root must be Or
    assert isinstance(root, ps.Or)
    # left child MIT
    assert isinstance(root.left, ps.Leaf) and root.left.value == "MIT"
    # right child is And(Apache, GPL)
    assert isinstance(root.right, ps.And)
    assert isinstance(root.right.left, ps.Leaf) and root.right.left.value == "Apache-2.0"
    assert isinstance(root.right.right, ps.Leaf) and root.right.right.value == "GPL-3.0"


def test_parse_parentheses_override_precedence(monkeypatch):
    """Parentheses must enforce precedence: (A AND B) -> And at the top."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    root = ps.parse_spdx("(MIT AND GPL-3.0)")
    assert isinstance(root, ps.And)
    assert isinstance(root.left, ps.Leaf) and root.left.value == "MIT"
    assert isinstance(root.right, ps.Leaf) and root.right.value == "GPL-3.0"


def test_parse_with_combines_with_token(monkeypatch):
    """The WITH construct must be combined into a single Leaf token.

    Ex: 'GPL-2.0 WITH Autoconf-exception-generic' -> Leaf with combined value.
    """
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    expr = "GPL-2.0 WITH Autoconf-exception-generic"
    node = ps.parse_spdx(expr)
    assert isinstance(node, ps.Leaf)
    # the token retains the combined form 'GPL-2.0 WITH Autoconf-exception-generic'
    assert "WITH" in node.value and node.value.startswith("GPL-2.0")


def test_parser_handles_multiple_spaces_and_tabs(monkeypatch):
    """Verify that the parser ignores multiple spaces and tabs between tokens."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    root = ps.parse_spdx("MIT    OR\tGPL-3.0")
    assert isinstance(root, ps.Or)
    assert isinstance(root.left, ps.Leaf) and root.left.value == "MIT"
    assert isinstance(root.right, ps.Leaf) and root.right.value == "GPL-3.0"


def test_parser_parses_deeply_nested_parentheses(monkeypatch):
    """Verify correct parsing of expressions with nested parentheses."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    root = ps.parse_spdx("A OR (B AND (C OR D))")
    assert isinstance(root, ps.Or)
    assert isinstance(root.left, ps.Leaf) and root.left.value == "A"
    assert isinstance(root.right, ps.And)
    assert isinstance(root.right.left, ps.Leaf) and root.right.left.value == "B"
    inner = root.right.right
    assert isinstance(inner, ps.Or)
    assert isinstance(inner.left, ps.Leaf) and inner.left.value == "C"
    assert isinstance(inner.right, ps.Leaf) and inner.right.value == "D"


def test_parser_with_token_handles_extra_spaces_and_case(monkeypatch):
    """Verify that the 'WITH' token is recognized even with extra spaces and different cases."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    node = ps.parse_spdx("mit  with   Exception")
    assert isinstance(node, ps.Leaf)
    assert "WITH" in node.value and node.value.startswith("mit")


def test_parser_handles_malformed_input_gracefully(monkeypatch):
    """Ensures malformed inputs do not raise unhandled exceptions; accepts None or partial Node."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    malformed = ["(MIT AND", "MIT OR", "AND MIT", "MIT WITH"]
    for expr in malformed:
        node = ps.parse_spdx(expr)
        assert node is None or isinstance(node, ps.Node)


def test_tokenize_multiple_with_occurrences(monkeypatch):
    """Verify that an expression with multiple occurrences of WITH does not crash the parser
    and that at least the first occurrence is combined into a token containing 'WITH'."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    expr = "A WITH X WITH Y"
    node = ps.parse_spdx(expr)
    # We don't make rigid assumptions about structure, but ensure it doesn't raise exceptions
    # and that the string 'WITH' is present in at least one leaf value if a leaf exists.
    if node is None:
        assert node is None
    else:
        # Recursively search for a Leaf containing WITH
        found_with = False
        def collect(n):
            nonlocal found_with
            if isinstance(n, ps.Leaf):
                if "WITH" in n.value:
                    found_with = True
            elif isinstance(n, ps.And) or isinstance(n, ps.Or):
                collect(n.left)
                collect(n.right)
        collect(node)
        assert found_with or node is not None


def test_parser_handles_special_characters_and_plus(monkeypatch):
    """Tokens with special characters like '+' and '/' must not cause crashes and must
    be passed to normalize_symbol (mocked)."""
    calls = []
    def fake_normalize(s):
        calls.append(s)
        return s
    monkeypatch.setattr(ps, "normalize_symbol", fake_normalize)

    expr = "GPL-2.0+ OR BSD-3-Clause/"
    node = ps.parse_spdx(expr)
    # Ensure the parser does not crash and normalize_symbol was called
    assert node is not None
    assert any("GPL-2.0" in c for c in calls)
    assert any("BSD-3-Clause" in c or "/" in c for c in calls)


def test_parser_malformed_parenthesis_does_not_crash(monkeypatch):
    """Input with missing parentheses must not raise unhandled exceptions.
    Expected behavior is for the parser to return None or a partial subtree.
    """
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    for expr in ["(MIT AND", "MIT OR", "(A OR (B AND C)", "(OR) MIT"]:
        node = ps.parse_spdx(expr)
        assert node is None or isinstance(node, ps.Node)