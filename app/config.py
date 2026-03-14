import os

from dotenv import load_dotenv
from agno.models.google import Gemini

load_dotenv()


def get_model() -> Gemini:
    """Return the configured Gemini model instance.

    retry_with_guidance_limit=3 gives the model up to 3 attempts to
    self-correct when Gemini produces a malformed function call (e.g.
    invalid JSON in delegation tool calls).  This is the primary
    mitigation for the MALFORMED_FUNCTION_CALL finish reason.
    """
    return Gemini(
        id=os.getenv("MODEL_ID", "gemini-2.5-flash"),
        retry_with_guidance_limit=3,
    )
