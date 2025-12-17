import pytest
from unittest.mock import patch, mock_open
from app.services.llm.code_generator import regenerate_code
from app.services.llm.suggestion import ask_llm_for_suggestions, review_document, enrich_with_llm_suggestions


# Tests for code_generator.py

def test_regenerate_code_success_with_markdown():
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "```python\nprint('hello')\n```"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_success_no_markdown():
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "print('hello')"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_no_response():
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = None
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_exception():
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.side_effect = Exception("error")
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


# Tests for suggestion.py

def test_ask_llm_for_suggestions():
    issue = {"file_path": "file.py", "detected_license": "GPL", "reason": "incompatible"}
    with patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "MIT, Apache-2.0"
        result = ask_llm_for_suggestions(issue, "MIT")
        assert result == "MIT, Apache-2.0"


def test_review_document_success():
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "<advice>Change license</advice>"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result == "Change license"


def test_review_document_no_tags():
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "Some advice without tags"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_file_error():
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_llm_error():
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_enrich_with_llm_suggestions_compatible():
    issues = [{"file_path": "file.py", "detected_license": "MIT", "compatible": True, "reason": "ok"}]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert result[0]["suggestion"] == "The file is compatible with the project's main license. No action needed."
    assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_incompatible_code():
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions') as mock_ask:
        mock_ask.return_value = "MIT, Apache-2.0"
        result = enrich_with_llm_suggestions("MIT", issues)
        assert len(result) == 1
        assert "MIT, Apache-2.0" in result[0]["suggestion"]
        assert result[0]["licenses"] == "MIT, Apache-2.0"


def test_enrich_with_llm_suggestions_incompatible_doc():
    issues = [{"file_path": "file.md", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    with patch('app.services.llm.suggestion.review_document') as mock_review:
        mock_review.return_value = "Change license"
        result = enrich_with_llm_suggestions("MIT", issues)
        assert len(result) == 1
        assert "Change license" in result[0]["suggestion"]
        assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_with_regenerated():
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    regenerated_map = {"file.py": "/path/to/new.py"}
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions') as mock_ask:
        mock_ask.return_value = "MIT, Apache-2.0"
        result = enrich_with_llm_suggestions("MIT", issues, regenerated_map)
        assert result[0]["regenerated_code_path"] == "/path/to/new.py"
