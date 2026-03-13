import sqlite3
from typing import Dict
from utils.text_normalizer import deterministic_normalize

def load_inventory(db_path) -> Dict[str, int]:
    inventory: Dict[str, int] = {}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT item, stock FROM inventory")
        rows = cursor.fetchall()

        for item_name, stock in rows:
            normalized_name = deterministic_normalize(item_name)
            inventory[normalized_name] = int(stock)
    finally:
        conn.close()

    return inventory