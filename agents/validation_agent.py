import sqlite3
from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from models import validation_schema
from models.validation_schema import ValidationResult


class ValidationAgent:

    def __init__(self, db_path="inventory.db"):
        self.conn = sqlite3.connect(db_path)
        self.agent = Agent(
            model=OpenAIResponses("gpt-4.1-mini"),
            markdown=True,
            output_schema=ValidationResult,
            # eventually add more validation tools
            tools=[self.get_count_of_item]
            )

    def get_count_of_item(self, item: str):
        """Use this function to get count of items in the sql db.
            Args:
        item (int): Number of stories to return. Defaults to 10.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            "SELECT stock FROM inventory WHERE item=?",
                (item)
        )
        result = cursor.fetchone()
        if not result:
            return "No item found."
        else:
            return result[0]


    def run(self, invoice_state):


        return invoice_state