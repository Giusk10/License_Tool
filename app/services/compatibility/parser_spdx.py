"""
This module implements a lightweight parser for a subset of SPDX expressions
relevant to this project.
It constructs an Abstract Syntax Tree (AST) composed of Leaf, And, and Or nodes.

Supported syntax:
- Logical operators: AND, OR (AND has higher precedence).
- Grouping: Parentheses `()`.
- Special construct: WITH (e.g., 'GPL-2.0-or-later WITH Classpath-exception').
  Note: 'WITH' clauses are collapsed into the Leaf node for simplified evaluation.
"""

from typing import List, Optional
from .compat_utils import normalize_symbol

class Node:
    pass

class Leaf(Node):
    """
    Leaf node that represents a single license symbol, possibly with a WITH clause.
    """
    def __init__(self, value: str):
        # The value is normalized for convenience
        self.value = normalize_symbol(value)
    def __repr__(self):
        return f"Leaf({self.value})"

class And(Node):
    """
    And node representing a logical AND operation between two nodes.
    """
    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right
    def __repr__(self):
        return f"And({self.left}, {self.right})"

class Or(Node):
    """
    Or node representing a logical OR operation between two nodes.
    """
    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right
    def __repr__(self):
        return f"Or({self.left}, {self.right})"


def _tokenize(expr: str) -> List[str]:
    """
    Tokenizes the expression into words and parentheses, combining any "WITH" construct
    into a single token "<ID> WITH <ID>" to simplify parsing.
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

    # Combines "WITH" constructs into single tokens
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
    Recursively parses the SPDX expression with AND > OR precedence and support for parentheses.

    Returns None for empty expressions or a Node (Leaf/And/Or).
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
