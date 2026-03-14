"""Ticker validation tool for verifying stock symbols against YFinance."""

import json
from typing import Any

import yfinance as yf
from agno.tools import Toolkit


class TickerValidationTool(Toolkit):
    """Validates stock ticker symbols using YFinance.

    Used by the Research Agent to verify tickers before spending
    time and API credits on full research.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="ticker_validation",
            tools=[self.validate_tickers],
            **kwargs,
        )

    def validate_tickers(self, tickers: str) -> str:
        """Validate a comma-separated list of stock ticker symbols.

        Checks each ticker against Yahoo Finance to verify it exists
        and represents a real, active company.

        Args:
            tickers: Comma-separated ticker symbols (e.g. "AAPL,MSFT,NVDA")

        Returns:
            JSON with valid_tickers, invalid_tickers, and details.
        """
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

        if not ticker_list:
            return json.dumps(
                {
                    "error": (
                        "No ticker symbols provided. Please provide "
                        "comma-separated ticker symbols (e.g. 'AAPL,MSFT,NVDA')."
                    ),
                    "valid_tickers": [],
                    "invalid_tickers": [],
                }
            )

        valid: list[dict[str, str]] = []
        invalid: list[dict[str, str]] = []

        for symbol in ticker_list:
            try:
                info = yf.Ticker(symbol).info
                if info and info.get("shortName"):
                    valid.append(
                        {
                            "ticker": symbol,
                            "name": info.get("shortName", "Unknown"),
                            "exchange": info.get("exchange", "Unknown"),
                        }
                    )
                else:
                    invalid.append(
                        {
                            "ticker": symbol,
                            "reason": (
                                f"Ticker '{symbol}' was not found or has no data "
                                f"on Yahoo Finance. Check the symbol and try again."
                            ),
                        }
                    )
            except Exception as e:
                invalid.append(
                    {
                        "ticker": symbol,
                        "reason": f"Error looking up '{symbol}': {e}",
                    }
                )

        result: dict[str, Any] = {
            "valid_tickers": [v["ticker"] for v in valid],
            "invalid_tickers": [i["ticker"] for i in invalid],
            "details": {
                "valid": valid,
                "invalid": invalid,
            },
        }

        if invalid:
            names = ", ".join(i["ticker"] for i in invalid)
            result["warning"] = (
                f"The following tickers could not be validated: {names}. "
                "Please verify these symbols. Common issues: ticker may be "
                "delisted, misspelled, or use a different exchange suffix "
                "(e.g., .L for London, .TO for Toronto)."
            )

        return json.dumps(result, indent=2)
