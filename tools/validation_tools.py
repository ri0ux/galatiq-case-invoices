from typing import List
from models.invoice_schema import Invoice
from models.validation_schema import ValidationIssue
from collections import defaultdict
from typing import Dict, List, Tuple, cast
from models.invoice_schema import LineItem
from models.validation_schema import AggregatedItemDemand, ItemValidation
from utils.normalizer import normalize_issues, normalize_item_name
from utils.db_functions import load_inventory
from config.config import Config
from datetime import date, datetime


def validate_sequential_inventory_allocation(canonical_invoices: Dict[str, Invoice]) -> Dict[str, List[ValidationIssue]]:
        """
        Allocate inventory in deterministic invoice order.
        Only invoices that cannot be fulfilled from remaining stock get
        invoice-level inventory failures.
        """
        remaining_stock = load_inventory(Config.DB_PATH)
        invoice_inventory_issues: Dict[str, List[ValidationIssue]] = defaultdict(list)

        sorted_invoices = sorted(
            canonical_invoices.values(),
            key=_invoice_sort_key,
        )

        for invoice in sorted_invoices:
            invoice_seen_keys: set[tuple[str, str]] = set()

            # collapse repeated item names inside one invoice before allocating
            invoice_item_totals: Dict[str, Dict[str, object]] = {}

            for line_item in invoice.line_items:
                normalized_name = normalize_item_name(line_item.item)

                if normalized_name not in invoice_item_totals:
                    invoice_item_totals[normalized_name] = {
                        "display_name": line_item.item,
                        "quantity": line_item.quantity,
                    }
                else:
                    invoice_item_totals[normalized_name]["quantity"] = (
                        cast(int, invoice_item_totals[normalized_name]["quantity"])
                        + line_item.quantity
                    )

            for normalized_name, payload in invoice_item_totals.items():
                display_name = cast(str, payload["display_name"])
                quantity_needed = cast(int, payload["quantity"])

                # unknown item
                if normalized_name not in remaining_stock:
                    _append_unique_issue(
                        invoice_inventory_issues[invoice.invoice_number],
                        invoice_seen_keys,
                        ValidationIssue(
                            item=display_name,
                            issue_type="Unknown Item",
                            message=(
                                f"Item '{display_name}' maps to normalized key "
                                f"'{normalized_name}', which was not found in inventory database."
                            ),
                        ),
                    )
                    continue

                available = remaining_stock[normalized_name]

                if available <= 0:
                    _append_unique_issue(
                        invoice_inventory_issues[invoice.invoice_number],
                        invoice_seen_keys,
                        ValidationIssue(
                            item=display_name,
                            issue_type="Out of Stock",
                            message=(
                                f"Item '{display_name}' maps to inventory item "
                                f"'{normalized_name}', which has no remaining stock."
                            ),
                        ),
                    )
                    continue

                if quantity_needed > available:
                    _append_unique_issue(
                        invoice_inventory_issues[invoice.invoice_number],
                        invoice_seen_keys,
                        ValidationIssue(
                            item=display_name,
                            issue_type="Insufficient Inventory",
                            message=(
                                f"Item '{display_name}' requires {quantity_needed} units, "
                                f"but only {available} remaining for inventory item "
                                f"'{normalized_name}'."
                            ),
                        ),
                    )
                    continue

                # reserve stock only if invoice can be fulfilled for that item
                remaining_stock[normalized_name] -= quantity_needed
        return invoice_inventory_issues


