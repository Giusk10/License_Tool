import os
import re
from typing import List, Dict
from app.services.llm.ollama_api import call_ollama_deepseek
from app.utility.config import CLONE_BASE_DIR


def ask_llm_for_suggestions(issue: dict, main_spdx: str) -> str:

    prompt = (
        f"You are a software license expert. A file in the project has a license conflict.\n"
        f"The file '{issue['file_path']}' is released under the license '{issue['detected_license']}', "
        f"which is incompatible with the license {main_spdx}.\n"
        f"Reason for the conflict: {issue['reason']}\n\n"
        f"Provide **ONLY** alternative licenses compatible with the license {main_spdx} that could be adopted to resolve the conflict. "
        f"**DO NOT** provide analysis, explanations, headers, or additional text. "
        f"Respond exactly in the following format: 'License1, License2, License3'"
    )

    suggestion = call_ollama_deepseek(prompt)

    return suggestion

def review_document(issue: dict, main_spdx: str, licenses: str) -> str:
    file_path = issue["file_path"]
    # Ensure that CLONE_BASE_DIR is defined globally or passed as an argument
    abs_path = os.path.join(CLONE_BASE_DIR, file_path)

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            document_content = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None

    print(f"Reviewing document: {file_path}")

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
        "2. Briefly explain the necessary action to resolve the incompatibility (e.g., 'Request dual-licensing from the author', 'Isolate the component', 'Release under X license instead of Y').\n"
        "3. Be direct and pragmatic.\n\n"

        "### OUTPUT FORMAT (MANDATORY)\n"
        "Your response must STRICTLY follow this format, without markdown (```) and without any additional text:\n"
        "<advice>Your operational suggestion here.</advice>"
    )

    try:
        response = call_ollama_deepseek(prompt)

        if not response:
            return None

        # --- IMPROVED EXTRACTION LOGIC (REGEX) ---
        # Searches for everything between <advice> and </advice>.
        # re.DOTALL allows the dot (.) to include newlines.
        # re.IGNORECASE makes the tag case-insensitive (e.g., <Advice>).
        match = re.search(r"<advice>(.*?)</advice>", response, re.DOTALL | re.IGNORECASE)

        if match:
            # Returns only the clean content inside the tags
            return match.group(1).strip()
        else:
            # Fallback: If the model does not use the tags, try to return everything clean
            # or None if you want to be strict. Here we log the error for debugging.
            print(f"Warning: <advice> tag format not found in response for {file_path}")
            return None

    except Exception as e:
        print(f"Error during LLM call: {e}")
        return None

def enrich_with_llm_suggestions(main_spdx: str, issues: List[Dict], regenerated_map: Dict[str, str] = None) -> List[Dict]:
    """
    For each issue, returns a dictionary with fields:
      - file_path, detected_license, compatible, reason
      - suggestion: suggested text
      - regenerated_code_path: regenerated code if present in `regenerated_map`
    `regenerated_map` is optional.
    """
    if regenerated_map is None:
        regenerated_map = {}

    enriched = []

    licenses = ""

    for issue in issues:
        file_path = issue["file_path"]
        detected_license = issue["detected_license"]
        
        if issue.get("compatible"):
            enriched.append({
                "file_path": issue["file_path"],
                "detected_license": issue["detected_license"],
                "compatible": issue["compatible"],
                "reason": issue["reason"],
                "suggestion": "The file is compatible with the project's main license. No action needed.",
                # If the file was regenerated, insert the code here
                "licenses": "",
                "regenerated_code_path": regenerated_map.get(issue["file_path"]),
            })
        else:
            if not file_path.endswith(('.md', '.txt', '.rst', 'THIRD-PARTY-NOTICE', 'NOTICE')):
                licenses = ask_llm_for_suggestions(issue, main_spdx)

                enriched.append({
                    "file_path": issue["file_path"],
                    "detected_license": issue["detected_license"],
                    "compatible": issue["compatible"],
                    "reason": issue["reason"],
                    "suggestion": f"1§ Consider changing the project's main license to adopt "
                                  f"the license '{detected_license}' (or a compatible one) to resolve the conflict.\n"
                                  f"2§ Look for an alternative component or a different library that implements the logic of "
                                  f"'{file_path}' but is released under a license compatible with the project's current license."
                                  f"\n3§ Here are some alternative compatible licenses you might consider: {licenses}",
                    # If the file was regenerated, insert the code here
                    "licenses": licenses,
                    "regenerated_code_path": regenerated_map.get(issue["file_path"]),
                })

            else:

                suggestion = review_document(issue, main_spdx, licenses)

                enriched.append({
                    "file_path": issue["file_path"],
                    "detected_license": issue["detected_license"],
                    "compatible": issue["compatible"],
                    "reason": issue["reason"],
                    "suggestion": f"1§ Consider changing the project's main license to adopt "
                                  f"the license '{detected_license}' (or a compatible one) to resolve the conflict.\n"
                                  f"2§ Look for an alternative component or a different library that implements the logic of "
                                  f"'{file_path}' but is released under a license compatible with the project's current license."
                                  f"\n3§{suggestion}",
                    # If the file was regenerated, insert the code here
                    "licenses": licenses,
                    "regenerated_code_path": regenerated_map.get(issue["file_path"]),
                })

    return enriched