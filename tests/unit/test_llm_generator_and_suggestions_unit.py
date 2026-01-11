"""
test: services/llm/test_llm_generator_and_suggestions_unit.py

Questo modulo contiene test per la logica di generazione dei prompt per LLM e per la gestione dei suggerimenti di licenza.
Verifica la corretta costruzione dei prompt, la gestione delle risposte dell'LLM, la robustezza contro errori di parsing e la coerenza delle raccomandazioni.

La suite copre:
1. Generazione dei prompt: Costruzione di prompt dettagliati per l'LLM in base ai requisiti e alle licenze rilevate.
2. Parsing delle risposte: Gestione di risposte JSON e Markdown, fallback in caso di errori.
3. Raccomandazioni di licenza: Coerenza tra i suggerimenti forniti e i requisiti specificati.
4. Edge case: Gestione di input vuoti, errori di parsing, risposte malformate.
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
    Verifica che la generazione del codice funzioni correttamente quando l'output dell'LLM include
    blocchi di codice Markdown (ad es., ```python ... ```). I blocchi devono essere rimossi.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "```python\nprint('hello')\n```"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_success_no_markdown():
    """
    Verifica che la generazione del codice funzioni correttamente quando l'LLM restituisce codice non formattato
    senza alcuna formattazione Markdown.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "print('hello')"
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result == "print('hello')"


def test_regenerate_code_no_response():
    """
    Verifica che la funzione restituisca None se il backend dell'LLM non restituisce alcuna risposta
    (None).
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = None
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_exception():
    """
    Verifica che le eccezioni sollevate durante la chiamata all'LLM vengano catturate e gestite
    in modo elegante, restituendo None.
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.side_effect = Exception("error")
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


def test_regenerate_code_validation_fails():
    """
    Verifica che il codice generato venga rifiutato (restituisce None) se non supera i controlli di validazione generali
    (ad es., se è troppo corto).
    """
    with patch('app.services.llm.code_generator.call_ollama_qwen3_coder') as mock_call:
        mock_call.return_value = "short"  # Troppo corto
        result = regenerate_code("old code", "MIT", "GPL", "MIT, Apache")
        assert result is None


# ==============================================================================
# TESTS FOR LICENSE SUGGESTIONS (ENRICHMENT)
# ==============================================================================

def test_ask_llm_for_suggestions():
    """
    Verifica che `ask_llm_for_suggestions` invochi correttamente l'LLM con i dettagli del problema e restituisca
    la stringa di licenza suggerita dal modello.
    """
    issue = {"file_path": "file.py", "detected_license": "GPL", "reason": "incompatible"}
    with patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "MIT, Apache-2.0"
        result = ask_llm_for_suggestions(issue, "MIT")
        assert result == "MIT, Apache-2.0"


def test_review_document_success():
    """
    Verifica che `review_document` legga il contenuto del file, lo invii all'LLM e
    estragga il consiglio contenuto all'interno dei tag XML previsti (<advice>).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "<advice>Change license</advice>"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result == "Change license"


def test_review_document_no_tags():
    """
    Verifica che `review_document` restituisca None se la risposta dell'LLM non contiene
    i tag XML richiesti per estrarre il consiglio.
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = "Some advice without tags"
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_llm_returns_none():
    """
    Verifica che `review_document` restituisca None se la risposta dell'LLM è None o vuota.
    Questo copre il controllo `if not response:`.
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek') as mock_call:
        mock_call.return_value = None
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_file_error():
    """
    Verifica che `review_document` gestisca gli errori di I/O dei file in modo elegante (restituisce None).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_review_document_llm_error():
    """
    Verifica che `review_document` gestisca gli errori dell'API dell'LLM in modo elegante (restituisce None).
    """
    issue = {"file_path": "file.md", "detected_license": "GPL"}
    with patch('builtins.open', mock_open(read_data="content")), \
         patch('app.services.llm.suggestion.call_ollama_deepseek', side_effect=Exception("error")):
        result = review_document(issue, "MIT", "MIT, Apache")
        assert result is None


