import pytest
from unittest.mock import patch
from app.services.llm.license_recommender import (
    suggest_license_based_on_requirements,
    needs_license_suggestion
)

class TestLicenseRecommenderService:
    """
    Unit tests for the license_recommender service logic.
    These tests verify the core logic functions in isolation without invoking the API.
    """

    def test_needs_license_suggestion_no_main_license(self):
        """
        Test `needs_license_suggestion` when no main license exists.
        Should return True if the main license is 'Unknown', 'None', or empty.
        """
        issues = [{"detected_license": "MIT", "compatible": True}]
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

    @patch('app.services.llm.license_recommender.call_ollama_deepseek')
    def test_suggest_license_without_detected_licenses(self, mock_llm):
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
        Test that Markdown code blocks are stripped from the LLM response before parsing.
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