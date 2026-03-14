from agno.agent import Agent

from app.config import get_model
from app.tools.finance import get_finance_tools
from app.tools.search import get_search_tools
from app.tools.ticker_validation import CompanyValidationTool


def create_research_agent() -> Agent:
    """Create the Research Agent (Specialist #1).

    Performs comprehensive data gathering for all downstream agents.
    Adapts its strategy based on whether companies are public or private:
    - Public companies: YFinance for financials + Tavily for news
    - Private companies: Tavily-only for all data
    """
    return Agent(
        name="Research Agent",
        role="Financial research specialist",
        description=(
            "Gathers comprehensive financial data, news, and risk-relevant "
            "information for a set of companies in a given sector. Handles "
            "both publicly traded companies (via YFinance) and private "
            "companies (via web search)."
        ),
        model=get_model(),
        tools=[get_search_tools(), get_finance_tools(), CompanyValidationTool()],
        instructions=[
            "You are a financial research specialist.",
            "",
            "STEP 0 - CLASSIFY COMPANIES:",
            "Before gathering any research data, ALWAYS use the validate_companies tool "
            "to classify the requested companies. Pass all company identifiers (tickers "
            "or names) as a comma-separated list.",
            "The tool will classify each as PUBLIC (found on Yahoo Finance) or PRIVATE "
            "(not publicly traded).",
            "",
            "STEP 1 - RESEARCH PUBLIC COMPANIES:",
            "For each PUBLIC company, use YFinance tools to collect:",
            "- Current stock price and market capitalization",
            "- P/E ratio and revenue growth",
            "- Analyst consensus rating",
            "And use Tavily search to find:",
            "- 3-5 recent news headlines (covering both positive and negative developments)",
            "- Key products and services",
            "- Competitive position in the sector",
            "- Negative news: lawsuits, controversies, regulatory issues",
            "Set company_type to 'PUBLIC' and include the ticker.",
            "",
            "STEP 2 - RESEARCH PRIVATE COMPANIES:",
            "For each PRIVATE company, use Tavily search to find:",
            "- Latest funding round, total funding raised, and latest valuation",
            "- Key investors and backers",
            "- Estimated annual revenue or ARR (if available publicly)",
            "- Current funding stage (Seed, Series A/B/C/D, etc.)",
            "- Key products and services",
            "- Competitive position in the sector",
            "- 3-5 recent news headlines",
            "- Negative news: lawsuits, controversies, regulatory issues",
            "Set company_type to 'PRIVATE' and leave ticker as null.",
            "Do NOT use YFinance tools for private companies.",
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
