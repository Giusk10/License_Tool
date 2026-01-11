# Questo file .feature definisce uno scenario di test Behave per la verifica del download del report di analisi e del codice sorgente tramite License Checker.
Feature: Report Download
  As a user
  I want to download the analysis results and source code
  So that I can use them locally

  Scenario: Download report after analysis
    Given I am on the License Checker home page

    # Usa un repository piccolo per velocizzare il test (es. antgaldo/checkers o psf/requests)
    When I enter "psf" in the Owner field
    And I enter "requests" in the Repository field
    And I click on the Clone Repository button
    Then I should wait to see "Repository Cloned Successfully"

    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"

    # Clicca il pulsante di download nella pagina del report
    When I click on the button containing "Download"

    # Controlla se il file appare effettivamente nella nostra cartella di download
    # Il formato del nome file da Callback.jsx è: {owner}_{repo}.zip
    Then I should have a downloaded file named "psf_requests.zip"