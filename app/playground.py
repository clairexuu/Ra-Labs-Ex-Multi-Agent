"""Agno Playground server for the Investment Team demo.

Run with:
    python app/playground.py

Then open http://localhost:7777 in your browser, or connect
from https://app.agno.com/playground to localhost:7777.

Demo prompts:
    "Analyze NVDA, AMD, and INTC in the Semiconductors sector"
    "Analyze Anthropic, OpenAI, and Cohere in the AI sector"
    "Find 3 AI startups in autonomous driving and compare them"
    "Search for 4 public companies in cloud computing and compare"
"""

from agno.os import AgentOS

from app.team.investment_team import create_investment_team

investment_team = create_investment_team()

agent_os = AgentOS(teams=[investment_team])
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve("app.playground:app", host="0.0.0.0", reload=True, port=7777)
