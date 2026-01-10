Feature: GitHub Repository Analysis
  As a user
  I want to clone and analyze a GitHub repository
  So that I can see the license compatibility report

  Scenario: Complete analysis flow (Clone -> Analyze -> Report)
    Given I am on the License Checker home page
    When I enter "psf" in the Owner field
    And I enter "requests" in the Repository field
    And I click on the Clone Repository button

    # Waiting for the cloning process to complete
    Then I should wait to see "Repository Cloned Successfully"

    # Analyzing the cloned repository
    When I click on the button containing "Analyze Repository"

    # Waiting for the analysis to complete
    Then I should wait to see "Analysis Report"
    And I should see "Main License"
    And I should see "License Issues & Compatibility"