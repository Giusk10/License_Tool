"""
test: services/llm/test_llm_generator_and_suggestions_unit.py

Unit tests for the LLM-based services:
1. Code Generator (regenerate_code)
2. Suggestion Enrichment (enrich_with_llm_suggestions)
3. License Recommender (suggest_license_based_on_requirements)

These tests verify the interaction with the LLM API wrappers (mocked),
parsing/validation of generated content, and error handling strategies.
"""

import json
from unittest.mock import patch, mock_open
from app.services.llm.code_generator import regenerate_code, validate_generated_code
from app.services.llm.suggestion import ask_llm_for_suggestions, review_document, enrich_with_llm_suggestions
from app.services.llm import license_recommender

# ==============================================================================
# TESTS FOR CODE GENERATION
# ==============================================================================

def test_regenerate_code_success_with_markdown():
    """
    Verify that code generation works correctly when the LLM output includes
    Markdown code blocks (e.g., ```python ... ```). The blocks should be stripped.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "```python\nprint('hello')\n```"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_success_no_markdown():
    """
    Verify that code generation works correctly when the LLM returns raw code
    without any Markdown formatting.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "print('hello')"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_no_response():
    """
    Verify that the function returns None if the LLM backend returns no response
    (None).
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = None
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_exception():
    """
    Verify that exceptions raised during the LLM call are caught and handled
    gracefully, returning None.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.side_effect = Exception("error")
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_validation_fails():
    """
    Verify that generated code is rejected (returns None) if it fails general
    validation checks (e.g., being too short).
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "short"  # Too short
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


# ==============================================================================
# TESTS FOR LICENSE SUGGESTIONS (ENRICHMENT)
# ==============================================================================

def test_ask_llm_for_suggestions():
    """
    Verify that `ask_llm_for_suggestions` correctly invokes the LLM with the
    issue details and returns the license string suggested by the model.
    """
    issue = {"file_path": "file.py", "detected_license": "GPL", "reason": "incompatible"}
    with patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "MIT, Apache-2.0"
        result = ask_llm_for_suggestions(issue, "MIT")
        assert result == "MIT, Apache-2.0"


def test_review_document_success():
    """
    Verify that `review_document` reads the file content, sends it to the LLM,
    and extracts the advice contained within the expected XML tags (<advice>).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "<advice>Change license</advice>"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result == "Change license"


def test_review_document_no_tags():
    """
    Verify that `review_document` returns None if the LLM response does not
    contain the required XML tags to extract the advice.
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "Some advice without tags"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_llm_returns_none():
    """
    Verify that `review_document` returns None if the LLM response is None or empty.
    This covers the `if not response:` check.
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = None
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_file_error():
    """
    Verify that `review_document` handles file I/O errors gracefully (returns None).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_llm_error():
    """
    Verify that `review_document` handles LLM API errors gracefully (returns None).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_enrich_with_llm_suggestions_compatible():
    """
    Verify that for issues marked as 'compatible', the enrichment logic adds a
    standard 'No action needed' message without calling the LLM.
    """
    issues = [{"file_path": "file.py", "detected_license": "MIT", "compatible": True, "reason": "ok"}]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert result[0]["suggestion"] == "The file is compatible with the project's main license. No action needed."
    assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_incompatible_code():
    """
    Verify that for incompatible code files, the enrichment logic calls
    `ask_llm_for_suggestions` and populates the results.
    """
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions') as mock_ask:
        mock_ask.return_value = "MIT, Apache-2.0"
        result = enrich_with_llm_suggestions("MIT", issues)
        assert len(result) == 1
        assert "MIT, Apache-2.0" in result[0]["suggestion"]
        assert result[0]["licenses"] == "MIT, Apache-2.0"


