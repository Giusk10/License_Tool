"""
License Ranking Module.

This module provides functionality to select the most permissive license
from a set of licenses detected in a file, based on a predefined ranking configuration.
It helps in resolving multi-license scenarios (e.g., OR clauses) by defaulting to
the option that offers the most freedom.
"""

import json
import os
import re
from typing import Dict


def choose_most_permissive_license_in_file(licenses: Dict[str, str]) -> Dict[str, str]:
    """
    Sceglie la licenza più permissiva da una lista di licenze per ogni file.
    Questa è una funzione segnaposto e dovrebbe essere implementata in base a criteri
    specifici di permissività.

    Args:
        licenses (Dict[str, str]): Un dizionario che mappa i percorsi dei file alla loro espressione SPDX rilevata.
    Returns:
        Dict[str, str]: Un dizionario che mappa i percorsi dei file all'espressione SPDX della licenza più permissiva
    """

    for file_path, license_expr in licenses.items():
        if license_expr.count('AND') > 0 or license_expr.count('OR') > 0:
            extracted_licenses = estract_licenses(license_expr)
            rank_rules = load_json_rank()
            order_map = {lic: idx for idx, lic in enumerate(rank_rules.get("license_order_permissive", []))}
            ranked_licenses = sorted(extracted_licenses, key=lambda x: order_map.get(x, float('inf')))

            licenses[file_path] = ranked_licenses[0]

    return licenses

def estract_licenses(spdx_license: str) -> list[str]:
    """
    Estrae tutte le licenze da una espressione SPDX complessa (con AND/OR e parentesi).
    Restituisce una lista di licenze trovate al livello più alto dell'espressione.
    """
    s = spdx_license or ''
    results: list[str] = []
    curr: list[str] = []
    depth = 0
    i = 0

    while i < len(s):
        # Cerchiamo il pattern " OR " (solo maiuscolo e con spazi ai lati)
        # Usiamo un lookahead per non consumare caratteri inutilmente
        match_or = re.match(r' +OR +', s[i:])

        if s[i] == '(':
            depth += 1
            curr.append(s[i])
            i += 1
        elif s[i] == ')':
            depth = max(depth - 1, 0)
            curr.append(s[i])
            i += 1
        elif match_or and depth == 0:
            # Trovato " OR " al livello zero: dividiamo
            part = ''.join(curr).strip()
            if part:
                results.append(part)
            curr = []
            i += match_or.end()
        else:
            curr.append(s[i])
            i += 1

    last = ''.join(curr).strip()
    if last:
        results.append(last)
    return results

def load_json_rank() -> dict:
    """
    Carica il file JSON che contiene l'ordine di permissività delle licenze.
    """
    rules_path = os.path.join(os.path.dirname(__file__), 'license_order_permissive.json')
    if not os.path.exists(rules_path):
        raise FileNotFoundError(f"Unable to find the rules file: {rules_path}")

    with open(rules_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    return rules
