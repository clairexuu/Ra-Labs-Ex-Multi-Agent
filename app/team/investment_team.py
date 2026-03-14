from agno.team import Team
from agno.team.mode import TeamMode

from app.agents.analyst import create_analyst_agent
from app.agents.critic import create_critic_agent
from app.agents.decision import create_decision_agent
from app.agents.research import create_research_agent
from app.config import get_model
from app.observability import (
    log_team_metrics,
    on_agent_completed,
    on_agent_started,
    on_workflow_started,
    setup_logging,
)


def create_investment_team() -> Team:
    """Create the Investment Team with a coordinating leader, a parallel
    analysis sub-team, and specialist agents.

    Architecture:
        - Team coordinator (Investment Committee Lead): Orchestrates the workflow
          and synthesizes the final investment memo (coordinator + output/review)
        - Research Agent (Specialist #1): Comprehensive data gathering
        - Analysis Team (broadcast sub-team): Runs Analyst + Critic in parallel
            - Analyst Agent (Specialist #2): Comparative financial analysis
            - Critic Agent (Specialist #3): Risk assessment and contrarian review
        - Decision Agent (Specialist #4): Investment decisions

    Execution flow:
        1. Coordinator delegates to Research Agent for data gathering
        2. Coordinator delegates to Analysis Team (broadcast), which runs
           Analyst Agent and Critic Agent concurrently
        3. Coordinator delegates to Decision Agent for investment decisions
        4. Coordinator synthesizes all outputs into the final investment memo
    """
    setup_logging()

    research_agent = create_research_agent()
    analyst_agent = create_analyst_agent()
    critic_agent = create_critic_agent()
    decision_agent = create_decision_agent()

    # Attach real-time observability hooks to each agent
    for agent in [research_agent, analyst_agent, critic_agent, decision_agent]:
        agent.pre_hooks = [on_agent_started]
        agent.post_hooks = [on_agent_completed]

    # Broadcast sub-team: runs Analyst + Critic concurrently.
    # Both receive the same delegated task (enriched with Research output
    # via the outer team's share_member_interactions) and produce their
    # specialized outputs in parallel.
    analysis_team = Team(
        name="Analysis Team",
        mode=TeamMode.broadcast,
        model=get_model(),
        members=[analyst_agent, critic_agent],
        description=(
            "Parallel analysis sub-team that runs financial analysis and risk "
            "assessment simultaneously. Delegates the research data to both "
            "the Analyst Agent and Critic Agent, then returns their outputs."
        ),
        instructions=[
            "You coordinate a parallel analysis of research data.",
            "When you receive research data and a task, broadcast it to both members.",
        ],
        respond_directly=True,
        share_member_interactions=False,
        show_members_responses=False,
        stream_member_events=False,
        markdown=False,
    )

    return Team(
        name="Investment Team",
        mode=TeamMode.coordinate,
        model=get_model(),
        members=[research_agent, analysis_team, decision_agent],
        description=(
            "An investment analysis team that researches and evaluates "
            "companies to produce investment recommendation memos."
        ),
        instructions=[
            "You are the Investment Committee Lead coordinating a team of specialists.",
            "When a user asks you to analyze companies, follow this workflow:",
            "",
            "IMPORTANT: You MUST complete ALL four steps below before producing the final memo. "
            "Do NOT stop after receiving the analysis — you MUST also delegate to the Decision Agent.",
            "",
            "The user may provide stock tickers (e.g., NVDA, AMD), company names "
            "(e.g., Anthropic, OpenAI), or a mix of both. The Research Agent will "
            "classify each as PUBLIC or PRIVATE and adapt its research accordingly.",
            "",
            "The user may also ask you to DISCOVER or FIND companies in a sector/niche, "
            "e.g., 'find 3 AI startups in autonomous driving and compare them'. In this "
            "case, pass the full request to the Research Agent, which has a "
            "discover_companies tool to search for and validate companies automatically. "
            "The rest of the workflow (analysis, risk assessment, decision) proceeds "
            "identically.",
            "",
            "IMPORTANT: For discovery requests, do NOT report discovery issues to the user. "
            "Do NOT mention which companies were rejected, failed verification, or could not "
            "be found. Do NOT tell the user you are re-delegating or retrying. Present "
            "the final discovered companies seamlessly as if they were always the target. "
            "The user should only see the final investment memo with the successfully "
            "discovered companies.",
            "",
            "STEP 1 - RESEARCH:",
            "Delegate to the Research Agent to gather comprehensive data on the companies.",
            "Pass ALL company identifiers exactly as the user provided them.",
            "The Research Agent will classify companies as public or private and gather "
            "appropriate data: financials via YFinance for public companies, and funding/"
            "valuation data via web search for private companies.",
            "",
            "STEP 2 - PARALLEL ANALYSIS:",
            "After receiving the research data, delegate to the Analysis Team.",
            "The Analysis Team will run the Analyst Agent and Critic Agent in parallel.",
            "Ask it to analyze the research data: the Analyst should produce a comparative",
            "analysis with strengths, weaknesses, valuation, growth outlook, and",
            "a top pick; the Critic should identify risks, challenge assumptions, find data",
            "gaps, and provide a contrarian view.",
            "Include the full research data in your delegation so both agents can access it.",
            "",
            "STEP 3 - DECISION:",
            "After receiving the combined analysis and risk assessment from the Analysis Team,",
            "delegate to the Decision Agent.",
            "Ask the Decision Agent to weigh the analyst's findings against the",
            "critic's risks and produce explicit investment decisions for each",
            "company: BUY/HOLD/SELL for public companies, INVEST/PASS/WATCH for",
            "private companies, along with the overall top pick and investment thesis.",
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
            "## Investment Decisions (use the Decision Agent's recommendations)",
            "## Top Pick and Thesis",
            "## Open Questions and Next Steps",
            "",
            "Use the Decision Agent's recommendations as the basis for the Investment Decisions",
            "and Top Pick sections. Do not override them - present them with the supporting evidence.",
            "For private companies, include funding and valuation context instead of stock metrics.",
            "The memo should be concise and actionable.",
        ],
        show_members_responses=False,
        stream_member_events=False,
        share_member_interactions=True,
        markdown=True,
        pre_hooks=[on_workflow_started],
        post_hooks=[log_team_metrics],
    )
