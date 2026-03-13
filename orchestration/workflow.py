import asyncio
import json

from agents.ingestion_agent import IngestionAgent
from agents.validation_agents.validation_team import ValidationTeam
from agents.approval_agent import ApprovalAgent
from agents.payment_agent import PaymentAgent

from utils.invoice_canonicalizer import canonicalize_invoices
from utils.logger import get_logger
from models.invoice_state import GLOBAL_INVOICE_STATE


logger = get_logger(__name__)


async def run_invoice_pipeline(invoices):
    logger.info("Starting invoice pipeline for %s input files", len(invoices))

    ingestion_agent = IngestionAgent()
    validation_team = ValidationTeam()
    approval_agent = ApprovalAgent()
    payment_agent = PaymentAgent()

    # -------------------------
    # INGESTION
    # -------------------------
    logger.info("Starting ingestion stage")

    tasks = [
        ingestion_agent.invoice_extractor(file_name, raw_invoice)
        for file_name, raw_invoice in invoices.items()
    ]

    extracted = await asyncio.gather(*tasks)

    for file_name, invoice in zip(invoices.keys(), extracted):
        GLOBAL_INVOICE_STATE.invoices[file_name] = invoice

    logger.info(
        "Ingestion complete: extracted %s invoices",
        len(GLOBAL_INVOICE_STATE.invoices),
    )

    # -------------------------
    # CANONICALIZATION
    # -------------------------
    logger.info("Starting canonicalization stage")

    canonical, conflicts = canonicalize_invoices()

    GLOBAL_INVOICE_STATE.canonical_invoices = canonical
    GLOBAL_INVOICE_STATE.invoice_conflicts = conflicts

    logger.info(
        "Canonicalization complete: %s canonical invoices, %s conflicts",
        len(canonical),
        len(conflicts),
    )

    # -------------------------
    # VALIDATION
    # -------------------------
    logger.info("Starting validation stage")

    invoice_validations, item_validations, aggregated_items = validation_team.run(
        GLOBAL_INVOICE_STATE.canonical_invoices
    )

    GLOBAL_INVOICE_STATE.invoice_validations = invoice_validations
    GLOBAL_INVOICE_STATE.item_validations = item_validations
    GLOBAL_INVOICE_STATE.items = aggregated_items

    validation_passed = sum(
        1 for v in invoice_validations.values() if v.status == "passed"
    )
    validation_failed = sum(
        1 for v in invoice_validations.values() if v.status == "failed"
    )

    logger.info(
        "Validation complete: %s passed, %s failed, %s aggregated items, %s item validations",
        validation_passed,
        validation_failed,
        len(aggregated_items),
        len(item_validations),
    )

    # -------------------------
    # APPROVAL
    # -------------------------
    logger.info("Starting approval stage")

    approvals = approval_agent.run()
    GLOBAL_INVOICE_STATE.approvals = approvals

    approved_count = sum(1 for a in approvals.values() if a.status == "approved")
    manual_review_count = sum(
        1 for a in approvals.values() if a.status == "manual_review"
    )
    rejected_count = sum(1 for a in approvals.values() if a.status == "rejected")

    logger.info(
        "Approval complete: %s approved, %s manual review, %s rejected",
        approved_count,
        manual_review_count,
        rejected_count,
    )

    # -------------------------
    # PAYMENT
    # -------------------------
    logger.info("Starting payment stage")

    payment_results = payment_agent.run()
    GLOBAL_INVOICE_STATE.payment_results = payment_results

    payment_success_count = sum(
        1 for p in payment_results.values() if p.payment_status == "success"
    )
    payment_not_paid_count = sum(
        1 for p in payment_results.values() if p.payment_status != "success"
    )

    logger.info(
        "Payment complete: %s successful, %s not paid",
        payment_success_count,
        payment_not_paid_count,
    )

    # -------------------------
    # EXPORT FINAL STATE
    # -------------------------
    logger.info("Exporting final pipeline state to final_invoice_state.json")

    with open("final_invoice_state.json", "w", encoding="utf-8") as f:
        json.dump(
            GLOBAL_INVOICE_STATE.model_dump(),
            f,
            indent=2,
            default=str,
            ensure_ascii=False,
        )

    logger.info("Pipeline complete. Output written to final_invoice_state.json")