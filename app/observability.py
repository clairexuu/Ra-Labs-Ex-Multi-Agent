"""Real-time observability hooks for the Investment Team.

Provides structured logging, trace ID propagation, tool-level metrics,
workflow event timelines, and error categorization.

Hook wiring (in investment_team.py):
  - Team   pre_hooks  → on_workflow_started
  - Agent  pre_hooks  → on_agent_started
  - Agent  post_hooks → on_agent_completed
  - Team   post_hooks → log_team_metrics
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

# ── Structured logging ────────────────────────────────────────────

logger = logging.getLogger("investment_team")

# Context variables for per-workflow state
_trace_id: ContextVar[str] = ContextVar("trace_id", default="no-trace")
_tool_collector: ContextVar["ToolMetricsCollector | None"] = ContextVar(
    "tool_collector", default=None
)
_event_timeline: ContextVar["EventTimeline | None"] = ContextVar(
    "event_timeline", default=None
)


class TraceIdFilter(logging.Filter):
    """Inject the current trace_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id.get("no-trace")  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines for the events log file."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", "no-trace"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra structured fields if present
        for key in ("event", "agent", "tool", "duration_s", "tokens",
                     "error_type", "attempts", "success"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry)


class StderrFormatter(logging.Formatter):
    """Human-readable format for stderr, similar to the original output."""

    def format(self, record: logging.LogRecord) -> str:
        trace = getattr(record, "trace_id", "no-trace")
        short_trace = trace[:8] if trace != "no-trace" else ""
        prefix = f"[{short_trace}] " if short_trace else ""
        return f"{prefix}{record.getMessage()}"


def setup_logging() -> None:
    """Configure logging with stderr and JSON file handlers.

    Safe to call multiple times — skips if handlers are already attached.
    """
    if logger.handlers:
        return

    logger.setLevel(logging.DEBUG)
    logger.addFilter(TraceIdFilter())

    # Human-readable stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(StderrFormatter())
    logger.addHandler(stderr_handler)

    # Structured JSON file handler
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOGS_DIR / "events.jsonl")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False


# ── Trace ID helpers ──────────────────────────────────────────────


def get_trace_id() -> str:
    """Return the current workflow trace ID."""
    return _trace_id.get("no-trace")


# ── Tool-level metrics ────────────────────────────────────────────


@dataclass
class ToolCallRecord:
    """A single tool invocation record."""

    tool_name: str
    timestamp: str
    duration_s: float
    success: bool
    attempts: int
    error: str | None = None


class ToolMetricsCollector:
    """Collects tool call records for the current workflow run."""

    def __init__(self) -> None:
        self.records: list[ToolCallRecord] = []

    def record(self, rec: ToolCallRecord) -> None:
        self.records.append(rec)

    def summary(self) -> list[dict[str, Any]]:
        """Return per-tool aggregated stats."""
        by_tool: dict[str, list[ToolCallRecord]] = {}
        for r in self.records:
            by_tool.setdefault(r.tool_name, []).append(r)

        result = []
        for tool_name, calls in by_tool.items():
            successes = [c for c in calls if c.success]
            errors = [c for c in calls if not c.success]
            avg_dur = (
                sum(c.duration_s for c in calls) / len(calls)
                if calls
                else 0.0
            )
            result.append({
                "tool": tool_name,
                "calls": len(calls),
                "successes": len(successes),
                "errors": len(errors),
                "avg_duration_s": round(avg_dur, 3),
                "total_attempts": sum(c.attempts for c in calls),
            })
        return result

    def to_records(self) -> list[dict[str, Any]]:
        """Return all individual records as dicts."""
        return [asdict(r) for r in self.records]


def get_tool_collector() -> "ToolMetricsCollector | None":
    """Return the current workflow's tool metrics collector."""
    return _tool_collector.get(None)


