import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
import shutil
from app.services.analysis_workflow import run_analysis_logic
from app.models.schemas import CloneResult

class TestRegeneration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.test_dir, "test_repo")
        os.makedirs(self.repo_path)
        
        # Create a dummy incompatible file
        self.file_path = os.path.join(self.repo_path, "bad_license.py")
        with open(self.file_path, "w") as f:
            f.write("# License: GPL-3.0\ndef foo(): pass")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("app.services.analysis_workflow.clone_repo")
    @patch("app.services.analysis_workflow.run_scancode")
    @patch("app.services.analysis_workflow.detect_main_license_scancode")
    @patch("app.services.analysis_workflow.filter_with_llm")
    @patch("app.services.analysis_workflow.extract_file_licenses_from_llm")
    @patch("app.services.analysis_workflow.check_compatibility")
    @patch("app.services.code_generator._call_ollama")
    @patch("app.services.analysis_workflow.generate_report")
    def test_regeneration_flow(self, mock_report, mock_ollama, mock_compat, mock_extract, mock_filter, mock_detect, mock_scan, mock_clone):
        # Mock Clone
        mock_clone.return_value = CloneResult(success=True, repo_path=self.repo_path)
        
        # Mock ScanCode (called twice)
        mock_scan.return_value = {"files": []} # dummy
        
        # Mock Main License
        mock_detect.return_value = "MIT"
        
        # Mock LLM Filter & Extract (called twice)
        # First pass: GPL
        # Second pass: MIT (after regen)
        mock_extract.side_effect = [
            {"bad_license.py": "GPL-3.0"}, # First pass
            {"bad_license.py": "MIT"}       # Second pass
        ]
        
        # Mock Compatibility (called twice)
        # First pass: Incompatible
        # Second pass: Compatible
        mock_compat.side_effect = [
            {"issues": [{"file_path": "bad_license.py", "detected_license": "GPL-3.0", "compatible": False, "reason": "GPL != MIT"}]},
            {"issues": [{"file_path": "bad_license.py", "detected_license": "MIT", "compatible": True, "reason": "MIT == MIT"}]}
        ]
        
        # Mock Ollama (Regeneration)
        mock_ollama.return_value = "# License: MIT\ndef foo(): pass # Fixed"
        
        # Mock Report
        mock_report.return_value = "/tmp/report.txt"

        # Run
        response = run_analysis_logic("owner", "repo", "token")
        
        # Verify
        # 1. File should be overwritten
        with open(self.file_path, "r") as f:
            content = f.read()
            self.assertIn("Fixed", content)
            self.assertIn("MIT", content)
            
        # 2. Response should have regenerated_code_path populated with content
        issue = response.issues[0]
        self.assertEqual(issue.file_path, "bad_license.py")
        self.assertTrue(issue.compatible) # Should be from the second pass
        self.assertIn("Fixed", issue.regenerated_code_path)

if __name__ == "__main__":
    unittest.main()
