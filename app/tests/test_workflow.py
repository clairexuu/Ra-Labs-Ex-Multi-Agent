"""Tests for agent and team creation."""

from agno.agent import Agent
from agno.team import Team
from agno.team.mode import TeamMode

from app.agents.analyst import create_analyst_agent
from app.agents.critic import create_critic_agent
from app.agents.decision import create_decision_agent
from app.agents.research import create_research_agent
from app.team.investment_team import create_investment_team


class TestAgentCreation:
    def test_research_agent_creates_successfully(self):
        agent = create_research_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Research Agent"
        assert len(agent.tools) == 3  # Tavily + YFinance + CompanyValidation

    def test_analyst_agent_creates_successfully(self):
        agent = create_analyst_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Analyst Agent"

    def test_critic_agent_creates_successfully(self):
        agent = create_critic_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Critic Agent"

    def test_decision_agent_creates_successfully(self):
        agent = create_decision_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Decision Agent"

    def test_analyst_agent_has_retry_config(self):
        agent = create_analyst_agent()
        assert agent.retries == 2
        assert agent.exponential_backoff is True
        assert agent.delay_between_retries == 2

    def test_critic_agent_has_retry_config(self):
        agent = create_critic_agent()
        assert agent.retries == 2
        assert agent.exponential_backoff is True
        assert agent.delay_between_retries == 2

    def test_decision_agent_has_retry_config(self):
        agent = create_decision_agent()
        assert agent.retries == 2
        assert agent.exponential_backoff is True
        assert agent.delay_between_retries == 2


class TestTeamCreation:
    def test_investment_team_creates_successfully(self):
        team = create_investment_team()
        assert isinstance(team, Team)
        assert team.name == "Investment Team"
        # 3 members: Research Agent, Analysis Team (sub-team), Decision Agent
        assert len(team.members) == 3

    def test_analysis_sub_team_structure(self):
        team = create_investment_team()
        # Second member is the broadcast Analysis Team
        analysis_team = team.members[1]
        assert isinstance(analysis_team, Team)
        assert analysis_team.name == "Analysis Team"
        assert analysis_team.mode == TeamMode.broadcast
        assert len(analysis_team.members) == 2