def record_tool_call(
    tool_name: str,
    duration_s: float,
    success: bool,
    attempts: int,
    error: str | None = None,
) -> None:
    """Record a tool call from anywhere (called by resilient wrappers)."""
    collector = _tool_collector.get(None)
    if collector is None:
        return
    rec = ToolCallRecord(
        tool_name=tool_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_s=round(duration_s, 3),
        success=success,
        attempts=attempts,
        error=error,
    )
    collector.record(rec)

    # Also append to the event timeline
    timeline = _event_timeline.get(None)
    if timeline is not None:
        event_type = "tool_call" if success else "tool_error"
        detail = None if success else error
        timeline.append(WorkflowEvent(
            timestamp=rec.timestamp,
            event=event_type,
            agent=None,
            tool=tool_name,
            duration_s=rec.duration_s,
            detail=detail,
        ))


# ── Workflow event timeline ───────────────────────────────────────


@dataclass
class WorkflowEvent:
    """A single timestamped event in the workflow."""

    timestamp: str
    event: str  # agent_started, agent_completed, tool_call, tool_error, retry, error, workflow_started
    agent: str | None = None
    tool: str | None = None
    duration_s: float | None = None
    detail: str | None = None


class EventTimeline:
    """Accumulates timestamped events for one workflow run."""

    def __init__(self) -> None:
        self.events: list[WorkflowEvent] = []

    def append(self, event: WorkflowEvent) -> None:
        self.events.append(event)

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.events]


def get_event_timeline() -> "EventTimeline | None":
    """Return the current workflow's event timeline."""
    return _event_timeline.get(None)


def record_timeline_event(
    event: str,
    agent: str | None = None,
    tool: str | None = None,
    duration_s: float | None = None,
    detail: str | None = None,
) -> None:
    """Append an event to the current workflow timeline."""
    timeline = _event_timeline.get(None)
    if timeline is None:
        return
    timeline.append(WorkflowEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event=event,
        agent=agent,
        tool=tool,
        duration_s=duration_s,
        detail=detail,
    ))


# ── Error categorization ─────────────────────────────────────────


def categorize_error(error_text: str) -> str:
    """Categorize an error string into a known type."""
    lower = error_text.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "rate limit" in lower or "429" in lower or "quota" in lower:
        return "rate_limit"
    if "circuit breaker" in lower or "circuit-breaker" in lower:
        return "circuit_breaker"
    if "validation" in lower or "validationerror" in lower:
        return "validation_error"
    if any(m in lower for m in ["error fetching", "error getting", "could not fetch", "error:"]):
        return "api_error"
    return "unknown"


# ── Metric helpers ────────────────────────────────────────────────


def _safe_duration(metrics) -> float | None:
    """Extract duration from a RunMetrics.

    Post-hooks run *before* ``_cleanup_and_store`` calls ``stop_timer()``,
    so ``metrics.duration`` is still None at hook time.  Fall back to the
    live ``timer.elapsed`` property which computes the elapsed time from
    the still-running timer.
    """
    if metrics is None:
        return None
    if metrics.duration is not None:
        return metrics.duration
    if metrics.timer is not None:
        return metrics.timer.elapsed
    return None


def _resolve_status(status) -> str:
    """Map a RunStatus to a display string.

    Post-hooks fire while status is still RUNNING.  If the run hasn't
    been marked as error/cancelled/paused, it's effectively completed.
    """
    if status == RunStatus.running:
        status = RunStatus.completed
    return status.value if hasattr(status, "value") else str(status)


# ── Real-time hooks (fired as things happen) ──────────────────────


def on_workflow_started(team) -> None:
    """Team pre-hook: initialize trace ID, collectors, and announce start."""
    try:
        # Initialize per-workflow state
        tid = uuid.uuid4().hex
        _trace_id.set(tid)
        _tool_collector.set(ToolMetricsCollector())
        _event_timeline.set(EventTimeline())

        logger.info(
            "",
            extra={"event": "workflow_started", "agent": team.name},
        )
        logger.info("=" * 60)
        logger.info(f"WORKFLOW STARTED  ({team.name})  trace={tid[:8]}")
        logger.info("=" * 60)

        record_timeline_event("workflow_started", agent=team.name)
    except Exception as e:
        logger.error(f"on_workflow_started error: {e}")


