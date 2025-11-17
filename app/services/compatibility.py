from typing import Dict, List, Optional, Tuple
import os
import json
from license_expression import Licensing


licensing = Licensing()

# Percorso della matrice estesa in JSON (sottinsieme ispirato a OSADL)
_OSADL_MATRIX_PATH = os.path.join(os.path.dirname(__file__), "osadl_matrix.json")

# Fallback minimale (compatibilità binaria) usato se il JSON non è disponibile.
_FALLBACK_BINARY_MATRIX = {
    "MIT": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "Apache-2.0": ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"],
    "BSD-3-Clause": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "BSD-2-Clause": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"],
    "GPL-3.0-only": ["GPL-3.0-only", "GPL-3.0-or-later"],
    "GPL-3.0-or-later": ["GPL-3.0-only", "GPL-3.0-or-later"],
}

# Alias/sinonimi comuni -> forma canonica usata nella matrice
_SYNONYMS = {
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-2.0+": "GPL-2.0-or-later",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
}


def _normalize_symbol(sym: str) -> str:
    if not sym:
        return sym
    s = sym.strip()
    # normalizza spazi multipli attorno a WITH
    if " with " in s:
        s = s.replace(" with ", " WITH ")
    if " With " in s:
        s = s.replace(" With ", " WITH ")
    if " with" in s and " WITH" not in s:
        s = s.replace(" with", " WITH")
    if "+" in s and "-or-later" not in s:
        # esempio: GPL-3.0+ -> GPL-3.0-or-later
        s = s.replace("+", "-or-later")
    # applica alias precisi
    return _SYNONYMS.get(s, s)


