Feature: Error Handling
  As a user
  I want to be notified if the repository does not exist
  So that I can correct my input

  Scenario: Try to clone a non-existent repository
    Given I am on the License Checker home page
    When I enter "this-user-does-not-exist" in the Owner field
    And I enter "nothing-here" in the Repository field
    And I click on the Clone Repository button
    Then I should see an error alert containing "Cloning failed"