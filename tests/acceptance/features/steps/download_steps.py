# pylint: disable=not-callable

import os
import time
from behave import then


@then('I should have a downloaded file named "{filename}"')
def step_impl(context, filename):
    # Full path to the expected file
    file_path = os.path.join(context.download_dir, filename)

    # Downloads are not instantaneous. We need a polling loop.
    # We wait up to 10 seconds for the file to appear.
    max_wait = 20
    found = False

    for i in range(max_wait):
        if os.path.exists(file_path):
            found = True
            break
        time.sleep(1)  # Wait 1 second before checking again

    assert found, f"File '{filename}' was not found in {context.download_dir} after {max_wait} seconds."

    # Optional: Check if file size is greater than 0 to ensure it's not empty
    file_size = os.path.getsize(file_path)
    assert file_size > 0, f"File '{filename}' was found but is empty (0 bytes)."