def test_enrich_with_llm_suggestions_compatible():
    """
    Verifica che per i problemi contrassegnati come 'compatibili', la logica di arricchimento aggiunga un
    messaggio standard 'Nessuna azione necessaria' senza chiamare l'LLM.
    """
    issues = [{"file_path": "file.py", "detected_license": "MIT", "compatible": True, "reason": "ok"}]
    result = enrich_with_llm_suggestions("MIT", issues)
    assert len(result) == 1
    assert result[0]["suggestion"] == "The file is compatible with the project's main license. No action needed."
    assert result[0]["licenses"] == ""


def test_enrich_with_llm_suggestions_incompatible_code():
    """
    Verifica che per i file di codice incompatibili, la logica di arricchimento chiami
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
    Verifica che per i file di documentazione incompatibili (ad es., .md), la logica di arricchimento
    chiami `review_document` invece del flusso di suggerimento del codice.
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
    Verifica che se viene fornita una mappatura dei percorsi del codice rigenerato, il problema
    venga aggiornato con il percorso del nuovo file.
    """
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]
    regenerated_map = {"file.py": "/path/to/new.py"}
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions') as mock_ask:
        mock_ask.return_value = "MIT, Apache-2.0"
        result = enrich_with_llm_suggestions("MIT", issues, regenerated_map)
        assert result[0]["regenerated_code_path"] == "/path/to/new.py"


def test_enrich_with_llm_suggestions_conditional_outcome():
    """
    Verifica che quando la compatibilità è None e il motivo contiene
    'Outcome: conditional', venga restituito il messaggio di suggerimento specifico
    e nessuna licenza venga proposta.
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
    Verifica che quando la compatibilità è None e il motivo contiene
    'Outcome: unknown', venga restituito il messaggio di suggerimento specifico
    e nessuna licenza venga proposta.
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
    Verifica che quando la compatibilità è None ma il motivo non è né condizionale né sconosciuto,
    venga restituito il messaggio di fallback 'non può essere determinato'.
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
    Verifica che codice Python valido superi la validazione.
    """
    code = "print('hello world')"
    assert validate_generated_code(code) is True


def test_validate_generated_code_too_short():
    """
    Verifica che il codice che non supera il requisito di lunghezza minima non superi la validazione.
    """
    code = "hi"
    assert validate_generated_code(code) is False


def test_validate_generated_code_empty():
    """
    Verifica che le stringhe di codice vuote non superino la validazione.
    """
    code = ""
    assert validate_generated_code(code) is False


def test_validate_generated_code_none():
    """
    Verifica che None non superi la validazione.
    """
    code = None
    assert validate_generated_code(code) is False


def test_validate_generated_code_invalid_type():
    """
    Verifica che gli input non stringa non superino la validazione (copre il controllo isinstance).
    """
    assert validate_generated_code(123) is False
    assert validate_generated_code({}) is False


# ==============================================================================
# TESTS FOR LICENSE RECOMMENDER (NEW ADDITIONS)
# ==============================================================================

def test_suggest_license_success_clean_json():
    """
    Verifica che una risposta JSON valida dall'LLM venga correttamente analizzata
    e restituita.
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
    Verifica che i blocchi di codice Markdown (```json ... ```) vengano rimossi da
    la risposta dell'LLM prima dell'analisi.
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
    Verifica che se l'LLM restituisce None o una stringa vuota, la funzione
    solleva/cattura ValueError e restituisce il fallback (MIT).
    """
    requirements = {}

    # Simula risposta vuota
    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value=""):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        # Dovrebbe restituire il fallback
        assert result["suggested_license"] == "MIT"
        assert "recommended as it's permissive" in result["explanation"]

def test_suggest_license_invalid_json_fallback():
    """
    Verifica che se l'LLM restituisce JSON non valido (testo spazzatura),
    la funzione catturi JSONDecodeError e restituisca il fallback.
    """
    requirements = {}

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value="Not a JSON"):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "MIT"

def test_suggest_license_generic_exception_fallback():
    """
    Verifica che eccezioni inaspettate (ad es. errore di rete) vengano catturate
    e risultino in un fallback sicuro.
    """
    requirements = {}

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", side_effect=Exception("API Down")):
        result = license_recommender.suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "MIT"
        assert "error occurred during analysis" in result["explanation"]

