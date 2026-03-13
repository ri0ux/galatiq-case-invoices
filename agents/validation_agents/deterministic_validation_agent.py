from typing import Dict, List

from models.invoice_schema import Invoice
from models.validation_schema import (
    AggregatedItemDemand,
    InvoiceValidation,
    ItemValidation,
    ValidationIssue,
)
from tools.validation_tools import (
    calculate_inventory_pressure,
    validate_aggregate_item_pressure,
    validate_arithmetic,
    validate_dates,
    validate_required_fields,
    validate_sequential_inventory_allocation,
)
from utils.normalizer import dedupe_issues, normalize_issues


class DeterministicValidationAgent:
    def run_invoice_checks(
        self,
        canonical_invoices: Dict[str, Invoice],
    ) -> Dict[str, InvoiceValidation]:
        invoice_results: Dict[str, InvoiceValidation] = {}

        for invoice_number, invoice in canonical_invoices.items():
            issues: List[ValidationIssue] = []
            issues.extend(validate_required_fields(invoice))
            issues.extend(validate_dates(invoice))
            issues.extend(validate_arithmetic(invoice))

            issues = normalize_issues(issues)

            invoice_results[invoice_number] = InvoiceValidation(
                file_name=invoice.file_name,
                invoice_number=invoice_number,
                status="failed" if issues else "passed",
                issues=issues,
            )

        return invoice_results

    def run_item_checks(
        self,
        canonical_invoices: Dict[str, Invoice],
    ) -> tuple[
        List[AggregatedItemDemand],
        Dict[str, ItemValidation],
        Dict[str, List[ValidationIssue]],
    ]:
        aggregated_items, _ = calculate_inventory_pressure(canonical_invoices)
        item_validations = validate_aggregate_item_pressure(aggregated_items)
        sequential_inventory_issues = validate_sequential_inventory_allocation(
            canonical_invoices
        )

        return aggregated_items, item_validations, sequential_inventory_issues

    def merge_inventory_issues(
        self,
        invoice_results: Dict[str, InvoiceValidation],
        sequential_inventory_issues: Dict[str, List[ValidationIssue]],
    ) -> Dict[str, InvoiceValidation]:
        for invoice_number, issues in sequential_inventory_issues.items():
            if invoice_number in invoice_results:
                invoice_results[invoice_number].issues.extend(normalize_issues(issues))

        for invoice_number, validation in invoice_results.items():
            validation.issues = dedupe_issues(validation.issues)
            validation.status = "failed" if validation.issues else "passed"

        return invoice_results