from agno.agent import Agent
import asyncio
from agno.models.openai import OpenAIResponses
from models.invoice_schema import Invoice, ItemCollection, RawInvoiceFile
from models.invoice_state import GLOBAL_INVOICE_STATE 
from typing import cast, Dict, Any
from tools.parsing_tools import get_validation_by_file_name
import json
from dotenv import load_dotenv

load_dotenv()


class IngestionAgent:

    def __init__(self) -> None:
        self.invoice_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=Invoice
        )
        self.item_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=ItemCollection,
            tools=[get_validation_by_file_name]
            )

    async def invoice_extractor(self, file_name: str, raw_invoice: RawInvoiceFile) -> Invoice:
        """
        Extract structured invoice data from raw text.
        """

        run_output = self.invoice_agent.run(input=f"""
                Act as a precise invoice xtraction expert. Your task is to extract data from the provided Invoice Text and normalize it into a STRICT JSON format passed to you. 

                ### STANDARDIZATION RULES:
                1. INVOICE NUMBER: Always prefix with 'INV-'. If the number is '1002', convert it to 'INV-1002'. Remove any internal spaces (e.g., 'INV 1012' becomes 'INV-1012'). If an invoice is the revised version, the invoice will become: INV-1012-REV.
                2. FILE NAME: Always format as 'data/invoices/invoice_[NUMBER].extension'. Use the digits from the invoice number.
                3. DATES: Convert all dates (e.g., "Jan 30 2026", "01/30/26", "yesterday") into standard ISO 8601 format: YYYY-MM-DD.
                4. NUMBERS: Strip all currency symbols ($) and commas. All financial values must be valid Floats.
                5. MATH: If a line item 'total_price' is missing, calculate it manually as (quantity * unit_price).
                6. CURRENCY: Default to "USD" unless another code is explicitly mentioned.
                7. VENDOR: If the address is not explicitly stated, return null. Clean the vendor name of any obvious shorthand (e.g., "Vndr" -> "Vendor").  
                8. Do not make anything up. Simply extract the data into the given format.
                        \n\nInvoice text:
                        {json.dumps(raw_invoice.model_dump(), indent=2)}
                         """
                            )
        # Explicit cast for type checking
        invoice = cast(Invoice, run_output.content)
        # update gloab invoice object
        GLOBAL_INVOICE_STATE.invoices[file_name] = invoice
        return invoice
    
    