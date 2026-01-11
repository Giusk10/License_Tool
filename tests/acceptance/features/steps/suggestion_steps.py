# Questo file contiene gli step Behave per l'interazione con la modale di suggerimento licenza AI e la gestione delle checkbox delle preferenze.
# pylint: disable=not-callable
from behave import when
from selenium.webdriver.common.by import By

# Step per cliccare sulle checkbox in base al testo accanto (es. "Commercial use allowed")
@when('I toggle the "{label_text}" checkbox')
def step_toggle_checkbox(context, label_text):
    # L'HTML è strutturato come <label> <input> <span>Testo</span> </label>
    # Cliccando sull'etichetta si attiva/disattiva la checkbox in Selenium
    xpath = f"//label[contains(., '{label_text}')]"
    element = context.browser.find_element(By.XPATH, xpath)
    element.click()

# Step specifico per il pulsante all'interno della modale
@when('I click the suggestion submit button')
def step_submit_suggestion(context):
    # Ambiguità: ci sono due pulsanti con il testo "Get Suggestion" nella pagina
    # (uno sotto nel report, uno nella modale).
    # Per essere sicuri di cliccare quello giusto (quello di submit), usiamo un selettore CSS preciso.
    # Cerchiamo un pulsante di tipo 'submit' all'interno di un tag 'form'.
    submit_btn = context.browser.find_element(By.CSS_SELECTOR, "form button[type='submit']")
    submit_btn.click()