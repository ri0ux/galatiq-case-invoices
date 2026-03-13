import argparse
import os
import asyncio
from agents import approval_agent
from agents.ingestion_agent import IngestionAgent
from agents.validation_agent import ValidationAgent
from agents.approval_agent import ApprovalAgent
from utils.file_loader import load_single_invoice, load_invoice_directory
from utils.invoice_canonicalizer import canonicalize_invoices
from models.invoice_schema import RawInvoiceFile
from models.invoice_state import GLOBAL_INVOICE_STATE
from utils.item_aggregation import item_summarizer
import json


def load_invoice(path: str) -> RawInvoiceFile:
    """
    Load a single invoice file and return a RawInvoiceFile object.
    """
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

    ingestion_agent = IngestionAgent()
    validation_agent = ValidationAgent()
    approval_agent = ApprovalAgent()

    # 1. Create a list of extraction coroutine objects
    tasks = [
        ingestion_agent.invoice_extractor(file_name, raw_invoice) 
        for file_name, raw_invoice in invoices.items()
    ]
    
    # 2. Run all extraction tasks concurrently
    # The '*' unpacks the list so gather sees gather(coro1, coro2, ...)
    await asyncio.gather(*tasks)

    # 3. Validation and Summarization usually require the previous steps 
    # to be finished (Map-Reduce pattern)
    # invoice_findings = validation_agent.invoice_validator()
    
    # items = ingestion_agent.item_summarizer()

    # approval_agent.run()
    # summary= item_summarizer()

    canonical_invoices, conflicts = canonicalize_invoices()
    res = validation_agent.run()
    res = approval_agent.run()
    
    # print("\n================ FINAL GLOBAL OUTPUT ================")
    with open("final_invoice_state.json", "w", encoding="utf-8") as f:
        json.dump(
            GLOBAL_INVOICE_STATE.model_dump(), 
            f, 
            indent=2, 
            default=str,
            ensure_ascii=False  # Keeps symbols like € or £ readable
    )

    print("✅ Global state successfully exported to final_invoice_state.json")
    # print("=====================================================")

if __name__ == "__main__":
    # 4. Use asyncio.run to start the event loop
    asyncio.run(main())