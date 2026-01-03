"""
test: services/llm/test_llm_generator_and_suggestions_unit.py

Test unitari per i servizi di generazione codice basato su LLM e suggerimento licenze.
Questi test verificano l'interazione con i wrapper API LLM (mockati),
l'analisi e la validazione del codice generato, e la logica per arricchire
i risultati di analisi con suggerimenti basati su AI.
"""

from unittest.mock import patch, mock_open
from app.services.llm.code_generator import regenerate_code, validate_generated_code
from app.services.llm.suggestion import ask_llm_for_suggestions, review_document, enrich_with_llm_suggestions


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
