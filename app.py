import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from models.invoice_schema import RawInvoiceFile
from models.invoice_state import GLOBAL_INVOICE_STATE
from orchestration.workflow import run_invoice_pipeline
from utils.file_loader import load_single_invoice


st.set_page_config(
    page_title="Invoice Processing Automation",
    page_icon="🧾",
    layout="wide",
)

SUPPORTED_EXTENSIONS = ["txt", "csv", "json", "xml", "pdf"]


def reset_global_state() -> None:
    GLOBAL_INVOICE_STATE.invoices.clear()
    GLOBAL_INVOICE_STATE.canonical_invoices.clear()
    GLOBAL_INVOICE_STATE.invoice_conflicts.clear()
    GLOBAL_INVOICE_STATE.item_validations.clear()
    GLOBAL_INVOICE_STATE.invoice_validations.clear()
    GLOBAL_INVOICE_STATE.items.clear()
    GLOBAL_INVOICE_STATE.approvals.clear()
    GLOBAL_INVOICE_STATE.payment_results.clear()


def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def uploaded_files_to_invoices(uploaded_files) -> dict[str, RawInvoiceFile]:
    invoices: dict[str, RawInvoiceFile] = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        for uploaded_file in uploaded_files:
            suffix = Path(uploaded_file.name).suffix.lower()
            if suffix.lstrip(".") not in SUPPORTED_EXTENSIONS:
                continue

            safe_name = Path(uploaded_file.name).name
            temp_path = Path(tmpdir) / safe_name

            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            raw_text = load_single_invoice(str(temp_path))

            invoices[str(temp_path)] = RawInvoiceFile(
                file_path=str(temp_path),
                file_type=suffix,
                raw_text=raw_text,
                extracted_invoice_number=None,
            )

        if not invoices:
            return {}

        run_async(run_invoice_pipeline(invoices))

    return invoices


def load_state_from_json(path: str = "final_invoice_state.json") -> dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def status_color(status: str) -> str:
    mapping = {
        "approved": "🟢",
        "manual_review": "🟡",
        "rejected": "🔴",
        "passed": "🟢",
        "failed": "🔴",
        "success": "🟢",
        "not_paid": "⚪",
    }
    return mapping.get(str(status).lower(), "⚪")


