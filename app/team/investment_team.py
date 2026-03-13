from agno.team import Team
from agno.team.mode import TeamMode

from app.agents.analyst import create_analyst_agent
from app.agents.critic import create_critic_agent
from app.agents.research import create_research_agent
from app.config import get_model


def create_investment_team() -> Team:
    """Create the Investment Team with a coordinating leader and 3 specialists.

    The Team itself acts as the coordinating agent (Investment Committee Lead).
    It delegates to 3 specialist member agents and synthesizes the final memo.

    Architecture:
        - Team coordinator (Investment Committee Lead): Orchestrates the workflow
          and synthesizes the final investment memo (coordinator + output/review)
        - Research Agent (Specialist #1): Comprehensive data gathering
        - Analyst Agent (Specialist #2): Comparative financial analysis
        - Critic Agent (Specialist #3): Risk assessment and contrarian review

    Execution flow:
        1. Coordinator delegates to Research Agent for data gathering
        2. Coordinator delegates to Analyst Agent for financial analysis
        3. Coordinator delegates to Critic Agent for risk assessment
        4. Coordinator synthesizes all outputs into the final investment memo
    """
    research_agent = create_research_agent()
    analyst_agent = create_analyst_agent()
    critic_agent = create_critic_agent()

    return Team(
        name="Investment Team",
        mode=TeamMode.coordinate,
        model=get_model(),
        members=[research_agent, analyst_agent, critic_agent],
        description=(
            "An investment analysis team that researches and evaluates "
            "companies to produce investment recommendation memos."
        ),
        instructions=[
            "You are the Investment Committee Lead coordinating a team of specialists.",
            "When a user asks you to analyze companies, follow this workflow:",
            "",
            "STEP 1 - RESEARCH:",
            "Delegate to the Research Agent to gather comprehensive data on the companies.",
            "Ask the Research Agent to research each company's financials, news, products,",
            "competitive position, and any negative news (lawsuits, regulatory issues, etc).",
            "",
            "STEP 2 - ANALYSIS:",
            "After receiving the research data, delegate to the Analyst Agent.",
            "Ask the Analyst Agent to produce a comparative financial analysis",
            "based on the research data, including strengths, weaknesses, valuation,",
            "and growth outlook for each company, with a top pick recommendation.",
            "",
            "STEP 3 - RISK REVIEW:",
            "After receiving the analysis, delegate to the Critic Agent.",
            "Ask the Critic Agent to identify risks, challenge assumptions,",
            "and provide a contrarian view based on the research data.",
            "",
            "STEP 4 - FINAL MEMO:",
            "After receiving all specialist outputs, synthesize everything into",
            "a comprehensive investment memo in markdown format with these sections:",
            "",
            "# Investment Memo: [Sector]",
            "## Executive Summary",
            "## Company Overviews",
            "## Comparative Analysis",
            "## Risk Assessment",
            "## Recommendation (BUY / HOLD / SELL for each company)",
            "## Open Questions and Next Steps",
            "",
            "Be decisive. Make clear recommendations backed by the specialist analysis.",
            "The memo should be concise and actionable.",
        ],
        show_members_responses=True,
        share_member_interactions=True,
        markdown=True,
    )
