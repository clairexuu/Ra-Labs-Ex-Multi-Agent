"""Tests for agent and team creation."""

from agno.agent import Agent
from agno.team import Team

from app.agents.analyst import create_analyst_agent
from app.agents.critic import create_critic_agent
from app.agents.research import create_research_agent
from app.team.investment_team import create_investment_team


class TestAgentCreation:
    def test_research_agent_creates_successfully(self):
        agent = create_research_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Research Agent"
        assert len(agent.tools) == 2  # DuckDuckGo + YFinance

    def test_analyst_agent_creates_successfully(self):
        agent = create_analyst_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Analyst Agent"

    def test_critic_agent_creates_successfully(self):
        agent = create_critic_agent()
        assert isinstance(agent, Agent)
        assert agent.name == "Critic Agent"


class TestTeamCreation:
    def test_investment_team_creates_successfully(self):
        team = create_investment_team()
        assert isinstance(team, Team)
        assert team.name == "Investment Team"
        assert len(team.members) == 3
