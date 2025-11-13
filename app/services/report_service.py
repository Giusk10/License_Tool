import os
from typing import List

def generate_report(repo_path: str, main_license: str, issues: List[dict]) -> str:
    report_dir = os.path.join(repo_path, "report")
    os.makedirs(report_dir, exist_ok=True)
    out_path = os.path.join(report_dir, "license_report.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("📄 License Compatibility Report\n")
        f.write("---------------------------------\n")
        f.write(f"Licenza principale: {main_license}\n\n")

        for issue in issues:
            # issue è un dict, non un oggetto
            status = "✅ Compatibile" if issue["compatible"] else "❌ Incompatibile"

            f.write(f"- {issue['file']} → {issue['license']} {status}\n")

            if issue.get("reason"):
                f.write(f"  Motivo: {issue['reason']}\n")
            if issue.get("suggestion"):
                f.write(f"  Suggerimento AI: {issue['suggestion']}\n")
            if issue.get("regenerated_code_path"):
                f.write(f"  Codice rigenerato: {issue['regenerated_code_path']}\n")

            f.write("\n")

    return out_path
