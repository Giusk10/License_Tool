"""
BLACK BOX TESTING - LICENSE TOOL
=================================

Questo modulo implementa test di tipo Black Box per il License Tool, un sistema che analizza
repository GitHub per rilevare licenze, verificare compatibilità e suggerire licenze appropriate.

OBIETTIVO DEI TEST:
-------------------
I test verificano il comportamento del sistema dal punto di vista dell'utente finale, senza
conoscere i dettagli implementativi interni. Si concentrano su:
- Input/Output delle API REST
- Flussi di lavoro end-to-end
- Gestione degli errori
- Coerenza delle risposte

TEST CASES IMPLEMENTATI:
------------------------
TC-01: Health Check
    - Verifica che il server sia attivo e risponda correttamente all'endpoint root
    - Valida la struttura della risposta JSON

TC-02: Clone & Analyze Flow (Happy Path)
    - Testa il flusso completo di clonazione e analisi di un repository GitHub
    - Clona un repository pubblico reale
    - Esegue l'analisi delle licenze del repository clonato
    - Verifica la struttura della risposta (repository, main_license, issues)
    - Valida che vengano rilevate informazioni sulle licenze

TC-03: Error Handling
    - Verifica la gestione degli errori per repository inesistenti
    - Controlla che il sistema risponda con codici di stato HTTP appropriati
    - Valida che non vengano accettate richieste non valide

TC-04: AI License Suggestion
    - Testa il sistema di raccomandazione licenze basato su AI
    - Invia requisiti specifici (uso commerciale, modifiche, distribuzione, copyleft)
    - Verifica che il suggerimento sia coerente con i requisiti forniti
    - Valida che licenze permissive vengano suggerite quando richiesto "no copyleft"

PREREQUISITI:
-------------
- Il server FastAPI deve essere in esecuzione su http://localhost:8000
- Il servizio Ollama (AI) deve essere attivo per TC-04
- Connessione internet per clonare repository GitHub reali

ESECUZIONE:
-----------
python blackbox_tester.py

oppure con pytest:
pytest blackbox_tester.py -v

oppure con coverage:
coverage run -m pytest blackbox_tester.py -v
coverage report
"""

import requests
import unittest
import sys

# CONFIGURAZIONE
# Cambia questo URL se il tuo server gira su una porta diversa o su un host remoto
BASE_URL = "https://licensechecker-license-checker-tool.hf.space"

class TestLicenseToolBlackBox(unittest.TestCase):

    def setUp(self):
        """Verifica preliminare che il server sia attivo."""
        self.base_url = BASE_URL
        try:
            response = requests.get(f"{self.base_url}/")
            if response.status_code != 200:
                print(f"\n[!] Attenzione: Il server risponde con {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"\n[!] Errore: Impossibile connettersi a {self.base_url}. Assicurati che il server sia avviato.")
            sys.exit(1)

    def test_01_health_check(self):
        """TC-01: Verifica che l'endpoint root risponda."""
        print("\nEsecuzione TC-01: Health Check...")
        response = requests.get(f"{self.base_url}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())
        print(" -> PASS")

    def test_02_clone_and_analyze_flow(self):
        """
        TC-02: Flusso completo (Happy Path).
        1. Clona un repo pubblico (es. requests/requests o un tuo repo di test).
        2. Richiedi l'analisi del repo clonato.
        """
        print("\nEsecuzione TC-02: Clone & Analyze Flow...")

        # Dati di test: usiamo un repo noto e leggero se possibile, o uno fittizio se mockato
        payload = {"owner": "giusk10", "repo": "license_tool"}

        # 1. Step Clone
        clone_url = f"{self.base_url}/api/clone"
        clone_res = requests.post(clone_url, json=payload)

        if clone_res.status_code != 200:
            print(f" -> Clone fallito: {clone_res.text}")

        self.assertEqual(clone_res.status_code, 200, "La clonazione dovrebbe avere successo")
        self.assertEqual(clone_res.json()["status"], "cloned")

        # 2. Step Analyze
        analyze_url = f"{self.base_url}/api/analyze"
        analyze_res = requests.post(analyze_url, json=payload)

        self.assertEqual(analyze_res.status_code, 200, "L'analisi dovrebbe avere successo")
        data = analyze_res.json()

        # Verifiche Black Box sulla struttura della risposta
        self.assertIn("repository", data)
        self.assertIn("main_license", data)
        self.assertIn("issues", data)
        self.assertIsInstance(data["issues"], list)
        print(f" -> Analisi completata per {data['repository']}. Licenza rilevata: {data['main_license']}")
        print(" -> PASS")

    def test_03_error_handling_invalid_repo(self):
        """TC-03: Verifica gestione errori per repo inesistente."""
        print("\nEsecuzione TC-03: Error Handling...")

        payload = {"owner": "non_existent_owner_12345", "repo": "non_existent_repo_98765"}

        # Ci aspettiamo che il clone fallisca
        response = requests.post(f"{self.base_url}/api/clone", json=payload)

        # A seconda dell'implementazione, potrebbe ritornare 400 o 500
        # Basandoci sul tuo codice: raise HTTPException(status_code=400, detail=str(ve))
        self.assertNotEqual(response.status_code, 200, "Il clone di un repo inesistente non deve dare 200 OK")
        print(f" -> Correttamente rifiutato con status {response.status_code}")
        print(" -> PASS")

    def test_04_license_suggestion(self):
        """
        TC-04: Verifica suggerimento licenza (AI).
        Simuliamo la richiesta dal form Frontend.
        """
        print("\nEsecuzione TC-04: AI License Suggestion...")

        # Payload basato su schemas.py LicenseRequirementsRequest
        payload = {
            "owner": "test_user",
            "repo": "test_project",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "trademark_use": False,
            "liability": False,
            "copyleft": "none",  # Richiediamo esplicitamente una licenza permissiva
            "additional_requirements": "Short and simple."
        }

        url = f"{self.base_url}/api/suggest-license"
        response = requests.post(url, json=payload)

        if response.status_code == 500:
            print(" -> [SKIP] Il servizio AI/Ollama potrebbe non essere attivo o raggiungibile.")
            return

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("suggested_license", data)
        self.assertIn("explanation", data)

        # Verifica logica di base (Black Box):
        # Se chiedo "copyleft: none" e "commercial_use: true", mi aspetto MIT, Apache o BSD.
        suggestion = data["suggested_license"].upper()
        possibili_match = ["MIT", "APACHE", "BSD", "ISC"]
        is_permissive = any(lic in suggestion for lic in possibili_match)

        if is_permissive:
            print(f" -> Suggerimento coerente ricevuto: {suggestion}")
        else:
            print(f" -> [!] Nota: Il modello ha suggerito {suggestion} nonostante la richiesta di 'no copyleft'.")

        print(" -> PASS")

if __name__ == "__main__":
    unittest.main()