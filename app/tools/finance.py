from app.tools.resilient_wrappers import ResilientYFinanceTools


def get_finance_tools() -> ResilientYFinanceTools:
    """Return YFinance tools with retry and circuit breaker.

    Used by the Research Agent to gather stock prices, analyst
    recommendations, company info, and company news.
    """
    return ResilientYFinanceTools(
        enable_stock_price=True,
        enable_analyst_recommendations=True,
        enable_company_info=True,
        enable_company_news=True,
    )
