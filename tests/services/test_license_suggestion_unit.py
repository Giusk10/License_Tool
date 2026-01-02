"""
test: services/llm/test_license_suggestion_unit.py

Unit Tests for License Suggestion Feature.

This module tests the license recommendation functionality including
the endpoint integration, service logic, LLM interaction, and requirement validation.
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
    """Test cases for the /api/suggest-license endpoint."""

    def test_suggest_license_success(self):
        """
        Test successful license suggestion request.
        Verifies that providing valid requirements returns a 200 OK response
        with the expected JSON structure containing a suggestion, explanation, and alternatives.
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
        Test license suggestion when existing licenses are detected in the project.
        Verifies that the detected licenses are included in the prompt sent to the LLM
        and that the response reflects compatibility with them.
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
        Test that detecting a GPL license results in a compatible suggestion.
        Ensures that if the project already contains GPL code, the suggestion
        respects the strong copyleft requirements.
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
        Test that an empty detected_licenses list is handled correctly.
        Verifies that the prompt does not include the 'EXISTING LICENSES' section
        when the list is empty.
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
        Test license suggestion with strong copyleft requirement.
        Verifies that selecting 'strong' copyleft results in appropriate suggestions (e.g., GPL).
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
        Test fallback behavior when the LLM service fails or returns invalid data.
        Verifies that the system defaults to a safe suggestion (e.g., MIT) if the LLM response is invalid.
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
    """Test cases for the license_recommender service logic."""

    def test_needs_license_suggestion_no_main_license(self):
        """
        Test `needs_license_suggestion` when no main license exists.
        Should return True if the main license is 'Unknown', 'None', or empty.
        """
        issues = [
            {"detected_license": "MIT", "compatible": True}
        ]

        assert needs_license_suggestion("Unknown", issues) is True
        assert needs_license_suggestion("None", issues) is True
        assert needs_license_suggestion("", issues) is True


    def test_needs_license_suggestion_not_needed(self):
        """
        Test `needs_license_suggestion` when a main license is already present.
        Should return False.
        """
        issues = [
            {"detected_license": "MIT", "compatible": True},
            {"detected_license": "Apache-2.0", "compatible": True}
        ]

        assert needs_license_suggestion("MIT", issues) is False

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_based_on_requirements_permissive(self, mock_llm):
        """
        Test `suggest_license_based_on_requirements` for permissive license requirements.
        Verifies that the service correctly calls the LLM and parses the response.
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
        Test that `detect_licenses` are correctly formatted and included in the LLM prompt string.
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
        Test that the prompt is constructed correctly when no detected licenses are provided.
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
        Test robustness against malformed JSON responses from the LLM.
        Should catch the parsing error and return the fallback license.
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
        Test that Markdown code blocks (```json ... ```) are stripped from the LLM response
        before parsing.
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
    """Test cases for AnalyzeResponse schema validation regarding the suggestion flag."""

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analyze_sets_needs_suggestion_flag(self, mock_scan):
        """
        Test that the analyze endpoint correctly sets the 'needs_license_suggestion' flag
        in the response when the main license is unknown.
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