def _load_osadl_matrix() -> Dict[str, Dict[str, str]]:
    """
    Carica la matrice stile OSADL da JSON e restituisce un dict:
      { main_spdx: { dep_spdx: "yes"|"no"|"conditional" } }

    Se il file non è presente o invalido, ritorna una conversione del
    fallback binario in tri-stato (yes per le voci consentite, no per il resto).
    """
    try:
        if os.path.exists(_OSADL_MATRIX_PATH):
            with open(_OSADL_MATRIX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            matrix = data.get("matrix")
            if isinstance(matrix, dict) and matrix:
                # normalizza chiavi come stringhe precise
                normalized: Dict[str, Dict[str, str]] = {}
                for main, row in matrix.items():
                    if not isinstance(row, dict):
                        continue
                    main_n = _normalize_symbol(main)
                    normalized[main_n] = {}
                    for k, v in row.items():
                        if v in {"yes", "no", "conditional"}:
                            normalized[_normalize_symbol(main_n)][_normalize_symbol(k)] = v
                if normalized:
                    return normalized
    except Exception:
        # qualsiasi problema -> si passa al fallback
        pass

    # Costruzione fallback tri-stato: yes per consentite, no per altre conosciute nelle chiavi
    mains = set(_FALLBACK_BINARY_MATRIX.keys())
    all_syms = set()
    for allowed in _FALLBACK_BINARY_MATRIX.values():
        all_syms.update(allowed)
    all_syms.update(mains)

    fallback_tristate: Dict[str, Dict[str, str]] = {}
    for main, allowed in _FALLBACK_BINARY_MATRIX.items():
        row: Dict[str, str] = {}
        allowed_set = set(allowed)
        for sym in all_syms:
            row[_normalize_symbol(sym)] = "yes" if sym in allowed_set else "no"
        fallback_tristate[_normalize_symbol(main)] = row
    return fallback_tristate


# Carica una sola volta
_OSADL_MATRIX = _load_osadl_matrix()


# ---------------------- Parser SPDX semplice (AND/OR/WITH) ----------------------
class _Node:
    pass


class _Leaf(_Node):
    def __init__(self, value: str):
        # value è un identificatore SPDX oppure "X WITH Y"
        self.value = _normalize_symbol(value)

    def __repr__(self):
        return f"Leaf({self.value})"


class _And(_Node):
    def __init__(self, left: _Node, right: _Node):
        self.left = left
        self.right = right

    def __repr__(self):
        return f"And({self.left}, {self.right})"


class _Or(_Node):
    def __init__(self, left: _Node, right: _Node):
        self.left = left
        self.right = right

    def __repr__(self):
        return f"Or({self.left}, {self.right})"


def _tokenize(expr: str) -> List[str]:
    if not expr:
        return []
    s = expr.strip()
    tokens: List[str] = []
    buf = []
    i = 0
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

    # Unire il costrutto WITH in un unico token: "<ID> WITH <ID>"
    out: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if i + 2 < len(tokens) and tokens[i + 1].upper() == "WITH":
            # combina
            out.append(f"{t} WITH {tokens[i + 2]}")
            i += 3
        else:
            out.append(t)
            i += 1
    return out


def _parse_spdx(expr: str) -> Optional[_Node]:
    """
    Parser ricorsivo con precedenza: AND > OR.
    Supporta parentesi e token "WITH" aggregati al leaf.
    """
    tokens = _tokenize(expr)
    if not tokens:
        return None

    # parser con indice interno
    idx = 0

    def peek() -> Optional[str]:
        nonlocal idx
        return tokens[idx] if idx < len(tokens) else None

    def consume() -> Optional[str]:
        nonlocal idx
        t = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return t

    def parse_primary() -> Optional[_Node]:
        t = peek()
        if t is None:
            return None
        if t == "(":
            consume()
            node = parse_or()
            if peek() == ")":
                consume()
            return node
        # altrimenti è un leaf (già con WITH aggregato se presente)
        val = consume()
        return _Leaf(val)

    def parse_and() -> Optional[_Node]:
        left = parse_primary()
        while True:
            t = peek()
            if t is not None and t.upper() == "AND":
                consume()
                right = parse_primary()
                left = _And(left, right)
            else:
                break
        return left

    def parse_or() -> Optional[_Node]:
        left = parse_and()
        while True:
            t = peek()
            if t is not None and t.upper() == "OR":
                consume()
                right = parse_and()
                left = _Or(left, right)
            else:
                break
        return left

    root = parse_or()
    return root


# ---------------------- Valutazione tri-stato contro matrice ----------------------
Tri = str  # alias semantico: "yes" | "no" | "conditional" | "unknown"


def _lookup_status(main_license: str, dep_license: str) -> Tri:
    row = _OSADL_MATRIX.get(main_license)
    if not row:
        return "unknown"
    # tentativi di lookup con varie normalizzazioni
    candidates = [dep_license, _normalize_symbol(dep_license), dep_license.strip()]
    for c in candidates:
        status = row.get(c)
        if status in {"yes", "no", "conditional"}:
            return status
    return "unknown"


def _combine_and(a: Tri, b: Tri) -> Tri:
    # Tavola verità conservativa
    if a == "no" or b == "no":
        return "no"
    if a == "yes" and b == "yes":
        return "yes"
    # tutto il resto (conditional/unknown con yes/conditional/unknown) -> conditional
    return "conditional"


def _combine_or(a: Tri, b: Tri) -> Tri:
    if a == "yes" or b == "yes":
        return "yes"
    if a == "no" and b == "no":
        return "no"
    # almeno uno è conditional/unknown e nessuno yes -> conditional
    return "conditional"


def _eval_node(main_license: str, node: Optional[_Node]) -> Tuple[Tri, List[str]]:
    """
    Valuta ricorsivamente l'espressione e ritorna:
      (stato, traccia_spiegazioni)
    """
    if node is None:
        return "unknown", ["Espressione mancante o non riconosciuta"]

    if isinstance(node, _Leaf):
        status = _lookup_status(main_license, node.value)
        reason = f"{node.value} → {status} rispetto a {main_license}"
        return status, [reason]

    if isinstance(node, _And):
        ls, ltrace = _eval_node(main_license, node.left)
        rs, rtrace = _eval_node(main_license, node.right)
        combined = _combine_and(ls, rs)
        return combined, ltrace + rtrace + [f"AND ⇒ {combined}"]

    if isinstance(node, _Or):
        ls, ltrace = _eval_node(main_license, node.left)
        rs, rtrace = _eval_node(main_license, node.right)
        combined = _combine_or(ls, rs)
        return combined, ltrace + rtrace + [f"OR ⇒ {combined}"]

    return "unknown", ["Nodo non riconosciuto"]


def _extract_symbols(expr: str) -> List[str]:
    """
    Restituisce i singoli identificatori di licenza (senza struttura) da una espressione SPDX.
    Nota: conservata per retrocompatibilità e per motivi di debug; la logica
    principale ora usa il parser tri-stato con struttura.
    """
    if not expr:
        return []

    try:
        tree = licensing.parse(expr, strict=False)
    except Exception:
        return []

    return [str(sym) for sym in getattr(tree, "symbols", [])]


def check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict:
    """
    Calcola la compatibilità tra la licenza principale e le licenze dei singoli file
    usando una matrice estesa (ispirata a OSADL) e valutando correttamente
    le espressioni SPDX con AND/OR/WITH.

    Restituisce:
    {
        "main_license": <spdx>,
        "issues": [
            {
                "file_path": "...",
                "detected_license": "...",
                "compatible": True/False,
                "reason": "..."
            }
        ]
    }
    """

    issues = []

    # normalizza la licenza principale
    main_license_n = _normalize_symbol(main_license)

    # Caso 1: nessuna licenza principale trovata
    if not main_license_n or main_license_n in {"UNKNOWN", "NOASSERTION", "NONE"}:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": "Licenza principale non rilevata o non valida (UNKNOWN/NOASSERTION/NONE)",
            })
        return {
            "main_license": main_license or "UNKNOWN",
            "issues": issues,
        }

    # Verifica se la licenza principale è coperta dalla matrice
    if main_license_n not in _OSADL_MATRIX:
        for file_path, license_expr in file_licenses.items():
            issues.append({
                "file_path": file_path,
                "detected_license": license_expr,
                "compatible": False,
                "reason": f"Licenza principale {main_license_n} non presente nella matrice di compatibilità",
            })
        return {
            "main_license": main_license_n,
            "issues": issues,
        }

    for file_path, license_expr in file_licenses.items():
        license_expr = (license_expr or "").strip()

        node = _parse_spdx(license_expr)
        status, trace = _eval_node(main_license_n, node)

        if status == "yes":
            compatible = True
            reason = "; ".join(trace)
        elif status == "no":
            compatible = False
            reason = "; ".join(trace)
        else:  # conditional o unknown
            compatible = False
            hint = "conditional" if status == "conditional" else "unknown"
            reason = "; ".join(trace) + f"; Esito: {hint}. Richiede verifica di conformità/manuale."

        issues.append({
            "file_path": file_path,
            "detected_license": license_expr,
            "compatible": compatible,
            "reason": reason,
        })

    return {
        "main_license": main_license_n,
        "issues": issues,
    }
