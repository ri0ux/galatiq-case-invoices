import sqlite3


conn = sqlite3.connect("inventory.db")
def get_count_of_item(item: str):
    """Use this function to get count of items in the sql db.
        Args:
    item (int): Number of stories to return. Defaults to 10.
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