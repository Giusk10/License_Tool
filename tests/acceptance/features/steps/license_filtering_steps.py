# Questo file contiene gli step Behave per la gestione dei filtri di compatibilità delle licenze nella pagina di report di License Checker.
# pylint: disable=not-callable
from behave import when, then
from selenium.webdriver.common.by import By
import time


@when('I click the filter toggle "{toggle_name}"')
def step_click_filter_toggle(context, toggle_name):
    # 1. Trova l'elemento del toggle
    # Si usa XPath per trovare un elemento che contiene il testo desiderato.
    # 'normalize-space' viene aggiunto per sicurezza contro spazi bianchi extra.
    xpath = f"//*[contains(text(), '{toggle_name}')]"
    toggle = context.browser.find_element(By.XPATH, xpath)

    # 2. FORZA IL CLICK CON JAVASCRIPT
    # Invece di toggle.click(), si usa questo comando.
    # Dice al browser: "Esegui l'evento click su questo elemento ORA",
    # ignorando se è coperto o se il mouse è altrove.
    context.browser.execute_script("arguments[0].click();", toggle)

    # 3. Pausa per il re-render
    # React ha bisogno di qualche millisecondo per nascondere gli elementi dopo il click.
    # Senza questa pausa, il test controlla la pagina PRIMA che gli elementi scompaiano.
    time.sleep(1)


@then('I should not see "{text}"')
def step_should_not_see(context, text):
    # Logica robusta per verificare che il testo NON sia presente.
    # Si cercano elementi che contengono ESATTAMENTE questo testo (ignorando sottostringhe come "Compatible" in "Incompatible").
    xpath = f"//*[normalize-space(text())='{text}']"

    elements = context.browser.find_elements(By.XPATH, xpath)

    # Filtra solo gli elementi effettivamente visibili a schermo
    visible_elements = [e for e in elements if e.is_displayed()]

    assert len(
        visible_elements) == 0, f"Found {len(visible_elements)} elements showing exactly '{text}' (substrings ignored)."