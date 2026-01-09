# pylint: disable=not-callable
from behave import when
from selenium.webdriver.common.by import By

# Step to click checkboxes based on the text next to them (e.g., "Commercial use allowed")
@when('I toggle the "{label_text}" checkbox')
def step_toggle_checkbox(context, label_text):
    # The HTML is structured as <label> <input> <span>Text</span> </label>
    # Clicking on the label automatically toggles the checkbox in Selenium
    xpath = f"//label[contains(., '{label_text}')]"
    element = context.browser.find_element(By.XPATH, xpath)
    element.click()

# Specific step for the button inside the modal
@when('I click the suggestion submit button')
def step_submit_suggestion(context):
    # Ambiguity: there are two buttons with text "Get Suggestion" on the page
    # (one below in the report, one in the modal).
    # To ensure we click the right one (the submit one), we use a precise CSS selector.
    # We look for a button of type 'submit' inside a 'form' tag.
    submit_btn = context.browser.find_element(By.CSS_SELECTOR, "form button[type='submit']")
    submit_btn.click()