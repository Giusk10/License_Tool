"""
This module generates a human-readable text report summarizing the license analysis,
including compatibility status, AI suggestions, and paths to regenerated code.
"""

import os
from typing import List
from app.models.schemas import LicenseIssue

def generate_report(repo_path: str, main_license: str, issues: List[LicenseIssue]) -> str:
    """
    Generates a text report summarizing license compatibility issues.

    Args:
        repo_path (str): The path to the repository.
        main_license (str): The main license of the repository.
        issues (List[LicenseIssue]): A list of license issues detected.

    Returns:
        str: The path to the generated report file.
    """
    report_path = os.path.join(repo_path, "LICENSE_REPORT.txt")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("📄 License Compatibility Report\n")
        f.write("---------------------------------\n")
        f.write(f"Licenza principale: {main_license}\n\n")

        for issue in issues:
            status = "✅ Compatibile" if issue.compatible else "❌ Incompatibile"
            f.write(f"- {issue.file_path} → {issue.detected_license} {status}\n")
            if issue.reason:
                f.write(f"  Motivo: {issue.reason}\n")
            if issue.suggestion:
                f.write(f"  Suggerimento AI: {issue.suggestion}\n")
            if issue.regenerated_code_path:
                f.write(f"  Codice rigenerato: {issue.regenerated_code_path}\n")
            f.write("\n")

    return report_path
