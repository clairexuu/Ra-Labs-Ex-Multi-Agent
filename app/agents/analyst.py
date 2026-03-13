from agno.agent import Agent

from app.config import get_model
from app.models.schemas import FinancialAnalysis


def create_analyst_agent() -> Agent:
    """Create the Analyst Agent (Specialist #2).

    Produces comparative financial analysis from the research data
    provided by the Research Agent. No tools needed - pure reasoning.
    """
    return Agent(
        name="Analyst Agent",
        role="Senior financial analyst",
        description=(
            "Analyzes research data to produce comparative financial analysis "
            "with strengths, weaknesses, valuation, and growth outlook per company."
        ),
        model=get_model(),
        instructions=[
            "You are a senior financial analyst.",
            "You will receive research data about multiple companies in a sector.",
            "",
            "Focus on the FINANCIAL aspects of the research data:",
            "- Current price, market cap, P/E ratio, revenue growth",
            "- Analyst consensus ratings",
            "- Competitive positioning",
            "",
            "For each company, produce:",
            "- 2-4 key strengths",
            "- 2-4 key weaknesses",
            "- Valuation assessment (overvalued, fairly valued, or undervalued) with reasoning",
            "- Growth outlook for the next 12-18 months",
            "",
            "Then provide a comparative summary and identify your top pick with justification.",
            "",
            "Base your analysis only on the data provided. Do not fabricate financial numbers.",
            "If data is missing for a company, acknowledge the gap and work with what is available.",
        ],
        output_schema=FinancialAnalysis,
        markdown=False,
    )
