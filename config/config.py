from json import load
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_PATH = "inventory.db"