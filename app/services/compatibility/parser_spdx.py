"""
SPDX Expression Parser.

This module implements a lightweight recursive descent parser for a subset of
SPDX license expressions relevant to this project. It constructs an
Abstract Syntax Tree (AST) composed of Leaf, And, and Or nodes.

Supported Syntax:
- Logical Operators: AND, OR (AND has higher precedence).
- Grouping: Parentheses `(...)`.
- Exception Clauses: WITH (e.g., 'GPL-2.0-or-later WITH Classpath-exception').

Note:
    'WITH' clauses are collapsed into the `Leaf` node during tokenization
    to simplify the evaluation logic.
"""

from typing import List, Optional
from .compat_utils import normalize_symbol


class Node:  # pylint: disable=too-few-public-methods
    """
    Abstract base class representing a generic node in the SPDX expression AST.
    """


class Leaf(Node):  # pylint: disable=too-few-public-methods
    """
    Leaf node representing a single license symbol, potentially including a WITH clause.

    Attributes:
        value (str): The normalized license string (e.g., "MIT" or "GPL-2.0 WITH Exception").
    """

    def __init__(self, value: str):
        # The value is normalized immediately upon creation
        self.value = normalize_symbol(value)

    def __repr__(self) -> str:
        return f"Leaf({self.value})"


class And(Node):  # pylint: disable=too-few-public-methods
    """
    Node representing a logical AND operation between two sub-expressions.

    Attributes:
        left (Node): The left operand.
        right (Node): The right operand.
    """

    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"And({self.left}, {self.right})"


class Or(Node):  # pylint: disable=too-few-public-methods
    """
    Node representing a logical OR operation between two sub-expressions.

    Attributes:
        left (Node): The left operand.
        right (Node): The right operand.
    """

    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"Or({self.left}, {self.right})"


def _tokenize(expr: str) -> List[str]:
    """
    Tokenizes the expression into symbols, operators, and parentheses.

    It performs two passes:
    1. Splits the string by whitespace and parentheses.
    2. Merges "WITH" constructs into a single token (e.g., "A", "WITH", "B" -> "A WITH B").

    Args:
        expr (str): The raw SPDX expression string.

    Returns:
        List[str]: A list of clean tokens.
    """
    if not expr:
        return []

    s = expr.strip()
    tokens: List[str] = []
    buf: List[str] = []
    i = 0

    # Pass 1: Basic lexing
    while i < len(s):
        ch = s[i]

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

    # Pass 2: Merge "WITH" clauses
    # Converts ["GPL", "WITH", "Exc"] into ["GPL WITH Exc"]
    out: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        # Check if the next token is WITH and there is a token after that
        if i + 2 < len(tokens) and tokens[i + 1].upper() == "WITH":
            out.append(f"{t} WITH {tokens[i + 2]}")
            i += 3
        else:
            out.append(t)
            i += 1

    return out


def parse_spdx(expr: str) -> Optional[Node]:
    """
    Recursively parses an SPDX expression string into an AST.

    Implements operator precedence:
    1. Parentheses `()`
    2. AND
    3. OR

    Args:
        expr (str): The SPDX expression to parse.

    Returns:
        Optional[Node]: The root node of the AST, or None if the expression is empty/invalid.
    """
    tokens = _tokenize(expr)
    if not tokens:
        return None

    idx = 0

    # --- Inner Helper Functions (Closure) ---

    def peek() -> Optional[str]:
        """Returns the current token without consuming it."""
        nonlocal idx
        return tokens[idx] if idx < len(tokens) else None

    def consume() -> Optional[str]:
        """Returns the current token and advances the pointer."""
        nonlocal idx
        t = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return t

    def parse_primary() -> Optional[Node]:
        """Parses a primary expression: a Leaf or a parenthesized sub-expression."""
        t = peek()
        if t is None:
            return None

        if t == "(":
            consume()  # eat '('
            node = parse_or()
            if peek() == ")":
                consume()  # eat ')'
            return node

        # It's a license symbol (Leaf)
        val = consume()
        if val:
            return Leaf(val)
        return None

    def parse_and() -> Optional[Node]:
        """Parses 'AND' sequences (higher precedence than OR)."""
        left = parse_primary()
        while True:
            t = peek()
            if t is not None and t.upper() == "AND":
                consume()  # eat 'AND'
                right = parse_primary()
                if left and right:
                    left = And(left, right)
            else:
                break
        return left

    def parse_or() -> Optional[Node]:
        """Parses 'OR' sequences (lowest precedence)."""
        left = parse_and()
        while True:
            t = peek()
            if t is not None and t.upper() == "OR":
                consume()  # eat 'OR'
                right = parse_and()
                if left and right:
                    left = Or(left, right)
            else:
                break
        return left

    # --- End Helpers ---

    return parse_or()
