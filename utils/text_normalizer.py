import re

def deterministic_normalize(name: str) -> str:
    value = (name or "").strip().lower()
    value = re.sub(r"\(.*?\)", "", value)
    value = re.sub(r"[^a-z0-9\s]", "", value)
    value = value.replace(" ", "")
    return value.strip()