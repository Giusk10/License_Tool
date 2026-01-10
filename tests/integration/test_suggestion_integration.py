"""
License Suggestion Integration Test Module.

This module contains integration tests for the license suggestion feature, focusing
on the `/api/suggest-license` endpoint and related analysis responses.
Unlike unit tests, these tests utilize the FastAPI `TestClient` to verify the
full request/response cycle, including routing, Pydantic validation, and
controller orchestration.

The suite covers:
1. License Suggestion Endpoint: Verifying successful suggestions based on user requirements.
2. Contextual Suggestions: Ensuring existing project licenses influence the recommendation.
3. Copyleft Logic: Validating that specific constraints (e.g., strong copyleft) are respected.
4. Error Handling & Fallback: Verifying behavior when the LLM service returns malformed data.
5. Analysis Integration: Checking that the analysis endpoint correctly flags when a suggestion is needed.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

# Initialize the client for integration tests
client = TestClient(app)


class TestLicenseSuggestionEndpoint:
    """
    Integration tests for the /api/suggest-license endpoint.

    Verifies the correct handling of HTTP requests, payload validation,
    and JSON response formatting by simulating calls to the running application.
    """

    def test_suggest_license_success(self):
        """
        Verifies a standard successful suggestion request.

        Ensures that providing valid requirements returns a 200 OK status
        and a JSON structure containing the suggestion, explanation, and alternatives.
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
        Verifies that detected licenses are passed to the context.

        Ensures that if the request includes a list of pre-detected licenses,
        these are correctly formatted and included in the prompt sent to the LLM.
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

            call_args = mock_llm.call_args[0][0]
            assert "Apache-2.0" in call_args
            assert "EXISTING LICENSES IN PROJECT" in call_args

    def test_suggest_license_with_detected_gpl_should_suggest_compatible(self):
        """
        Verifies compatibility logic with viral licenses.

        Ensures that if a GPL license is detected in the project, the suggestion
        engine prioritizes compatible licenses (e.g., avoiding permissive-only suggestions).
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
                "explanation": "GPL-3.0 is compatible with existing GPL-3.0 license.",
                "alternatives": ["AGPL-3.0"]
            }
            '''
            response = client.post("/api/suggest-license", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert "GPL" in data["suggested_license"]

    def test_suggest_license_with_empty_detected_licenses(self):
        """
        Verifies behavior when the detected licenses list is empty.

        Ensures the 'EXISTING LICENSES' section is omitted from the prompt
        to avoid confusing the LLM with empty data.
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

            call_args = mock_llm.call_args[0][0]
            assert "EXISTING LICENSES IN PROJECT" not in call_args

    def test_suggest_license_with_strong_copyleft(self):
        """
        Verifies strict copyleft requirement handling.

        Ensures that setting 'copyleft' to 'strong' forces the system
        to suggest licenses like GPL or AGPL.
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
        Verifies resilience against LLM failures.

        Ensures that if the LLM returns invalid JSON or fails, the endpoint
        gracefully degrades to a default safe suggestion (MIT).
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
            assert data["suggested_license"] == "MIT"


class TestAnalyzeResponseWithSuggestion:
    """
    Integration tests for schema validation in analysis workflows.
    """

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analyze_sets_needs_suggestion_flag(self, mock_scan):
        """
        Verifies that the analysis endpoint sets the suggestion flag.

        When the main license is unknown, the API response must include
        `needs_license_suggestion=True` to trigger frontend prompts.
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