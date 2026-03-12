from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field
import datetime


class LineItem(BaseModel):
    item: str = Field(..., description="Name of the product")
    quantity: int = Field(..., description="Quantity ordered")
    unit_price: float = Field(..., description="Price per unit")
    total_price: Optional[float] = Field(None, description="Optional total price")


class ItemCollection(BaseModel):
    items: List[LineItem] = Field(default_factory=list)


class Vendor(BaseModel):
    name: str = Field(..., description="Vendor name")
    address: Optional[str] = Field(None, description="Vendor address")


class Invoice(BaseModel):
    invoice_number: str = Field(..., description="Unique invoice ID, file name without the file type")
    file_name: str = Field(..., description="file name of invoice file (data/pdfs/filename.pdf)")
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
    notes: Optional[str] = Field(None, description="Notes about the invoice, anything odd that should be noted, for example, it maybe is the revised version")
    @property
    def invoice_date_parsed(self):
        if self.invoice_date:
            return datetime.datetime.strptime(self.invoice_date, "%B %d, %Y").date()
        return None


class RawInvoiceFile(BaseModel):
    file_path: str = Field(..., description="Path to the invoice file")
    file_type: str = Field(..., description="File extension type such as .pdf, .txt, .json")
    raw_text: str = Field(..., description="Extracted text content from the invoice file")

    # populated later by ingestion agent
    extracted_invoice_number: Optional[str] = Field(
        None, description="Invoice number detected during extraction"
    )