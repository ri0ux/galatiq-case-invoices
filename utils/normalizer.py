import re
from typing import Dict, List, cast
from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from models.validation_schema import NamingResult, ValidationIssue
from utils.db_functions import load_inventory
from config.config import Config
from utils.text_normalizer import deterministic_normalize

name_cache: Dict[str, str] = {}

naming_agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=NamingResult,
        )

def normalize_item_name(name: str) -> str:
        if name in name_cache:
            return name_cache[name]

        deterministic = deterministic_normalize(name)

        if deterministic in load_inventory_keys():
            name_cache[name] = deterministic
            return deterministic

        try:
            result = cast(NamingResult, naming_agent.run(input=name).content)
            normalized = deterministic_normalize(result.name)
        except Exception:
            normalized = deterministic

        name_cache[name] = normalized
        return normalized

def normalize_issues(issues: List[ValidationIssue]) -> List[ValidationIssue]:
    normalized: List[ValidationIssue] = []

    for issue in issues:
        normalized.append(
            ValidationIssue(
                item=issue.item,
                issue_type=_normalize_issue_type(issue.issue_type),
                message=issue.message.strip(),
            )
        )

    return normalized

def load_inventory_keys() -> set[str]:
    return set(load_inventory(Config.DB_PATH).keys())

def dedupe_issues(issues: List[ValidationIssue]) -> List[ValidationIssue]:
    deduped: List[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()

    for issue in issues:
        key = (issue.item or "", issue.issue_type, issue.message)
        if key not in seen:
            deduped.append(issue)
            seen.add(key)

    return deduped

def _normalize_issue_type(issue_type: str) -> str:
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