def test_enrich_with_llm_suggestions_incompatible_doc():
    """
    Verify that for incompatible documentation files (e.g., .md), the enrichment logic
    calls `review_document` instead of the code suggestion flow.
    """
    issues = [{"file_path": "file.md", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    with patch('app.services.llm.suggestion.review_document') as mock_review:
        mock_review.return_value = "Change license"
        result = enrich_with_llm_suggestions("MIT", issues)
        assert len(result) == 1
        assert "Change license" in result[0]["suggestion"]
        assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_with_regenerated():
    """
    Verify that if a mapping of regenerated code paths is provided, the issue
    is updated with the path to the new file.
    """
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    regenerated_map = {"file.py": "/path/to/new.py"}
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions') as mock_ask:
        mock_ask.return_value = "MIT, Apache-2.0"
        result = enrich_with_llm_suggestions("MIT", issues, regenerated_map)
        assert result[0]["regenerated_code_path"] == "/path/to/new.py"


def test_enrich_with_llm_suggestions_conditional_outcome():
    """
    Verify that when compatibility is None and the reason contains
    'Outcome: conditional', the specific suggestion message is returned
    and no licenses are proposed.
    """
    issues = [{
        "file_path": "file.py",
        "detected_license": "GPL",
        "compatible": None,
        "reason": "Outcome: conditional - requires additional terms"
    }]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert result[0]["suggestion"] == "License unavailable in Matrix for check compatibility."
    assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_unknown_outcome():
    """
    Verify that when compatibility is None and the reason contains
    'Outcome: unknown', the specific suggestion message is returned
    and no licenses are proposed.
    """
    issues = [{
        "file_path": "file.py",
        "detected_license": "GPL",
        "compatible": None,
        "reason": "Outcome: unknown - license not found"
    }]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert result[0]["suggestion"] == "License unavailable in Matrix for check compatibility."
    assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_compatible_none_fallback():
    """
    Verify that when compatibility is None but reason is neither conditional nor unknown,
    the fallback 'could not be determined' message is returned.
    """
    issues = [{
        "file_path": "file.py",
        "detected_license": "GPL",
        "compatible": None,
        "reason": "Some random failure"
    }]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert "The repository main license could not be determined" in result[0]["suggestion"]
    assert result[0]["licenses"] == ""


# ==============================================================================
# TESTS FOR CODE VALIDATION
# ==============================================================================

def test_validate_generated_code_valid_python():
    """
    Verify that valid Python code passes validation.
    """
    code = "print('hello world')"
    assert validate_generated_code(code) is True


def test_validate_generated_code_too_short():
    """
    Verify that code failing the minimum length requirement fails validation.
    """
    code = "hi"
    assert validate_generated_code(code) is False


def test_validate_generated_code_empty():
    """
    Verify that empty code strings fail validation.
    """
    code = ""
    assert validate_generated_code(code) is False


def test_validate_generated_code_none():
    """
    Verify that None fails validation.
    """
    code = None
    assert validate_generated_code(code) is False


def test_validate_generated_code_invalid_type():
    """
    Verify that non-string inputs fail validation (covers isinstance check).
    """
    assert validate_generated_code(123) is False
    assert validate_generated_code({}) is False


# ==============================================================================
# TESTS FOR LICENSE RECOMMENDER (NEW ADDITIONS)
# ==============================================================================

def test_suggest_license_success_clean_json():
    """
    Verifies that a valid JSON response from the LLM is correctly parsed
    and returned.
    """
    requirements = {"commercial_use": True}
    mock_response = json.dumps({
        "suggested_license": "Apache-2.0",
        "explanation": "Fits commercial needs.",
        "alternatives": ["MIT"]
    })

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value=mock_response):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "Apache-2.0"
        assert result["alternatives"] == ["MIT"]

def test_suggest_license_strips_markdown():
    """
    Verifies that Markdown code blocks (```json ... ```) are stripped from
    the LLM response before parsing.
    """
    requirements = {"commercial_use": True}
    mock_response = "```json\n" + json.dumps({
        "suggested_license": "BSD-3-Clause",
        "explanation": "Exp",
        "alternatives": []
    }) + "\n```"

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value=mock_response):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "BSD-3-Clause"

def test_suggest_license_empty_response_fallback():
    """
    Verifies that if the LLM returns None or empty string, the function
    raises/catches ValueError and returns the fallback (MIT).
    """
    requirements = {}

    # Simulate empty response
    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value=""):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        # Should return fallback
        assert result["suggested_license"] == "MIT"
        assert "recommended as it's permissive" in result["explanation"]

def test_suggest_license_invalid_json_fallback():
    """
    Verifies that if the LLM returns invalid JSON (garbage text),
    the function catches JSONDecodeError and returns the fallback.
    """
    requirements = {}

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value="Not a JSON"):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "MIT"

def test_suggest_license_generic_exception_fallback():
    """
    Verifies that unexpected exceptions (e.g. network error) are caught
    and result in a safe fallback.
    """
    requirements = {}

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", side_effect=Exception("API Down")):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "MIT"
        assert "error occurred during analysis" in result["explanation"]

