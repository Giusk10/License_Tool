"""
Parser di Espressioni SPDX.

Questo modulo implementa un parser leggero a discesa ricorsiva per un sottoinsieme di
espressioni di licenza SPDX rilevanti per questo progetto. Costruisce un
Abstract Syntax Tree (AST) composto da nodi Leaf, And e Or.

Sintassi Supportata:
- Operatori Logici: AND, OR (AND ha precedenza maggiore).
- Raggruppamento: Parentesi `(...)`.
- Clausole di Eccezione: WITH (es. 'GPL-2.0-or-later WITH Classpath-exception').

Nota:
    Le clausole 'WITH' vengono collassate nel nodo `Leaf` durante la tokenizzazione
    per semplificare la logica di valutazione.
"""

from typing import List, Optional
from .compat_utils import normalize_symbol


class Node:  # pylint: disable=too-few-public-methods
    """
    Classe base astratta che rappresenta un nodo generico nell'AST dell'espressione SPDX.
    """


class Leaf(Node):  # pylint: disable=too-few-public-methods
    """
    Nodo foglia che rappresenta un singolo simbolo di licenza, potenzialmente includendo una clausola WITH.

    Attributes:
        value (str): La stringa della licenza normalizzata (es. "MIT" o "GPL-2.0 WITH Exception").
    """

    def __init__(self, value: str):
        # Il valore viene normalizzato immediatamente alla creazione
        self.value = normalize_symbol(value)

    def __repr__(self) -> str:
        return f"Leaf({self.value})"


class And(Node):  # pylint: disable=too-few-public-methods
    """
    Nodo che rappresenta un'operazione logica AND tra due sotto-espressioni.

    Attributes:
        left (Node): L'operando sinistro.
        right (Node): L'operando destro.
    """

    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"And({self.left}, {self.right})"


class Or(Node):  # pylint: disable=too-few-public-methods
    """
    Nodo che rappresenta un'operazione logica OR tra due sotto-espressioni.

    Attributes:
        left (Node): L'operando sinistro.
        right (Node): L'operando destro.
    """

    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"Or({self.left}, {self.right})"


def _tokenize(expr: str) -> List[str]:
    """
    Tokenizza l'espressione in simboli, operatori e parentesi.

    Esegue due passaggi:
    1. Divide la stringa per spazi bianchi e parentesi.
    2. Unisce i costrutti "WITH" in un singolo token (es. "A", "WITH", "B" -> "A WITH B").

    Args:
        expr (str): La stringa dell'espressione SPDX grezza.

    Returns:
        List[str]: Un elenco di token puliti.
    """
    if not expr:
        return []

    s = expr.strip()
    tokens: List[str] = []
    buf: List[str] = []
    i = 0

    # Passaggio 1: Lexing di base
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

    # Passaggio 2: Unione delle clausole "WITH"
    # Converte ["GPL", "WITH", "Exc"] in ["GPL WITH Exc"]
    out: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        # Controlla se il prossimo token è WITH e c'è un token dopo di esso
        if i + 2 < len(tokens) and tokens[i + 1].upper() == "WITH":
            out.append(f"{t} WITH {tokens[i + 2]}")
            i += 3
        else:
            out.append(t)
            i += 1

    return out


def parse_spdx(expr: str) -> Optional[Node]:
    """
    Analizza ricorsivamente una stringa di espressione SPDX in un AST.

    Implementa la precedenza degli operatori:
    1. Parentesi `()`
    2. AND
    3. OR

    Args:
        expr (str): L'espressione SPDX da analizzare.

    Returns:
        Optional[Node]: Il nodo radice dell'AST, o None se l'espressione è vuota/non valida.
    """
    tokens = _tokenize(expr)
    if not tokens:
        return None

    idx = 0

    # --- Funzioni Helper Interne (Closure) ---

    def peek() -> Optional[str]:
        """Restituisce il token corrente senza consumarlo."""
        nonlocal idx
        return tokens[idx] if idx < len(tokens) else None

    def consume() -> Optional[str]:
        """Restituisce il token corrente e avanza il puntatore."""
        nonlocal idx
        t = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return t

    def parse_primary() -> Optional[Node]:
        """Analizza un'espressione primaria: una Foglia o una sotto-espressione tra parentesi."""
        t = peek()
        if t is None:
            return None

        if t == "(":
            consume()  # consuma '('
            node = parse_or()
            if peek() == ")":
                consume()  # consuma ')'
            return node

        # È un simbolo di licenza (Foglia)
        val = consume()
        if val:
            return Leaf(val)
        return None

    def parse_and() -> Optional[Node]:
        """Analizza sequenze 'AND' (precedenza maggiore rispetto a OR)."""
        left = parse_primary()
        while True:
            t = peek()
            if t is not None and t.upper() == "AND":
                consume()  # consuma 'AND'
                right = parse_primary()
                if left and right:
                    left = And(left, right)
            else:
                break
        return left

    def parse_or() -> Optional[Node]:
        """Analizza sequenze 'OR' (precedenza più bassa)."""
        left = parse_and()
        while True:
            t = peek()
            if t is not None and t.upper() == "OR":
                consume()  # consuma 'OR'
                right = parse_and()
                if left and right:
                    left = Or(left, right)
            else:
                break
        return left

    # --- Fine Helper ---

    return parse_or()
