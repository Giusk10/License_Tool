"""
License Suggestion Module.

Questo modulo orchestra la generazione di suggerimenti basati su AI per risolvere
conflitti di compatibilità delle licenze. Si interfaccia con l'LLM per:
1. Suggerire licenze alternative compatibili per i file di codice.
2. Rivedere file di documentazione o avvisi per raccomandare azioni di conformità.
"""

import os
import re
import logging
from typing import List, Dict, Optional

from app.services.llm.ollama_api import call_ollama_deepseek
from app.utility.config import CLONE_BASE_DIR

logger = logging.getLogger(__name__)

# Estensioni e nomi dei file considerati come documentazione/avvisi
DOCUMENT_EXTENSIONS = ('.md', '.txt', '.rst', 'THIRD-PARTY-NOTICE', 'NOTICE')


def ask_llm_for_suggestions(issue: Dict[str, str], main_spdx: str) -> str:
    """
    Interroga l'LLM per un elenco di licenze alternative compatibili con il progetto.

    Args:
        issue (Dict[str, str]): Il dizionario del problema contenente 'file_path',
            'detected_license' e 'reason'.
        main_spdx (str): L'identificatore della licenza principale del progetto.

    Returns:
        str: Una stringa separata da virgole di licenze raccomandate (es. "MIT, Apache-2.0").
    """
    prompt = (
        f"You are a software license expert. A file in the project has a license conflict.\n"
        f"The file '{issue['file_path']}' is released under the license "
        f"'{issue['detected_license']}', which is incompatible with the license {main_spdx}.\n"
        f"Reason for the conflict: {issue['reason']}\n\n"
        f"Provide **ONLY** alternative licenses compatible with the license {main_spdx} "
        f"that could be adopted to resolve the conflict. "
        f"**DO NOT** provide analysis, explanations, headers, or additional text. "
        f"Respond exactly in the following format: 'License1, License2, License3'"
    )

    suggestion = call_ollama_deepseek(prompt)
    return suggestion


def review_document(issue: Dict[str, str], main_spdx: str, licenses: str) -> Optional[str]:
    """
    Rivede un file di documentazione per suggerire la gestione delle menzioni di licenza.

    Legge il contenuto del file e chiede all'LLM un consiglio pragmatico (es.
    "Richiedi dual-licensing", "Aggiorna l'avviso").

    Args:
        issue (Dict[str, str]): Il dizionario del problema contenente 'file_path' e 'detected_license'.
        main_spdx (str): La licenza principale del progetto.
        licenses (str): Un elenco di licenze alternative identificate in precedenza (opzionale).

    Returns:
        Optional[str]: Il consiglio operativo estratto dalla risposta dell'LLM,
        o None se la lettura fallisce o non viene trovato alcun consiglio.
    """
    file_path = issue["file_path"]
    abs_path = os.path.join(CLONE_BASE_DIR, file_path)

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            document_content = f.read()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Error reading documentation file %s", file_path)
        return None

    logger.info("Reviewing document: %s", file_path)

    prompt = (
        "### ROLE\n"
        "Act as a Senior Open Source Compliance Officer.\n\n"
        "### DATA\n"
        f"1. Detected License (Incompatible): '{issue['detected_license']}'\n"
        f"2. Project License (Target): '{main_spdx}'\n"
        f"3. Accepted Alternative Licenses: {licenses}\n"
        f"4. Content/Snippet under review:\n'''\n{document_content}\n'''\n\n"
        "### OBJECTIVE\n"
        "Analyze the legal conflict and provide a strategic recommendation to resolve it.\n\n"
        "### INSTRUCTIONS\n"
        "1. DO NOT rewrite the code or the document text.\n"
        "2. Briefly explain the necessary action to resolve the incompatibility "
        "(e.g., 'Request dual-licensing from the author', 'Isolate the component', "
        "'Release under X license instead of Y').\n"
        "3. Be direct and pragmatic.\n\n"
        "### OUTPUT FORMAT (MANDATORY)\n"
        "Your response must STRICTLY follow this format, without markdown (```) "
        "and without any additional text:\n"
        "<advice>Your operational suggestion here.</advice>"
    )

    try:
        response = call_ollama_deepseek(prompt)
        if not response:
            return None

        # Estrae il contenuto all'interno dei tag <advice>
        match = re.search(r"<advice>(.*?)</advice>", response, re.DOTALL | re.IGNORECASE)

        if match:
            return match.group(1).strip()

        # Fallback se il modello ignora i tag
        logger.warning(
            "Warning: <advice> tag format not found in response for %s", file_path
        )
        return None

    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Error during LLM call for document review")
        return None


