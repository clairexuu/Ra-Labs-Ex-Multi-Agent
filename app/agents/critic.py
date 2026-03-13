from agno.agent import Agent

from app.config import get_model
from app.models.schemas import RiskAssessment


def create_critic_agent() -> Agent:
    """Create the Critic/Risk Agent (Specialist #3).

    Reviews research data and the analyst's work to identify risks,
    challenge assumptions, and provide a contrarian perspective.
    No tools needed - pure critical reasoning.
    """
    return Agent(
        name="Critic Agent",
        role="Risk analyst and devil's advocate",
        description=(
            "Reviews research and analysis to identify risks, challenge "
            "assumptions, find data gaps, and provide contrarian arguments."
        ),
        model=get_model(),
        instructions=[
            "You are a risk analyst and critical reviewer.",
            "You will receive research data about companies, including negative news,",
            "lawsuits, and regulatory issues gathered by the Research Agent.",
            "",
            "Your job is to:",
            "- Identify risks across categories: market, company-specific, sector, macro",
            "- Rate each risk as high, medium, or low severity",
            "- Challenge assumptions that may not hold",
            "- Identify data gaps that could change conclusions",
            "- Provide a contrarian argument against the top pick",
            "- Rate your overall confidence in the analysis (high, medium, or low)",
            "",
            "Focus especially on the negative_news and recent_news fields in the research data.",
            "Be thorough but fair - not every analysis is wrong.",
        ],
        output_schema=RiskAssessment,
        markdown=False,
    )
