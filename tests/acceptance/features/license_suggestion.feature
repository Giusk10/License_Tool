Feature: AI License Suggestion
  As a user
  I want to get a license recommendation for an unlicensed project
  So that I know which license suits my needs

  Scenario: Analyze unlicensed repo and get suggestion
    # Reach the report (Reused steps)
    Given I am on the License Checker home page
    When I enter "octocat" in the Owner field
    And I enter "Hello-World" in the Repository field
    And I click on the Clone Repository button
    Then I should wait to see "Repository Cloned Successfully"

    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"

    # Verify that the project is indeed unlicensed (appears as UNLICENSE in UI)
    And I should see "UNLICENSE"

    # Click on 'Get Suggestion' button in the report page
    When I click on the button containing "Get Suggestion"

    # Verify that the modal has opened
    Then I should see "License Recommendation"
    And I should see "Permissions & Requirements"

    # Interact with the form: change a preference (e.g. toggle 'Commercial use')
    When I toggle the "Commercial use allowed" checkbox

    # Submit the request (use a specific step to avoid confusion with the opening button)
    And I click the suggestion submit button

    # Wait for AI response
    Then I should wait to see "Recommended License"
    And I should see "Explanation"