def enrich_with_llm_suggestions(
        main_spdx: str,
        issues: List[Dict],
        regenerated_map: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """
    Arricchisce l'elenco dei problemi con suggerimenti generati dall'AI e licenze alternative.

    Per ogni problema:
    - Se compatibile: Aggiunge un messaggio "Nessuna azione necessaria".
    - Se incompatibile (Codice): Interroga l'LLM per licenze alternative.
    - Se incompatibile (Documenti): Rivede il documento per un consiglio specifico.

    Args:
        main_spdx (str): La licenza principale del progetto.
        issues (List[Dict]): L'elenco dei dizionari di problemi grezzi.
        regenerated_map (Optional[Dict[str, str]]): Una mappa dei percorsi dei file ai
            percorsi del codice rigenerato (se presenti).

    Returns:
        List[Dict]: L'elenco dei problemi arricchiti con i campi 'suggestion', 'licenses',
        e 'regenerated_code_path'.
    """
    if regenerated_map is None:
        regenerated_map = {}

    enriched = []

    for issue in issues:
        file_path = issue["file_path"]
        detected_license = issue["detected_license"]

        # Reset licenses string for each issue to avoid scope leaking
        licenses_list_str = ""

        # Standard suggestion templates
        sugg_change_license = (
            f"1§ Consider changing the project's main license to adopt "
            f"the license '{detected_license}' (or a compatible one) to resolve the conflict."
        )
        sugg_find_alternative = (
            f"2§ Look for an alternative component or a different library that implements "
            f"the logic of '{file_path}' but is released under a license compatible with "
            f"the project's current license."
        )

        suggestion_text = ""

        # Caso 1: Il file è compatibile
        if issue.get("compatible"):
            suggestion_text = (
                "The file is compatible with the project's main license. No action needed."
            )

        elif issue.get("compatible") is None:
            # Gestisce stati "condizionali" o sconosciuti codificati nel testo del motivo
            reason_text = issue.get("reason", "")
            if "Outcome: conditional" in reason_text or "Outcome: unknown" in reason_text:
                # User requested this specific suggestion for conditional/unknown outcomes
                suggestion_text = "License unavailable in Matrix for check compatibility."
            else:
                suggestion_text = (
                    "The repository main license could not be determined, please click on the toggle 'Get Suggestion' to choose a main license."
                )

        # Caso 2: File Incompatibile
        else:
            is_document = file_path.endswith(DOCUMENT_EXTENSIONS)

            if not is_document:
                # È un file di codice: chiedi licenze alternative
                licenses_list_str = ask_llm_for_suggestions(issue, main_spdx)

                suggestion_text = (
                    f"{sugg_change_license}\n"
                    f"{sugg_find_alternative}\n"
                    f"3§ Here are some alternative compatible licenses you might consider: "
                    f"{licenses_list_str}"
                )
            else:
                # Passiamo una stringa di licenze vuota qui poiché non abbiamo chiesto alternative
                # per questo file specifico
                doc_advice = review_document(issue, main_spdx, licenses_list_str)

                # If review returns None, fallback to generic suggestion, otherwise append advice
                advice_part = doc_advice if doc_advice else "Check document manually."

                suggestion_text = (
                    f"{sugg_change_license}\n"
                    f"{sugg_find_alternative}\n"
                    f"3§ {advice_part}"
                )

        # Costruisce il dizionario arricchito finale
        enriched.append({
            "file_path": file_path,
            "detected_license": detected_license,
            "compatible": issue["compatible"],
            "reason": issue["reason"],
            "suggestion": suggestion_text,
            "licenses": licenses_list_str,
            "regenerated_code_path": regenerated_map.get(file_path),
        })

    return enriched
