"""Tests for the observability hooks."""

import json
from types import SimpleNamespace

from agno.models.metrics import RunMetrics
from agno.run.base import RunStatus
from agno.run.agent import RunOutput
from agno.run.team import TeamRunOutput

from app.observability import (
    _build_log_entry,
    _format_table,
    _write_jsonl,
    log_team_metrics,
    on_agent_completed,
    on_agent_started,
    on_workflow_started,
)


def _make_agent_response(
    name: str, duration: float, total_tokens: int, status: RunStatus = RunStatus.completed,
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
    """Create a TeamRunOutput with realistic member responses."""
    members = [
        _make_agent_response("Research Agent", 4.12, 1500),
        _make_agent_response("Analyst Agent", 3.05, 1200),
        _make_agent_response("Critic Agent", 2.80, 900),
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


# ── Real-time hook tests ────────────────────────────────────────────


class TestOnWorkflowStarted:
    def test_prints_banner(self, capsys):
        team = SimpleNamespace(name="Investment Team")
        on_workflow_started(team=team)
        captured = capsys.readouterr().err
        assert "WORKFLOW STARTED" in captured
        assert "Investment Team" in captured


class TestOnAgentStarted:
    def test_prints_agent_name(self, capsys):
        agent = SimpleNamespace(name="Research Agent")
        on_agent_started(agent=agent)
        captured = capsys.readouterr().err
        assert "Research Agent" in captured
        assert "started" in captured


class TestOnAgentCompleted:
    def test_prints_completed_with_metrics(self, capsys):
        agent = SimpleNamespace(name="Analyst Agent")
        run_output = _make_agent_response("Analyst Agent", 3.05, 1200)
        on_agent_completed(run_output=run_output, agent=agent)
        captured = capsys.readouterr().err
        assert "Analyst Agent" in captured
        assert "completed" in captured
        assert "3.05s" in captured
        assert "1200" in captured

    def test_prints_error_on_failure(self, capsys):
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
        captured = capsys.readouterr().err
        assert "Critic Agent" in captured
        assert "ERROR" in captured
        assert "API rate limit exceeded" in captured

    def test_prints_cancelled(self, capsys):
        agent = SimpleNamespace(name="Decision Agent")
        run_output = RunOutput(
            agent_name="Decision Agent",
            agent_id="decision-id",
            run_id="decision-run",
            status=RunStatus.cancelled,
            metrics=RunMetrics(),
        )
        on_agent_completed(run_output=run_output, agent=agent)
        captured = capsys.readouterr().err
        assert "CANCELLED" in captured


# ── Summary table tests ─────────────────────────────────────────────


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
            metrics=RunMetrics(duration=7.0, total_tokens=2700, input_tokens=1500, output_tokens=1200),
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
