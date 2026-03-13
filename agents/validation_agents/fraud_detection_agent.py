from typing import cast

from agno.agent import Agent
from agno.models.openai import OpenAIResponses

from models.invoice_schema import Invoice
from models.validation_schema import FraudCheckResult


class FraudDetectionAgent:
    def __init__(self) -> None:
        self.fraud_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=FraudCheckResult,
            instructions="""
            You are a fraud screening specialist for invoice processing.

            Review this invoice for fraud or social engineering signals ONLY.

            You may flag ONLY these issue types:
            - Suspicious Vendor Naming
            - Unusually Urgent Due Date
            - Urgent Payment Terms
            - Coercive Payment Language
            - Suspicious Payment Instructions
            - Suspicious Amount

            Important rules:
            - Missing vendor address by itself is NOT enough to flag fraud.
            - Only consider missing vendor address as supporting context when there are stronger suspicious indicators already present.
            - Be conservative. Ordinary invoices with missing address alone should return no fraud issues.
            - If there is no clear fraud or social engineering signal, return suspicious=false and an empty issues list.

            You must NOT validate:
            - arithmetic
            - totals
            - inventory
            - duplicates
            - formatting
            - general field completeness
            """,
        )

    def run(self, invoice: Invoice) -> FraudCheckResult:
        prompt = f"""
        Invoice:
        - invoice_number: {invoice.invoice_number}
        - vendor_name: {invoice.vendor.name if invoice.vendor else None}
        - vendor_address: {invoice.vendor.address if invoice.vendor else None}
        - invoice_date: {invoice.invoice_date}
        - due_date: {invoice.due_date}
        - total: {invoice.total}
        - currency: {invoice.currency}
        - payment_terms: {invoice.payment_terms}
        - notes: {invoice.notes}
        """
        result = self.fraud_agent.run(prompt)
        return cast(FraudCheckResult, result.content)