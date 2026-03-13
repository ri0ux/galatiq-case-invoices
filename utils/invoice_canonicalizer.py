from collections import defaultdict
from typing import Dict, List, Tuple
import re

from models.invoice_schema import Invoice, LineItem
from models.validation_schema import InvoiceValidation, ValidationIssue
from models.invoice_state import GLOBAL_INVOICE_STATE


def normalize_item_name(name: str) -> str:
    """
    Normalize item names for business-level comparison.
    Examples:
    - "Widget A" -> "widgeta"
    - "WidgetA (rush order)" -> "widgeta"
    """
    value = (name or "").lower()
    value = re.sub(r"\(.*?\)", "", value)
    value = value.replace(" ", "")
    return value.strip()


def get_base_invoice_number(invoice_number: str) -> str:
    """
    Normalize invoice numbers so revisions collapse to the same base invoice.

    Examples:
    - INV-1004-REV -> INV-1004
    - INV-1004-R1  -> INV-1004
    - INV 1012     -> INV-1012
    """
    value = (invoice_number or "").strip().upper()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-REV$", "", value)
    value = re.sub(r"-R\d+$", "", value)
    return value


def is_revised_invoice(invoice: Invoice) -> bool:
    """
    Detect whether an invoice is an explicit revised version.
    """
    invoice_number = (invoice.invoice_number or "").upper()
    file_name = (invoice.file_name or "").lower()
    notes = (invoice.notes or "").lower()

    return (
        invoice_number.endswith("-REV")
        or bool(re.search(r"-R\d+$", invoice_number))
        or "revised" in file_name
        or "revised" in notes
        or "revision" in notes
    )


def normalize_line_items_for_signature(items: List[LineItem]) -> List[dict]:
    """
    Build a normalized, order-independent representation of line items
    for business-equivalence comparison.
    """
    normalized = []

    for item in items:
        normalized.append(
            {
                "item": normalize_item_name(item.item),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
            }
        )

    normalized.sort(
        key=lambda x: (
            x["item"],
            x["quantity"],
            x["unit_price"],
            x["total_price"] if x["total_price"] is not None else -1,
        )
    )

    return normalized


def business_signature(invoice: Invoice) -> dict:
    """
    Compare invoices using business-important fields only.

    Ignore differences such as:
    - file_name
    - vendor address presence/absence
    - subtotal presence/absence
    - tax fields null vs 0
    - payment terms missing vs present
    """
    return {
        "invoice_number": get_base_invoice_number(invoice.invoice_number),
        "vendor_name": (invoice.vendor.name or "").strip().lower(),
        "invoice_date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "line_items": normalize_line_items_for_signature(invoice.line_items),
        "total": invoice.total,
    }


def richness_score(invoice: Invoice) -> int:
    """
    Prefer the richer invoice when two versions are business-equivalent.
    """
    score = 0

    if invoice.vendor.address:
        score += 1
    if invoice.subtotal is not None:
        score += 1
    if invoice.tax_rate is not None:
        score += 1
    if invoice.tax_amount is not None:
        score += 1
    if invoice.payment_terms:
        score += 1
    if invoice.notes:
        score += 1

    return score


def make_conflict(invoice_number: str, versions: List[Invoice]) -> InvoiceValidation:
    return InvoiceValidation(
        file_name=", ".join(v.file_name for v in versions),
        invoice_number=invoice_number,
        status="failed",
        issues=[
            ValidationIssue(
                item=None,
                issue_type="Revision Conflict",
                message=(
                    f"Multiple versions found for invoice {invoice_number} "
                    f"with materially different contents and no clear winner."
                ),
            )
        ],
    )


def choose_richest_version(versions: List[Invoice]) -> Invoice:
    """
    Pick the most complete version among business-equivalent duplicates.
    """
    return max(versions, key=richness_score)


def canonicalize_invoices() -> Tuple[Dict[str, Invoice], List[InvoiceValidation]]:
    """
    Transform raw extracted invoices into one canonical invoice per base invoice number.

    Rules:
    1. Group by base invoice number
    2. If only one invoice exists -> keep it
    3. If exactly one explicit revised version exists -> keep revised
    4. If versions are business-equivalent -> keep richest version
    5. Otherwise -> mark conflict
    """
    grouped: Dict[str, List[Invoice]] = defaultdict(list)

    for invoice in GLOBAL_INVOICE_STATE.invoices.values():
        base_number = get_base_invoice_number(invoice.invoice_number)
        grouped[base_number].append(invoice)

    canonical_invoices: Dict[str, Invoice] = {}
    conflicts: List[InvoiceValidation] = []

    for base_number, versions in grouped.items():
        # Case 1: only one version
        if len(versions) == 1:
            chosen = versions[0].model_copy(deep=True)
            chosen.invoice_number = base_number
            canonical_invoices[base_number] = chosen
            continue

        # Case 2: one explicit revised version wins
        revised_versions = [v for v in versions if is_revised_invoice(v)]
        if len(revised_versions) == 1:
            chosen = revised_versions[0].model_copy(deep=True)
            chosen.invoice_number = base_number
            canonical_invoices[base_number] = chosen
            continue

        # Case 3: all business-equivalent -> keep richest version
        first_sig = business_signature(versions[0])
        all_equivalent = all(
            business_signature(v) == first_sig
            for v in versions[1:]
        )

        if all_equivalent:
            chosen = choose_richest_version(versions).model_copy(deep=True)
            chosen.invoice_number = base_number
            canonical_invoices[base_number] = chosen
            continue

        # Case 4: unresolved conflict
        conflicts.append(make_conflict(base_number, versions))

    GLOBAL_INVOICE_STATE.canonical_invoices = canonical_invoices
    GLOBAL_INVOICE_STATE.invoice_conflicts = conflicts

    return canonical_invoices, conflicts