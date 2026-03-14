"""Tests for tool-level retry, circuit breaker, and company validation."""

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.observability import (
    _event_timeline,
    _tool_collector,
    _trace_id,
    on_workflow_started,
    setup_logging,
)
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
# Tool metric recording via observability
# ---------------------------------------------------------------------------
class TestResilientMethodMetrics:
    """Verify _resilient_method records tool calls and timeline events."""

    @pytest.fixture(autouse=True)
    def _init_observability(self):
        setup_logging()
        token_trace = _trace_id.set("no-trace")
        token_collector = _tool_collector.set(None)
        token_timeline = _event_timeline.set(None)
        # Initialize workflow context so collectors exist
        on_workflow_started(team=SimpleNamespace(name="Test"))
        yield
        _trace_id.reset(token_trace)
        _tool_collector.reset(token_collector)
        _event_timeline.reset(token_timeline)

    def test_success_records_tool_call(self):
        method = MagicMock(return_value="100.00")
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        wrapped("AAPL")

        collector = _tool_collector.get(None)
        assert len(collector.records) == 1
        assert collector.records[0].tool_name == "test_tool"
        assert collector.records[0].success is True
        assert collector.records[0].attempts == 1
        assert collector.records[0].error is None

    def test_retry_success_records_attempt_count(self):
        method = MagicMock(
            side_effect=["Error fetching data", "100.00"]
        )
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        wrapped("AAPL")

        collector = _tool_collector.get(None)
        assert len(collector.records) == 1
        assert collector.records[0].success is True
        assert collector.records[0].attempts == 2

    def test_failure_records_error(self):
        method = MagicMock(return_value="Error fetching data")
        breaker = CircuitBreaker(failure_threshold=5)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=2, min_wait=0.01
        )
        wrapped("AAPL")

        collector = _tool_collector.get(None)
        assert len(collector.records) == 1
        assert collector.records[0].success is False
        assert collector.records[0].attempts == 2
        assert collector.records[0].error is not None

    def test_circuit_breaker_block_records_metric(self):
        method = MagicMock(return_value="should not be called")
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        wrapped("AAPL")

        collector = _tool_collector.get(None)
        assert len(collector.records) == 1
        assert collector.records[0].success is False
        assert collector.records[0].error == "circuit_breaker_open"

    def test_retry_events_in_timeline(self):
        method = MagicMock(
            side_effect=[ConnectionError("network down"), "100.00"]
        )
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        wrapped("AAPL")

        timeline = _event_timeline.get(None)
        retry_events = [e for e in timeline.events if e.event == "retry"]
        assert len(retry_events) == 1
        assert "network down" in retry_events[0].detail

    def test_duration_is_recorded(self):
        method = MagicMock(return_value="100.00")
        breaker = CircuitBreaker(failure_threshold=3)
        wrapped = _resilient_method(
            method, breaker, "test_tool", max_retries=3, min_wait=0.01
        )
        wrapped("AAPL")

        collector = _tool_collector.get(None)
        assert collector.records[0].duration_s >= 0.0
        assert isinstance(collector.records[0].duration_s, float)


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
# Company validation tool
# ---------------------------------------------------------------------------
class TestCompanyValidationTool:
    def test_tool_instantiates(self):
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        assert "validate_companies" in tool.functions

    def test_empty_input(self):
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies(""))
        assert result["public_companies"] == []
        assert result["private_companies"] == []
        assert "error" in result

    def test_whitespace_only_input(self):
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("  ,  , "))
        assert result["public_companies"] == []
        assert result["private_companies"] == []
        assert "error" in result

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_public_ticker(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {
            "shortName": "Apple Inc.",
            "exchange": "NMS",
        }
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("AAPL"))
        assert len(result["public_companies"]) == 1
        assert result["public_companies"][0]["ticker"] == "AAPL"
        assert result["public_companies"][0]["company_type"] == "PUBLIC"
        assert result["private_companies"] == []

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_private_company(self, mock_ticker_cls, mock_search_cls):
        mock_ticker_cls.return_value.info = {}
        mock_search_cls.return_value.quotes = []
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("Anthropic"))
        assert result["public_companies"] == []
        assert len(result["private_companies"]) == 1
        assert result["private_companies"][0]["company_type"] == "PRIVATE"
        assert result["private_companies"][0]["company_name"] == "Anthropic"
        assert "note" in result

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_mixed_public_private(self, mock_ticker_cls, mock_search_cls):
        def side_effect(symbol):
            mock = MagicMock()
            if symbol == "AAPL":
                mock.info = {"shortName": "Apple Inc.", "exchange": "NMS"}
            else:
                mock.info = {}
            return mock

        mock_ticker_cls.side_effect = side_effect
        mock_search_cls.return_value.quotes = []
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("AAPL,Anthropic"))
        assert len(result["public_companies"]) == 1
        assert len(result["private_companies"]) == 1
        assert result["summary"]["public_count"] == 1
        assert result["summary"]["private_count"] == 1
        assert "note" in result

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_exception_classifies_as_private(self, mock_ticker_cls, mock_search_cls):
        mock_ticker_cls.side_effect = Exception("Network error")
        mock_search_cls.return_value.quotes = []
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("Anthropic"))
        assert len(result["private_companies"]) == 1
        assert result["public_companies"] == []

    @patch("app.tools.ticker_validation.yf.Ticker")
    @patch("app.tools.ticker_validation.yf.Search")
    def test_company_name_resolves_to_ticker(self, mock_search_cls, mock_ticker_cls):
        """Company name like 'NVIDIA' resolves to ticker 'NVDA' via search."""

        def ticker_side_effect(symbol):
            mock = MagicMock()
            if symbol == "NVDA":
                mock.info = {
                    "shortName": "NVIDIA Corporation",
                    "exchange": "NMS",
                }
            else:
                mock.info = {}
            return mock

        mock_ticker_cls.side_effect = ticker_side_effect
        mock_search_cls.return_value.quotes = [
            {"symbol": "NVDA", "quoteType": "EQUITY", "shortname": "NVIDIA Corporation"}
        ]
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("NVIDIA"))
        assert len(result["public_companies"]) == 1
        assert result["public_companies"][0]["ticker"] == "NVDA"
        assert result["public_companies"][0]["company_type"] == "PUBLIC"
        assert result["private_companies"] == []

    @patch("app.tools.ticker_validation.yf.Ticker")
    @patch("app.tools.ticker_validation.yf.Search")
    def test_typo_resolves_via_fuzzy_search(self, mock_search_cls, mock_ticker_cls):
        """Typo like 'Appel' resolves to 'AAPL' via fuzzy search."""

        def ticker_side_effect(symbol):
            mock = MagicMock()
            if symbol == "AAPL":
                mock.info = {"shortName": "Apple Inc.", "exchange": "NMS"}
            else:
                mock.info = {}
            return mock

        mock_ticker_cls.side_effect = ticker_side_effect
        mock_search_cls.return_value.quotes = [
            {"symbol": "AAPL", "quoteType": "EQUITY", "shortname": "Apple Inc."}
        ]
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("Appel"))
        assert len(result["public_companies"]) == 1
        assert result["public_companies"][0]["ticker"] == "AAPL"
        assert result["private_companies"] == []

    @patch("app.tools.ticker_validation.yf.Ticker")
    @patch("app.tools.ticker_validation.yf.Search")
    def test_search_skips_non_equity_quotes(self, mock_search_cls, mock_ticker_cls):
        """Search results that aren't EQUITY (e.g., ETFs) are skipped."""
        mock_ticker_cls.return_value.info = {}
        mock_search_cls.return_value.quotes = [
            {"symbol": "SPY", "quoteType": "ETF", "shortname": "SPDR S&P 500"}
        ]
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("S&P 500"))
        assert result["public_companies"] == []
        assert len(result["private_companies"]) == 1

    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_normalizes_to_uppercase(self, mock_ticker_cls):
        mock_ticker_cls.return_value.info = {
            "shortName": "Apple Inc.",
            "exchange": "NMS",
        }
        from app.tools.ticker_validation import CompanyValidationTool

        tool = CompanyValidationTool()
        result = json.loads(tool.validate_companies("aapl"))
        assert result["public_companies"][0]["ticker"] == "AAPL"
