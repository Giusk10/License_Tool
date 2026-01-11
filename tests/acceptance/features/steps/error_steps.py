# Questo file contiene gli step Behave per la gestione e la verifica degli alert di errore visualizzati dal browser durante l'uso di License Checker.

# pylint: disable=not-callable

from behave import then
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time  # Importato per gestire il ritardo


@then('I should see an error alert containing "{text}"')
def step_impl(context, text):
    # Attende che sia presente un alert del browser (pop-up)
    WebDriverWait(context.browser, 20).until(EC.alert_is_present())

    # Passa il contesto all'alert
    alert = context.browser.switch_to.alert
    alert_text = alert.text

    # Asserzione: verifica che il testo sia presente nell'alert
    assert text in alert_text, f"Alert text was: {alert_text}"

    # Attende 3 secondi per permettere all'utente di vedere l'alert prima che venga chiuso
    time.sleep(3)

    # Accetta (chiude) l'alert
    alert.accept()