def on_agent_started(agent) -> None:
    """Agent pre-hook: announce an agent has begun work."""
    try:
        name = getattr(agent, "name", "unknown")
        logger.info(
            f"  [{name}]  started",
            extra={"event": "agent_started", "agent": name},
        )
        record_timeline_event("agent_started", agent=name)
    except Exception as e:
        logger.error(f"on_agent_started error: {e}")


def on_agent_completed(run_output, agent) -> None:
    """Agent post-hook: announce completion or failure with metrics."""
    try:
        name = getattr(agent, "name", None) or getattr(run_output, "agent_name", "unknown")
        m = run_output.metrics
        dur = _safe_duration(m)
        dur_str = f"{dur:.2f}s" if dur is not None else "N/A"
        tok = m.total_tokens if m else "N/A"
        status = run_output.status

        if status in (RunStatus.error, RunStatus.cancelled):
            status_str = status.value
            error_msg = ""
            error_type = "unknown"
            if run_output.content:
                text = str(run_output.content)
                error_msg = f"  {text[:120]}"
                error_type = categorize_error(text)
            logger.error(
                f"  [{name}]  {status_str}{error_msg}",
                extra={
                    "event": "agent_error",
                    "agent": name,
                    "error_type": error_type,
                    "duration_s": dur,
                },
            )
            record_timeline_event(
                "error",
                agent=name,
                duration_s=dur,
                detail=f"{status_str}: {error_msg.strip()}" if error_msg else status_str,
            )
        else:
            logger.info(
                f"  [{name}]  completed   duration={dur_str}   tokens={tok}",
                extra={
                    "event": "agent_completed",
                    "agent": name,
                    "duration_s": dur,
                    "tokens": tok,
                },
            )
            record_timeline_event("agent_completed", agent=name, duration_s=dur)
    except Exception as e:
        logger.error(f"on_agent_completed error: {e}")


# ── Final summary (team post-hook) ────────────────────────────────


def _build_agent_entry(member_response) -> Dict[str, Any]:
    """Build a per-agent metrics dict from a member RunOutput/TeamRunOutput."""
    name = getattr(member_response, "agent_name", None) or getattr(member_response, "team_name", None) or "unknown"
    m = member_response.metrics
    status = _resolve_status(member_response.status)
    return {
        "name": name,
        "duration_s": _safe_duration(m),
        "total_tokens": m.total_tokens if m else None,
        "input_tokens": m.input_tokens if m else None,
        "output_tokens": m.output_tokens if m else None,
        "status": status,
    }


def _build_log_entry(run_output: TeamRunOutput) -> Dict[str, Any]:
    """Build the structured log entry from a TeamRunOutput."""
    m = run_output.metrics
    status_str = _resolve_status(run_output.status)

    agents: List[Dict[str, Any]] = []
    for member in run_output.member_responses:
        # Flatten nested sub-teams (e.g. broadcast Analysis Team) so
        # individual agents appear in the report instead of one opaque entry.
        if isinstance(member, TeamRunOutput) and member.member_responses:
            for sub_member in member.member_responses:
                agents.append(_build_agent_entry(sub_member))
        else:
            agents.append(_build_agent_entry(member))

    # Collect tool metrics and timeline
    collector = _tool_collector.get(None)
    timeline = _event_timeline.get(None)

    # Agno's TeamRunOutput.metrics only tracks the coordinator's own tokens.
    # To get the true total we must add all member-agent tokens on top.
    coordinator_input = m.input_tokens if m else 0
    coordinator_output = m.output_tokens if m else 0
    coordinator_total = m.total_tokens if m else 0
    agent_input = sum(a.get("input_tokens") or 0 for a in agents)
    agent_output = sum(a.get("output_tokens") or 0 for a in agents)
    agent_total = sum(a.get("total_tokens") or 0 for a in agents)

    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": _trace_id.get("no-trace"),
        "run_id": run_output.run_id,
        "session_id": run_output.session_id,
        "status": status_str,
        "total_duration_s": _safe_duration(m),
        "total_tokens": coordinator_total + agent_total,
        "input_tokens": coordinator_input + agent_input,
        "output_tokens": coordinator_output + agent_output,
        "coordinator_tokens": coordinator_total,
        "agents": agents,
        "tool_calls": collector.to_records() if collector else [],
        "tool_summary": collector.summary() if collector else [],
        "events": timeline.to_list() if timeline else [],
    }
    return entry


