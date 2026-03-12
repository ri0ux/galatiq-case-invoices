from typing import List, Dict
from models.invoice_schema import Invoice, LineItem
from models.validation_schema import InvoiceValidation, ItemValidation
from pydantic import BaseModel, Field


class GlobalInvoiceState(BaseModel):
    """
    Shared state for all agents, using your exact models.
    """
    # All structured invoices keyed by file_name
    invoices: Dict[str, Invoice] = Field(default_factory=dict)

    # Item-level validations keyed by item_name
    item_validations: Dict[str, ItemValidation] = Field(default_factory=dict)

    # Invoice-level validations keyed by invoice_number
    invoice_validations: List[InvoiceValidation] = Field(default_factory=list)

    # Aggregated item collection
    items: List[LineItem] = Field(default_factory=list)


# Singleton instance that all agents can import and update
GLOBAL_INVOICE_STATE = GlobalInvoiceState()