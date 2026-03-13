# Design Document: Investment Team Multi-Agent System

## Overview

This project implements the **Investment Team** track of the Agno multi-agent take-home exercise. The system uses 5 AI agents (1 coordinator + 4 specialists) orchestrated via an Agno Team in **coordinate mode** to research companies, analyze financials, assess risks, make investment decisions, and produce a final investment recommendation memo. The demo runs through the **Agno Playground UI**.

## Architecture

```
                  Agno Playground UI (localhost:7777)
                             │
                             ▼
              ┌─────────────────────────────┐
              │  Investment Committee Lead   │  Coordinating Agent (Team Leader)
              │  (coordinator + output/review│  + Output/Review Step
              │   step)                      │  Synthesizes final memo
              └─────────────┬───────────────┘
                            │
               Step 1: Delegate to Research
                            │
                            ▼
                   ┌──────────────┐
                   │Research Agent │  Specialist #1
                   │ Tavily +     │  Gathers financial data + news
                   │ YFinance     │  + risk-relevant info
                   └──────┬───────┘
                          │
         Step 2: Delegate to Analyst
                          │
                          ▼
                 ┌──────────────┐
                 │ Analyst Agent │  Specialist #2
                 │ Comparative   │  Strengths, weaknesses,
                 │ analysis      │  valuation, top pick
                 └──────┬───────┘
                        │
         Step 3: Delegate to Critic
                        │
                        ▼
                 ┌──────────────┐
                 │ Critic/Risk  │  Specialist #3
                 │   Agent      │  Risks, assumptions,
                 │              │  contrarian view
                 └──────┬───────┘
                        │
         Step 4: Delegate to Decision
                        │
                        ▼
                 ┌──────────────┐
                 │Decision Agent│  Specialist #4
                 │ BUY/HOLD/SELL│  Weighs analysis vs risks,
                 │ decisions    │  top pick, thesis
                 └──────┬───────┘
                        │
         Step 5: Coordinator collects all outputs
                 and composes final investment memo
```

### Agent Roles (mapping to requirements)

| Requirement | Agent | Description |
|-------------|-------|-------------|
| 1 coordinating agent | **Investment Committee Lead** (Team coordinator) | Orchestrates the workflow sequence, collects all specialist outputs, and synthesizes the final investment memo |
| Specialist #1 | **Research Agent** | Comprehensive data gathering using Tavily (web search) and YFinance (financial data). Collects general info, financials, news, and negative news for all downstream agents |
| Specialist #2 | **Analyst Agent** | Pure-reasoning agent that produces comparative financial analysis from the research data: strengths, weaknesses, valuation assessment, growth outlook, and top pick |
| Specialist #3 | **Critic/Risk Agent** | Pure-reasoning agent that identifies risks, challenges assumptions, finds data gaps, and provides a contrarian argument based on the research data |
| Specialist #4 | **Decision Agent** | Pure-reasoning agent that synthesizes the Analyst's findings and Critic's risks into explicit BUY/HOLD/SELL decisions for each company, identifies the top pick, and states the investment thesis |
| 1 output/review step | **Investment Committee Lead** | Same coordinator agent collects all outputs and composes the structured final memo |

### Execution Flow

1. **Research** — Coordinator delegates to Research Agent, which uses Tavily + YFinance tools to gather comprehensive data on each company (general info, financials, news, negative news/lawsuits/regulatory issues)
2. **Analysis** — Coordinator delegates to Analyst Agent, which receives the research data (via `share_member_interactions=True`) and produces a typed `FinancialAnalysis` with per-company strengths/weaknesses/valuation/growth and a top pick
3. **Risk Review** — Coordinator delegates to Critic Agent, which receives the research data and produces a typed `RiskAssessment` with categorized risks, challenged assumptions, data gaps, and a contrarian view
4. **Decision** — Coordinator delegates to Decision Agent, which receives the financial analysis and risk assessment (via `share_member_interactions=True`) and produces a typed `InvestmentDecision` with per-company BUY/HOLD/SELL recommendations, top pick, investment thesis, and key conditions
5. **Final Memo** — Coordinator synthesizes all specialist outputs into a markdown investment memo, using the Decision Agent's recommendations as the basis for the Investment Decisions and Top Pick sections

### Why Agno Team Coordinate Mode

- The Team coordinator acts as the **coordinating agent** and the **output/review step**, while 4 specialists handle research, analysis, risk review, and decision-making
- `mode="coordinate"` — the coordinator orchestrates which member to call and in what order
- `share_member_interactions=True` — each specialist sees the outputs of prior specialists, so the Analyst and Critic both have access to the Research Agent's data
- `show_members_responses=True` — each specialist's work is displayed in the Playground UI

## Tools

| Tool | Module | Used By | Purpose |
|------|--------|---------|---------|
| **TavilyTools** | `app/tools/search.py` | Research Agent | Web search for company news, products, competitive position, lawsuits, regulatory issues |
| **YFinanceTools** | `app/tools/finance.py` | Research Agent | Stock prices, market cap, P/E ratio, analyst recommendations, company info, financial news |

Both tools are configured in `app/tools/` and imported by the Research Agent. The Analyst and Critic agents have no tools — they perform pure reasoning on the research data passed to them by the coordinator.

## Typed State (Pydantic Models)

All agent inputs/outputs use strongly typed Pydantic models defined in `app/models/schemas.py`:

### Research Agent Output
- **`CompanyResearch`** — Single company data: ticker, company_name, sector, current_price, market_cap, pe_ratio, revenue_growth, analyst_consensus, recent_news, key_products, competitive_position, negative_news
- **`CompanyResearchSet`** — Collection: sector, list of `CompanyResearch`, research_date

