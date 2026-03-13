from agno.agent import Agent
import json
from agno.models.openai import OpenAIResponses
from models.invoice_schema import ItemCollection, LineItem
from models.validation_schema import InvoiceValidation, ItemValidation
from models.invoice_state import GLOBAL_INVOICE_STATE
from tools.inventory_tools import get_count_of_item
from typing import cast, Dict, List
from pydantic import BaseModel, Field
import re

approved_invoices = {
    a.invoice_number
    for a in GLOBAL_INVOICE_STATE.approvals
    if a.approved
}

def normalize_item_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\(.*?\)", "", name)  # remove modifiers like "(rush order)"
    name = name.replace(" ", "")
    return name


def item_summarizer() -> ItemCollection:

    invoices = GLOBAL_INVOICE_STATE.invoices

    aggregated = {}

    for invoice in invoices.values():
        if invoice.invoice_number not in approved_invoices:
            continue 
        for item in invoice.line_items:

            normalized = normalize_item_name(item.item)

            quantity = item.quantity
            unit_price = item.unit_price
            total_price = item.total_price

            if total_price is None:
                total_price = quantity * unit_price

            if normalized not in aggregated:
                aggregated[normalized] = LineItem(
                    item=normalized,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price
                )
            else:
                existing = aggregated[normalized]

                existing.quantity += quantity
                existing.total_price += total_price

    result = ItemCollection(items=list(aggregated.values()))

    GLOBAL_INVOICE_STATE.items = result.items

    return result