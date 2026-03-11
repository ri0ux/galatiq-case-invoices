from typing import List, Optional
from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    item: Optional[str] = Field(None, description="Item related to the issue, if applicable")
    issue_type: str = Field(..., description="Type of validation problem")
    message: str = Field(..., description="Human readable description of the issue")


class ValidationResult(BaseModel):
    status: str = Field(...,description="Overall validation status: passed or failed")
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="List of validation issues discovered"
    )