def validate_arithmetic(invoice: Invoice) -> List[ValidationIssue]:
        """
        Description
        Validates invoice math and financial consistency. This tool checks line-item math, subtotal consistency, total consistency, and negative financial values. It does not validate fraud, inventory, or field completeness.

        Input

        invoice: Invoice
        A structured invoice object containing line items, subtotal, tax amount, and total.

        Output

        List[ValidationIssue]
        A list of arithmetic and amount-related validation issues. Returns an empty list if all calculations are consistent.
        """
        issues: List[ValidationIssue] = []

        if not invoice.line_items:
            return issues

        computed_subtotal = 0.0

        for item in invoice.line_items:
            if item.quantity < 0:
                issues.append(
                    ValidationIssue(
                        item=item.item,
                        issue_type="Negative Quantity",
                        message=f"Item '{item.item}' has negative quantity: {item.quantity}.",
                    )
                )

            if item.unit_price < 0:
                issues.append(
                    ValidationIssue(
                        item=item.item,
                        issue_type="Negative Unit Price",
                        message=f"Item '{item.item}' has negative unit price: {item.unit_price}.",
                    )
                )

            expected_line_total = round(item.quantity * item.unit_price, 2)

            if item.total_price is None:
                issues.append(
                    ValidationIssue(
                        item=item.item,
                        issue_type="Missing Line Total",
                        message=f"Item '{item.item}' is missing total_price.",
                    )
                )
            else:
                actual_line_total = round(item.total_price, 2)
                if actual_line_total != expected_line_total:
                    issues.append(
                        ValidationIssue(
                            item=item.item,
                            issue_type="Line Total Mismatch",
                            message=(
                                f"Item '{item.item}' total_price={actual_line_total} but "
                                f"expected {expected_line_total} from quantity * unit_price."
                            ),
                        )
                    )

            computed_subtotal += expected_line_total

        computed_subtotal = round(computed_subtotal, 2)

        if invoice.subtotal is not None:
            actual_subtotal = round(invoice.subtotal, 2)
            if actual_subtotal != computed_subtotal:
                issues.append(
                    ValidationIssue(
                        item=None,
                        issue_type="Subtotal Mismatch",
                        message=(
                            f"Invoice subtotal={actual_subtotal} but expected "
                            f"{computed_subtotal} from summed line items."
                        ),
                    )
                )

        if invoice.total is not None:
            tax_amount = round(invoice.tax_amount or 0.0, 2)
            expected_total = round(computed_subtotal + tax_amount, 2)
            actual_total = round(invoice.total, 2)

            if actual_total != expected_total:
                issues.append(
                    ValidationIssue(
                        item=None,
                        issue_type="Total Mismatch",
                        message=(
                            f"Invoice total={actual_total} but expected {expected_total} "
                            f"(subtotal + tax_amount)."
                        ),
                    )
                )

            if actual_total < 0:
                issues.append(
                    ValidationIssue(
                        item=None,
                        issue_type="Negative Total",
                        message=f"Invoice total is negative: {actual_total}.",
                    )
                )

        return issues
    
def validate_dates(invoice: Invoice) -> List[ValidationIssue]:
    """
    Description
        Validates invoice date consistency. This tool checks whether the due date occurs before the invoice date. It only performs date relationship checks and does not validate missing fields or date formatting.

    Input

    invoice: Invoice
    A structured invoice object with invoice_date and due_date.

    Output

    List[ValidationIssue]
    A list of date-related validation issues. Returns an empty list if the dates are logically valid or if the required dates are not present.
    """
    issues: List[ValidationIssue] = []

    if invoice.invoice_date and invoice.due_date:
        if invoice.due_date < invoice.invoice_date:
            issues.append(
                ValidationIssue(
                    item=None,
                    issue_type="Invalid Dates",
                    message=(
                        f"Due date {invoice.due_date} is earlier than invoice date "
                        f"{invoice.invoice_date}."
                    ),
                )
            )

    return issues

def validate_required_fields(invoice: Invoice) -> List[ValidationIssue]:
    """
    Description
    Checks whether the invoice contains the minimum required fields needed for downstream processing. This tool only validates field presence and emptiness. It does not check arithmetic, fraud, inventory, or approval policy.

    Input

    invoice: Invoice
    A structured invoice object containing vendor, invoice number, dates, line items, totals, and related metadata.

    Output

    List[ValidationIssue]
    A list of validation issues for missing or empty required fields. Returns an empty list if all required fields are present.
    """
    issues: List[ValidationIssue] = []

    if not invoice.vendor or not invoice.vendor.name or not invoice.vendor.name.strip():
        issues.append(
            ValidationIssue(
                item=None,
                issue_type="Missing Vendor",
                message="Vendor name is missing.",
            )
        )

    if not invoice.invoice_number or not invoice.invoice_number.strip():
        issues.append(
            ValidationIssue(
                item=None,
                issue_type="Missing Invoice Number",
                message="Invoice number is missing.",
            )
        )

    if not invoice.invoice_date:
        issues.append(
            ValidationIssue(
                item=None,
                issue_type="Missing Invoice Date",
                message="Invoice date is missing.",
            )
        )

    if not invoice.due_date:
        issues.append(
            ValidationIssue(
                item=None,
                issue_type="Missing Due Date",
                message="Due date is missing.",
            )
        )

    if not invoice.line_items:
        issues.append(
            ValidationIssue(
                item=None,
                issue_type="Missing Line Items",
                message="Invoice has no line items.",
            )
        )

    if invoice.total is None:
        issues.append(
            ValidationIssue(
                item=None,
                issue_type="Missing Total",
                message="Invoice total is missing.",
            )
        )

    return issues





