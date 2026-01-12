# Questo file configura l'ambiente di test Behave/Selenium: setup e teardown del browser, gestione cartella download e variabili di ambiente.

from selenium import webdriver
import os
import time

def before_all(context):
    # Se FRONTEND_URL esiste (es. in CI), usa quello.
    # Altrimenti usa localhost:5173.
    context.base_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Definisce una cartella dedicata per i download dei test dentro la cartella features
    base_dir = os.path.dirname(os.path.abspath(__file__))
    context.download_dir = os.path.join(base_dir, "downloads")

    if not os.path.exists(context.download_dir):
        os.makedirs(context.download_dir)

    # Pulisce la cartella dei download prima di ogni run
    for f in os.listdir(context.download_dir):
        file_path = os.path.join(context.download_dir, f)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error cleaning download dir: {e}")

    options = webdriver.ChromeOptions()

    # Modalità headless per ambienti CI
    if os.getenv("HEADLESS") == "true":
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

    # Configura Chrome per scaricare i file automaticamente nella cartella scelta
    prefs = {
        "download.default_directory": context.download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    context.browser = webdriver.Chrome(options=options)
    context.browser.implicitly_wait(5)  # Imposta un'attesa implicita per tutti gli elementi

def after_step(context, step):
    time.sleep(1)  # Pausa dopo ogni step per maggiore stabilità dei test


def after_all(context):
    context.browser.quit()  # Chiude il browser al termine dei test
