"""
Modulo `parser_spdx` — parser semplice per espressioni SPDX.

Supporta:
- operatori logici: AND, OR (AND ha priorità su OR; case-insensitive)
- parentesi per raggruppamento: (...)
- costrutto WITH: combinato in un unico token "<ID> WITH <ID>"

Comportamento:
- Restituisce `None` per stringhe vuote o composte solo da spazi.
- Restituisce un albero di nodi (`Leaf`, `And`, `Or`) per espressioni valide.
- Per input malformati il parser tenta di recuperare senza sollevare eccezioni non gestite
  (può restituire `None` o un sotto-albero parziale); definire test espliciti per il comportamento atteso.
- `Leaf` chiama `normalize_symbol(value)`; nei test mockare `normalize_symbol` nel modulo `parser_spdx`.
"""

from app.services.compatibility import parser_spdx as ps


def test_parse_empty_returns_none():
    """Espressione vuota deve tornare None."""
    assert ps.parse_spdx("") is None
    assert ps.parse_spdx("   ") is None


def test_parse_simple_license_creates_leaf(monkeypatch):
    """Un token semplice deve diventare un Leaf e chiamare normalize_symbol."""
    # mock della normalize_symbol per verificare che venga usata
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s.upper())

    node = ps.parse_spdx("mit")
    assert isinstance(node, ps.Leaf)
    assert node.value == "MIT"


def test_parse_with_operator_precedence(monkeypatch):
    """AND ha priorità rispetto a OR.

    'A OR B AND C' deve essere parsato come Or(Leaf(A), And(Leaf(B), Leaf(C))).
    """
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    expr = "MIT OR Apache-2.0 AND GPL-3.0"
    root = ps.parse_spdx(expr)

    # root deve essere Or
    assert isinstance(root, ps.Or)
    # left child MIT
    assert isinstance(root.left, ps.Leaf) and root.left.value == "MIT"
    # right child è And(Apache, GPL)
    assert isinstance(root.right, ps.And)
    assert isinstance(root.right.left, ps.Leaf) and root.right.left.value == "Apache-2.0"
    assert isinstance(root.right.right, ps.Leaf) and root.right.right.value == "GPL-3.0"

def test_parse_parentheses_override_precedence(monkeypatch):
    """Le parentesi devono forzare la precedenza: (A AND B) -> And al top."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    root = ps.parse_spdx("(MIT AND GPL-3.0)")
    assert isinstance(root, ps.And)
    assert isinstance(root.left, ps.Leaf) and root.left.value == "MIT"
    assert isinstance(root.right, ps.Leaf) and root.right.value == "GPL-3.0"


def test_parse_with_combines_with_token(monkeypatch):
    """Il costrutto WITH deve essere combinato in un singolo Leaf token.

    Es: 'GPL-2.0 WITH Autoconf-exception-generic' -> Leaf con valore combinato.
    """
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)

    expr = "GPL-2.0 WITH Autoconf-exception-generic"
    node = ps.parse_spdx(expr)
    assert isinstance(node, ps.Leaf)
    # il token mantiene la forma combinata 'GPL-2.0 WITH Autoconf-exception-generic'
    assert "WITH" in node.value and node.value.startswith("GPL-2.0")

def test_parser_handles_multiple_spaces_and_tabs(monkeypatch):
    """Verifica che il parser ignori spazi multipli e tabulazioni tra i token."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    root = ps.parse_spdx("MIT    OR\tGPL-3.0")
    assert isinstance(root, ps.Or)
    assert isinstance(root.left, ps.Leaf) and root.left.value == "MIT"
    assert isinstance(root.right, ps.Leaf) and root.right.value == "GPL-3.0"


def test_parser_parses_deeply_nested_parentheses(monkeypatch):
    """Verifica il parsing corretto di espressioni con parentesi annidate."""
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
    """Verifica che il token 'WITH' venga riconosciuto anche con spazi extra e case diversi."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    node = ps.parse_spdx("mit  with   Exception")
    assert isinstance(node, ps.Leaf)
    assert "WITH" in node.value and node.value.startswith("mit")


def test_parser_handles_malformed_input_gracefully(monkeypatch):
    """Assicura che input malformati non sollevino eccezioni non gestite; accetta None o Node parziale."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    malformed = ["(MIT AND", "MIT OR", "AND MIT", "MIT WITH"]
    for expr in malformed:
        node = ps.parse_spdx(expr)
        assert node is None or isinstance(node, ps.Node)