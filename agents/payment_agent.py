import json
from typing import Dict, cast

from agno.agent import Agent
from agno.models.openai import OpenAIResponses

from models.invoice_state import GLOBAL_INVOICE_STATE
from models.payment_schema import PaymentResult
from tools.payment_tools import mock_payment


class PaymentAgent:
    def __init__(self) -> None:
        self.payment_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=PaymentResult,
            instructions=(
                "You are a payment processor agent. "
                "You will be given an invoice and an approval decision made by another LLM. "
                "If the approval decision says the invoice is approved, use the payment tool to make the payment. "
                "If the approval decision says the invoice is rejected or manual_review, do not use the payment tool. "
                "You are not a validator. You are only deciding whether to execute payment based on the provided approval decision. "
                "Output a fully populated PaymentResult."
            ),
            tools=[mock_payment],
        )

    def run(self) -> Dict[str, PaymentResult]:
        payment_results: Dict[str, PaymentResult] = {}

        for invoice_number, invoice in GLOBAL_INVOICE_STATE.canonical_invoices.items():
            approval = GLOBAL_INVOICE_STATE.approvals[invoice_number]

            prompt = f"""
            Invoice:
            {json.dumps(invoice.model_dump(), indent=2, default=str)}

            Approval:
            {json.dumps(approval.model_dump(), indent=2, default=str)}
            """

            run_output = self.payment_agent.run(prompt)
            res = cast(PaymentResult, run_output.content)
            payment_results[invoice_number] = res

        return payment_results