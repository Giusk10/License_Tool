from selenium import webdriver
import os
import shutil
import time

def before_all(context):
    # If FRONTEND_URL exists (CI), use it.
    # Otherwise, use localhost:5173.
    context.base_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Define a dedicated folder for test downloads inside the features directory
    context.download_dir = os.path.abspath("features/downloads")

    if not os.path.exists(context.download_dir):
        os.makedirs(context.download_dir)

    # Clean the directory
    for f in os.listdir(context.download_dir):
        file_path = os.path.join(context.download_dir, f)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error cleaning download dir: {e}")

    options = webdriver.ChromeOptions()

    # Headless mode for CI environments
    if os.getenv("HEADLESS") == "true":
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

    # Configure Chrome to download files automatically
    prefs = {
        "download.default_directory": context.download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    context.browser = webdriver.Chrome(options=options)
    context.browser.implicitly_wait(5)

def after_step(context, step):
    time.sleep(1)
    pass

def after_all(context):
    context.browser.quit()