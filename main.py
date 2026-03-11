import argparse
import os
from agents.ingestion_agent import IngestionAgent

from utils.file_loader import load_single_invoice, load_invoice_directory


def load_invoice(path: str) -> dict:
    """
    Load a single invoice file and return a structured state object.
    """

    print(f"\nProcessing invoice: {path}")

    ext = os.path.splitext(path)[1]
    raw_text = load_single_invoice(path)

    invoice_state = {
        "file_path": path,
        "file_type": ext,
        "raw_text": raw_text,
        "extracted_data": None,
        "validation": None,
        "approval": None,
        "payment": None
    }

    return invoice_state


def load_invoices_from_directory(directory: str) -> dict:
    """
    Load all invoices from a directory into memory.
    """

    files = load_invoice_directory(directory)

    if not files:
        print("No invoice files found.")
        return {}

    invoices = {}

    for file_path in files:
        invoice_state = load_invoice(file_path)
        invoices[file_path] = invoice_state

    return invoices


def main():

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

    invoices = {}

    if args.invoice_path:

        invoice_state = load_invoice(args.invoice_path)
        invoices[args.invoice_path] = invoice_state

    elif args.invoice_dir:

        invoices = load_invoices_from_directory(args.invoice_dir)

    else:

        print("Please provide either --invoice_path or --invoice_dir")
        return

    print("\n==============================")
    print(f"Loaded {len(invoices)} invoice(s) into memory")
    print("==============================\n")

    print("Starting AGENT")
    ingestion_agent = IngestionAgent()

    for path in invoices:
        print(ingestion_agent.get_response(invoices, path))


if __name__ == "__main__":
    main()