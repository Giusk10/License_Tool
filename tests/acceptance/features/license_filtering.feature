Feature: Analysis Result Filtering
  As a user
  I want to filter the analysis results
  So that I can focus only on compatible or incompatible licenses

  Scenario: Filter issues by compatibility
    # Initial setup: Reach the report page
    Given I am on the License Checker home page
    When I enter "psf" in the Owner field
    And I enter "requests" in the Repository field
    And I click on the Clone Repository button
    Then I should wait to see "Repository Cloned Successfully"
    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"

    # 1. Filter: Compatible Only (Click the checkmark ✓)
    When I click the filter toggle "✓"
    # Verify: We should see "Compatible" label but NOT "Incompatible"
    Then I should see "Compatible"
    And I should not see "Incompatible"

    # 2. Filter: Incompatible Only (Click the cross ✗)
    When I click the filter toggle "✗"
    # Verify: "Compatible" should disappear
    Then I should not see "Compatible"