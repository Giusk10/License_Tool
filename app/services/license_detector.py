def detect_main_license_scancode(data: dict) -> str:
    """
    Detects main project license from ScanCode output.
    Supports all ScanCode formats:
    - spdx_license_key
    - license_expression
    - license_expressions
    """
    for entry in data.get("files", []):
        path = entry.get("path", "").lower()

        if "license" in path or "copying" in path:
            for lic in entry.get("licenses", []):

                if "spdx_license_key" in lic and lic["spdx_license_key"]:
                    return lic["spdx_license_key"]

                if "license_expression" in lic and lic["license_expression"]:
                    return lic["license_expression"].upper()

                if "license_expressions" in lic and lic["license_expressions"]:
                    return lic["license_expressions"][0].upper()

    return "UNKNOWN"


def extract_file_licenses_scancode(data: dict) -> dict:
    """
    Extract SPDX licenses for each file using ScanCode.
    Returns: { file_path: spdx_id }
    """
    results = {}

    for entry in data.get("files", []):
        file_path = entry.get("path")
        licenses = entry.get("licenses", [])

        if not licenses:
            continue

        lic = licenses[0]

        if "spdx_license_key" in lic:
            results[file_path] = lic["spdx_license_key"]

        elif "license_expression" in lic:
            results[file_path] = lic["license_expression"].upper()

        elif "license_expressions" in lic and lic["license_expressions"]:
            results[file_path] = lic["license_expressions"][0].upper()

    return results
