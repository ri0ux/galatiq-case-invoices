from typing import List, Optional
from pydantic import BaseModel, Field
import datetime


class LineItem(BaseModel):
    item: str = Field(..., description="Name of the product")
    quantity: int = Field(..., description="Quantity ordered")
    unit_price: float = Field(..., description="Price per unit")
    total_price: Optional[float] = Field(None, description="Optional total price")


class Vendor(BaseModel):
    name: str = Field(..., description="Vendor name")
    address: Optional[str] = Field(None, description="Vendor address")


class Invoice(BaseModel):
    invoice_number: str = Field(..., description="Unique invoice ID")
    vendor: Vendor
    invoice_date: Optional[str] = Field(None, description="Invoice creation date")
    due_date: Optional[str] = Field(None, description="Invoice due date")
    line_items: List[LineItem] = Field(..., description="List of items in invoice")
    subtotal: Optional[float] = Field(None, description="Subtotal amount")
    tax_rate: Optional[float] = Field(0.0, description="Tax rate as decimal")
    tax_amount: Optional[float] = Field(0.0, description="Calculated tax amount")
    total: Optional[float] = Field(None, description="Total invoice amount")
    currency: str = Field("USD", description="Currency code")
    payment_terms: Optional[str] = Field(None, description="Payment terms")
    @property
    def invoice_date_parsed(self):
        if self.invoice_date:
            return datetime.datetime.strptime(self.invoice_date, "%B %d, %Y").date()
        return None