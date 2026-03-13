from pydantic import BaseModel

class ApprovalDecision(BaseModel):
    invoice_number: str
    approved: bool
    status: str   # approved, rejected, manual_review
    reason: str
    risk_score: int