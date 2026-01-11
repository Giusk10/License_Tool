# Questo file .feature definisce uno scenario di test Behave per verificare la funzionalità di upload di un file zip contenente codice sorgente e l'analisi di un progetto privato senza clonazione tramite l'interfaccia License Checker.
Feature: Zip File Upload
  As a user
  I want to upload a local zip file containing source code
  So that I can analyze a private repository without cloning it

  Scenario: Upload a valid zip file
    Given I am on the License Checker home page

    # Nome Owner e Repository sono richiesti per identificazione anche durante l'upload
    When I enter "local-user" in the Owner field
    And I enter "my-zip-project" in the Repository field

    # Step specifico per il caricamento del file zip
    And I upload the file "tests/acceptance/features/fixtures/test_repo.zip"

    # Verifica che l'upload sia avvenuto con successo
    Then I should wait to see "Repository Uploaded Successfully"

    # Procedi con l'analisi del progetto caricato
    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"