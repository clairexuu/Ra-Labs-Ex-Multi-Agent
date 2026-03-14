"""Tests for the observability hooks, structured logging, trace IDs,
tool metrics, event timeline, and error categorization."""

import io
import json
import logging
from types import SimpleNamespace

import pytest
from agno.models.metrics import RunMetrics
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput

from app.observability import (
    EventTimeline,
    ToolCallRecord,
    ToolMetricsCollector,
    TraceIdFilter,
    WorkflowEvent,
    _build_log_entry,
    _event_timeline,
    _format_table,
    _tool_collector,
    _trace_id,
    _write_jsonl,
    categorize_error,
    get_trace_id,
    log_team_metrics,
    on_agent_completed,
    on_agent_started,
    on_workflow_started,
    record_timeline_event,
    record_tool_call,
    setup_logging,
)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_logging_and_context():
    """Ensure logging is configured and context vars are reset for each test."""
    setup_logging()
    # Reset context vars to clean state
    token_trace = _trace_id.set("no-trace")
    token_collector = _tool_collector.set(None)
    token_timeline = _event_timeline.set(None)
    yield
    _trace_id.reset(token_trace)
    _tool_collector.reset(token_collector)
    _event_timeline.reset(token_timeline)


@pytest.fixture
def captured_logs():
    """Capture log output from the investment_team logger via a StringIO handler."""
    logger = logging.getLogger("investment_team")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    yield stream
    logger.removeHandler(handler)


def _make_agent_response(
    name: str,
    duration: float,
    total_tokens: int,
    status: RunStatus = RunStatus.completed,
) -> RunOutput:
    """Create a minimal RunOutput with metrics for testing."""
    metrics = RunMetrics(
        input_tokens=total_tokens // 2,
        output_tokens=total_tokens - total_tokens // 2,
        total_tokens=total_tokens,
        duration=duration,
    )
    return RunOutput(
        agent_name=name,
        agent_id=f"{name}-id",
        run_id=f"{name}-run",
        metrics=metrics,
        status=status,
    )


def _make_team_output() -> TeamRunOutput:
    """Create a TeamRunOutput with realistic member responses.

    Mirrors the nested structure: the Analysis Team (broadcast sub-team)
    wraps Analyst + Critic responses inside a TeamRunOutput.
    """
    analyst_response = _make_agent_response("Analyst Agent", 3.05, 1200)
    critic_response = _make_agent_response("Critic Agent", 2.80, 900)

    analysis_team_response = TeamRunOutput(
        run_id="analysis-team-run",
        team_id="analysis-team-id",
        team_name="Analysis Team",
        status=RunStatus.completed,
        metrics=RunMetrics(
            duration=3.10, total_tokens=2100, input_tokens=1100, output_tokens=1000
        ),
        member_responses=[analyst_response, critic_response],
    )

    members = [
        _make_agent_response("Research Agent", 4.12, 1500),
        analysis_team_response,
        _make_agent_response("Decision Agent", 1.50, 600),
    ]
    team_metrics = RunMetrics(
        input_tokens=3000,
        output_tokens=2000,
        total_tokens=5000,
        duration=12.34,
    )
    return TeamRunOutput(
        run_id="test-run-123",
        session_id="test-session-456",
        team_id="team-1",
        status=RunStatus.completed,
        metrics=team_metrics,
        member_responses=members,
    )


# ── Setup logging tests ───────────────────────────────────────────


class TestSetupLogging:
    def test_configures_handlers(self):
        logger = logging.getLogger("investment_team")
        assert len(logger.handlers) >= 2
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "StreamHandler" in handler_types
        assert "FileHandler" in handler_types

    def test_idempotent(self):
        logger = logging.getLogger("investment_team")
        count_before = len(logger.handlers)
        setup_logging()
        setup_logging()
        assert len(logger.handlers) == count_before

    def test_has_trace_id_filter(self):
        logger = logging.getLogger("investment_team")
        filter_types = [type(f).__name__ for f in logger.filters]
        assert "TraceIdFilter" in filter_types

    def test_propagation_disabled(self):
        logger = logging.getLogger("investment_team")
        assert logger.propagate is False


class TestTraceIdFilter:
    def test_injects_trace_id(self):
        _trace_id.set("abc123")
        f = TraceIdFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        f.filter(record)
        assert record.trace_id == "abc123"  # type: ignore[attr-defined]

    def test_default_trace_id(self):
        f = TraceIdFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        f.filter(record)
        assert record.trace_id == "no-trace"  # type: ignore[attr-defined]


