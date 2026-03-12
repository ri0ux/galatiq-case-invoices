import argparse
import os
import asyncio
from agents.ingestion_agent import IngestionAgent
from agents.validation_agent import ValidationAgent
from utils.file_loader import load_single_invoice, load_invoice_directory
from models.invoice_schema import RawInvoiceFile
from models.invoice_state import GLOBAL_INVOICE_STATE


def load_invoice(path: str) -> RawInvoiceFile:
    """
    Load a single invoice file and return a RawInvoiceFile object.
    """

    print(f"\nProcessing invoice: {path}")

    ext = os.path.splitext(path)[1]
    raw_text = load_single_invoice(path)

    raw_invoice = RawInvoiceFile(
        file_path=path,
        file_type=ext,
        raw_text=raw_text,
        extracted_invoice_number=None
    )

    return raw_invoice


def load_invoices_from_directory(directory: str) -> dict[str, RawInvoiceFile]:
    """
    Load all invoices from a directory into memory.
    """

    files = load_invoice_directory(directory)

    if not files:
        print("No invoice files found.")
        return {}

    invoices: dict[str, RawInvoiceFile] = {}

    for file_path in files:
        invoice_state = load_invoice(file_path)
        invoices[file_path] = invoice_state

    return invoices


def command_line_parser() -> dict[str, RawInvoiceFile] | None:

    parser = argparse.ArgumentParser(
        description="AI Invoice Processing System"
    )

    parser.add_argument(
        "--invoice_path",
        type=str,
        help="Path to a single invoice file"
    )

    parser.add_argument(
        "--invoice_dir",
        type=str,
        help="Path to a directory containing invoice files"
    )

    args = parser.parse_args()

    invoices: dict[str, RawInvoiceFile] = {}

    if args.invoice_path:

        invoice_state = load_invoice(args.invoice_path)
        invoices[args.invoice_path] = invoice_state

    elif args.invoice_dir:

        invoices = load_invoices_from_directory(args.invoice_dir)

    else:

        print("Please provide either --invoice_path or --invoice_dir")
        return None

    return invoices


async def main():
    invoices = command_line_parser()
    if not invoices:
        return

    print(f"\nStarting AGENT on {len(invoices)} invoices...")

    ingestion_agent = IngestionAgent()
    validation_agent = ValidationAgent()

    # 1. Create a list of extraction coroutine objects
    tasks = [
        ingestion_agent.invoice_extractor(file_name, raw_invoice) 
        for file_name, raw_invoice in invoices.items()
    ]
    
    # 2. Run all extraction tasks concurrently
    # The '*' unpacks the list so gather sees gather(coro1, coro2, ...)
    print("Extracting data from all invoices concurrently...")
    await asyncio.gather(*tasks)

    # 3. Validation and Summarization usually require the previous steps 
    # to be finished (Map-Reduce pattern)
    print("Validating invoices...")
    invoice_findings = validation_agent.invoice_validator()
    print("Invoice findings: ",invoice_findings)
    
    print("Summarizing final item collection...")
    items = ingestion_agent.item_summarizer()
    
    print("\nFINAL ITEMS:\n", items)

if __name__ == "__main__":
    # 4. Use asyncio.run to start the event loop
    asyncio.run(main())