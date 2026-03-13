from agno.tools.yfinance import YFinanceTools


def get_finance_tools() -> YFinanceTools:
    """Return configured YFinance tools for financial data retrieval.

    Used by the Research Agent to gather stock prices, analyst
    recommendations, company info, and company news.
    """
    return YFinanceTools(
        enable_stock_price=True,
        enable_analyst_recommendations=True,
        enable_company_info=True,
        enable_company_news=True,
    )
