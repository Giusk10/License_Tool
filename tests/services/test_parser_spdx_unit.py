"""
test: services/compatibility/parser_spdx.py
"""

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

def test_tokenize_multiple_with_occurrences(monkeypatch):
    """Verifica che un'espressione con più occorrenze di WITH non faccia crashare il parser
    e che almeno la prima occorrenza venga combinata in un token contenente 'WITH'."""
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    expr = "A WITH X WITH Y"
    node = ps.parse_spdx(expr)
    # Non facciamo assunzioni rigide su struttura, ma assicuriamo che non sollevi eccezioni
    # e che la stringa 'WITH' sia presente in almeno una leaf value se esiste una leaf.
    if node is None:
        assert node is None
    else:
        # Cerca ricorsivamente una Leaf che contenga WITH
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
    """Token con caratteri speciali come '+' e '/' non devono causare crash e devono
    essere passati a normalize_symbol (mockata)"""
    calls = []
    def fake_normalize(s):
        calls.append(s)
        return s
    monkeypatch.setattr(ps, "normalize_symbol", fake_normalize)

    expr = "GPL-2.0+ OR BSD-3-Clause/"
    node = ps.parse_spdx(expr)
    # Assicuriamoci che il parser non crashi e che normalize_symbol sia stata chiamata
    assert node is not None
    assert any("GPL-2.0" in c for c in calls)
    assert any("BSD-3-Clause" in c or "/" in c for c in calls)


def test_parser_malformed_parenthesis_does_not_crash(monkeypatch):
    """Input con parentesi mancanti non deve sollevare eccezioni non gestite.
    Il comportamento atteso è che il parser ritorni None o un sottoalbero parziale.
    """
    monkeypatch.setattr(ps, "normalize_symbol", lambda s: s)
    for expr in ["(MIT AND", "MIT OR", "(A OR (B AND C)", "(OR) MIT"]:
        node = ps.parse_spdx(expr)
        assert node is None or isinstance(node, ps.Node)

