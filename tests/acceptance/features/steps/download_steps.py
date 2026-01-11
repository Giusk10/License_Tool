# Questo file contiene gli step Behave per la verifica della presenza e validità dei file scaricati tramite l'applicazione License Checker.
# pylint: disable=not-callable

import os
import time
from behave import then


@then('I should have a downloaded file named "{filename}"')
def step_impl(context, filename):
    # Percorso completo del file atteso
    file_path = os.path.join(context.download_dir, filename)

    # I download non sono istantanei. Serve un ciclo di polling.
    # Si attende fino a 20 secondi che il file compaia.
    max_wait = 20
    found = False

    for i in range(max_wait):
        if os.path.exists(file_path):
            found = True
            break
        time.sleep(1)  # Attende 1 secondo prima di controllare di nuovo

    assert found, f"File '{filename}' was not found in {context.download_dir} after {max_wait} seconds."

    # Opzionale: controlla che la dimensione del file sia maggiore di 0 per assicurarsi che non sia vuoto
    file_size = os.path.getsize(file_path)
    assert file_size > 0, f"File '{filename}' was found but is empty (0 bytes)."

