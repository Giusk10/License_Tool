# pylint: disable=not-callable

import os
from behave import when
from selenium.webdriver.common.by import By


@when('I upload the file "{file_path}"')
def step_impl(context, file_path):
    # Convert relative path to absolute path (Selenium requirement)
    abs_path = os.path.abspath(file_path)

    # Find the hidden file input.
    # In React, <input type="file" style={{ display: 'none' }} /> is common.
    # We send keys directly to it without clicking.
    file_input = context.browser.find_element(By.CSS_SELECTOR, "input[type='file']")
    file_input.send_keys(abs_path)