def calculate_inventory_pressure(canonical_invoices: Dict[str, Invoice]) -> Tuple[List[AggregatedItemDemand], Dict[str, List[Tuple[str, LineItem]]]]:
    """
    Aggregate normalized demand across all canonical invoices. Uses the ItemNormalization agent to get an item name.

    Returns:
    - aggregated_items
    - invoice_item_map: normalized_item -> [(invoice_number, original_line_item), ...]
    """
    item_totals: Dict[str, AggregatedItemDemand] = {}
    invoice_item_map: Dict[str, List[Tuple[str, LineItem]]] = defaultdict(list)

    for invoice_number, invoice in canonical_invoices.items():
        for line_item in invoice.line_items:
            normalized_name = normalize_item_name(line_item.item)
            invoice_item_map[normalized_name].append((invoice_number, line_item))

            line_total = (
                line_item.total_price
                if line_item.total_price is not None
                else line_item.quantity * line_item.unit_price
            )

            if normalized_name not in item_totals:
                item_totals[normalized_name] = AggregatedItemDemand(
                    normalized_item_name=normalized_name,
                    display_name=line_item.item,
                    total_quantity=line_item.quantity,
                    total_amount=float(line_total),
                    invoice_numbers=[invoice_number],
                )
            else:
                item_totals[normalized_name].total_quantity += line_item.quantity
                item_totals[normalized_name].total_amount += float(line_total)

                if invoice_number not in item_totals[normalized_name].invoice_numbers:
                    item_totals[normalized_name].invoice_numbers.append(invoice_number)

    return list(item_totals.values()), invoice_item_map

def validate_aggregate_item_pressure(aggregated_items: List[AggregatedItemDemand]) -> Dict[str, ItemValidation]:
        """
        This is global reporting only.
        It does NOT decide which specific invoice fails.
        """
        inventory = load_inventory(Config.DB_PATH)
        item_validations: Dict[str, ItemValidation] = {}

        for item in aggregated_items:
            issues: List[ValidationIssue] = []
            key = item.normalized_item_name

            if key not in inventory:
                issues.append(
                    ValidationIssue(
                        item=key,
                        issue_type="Unknown Item",
                        message=f"Normalized item '{key}' was not found in inventory database.",
                    )
                )
            else:
                stock = inventory[key]

                if stock == 0:
                    issues.append(
                        ValidationIssue(
                            item=key,
                            issue_type="Out of Stock",
                            message=f"Item '{key}' is in inventory but stock is 0.",
                        )
                    )

                if item.total_quantity > stock:
                    issues.append(
                        ValidationIssue(
                            item=key,
                            issue_type="Insufficient Inventory",
                            message=(
                                f"Aggregated demand for '{key}' is {item.total_quantity}, "
                                f"but only {stock} available in inventory."
                            ),
                        )
                    )
            issues = normalize_issues(issues)
            item_validations[key] = ItemValidation(
                item_name=key,
                status="failed" if issues else "passed",
                issues=issues,
            )

        return item_validations

# helpers for validate_sequential_inventory_allocation
def _append_unique_issue(target: List[ValidationIssue], seen: set[tuple[str, str]], issue: ValidationIssue) -> None:
    key = (issue.item or "", issue.issue_type)
    if key not in seen:
        target.append(issue)
        seen.add(key)

def _invoice_sort_key(invoice: Invoice) -> tuple[date, str]:
    """
    Deterministic processing order:
    1. invoice_date ascending
    2. invoice_number ascending
    """

    invoice_date = invoice.invoice_date

    if isinstance(invoice_date, str):
        invoice_date = datetime.fromisoformat(invoice_date).date()

    if invoice_date is None:
        invoice_date = date.max

    return (invoice_date, invoice.invoice_number)