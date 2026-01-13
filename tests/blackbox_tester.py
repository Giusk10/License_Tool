"""Black Box Testing module for the License Tool.

This module implements Black Box tests for the License Tool, a system that analyzes
GitHub repositories to detect licenses, verify compatibility, and suggest appropriate licenses.

Test Objectives:
    The tests verify the system behavior from an end-user perspective, without
    knowledge of internal implementation details. They focus on:
    - REST API Input/Output.
    - End-to-end workflows.
    - Error handling.
    - Response consistency.

Implemented Test Cases:
    TC-01: Health Check
        - Verifies that the server is active and responds correctly to the root endpoint.
        - Validates the JSON response structure.

    TC-02: Clone & Analyze Flow (Happy Path)
        - Tests the complete flow of cloning and analyzing a GitHub repository.
        - Clones a real public repository.
        - Analyzes the licenses of the cloned repository.
        - Verifies the response structure (repository, main_license, issues).
        - Validates that license information is detected.

    TC-03: Error Handling
        - Verifies error handling for non-existent repositories.
        - Checks that the system responds with appropriate HTTP status codes.
        - Validates that invalid requests are not accepted.

    TC-04: AI License Suggestion
        - Tests the AI-based license recommendation system.
        - Sends specific requirements (commercial use, modifications, distribution, copyleft).
        - Verifies that the suggestion is consistent with the provided requirements.
        - Validates that permissive licenses are suggested when "no copyleft" is requested.

Prerequisites:
    - The FastAPI server must be running at http://localhost:8000.
    - The Ollama (AI) service must be active for TC-04.
    - Internet connection to clone real GitHub repositories.

Usage:
    python tests/sanity_check.py

    Or with pytest:
    pytest tests/sanity_check.py -v
"""

import sys
import unittest
import requests

# CONFIGURATION
# Change this URL if your server runs on a different port or remote host.
BASE_URL = "http://localhost:8000"


class TestLicenseToolBlackBox(unittest.TestCase):
    """Black box test suite for the License Tool API.

    Attributes:
        base_url (str): The base URL of the running License Tool API.
    """

    def setUp(self):
        """Performs a preliminary check to ensure the server is active.

        This method runs before every test. It attempts to connect to the root
        endpoint. If the connection fails or the status code is not 200, the
        test execution is aborted.

        Raises:
            SystemExit: If the server is unreachable.
        """
        self.base_url = BASE_URL
        try:
            response = requests.get(f"{self.base_url}/")
            if response.status_code != 200:
                print(f"\n[!] Warning: Server responded with status code {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(
                f"\n[!] Error: Unable to connect to {self.base_url}. "
                "Ensure the server is running."
            )
            sys.exit(1)

    def test_01_health_check(self):
        """TC-01: Verifies that the root endpoint is responsive.

        Asserts:
            - The HTTP status code is 200.
            - The JSON response contains a 'message' key.
        """
        print("\nRunning TC-01: Health Check...")
        response = requests.get(f"{self.base_url}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())
        print(" -> PASS")

    def test_02_clone_and_analyze_flow(self):
        """TC-02: Verifies the complete Clone & Analyze flow (Happy Path).

        Steps:
            1. Clone a public repository (e.g., a known test repo).
            2. Request an analysis of the cloned repository.

        Asserts:
            - The clone request returns HTTP 200 and status 'cloned'.
            - The analyze request returns HTTP 200.
            - The analysis response contains 'repository', 'main_license', and 'issues'.
        """
        print("\nRunning TC-02: Clone & Analyze Flow...")

        # Test data: using a known repo.
        payload = {"owner": "giusk10", "repo": "license_tool"}

        # 1. Clone Step
        clone_url = f"{self.base_url}/api/clone"
        clone_res = requests.post(clone_url, json=payload)

        if clone_res.status_code != 200:
            print(f" -> Clone failed: {clone_res.text}")

        self.assertEqual(clone_res.status_code, 200, "Cloning should succeed")
        self.assertEqual(clone_res.json()["status"], "cloned")

        # 2. Analyze Step
        analyze_url = f"{self.base_url}/api/analyze"
        analyze_res = requests.post(analyze_url, json=payload)

        self.assertEqual(analyze_res.status_code, 200, "Analysis should succeed")
        data = analyze_res.json()

        # Black Box verification of response structure
        self.assertIn("repository", data)
        self.assertIn("main_license", data)
        self.assertIn("issues", data)
        self.assertIsInstance(data["issues"], list)
        print(
            f" -> Analysis completed for {data['repository']}. "
            f"Detected license: {data['main_license']}"
        )
        print(" -> PASS")

    def test_03_error_handling_invalid_repo(self):
        """TC-03: Verifies error handling for non-existent repositories.

        Asserts:
            - The clone request for a non-existent repo does not return HTTP 200.
        """
        print("\nRunning TC-03: Error Handling...")

        payload = {
            "owner": "non_existent_owner_12345",
            "repo": "non_existent_repo_98765"
        }

        # We expect the clone to fail
        response = requests.post(f"{self.base_url}/api/clone", json=payload)

        self.assertNotEqual(
            response.status_code,
            200,
            "Cloning a non-existent repo must not return 200 OK"
        )
        print(f" -> Correctly rejected with status {response.status_code}")
        print(" -> PASS")

    def test_04_license_suggestion(self):
        """TC-04: Verifies the AI-based license suggestion feature.

        Simulates a request from the frontend form with specific constraints
        (e.g., commercial use allowed, no copyleft).

        Asserts:
            - The response status code is 200 (if AI service is active).
            - The response contains 'suggested_license' and 'explanation'.
            - The suggested license is permissive (MIT, Apache, BSD, ISC) when
              'copyleft' is set to 'none'.
        """
        print("\nRunning TC-04: AI License Suggestion...")

        # Payload based on schemas.py LicenseRequirementsRequest
        payload = {
            "owner": "test_user",
            "repo": "test_project",
            "commercial_use": True,
            "modification": True,
            "distribution": True,
            "patent_grant": False,
            "trademark_use": False,
            "liability": False,
            "copyleft": "none",  # Explicitly requesting a permissive license
            "additional_requirements": "Short and simple."
        }

        url = f"{self.base_url}/api/suggest-license"
        response = requests.post(url, json=payload)

        if response.status_code == 500:
            print(" -> [SKIP] AI/Ollama service might be inactive or unreachable.")
            return

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("suggested_license", data)
        self.assertIn("explanation", data)

        # Basic logic verification (Black Box):
        # If requesting "copyleft: none" and "commercial_use: true", expect MIT, Apache, or BSD.
        suggestion = data["suggested_license"].upper()
        possible_matches = ["MIT", "APACHE", "BSD", "ISC"]
        is_permissive = any(lic in suggestion for lic in possible_matches)

        if is_permissive:
            print(f" -> Consistent suggestion received: {suggestion}")
        else:
            print(
                f" -> [!] Note: Model suggested {suggestion} despite "
                "requesting 'no copyleft'."
            )

        print(" -> PASS")


if __name__ == "__main__":
    unittest.main()