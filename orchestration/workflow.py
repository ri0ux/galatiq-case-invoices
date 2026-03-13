import asyncio
import json

from agents.ingestion_agent import IngestionAgent
from agents.approval_agent import ApprovalAgent
from agents.validation_agents.validation_team import ValidationTeam
from agents.payment_agent import PaymentAgent

from utils.invoice_canonicalizer import canonicalize_invoices
from models.invoice_state import GLOBAL_INVOICE_STATE


async def run_invoice_pipeline(invoices):

    ingestion_agent = IngestionAgent()
    validation_team = ValidationTeam()
    approval_agent = ApprovalAgent()
    payment_agent = PaymentAgent()

    # -------------------------
    # INGESTION
    # -------------------------

    tasks = [
        ingestion_agent.invoice_extractor(file_name, raw_invoice)
        for file_name, raw_invoice in invoices.items()
    ]

    extracted = await asyncio.gather(*tasks)

    for file_name, invoice in zip(invoices.keys(), extracted):
        GLOBAL_INVOICE_STATE.invoices[file_name] = invoice

    # -------------------------
    # CANONICALIZATION
    # -------------------------

    canonical, conflicts = canonicalize_invoices()

    GLOBAL_INVOICE_STATE.canonical_invoices = canonical
    GLOBAL_INVOICE_STATE.invoice_conflicts = conflicts

    # -------------------------
    # VALIDATION
    # -------------------------

    validation_team = ValidationTeam()

    invoice_validations, item_validations, aggregated_items = validation_team.run(
        GLOBAL_INVOICE_STATE.canonical_invoices
    )

    GLOBAL_INVOICE_STATE.invoice_validations = invoice_validations
    GLOBAL_INVOICE_STATE.item_validations = item_validations
    GLOBAL_INVOICE_STATE.items = aggregated_items

    # -------------------------
    # APPROVAL
    # -------------------------

    approvals = approval_agent.run()

    GLOBAL_INVOICE_STATE.approvals = approvals

    # -------------------------
    # PAYMENT
    # -------------------------

    payment_results = payment_agent.run()

    GLOBAL_INVOICE_STATE.payment_results = payment_results
    # -------------------------
    # EXPORT FINAL STATE
    # -------------------------

    with open("final_invoice_state.json", "w", encoding="utf-8") as f:
        json.dump(
            GLOBAL_INVOICE_STATE.model_dump(),
            f,
            indent=2,
            default=str,
            ensure_ascii=False
        )

    print("Pipeline complete. Output written to final_invoice_state.json")