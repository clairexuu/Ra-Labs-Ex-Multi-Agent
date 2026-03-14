from agno.agent import Agent

from app.config import get_model
from app.tools.finance import get_finance_tools
from app.tools.search import get_search_tools
from app.tools.ticker_validation import TickerValidationTool


def create_research_agent() -> Agent:
    """Create the Research Agent (Specialist #1).

    Performs comprehensive data gathering for all downstream agents:
    - General info and recent news (for the final memo)
    - Financial data (for the Analyst Agent)
    - Negative news, lawsuits, regulatory issues (for the Critic Agent)
    """
    return Agent(
        name="Research Agent",
        role="Financial research specialist",
        description=(
            "Gathers comprehensive financial data, news, and risk-relevant "
            "information for a set of companies in a given sector."
        ),
        model=get_model(),
        tools=[get_search_tools(), get_finance_tools(), TickerValidationTool()],
        instructions=[
            "You are a financial research specialist.",
            "",
            "STEP 0 - VALIDATE TICKERS:",
            "Before gathering any research data, ALWAYS use the validate_tickers tool "
            "to verify that the requested ticker symbols are valid.",
            "If any tickers are invalid, report the invalid tickers in your response "
            "with the suggestion to check the ticker symbol.",
            "Continue researching only the valid tickers.",
            "If ALL tickers are invalid, stop and report the issue.",
            "",
            "For each VALID company ticker, gather comprehensive data using your tools.",
            "",
            "Use YFinance tools to collect:",
            "- Current stock price and market capitalization",
            "- P/E ratio and revenue growth",
            "- Analyst consensus rating",
            "",
            "Use Tavily search to find:",
            "- 3-5 recent news headlines (covering both positive and negative developments)",
            "- Key products and services",
            "- Competitive position in the sector",
            "- Negative news: lawsuits, controversies, regulatory issues, management concerns",
            "",
            "IMPORTANT: If a tool call fails or returns no data for a company, "
            "note the data gap and continue with available information. "
            "Do not stop the entire research if one data point is unavailable.",
            "",
            "Include today's date as the research_date.",
        ],
        retries=2,
        delay_between_retries=2,
        exponential_backoff=True,
        markdown=False,
    )
