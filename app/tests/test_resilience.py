"""Tests for tool-level retry, circuit breaker, and ticker validation."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.tools.resilient_wrappers import (
    CircuitBreaker,
    ResilientTavilyTools,
    ResilientYFinanceTools,
    _is_error_response,
    _resilient_method,
)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------
class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.is_open is False
        assert cb.allow_request() is True

    def test_trips_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True
        assert cb.allow_request() is False

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb.record_success()
        assert cb.is_open is False
        assert cb.consecutive_failures == 0

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.1)
        cb.record_failure()
        assert cb.allow_request() is False
        time.sleep(0.15)
        assert cb.allow_request() is True  # half-open: allows probe

    def test_failure_below_threshold_stays_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False
        assert cb.allow_request() is True

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        # Only 1 failure since last success, not 3
        assert cb.is_open is False


# ---------------------------------------------------------------------------
# Error response detection
# ---------------------------------------------------------------------------
class TestIsErrorResponse:
    def test_detects_error_fetching(self):
        assert _is_error_response("Error fetching current price for XYZ") is True

    def test_detects_could_not_fetch(self):
        assert _is_error_response("Could not fetch company info for XYZ") is True

    def test_detects_error_colon(self):
        assert _is_error_response("Error: something broke") is True

    def test_detects_error_getting(self):
        assert _is_error_response("Error getting analyst recommendations") is True

    def test_passes_valid_price(self):
        assert _is_error_response("123.45") is False

    def test_passes_valid_json(self):
        assert _is_error_response('{"Name": "NVIDIA"}') is False

    def test_handles_non_string(self):
        assert _is_error_response(42) is False
        assert _is_error_response(None) is False


# ---------------------------------------------------------------------------
# Resilient method wrapper
# ---------------------------------------------------------------------------
class TestResilientMethod:
    def test_returns_on_first_success(self):
        method = MagicMock(return_value="100.00")
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        result = wrapped("AAPL")
        assert result == "100.00"
        assert method.call_count == 1
        assert breaker.consecutive_failures == 0

    def test_retries_on_error_string(self):
        method = MagicMock(
            side_effect=[
                "Error fetching current price for AAPL",
                "100.00",
            ]
        )
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        result = wrapped("AAPL")
        assert result == "100.00"
        assert method.call_count == 2

    def test_retries_on_exception(self):
        method = MagicMock(
            side_effect=[
                ConnectionError("network down"),
                "100.00",
            ]
        )
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        result = wrapped("AAPL")
        assert result == "100.00"
        assert method.call_count == 2

    def test_exhausts_retries_and_records_failure(self):
        method = MagicMock(return_value="Error fetching data")
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=2, min_wait=0.01
        )
        result = wrapped("AAPL")
        assert "Error fetching data" in result
        assert method.call_count == 2
        assert breaker.consecutive_failures == 1

    def test_circuit_breaker_blocks_when_open(self):
        method = MagicMock(return_value="should not be called")
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()  # trip it
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        result = wrapped("AAPL")
        assert "Service temporarily unavailable" in result
        assert method.call_count == 0  # never called

    def test_all_exceptions_exhaust_retries(self):
        method = MagicMock(side_effect=TimeoutError("timeout"))
        breaker = CircuitBreaker(failure_threshold=5)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        result = wrapped("AAPL")
        assert "Error:" in result
        assert method.call_count == 3
        assert breaker.consecutive_failures == 1


# ---------------------------------------------------------------------------
# Integration: verify wrappers actually wrap entrypoints
# ---------------------------------------------------------------------------
class TestResilientToolsIntegration:
    def test_resilient_yfinance_has_functions(self):
        tools = ResilientYFinanceTools(
            enable_stock_price=True,
            enable_company_info=True,
        )
        assert len(tools.functions) > 0
        for func_name, func_obj in tools.functions.items():
            assert func_obj.entrypoint is not None

    def test_resilient_tavily_has_functions(self):
        tools = ResilientTavilyTools()
        assert len(tools.functions) > 0
        for func_name, func_obj in tools.functions.items():
            assert func_obj.entrypoint is not None

    def test_finance_factory_returns_resilient(self):
        from app.tools.finance import get_finance_tools

        tools = get_finance_tools()
        assert isinstance(tools, ResilientYFinanceTools)

    def test_search_factory_returns_resilient(self):
        from app.tools.search import get_search_tools

        tools = get_search_tools()
        assert isinstance(tools, ResilientTavilyTools)

    def test_research_agent_has_retry_config(self):
        from app.agents.research import create_research_agent

        agent = create_research_agent()
        assert agent.retries == 2
        assert agent.exponential_backoff is True
        assert agent.delay_between_retries == 2


# ---------------------------------------------------------------------------
# Ticker validation tool
# ---------------------------------------------------------------------------
class TestTickerValidationTool:
    def test_tool_instantiates(self):
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        assert "validate_tickers" in tool.functions

    def test_empty_input(self):
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers(""))
        assert result["valid_tickers"] == []
        assert "error" in result

    def test_whitespace_only_input(self):
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers("  ,  , "))
        assert result["valid_tickers"] == []
        assert "error" in result

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_valid_ticker(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {
            "shortName": "Apple Inc.",
            "exchange": "NMS",
        }
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers("AAPL"))
        assert "AAPL" in result["valid_tickers"]
        assert result["invalid_tickers"] == []
        assert "warning" not in result

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_invalid_ticker(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {}
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers("XYZFAKE"))
        assert result["valid_tickers"] == []
        assert "XYZFAKE" in result["invalid_tickers"]
        assert "warning" in result

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_mixed_valid_invalid(self, mock_ticker_cls):
        def side_effect(symbol):
            mock = MagicMock()
            if symbol == "AAPL":
                mock.info = {"shortName": "Apple Inc.", "exchange": "NMS"}
            else:
                mock.info = {}
            return mock

        mock_ticker_cls.side_effect = side_effect
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers("AAPL,FAKEXYZ"))
        assert "AAPL" in result["valid_tickers"]
        assert "FAKEXYZ" in result["invalid_tickers"]
        assert "warning" in result

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_exception_handling(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("Network error")
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers("AAPL"))
        assert "AAPL" in result["invalid_tickers"]
        assert result["valid_tickers"] == []

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_normalizes_to_uppercase(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {
            "shortName": "Apple Inc.",
            "exchange": "NMS",
        }
        from app.tools.ticker_validation import TickerValidationTool

        tool = TickerValidationTool()
        result = json.loads(tool.validate_tickers("aapl"))
        assert "AAPL" in result["valid_tickers"]
