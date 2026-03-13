from typing import Dict, List

from models.invoice_schema import Invoice
from models.validation_schema import (
    AggregatedItemDemand,
    InvoiceValidation,
    ItemValidation,
)
from utils.normalizer import dedupe_issues, normalize_issues
from agents.validation_agents.deterministic_validation_agent import DeterministicValidationAgent
from agents.validation_agents.fraud_detection_agent import FraudDetectionAgent


class ValidationTeam:
    def __init__(self) -> None:
        self.deterministic_agent = DeterministicValidationAgent()
        self.fraud_agent = FraudDetectionAgent()

    def run(
        self,
        canonical_invoices: Dict[str, Invoice],
    ) -> tuple[
        Dict[str, InvoiceValidation],
        Dict[str, ItemValidation],
        List[AggregatedItemDemand],
    ]:
        """
        Validation flow:
        1. Per-invoice deterministic validation
        2. Fraud screen
        3. Aggregate normalized item demand
        4. Aggregate inventory pressure -> item_validations
        5. Sequential stock allocation -> invoice-level inventory issues
        6. Dedupe invoice issues
        """
        invoice_results = self.deterministic_agent.run_invoice_checks(canonical_invoices)

        # Fraud checks
        for invoice_number, invoice in canonical_invoices.items():
            fraud_result = self.fraud_agent.run(invoice)

            if invoice_number in invoice_results:
                invoice_results[invoice_number].issues.extend(
                    normalize_issues(fraud_result.issues)
                )

        # Item + inventory checks
        aggregated_items, item_validations, sequential_inventory_issues = (
            self.deterministic_agent.run_item_checks(canonical_invoices)
        )

        invoice_results = self.deterministic_agent.merge_inventory_issues(
            invoice_results,
            sequential_inventory_issues,
        )

        # Final dedupe/status refresh after fraud + inventory merges
        for invoice_number, validation in invoice_results.items():
            validation.issues = dedupe_issues(validation.issues)
            validation.status = "failed" if validation.issues else "passed"

        return invoice_results, item_validations, aggregated_items