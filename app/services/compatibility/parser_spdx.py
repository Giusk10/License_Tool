"""
Modulo `parser_spdx` — parser semplice per espressioni SPDX.

Supporta un sotto-insieme delle espressioni SPDX utile per l'applicazione:
- operatori logici: AND, OR (AND ha priorità su OR)
- parentesi per raggruppamento
- costrutto speciale WITH (es. "GPL-2.0-or-later WITH Autoconf-exception-generic")

Il parser non è un parser completo SPDX ma è sufficiente per le espressioni prodotte
da ScanCode + LLM in questo progetto. Restituisce un albero di nodi (Leaf/And/Or)
che può essere percorso da `evaluator.eval_node`.
"""

from typing import List, Optional
from .compat_utils import normalize_symbol

class Node:
    pass

class Leaf(Node):
    def __init__(self, value: str):
        # Il value è normalizzato per comodità (es. + -> -or-later, WITH uppercase)
        self.value = normalize_symbol(value)
    def __repr__(self):
        return f"Leaf({self.value})"

class And(Node):
    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right
    def __repr__(self):
        return f"And({self.left}, {self.right})"

class Or(Node):
    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right
    def __repr__(self):
        return f"Or({self.left}, {self.right})"


def _tokenize(expr: str) -> List[str]:
    """
    Tokenizza l'espressione in parole e parentesi, combinando eventuale costrutto "WITH"
    in un singolo token "<ID> WITH <ID>" per semplificare il parser.
    """
    if not expr:
        return []
    s = expr.strip()
    tokens: List[str] = []
    buf = []
    i = 0
    while i < len(s):
        ch = s[i]
        assert isinstance(ch, str) and len(ch) == 1
        if ch in "()":
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(ch)
            i += 1
        elif ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    if buf:
        tokens.append("".join(buf))

    # Combina token in cui appare il costrutto WITH in un singolo token per leaf
    out: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if i + 2 < len(tokens) and tokens[i + 1].upper() == "WITH":
            out.append(f"{t} WITH {tokens[i + 2]}")
            i += 3
        else:
            out.append(t)
            i += 1
    return out


def parse_spdx(expr: str) -> Optional[Node]:
    """
    Esegue il parsing ricorsivo con la precedenza AND > OR e supporto per le parentesi.

    Restituisce None per espressione vuota o un Node (Leaf/And/Or).
    """
    tokens = _tokenize(expr)
    if not tokens:
        return None
    idx = 0
    def peek() -> Optional[str]:
        nonlocal idx
        return tokens[idx] if idx < len(tokens) else None
    def consume() -> Optional[str]:
        nonlocal idx
        t = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return t
    def parse_primary() -> Optional[Node]:
        t = peek()
        if t is None:
            return None
        if t == "(":
            consume()
            node = parse_or()
            if peek() == ")":
                consume()
            return node
        val = consume()
        return Leaf(val)
    def parse_and() -> Optional[Node]:
        left = parse_primary()
        while True:
            t = peek()
            if t is not None and t.upper() == "AND":
                consume()
                right = parse_primary()
                left = And(left, right)
            else:
                break
        return left
    def parse_or() -> Optional[Node]:
        left = parse_and()
        while True:
            t = peek()
            if t is not None and t.upper() == "OR":
                consume()
                right = parse_and()
                left = Or(left, right)
            else:
                break
        return left
    return parse_or()
