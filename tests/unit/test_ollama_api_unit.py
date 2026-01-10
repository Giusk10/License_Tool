"""
Unit tests for the Ollama API integration module.
These tests verify the low-level helper functions for managing the Ollama service
lifecycle, checking model installation, and executing prompts against specific models.
It mocks external dependencies (requests, subprocess, file system) to ensure
isolated and fast execution.
"""

import unittest
import json
import requests
import subprocess
from unittest.mock import patch, MagicMock, mock_open

# Import module to be tested
from app.services.llm import ollama_api


class TestOllamaApiUnit(unittest.TestCase):

    # ==============================================================================
    # TESTS FOR SERVICE LIFECYCLE (Status & Start)
    # ==============================================================================

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_ollama_running_true(self, mock_get):
        """
        Verify that `_is_ollama_running` returns True if the service endpoint
        responds with a success status code.
        """
        mock_get.return_value.status_code = 200
        self.assertTrue(ollama_api._is_ollama_running())

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_ollama_running_false(self, mock_get):
        """
        Verify that `_is_ollama_running` returns False if the request raises
        an exception (indicating the service is down or unreachable).
        """
        mock_get.side_effect = requests.RequestException
        self.assertFalse(ollama_api._is_ollama_running())

    @patch('app.services.llm.ollama_api.subprocess.Popen')
    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api.time.sleep')  # Mock sleep to speed up tests
    def test_start_ollama_success(self, mock_sleep, mock_is_running, mock_popen):
        """
        Verify that `_start_ollama` successfully spawns the process and waits
        until the service becomes responsive (simulated by _is_ollama_running returning True).
        """
        # Scenario: first check returns False (not ready), second returns True (ready)
        mock_is_running.side_effect = [False, True]
        result = ollama_api._start_ollama(wait_seconds=1)

        self.assertTrue(result)
        mock_popen.assert_called_once()

    @patch('app.services.llm.ollama_api.subprocess.Popen')
    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api.time.sleep')
    def test_start_ollama_timeout(self, mock_sleep, mock_is_running, mock_popen):
        """
        Verify that `_start_ollama` returns False if the service does not become
        responsive within the specified timeout period.
        """
        mock_is_running.return_value = False
        result = ollama_api._start_ollama(wait_seconds=0.1)
        self.assertFalse(result)

    @patch('app.services.llm.ollama_api.subprocess.Popen')
    def test_start_ollama_popen_error(self, mock_popen):
        """
        Verify that `_start_ollama` returns False and handles the exception
        if the subprocess fails to spawn (e.g., executable not found).
        """
        mock_popen.side_effect = OSError("Error spawning")
        result = ollama_api._start_ollama()
        self.assertFalse(result)

    # ==============================================================================
    # TESTS FOR MODEL MANAGEMENT (Check & Pull)
    # ==============================================================================

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_model_installed_found(self, mock_get):
        """
        Verify that `_is_model_installed` returns True when the requested model
        name is present in the JSON list returned by the API.
        """
        mock_response = {"models": [{"name": "qwen2.5-coder"}, {"name": "other"}]}
        mock_get.return_value.json.return_value = mock_response
        self.assertTrue(ollama_api._is_model_installed("qwen2.5-coder"))

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_model_installed_not_found(self, mock_get):
        """
        Verify that `_is_model_installed` returns False when the requested model
        name is missing from the API response.
        """
        mock_response = {"models": [{"name": "other"}]}
        mock_get.return_value.json.return_value = mock_response
        self.assertFalse(ollama_api._is_model_installed("missing-model"))

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_model_installed_error(self, mock_get):
        """
        Verify that `_is_model_installed` returns False gracefully if the API call fails.
        """
        mock_get.side_effect = requests.RequestException
        self.assertFalse(ollama_api._is_model_installed("any"))

    @patch('app.services.llm.ollama_api.subprocess.run')
    def test_pull_model_success(self, mock_run):
        """
        Verify that `_pull_model` calls the subprocess with the correct arguments.
        """
        ollama_api._pull_model("model-name")
        mock_run.assert_called_once()

    @patch('app.services.llm.ollama_api.subprocess.run')
    def test_pull_model_error(self, mock_run):
        """
        Verify that `_pull_model` catches subprocess errors and logs them
        without crashing the application.
        """
        mock_run.side_effect = subprocess.SubprocessError
        # Should not raise exception
        ollama_api._pull_model("model-name")

    # ==============================================================================
    # TESTS FOR ORCHESTRATION (Ensure Ready)
    # ==============================================================================

    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api._start_ollama')
    @patch('app.services.llm.ollama_api._is_model_installed')
    @patch('app.services.llm.ollama_api._pull_model')
    def test_ensure_ollama_ready_start_and_pull(self, mock_pull, mock_installed, mock_start, mock_running):
        """
        Verify that `ensure_ollama_ready` attempts to start the service and
        pull the model if they are missing/not running.
        """
        # Scenario: Service down, Model missing -> Start True, Pull triggered
        mock_running.return_value = False
        mock_start.return_value = True
        mock_installed.return_value = False

        ollama_api.ensure_ollama_ready("test-model")

        mock_start.assert_called_once()
        mock_pull.assert_called_once_with("test-model")

    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api._start_ollama')
    def test_ensure_ollama_ready_fail_start(self, mock_start, mock_running):
        """
        Verify that `ensure_ollama_ready` raises RuntimeError if the service
        cannot be started.
        """
        mock_running.return_value = False
        mock_start.return_value = False

        with self.assertRaises(RuntimeError):
            ollama_api.ensure_ollama_ready("test-model")

    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api._is_model_installed')
    def test_ensure_ollama_ready_fail_pull_check(self, mock_installed, mock_running):
        """
        Verify that `ensure_ollama_ready` raises RuntimeError if the model is
        missing and `pull_if_needed` is set to False.
        """
        mock_running.return_value = True
        mock_installed.return_value = False

        with self.assertRaises(RuntimeError):
            ollama_api.ensure_ollama_ready("test-model", pull_if_needed=False)

    # ==============================================================================
    # TESTS FOR API EXECUTION (DeepSeek & Qwen)
    # ==============================================================================

    @patch('app.services.llm.ollama_api.ensure_ollama_ready')
    @patch('app.services.llm.ollama_api.requests.post')
    @patch('app.services.llm.ollama_api.os.makedirs')  # Prevent directory creation
    @patch('builtins.open', new_callable=mock_open)
    def test_call_ollama_qwen3_coder_success(self, mock_file, mock_makedirs, mock_post, mock_ensure):
        """
        Verify that `call_ollama_qwen3_coder` sends the correct payload, saves
        debug output to a file, and returns the response string.
        """
        mock_post.return_value.json.return_value = {"response": "print('code')"}
        mock_post.return_value.status_code = 200

        result = ollama_api.call_ollama_qwen3_coder("prompt")

        self.assertEqual(result, "print('code')")
        mock_ensure.assert_called_once()
        # Verify that the debug file is written
        mock_file.assert_called()

    @patch('app.services.llm.ollama_api.ensure_ollama_ready')
    @patch('app.services.llm.ollama_api.requests.post')
    @patch('app.services.llm.ollama_api.os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_call_ollama_deepseek_clean_markdown(self, mock_file, mock_makedirs, mock_post, mock_ensure):
        """
        Verify that `call_ollama_deepseek` correctly strips Markdown code fences
        (e.g., ```json ... ```) from the response string.
        """
        # Simulate response with markdown blocks
        raw_response = "```json\n{\"key\": \"val\"}\n```"
        mock_post.return_value.json.return_value = {"response": raw_response}

        result = ollama_api.call_ollama_deepseek("prompt")

        # Verify markdown removal
        expected = "\n{\"key\": \"val\"}\n"
        self.assertEqual(result, expected)
