import sqlite3

def initialize_database():
    conn = sqlite3.connect('inventory.db')  # Persist to file so all agents can access it
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS inventory')
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (item TEXT PRIMARY KEY, stock INTEGER)')
    cursor.execute("""
        INSERT INTO inventory VALUES
        ('WidgetA', 1000000),
        ('WidgetB', 1000000000),
        ('GadgetX', 10000000),
        ('FakeItem', 0),
        ('WidgetC', 987348),
        ('SuperGizmo', 79820347),
        ('MegaSprocket', 879123)
        """)
    conn.commit()
    conn.close()