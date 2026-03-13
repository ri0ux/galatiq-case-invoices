from models.invoice_schema import RawInvoiceFile
from utils.file_loader import load_single_invoice, load_invoice_directory
import os


def load_invoice(path: str) -> RawInvoiceFile:

    ext = os.path.splitext(path)[1]
    raw_text = load_single_invoice(path)

    return RawInvoiceFile(
        file_path=path,
        file_type=ext,
        raw_text=raw_text,
        extracted_invoice_number=None
    )


def load_invoices_from_input(invoice_path=None, invoice_dir=None):

    invoices = {}

    if invoice_path:
        invoices[invoice_path] = load_invoice(invoice_path)

    elif invoice_dir:
        files = load_invoice_directory(invoice_dir)

        for path in files:
            invoices[path] = load_invoice(path)

    return invoices