"""Company validation tool for classifying inputs as public or private companies."""

import json
from typing import Any

import yfinance as yf
from agno.tools import Toolkit


class CompanyValidationTool(Toolkit):
    """Validates and classifies company identifiers.

    For each input, determines whether it is:
    - A valid public company ticker (verified via YFinance)
    - A private company name (not found on YFinance)

    This classification drives downstream behavior: public companies
    use YFinance for data; private companies use web search.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="company_validation",
            tools=[self.validate_companies],
            **kwargs,
        )

    def validate_companies(self, identifiers: str) -> str:
        """Classify a comma-separated list of company identifiers.

        Each identifier can be a stock ticker (e.g., "AAPL") or a company
        name (e.g., "Anthropic"). The tool checks YFinance first; if the
        identifier is not found, it is classified as a private company.

        Args:
            identifiers: Comma-separated tickers or company names
                         (e.g., "NVDA,Anthropic,AAPL,OpenAI")

        Returns:
            JSON with public_companies, private_companies, and details.
        """
        id_list = [t.strip() for t in identifiers.split(",") if t.strip()]

        if not id_list:
            return json.dumps(
                {
                    "error": (
                        "No company identifiers provided. Please provide "
                        "comma-separated tickers or company names "
                        "(e.g. 'AAPL,Anthropic,NVDA')."
                    ),
                    "public_companies": [],
                    "private_companies": [],
                }
            )

        public: list[dict[str, str]] = []
        private: list[dict[str, str]] = []

        for identifier in id_list:
            ticker_candidate = identifier.strip().upper()
            try:
                info = yf.Ticker(ticker_candidate).info
                if info and info.get("shortName"):
                    public.append(
                        {
                            "ticker": ticker_candidate,
                            "company_name": info.get("shortName", identifier),
                            "exchange": info.get("exchange", "Unknown"),
                            "company_type": "PUBLIC",
                        }
                    )
                else:
                    private.append(
                        {
                            "company_name": identifier,
                            "company_type": "PRIVATE",
                            "reason": (
                                f"'{identifier}' not found on Yahoo Finance. "
                                f"Treating as private company."
                            ),
                        }
                    )
            except Exception:
                private.append(
                    {
                        "company_name": identifier,
                        "company_type": "PRIVATE",
                        "reason": (
                            f"'{identifier}' could not be looked up. "
                            f"Treating as private company."
                        ),
                    }
                )

        result: dict[str, Any] = {
            "public_companies": public,
            "private_companies": private,
            "summary": {
                "total": len(id_list),
                "public_count": len(public),
                "private_count": len(private),
            },
        }

        if private:
            names = ", ".join(p["company_name"] for p in private)
            result["note"] = (
                f"The following are classified as private companies: {names}. "
                "Use web search (Tavily) instead of YFinance for data gathering."
            )

        return json.dumps(result, indent=2)
