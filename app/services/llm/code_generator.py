from typing import Optional
from app.services.llm.ollama_api import call_ollama_qwen3_coder  # if you want to make it public, move it

def regenerate_code(
    code_content: str,
    main_license: str,
    detected_license: str,
    licenses: str
) -> Optional[str]:
    """
    Asks Ollama to regenerate a code block with a compatible license.
    """
    prompt = (
        f"You are a software licensing and refactoring expert. "
        f"The following code is currently under the license '{detected_license}', which is incompatible with the project's main license '{main_license}'.\n"
        f"Your task is to find a component that is functionally equivalent but can be released under a license compatible with '{main_license}' among these: {licenses}.\n"
        f"If the component does not exist, regenerate it from scratch while maintaining the same functionality but ensuring it is under a license compatible with one of these: {licenses}.\n"
        f"Ensure that the regenerated code does not contain parts copied from the original code to avoid licensing issues.\n\n"
        f"Here is the original code:\n"
        f"```\n{code_content}\n```\n\n"
        f"Return ONLY the regenerated code, without markdown (```) and without extra verbal explanations. The code must be ready to be saved to a file."
    )
    try:
        response = call_ollama_qwen3_coder(prompt)
        if not response:
            return None
            
        # Clean Markdown if present
        clean_response = response.strip()
        if clean_response.startswith("```"):
            # Remove the first line (```python or similar)
            clean_response = clean_response.split("\n", 1)[1]
            # Remove the last line (```)
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("\n", 1)[0]
        
        return clean_response.strip()
    except Exception:
        return None