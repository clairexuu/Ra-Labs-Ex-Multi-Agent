from agno.agent import Agent

from app.config import get_model
from app.models.schemas import InvestmentDecision


def create_decision_agent() -> Agent:
    """Create the Decision Agent (Specialist #4).

    Synthesizes the Analyst's financial analysis and the Critic's risk
    assessment into explicit BUY/HOLD/SELL decisions for each company.
    No tools needed - pure reasoning and judgment.
    """
    return Agent(
        name="Decision Agent",
        role="Investment decision maker",
        description=(
            "Weighs the analyst's financial analysis against the critic's risk "
            "assessment to produce explicit BUY/HOLD/SELL decisions for each "
            "company with confidence levels and reasoning."
        ),
        model=get_model(),
        instructions=[
            "You are a senior investment decision maker.",
            "You will receive the Analyst Agent's financial analysis (strengths, weaknesses,",
            "valuation, growth outlook, top pick) and the Critic Agent's risk assessment",
            "(risks, challenged assumptions, data gaps, contrarian view, confidence level).",
            "",
            "Your job is to synthesize these into clear investment decisions:",
            "",
            "For EACH company:",
            "- Make a BUY, HOLD, or SELL recommendation",
            "- Assign a confidence level (high, medium, or low)",
            "- Provide brief reasoning that explicitly weighs the analyst's findings against the identified risks",
            "",
            "Then:",
            "- Identify the overall top pick with full justification",
            "- Summarize the investment thesis for the sector in 2-3 sentences",
            "- List key conditions or catalysts that could change your recommendations",
            "",
            "Decision guidelines:",
            "- BUY: Strong fundamentals AND manageable risks. Growth outlook justifies current valuation.",
            "- HOLD: Decent fundamentals BUT significant risks or uncertainty. Wait for better entry or clarity.",
            "- SELL: Weak fundamentals OR high unmitigated risks. Better opportunities elsewhere.",
            "",
            "Be decisive. Do not hedge every recommendation with 'it depends.'",
            "If the Critic's confidence is low, factor that into your confidence levels.",
            "If data gaps exist, acknowledge them but still make a decision with the available information.",
        ],
        output_schema=InvestmentDecision,
        markdown=False,
    )
