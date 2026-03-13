import asyncio
import os
from init_db import initialize_database
from orchestration.workflow import run_invoice_pipeline
from utils.cli import parse_cli_args
from utils.invoice_loader import load_invoices_from_input


async def main():

    args = parse_cli_args()

    invoices = load_invoices_from_input(
        invoice_path=args.invoice_path,
        invoice_dir=args.invoice_dir
    )
    if not os.path.exists("inventory.db"):
        print("Initializing inventory database...")
        initialize_database()

    if not invoices:
        print("No invoices loaded.")
        return

    await run_invoice_pipeline(invoices)


if __name__ == "__main__":
    asyncio.run(main())