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
                        Extract structured invoice data from the following text. Return it structured in the manner provided.
                        Invoice text:
                        {json.dumps(raw_invoice.model_dump(), indent=2)}
                         """
                            )
        # Explicit cast for type checking
        invoice = cast(Invoice, run_output.content)
        # update gloab invoice object
        GLOBAL_INVOICE_STATE.invoices[file_name] = invoice
        return invoice
    
    def item_summarizer(self) -> ItemCollection:

        invoices = GLOBAL_INVOICE_STATE.invoices
        all_invoices = list(invoices.values())

        batch_size = 5
        intermediate_collections = []


        for i in range(0, len(all_invoices), batch_size):

            batch = all_invoices[i : i + batch_size]

            items_to_process = [inv.model_dump() for inv in batch]

            run = self.item_agent.run(
                f"""
            You are an expert invoice processor.

            You will receive invoices and have access to a tool to get potential issues detected by a validation agent

            The validation agent is very patricular, so make an expert decision on whether to let the validation impact your decision making for your job

            Your job:

            1. Detect duplicate invoices.
            - If the same invoice_number appears multiple times,
            choose the most recent or highest revision.

            2. Detect revisions.
            Examples:
            - INV-1001-R1
            - Invoice 1001 Rev 2
            - Notes saying "revised"

            3. Only include items from the **latest valid invoice**.

            4. Merge duplicate items across invoices:
            - Ignore case
            - Ignore spacing
            - Ignore minor modifiers like "(rush order)"

            5. Aggregate totals:
            - Sum quantities
            - Sum total_price

            6. If total_price is missing:
            compute quantity * unit_price.

            Return the final consolidated ItemCollection.

            Invoices:
            {items_to_process}
            """
                    )

            intermediate_collections.append(cast(ItemCollection, run.content))

        final_run = self.item_agent.run(
            f"""
            Combine these collections into a single final ItemCollection.

            Rules:
            - Merge duplicate items
            - Ignore case differences
            - Aggregate quantities and totals

            Collections:
            {[c.model_dump() for c in intermediate_collections]}
            """
        )
        final = cast(ItemCollection, final_run.content)
        GLOBAL_INVOICE_STATE.items = final.items

        return cast(ItemCollection, final_run.content)