from typing import List, Optional
from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    item: Optional[str] = Field(None, description="Item related to the issue, if applicable")
    issue_type: str = Field(..., description="Type of validation problem")
    message: str = Field(..., description="Human readable description of the issue")


class InvoiceValidation(BaseModel):
    file_name: str = Field(..., description="Name of invoice file")
    invoice_number: str = Field(..., description="Unique invoice ID")
    status: str = Field(...,description="Overall validation status: passed or failed")
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="List of validation issues discovered"
    )
class ItemValidation(BaseModel):
    item_name: str = Field(..., description="Unique item name")
    status: str = Field(...,description="Overall validation status: passed or failed")
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="List of validation issues discovered"
    )

class FraudCheckResult(BaseModel):
    suspicious: bool = Field(..., description="Whether the invoice appears suspicious")
    issues: List[ValidationIssue] = Field(default_factory=list)

class AggregatedItemDemand(BaseModel):
    normalized_item_name: str
    display_name: str
    total_quantity: int
    total_amount: float
    invoice_numbers: List[str] = Field(default_factory=list)

class NamingResult(BaseModel):
    name: str = Field(..., description="Canonical normalized item name used for inventory lookup")