def test_suggest_license_prompt_construction_full_flags():
    """
    Verifica che tutti i flag dei requisiti vengano correttamente convertiti nel testo del prompt.
    Ispeziona l'argomento passato al mock.
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

        # Controlla la presenza di tutti i flag nel prompt
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
    Verifica che i flag 'False' generino il corretto testo 'NON richiesto/consentito'
    e gestiscano le opzioni di copyleft 'weak'/'none'.
    """
    requirements = {
        "commercial_use": False,
        "modification": False,
        "distribution": False,
        "copyleft": "weak" # Test logica 'weak'
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
    Verifica la logica specifica per 'copyleft': 'none'.
    """
    requirements = {"copyleft": "none"}

    with patch("app.services.llm.license_recommender.call_ollama_deepseek", return_value="{}") as mock_call:
        license_recommender.suggest_license_based_on_requirements(requirements)
        call_arg = mock_call.call_args[0][0]
        assert "Copyleft: NO copyleft" in call_arg

def test_needs_suggestion_true_unknown_main():
    """
    Verifica che sia necessaria una suggestione se la licenza principale è Sconosciuta/None.
    """
    assert license_recommender.needs_license_suggestion(None, []) is True
    assert license_recommender.needs_license_suggestion("Unknown", []) is True
    assert license_recommender.needs_license_suggestion("no license", []) is True

def test_needs_suggestion_false_known_main():
    """
    Verifica che NON sia necessaria una suggestione se la licenza principale è conosciuta (ad es. MIT).
    Copre anche l'esecuzione del ciclo dove i problemi hanno licenze conosciute.
    """
    issues = [{"detected_license": "MIT"}]
    # Licenza principale conosciuta ("MIT") -> la logica passa al ciclo -> restituisce False
    assert license_recommender.needs_license_suggestion("MIT", issues) is False

def test_needs_suggestion_false_unknown_files():
    """
    Verifica il ramo specifico in cui i file hanno licenze 'sconosciute'.
    Nota: L'implementazione attuale restituisce False anche in questo caso.
    """
    issues = [{"detected_license": "unknown"}]
    # Principale conosciuto ("MIT") -> problema sconosciuto -> ciclo colpisce 'return False' presto
    assert license_recommender.needs_license_suggestion("MIT", issues) is False


def test_suggest_license_strips_generic_markdown():
    """
    Verifica che i blocchi di codice Markdown generici (``` ... ``` senza 'json')
    vengano correttamente rimossi. Questo copre il ramo specifico:
    'if response.startswith("```"):' che viene altrimenti saltato dai blocchi json.
    """
    requirements = {"commercial_use": True}
    # Risposta con tag di blocco di codice generico
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
    Verifica che se l'LLM non riesce a restituire un suggerimento (restituisce None) per un
    file di codice, il testo del suggerimento gestisca la situazione in modo elegante.
    """
    issues = [{"file_path": "file.py", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]

    # Mock ask_llm_for_suggestions per restituire None (simulando errore/riposta vuota)
    with patch('app.services.llm.suggestion.ask_llm_for_suggestions', return_value=None):
        result = enrich_with_llm_suggestions("MIT", issues)

        assert len(result) == 1
        # Quando licenses_list_str è None, f"{licenses_list_str}" diventa "None"
        assert "None" in result[0]["suggestion"]
        assert result[0]["licenses"] is None


def test_enrich_with_llm_suggestions_doc_review_failure_fallback():
    """
    Verifica che se l'LLM non riesce a esaminare un documento (restituisce None) per un
    file di testo/markdown, il messaggio di fallback 'Controlla il documento manualmente.' venga utilizzato.
    """
    issues = [{"file_path": "README.md", "detected_license": "GPL", "compatible": False, "reason": "incompatible"}]

    # Mock review_document per restituire None
    with patch('app.services.llm.suggestion.review_document', return_value=None):
        result = enrich_with_llm_suggestions("MIT", issues)

        assert len(result) == 1
        assert "Check document manually." in result[0]["suggestion"]

