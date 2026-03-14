"""End-to-end integration test — runs the full workflow against live APIs.

Usage:
    pytest app/tests/test_e2e.py -v -s          # run e2e only
    pytest app/tests/ -v -m "not e2e"           # skip e2e in fast runs
"""

import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

from agno.run.base import RunStatus

from app.team.investment_team import create_investment_team

DEMO_PROMPT = (
    "Analyze NVDA, AMD, and INTC in the Semiconductors sector "
    "and produce an investment memo"
)

PRIVATE_COMPANY_PROMPT = (
    "Analyze Anthropic, OpenAI, and Cohere in the AI sector "
    "and produce an investment memo"
)

MAX_ATTEMPTS = 2


def _workflow_complete(result) -> bool:
    """Check that all expected agents participated."""
    from agno.run.team import TeamRunOutput

    names = set()
    for member in result.member_responses:
        if isinstance(member, TeamRunOutput):
            names.add(member.team_name)
        else:
            names.add(member.agent_name)
    return {"Research Agent", "Analysis Team", "Decision Agent"} <= names


def _run_with_retry(prompt):
    """Run the workflow, retrying on errors or incomplete delegation."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        team = create_investment_team()
        result = team.run(prompt)
        if result.status != RunStatus.error and _workflow_complete(result):
            return result
        reason = (
            result.content if result.status == RunStatus.error
            else "incomplete workflow — not all agents participated"
        )
        print(
            f"\n  [e2e] attempt {attempt}/{MAX_ATTEMPTS} failed: {reason}",
            file=sys.stderr,
        )
    return result


@pytest.mark.e2e
class TestInvestmentTeamE2E:

    @pytest.fixture(scope="class")
    def result(self):
        """Run the workflow (with retry on transient LLM errors) once for all tests."""
        return _run_with_retry(DEMO_PROMPT)

    def test_workflow_completes(self, result):
        """Team runs to completion without error."""
        assert result.content is not None
        assert len(result.content) > 500  # non-trivial memo

    def test_memo_has_required_sections(self, result):
        """Final memo contains all sections from coordinator instructions."""
        content = result.content
        for heading in [
            "Executive Summary",
            "Company Overviews",
            "Comparative Analysis",
            "Risk Assessment",
            "Investment Decisions",
            "Top Pick",
            "Open Questions",
        ]:
            assert heading.lower() in content.lower(), f"Missing section: {heading}"

    def test_memo_mentions_all_tickers(self, result):
        """All requested companies appear in the output."""
        for ticker in ["NVDA", "AMD", "INTC"]:
            assert ticker in result.content

    def test_all_agents_participated(self, result):
        """All 4 specialist agents produced responses."""
        # Collect agent/team names from member_responses.  The coordinator
        # may occasionally retry a delegation, so we check that the
        # expected roles appear rather than asserting an exact count.
        from agno.run.team import TeamRunOutput

        names = set()
        for member in result.member_responses:
            if isinstance(member, TeamRunOutput):
                names.add(member.team_name)
            else:
                names.add(member.agent_name)

        assert "Research Agent" in names
        assert "Analysis Team" in names
        assert "Decision Agent" in names

    def test_metrics_captured(self, result):
        """Observability metrics are populated."""
        m = result.metrics
        assert m is not None
        assert m.total_tokens > 0
        assert m.input_tokens > 0
        assert m.output_tokens > 0


@pytest.mark.e2e
class TestPrivateCompanyE2E:

    @pytest.fixture(scope="class")
    def result(self):
        """Run the workflow for private AI companies."""
        return _run_with_retry(PRIVATE_COMPANY_PROMPT)

    def test_workflow_completes(self, result):
        """Team runs to completion without error."""
        assert result.content is not None
        assert len(result.content) > 500

    def test_memo_has_required_sections(self, result):
        """Final memo contains all sections from coordinator instructions."""
        content = result.content
        for heading in [
            "Executive Summary",
            "Company Overviews",
            "Comparative Analysis",
            "Risk Assessment",
            "Investment Decisions",
            "Top Pick",
            "Open Questions",
        ]:
            assert heading.lower() in content.lower(), f"Missing section: {heading}"

    def test_memo_mentions_all_companies(self, result):
        """All requested companies appear in the output."""
        for company in ["Anthropic", "OpenAI", "Cohere"]:
            assert company in result.content

    def test_all_agents_participated(self, result):
        """All 4 specialist agents produced responses."""
        from agno.run.team import TeamRunOutput

        names = set()
        for member in result.member_responses:
            if isinstance(member, TeamRunOutput):
                names.add(member.team_name)
            else:
                names.add(member.agent_name)

        assert "Research Agent" in names
        assert "Analysis Team" in names
        assert "Decision Agent" in names
