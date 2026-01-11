# Questo file .feature definisce uno scenario di test Behave per la richiesta di suggerimento licenza AI su un progetto senza licenza tramite l'interfaccia License Checker.
Feature: AI License Suggestion
  As a user
  I want to get a license recommendation for an unlicensed project
  So that I know which license suits my needs

  Scenario: Analyze unlicensed repo and get suggestion
    # Raggiungi la pagina del report (step riutilizzati)
    Given I am on the License Checker home page
    When I enter "antgaldo" in the Owner field
    And I enter "checkers" in the Repository field
    And I click on the Clone Repository button
    Then I should wait to see "Repository Cloned Successfully"

    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"

    # Verifica che il progetto sia effettivamente senza licenza (deve apparire come UNLICENSE nell'interfaccia)
    And I should see "UNLICENSE"

    # Clicca sul pulsante 'Get Suggestion' nella pagina del report
    When I click on the button containing "Get Suggestion"

    # Verifica che la modale sia stata aperta
    Then I should see "License Recommendation"
    And I should see "Permissions & Requirements"

    # Interagisci con il form: cambia una preferenza (ad esempio attiva/disattiva 'Commercial use')
    When I toggle the "Commercial use allowed" checkbox

    # Invia la richiesta (usa uno step specifico per evitare ambiguità con il pulsante di apertura)
    And I click the suggestion submit button

    # Attendi la risposta dell'AI
    Then I should wait to see "Recommended License"
    And I should see "Explanation"