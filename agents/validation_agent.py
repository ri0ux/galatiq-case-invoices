from agno.agent import Agent
import json
from agno.models.openai import OpenAIResponses
from models.validation_schema import InvoiceValidation, ItemValidation
from models.invoice_state import GLOBAL_INVOICE_STATE
from tools.inventory_tools import get_count_of_item
from typing import cast, Dict, List
from pydantic import BaseModel, Field

class InvoiceValidationCollection(BaseModel):
    # Change default_factory to list to match the List type hint
    invoice_validations: List[InvoiceValidation] = Field(default_factory=list, description="A list of invoice validation results")

class ValidationAgent:

    def __init__(self):
        self.item_validator_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=InvoiceValidation,
            # eventually add more validation tools
            tools=[get_count_of_item]
            )
        self.invoice_validator_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=InvoiceValidationCollection,
        )

    def invoice_validator(self):
        invoices = GLOBAL_INVOICE_STATE.invoices
        invoice_data_for_ai = {name: inv.model_dump() for name, inv in invoices.items()}

        prompt = f"""
            You are validating these structured invoices:
            {json.dumps(invoice_data_for_ai, indent=2, default=str)}

            Flag duplicate numbers, revisions, and suspicious data. DO not just flag any random thing, be very particular about what you flag. Take your time with determing what is suspicious when raising an issue.
        """

        run = self.invoice_validator_agent.run(prompt)
        
        # 1. Cast to the ACTUAL schema type you defined for the agent
        validated_data = cast(InvoiceValidationCollection, run.content)
        
        # 2. Extract the actual LIST of objects from the collection
        result_list = validated_data.invoice_validations
        
        # 3. Save that list to the global state
        GLOBAL_INVOICE_STATE.invoice_validations = result_list 
        
        return result_list


    def item_validation(self, invoice_state):

        invoice = invoice_state["extracted_data"]

        prompt = f"""
                You are validating an invoice.

                Invoice data:
                {invoice}

                Use the available tools to check inventory.

                Flag:
                - item not found
                - quantity exceeds stock
                - negative quantity
                - or any other suspicious information

                """

        run = self.item_validator_agent.run(prompt)

        result = cast(InvoiceValidation, run.content)

        invoice_state["validation"] = result

        return invoice_state