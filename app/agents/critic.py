from agno.agent import Agent

from app.config import get_model
from app.models.schemas import RiskAssessment


def create_critic_agent() -> Agent:
    """Create the Critic/Risk Agent (Specialist #3).

    Reviews research data to identify risks, challenge assumptions,
    and provide a contrarian perspective.  Runs in parallel with the
    Analyst Agent (does not depend on analysis output).
    Handles risks specific to both public and private companies.
    No tools needed - pure critical reasoning.
    """
    return Agent(
        name="Critic Agent",
        role="Risk analyst and devil's advocate",
        description=(
            "Reviews research and analysis to identify risks, challenge "
            "assumptions, find data gaps, and provide contrarian arguments. "
            "Handles risks specific to both public and private companies."
        ),
        model=get_model(),
        instructions=[
            "You are a risk analyst and critical reviewer.",
            "You will receive research data about companies, including negative news,",
            "lawsuits, and regulatory issues gathered by the Research Agent.",
            "Companies may be PUBLIC (stock market) or PRIVATE (venture-backed/startup).",
            "",
            "Your job is to:",
            "- Identify risks across categories: market, company-specific, sector, macro, regulatory",
            "- Rate each risk as high, medium, or low severity",
            "- Challenge assumptions that may not hold",
            "- Identify data gaps that could change conclusions",
            "- Provide a contrarian argument against the top pick",
            "- Rate your overall confidence in the analysis (high, medium, or low)",
            "",
            "For PRIVATE companies, pay special attention to:",
            "- Data reliability (private companies disclose less; estimates may be wrong)",
            "- Liquidity risk (no public market to exit)",
            "- Funding risk (ability to raise next round)",
            "- Key-person risk (founder dependency)",
            "- Competitive risk from well-funded incumbents",
            "- Valuation risk (private valuations can be inflated)",
            "",
            "Focus especially on the negative_news and recent_news fields in the research data.",
            "Be thorough but fair - not every analysis is wrong.",
            "Use company names (not tickers) in affected_companies for private companies.",
        ],
        output_schema=RiskAssessment,
        retries=2,
        delay_between_retries=2,
        exponential_backoff=True,
        markdown=False,
    )
