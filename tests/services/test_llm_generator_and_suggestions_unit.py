"""
test: services/llm/test_llm_generator_and_suggestions_unit.py

Unit tests for the LLM-based code generation and license suggestion services.
These tests verify the interaction with the LLM API wrappers (mocked),
the parsing and validation of generated code, and the logic for enriching
analysis results with AI-driven suggestions.
"""

import pytest
from unittest.mock import patch, mock_open
from app.services.llm.code_generator import regenerate_code, validate_generated_code
from app.services.llm.suggestion import ask_llm_for_suggestions, review_document, enrich_with_llm_suggestions


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


def test_regenerate_code_validation_syntax_error():
    """
    Verify that generated Python code is rejected (returns None) if it contains
    syntax errors detected by the AST parser.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "def invalid syntax("  # Syntax error
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


# ==============================================================================
# TESTS FOR LICENSE SUGGESTIONS
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


# ==============================================================================
# TESTS FOR CODE VALIDATION
# ==============================================================================

def test_validate_generated_code_valid_python():
    """
    Verify that valid Python code passes validation.
    """
    code = "print('hello world')"
    assert validate_generated_code(code) is True


def test_validate_generated_code_invalid_python():
    """
    Verify that Python code with syntax errors fails validation.
    """
    code = "def invalid("
    assert validate_generated_code(code) is False


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


def test_validate_generated_code_other_language():
    """
    Verify that for non-Python languages, basic length validation passes for valid input.
    """
    code = "some longer code"
    assert validate_generated_code(code, "javascript") is True  # Just length check


def test_validate_generated_code_other_language_short():
    """
    Verify that for non-Python languages, short code fails length validation.
    """
    code = "hi"
    assert validate_generated_code(code, "javascript") is False