# Questo file .feature definisce uno scenario di test Behave per la clonazione e l'analisi di un repository GitHub tramite License Checker, con verifica della visualizzazione del report di compatibilità delle licenze.
Feature: GitHub Repository Analysis
  As a user
  I want to clone and analyze a GitHub repository
  So that I can see the license compatibility report

  Scenario: Complete analysis flow (Clone -> Analyze -> Report)
    Given I am on the License Checker home page
    When I enter "psf" in the Owner field
    And I enter "requests" in the Repository field
    And I click on the Clone Repository button

    # Attesa che il processo di clonazione sia completato
    Then I should wait to see "Repository Cloned Successfully"

    # Analisi del repository clonato
    When I click on the button containing "Analyze Repository"

    # Attesa che l'analisi sia completata
    Then I should wait to see "Analysis Report"
    And I should see "Main License"
    And I should see "License Issues & Compatibility"