# ── Trace ID tests ────────────────────────────────────────────────


class TestTraceId:
    def test_workflow_started_sets_trace_id(self):
        team = SimpleNamespace(name="Investment Team")
        on_workflow_started(team=team)
        tid = get_trace_id()
        assert tid != "no-trace"
        assert len(tid) == 32  # UUID hex

    def test_trace_id_included_in_log_entry(self):
        team = SimpleNamespace(name="Investment Team")
        on_workflow_started(team=team)
        entry = _build_log_entry(_make_team_output())
        assert entry["trace_id"] != "no-trace"
        assert len(entry["trace_id"]) == 32


# ── Real-time hook tests ──────────────────────────────────────────


class TestOnWorkflowStarted:
    def test_logs_banner(self, captured_logs):
        team = SimpleNamespace(name="Investment Team")
        on_workflow_started(team=team)
        output = captured_logs.getvalue()
        assert "WORKFLOW STARTED" in output
        assert "Investment Team" in output

    def test_initializes_context_vars(self):
        team = SimpleNamespace(name="Investment Team")
        on_workflow_started(team=team)
        assert get_trace_id() != "no-trace"
        assert _tool_collector.get(None) is not None
        assert _event_timeline.get(None) is not None

    def test_records_timeline_event(self):
        team = SimpleNamespace(name="Investment Team")
        on_workflow_started(team=team)
        timeline = _event_timeline.get(None)
        assert timeline is not None
        assert len(timeline.events) == 1
        assert timeline.events[0].event == "workflow_started"


class TestOnAgentStarted:
    def test_logs_agent_name(self, captured_logs):
        agent = SimpleNamespace(name="Research Agent")
        on_agent_started(agent=agent)
        output = captured_logs.getvalue()
        assert "Research Agent" in output
        assert "started" in output

    def test_records_timeline_event(self):
        # Initialize context first
        on_workflow_started(team=SimpleNamespace(name="Test"))
        agent = SimpleNamespace(name="Research Agent")
        on_agent_started(agent=agent)
        timeline = _event_timeline.get(None)
        events = [e for e in timeline.events if e.event == "agent_started"]
        assert len(events) == 1
        assert events[0].agent == "Research Agent"


