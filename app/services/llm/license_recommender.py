"""
License Recommender Module.

This module provides AI-driven license recommendations based on user requirements
and constraints. It's used when no main license is detected.
"""

import json
import logging
from typing import Dict, List

from app.services.llm.ollama_api import call_ollama_deepseek

logger = logging.getLogger(__name__)


def suggest_license_based_on_requirements(
        requirements: Dict[str, any],
        detected_licenses: List[str] = None
) -> Dict[str, any]:

    """
    Suggests an appropriate license based on user-provided requirements.

    This function takes user requirements (commercial use, modification, distribution,
    patent grant, etc.) and asks the LLM to recommend the most suitable license.

    Args:
        requirements (Dict[str, any]): Dictionary containing user requirements:
            - commercial_use (bool): Whether commercial use is required
            - modification (bool): Whether modification is allowed
            - distribution (bool): Whether distribution is allowed
            - patent_grant (bool): Whether patent grant is needed
            - trademark_use (bool): Whether trademark use is needed
            - liability (bool): Whether liability protection is needed
            - copyleft (str): Copyleft preference ("strong", "weak", "none")
            - additional_requirements (str): Any additional free-text requirements

    Returns:
        Dict[str, any]: A dictionary containing:
            - suggested_license (str): The recommended license
            - explanation (str): Explanation of the recommendation
            - alternatives (List[str]): Alternative license options
    """
    # Build the requirements description
    req_parts = []

    if requirements.get("commercial_use"):
        req_parts.append("- Commercial use: REQUIRED")
    else:
        req_parts.append("- Commercial use: NOT required")

    if requirements.get("modification"):
        req_parts.append("- Modification: ALLOWED")
    else:
        req_parts.append("- Modification: NOT allowed")

    if requirements.get("distribution"):
        req_parts.append("- Distribution: ALLOWED")
    else:
        req_parts.append("- Distribution: NOT allowed")

    if requirements.get("patent_grant"):
        req_parts.append("- Patent grant: REQUIRED")

    if requirements.get("trademark_use"):
        req_parts.append("- Trademark use: REQUIRED")

    if requirements.get("liability"):
        req_parts.append("- Liability protection: REQUIRED")

    copyleft = requirements.get("copyleft")
    if copyleft:
        if copyleft == "strong":
            req_parts.append("- Copyleft: STRONG copyleft required (GPL-style)")
        elif copyleft == "weak":
            req_parts.append("- Copyleft: WEAK copyleft preferred (LGPL-style)")
        elif copyleft == "none":
            req_parts.append("- Copyleft: NO copyleft (permissive license preferred)")

    additional = requirements.get("additional_requirements")
    if additional:
        req_parts.append(f"- Additional requirements: {additional}")

    requirements_text = "\n".join(req_parts)

    if detected_licenses:
        detected_text = ", ".join(detected_licenses)
        requirements_text += f"\n\n### EXISTING LICENSES IN PROJECT\n{detected_text}\n\n**IMPORTANT**: The recommended license MUST be compatible with ALL existing licenses listed above. If incompatible, choose an alternative that ensures compatibility."

    prompt = f"""### ROLE
You are an expert in open source software licensing. Your task is to recommend
the most appropriate license for a software project based on the user's requirements.

### USER REQUIREMENTS
{requirements_text}

### TASK
Based on the requirements above, recommend the most suitable open source license.
Consider popular licenses like MIT, Apache-2.0, GPL-3.0, LGPL-3.0, BSD-3-Clause, etc.
If existing licenses are listed in the project, ensure the recommendation is compatible with them.

### OUTPUT FORMAT (MANDATORY)
You MUST respond with a valid JSON object with NO markdown formatting, NO code blocks, NO ```json tags.
Just the raw JSON object in this exact format:

{{
    "suggested_license": "LICENSE-NAME",
    "explanation": "Brief explanation of why this license fits the requirements",
    "alternatives": ["LICENSE-1", "LICENSE-2", "LICENSE-3"]
}}

Respond ONLY with the JSON object, nothing else."""

    response = ""
    try:
        response = call_ollama_deepseek(prompt)

        # Clean up response (remove markdown code blocks if present)
        response = response.strip() if response else ""
        if not response:
            logger.error("LLM response is empty or None.")
            raise ValueError("Empty response from LLM")
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        # Parse JSON response
        result = json.loads(response)

        return {
            "suggested_license": result.get("suggested_license", "MIT"),
            "explanation": result.get("explanation", "Unable to generate explanation"),
            "alternatives": result.get("alternatives", ["Apache-2.0", "BSD-3-Clause"])
        }

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse LLM response as JSON: %s", e)
        logger.debug("Raw response: %s", response)

        # Fallback to MIT as a safe default
        return {
            "suggested_license": "MIT",
            "explanation": "Based on your requirements, MIT License is recommended as it's permissive "
                           "and widely used. It allows commercial use, modification, and distribution "
                           "with minimal restrictions.",
            "alternatives": ["Apache-2.0", "BSD-3-Clause", "ISC"]
        }

    except Exception as e:
        logger.exception("Error during license suggestion: %s", e)

        # Fallback
        return {
            "suggested_license": "MIT",
            "explanation": "An error occurred during analysis. MIT License is suggested as a safe "
                           "default permissive license.",
            "alternatives": ["Apache-2.0", "BSD-3-Clause"]
        }


def needs_license_suggestion(main_license: str, issues: List[Dict]) -> bool:
    """
    Determines if a license suggestion is needed based on analysis results.

    A suggestion is needed when:
    1. No main license was detected (Unknown or None)
    2. There are files with unknown licenses

    Args:
        main_license (str): The detected main license
        issues (List[Dict]): List of license issues

    Returns:
        bool: True if license suggestion should be offered to the user
    """
    # Case 1: No main license detected
    if not main_license or main_license.lower() in ["unknown", "none", "no license"]:
        return True

    # Case 2: Check for unknown licenses in files
    for issue in issues:
        detected = issue.get("detected_license", "").lower()
        if "unknown" in detected or detected in ["none", ""]:
            return False

    return False

