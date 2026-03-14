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
            "STEP 0a - COMPANY DISCOVERY (when no specific companies are named):",
            "If the user's request asks you to FIND or DISCOVER companies in a sector/niche "
            "(e.g., 'find 3 AI startups in autonomous driving') rather than providing specific "
            "company names or tickers, use the discover_companies tool FIRST.",
            "Pass the sector/niche keyword, the requested count, and the company_type filter:",
            "- Use company_type='PRIVATE' when the user says 'startups' or 'private companies'",
            "- Use company_type='PUBLIC' when the user says 'public companies' or 'stocks'",
            "The discover_companies tool will search for and validate companies, returning them "
            "in the same format as validate_companies. After discovery, proceed to STEP 1 and "
            "STEP 2 using the discovered companies as if the user had named them explicitly.",
            "Do NOT call validate_companies after discover_companies - the discovery tool "
            "already performs validation.",
            "",
            "IMPORTANT: After discovery, only use the successfully returned companies. "
            "Do NOT report to the user which companies were rejected, failed verification, "
            "or were filtered out during discovery. Present the discovered companies "
            "seamlessly as if they were always the target companies.",
            "",
            "STEP 0 - CLASSIFY COMPANIES:",
            "Before gathering any research data, ALWAYS use the validate_companies tool "
            "to classify the requested companies. Pass all company identifiers (tickers "
            "or names) as a comma-separated list.",
            "The tool will classify each as PUBLIC (found on Yahoo Finance) or PRIVATE "
            "(not publicly traded). Private companies are also verified via web search "
            "and assigned a verification_status (VERIFIED, UNVERIFIED, or SEARCH_FAILED).",
            "",
            "IMPORTANT - UNVERIFIED COMPANIES:",
            "After classifying companies, check the validation results for any companies "
            "with verification_status 'UNVERIFIED'. For these companies:",
            "- Include a prominent warning in the research output noting the company "
            "could not be verified as a real entity",
            "- Still attempt to research the company, but note that data may be unreliable",
            "- Set verification_status and confidence_score in the CompanyResearch output",
            "If a company has verification_status 'SEARCH_FAILED', note the verification "
            "gap and proceed with available information.",
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
