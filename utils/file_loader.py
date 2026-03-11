import os
import json
import fitz  # PyMuPDF


def load_single_invoice(path: str) -> str:
    """Load invoice file based on extension."""

    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    extension = os.path.splitext(path)[1].lower()

    if extension == ".pdf":
        return load_pdf(path)

    elif extension in [".txt", ".csv", ".xml"]:
        return load_text(path)

    elif extension == ".json":
        return load_json(path)

    else:
        raise ValueError(f"Unsupported file type: {extension}")


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def load_json(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return json.dumps(data, indent=2)


def load_pdf(path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    
    text = []

    with fitz.open(path) as doc:
        for page in doc:
            text.append(page.get_text())

    return "\n".join(text)


def load_invoice_directory(directory: str):

    if not os.path.exists(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = []

    for filename in os.listdir(directory):

        full_path = os.path.join(directory, filename)

        if os.path.isfile(full_path):
            files.append(full_path)

    return files