## Project Structure

galatiq-case-invoices/

agents/
ingestion_agent.py
validation_agent.py
approval_agent.py
payment_agent.py

tools/
inventory_tools.py
payment_tools.py
parsing_tools.py

orchestration/
workflow.py

models/
invoice_schema.py
validation_schema.py

database/
setup_inventory.py

utils/
logger.py
file_loader.py

data/

main.py
requirements.txt
README.md

## Architecture

Agent Framework: Agno
Model: OpenAI - gpt-4.1-mini
Workflow: explicit orchestrator
Tools: Python functions
Database: SQLite

extract_agent → validation_agent → approval_agent → payment_agent

                 Orchestrator

                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼

Ingestion Agent Validation Agent Approval Agent
│
▼
Payment Agent
