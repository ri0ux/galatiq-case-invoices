# Invoice Processing Automation

This project is an automated invoice processing pipeline that ingests invoices, validates them, performs fraud screening, determines approval decisions, and executes simulated payments. The system uses a multi-agent architecture where each stage of the pipeline is responsible for a specific part of the workflow.

The application can be run in two ways:

1. As a command-line pipeline that processes invoices and exports results.
2. Through a Streamlit interface that allows users to upload invoices and view results in a dashboard.

The pipeline produces a structured output file (`final_invoice_state.json`) that contains the complete system state after processing.

---

# System Overview

The pipeline processes invoices through the following stages:

## 1. Ingestion

Invoice files are loaded and parsed into structured `Invoice` objects. Extraction is performed concurrently so multiple invoices can be processed at once.

## 2. Canonicalization

Invoices are normalized and merged into a canonical format. Duplicate invoices or conflicting data are recorded as conflicts.

## 3. Validation

Invoices undergo several validation checks:

- Required field validation
- Date validation
- Arithmetic validation
- Fraud screening
- Inventory pressure analysis
- Sequential inventory allocation

Validation produces both invoice-level and item-level validation results.

## 4. Approval

Invoices are evaluated against policy rules and validation outcomes to determine an approval decision:

- Approved
- Manual Review
- Rejected

## 5. Payment

Invoices that are approved proceed to the payment stage. Payment results are recorded in the global state.

## 6. Export

The full pipeline state is exported to:

```
final_invoice_state.json
```

This file contains invoices, validation results, approval decisions, item analysis, and payment outcomes.

---

# Project Structure

```
agents/
    ingestion_agent.py
    approval_agent.py
    payment_agent.py

    validation_agents/
        validation_team.py
        deterministic_validation_agent.py
        fraud_detection_agent.py
data/
    generate_pdfs.py
    invoices/
      all invoices (pdf, json, xml, etc)

models/
    invoice_schema.py
    validation_schema.py
    invoice_state.py
    approval_schema.py
    payment_schema.py

tools/
    validation_tools.py
    approval_tools.py
    inventory_tools.py
    parsing_tools.py
    payment_tools.py

utils/
    cli.py
    invoice_loader.py
    logger.py
    text_normalize.py
    normalizer.py
    db_functions.py
    file_loader.py
    invoice_canonicalizer.py

orchestrator/
    workflow.py

app.py
main.py
```

---

# Running the Pipeline (Command Line)

The command-line interface processes invoices and writes the final system state to disk.

## Run with a single invoice

```
python main.py --invoice_path=path/to/invoice.txt
```

## Run with a directory of invoices

```
python main.py --invoice_dir=path/to/invoices/
```

After execution, the system writes:

```
final_invoice_state.json
```

This file contains the complete output of the pipeline.

---

# Running the Streamlit UI

The Streamlit application provides an interface for uploading invoices and visualizing pipeline results.

## Start the UI

```
streamlit run app.py
```

## Using the Interface

1. Upload one or more invoice files in the sidebar.
2. Click **Run Pipeline**.
3. The system executes the full invoice pipeline.
4. Results are displayed in several sections:
   - Pipeline summary metrics
   - Invoice results table
   - Detailed invoice view
   - Aggregated inventory demand
   - Item validation results
   - Invoice conflicts

The UI reads the final pipeline state and displays it in a structured dashboard.

---

# Inventory Database

Inventory validation uses a SQLite database (`inventory.db`) that contains available stock levels for items.

Example table structure:

```
inventory
---------------------
item      TEXT
stock     INTEGER
```

Inventory validation includes:

- Unknown item detection
- Out-of-stock detection
- Insufficient inventory detection
- Sequential inventory allocation across invoices

---

# Validation Types

The validation stage includes both deterministic checks and LLM-assisted analysis.

## Deterministic Checks

- Required field validation
- Date consistency checks
- Arithmetic validation
- Inventory allocation checks

## LLM Checks

- Fraud detection
- Item name normalization

---

# Output

The final output of the system is stored in:

```
final_invoice_state.json
```

This file includes:

- Raw invoices
- Canonical invoices
- Validation results
- Item-level validations
- Approval decisions
- Payment results

The file can be inspected directly or visualized through the Streamlit UI.

---

# Requirements

Install dependencies before running the project.

```
pip install -r requirements.txt
```

The application requires:

- Python 3.10+
- Streamlit
- SQLite
- OpenAI-compatible API access for LLM agents

Environment variables must include:

```
OPENAI_API_KEY=your_key_here
```

---

# Logs

Logs for the pipeline can be viewed in logs/invoice_pipeline.txt

# Notes

The architecture separates deterministic validation logic from LLM-assisted reasoning. This design ensures that core validation rules remain predictable while allowing the system to perform contextual fraud analysis and normalization when needed.

The orchestrator coordinates all pipeline stages and updates the global system state as the workflow progresses.
