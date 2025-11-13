import os
import json
import subprocess

SCANCODE_BIN = "/Users/gius03/tools/scancode-toolkit-v32.4.1/scancode"

def run_scancode(repo_path: str) -> dict:
    """
    Runs ScanCode Toolkit and returns parsed JSON results.
    """
    output_file = os.path.join(repo_path, "scancode_output.json")

    cmd = [
        SCANCODE_BIN,
        "--license",
        "--json-pp", output_file,
        repo_path
    ]

    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        raise RuntimeError(f"Errore avvio ScanCode: {e}")

    if not os.path.exists(output_file):
        raise RuntimeError("ScanCode non ha generato il file JSON")

    with open(output_file, "r", encoding="utf-8") as f:
        return json.load(f)
