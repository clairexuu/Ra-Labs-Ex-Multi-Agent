"""Real-time observability hooks for the Investment Team.

Prints live status lines as each agent starts/completes, then a final
summary table with the full breakdown.  Also appends a structured JSON
line to logs/metrics.jsonl after each workflow run.

Hook wiring (in investment_team.py):
  - Team   pre_hooks  → on_workflow_started
  - Agent  pre_hooks  → on_agent_started
  - Agent  post_hooks → on_agent_completed
  - Team   post_hooks → log_team_metrics
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def _stderr(msg: str) -> None:
    """Print to stderr with flush so output appears immediately."""
    print(msg, file=sys.stderr, flush=True)


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


# ── Real-time hooks (printed as things happen) ──────────────────────


def on_workflow_started(team) -> None:
    """Team pre-hook: announce the workflow has started."""
    try:
        _stderr("")
        _stderr("=" * 60)
        _stderr(f"WORKFLOW STARTED  ({team.name})")
        _stderr("=" * 60)
    except Exception as e:
        _stderr(f"[observability] on_workflow_started error: {e}")


def on_agent_started(agent) -> None:
    """Agent pre-hook: announce an agent has begun work."""
    try:
        name = getattr(agent, "name", "unknown")
        _stderr(f"  [{name}]  started")
    except Exception as e:
        _stderr(f"[observability] on_agent_started error: {e}")


def on_agent_completed(run_output, agent) -> None:
    """Agent post-hook: announce an agent has finished (or failed)."""
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
            if run_output.content:
                # Truncate long error messages for the live line
                text = str(run_output.content)
                error_msg = f"  {text[:120]}"
            _stderr(f"  [{name}]  {status_str}{error_msg}")
        else:
            _stderr(f"  [{name}]  completed   duration={dur_str}   tokens={tok}")
    except Exception as e:
        _stderr(f"[observability] on_agent_completed error: {e}")


# ── Final summary (team post-hook) ──────────────────────────────────


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
        agents.append(_build_agent_entry(member))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_output.run_id,
        "session_id": run_output.session_id,
        "status": status_str,
        "total_duration_s": _safe_duration(m),
        "total_tokens": m.total_tokens if m else None,
        "input_tokens": m.input_tokens if m else None,
        "output_tokens": m.output_tokens if m else None,
        "agents": agents,
    }


def _format_table(entry: Dict[str, Any]) -> str:
    """Format the log entry as a human-readable table."""
    lines = [
        "",
        "=" * 60,
        "OBSERVABILITY REPORT",
        "=" * 60,
        f"  Run ID:     {entry['run_id']}",
        f"  Status:     {entry['status']}",
        f"  Duration:   {entry['total_duration_s']:.2f}s" if entry["total_duration_s"] else "  Duration:   N/A",
        f"  Tokens:     {entry['total_tokens']} (in: {entry['input_tokens']}, out: {entry['output_tokens']})",
        "-" * 60,
        "  Per-Agent Breakdown:",
    ]
    for agent in entry["agents"]:
        dur = f"{agent['duration_s']:.2f}s" if agent["duration_s"] is not None else "N/A"
        tok = agent["total_tokens"] if agent["total_tokens"] is not None else "N/A"
        st = agent.get("status", "N/A")
        lines.append(f"    {agent['name']:<20} duration={dur:<10} tokens={tok:<8} status={st}")
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
        _stderr(_format_table(entry))
        _write_jsonl(entry)
    except Exception as e:
        _stderr(f"[observability] log_team_metrics error: {e}")
