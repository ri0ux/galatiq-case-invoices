from json import load
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    AI_KEY = os.getenv("AI_KEY", "")
    MODEL = os.getenv("AI_MODEL", "")