import os
from typing import List
from ..models.schemas import LicenseIssue


def generate_report(repo_path: str, main_license: str, issues: List[LicenseIssue]) -> str:
    """
    Genera un report di testo nella root del repo clonato.
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
