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
    compatible: bool | None
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
        needs_license_suggestion (bool): Indicates if a license suggestion form should be shown.
    """
    repository: str
    main_license: str
    issues: List[LicenseIssue]
    needs_license_suggestion: bool = False


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


# ------------------------------------------------------------------
# LICENSE SUGGESTION MODELS
# ------------------------------------------------------------------

class LicenseRequirementsRequest(BaseModel):
    """
    Represents user requirements and constraints for license suggestion.

    Attributes:
        owner (str): The repository owner.
        repo (str): The repository name.
        commercial_use (bool): Whether commercial use is required.
        modification (bool): Whether modification is allowed.
        distribution (bool): Whether distribution is allowed.
        patent_grant (bool): Whether patent grant is needed.
        trademark_use (bool): Whether trademark use is needed.
        liability (bool): Whether liability protection is needed.
        copyleft (Optional[str]): Copyleft preference: "strong", "weak", "none", or None.
        additional_requirements (Optional[str]): Any additional free-text requirements.
        detected_licenses (Optional[List[str]]): List of licenses already detected in the project.
    """
    owner: str
    repo: str
    commercial_use: bool = True
    modification: bool = True
    distribution: bool = True
    patent_grant: bool = False
    trademark_use: bool = False
    liability: bool = False
    copyleft: Optional[str] = None  # "strong", "weak", "none"
    additional_requirements: Optional[str] = None
    detected_licenses: Optional[List[str]] = None


class LicenseSuggestionResponse(BaseModel):
    """
    Represents the AI-generated license suggestion response.

    Attributes:
        suggested_license (str): The recommended license identifier.
        explanation (str): Explanation of why this license was suggested.
        alternatives (Optional[List[str]]): Alternative license options.
    """
    suggested_license: str
    explanation: str
    alternatives: Optional[List[str]] = None


