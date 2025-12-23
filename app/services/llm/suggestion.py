"""
License Suggestion Module.

This module orchestrates the generation of AI-driven suggestions for resolving
license compatibility conflicts. It interfaces with the LLM to:
1. Suggest alternative compatible licenses for code files.
2. Review documentation or notice files to recommend compliance actions.
"""

import os
import re
import logging
from typing import List, Dict, Optional

from app.services.llm.ollama_api import call_ollama_deepseek
from app.utility.config import CLONE_BASE_DIR

logger = logging.getLogger(__name__)

# File extensions and names considered as documentation/notices
DOCUMENT_EXTENSIONS = ('.md', '.txt', '.rst', 'THIRD-PARTY-NOTICE', 'NOTICE')


def ask_llm_for_suggestions(issue: Dict[str, str], main_spdx: str) -> str:
    """
    Queries the LLM for a list of alternative licenses compatible with the project.

    Args:
        issue (Dict[str, str]): The issue dictionary containing 'file_path',
            'detected_license', and 'reason'.
        main_spdx (str): The project's main license identifier.

    Returns:
        str: A comma-separated string of recommended licenses (e.g., "MIT, Apache-2.0").
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
    Reviews a documentation file to suggest handling of license mentions.

    It reads the file content and asks the LLM for pragmatic advice (e.g.,
    "Request dual-licensing", "Update notice").

    Args:
        issue (Dict[str, str]): The issue dictionary containing 'file_path' and 'detected_license'.
        main_spdx (str): The project's main license.
        licenses (str): A list of previously identified alternative licenses (optional).

    Returns:
        Optional[str]: The operational advice extracted from the LLM response,
        or None if reading fails or no advice is found.
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

        # Extract content within <advice> tags
        match = re.search(r"<advice>(.*?)</advice>", response, re.DOTALL | re.IGNORECASE)

        if match:
            return match.group(1).strip()

        # Fallback if the model ignores the tags
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
    Enhances the list of issues with AI-generated suggestions and alternative licenses.

    For each issue:
    - If compatible: Adds a "No action needed" message.
    - If incompatible (Code): Queries LLM for alternative licenses.
    - If incompatible (Docs): Reviews the document for specific advice.

    Args:
        main_spdx (str): The project's main license.
        issues (List[Dict]): The list of raw issue dictionaries.
        regenerated_map (Optional[Dict[str, str]]): A map of file paths to
            regenerated code paths (if any).

    Returns:
        List[Dict]: The list of issues enriched with 'suggestion', 'licenses',
        and 'regenerated_code_path' fields.
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

        # Case 1: File is compatible
        if issue.get("compatible"):
            suggestion_text = (
                "The file is compatible with the project's main license. No action needed."
            )

        # Case 2: Incompatible File
        else:
            is_document = file_path.endswith(DOCUMENT_EXTENSIONS)

            if not is_document:
                # It's a code file: ask for alternative licenses
                licenses_list_str = ask_llm_for_suggestions(issue, main_spdx)

                suggestion_text = (
                    f"{sugg_change_license}\n"
                    f"{sugg_find_alternative}\n"
                    f"3§ Here are some alternative compatible licenses you might consider: "
                    f"{licenses_list_str}"
                )
            else:
                # We pass empty licenses string here as we haven't asked for alternatives
                # for this specific file
                doc_advice = review_document(issue, main_spdx, licenses_list_str)

                # If review returns None, fallback to generic suggestion, otherwise append advice
                advice_part = doc_advice if doc_advice else "Check document manually."

                suggestion_text = (
                    f"{sugg_change_license}\n"
                    f"{sugg_find_alternative}\n"
                    f"3§ {advice_part}"
                )

        # Build final enriched dictionary
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