def build_invoice_table(state: dict[str, Any]) -> pd.DataFrame:
    canonical = state.get("canonical_invoices", {})
    validations = state.get("invoice_validations", {})
    approvals = state.get("approvals", {})
    payments = state.get("payment_results", {})

    rows: list[dict[str, Any]] = []

    for invoice_number, invoice in canonical.items():
        validation = validations.get(invoice_number, {})
        approval = approvals.get(invoice_number, {})
        payment = payments.get(invoice_number, {})

        vendor_name = ((invoice.get("vendor") or {}).get("name")) or "Unknown Vendor"

        rows.append(
            {
                "Invoice Number": invoice_number,
                "Vendor": vendor_name,
                "Amount": invoice.get("total"),
                "Currency": invoice.get("currency"),
                "Validation": validation.get("status", "unknown"),
                "Approval": approval.get("status", "unknown"),
                "Payment": payment.get("payment_status", "unknown"),
                "Risk Score": approval.get("risk_score"),
                "Due Date": invoice.get("due_date"),
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values(by=["Invoice Number"]).reset_index(drop=True)

    return df


def render_summary_metrics(state: dict[str, Any]) -> None:
    canonical = state.get("canonical_invoices", {})
    validations = state.get("invoice_validations", {})
    approvals = state.get("approvals", {})
    payments = state.get("payment_results", {})

    total_invoices = len(canonical)
    validation_failed = sum(1 for v in validations.values() if v.get("status") == "failed")
    approved = sum(1 for a in approvals.values() if a.get("status") == "approved")
    manual_review = sum(1 for a in approvals.values() if a.get("status") == "manual_review")
    rejected = sum(1 for a in approvals.values() if a.get("status") == "rejected")
    paid = sum(1 for p in payments.values() if p.get("payment_status") == "success")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Invoices", total_invoices)
    c2.metric("Validation Failed", validation_failed)
    c3.metric("Approved", approved)
    c4.metric("Manual Review", manual_review)
    c5.metric("Rejected", rejected)
    c6.metric("Paid", paid)


def render_invoice_detail(state: dict[str, Any], invoice_number: str) -> None:
    canonical = state.get("canonical_invoices", {})
    validations = state.get("invoice_validations", {})
    approvals = state.get("approvals", {})
    payments = state.get("payment_results", {})

    invoice = canonical.get(invoice_number)
    validation = validations.get(invoice_number, {})
    approval = approvals.get(invoice_number, {})
    payment = payments.get(invoice_number, {})

    if not invoice:
        st.warning("Invoice not found.")
        return

    vendor = invoice.get("vendor") or {}

    c1, c2 = st.columns([1.4, 1])

    with c1:
        st.subheader(f"{invoice_number}")
        st.write(f"**Vendor:** {vendor.get('name') or 'Unknown Vendor'}")
        st.write(f"**Address:** {vendor.get('address') or 'N/A'}")
        st.write(f"**Invoice Date:** {invoice.get('invoice_date') or 'N/A'}")
        st.write(f"**Due Date:** {invoice.get('due_date') or 'N/A'}")
        st.write(f"**Total:** {invoice.get('total')} {invoice.get('currency') or ''}")
        st.write(f"**Payment Terms:** {invoice.get('payment_terms') or 'N/A'}")
        st.write(f"**Notes:** {invoice.get('notes') or 'N/A'}")

    with c2:
        st.subheader("Decision Summary")
        validation_status = validation.get("status", "unknown")
        approval_status = approval.get("status", "unknown")
        payment_status = payment.get("payment_status", "unknown")

        st.write(f"**Validation:** {status_color(validation_status)} {validation_status}")
        st.write(f"**Approval:** {status_color(approval_status)} {approval_status}")
        st.write(f"**Payment:** {status_color(payment_status)} {payment_status}")
        st.write(f"**Risk Score:** {approval.get('risk_score', 'N/A')}")
        st.write(f"**Reason:** {approval.get('reason') or payment.get('reason') or 'N/A'}")

    st.markdown("---")

    st.subheader("Line Items")
    line_items = invoice.get("line_items", [])
    if line_items:
        st.dataframe(pd.DataFrame(line_items), use_container_width=True, hide_index=True)
    else:
        st.info("No line items found.")

    st.subheader("Validation Issues")
    issues = validation.get("issues", [])
    if issues:
        for issue in issues:
            st.error(f"{issue.get('issue_type')}: {issue.get('message')}")
    else:
        st.success("No validation issues.")

    with st.expander("Raw Invoice JSON"):
        st.json(invoice)

    with st.expander("Raw Validation JSON"):
        st.json(validation)

    with st.expander("Raw Approval JSON"):
        st.json(approval)

    with st.expander("Raw Payment JSON"):
        st.json(payment)


def render_items_section(state: dict[str, Any]) -> None:
    st.subheader("Aggregated Item Demand")
    items = state.get("items", [])
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    else:
        st.info("No aggregated item data available.")

    st.subheader("Item Validation Results")
    item_validations = state.get("item_validations", {})
    if item_validations:
        rows = []
        for item_name, payload in item_validations.items():
            rows.append(
                {
                    "Item": item_name,
                    "Status": payload.get("status"),
                    "Issue Count": len(payload.get("issues", [])),
                    "Issues": "; ".join(
                        issue.get("issue_type", "") for issue in payload.get("issues", [])
                    ),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No item validation data available.")


def render_conflicts_section(state: dict[str, Any]) -> None:
    st.subheader("Invoice Conflicts")
    conflicts = state.get("invoice_conflicts", [])
    if conflicts:
        st.json(conflicts)
    else:
        st.success("No invoice conflicts detected.")


st.title("🧾 Invoice Processing Automation")
st.caption("Multi-agent invoice ingestion, validation, approval, and payment demo")

with st.sidebar:
    st.header("Run Pipeline")
    uploaded_files = st.file_uploader(
        "Upload invoice files",
        type=SUPPORTED_EXTENSIONS,
        accept_multiple_files=True,
    )

    run_clicked = st.button("Run Pipeline", type="primary", use_container_width=True)

    st.markdown("---")
    st.header("Supported Formats")
    st.write(", ".join(SUPPORTED_EXTENSIONS).upper())

if run_clicked:
    if not uploaded_files:
        st.warning("Upload at least one invoice file.")
    else:
        reset_global_state()
        with st.spinner("Running invoice pipeline..."):
            uploaded_files_to_invoices(uploaded_files)
            st.session_state["pipeline_state"] = GLOBAL_INVOICE_STATE.model_dump()

        st.success("Pipeline finished successfully.")

if "pipeline_state" not in st.session_state:
    existing_state = load_state_from_json()
    if existing_state:
        st.session_state["pipeline_state"] = existing_state

state = st.session_state.get("pipeline_state")

if not state:
    st.info("Upload invoices and run the pipeline to see results.")
else:
    render_summary_metrics(state)

    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Invoice Results", "Invoice Detail", "Inventory Analysis", "Conflicts"]
    )

    with tab1:
        st.subheader("Pipeline Results")
        df = build_invoice_table(state)
        if df.empty:
            st.info("No invoice results available.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        canonical = state.get("canonical_invoices", {})
        invoice_numbers = sorted(canonical.keys())

        if not invoice_numbers:
            st.info("No invoice details available.")
        else:
            selected_invoice = st.selectbox("Select invoice", invoice_numbers)
            render_invoice_detail(state, selected_invoice)

    with tab3:
        render_items_section(state)

    with tab4:
        render_conflicts_section(state)