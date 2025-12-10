from typing import List, Optional
from pydantic import BaseModel

# ----- REQUEST -----
class AnalyzeRequest(BaseModel):
    owner: str
    repo: str

# ----- ISSUE (nuovo formato compatibile con i tuoi dict) -----
class LicenseIssue(BaseModel):
    file_path: str
    detected_license: str
    compatible: bool
    reason: Optional[str] = None
    suggestion: Optional[str] = None
    licenses: Optional[str] = None
    regenerated_code_path: Optional[str] = None

# ----- RESPONSE -----
class AnalyzeResponse(BaseModel):
    repository: str
    main_license: str
    issues: List[LicenseIssue]   # usa il nuovo formato
    report_path: str

# ----- GITHUB CLONE RESULT (lo lasciamo invariato!) -----
class CloneResult(BaseModel):
    success: bool
    repo_path: Optional[str] = None
    error: Optional[str] = None