def test_suggest_license_prompt_construction_full_flags():
    """
    Verifies that all requirement flags are correctly converted into the prompt text.
    Inspects the argument passed to the mock.
    """
    requirements = {
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "patent_grant": True,
        "trademark_use": True,
        "liability": True,
        "copyleft": "strong",
        "additional_requirements": "Must be OSI approved"
    }
    detected_licenses = ["GPL-2.0"]

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value="{}") as mock_call:
        license_recommender.suggest_license_based_on_requirements(requirements, detected_licenses)

        call_arg = mock_call.call_args[0][0]

        # Check presence of all flags in the prompt
        assert "Commercial use: REQUIRED" in call_arg
        assert "Modification: ALLOWED" in call_arg
        assert "Distribution: ALLOWED" in call_arg
        assert "Patent grant: REQUIRED" in call_arg
        assert "Trademark use: REQUIRED" in call_arg
        assert "Liability protection: REQUIRED" in call_arg
        assert "Copyleft: STRONG copyleft required" in call_arg
        assert "Must be OSI approved" in call_arg
        assert "EXISTING LICENSES IN PROJECT" in call_arg
        assert "GPL-2.0" in call_arg

def test_suggest_license_prompt_construction_false_flags():
    """
    Verifies that 'False' flags generate the correct 'NOT required/allowed' text
    and handles 'weak'/'none' copyleft options.
    """
    requirements = {
        "commercial_use": False,
        "modification": False,
        "distribution": False,
        "copyleft": "weak" # Test 'weak' logic
    }

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value="{}") as mock_call:
        license_recommender.suggest_license_based_on_requirements(requirements)

        call_arg = mock_call.call_args[0][0]

        assert "Commercial use: NOT required" in call_arg
        assert "Modification: NOT allowed" in call_arg
        assert "Distribution: NOT allowed" in call_arg
        assert "Copyleft: WEAK copyleft preferred" in call_arg

def test_suggest_license_prompt_construction_no_copyleft():
    """
    Verifies specific logic for 'copyleft': 'none'.
    """
    requirements = {"copyleft": "none"}

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value="{}") as mock_call:
        license_recommender.suggest_license_based_on_requirements(requirements)
        call_arg = mock_call.call_args[0][0]
        assert "Copyleft: NO copyleft" in call_arg

def test_needs_suggestion_true_unknown_main():
    """
    Verifies that suggestion is needed if main license is Unknown/None.
    """
    assert license_recommender.needs_license_suggestion(None, []) is True
    assert license_recommender.needs_license_suggestion("Unknown", []) is True
    assert license_recommender.needs_license_suggestion("no license", []) is True

def test_needs_suggestion_false_known_main():
    """
    Verifies that suggestion is NOT needed if main license is known (e.g. MIT).
    Also covers the loop execution where issues have known licenses.
    """
    issues = [{"detected_license": "MIT"}]
    # Main license known ("MIT") -> logic falls through to loop -> returns False
    assert license_recommender.needs_license_suggestion("MIT", issues) is False

def test_needs_suggestion_false_unknown_files():
    """
    Verifies the specific branch where files have 'unknown' licenses.
    Note: Current implementation returns False in this case too.
    """
    issues = [{"detected_license": "unknown"}]
    # Main known ("MIT") -> issue is unknown -> loop hits 'return False' early
    assert license_recommender.needs_license_suggestion("MIT", issues) is False


def test_suggest_license_strips_generic_markdown():
    """
    Verifies that generic Markdown code blocks (``` ... ``` without 'json')
    are correctly stripped. This covers the specific branch:
    'if response.startswith("```"):' which is otherwise skipped by json blocks.
    """
    requirements = {"commercial_use": True}
    # Response with generic code block tags
    mock_response = "```\n" + json.dumps({
        "suggested_license": "GPL-3.0",
        "explanation": "Strong copyleft",
        "alternatives": []
    }) + "\n```"

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value=mock_response):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "GPL-3.0"


def test_enrich_with_llm_suggestions_llm_failure_fallback():
    """
    Verifies that if the LLM fails to return a suggestion (returns None) for a
    code file, the suggestion text handles it gracefully.
    """
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]

    # Mock ask_llm_for_suggestions to return None (simulating failure/empty response)
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions', return_value=None):
        result = enrich_with_llm_suggestions("MIT", issues)

        assert len(result) == 1
        # When licenses_list_str is None, f"{licenses_list_str}" becomes "None"
        assert "None" in result[0]["suggestion"]
        assert result[0]["licenses"] is None


def test_enrich_with_llm_suggestions_doc_review_failure_fallback():
    """
    Verifies that if the LLM fails to review a document (returns None) for a
    text/markdown file, the fallback message 'Check document manually.' is used.
    """
    issues = [{"file_path": "README.md", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]

    # Mock review_document to return None
    with patch('app.services.llm.suggestion.review_document', return_value=None):
        result = enrich_with_llm_suggestions("MIT", issues)

        assert len(result) == 1
        assert "Check document manually." in result[0]["suggestion"]