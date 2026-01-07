"""
test: services/llm/test_llm_generator_and_suggestions_unit.py

Test unitari per i servizi di generazione codice basato su LLM e suggerimento licenze.
Questi test verificano l'interazione con i wrapper API LLM (mockati),
l'analisi e la validazione del codice generato, e la logica per arricchire
i risultati di analisi con suggerimenti basati su AI.
"""

import json
from unittest.mock import patch, mock_open
from app.services.llm.code_generator import regenerate_code, validate_generated_code
from app.services.llm.suggestion import ask_llm_for_suggestions, review_document, enrich_with_llm_suggestions
from app.services.llm import license_recommender

# ==============================================================================
# TEST PER GENERAZIONE CODICE
# ==============================================================================

def test_regenerate_code_success_with_markdown():
    """
    Verifica che la generazione codice funzioni correttamente quando l'output LLM include
    blocchi di codice Markdown (ad es., ```python ... ```). I blocchi dovrebbero essere rimossi.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "```python\nprint('hello')\n```"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_success_no_markdown():
    """
    Verifica che la generazione codice funzioni correttamente quando l'LLM restituisce codice grezzo
    senza alcuna formattazione Markdown.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "print('hello')"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_no_response():
    """
    Verifica che la funzione restituisca None se il backend LLM non restituisce risposta
    (None).
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = None
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_exception():
    """
    Verifica che le eccezioni sollevate durante la chiamata LLM siano catturate e gestite
    con grazia, restituendo None.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.side_effect = Exception("error")
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_validation_fails():
    """
    Verifica che il codice generato sia rifiutato (restituisce None) se fallisce i controlli
    di validazione generali (ad es., essere troppo corto).
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "short"  # Too short
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


# ==============================================================================
# TEST PER SUGGERIMENTI LICENZE
# ==============================================================================

def test_ask_llm_for_suggestions():
    """
    Verifica che `ask_llm_for_suggestions` invochi correttamente l'LLM con i
    dettagli del problema e restituisca la stringa di licenza suggerita dal modello.
    """
    issue = {"file_path": "file.py", "detected_license": "GPL", "reason": "incompatible"}
    with patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "MIT, Apache-2.0"
        result = ask_llm_for_suggestions(issue, "MIT")
        assert result == "MIT, Apache-2.0"


def test_review_document_success():
    """
    Verifica che `review_document` legga il contenuto del file, lo invii all'LLM,
    ed estragga il consiglio contenuto nei tag XML previsti (<advice>).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "<advice>Change license</advice>"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result == "Change license"


def test_review_document_no_tags():
    """
    Verifica che `review_document` restituisca None se la risposta LLM non
    contiene i tag XML richiesti per estrarre il consiglio.
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
    Verifica che `review_document` gestisca gli errori I/O file con grazia (restituisce None).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_llm_error():
    """
    Verifica che `review_document` gestisca gli errori API LLM con grazia (restituisce None).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_enrich_with_llm_suggestions_compatible():
    """
    Verifica che per problemi marcati come 'compatible', la logica di arricchimento aggiunga un
    messaggio standard 'No action needed' senza chiamare l'LLM.
    """
    issues = [{"file_path": "file.py", "detected_license": "MIT", "compatible": True, "reason": "ok"}]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert result[0]["suggestion"] == "The file is compatible with the project's main license. No action needed."
    assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_incompatible_code():
    """
    Verifica che per file di codice incompatibili, la logica di arricchimento chiami
    `ask_llm_for_suggestions` e popoli i risultati.
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
    Verifica che per file di documentazione incompatibili (ad es., .md), la logica di arricchimento
    chiami `review_document` invece del flusso di suggerimento codice.
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
    Verifica che se viene fornito un mapping di percorsi di codice rigenerato, il problema
    sia aggiornato con il percorso al nuovo file.
    """
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    regenerated_map = {"file.py": "/path/to/new.py"}
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions') as mock_ask:
        mock_ask.return_value = "MIT, Apache-2.0"
        result = enrich_with_llm_suggestions("MIT", issues, regenerated_map)
        assert result[0]["regenerated_code_path"] == "/path/to/new.py"


def test_enrich_with_llm_suggestions_conditional_outcome():
    """
    Verifica che quando la compatibilità è None e la ragione contiene
    'Outcome: conditional', venga restituito il messaggio di suggerimento specifico
    e non vengano proposte licenze.
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
    Verifica che quando la compatibilità è None e la ragione contiene
    'Outcome: unknown', venga restituito il messaggio di suggerimento specifico
    e non vengano proposte licenze.
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
# TEST PER VALIDAZIONE CODICE
# ==============================================================================

def test_validate_generated_code_valid_python():
    """
    Verifica che codice Python valido passi la validazione.
    """
    code = "print('hello world')"
    assert validate_generated_code(code) is True


def test_validate_generated_code_too_short():
    """
    Verifica che codice che fallisce il requisito di lunghezza minima fallisca la validazione.
    """
    code = "hi"
    assert validate_generated_code(code) is False


def test_validate_generated_code_empty():
    """
    Verifica che stringhe di codice vuote falliscano la validazione.
    """
    code = ""
    assert validate_generated_code(code) is False


def test_validate_generated_code_none():
    """
    Verifica che None fallisca la validazione.
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