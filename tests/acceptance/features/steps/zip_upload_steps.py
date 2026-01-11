# Questo file contiene gli step Behave per l'upload di file zip tramite l'interfaccia License Checker e la verifica del caricamento.
# pylint: disable=not-callable

import os
from behave import when
from selenium.webdriver.common.by import By


@when('I upload the file "{file_path}"')
def step_impl(context, file_path):
    # Converte il percorso relativo in percorso assoluto (richiesto da Selenium)
    abs_path = os.path.abspath(file_path)

    # Trova l'input file nascosto.
    # In React, è comune usare <input type="file" style={{ display: 'none' }} />.
    # Inviamo il percorso del file direttamente senza cliccare sull'input.
    file_input = context.browser.find_element(By.CSS_SELECTOR, "input[type='file']")
    file_input.send_keys(abs_path)