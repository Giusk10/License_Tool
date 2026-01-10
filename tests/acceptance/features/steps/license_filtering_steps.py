# pylint: disable=not-callable
from behave import when, then
from selenium.webdriver.common.by import By
import time


@when('I click the filter toggle "{toggle_name}"')
def step_click_filter_toggle(context, toggle_name):
    # 1. Find the element
    # We use XPath to find an element containing the text.
    # 'normalize-space' is added for safety against extra whitespace.
    xpath = f"//*[contains(text(), '{toggle_name}')]"
    toggle = context.browser.find_element(By.XPATH, xpath)

    # 2. FORCE CLICK WITH JAVASCRIPT
    # Instead of toggle.click(), we use this command.
    # This tells the browser: "Execute the click event on this element NOW",
    # ignoring if it's covered or if the mouse is elsewhere.
    context.browser.execute_script("arguments[0].click();", toggle)

    # 3. Pause for re-render
    # React needs a few milliseconds to hide elements after the click.
    # Without this, the test checks the page BEFORE the elements disappear.
    time.sleep(1)


@then('I should not see "{text}"')
def step_should_not_see(context, text):
    # Robust logic to verify that the text is NOT present.
    # We check for elements containing EXACTLY this text (ignoring substrings like "Compatible" in "Incompatible").
    xpath = f"//*[normalize-space(text())='{text}']"

    elements = context.browser.find_elements(By.XPATH, xpath)

    # Filter only elements that are actually visible on screen
    visible_elements = [e for e in elements if e.is_displayed()]

    assert len(
        visible_elements) == 0, f"Found {len(visible_elements)} elements showing exactly '{text}' (substrings ignored)."