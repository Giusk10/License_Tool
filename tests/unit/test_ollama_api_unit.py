"""
Test unitari per il modulo di integrazione con l'API Ollama.
Questi test verificano le funzioni di basso livello per la gestione del ciclo di vita del servizio Ollama,
controllo dell'installazione dei modelli ed esecuzione dei prompt su modelli specifici.
Le dipendenze esterne (requests, subprocess, file system) sono mockate per garantire
esecuzione isolata e veloce.
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
        Verifica che `_is_ollama_running` restituisca True se l'endpoint del servizio
        risponde con uno status di successo.
        """
        mock_get.return_value.status_code = 200
        self.assertTrue(ollama_api._is_ollama_running())

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_ollama_running_false(self, mock_get):
        """
        Verifica che `_is_ollama_running` restituisca False se la richiesta solleva
        un'eccezione (servizio non attivo o non raggiungibile).
        """
        mock_get.side_effect = requests.RequestException
        self.assertFalse(ollama_api._is_ollama_running())

    @patch('app.services.llm.ollama_api.subprocess.Popen')
    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api.time.sleep')  # Mock sleep per velocizzare i test
    def test_start_ollama_success(self, mock_sleep, mock_is_running, mock_popen):
        """
        Verifica che `_start_ollama` avvii correttamente il processo e attenda
        che il servizio diventi responsivo (simulato da _is_ollama_running che restituisce True).
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
        Verifica che `_start_ollama` restituisca False se il servizio non diventa
        responsivo entro il timeout specificato.
        """
        mock_is_running.return_value = False
        result = ollama_api._start_ollama(wait_seconds=0.1)
        self.assertFalse(result)

    @patch('app.services.llm.ollama_api.subprocess.Popen')
    def test_start_ollama_popen_error(self, mock_popen):
        """
        Verifica che `_start_ollama` restituisca False e gestisca l'eccezione
        se il sottoprocesso fallisce ad avviarsi (es. eseguibile non trovato).
        """
        mock_popen.side_effect = OSError("Error spawning")
        result = ollama_api._start_ollama()
        self.assertFalse(result)

    # ===============================================================================
    # TEST SULLA GESTIONE DEI MODELLI (Check & Pull)
    # ===============================================================================

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_model_installed_found(self, mock_get):
        """
        Verifica che `_is_model_installed` restituisca True quando il nome del modello
        richiesto è presente nella lista JSON restituita dall'API.
        """
        mock_response = {"models": [{"name": "qwen2.5-coder"}, {"name": "other"}]}
        mock_get.return_value.json.return_value = mock_response
        self.assertTrue(ollama_api._is_model_installed("qwen2.5-coder"))

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_model_installed_not_found(self, mock_get):
        """
        Verifica che `_is_model_installed` restituisca False quando il modello richiesto
        non è presente nella risposta dell'API.
        """
        mock_response = {"models": [{"name": "other"}]}
        mock_get.return_value.json.return_value = mock_response
        self.assertFalse(ollama_api._is_model_installed("missing-model"))

    @patch('app.services.llm.ollama_api.requests.get')
    def test_is_model_installed_error(self, mock_get):
        """
        Verifica che `_is_model_installed` restituisca False in modo sicuro se la chiamata API fallisce.
        """
        mock_get.side_effect = requests.RequestException
        self.assertFalse(ollama_api._is_model_installed("any"))

    @patch('app.services.llm.ollama_api.subprocess.run')
    def test_pull_model_success(self, mock_run):
        """
        Verifica che `_pull_model` chiami il sottoprocesso con gli argomenti corretti.
        """
        ollama_api._pull_model("model-name")
        mock_run.assert_called_once()

    @patch('app.services.llm.ollama_api.subprocess.run')
    def test_pull_model_error(self, mock_run):
        """
        Verifica che `_pull_model` intercetti errori del sottoprocesso e li logghi
        senza far crashare l'applicazione.
        """
        mock_run.side_effect = subprocess.SubprocessError
        # Should not raise exception
        ollama_api._pull_model("model-name")

    # ===============================================================================
    # TEST DI ORCHESTRAZIONE (Ensure Ready)
    # ===============================================================================

    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api._start_ollama')
    @patch('app.services.llm.ollama_api._is_model_installed')
    @patch('app.services.llm.ollama_api._pull_model')
    def test_ensure_ollama_ready_start_and_pull(self, mock_pull, mock_installed, mock_start, mock_running):
        """
        Verifica che `ensure_ollama_ready` tenti di avviare il servizio e
        scaricare il modello se non sono attivi/presenti.
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
        Verifica che `ensure_ollama_ready` sollevi RuntimeError se il servizio
        non può essere avviato.
        """
        mock_running.return_value = False
        mock_start.return_value = False

        with self.assertRaises(RuntimeError):
            ollama_api.ensure_ollama_ready("test-model")

    @patch('app.services.llm.ollama_api._is_ollama_running')
    @patch('app.services.llm.ollama_api._is_model_installed')
    def test_ensure_ollama_ready_fail_pull_check(self, mock_installed, mock_running):
        """
        Verifica che `ensure_ollama_ready` sollevi RuntimeError se il modello è
        mancante e `pull_if_needed` è impostato a False.
        """
        mock_running.return_value = True
        mock_installed.return_value = False

        with self.assertRaises(RuntimeError):
            ollama_api.ensure_ollama_ready("test-model", pull_if_needed=False)

    # ===============================================================================
    # TEST SULL'ESECUZIONE API (DeepSeek & Qwen)
    # ===============================================================================

    @patch('app.services.llm.ollama_api.ensure_ollama_ready')
    @patch('app.services.llm.ollama_api.requests.post')
    @patch('app.services.llm.ollama_api.os.makedirs')  # Previene la creazione di directory
    @patch('builtins.open', new_callable=mock_open)
    def test_call_ollama_qwen3_coder_success(self, mock_file, mock_makedirs, mock_post, mock_ensure):
        """
        Verifica che `call_ollama_qwen3_coder` invii il payload corretto, salvi
        l'output di debug su file e restituisca la stringa di risposta.
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
        Verifica che `call_ollama_deepseek` rimuova correttamente i blocchi Markdown
        (ad es. ```json ... ```) dalla stringa di risposta.
        """
        # Simulate response with markdown blocks
        raw_response = "```json\n{\"key\": \"val\"}\n```"
        mock_post.return_value.json.return_value = {"response": raw_response}

        result = ollama_api.call_ollama_deepseek("prompt")

        # Verify markdown removal
        expected = "\n{\"key\": \"val\"}\n"
        self.assertEqual(result, expected)
