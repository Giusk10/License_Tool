from selenium import webdriver
import os
import shutil
import time


def before_all(context):
    # Define a dedicated folder for test downloads inside the features directory
    context.download_dir = os.path.abspath("features/downloads")

    # Create the directory if it doesn't exist
    if not os.path.exists(context.download_dir):
        os.makedirs(context.download_dir)

    # Clean the directory before starting tests to avoid false positives
    for f in os.listdir(context.download_dir):
        file_path = os.path.join(context.download_dir, f)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error cleaning download dir: {e}")

    options = webdriver.ChromeOptions()

    # Configure Chrome to download files automatically to our specific folder
    prefs = {
        "download.default_directory": context.download_dir,
        "download.prompt_for_download": False,  # Disable the "Save As" popup
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    # Initialize the browser with these options
    context.browser = webdriver.Chrome(options=options)
    context.browser.implicitly_wait(5)


def after_step(context, step):
    time.sleep(1)
    pass


def after_all(context):
    context.browser.quit()

    #shutil.rmtree(context.download_dir)