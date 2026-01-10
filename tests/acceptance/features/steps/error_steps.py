# pylint: disable=not-callable

from behave import then
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time  # Imported to handle the delay


@then('I should see an error alert containing "{text}"')
def step_impl(context, text):
    # Wait until the browser alert (pop-up) is present
    WebDriverWait(context.browser, 20).until(EC.alert_is_present())

    # Switch context to the alert
    alert = context.browser.switch_to.alert
    alert_text = alert.text

    # Assertion
    assert text in alert_text, f"Alert text was: {alert_text}"

    # Wait 3 seconds so the user can see the alert before it closes
    time.sleep(3)

    # Accept (Close) the alert
    alert.accept()