"""
test: services/llm/test_license_suggestion_unit.py

Test unitari per la funzionalità di suggerimento licenze.

Questo modulo testa la funzionalità di raccomandazione licenze inclusi
l'integrazione endpoint, la logica del servizio, l'interazione LLM e la validazione requisiti.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.license_recommender import (
    suggest_license_based_on_requirements,
    needs_license_suggestion
)


client = TestClient(app)


class TestLicenseSuggestionEndpoint:
    """Casi di test per l'endpoint /api/suggest-license."""

    def test_suggest_license_success(self):
        """
        Testa richiesta di suggerimento licenze riuscita.
        Verifica che fornire requisiti validi restituisca una risposta 200 OK
        con la struttura JSON prevista contenente suggerimento, spiegazione e alternative.
        """
        payload = {
            "owner": "test_owner",
            "repo": "test_repo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "trademark_use": False,
            "liability": False,
            "copyleft": "none",
            "additional_requirements": ""
        }

        with patch('app.services.llm.license_recommender.call_ollama_deepseek') as mock_llm:
            mock_llm.return_value = '''
            {
                "suggested_license": "MIT",
                "explanation": "MIT is a permissive license suitable for your requirements.",
                "alternatives": ["Apache-2.0", "BSD-3-Clause"]
            }
            '''

            response = client.post("/api/suggest-license", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert "suggested_license" in data
            assert "explanation" in data
            assert "alternatives" in data

    def test_suggest_license_with_detected_licenses(self):
        """
        Testa suggerimento licenze quando licenze esistenti sono rilevate nel progetto.
        Verifica che le licenze rilevate siano incluse nel prompt inviato all'LLM
        e che la risposta rifletta la compatibilità con esse.
        """
        payload = {
            "owner": "test_owner",
            "repo": "test_repo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "copyleft": "none",
            "detected_licenses": ["Apache-2.0", "MIT"]
        }

        with patch('app.services.llm.license_recommender.call_ollama_deepseek') as mock_llm:
            mock_llm.return_value = '''
            {
                "suggested_license": "Apache-2.0",
                "explanation": "Apache-2.0 is compatible with detected licenses MIT and Apache-2.0.",
                "alternatives": ["MIT", "BSD-3-Clause"]
            }
            '''

            response = client.post("/api/suggest-license", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["suggested_license"] == "Apache-2.0"
            assert "compatible" in data["explanation"].lower() or "apache-2.0" in data["explanation"].lower()

            # Verify that the LLM was called with a prompt containing detected licenses
            call_args = mock_llm.call_args[0][0]
            assert "Apache-2.0" in call_args
            assert "MIT" in call_args
            assert "EXISTING LICENSES IN PROJECT" in call_args

    def test_suggest_license_with_detected_gpl_should_suggest_compatible(self):
        """
        Testa che il rilevamento di una licenza GPL risulti in un suggerimento compatibile.
        Garantisce che se il progetto contiene già codice GPL, il suggerimento
        rispetti i requisiti di strong copyleft.
        """
        payload = {
            "owner": "test_owner",
            "repo": "test_repo",
            "commercial_use": False,
            "modification": True,
            "distribution": True,
            "copyleft": "strong",
            "detected_licenses": ["GPL-3.0"]
        }

        with patch('app.services.llm.license_recommender.call_ollama_deepseek') as mock_llm:
            mock_llm.return_value = '''
            {
                "suggested_license": "GPL-3.0",
                "explanation": "GPL-3.0 is compatible with existing GPL-3.0 license and enforces strong copyleft.",
                "alternatives": ["AGPL-3.0"]
            }
            '''

            response = client.post("/api/suggest-license", json=payload)

            assert response.status_code == 200
            data = response.json()
            # Should suggest GPL-compatible license
            assert "GPL" in data["suggested_license"]

            # Verify prompt included detected licenses
            call_args = mock_llm.call_args[0][0]
            assert "GPL-3.0" in call_args

    def test_suggest_license_with_empty_detected_licenses(self):
        """
        Testa che una lista detected_licenses vuota sia gestita correttamente.
        Verifica che il prompt non includa la sezione 'EXISTING LICENSES'
        quando la lista è vuota.
        """
        payload = {
            "owner": "test_owner",
            "repo": "test_repo",
            "commercial_use": True,
            "copyleft": "none",
            "detected_licenses": []
        }

        with patch('app.services.llm.license_recommender.call_ollama_deepseek') as mock_llm:
            mock_llm.return_value = '''
            {
                "suggested_license": "MIT",
                "explanation": "MIT is a permissive license.",
                "alternatives": ["Apache-2.0"]
            }
            '''

            response = client.post("/api/suggest-license", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["suggested_license"] == "MIT"

            # Verify prompt does NOT include EXISTING LICENSES section
            call_args = mock_llm.call_args[0][0]
            assert "EXISTING LICENSES IN PROJECT" not in call_args

    def test_suggest_license_with_strong_copyleft(self):
        """
        Testa suggerimento licenze con requisito strong copyleft.
        Verifica che selezionare 'strong' copyleft risulti in suggerimenti appropriati (ad es., GPL).
        """
        payload = {
            "owner": "test_owner",
            "repo": "test_repo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": True,
            "trademark_use": False,
            "liability": False,
            "copyleft": "strong",
            "additional_requirements": "Must ensure all derivatives are open source"
        }

        with patch('app.services.llm.license_recommender.call_ollama_deepseek') as mock_llm:
            mock_llm.return_value = '''
            {
                "suggested_license": "GPL-3.0",
                "explanation": "GPL-3.0 provides strong copyleft protection.",
                "alternatives": ["AGPL-3.0", "GPL-2.0"]
            }
            '''

            response = client.post("/api/suggest-license", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["suggested_license"] == "GPL-3.0"

    def test_suggest_license_llm_failure_fallback(self):
        """
        Testa comportamento di fallback quando il servizio LLM fallisce o restituisce dati invalidi.
        Verifica che il sistema utilizzi come default un suggerimento sicuro (ad es., MIT) se la risposta LLM è invalida.
        """
        payload = {
            "owner": "test_owner",
            "repo": "test_repo",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "trademark_use": False,
            "liability": False,
            "copyleft": "none"
        }

        with patch('app.services.llm.license_recommender.call_ollama_deepseek') as mock_llm:
            mock_llm.return_value = "Invalid JSON response"

            response = client.post("/api/suggest-license", json=payload)

            assert response.status_code == 200
            data = response.json()
            # Should fallback to MIT
            assert data["suggested_license"] == "MIT"
            assert "explanation" in data


class TestLicenseRecommenderService:
    """Casi di test per la logica del servizio license_recommender."""

    def test_needs_license_suggestion_no_main_license(self):
        """
        Testa `needs_license_suggestion` quando non esiste una licenza principale.
        Dovrebbe restituire True se la licenza principale è 'Unknown', 'None', o vuota.
        """
        issues = [
            {"detected_license": "MIT", "compatible": True}
        ]

        assert needs_license_suggestion("Unknown", issues) is True
        assert needs_license_suggestion("None", issues) is True
        assert needs_license_suggestion("", issues) is True


    def test_needs_license_suggestion_not_needed(self):
        """
        Testa `needs_license_suggestion` quando una licenza principale è già presente.
        Dovrebbe restituire False.
        """
        issues = [
            {"detected_license": "MIT", "compatible": True},
            {"detected_license": "Apache-2.0", "compatible": True}
        ]

        assert needs_license_suggestion("MIT", issues) is False

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_based_on_requirements_permissive(self, mock_llm):
        """
        Testa `suggest_license_based_on_requirements` per requisiti di licenza permissiva.
        Verifica che il servizio chiami correttamente l'LLM e analizzi la risposta.
        """
        mock_llm.return_value = '''
        {
            "suggested_license": "MIT",
            "explanation": "Permissive and widely used",
            "alternatives": ["BSD-3-Clause", "ISC"]
        }
        '''

        requirements = {
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "trademark_use": False,
            "liability": False,
            "copyleft": "none"
        }

        result = suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "MIT"
        assert "explanation" in result
        assert len(result["alternatives"]) > 0

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_with_detected_licenses_in_prompt(self, mock_llm):
        """
        Testa che `detect_licenses` siano correttamente formattate e incluse nella stringa prompt LLM.
        """
        mock_llm.return_value = '''
        {
            "suggested_license": "Apache-2.0",
            "explanation": "Compatible with existing licenses",
            "alternatives": ["MIT"]
        }
        '''

        requirements = {
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "copyleft": "none"
        }

        detected_licenses = ["Apache-2.0", "MIT", "BSD-3-Clause"]

        result = suggest_license_based_on_requirements(requirements, detected_licenses=detected_licenses)

        assert result["suggested_license"] == "Apache-2.0"

        # Verify the prompt includes detected licenses
        call_args = mock_llm.call_args[0][0]
        assert "EXISTING LICENSES IN PROJECT" in call_args
        assert "Apache-2.0, MIT, BSD-3-Clause" in call_args
        assert "compatible" in call_args.lower()

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_without_detected_licenses(self, mock_llm):
        """
        Testa che il prompt sia costruito correttamente quando non vengono fornite licenze rilevate.
        """
        mock_llm.return_value = '''
        {
            "suggested_license": "MIT",
            "explanation": "Simple permissive license",
            "alternatives": ["BSD-3-Clause"]
        }
        '''

        requirements = {
            "commercial_use": True,
            "copyleft": "none"
        }

        result = suggest_license_based_on_requirements(requirements, detected_licenses=None)

        assert result["suggested_license"] == "MIT"

        # Verify the prompt does NOT include detected licenses section
        call_args = mock_llm.call_args[0][0]
        assert "EXISTING LICENSES IN PROJECT" not in call_args

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_json_parsing_error(self, mock_llm):
        """
        Testa robustezza contro risposte JSON malformate dall'LLM.
        Dovrebbe catturare l'errore di analisi e restituire la licenza di fallback.
        """
        mock_llm.return_value = "This is not valid JSON"

        requirements = {
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "copyleft": "none"
        }

        result = suggest_license_based_on_requirements(requirements)

        # Should return MIT as fallback
        assert result["suggested_license"] == "MIT"
        assert "explanation" in result

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_with_markdown_wrapper(self, mock_llm):
        """
        Testa che i blocchi di codice Markdown (```json ... ```) siano rimossi dalla risposta LLM
        prima dell'analisi.
        """
        mock_llm.return_value = '''```json
        {
            "suggested_license": "Apache-2.0",
            "explanation": "Good for patent protection",
            "alternatives": ["MIT", "BSD-3-Clause"]
        }
        ```'''

        requirements = {
            "commercial_use": True,
            "patent_grant": True,
            "copyleft": "none"
        }

        result = suggest_license_based_on_requirements(requirements)

        assert result["suggested_license"] == "Apache-2.0"


class TestAnalyzeResponseWithSuggestion:
    """Casi di test per la validazione schema AnalyzeResponse riguardo al flag suggestion."""

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analyze_sets_needs_suggestion_flag(self, mock_scan):
        """
        Testa che l'endpoint analyze imposti correttamente il flag 'needs_license_suggestion'
        nella risposta quando la licenza principale è sconosciuta.
        """
        from app.models.schemas import AnalyzeResponse

        mock_response = AnalyzeResponse(
            repository="test_owner/test_repo",
            main_license="Unknown",
            issues=[],
            needs_license_suggestion=True
        )
        mock_scan.return_value = mock_response

        payload = {
            "owner": "test_owner",
            "repo": "test_repo"
        }

        response = client.post("/api/analyze", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data.get("needs_license_suggestion") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])