import os

from dotenv import load_dotenv
from agno.models.google import Gemini

load_dotenv()


def get_model() -> Gemini:
    """Return the configured Gemini model instance."""
    return Gemini(id=os.getenv("MODEL_ID", "gemini-2.5-flash"))
