from typing import List, Dict
from models.approval_schema import ApprovalDecision
from models.invoice_schema import Invoice, LineItem
from models.validation_schema import AggregatedItemDemand, InvoiceValidation, ItemValidation
from pydantic import BaseModel, Field


class GlobalInvoiceState(BaseModel):
    """
    Shared state for all agents, using your exact models.
    """
    invoices: Dict[str, Invoice] = Field(default_factory=dict)
    canonical_invoices: Dict[str, Invoice] = Field(default_factory=dict)
    invoice_conflicts: List[InvoiceValidation] = Field(default_factory=list)

    item_validations: Dict[str, ItemValidation] = Field(default_factory=dict)
    invoice_validations: Dict[str, InvoiceValidation] = Field(default_factory=dict)

    items: List[AggregatedItemDemand] = Field(default_factory=list)

    approvals: Dict[str, ApprovalDecision] = Field(default_factory=dict)
    payment_results: Dict[str, dict] = Field(default_factory=dict)


# Singleton instance that all agents can import and update
GLOBAL_INVOICE_STATE = GlobalInvoiceState()