### Analyst Agent Output
- **`CompanyAnalysis`** — Per-company: ticker, strengths, weaknesses, valuation_assessment, growth_outlook
- **`FinancialAnalysis`** — Comparative: sector, list of `CompanyAnalysis`, comparative_summary, top_pick

### Critic Agent Output
- **`RiskFactor`** — Single risk: category, description, severity, affected_tickers
- **`RiskAssessment`** — Full assessment: list of `RiskFactor`, assumptions_challenged, data_gaps, contrarian_view, overall_confidence

### Decision Agent Output
- **`CompanyDecision`** — Per-company: ticker, recommendation (BUY/HOLD/SELL), confidence, reasoning
- **`InvestmentDecision`** — Full decision: sector, list of `CompanyDecision`, top_pick, top_pick_justification, investment_thesis, key_conditions

All models use `output_schema` on the Agent to enforce structured output from the LLM.

## Resilience

### Scenario 1: Missing/partial research data
If YFinance or Tavily tools fail for a company (invalid ticker, API timeout, rate limit), the Research Agent's instructions say: *"If a tool call fails or returns no data for a company, note the data gap and continue with available information."* The Critic Agent will then flag these gaps in its risk assessment.

### Scenario 2: Transient LLM/tool failure
Agno's built-in retry mechanism is available on each agent. If a Gemini API call fails (rate limit, server error, timeout), Agno can automatically retry with exponential backoff. The Team coordinator handles member failures gracefully by noting which specialist could not complete their analysis.

## File Structure

```
app/
  __init__.py
  playground.py              # Agno Playground server (port 7777)
  config.py                  # Gemini model config via env vars
  models/
    __init__.py
    schemas.py               # All Pydantic models for typed state
  agents/
    __init__.py
    research.py              # Research Agent (specialist #1)
    analyst.py               # Analyst Agent (specialist #2)
    critic.py                # Critic/Risk Agent (specialist #3)
    decision.py              # Decision Agent (specialist #4)
  team/
    __init__.py
    investment_team.py       # Team definition with coordinator
  tools/
    __init__.py
    search.py                # DuckDuckGoTools configuration
    finance.py               # YFinanceTools configuration
  tests/
    __init__.py
    test_schemas.py          # Pydantic model serialization tests
    test_workflow.py         # Agent/Team creation tests
data/
  examples/
    sample_memo.md           # Example output artifact
pyproject.toml               # Dependencies
.env.example                 # Environment variable template
README.md                    # Project documentation
design.md                    # This file
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `agno` | Multi-agent framework (Team, Agent, Playground) |
| `google-genai` | Gemini LLM provider (gemini-2.0-flash default) |
| `yfinance` | Financial data: stock prices, analyst recommendations, company info |
| `tavily-python` | Web search for news, lawsuits, regulatory info |
| `pydantic>=2.0` | Typed state models for agent inputs/outputs |
| `python-dotenv` | Environment variable management |
| `sqlalchemy` | Agno SQLite storage backend |
| `fastapi[standard]` | Agno Playground server |

## How to Run

### Prerequisites

- Python 3.11+
- Google Gemini API key — get one free at https://aistudio.google.com

### Installation

```bash
# Clone the repository
git clone https://github.com/clairexuu/Ra-Labs-Ex-Multi-Agent.git
cd Ra-Labs-Ex-Multi-Agent

# Install dependencies
pip install -e ".[dev]"

# Configure API key
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=your-key-here
```

### Set Up and Run Locally

1. Start the AgentOS server:

```bash
python app/playground.py
```

2. In a separate terminal, launch the local chat UI:

```bash
npx create-agent-ui@latest
cd agent-ui
npm run dev
```

4. Open **http://localhost:3000** in your browser. On the left panel under "Mode", select "Team", then select "Investment Team". Ready to Chat. 

### Demo Prompt

Enter this in the Playground chat:

> Analyze NVDA, AMD, and INTC in the Semiconductors sector and produce an investment memo

The coordinator will delegate to Research → Analyst → Critic, then synthesize the final memo. Each specialist's work is visible in the UI.

### Run Tests

```bash
pytest app/tests/ -v
```

Expected: 11 tests pass (6 schema tests + 5 agent/team creation tests).

## Implementation Notes

### Agno API Details (discovered during implementation)

- Agent structured output uses `output_schema=` (not `response_model=`)
- YFinanceTools parameters use `enable_` prefix: `enable_stock_price=True` (not `stock_price=True`)
- Team has no `leader=` parameter — the Team itself is the coordinator; its `model` and `instructions` define the coordinator behavior
- Agent does not accept `show_tool_calls=` — tool call visibility is controlled at the Team/Playground level
- DuckDuckGo search requires the `ddgs` package in addition to `duckduckgo-search`

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestration | Agno Team coordinate mode | Satisfies "real multi-agent pattern" requirement; coordinator is a genuine agent, not just Python glue code |
| Model | Gemini 2.0 Flash | Free tier available, fast, good structured output support. Swappable via `MODEL_ID` env var |
| Tools | Tavily + YFinance only | Exercise says 2-4 tools; these cover web search + financial data. Research Agent gathers all data for downstream agents |
| Tool placement | Both tools on Research Agent only | Research Agent is the single data-gathering step. Analyst and Critic do pure reasoning on the research data |
| Demo UX | Agno Playground | Preferred option per requirements. Shows team execution, member responses, and tool calls in a web UI |
| Database | SQLite (local file) | No PostgreSQL setup needed. Sufficient for demo session persistence |
| Scope | 5 agents (1 coordinator + 4 specialists), 2 tools, typed state, Playground demo | Per the "do not overbuild" guidance in the exercise |
