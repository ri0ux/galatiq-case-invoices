from typing import Dict, List, cast

from agno.agent import Agent
from agno.models.openai import OpenAIResponses

from models.approval_schema import ApprovalDecision
from models.invoice_state import GLOBAL_INVOICE_STATE
from models.validation_schema import ValidationIssue
from tools.approval_tools import (
    get_invoice,
    get_validation_summary,
    get_policy_lane,
)


class ApprovalAgent:
    def __init__(self) -> None:
        self.decision_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            instructions="""
           You are an approval decision agent for invoice processing.

            Your job is to return one of:
            - approved
            - rejected
            - manual_review

            You must base your decision ONLY on:
            - the invoice fields explicitly provided
            - the policy lane explicitly provided
            - the validation summary explicitly provided

            Do NOT introduce new facts, assumptions, or risks that are not present in the provided validation summary or invoice fields.
            Do NOT claim an issue exists unless it is explicitly listed.

            Decision rules:
            - Be conservative.
            - Do NOT approve invoices with serious validation failures.
            - Reject invoices with hard failures such as unknown items, negative totals, invalid dates, or out-of-stock issues.
            - Prefer manual_review for borderline risk or higher-dollar invoices.
            - Approve only when the invoice is clean or clearly low risk.

            Risk score must be an integer from 0 to 100.

            Reasoning requirements:
            - The reason must reference only the actual listed issues or actual provided invoice fields.
            - Keep the reason concise and specific.
            - Do not mention imaginary or inferred issues.

            Return structured output only.
            You may call tools to retrieve invoice data, validation results,
            and policy classification.

            Use the available tools before making a decision if additional
            information is needed.
            """,
            output_schema=ApprovalDecision,
            tools=[
            get_invoice,
            get_validation_summary,
            get_policy_lane,
            ],
        )

        self.critique_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            instructions="""
            You are a critique agent reviewing an invoice approval decision.

            Your job is to check whether the proposed decision is too risky or too lenient.

            You must base your critique ONLY on:
            - the invoice fields explicitly provided
            - the policy lane explicitly provided
            - the validation summary explicitly provided
            - the initial decision explicitly provided

            Do NOT introduce new facts, assumptions, or risks that are not present in the provided information.
            Do NOT claim an issue exists unless it is explicitly listed.

            Critique rules:
            - Be more conservative than the first decision if needed.
            - If there is a serious validation issue, do not approve.
            - If the invoice is borderline, prefer manual_review over approval.
            - Keep the corrected reason concise and grounded in the provided validation summary.

            Risk score must be an integer from 0 to 100.

            Return a corrected final decision in the same structured format.
            You may call tools to retrieve invoice data, validation results,
            and policy classification.

            Use the available tools before making a decision if additional
            information is needed.
            """,
            output_schema=ApprovalDecision,
            tools=[
            get_invoice,
            get_validation_summary,
            get_policy_lane,
            ],
        )

    def run(self) -> Dict[str, ApprovalDecision]:
        decisions: Dict[str, ApprovalDecision] = {}

        for invoice_number in GLOBAL_INVOICE_STATE.canonical_invoices.keys():

            # initial decision (agent will call tools internally)
            decision = self._make_initial_decision(invoice_number)

            # reflection loop
            for _ in range(2):  # 2 critique passes is enough for this system
                critique = self._critique_decision(
                    invoice_number=invoice_number,
                    initial_decision=decision,
                )

                # if critique agrees, stop
                if critique.status == decision.status and critique.risk_score == decision.risk_score:
                    break

                # otherwise adopt critique as revised decision
                decision = critique

            decisions[invoice_number] = decision

        return decisions

    def summarize_validation_issues(self, invoice_number: str) -> str:
        validation = GLOBAL_INVOICE_STATE.invoice_validations.get(invoice_number)

        if not validation:
            return "No validation record found."

        if not validation.issues:
            return "No validation issues. Invoice passed validation."

        grouped: Dict[str, List[str]] = {}
        for issue in validation.issues:
            grouped.setdefault(issue.issue_type, []).append(issue.message)

        lines: List[str] = []
        for issue_type, messages in grouped.items():
            lines.append(f"{issue_type}:")
            unique_messages = list(dict.fromkeys(messages))
            for msg in unique_messages:
                lines.append(f"- {msg}")

        return "\n".join(lines)

    def _preclassify(self, invoice_number: str) -> str:
        """
        Deterministic lane assignment:
        - auto_reject_candidate
        - manual_review_candidate
        - auto_approve_candidate
        """
        invoice = GLOBAL_INVOICE_STATE.canonical_invoices[invoice_number]
        validation = GLOBAL_INVOICE_STATE.invoice_validations.get(invoice_number)

        if validation is None:
            return "manual_review_candidate"

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

        issue_types = {issue.issue_type for issue in validation.issues}

        if issue_types & hard_reject_issue_types:
            return "auto_reject_candidate"

        if issue_types & suspicious_issue_types:
            return "manual_review_candidate"

        if invoice.total is not None and invoice.total > 10000:
            return "manual_review_candidate"

        if validation.issues:
            return "manual_review_candidate"

        return "auto_approve_candidate"

    def _make_initial_decision(self, invoice_number: str) -> ApprovalDecision:
        prompt = f"""
            Invoice number: {invoice_number}
            Make an approval decision.
            """

        result = self.decision_agent.run(prompt)
        decision = cast(ApprovalDecision, result.content)
        return self._normalize_decision(decision, invoice_number)

    def _critique_decision(self, invoice_number: str, initial_decision: ApprovalDecision) -> ApprovalDecision:
        prompt = f"""
            Invoice number: {invoice_number}

            Initial decision:
            - status: {initial_decision.status}
            - approved: {initial_decision.approved}
            - risk_score: {initial_decision.risk_score}
            - reason: {initial_decision.reason}

            Review the initial decision and return a corrected final decision if needed.
            """

        result = self.critique_agent.run(prompt)
        critique = cast(ApprovalDecision, result.content)
        return self._normalize_decision(critique, invoice_number)

    def _merge_decisions(
        self,
        initial: ApprovalDecision,
        critique: ApprovalDecision,
    ) -> ApprovalDecision:
        """
        Conservative merge:
        rejected > manual_review > approved
        risk score = max
        """
        priority = {
            "approved": 0,
            "manual_review": 1,
            "rejected": 2,
        }

        initial_status = self._normalize_status(initial.status)
        critique_status = self._normalize_status(critique.status)

        if priority[critique_status] >= priority[initial_status]:
            chosen = critique
            chosen_status = critique_status
        else:
            chosen = initial
            chosen_status = initial_status

        final_risk = max(initial.risk_score, critique.risk_score)
        approved = chosen_status == "approved"

        return ApprovalDecision(
            invoice_number=chosen.invoice_number,
            approved=approved,
            status=chosen_status,
            reason=chosen.reason,
            risk_score=max(0, min(100, final_risk)),
        )

    def _normalize_decision(
        self,
        decision: ApprovalDecision,
        invoice_number: str,
    ) -> ApprovalDecision:
        status = self._normalize_status(decision.status)
        risk_score = max(0, min(100, int(decision.risk_score)))
        approved = status == "approved"

        return ApprovalDecision(
            invoice_number=invoice_number,
            approved=approved,
            status=status,
            reason=decision.reason,
            risk_score=risk_score,
        )

    def _normalize_status(self, status: str) -> str:
        value = (status or "").strip().lower()

        if value in {"approve", "approved"}:
            return "approved"
        if value in {"reject", "rejected"}:
            return "rejected"
        if value in {"manual_review", "manual review", "review"}:
            return "manual_review"

        return "manual_review"