"""Resilient wrappers for YFinance and Tavily tool classes.

Adds retry with exponential backoff and a circuit breaker pattern
around each tool method to handle transient API failures gracefully.
Tool call metrics are recorded via the observability module.
"""

import logging
import time
from functools import wraps
from typing import Any, Callable

from agno.tools.tavily import TavilyTools
from agno.tools.yfinance import YFinanceTools

from app.observability import categorize_error, record_timeline_event, record_tool_call

logger = logging.getLogger("investment_team.tools")


def _is_error_response(result: str) -> bool:
    """Detect error strings returned by YFinance/Tavily tools.

    These tools catch exceptions internally and return descriptive
    error strings rather than raising.  We treat these as failures
    for retry purposes.
    """
    if not isinstance(result, str):
        return False
    lower = result.lower()
    return any(
        marker in lower
        for marker in [
            "error fetching",
            "error getting",
            "could not fetch",
            "no results found",
            "error:",
        ]
    )


class CircuitBreaker:
    """Simple circuit breaker that trips after consecutive failures.

    States:
      - CLOSED  (normal): requests flow through
      - OPEN    (tripped): requests are rejected immediately
      - HALF-OPEN (probe): after reset_timeout, one request is allowed through
    """

    def __init__(
        self, failure_threshold: int = 3, reset_timeout: float = 60.0
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.consecutive_failures = 0
        self.last_failure_time: float | None = None
        self.is_open = False

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self.is_open = True

    def allow_request(self) -> bool:
        if not self.is_open:
            return True
        # Half-open: allow one probe after reset_timeout
        if (
            self.last_failure_time is not None
            and (time.time() - self.last_failure_time) >= self.reset_timeout
        ):
            return True
        return False


def _resilient_method(
    method: Callable,
    breaker: CircuitBreaker,
    tool_name: str,
    max_retries: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
) -> Callable:
    """Wrap a tool method with retry + circuit breaker logic."""

    @wraps(method)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        # Circuit breaker check
        if not breaker.allow_request():
            msg = (
                f"{tool_name} is unavailable "
                f"(tripped after {breaker.failure_threshold} consecutive failures)."
            )
            logger.warning(
                msg,
                extra={"event": "circuit_breaker_open", "tool": tool_name},
            )
            record_timeline_event(
                "circuit_breaker_open", tool=tool_name, detail=msg,
            )
            record_tool_call(
                tool_name, duration_s=0.0, success=False, attempts=0,
                error="circuit_breaker_open",
            )
            return (
                f"Service temporarily unavailable for {tool_name}. "
                f"The circuit breaker has tripped after "
                f"{breaker.failure_threshold} consecutive failures. "
                f"Please try again later."
            )

        # Retry loop with exponential backoff
        start = time.perf_counter()
        last_result: str | None = None
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                result = method(*args, **kwargs)
            except Exception as exc:
                error_type = categorize_error(str(exc))
                logger.warning(
                    f"{tool_name} attempt {attempt}/{max_retries} "
                    f"raised {type(exc).__name__}: {exc}",
                    extra={
                        "event": "retry",
                        "tool": tool_name,
                        "attempts": attempt,
                        "error_type": error_type,
                    },
                )
                record_timeline_event(
                    "retry",
                    tool=tool_name,
                    detail=f"attempt {attempt}/{max_retries}: {type(exc).__name__}: {str(exc)[:100]}",
                )
                last_result = f"Error: {exc}"
                last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
                if attempt < max_retries:
                    delay = min(min_wait * (2 ** (attempt - 1)), max_wait)
                    time.sleep(delay)
                continue

            if _is_error_response(result):
                error_type = categorize_error(result)
                logger.warning(
                    f"{tool_name} attempt {attempt}/{max_retries} "
                    f"returned error: {result[:120]}",
                    extra={
                        "event": "retry",
                        "tool": tool_name,
                        "attempts": attempt,
                        "error_type": error_type,
                    },
                )
                record_timeline_event(
                    "retry",
                    tool=tool_name,
                    detail=f"attempt {attempt}/{max_retries}: {result[:100]}",
                )
                last_result = result
                last_error = result[:120]
                if attempt < max_retries:
                    delay = min(min_wait * (2 ** (attempt - 1)), max_wait)
                    time.sleep(delay)
                continue

            # Success
            elapsed = time.perf_counter() - start
            breaker.record_success()
            record_tool_call(
                tool_name, duration_s=elapsed, success=True, attempts=attempt,
            )
            return result

        # All retries exhausted
        elapsed = time.perf_counter() - start
        breaker.record_failure()
        logger.error(
            f"{tool_name} failure count: "
            f"{breaker.consecutive_failures}/{breaker.failure_threshold}",
            extra={
                "event": "circuit_breaker_failure",
                "tool": tool_name,
            },
        )
        record_tool_call(
            tool_name, duration_s=elapsed, success=False,
            attempts=max_retries, error=last_error,
        )
        return last_result or f"Error: {tool_name} failed after {max_retries} attempts"

    return wrapper


class ResilientYFinanceTools(YFinanceTools):
    """YFinanceTools with per-method retry and a shared circuit breaker."""

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._breaker = CircuitBreaker(failure_threshold, reset_timeout)

        # Wrap each registered function's entrypoint
        for func_name in list(self.functions.keys()):
            original = self.functions[func_name].entrypoint
            self.functions[func_name].entrypoint = _resilient_method(
                original,
                self._breaker,
                f"YFinance.{func_name}",
                max_retries=max_retries,
            )


class ResilientTavilyTools(TavilyTools):
    """TavilyTools with per-method retry and a shared circuit breaker."""

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._breaker = CircuitBreaker(failure_threshold, reset_timeout)

        for func_name in list(self.functions.keys()):
            original = self.functions[func_name].entrypoint
            self.functions[func_name].entrypoint = _resilient_method(
                original,
                self._breaker,
                f"Tavily.{func_name}",
                max_retries=max_retries,
            )
