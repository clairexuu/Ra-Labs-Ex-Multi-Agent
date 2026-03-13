from agno.tools.tavily import TavilyTools


def get_search_tools() -> TavilyTools:
    """Return configured Tavily search tools.

    Used by the Research Agent to find general news, negative news,
    lawsuits, and regulatory information about companies.
    """
    return TavilyTools()
