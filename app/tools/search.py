from app.tools.resilient_wrappers import ResilientTavilyTools


def get_search_tools() -> ResilientTavilyTools:
    """Return Tavily search tools with retry and circuit breaker.

    Used by the Research Agent to find general news, negative news,
    lawsuits, and regulatory information about companies.
    """
    return ResilientTavilyTools()