def _format_table(entry: Dict[str, Any]) -> str:
    """Format the log entry as a human-readable table."""
    trace = entry.get("trace_id", "no-trace")
    lines = [
        "",
        "=" * 60,
        "OBSERVABILITY REPORT",
        "=" * 60,
        f"  Trace ID:   {trace}",
        f"  Run ID:     {entry['run_id']}",
        f"  Status:     {entry['status']}",
        f"  Duration:   {entry['total_duration_s']:.2f}s" if entry["total_duration_s"] else "  Duration:   N/A",
        f"  Tokens:     {entry['total_tokens']} (in: {entry['input_tokens']}, out: {entry['output_tokens']})",
        f"  Coordinator:{entry.get('coordinator_tokens', 'N/A')}",
        "-" * 60,
        "  Per-Agent Breakdown:",
    ]
    for agent in entry["agents"]:
        dur = f"{agent['duration_s']:.2f}s" if agent["duration_s"] is not None else "N/A"
        tok = agent["total_tokens"] if agent["total_tokens"] is not None else "N/A"
        st = agent.get("status", "N/A")
        lines.append(f"    {agent['name']:<20} duration={dur:<10} tokens={tok:<8} status={st}")

    # Tool call summary
    tool_summary = entry.get("tool_summary", [])
    if tool_summary:
        lines.append("-" * 60)
        lines.append("  Tool Calls:")
        for ts in tool_summary:
            err_str = f"   errors={ts['errors']}" if ts["errors"] > 0 else ""
            lines.append(
                f"    {ts['tool']:<35} calls={ts['calls']:<4} "
                f"success={ts['successes']:<4} avg={ts['avg_duration_s']:.2f}s{err_str}"
            )

    # Timeline
    events = entry.get("events", [])
    if events:
        lines.append("-" * 60)
        lines.append("  Timeline:")
        for ev in events:
            ts = ev["timestamp"]
            # Show only time portion for readability
            time_part = ts.split("T")[1][:12] if "T" in ts else ts
            parts = [f"    {time_part}  {ev['event']:<20}"]
            if ev.get("agent"):
                parts.append(f"agent={ev['agent']}")
            if ev.get("tool"):
                parts.append(f"tool={ev['tool']}")
            if ev.get("duration_s") is not None:
                parts.append(f"duration={ev['duration_s']:.2f}s")
            if ev.get("detail"):
                parts.append(f"detail={ev['detail'][:80]}")
            lines.append("  ".join(parts))

    lines.append("=" * 60)
    return "\n".join(lines)


def _write_jsonl(entry: Dict[str, Any]) -> None:
    """Append a JSON line to logs/metrics.jsonl."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "metrics.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def log_team_metrics(run_output: TeamRunOutput) -> None:
    """Team post-hook: print final summary and write structured log."""
    try:
        entry = _build_log_entry(run_output)
        logger.info(_format_table(entry))
        _write_jsonl(entry)
    except Exception as e:
        logger.error(f"log_team_metrics error: {e}")
