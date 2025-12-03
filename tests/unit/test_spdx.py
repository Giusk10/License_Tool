# TESTA parser_spdx.py ed evaluator.py

import pytest
from app.services.compatibility.parser_spdx import parse_spdx
from app.services.compatibility.evaluator import eval_node

# Test del Parser
def parse_simple_license():
    result = parse_spdx("MIT")
    # il parser restituisce un nodo; assicuriamoci che la rappresentazione contenga l'id della licenza
    assert "MIT" in repr(result)

def parse_complex_expression():
    expr = "MIT OR Apache-2.0"
    result = parse_spdx(expr)
    # verifico che sia un nodo OR con i due rami contenenti le licenze
    assert result.__class__.__name__ == "Or"
    assert "MIT" in repr(result.left)
    assert "Apache" in repr(result.right)

def parse_parenthesis():
    expr = "(MIT AND GPL-3.0)"
    result = parse_spdx(expr)
    assert result.__class__.__name__ == "And"
    assert "MIT" in repr(result.left)
    assert "GPL-3.0" in repr(result.right)

# Test dell'Evaluator (Logica di confronto)
def eval_simple_compatibility(mock_matrix_data):
    from unittest.mock import patch
    # patch della matrice e passaggio di nodi parsati a eval_node
    with patch("app.services.compatibility.matrix.get_matrix", return_value=mock_matrix_data):
        left = parse_spdx("MIT")
        right = parse_spdx("MIT")
        status, trace = eval_node(left, right)
        assert status == "yes"