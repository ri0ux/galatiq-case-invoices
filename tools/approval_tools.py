from typing import Dict, Any

from models.invoice_state import GLOBAL_INVOICE_STATE


def get_invoice(invoice_number: str) -> Dict[str, Any]:
    """
    Tool: Retrieve canonical invoice data.
    """

    invoice = GLOBAL_INVOICE_STATE.canonical_invoices.get(invoice_number)

    if not invoice:
        return {"error": f"Invoice {invoice_number} not found"}

    return invoice.model_dump()


def get_validation_summary(invoice_number: str) -> Dict[str, Any]:
    """
    Tool: Retrieve validation results for an invoice.
    """

    validation = GLOBAL_INVOICE_STATE.invoice_validations.get(invoice_number)

    if not validation:
        return {"error": f"No validation record for invoice {invoice_number}"}

    return validation.model_dump()


def get_policy_lane(invoice_number: str) -> Dict[str, Any]:
    """
    Tool: Retrieve the deterministic policy lane assigned to the invoice.
    """

    approvals = GLOBAL_INVOICE_STATE.approvals
    validations = GLOBAL_INVOICE_STATE.invoice_validations
    invoices = GLOBAL_INVOICE_STATE.canonical_invoices

    if invoice_number not in invoices:
        return {"error": f"Invoice {invoice_number} not found"}

    invoice = invoices[invoice_number]
    validation = validations.get(invoice_number)

    hard_reject_issue_types = {
        "Unknown Item",
        "Negative Total",
        "Invalid Dates",
        "Out of Stock",
        "Missing Vendor",
    }

    suspicious_issue_types = {
        "Suspicious Vendor Naming",
        "Suspicious Payment Instructions",
        "Coercive Payment Language",
        "Urgent Payment Terms",
        "Unusually Urgent Due Date",
        "Suspicious Amount",
    }

    if validation is None:
        lane = "manual_review_candidate"

    else:
        issue_types = {issue.issue_type for issue in validation.issues}

        if issue_types & hard_reject_issue_types:
            lane = "auto_reject_candidate"

        elif issue_types & suspicious_issue_types:
            lane = "manual_review_candidate"

        elif invoice.total is not None and invoice.total > 10000:
            lane = "manual_review_candidate"

        elif validation.issues:
            lane = "manual_review_candidate"

        else:
            lane = "auto_approve_candidate"

    return {
        "invoice_number": invoice_number,
        "policy_lane": lane
    }