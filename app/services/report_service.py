import os
from typing import List
from app.models.schemas import LicenseIssue


def generate_report(repo_path: str, main_license: str, issues: List[LicenseIssue]) -> str:
    """
    Genera un report di testo nella root del repo clonato.
    """
    report_path = os.path.join(repo_path, "LICENSE_REPORT.txt")

    return report_path
