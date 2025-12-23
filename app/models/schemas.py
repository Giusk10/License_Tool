"""
Schemas Module.

This module defines the Pydantic models used for data validation
in API requests and responses. It includes schemas for analysis requests,
license issue reporting, and repository cloning results.
"""

from typing import List, Optional
from pydantic import BaseModel

# ------------------------------------------------------------------
# REQUEST MODELS
# ------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """
    Represents the request payload for analyzing a repository.

    Attributes:
        owner (str): The username or organization name of the repository owner.
        repo (str): The name of the repository.
    """
    owner: str
    repo: str


# ------------------------------------------------------------------
# COMPONENT MODELS
# ------------------------------------------------------------------

class LicenseIssue(BaseModel):
    """
    Represents a single license compatibility issue or violation within a file.

    Attributes:
        file_path (str): The relative path to the file containing the issue.
        detected_license (str): The license identifier detected in the file.
        compatible (bool): Indicates if the file's license is compatible with the project.
        reason (Optional[str]): Explanation of why the license is incompatible.
        suggestion (Optional[str]): AI-generated suggestion to resolve the issue.
        licenses (Optional[str]): Additional license details or raw identification strings.
        regenerated_code_path (Optional[str]): Path to a locally generated file with fixes.
    """
    file_path: str
    detected_license: str
    compatible: bool
    reason: Optional[str] = None
    suggestion: Optional[str] = None
    licenses: Optional[str] = None
    regenerated_code_path: Optional[str] = None


# ------------------------------------------------------------------
# RESPONSE MODELS
# ------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    """
    Represents the main response payload for the analysis endpoint.

    Attributes:
        repository (str): The full repository name (e.g., "owner/repo").
        main_license (str): The primary license identified for the project.
        issues (List[LicenseIssue]): A list of detailed compatibility issues found.
    """
    repository: str
    main_license: str
    issues: List[LicenseIssue]


# ------------------------------------------------------------------
# INTERNAL MODELS
# ------------------------------------------------------------------

class CloneResult(BaseModel):
    """
    Internal model to track the outcome of a repository cloning operation.

    Used for both GitHub cloning and ZIP uploads.

    Attributes:
        success (bool): True if the operation was successful, False otherwise.
        repo_path (Optional[str]): The local file system path to the cloned/uploaded repo.
        error (Optional[str]): Error message if the operation failed.
    """
    success: bool
    repo_path: Optional[str] = None
    error: Optional[str] = None
