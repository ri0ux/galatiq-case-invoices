from pydantic import BaseModel, Field
from typing import Optional


class PaymentResult(BaseModel):
    invoice_number: str = Field(..., description="Invoice being processed")
    payment_status: str = Field(..., description="Result of payment attempt: success, failed, or not_paid")
    approved: bool = Field(..., description="Whether the invoice was approved for payment")
    decision_status: str = Field(..., description="Approval decision status: approved, rejected, or manual_review")
    vendor: Optional[str] = Field(None, description="Vendor receiving the payment")
    amount: Optional[float] = Field(None, description="Invoice total amount paid")
    reason: Optional[str] = Field(None, description="Reason for approval or rejection")
    risk_score: Optional[int] = Field(None, description="Risk score from approval agent")