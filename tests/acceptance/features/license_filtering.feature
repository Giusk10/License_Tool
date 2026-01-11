# Questo file .feature definisce uno scenario di test Behave per la funzionalità di filtro dei risultati di analisi per compatibilità delle licenze tramite l'interfaccia License Checker.
Feature: Analysis Result Filtering
  As a user
  I want to filter the analysis results
  So that I can focus only on compatible or incompatible licenses

  Scenario: Filter issues by compatibility
    # Setup iniziale: raggiungi la pagina del report
    Given I am on the License Checker home page
    When I enter "local-user" in the Owner field
    And I enter "my-zip-project" in the Repository field
    And I upload the file "tests/acceptance/features/fixtures/test_repo.zip"
    Then I should wait to see "Repository Uploaded Successfully"
    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"

    # 1. Filtro: Solo compatibili (clicca il check ✓)
    When I click the filter toggle "✓"
    # Verifica: dobbiamo vedere l'etichetta "Compatible" ma NON "Incompatible"
    Then I should see "Compatible"
    And I should not see "Incompatible"

    # 2. Filtro: Solo incompatibili (clicca la X ✗)
    When I click the filter toggle "✗"
    # Verifica: "Compatible" deve scomparire
    Then I should not see "Compatible"