class TestOnAgentCompleted:
    def test_logs_completed_with_metrics(self, captured_logs):
        agent = SimpleNamespace(name="Analyst Agent")
        run_output = _make_agent_response("Analyst Agent", 3.05, 1200)
        on_agent_completed(run_output=run_output, agent=agent)
        output = captured_logs.getvalue()
        assert "Analyst Agent" in output
        assert "completed" in output
        assert "3.05s" in output

    def test_logs_error_on_failure(self, captured_logs):
        agent = SimpleNamespace(name="Critic Agent")
        run_output = RunOutput(
            agent_name="Critic Agent",
            agent_id="critic-id",
            run_id="critic-run",
            status=RunStatus.error,
            content="API rate limit exceeded",
            metrics=RunMetrics(),
        )
        on_agent_completed(run_output=run_output, agent=agent)
        output = captured_logs.getvalue()
        assert "Critic Agent" in output
        assert "ERROR" in output
        assert "API rate limit exceeded" in output

    def test_logs_cancelled(self, captured_logs):
        agent = SimpleNamespace(name="Decision Agent")
        run_output = RunOutput(
            agent_name="Decision Agent",
            agent_id="decision-id",
            run_id="decision-run",
            status=RunStatus.cancelled,
            metrics=RunMetrics(),
        )
        on_agent_completed(run_output=run_output, agent=agent)
        output = captured_logs.getvalue()
        assert "CANCELLED" in output

    def test_error_categorized_in_timeline(self):
        """Verify error categorization flows through to the timeline event."""
        on_workflow_started(team=SimpleNamespace(name="Test"))
        agent = SimpleNamespace(name="Research Agent")
        run_output = RunOutput(
            agent_name="Research Agent",
            agent_id="research-id",
            run_id="research-run",
            status=RunStatus.error,
            content="Request timed out after 30s",
            metrics=RunMetrics(),
        )
        on_agent_completed(run_output=run_output, agent=agent)
        timeline = _event_timeline.get(None)
        error_events = [e for e in timeline.events if e.event == "error"]
        assert len(error_events) == 1
        assert "timed out" in error_events[0].detail

    def test_records_timeline_event_on_success(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        agent = SimpleNamespace(name="Analyst Agent")
        run_output = _make_agent_response("Analyst Agent", 3.05, 1200)
        on_agent_completed(run_output=run_output, agent=agent)
        timeline = _event_timeline.get(None)
        completed_events = [e for e in timeline.events if e.event == "agent_completed"]
        assert len(completed_events) == 1
        assert completed_events[0].agent == "Analyst Agent"

    def test_records_error_event_in_timeline(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        agent = SimpleNamespace(name="Critic Agent")
        run_output = RunOutput(
            agent_name="Critic Agent",
            agent_id="critic-id",
            run_id="critic-run",
            status=RunStatus.error,
            content="API failure",
            metrics=RunMetrics(),
        )
        on_agent_completed(run_output=run_output, agent=agent)
        timeline = _event_timeline.get(None)
        error_events = [e for e in timeline.events if e.event == "error"]
        assert len(error_events) == 1
        assert error_events[0].agent == "Critic Agent"


# ── Tool metrics collector tests ──────────────────────────────────


class TestToolMetricsCollector:
    def test_record_and_retrieve(self):
        collector = ToolMetricsCollector()
        rec = ToolCallRecord(
            tool_name="YFinance.get_stock_price",
            timestamp="2026-01-01T00:00:00+00:00",
            duration_s=1.5,
            success=True,
            attempts=1,
        )
        collector.record(rec)
        assert len(collector.records) == 1
        assert collector.records[0].tool_name == "YFinance.get_stock_price"

    def test_summary_aggregates(self):
        collector = ToolMetricsCollector()
        for i in range(3):
            collector.record(ToolCallRecord(
                tool_name="YFinance.get_stock_price",
                timestamp=f"2026-01-01T00:00:0{i}+00:00",
                duration_s=1.0 + i,
                success=i < 2,
                attempts=1 if i < 2 else 3,
                error="timeout" if i == 2 else None,
            ))
        collector.record(ToolCallRecord(
            tool_name="Tavily.web_search",
            timestamp="2026-01-01T00:00:03+00:00",
            duration_s=2.0,
            success=True,
            attempts=1,
        ))

        summary = collector.summary()
        assert len(summary) == 2

        yf = next(s for s in summary if s["tool"] == "YFinance.get_stock_price")
        assert yf["calls"] == 3
        assert yf["successes"] == 2
        assert yf["errors"] == 1
        assert yf["total_attempts"] == 5

        tv = next(s for s in summary if s["tool"] == "Tavily.web_search")
        assert tv["calls"] == 1
        assert tv["successes"] == 1
        assert tv["errors"] == 0

    def test_to_records_serializable(self):
        collector = ToolMetricsCollector()
        collector.record(ToolCallRecord(
            tool_name="test",
            timestamp="2026-01-01T00:00:00+00:00",
            duration_s=1.0,
            success=True,
            attempts=1,
        ))
        records = collector.to_records()
        assert len(records) == 1
        # Should be JSON-serializable
        json.dumps(records)

    def test_empty_summary(self):
        collector = ToolMetricsCollector()
        assert collector.summary() == []
        assert collector.to_records() == []


class TestRecordToolCall:
    def test_records_when_collector_exists(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_tool_call("YFinance.get_stock_price", 1.5, True, 1)
        collector = _tool_collector.get(None)
        assert len(collector.records) == 1
        assert collector.records[0].tool_name == "YFinance.get_stock_price"
        assert collector.records[0].success is True

    def test_skips_when_no_collector(self):
        # No workflow started, so no collector
        record_tool_call("YFinance.get_stock_price", 1.5, True, 1)
        # Should not raise

    def test_also_records_timeline_event(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_tool_call("Tavily.web_search", 2.0, True, 1)
        timeline = _event_timeline.get(None)
        tool_events = [e for e in timeline.events if e.event == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0].tool == "Tavily.web_search"

    def test_error_recorded_as_tool_error_event(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_tool_call("YFinance.get_stock_price", 3.0, False, 3, error="timeout")
        timeline = _event_timeline.get(None)
        error_events = [e for e in timeline.events if e.event == "tool_error"]
        assert len(error_events) == 1
        assert error_events[0].detail == "timeout"


# ── Event timeline tests ──────────────────────────────────────────


class TestEventTimeline:
    def test_append_and_to_list(self):
        timeline = EventTimeline()
        event = WorkflowEvent(
            timestamp="2026-01-01T00:00:00+00:00",
            event="agent_started",
            agent="Research Agent",
        )
        timeline.append(event)
        result = timeline.to_list()
        assert len(result) == 1
        assert result[0]["event"] == "agent_started"
        assert result[0]["agent"] == "Research Agent"

    def test_preserves_order(self):
        timeline = EventTimeline()
        for i, name in enumerate(["workflow_started", "agent_started", "agent_completed"]):
            timeline.append(WorkflowEvent(
                timestamp=f"2026-01-01T00:00:0{i}+00:00",
                event=name,
            ))
        events = timeline.to_list()
        assert [e["event"] for e in events] == [
            "workflow_started", "agent_started", "agent_completed"
        ]

    def test_serializable(self):
        timeline = EventTimeline()
        timeline.append(WorkflowEvent(
            timestamp="2026-01-01T00:00:00+00:00",
            event="tool_call",
            tool="YFinance.get_stock_price",
            duration_s=1.5,
        ))
        json.dumps(timeline.to_list())

    def test_empty(self):
        timeline = EventTimeline()
        assert timeline.to_list() == []


class TestRecordTimelineEvent:
    def test_records_when_timeline_exists(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_timeline_event("custom_event", agent="Test Agent", detail="test detail")
        timeline = _event_timeline.get(None)
        custom_events = [e for e in timeline.events if e.event == "custom_event"]
        assert len(custom_events) == 1
        assert custom_events[0].agent == "Test Agent"
        assert custom_events[0].detail == "test detail"

    def test_skips_when_no_timeline(self):
        record_timeline_event("custom_event")
        # Should not raise


# ── Error categorization tests ────────────────────────────────────


class TestCategorizeError:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Request timed out after 30s", "timeout"),
            ("Connection timed out", "timeout"),
            ("Rate limit exceeded", "rate_limit"),
            ("429 Too Many Requests", "rate_limit"),
            ("API quota exceeded", "rate_limit"),
            ("Circuit breaker tripped", "circuit_breaker"),
            ("circuit-breaker is open", "circuit_breaker"),
            ("ValidationError: field required", "validation_error"),
            ("Error fetching current price for XYZ", "api_error"),
            ("Error getting analyst recommendations", "api_error"),
            ("Could not fetch company info", "api_error"),
            ("Error: something broke", "api_error"),
            ("Some unknown issue occurred", "unknown"),
        ],
    )
    def test_categorizes_correctly(self, text, expected):
        assert categorize_error(text) == expected


# ── Summary table tests ───────────────────────────────────────────


class TestBuildLogEntry:
    def test_contains_required_fields(self):
        entry = _build_log_entry(_make_team_output())

        assert entry["run_id"] == "test-run-123"
        assert entry["status"] == "COMPLETED"
        assert entry["total_duration_s"] == 12.34
        assert entry["total_tokens"] == 5000
        assert entry["input_tokens"] == 3000
        assert entry["output_tokens"] == 2000
        assert "timestamp" in entry

    def test_includes_trace_id(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        entry = _build_log_entry(_make_team_output())
        assert "trace_id" in entry
        assert entry["trace_id"] != "no-trace"

    def test_includes_tool_calls_and_summary(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_tool_call("YFinance.get_stock_price", 1.5, True, 1)
        record_tool_call("Tavily.web_search", 2.0, True, 2)

        entry = _build_log_entry(_make_team_output())
        assert len(entry["tool_calls"]) == 2
        assert len(entry["tool_summary"]) == 2
        assert entry["tool_calls"][0]["tool_name"] == "YFinance.get_stock_price"

    def test_includes_events(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        on_agent_started(agent=SimpleNamespace(name="Research Agent"))

        entry = _build_log_entry(_make_team_output())
        assert len(entry["events"]) >= 2
        event_types = [e["event"] for e in entry["events"]]
        assert "workflow_started" in event_types
        assert "agent_started" in event_types

    def test_empty_tool_calls_when_no_collector(self):
        entry = _build_log_entry(_make_team_output())
        assert entry["tool_calls"] == []
        assert entry["tool_summary"] == []
        assert entry["events"] == []

    def test_per_agent_breakdown(self):
        entry = _build_log_entry(_make_team_output())
        agents = entry["agents"]

        assert len(agents) == 4
        assert agents[0]["name"] == "Research Agent"
        assert agents[0]["duration_s"] == 4.12
        assert agents[0]["total_tokens"] == 1500
        assert agents[0]["status"] == "COMPLETED"
        assert agents[3]["name"] == "Decision Agent"

    def test_handles_missing_metrics(self):
        output = TeamRunOutput(
            run_id="no-metrics",
            status=RunStatus.error,
            metrics=None,
            member_responses=[],
        )
        entry = _build_log_entry(output)

        assert entry["status"] == "ERROR"
        assert entry["total_duration_s"] is None
        assert entry["total_tokens"] is None
        assert entry["agents"] == []

    def test_per_agent_status_shown(self):
        members = [
            _make_agent_response("Research Agent", 4.0, 1500, RunStatus.completed),
            _make_agent_response("Analyst Agent", 3.0, 1200, RunStatus.error),
        ]
        output = TeamRunOutput(
            run_id="mixed",
            status=RunStatus.error,
            metrics=RunMetrics(
                duration=7.0, total_tokens=2700, input_tokens=1500, output_tokens=1200
            ),
            member_responses=members,
        )
        entry = _build_log_entry(output)
        assert entry["agents"][0]["status"] == "COMPLETED"
        assert entry["agents"][1]["status"] == "ERROR"


class TestFormatTable:
    def test_table_contains_agent_names_and_status(self):
        entry = _build_log_entry(_make_team_output())
        table = _format_table(entry)

        assert "OBSERVABILITY REPORT" in table
        assert "Research Agent" in table
        assert "Decision Agent" in table
        assert "12.34s" in table
        assert "COMPLETED" in table

    def test_table_contains_trace_id(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        entry = _build_log_entry(_make_team_output())
        table = _format_table(entry)
        assert "Trace ID:" in table
        assert entry["trace_id"] in table

    def test_table_contains_tool_summary(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_tool_call("YFinance.get_stock_price", 1.5, True, 1)
        record_tool_call("YFinance.get_stock_price", 2.0, False, 3, error="timeout")

        entry = _build_log_entry(_make_team_output())
        table = _format_table(entry)
        assert "Tool Calls:" in table
        assert "YFinance.get_stock_price" in table
        assert "errors=1" in table

    def test_table_contains_timeline(self):
        on_workflow_started(team=SimpleNamespace(name="Test"))
        on_agent_started(agent=SimpleNamespace(name="Research Agent"))

        entry = _build_log_entry(_make_team_output())
        table = _format_table(entry)
        assert "Timeline:" in table
        assert "workflow_started" in table
        assert "agent_started" in table

    def test_no_tool_section_when_empty(self):
        entry = _build_log_entry(_make_team_output())
        table = _format_table(entry)
        assert "Tool Calls:" not in table

    def test_no_timeline_section_when_empty(self):
        entry = _build_log_entry(_make_team_output())
        table = _format_table(entry)
        assert "Timeline:" not in table


class TestWriteJsonl:
    def test_writes_valid_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.observability.LOGS_DIR", tmp_path)

        entry = _build_log_entry(_make_team_output())
        _write_jsonl(entry)

        jsonl_file = tmp_path / "metrics.jsonl"
        assert jsonl_file.exists()

        line = jsonl_file.read_text().strip()
        parsed = json.loads(line)
        assert parsed["run_id"] == "test-run-123"
        assert len(parsed["agents"]) == 4

    def test_appends_multiple_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.observability.LOGS_DIR", tmp_path)

        entry = _build_log_entry(_make_team_output())
        _write_jsonl(entry)
        _write_jsonl(entry)

        lines = (tmp_path / "metrics.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    def test_jsonl_includes_new_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.observability.LOGS_DIR", tmp_path)

        on_workflow_started(team=SimpleNamespace(name="Test"))
        record_tool_call("YFinance.test", 1.0, True, 1)
        entry = _build_log_entry(_make_team_output())
        _write_jsonl(entry)

        parsed = json.loads((tmp_path / "metrics.jsonl").read_text().strip())
        assert "trace_id" in parsed
        assert "tool_calls" in parsed
        assert "tool_summary" in parsed
        assert "events" in parsed
        assert len(parsed["tool_calls"]) == 1


class TestLogTeamMetrics:
    def test_end_to_end(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.observability.LOGS_DIR", tmp_path)

        output = _make_team_output()
        log_team_metrics(run_output=output)

        jsonl_file = tmp_path / "metrics.jsonl"
        assert jsonl_file.exists()

        parsed = json.loads(jsonl_file.read_text().strip())
        assert parsed["status"] == "COMPLETED"
        assert parsed["total_duration_s"] == 12.34
        assert len(parsed["agents"]) == 4
        assert parsed["agents"][0]["status"] == "COMPLETED"
