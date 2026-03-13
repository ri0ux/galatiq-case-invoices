import sqlite3


conn = sqlite3.connect("inventory.db")
def get_count_of_item(item: str):
    """
    Get inventory count for an item from SQLite database.

    Args:
        item (str): item name

    Returns:
        int | None
    """
    cursor = conn.cursor()

    cursor.execute(
        "SELECT stock FROM inventory WHERE item=?",
        (item,)
    )

    result = cursor.fetchone()

    if not result:
        return None

    return result[0]