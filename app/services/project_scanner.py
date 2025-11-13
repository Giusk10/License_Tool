import os
from typing import List

SOURCE_EXTS = (".py", ".js", ".ts", ".rs", ".c", ".cpp", ".java", ".go", ".cs", ".md", ".txt")

def scan_project(root: str) -> List[str]:
    files: List[str] = []
    for path, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.lower().startswith("license"):
                files.append(os.path.join(path, fname))
            elif fname.endswith(SOURCE_EXTS):
                files.append(os.path.join(path, fname))
            elif fname in ("requirements.txt", "pyproject.toml", "package.json", "Cargo.toml"):
                files.append(os.path.join(path, fname))
    return files
