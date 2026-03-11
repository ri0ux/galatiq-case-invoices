from ast import Dict

from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from models.invoice_schema import Invoice
from typing import cast
from dotenv import load_dotenv

load_dotenv()


class IngestionAgent():

    def __init__(self) -> None:
        self.agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=Invoice
            )
    def get_response(self, invoice_dict: dict, invoice_path: str) -> dict:
        invoice_state = invoice_dict[invoice_path]
        raw_text = invoice_state.get("raw_text", "")
        run_output = self.agent.run(input=raw_text)
        # explicitly tell compiler type of "RunOutput.content"
        invoice = cast(Invoice, run_output.content)
        invoice_state["extracted_data"] = invoice
        invoice_dict[invoice_path] = invoice_state
        return invoice_dict