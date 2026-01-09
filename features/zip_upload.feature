Feature: Zip File Upload
  As a user
  I want to upload a local zip file containing source code
  So that I can analyze a private repository without cloning it

  Scenario: Upload a valid zip file
    Given I am on the License Checker home page

    # Owner and Repo names are required for identification even during upload
    When I enter "local-user" in the Owner field
    And I enter "my-zip-project" in the Repository field

    # Specific step for file upload
    And I upload the file "features/fixtures/test_repo.zip"

    # Verify upload success
    Then I should wait to see "Repository Uploaded Successfully"

    # Proceed to analysis
    When I click on the button containing "Analyze Repository"
    Then I should wait to see "Analysis Report"