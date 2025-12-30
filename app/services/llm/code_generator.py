"""
LLM Code Generator Module.

This module interacts with the configured LLM (via Ollama) to rewrite source code
that has been flagged as violating license compatibility. It constructs specific
prompts to ensure the generated code is functionally equivalent but compliant
with the target project's license.
"""

import logging
from typing import Optional
from app.services.llm.ollama_api import call_ollama_qwen3_coder

logger = logging.getLogger(__name__)


def regenerate_code(
    code_content: str,
    main_license: str,
    detected_license: str,
    licenses: str
) -> Optional[str]:
    """
    Requests the LLM to regenerate a code block under a compatible license.

    The prompt instructs the model to:
    1. Analyze the original code and its incompatible license.
    2. Rewrite the logic to be functionally equivalent but compliant with the
       `main_license` (preferring permissive licenses like MIT/Apache-2.0).
    3. Ensure no original restricted code (strong copyleft) is verbatim copied
       to avoid licensing issues.

    Args:
        code_content (str): The original source code that violates license compatibility.
        main_license (str): The primary license of the project (e.g., "MIT").
        detected_license (str): The license detected in the original code (e.g., "GPL-3.0").
        licenses (str): A string listing compatible licenses to target.

    Returns:
        Optional[str]: The cleaned, extracted source code string ready to be saved,
        or None if generation fails.
    """
    # Construct the prompt split across multiple lines for readability and PEP8 compliance
    prompt = (
        f"You are a software licensing and refactoring expert. "
        f"The following code is currently under the license '{detected_license}', "
        f"which is incompatible with the project's main license '{main_license}'.\n"
        f"Your task is to find a component that is functionally equivalent but "
        f"can be released under a license compatible with '{main_license}' among these: "
        f"{licenses}.\n"
        f"If the component does not exist, regenerate it from scratch while maintaining "
        f"the same functionality but ensuring it is under a license compatible with "
        f"one of these: {licenses}.\n"
        f"Ensure that the regenerated code does not contain parts copied from the "
        f"original code to avoid licensing issues.\n\n"
        f"Here is the original code:\n"
        f"```\n{code_content}\n```\n\n"
        f"Return ONLY the regenerated code, without markdown (```) and without "
        f"extra verbal explanations. The code must be ready to be saved to a file."
    )

    try:
        response = call_ollama_qwen3_coder(prompt)
        if not response:
            return None

        # Post-process: Clean up Markdown formatting if present
        clean_response = response.strip()

        if clean_response.startswith("```"):
            # Split by newline to remove the first line (e.g., ```python)
            parts = clean_response.split("\n", 1)
            if len(parts) > 1:
                clean_response = parts[1]

            # Remove the closing backticks if present at the end
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]

        clean_response = clean_response.strip()

        # Validate the generated code
        if not validate_generated_code(clean_response):
            logger.warning("Generated code failed validation")
            return None

        return clean_response

    except Exception:  # pylint: disable=broad-exception-caught
        # Broad catch is intentional here: it acts as a fail-safe to prevent
        # unpredictable LLM or network errors from crashing the entire analysis workflow.
        logger.exception("Error during code regeneration via LLM")
        return None


def validate_generated_code(code: str) -> bool:
    """
    Validates the generated code to ensure it's not empty and not too short.

    Args:
        code (str): The generated code string.

    Returns:
        bool: True if the code passes validation, False otherwise.
    """
    if not code or not isinstance(code, str):
        return False

    stripped = code.strip()
    if len(stripped) <= 10:  # Avoid very short or empty responses
        return False

    return True
