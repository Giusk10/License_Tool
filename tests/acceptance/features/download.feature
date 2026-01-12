Feature: Report Download
  As a user
  I want to download the analysis results and source code
  So that I can use them locally

  Scenario: Download report after analysis
    Given I am on the License Checker home page

    # Use a small repo for speed (e.g., antgaldo/checkers or psf/requests)
    When I enter "octocat" in the Owner field
    And I enter "Hello-World" in the Repository field
    And I click on the Clone Repository button
    Then I should wait to see "Repository Cloned Successfully"

    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"

    # Click the download button in the report page
    When I click on the button containing "Download"

    # Check if the file actually appears in our folder
    # The filename format from Callback.jsx is: {owner}_{repo}.zip
    Then I should have a downloaded file named "octocat_Hello-World.zip"