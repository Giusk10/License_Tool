"""
Modulo di test di integrazione per il suggerimento di licenza.

Questo modulo contiene test di integrazione per la funzionalità di suggerimento licenza, con focus
sull'endpoint `/api/suggest-license` e sulle risposte di analisi correlate.
A differenza dei test di unità, questi test utilizzano il `TestClient` di FastAPI per verificare l'intero ciclo richiesta/risposta,
compresi routing, validazione Pydantic e orchestrazione dei controller.

La suite copre:
1. Endpoint di suggerimento licenza: verifica suggerimenti corretti in base ai requisiti utente.
2. Suggerimenti contestuali: verifica che le licenze già presenti influenzino la raccomandazione.
3. Logica copyleft: verifica che vincoli specifici (es. strong copyleft) siano rispettati.
4. Gestione errori e fallback: verifica il comportamento quando il servizio LLM restituisce dati malformati.
5. Integrazione con l'analisi: verifica che l'endpoint di analisi segnali correttamente quando serve un suggerimento.
"""


from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

# Initialize the client for integration tests
client = TestClient(app)


class TestLicenseSuggestionEndpoint:
    """
    Test di integrazione per l'endpoint /api/suggest-license.

    Verifica la corretta gestione delle richieste HTTP, la validazione dei payload
    e la formattazione della risposta JSON simulando chiamate all'applicazione in esecuzione.
    """

    def test_suggest_license_success(self):
        """
        Verifica una richiesta di suggerimento standard andata a buon fine.

        Assicura che fornendo requisiti validi venga restituito uno status 200 OK
        e una struttura JSON contenente suggerimento, spiegazione e alternative.
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
        Verifica che le licenze rilevate vengano passate nel contesto.

        Assicura che, se la richiesta include una lista di licenze già rilevate,
        queste vengano correttamente formattate e incluse nel prompt inviato al LLM.
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
        Verifica la logica di compatibilità con licenze virali.

        Assicura che, se nel progetto viene rilevata una licenza GPL, il motore di suggerimento
        dia priorità a licenze compatibili (es. evitando solo suggerimenti permissivi).
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
        Verifica il comportamento quando la lista delle licenze rilevate è vuota.

        Assicura che la sezione 'EXISTING LICENSES' venga omessa dal prompt
        per non confondere il LLM con dati vuoti.
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
        Verifica la gestione di vincoli di copyleft forte.

        Assicura che impostando 'copyleft' a 'strong' il sistema suggerisca
        licenze come GPL o AGPL.
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
        Verifica la resilienza in caso di fallimento del LLM.

        Assicura che, se il LLM restituisce JSON non valido o fallisce, l'endpoint
        degradi in modo sicuro suggerendo una licenza di default (MIT).
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
    Test di integrazione per la validazione dello schema nei workflow di analisi.
    """

    @patch('app.controllers.analysis.perform_initial_scan')
    def test_analyze_sets_needs_suggestion_flag(self, mock_scan):
        """
        Verifica che l'endpoint di analisi imposti il flag di suggerimento.

        Quando la licenza principale è sconosciuta, la risposta API deve includere
        `needs_license_suggestion=True` per attivare i prompt lato frontend.
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

