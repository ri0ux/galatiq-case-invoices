from datetime import date, datetime
import re
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple, cast

from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from pydantic import BaseModel, Field

from models.invoice_schema import Invoice, LineItem
from models.invoice_state import GLOBAL_INVOICE_STATE
from models.validation_schema import InvoiceValidation, ItemValidation, ValidationIssue, AggregatedItemDemand


class FraudCheckResult(BaseModel):
    suspicious: bool = Field(..., description="Whether the invoice appears suspicious")
    issues: List[ValidationIssue] = Field(default_factory=list)


class NamingResult(BaseModel):
    name: str = Field(..., description="Canonical normalized item name used for inventory lookup")


class ValidationAgent:
    def __init__(self, db_path: str = "inventory.db") -> None:
        self.db_path = db_path

        self.fraud_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=FraudCheckResult,
        )

        self.naming_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=NamingResult,
        )

        self.name_cache: Dict[str, str] = {}
        self.inventory_keys = self._load_inventory_keys()

    def run(self) -> Dict[str, InvoiceValidation]:
        """
        Validation flow:
        1. Per-invoice required field / date / arithmetic validation
        2. Fraud screen
        3. Aggregate normalized item demand across all canonical invoices
        4. Aggregate inventory pressure analysis -> item_validations
        5. Sequential stock allocation -> invoice-level inventory issues
        6. Dedupe invoice issues
        """
        invoice_results: Dict[str, InvoiceValidation] = {}

        # -----------------------------------
        # STEP 1: per-invoice deterministic + fraud
        # -----------------------------------
        for invoice_number, invoice in GLOBAL_INVOICE_STATE.canonical_invoices.items():
            issues: List[ValidationIssue] = []

            issues.extend(self._validate_required_fields(invoice))
            issues.extend(self._validate_dates(invoice))
            issues.extend(self._validate_arithmetic(invoice))
            issues.extend(self._fraud_screen(invoice).issues)

            issues = self._normalize_issues(issues)

            invoice_results[invoice_number] = InvoiceValidation(
                file_name=invoice.file_name,
                invoice_number=invoice_number,
                status="failed" if issues else "passed",
                issues=issues,
            )

        # -----------------------------------
        # STEP 2: aggregate item demand
        # -----------------------------------
        aggregated_items, invoice_item_map = self._aggregate_items()
        GLOBAL_INVOICE_STATE.items = aggregated_items

        # -----------------------------------
        # STEP 3: aggregate inventory pressure
        # -----------------------------------
        GLOBAL_INVOICE_STATE.item_validations = self._validate_aggregate_item_pressure(
            aggregated_items
        )

        # -----------------------------------
        # STEP 4: sequential allocation for invoice-level inventory issues
        # -----------------------------------
        sequential_inventory_issues = self._validate_sequential_inventory_allocation()

        for invoice_number, issues in sequential_inventory_issues.items():
            if invoice_number in invoice_results:
                invoice_results[invoice_number].issues.extend(self._normalize_issues(issues))

        # -----------------------------------
        # STEP 5: dedupe invoice issues + refresh status
        # -----------------------------------
        for invoice_number, validation in invoice_results.items():
            validation.issues = self._dedupe_issues(validation.issues)
            validation.status = "failed" if validation.issues else "passed"

        GLOBAL_INVOICE_STATE.invoice_validations = invoice_results
        return invoice_results

    # ============================================================
    # Item aggregation
    # ============================================================

    def _aggregate_items(
        self,
    ) -> Tuple[List[AggregatedItemDemand], Dict[str, List[Tuple[str, LineItem]]]]:
        """
        Aggregate normalized demand across all canonical invoices.

        Returns:
        - aggregated_items
        - invoice_item_map: normalized_item -> [(invoice_number, original_line_item), ...]
        """
        item_totals: Dict[str, AggregatedItemDemand] = {}
        invoice_item_map: Dict[str, List[Tuple[str, LineItem]]] = defaultdict(list)

        for invoice_number, invoice in GLOBAL_INVOICE_STATE.canonical_invoices.items():
            for line_item in invoice.line_items:
                normalized_name = self._normalize_item_name(line_item.item)
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

    # ============================================================
    # Aggregate item pressure
    # ============================================================

    def _validate_aggregate_item_pressure(
        self,
        aggregated_items: List[AggregatedItemDemand],
    ) -> Dict[str, ItemValidation]:
        """
        This is global reporting only.
        It does NOT decide which specific invoice fails.
        """
        inventory = self._load_inventory()
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
            issues = self._normalize_issues(issues)
            item_validations[key] = ItemValidation(
                item_name=key,
                status="failed" if issues else "passed",
                issues=issues,
            )

        return item_validations

    # ============================================================
    # Sequential inventory allocation
    # ============================================================

    def _validate_sequential_inventory_allocation(
        self,
    ) -> Dict[str, List[ValidationIssue]]:
        """
        Allocate inventory in deterministic invoice order.
        Only invoices that cannot be fulfilled from remaining stock get
        invoice-level inventory failures.
        """
        remaining_stock = self._load_inventory()
        invoice_inventory_issues: Dict[str, List[ValidationIssue]] = defaultdict(list)

        sorted_invoices = sorted(
            GLOBAL_INVOICE_STATE.canonical_invoices.values(),
            key=self._invoice_sort_key,
        )

        for invoice in sorted_invoices:
            invoice_seen_keys: set[tuple[str, str]] = set()

            # collapse repeated item names inside one invoice before allocating
            invoice_item_totals: Dict[str, Dict[str, object]] = {}

            for line_item in invoice.line_items:
                normalized_name = self._normalize_item_name(line_item.item)

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
                    self._append_unique_issue(
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
                    self._append_unique_issue(
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
                    self._append_unique_issue(
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

    def _invoice_sort_key(self, invoice: Invoice) -> tuple[date, str]:
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

    # ============================================================
    # Deterministic invoice checks
    # ============================================================

    def _validate_required_fields(self, invoice: Invoice) -> List[ValidationIssue]:
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

    def _validate_dates(self, invoice: Invoice) -> List[ValidationIssue]:
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

    def _validate_arithmetic(self, invoice: Invoice) -> List[ValidationIssue]:
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

    # ============================================================
    # Fraud screen
    # ============================================================

    def _fraud_screen(self, invoice: Invoice) -> FraudCheckResult:
        prompt = f"""
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
        try:
            result = self.fraud_agent.run(prompt)
            return cast(FraudCheckResult, result.content)
        except Exception as e:
            return FraudCheckResult(
                suspicious=False,
                issues=[
                    ValidationIssue(
                        item=None,
                        issue_type="Fraud Screen Error",
                        message=f"Fraud screening failed: {str(e)}",
                    )
                ],
            )

    # ============================================================
    # Item normalization
    # ============================================================

    def _normalize_item_name(self, name: str) -> str:
        if name in self.name_cache:
            return self.name_cache[name]

        deterministic = self._deterministic_normalize(name)

        if deterministic in self.inventory_keys:
            self.name_cache[name] = deterministic
            return deterministic

        try:
            result = cast(NamingResult, self.naming_agent.run(input=name).content)
            normalized = self._deterministic_normalize(result.name)
        except Exception:
            normalized = deterministic

        self.name_cache[name] = normalized
        return normalized

    def _deterministic_normalize(self, name: str) -> str:
        value = (name or "").strip().lower()
        value = re.sub(r"\(.*?\)", "", value)
        value = re.sub(r"[^a-z0-9\s]", "", value)
        value = value.replace(" ", "")
        return value.strip()

    # ============================================================
    # Inventory loading
    # ============================================================

    def _load_inventory(self) -> Dict[str, int]:
        inventory: Dict[str, int] = {}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT item, stock FROM inventory")
            rows = cursor.fetchall()

            for item_name, stock in rows:
                normalized_name = self._deterministic_normalize(item_name)
                inventory[normalized_name] = int(stock)
        finally:
            conn.close()

        return inventory

    def _load_inventory_keys(self) -> set[str]:
        return set(self._load_inventory().keys())

    # ============================================================
    # Deduping helpers
    # ============================================================

    def _append_unique_issue(
        self,
        target: List[ValidationIssue],
        seen: set[tuple[str, str]],
        issue: ValidationIssue,
    ) -> None:
        key = (issue.item or "", issue.issue_type)
        if key not in seen:
            target.append(issue)
            seen.add(key)

    def _dedupe_issues(self, issues: List[ValidationIssue]) -> List[ValidationIssue]:
        deduped: List[ValidationIssue] = []
        seen: set[tuple[str, str, str]] = set()

        for issue in issues:
            key = (issue.item or "", issue.issue_type, issue.message)
            if key not in seen:
                deduped.append(issue)
                seen.add(key)

        return deduped
    def _normalize_issue_type(self, issue_type: str) -> str:
        value = (issue_type or "").strip().lower().replace("_", " ")

        mapping = {
            "missing vendor": "Missing Vendor",
            "missing vendor name": "Missing Vendor",
            "missing due date": "Missing Due Date",
            "missing invoice date": "Missing Invoice Date",
            "missing total": "Missing Total",
            "missing line items": "Missing Line Items",
            "missing vendor address": "Missing Vendor Address",

            "negative quantity": "Negative Quantity",
            "negative unit price": "Negative Unit Price",
            "negative total": "Negative Total",
            "negative total amount": "Negative Total",
            "suspicious amount": "Suspicious Amount",

            "subtotal mismatch": "Subtotal Mismatch",
            "total mismatch": "Total Mismatch",
            "line total mismatch": "Line Total Mismatch",
            "invalid dates": "Invalid Dates",

            "unknown item": "Unknown Item",
            "out of stock": "Out of Stock",
            "insufficient inventory": "Insufficient Inventory",

            "suspicious vendor naming": "Suspicious Vendor Naming",
            "suspicious vendor name": "Suspicious Vendor Naming",

            "unusually urgent due date": "Unusually Urgent Due Date",
            "urgent payment terms": "Urgent Payment Terms",
            "urgent payment language": "Coercive Payment Language",
            "coercive or urgent payment language": "Coercive Payment Language",
            "coercive payment language": "Coercive Payment Language",

            "suspicious payment instructions": "Suspicious Payment Instructions",

            "fraud screen error": "Fraud Screen Error",
        }

        return mapping.get(value, issue_type.strip().title())
    def _normalize_issues(self, issues: List[ValidationIssue]) -> List[ValidationIssue]:
        normalized: List[ValidationIssue] = []

        for issue in issues:
            normalized.append(
                ValidationIssue(
                    item=issue.item,
                    issue_type=self._normalize_issue_type(issue.issue_type),
                    message=issue.message.strip(),
                )
            )

        return normalized