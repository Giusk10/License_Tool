# pylint: disable=not-callable
from behave import given, when, then
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

@given('I am on the License Checker home page')
def step_visit_home_page(context):
    context.browser.get(context.base_url)


@when('I enter "{text}" in the Owner field')
def step_enter_owner(context, text):
    input_owner = context.browser.find_element(By.CSS_SELECTOR, "input[placeholder*='GitHub Owner']")
    input_owner.clear()
    input_owner.send_keys(text)


@when('I enter "{text}" in the Repository field')
def step_enter_repo(context, text):
    input_repo = context.browser.find_element(By.CSS_SELECTOR, "input[placeholder*='Repository Name']")
    input_repo.clear()
    input_repo.send_keys(text)


@when('I click on the Clone Repository button')
def step_click_clone(context):
    button = context.browser.find_element(By.XPATH, "//button[contains(., 'Clone Repository')]")
    button.click()


@when('I click on the button containing "{text}"')
def step_click_generic_button(context, text):
    wait = WebDriverWait(context.browser, 20)
    button = wait.until(EC.element_to_be_clickable((By.XPATH, f"//button[contains(., '{text}')]")))
    button.click()


@then('I should wait to see "{text}"')
def step_wait_see_text(context, text):
    wait = WebDriverWait(context.browser, 60)

    try:
        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), text))
    except:
        # If time runs out, fail the test showing what's on the page
        assert False, f"Timeout: Text '{text}' not found. Page content snippet: {context.browser.page_source[:200]}"


@then('I should see "{text}"')
def step_see_text(context, text):
    # Search in the VISIBLE text of the body, not raw HTML.
    # This solves issues with special characters like '&' which become '&amp;' in HTML
    body_text = context.browser.find_element(By.TAG_NAME, "body").text
    assert text in body_text, f"Text '{text}' not found in visible body text."