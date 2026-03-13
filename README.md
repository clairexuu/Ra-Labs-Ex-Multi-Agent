# Investment Team - Multi-Agent Analysis System

A multi-agent investment analysis system built with [Agno](https://github.com/agno-agi/agno) that researches and evaluates companies to produce investment recommendation memos.

**Track**: Investment Team

## Architecture

```
                  Agno Playground UI (localhost:7777)
                             │
                             ▼
              ┌─────────────────────────────┐
              │  Investment Committee Lead   │  Coordinating Agent
              │  (Team coordinator)          │  + Output/Review Step
              └─────────────┬───────────────┘
                            │
               Step 1: Delegate to Research
                            │
                            ▼
                   ┌──────────────┐
                   │Research Agent │  Specialist #1
                   │ Tavily +     │  Financial data + news +
                   │ YFinance     │  risk-relevant info
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
         Step 5: Coordinator synthesizes
                 final investment memo
```

### Agent Roles

| Agent | Role | Tools |
|-------|------|-------|
| **Investment Committee Lead** (coordinator) | Orchestrates workflow, synthesizes final memo | None (orchestration) |
| **Research Agent** (specialist #1) | Comprehensive data gathering: financials, news, negative news | Tavily, YFinance |
| **Analyst Agent** (specialist #2) | Comparative financial analysis: strengths, weaknesses, valuation | None (reasoning) |
| **Critic/Risk Agent** (specialist #3) | Risk assessment, challenges assumptions, contrarian view | None (reasoning) |
| **Decision Agent** (specialist #4) | BUY/HOLD/SELL decisions, weighs analysis vs risks, top pick | None (reasoning) |

### Tools Used

1. **TavilyTools** - Web search for company news, products, competitive position, lawsuits, regulatory issues
2. **YFinanceTools** - Stock prices, market cap, analyst recommendations, company info, financial news

## Setup

### Prerequisites
- Python 3.11+
- Google Gemini API key ([get one free](https://aistudio.google.com))

### Installation

```bash
# Clone the repository
git clone https://github.com/clairexuu/Ra-Labs-Ex-Multi-Agent.git
cd Ra-Labs-Ex-Multi-Agent

# Install dependencies
pip install -e ".[dev]"

# Configure API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

### Run the Demo

```bash
# Start the Agno Playground
python app/playground.py
```

Then open http://localhost:7777 in your browser (or connect from https://app.agno.com/playground).

**Demo prompt:**
> Analyze NVDA, AMD, and INTC in the Semiconductors sector and produce an investment memo

### Run Tests

```bash
pytest app/tests/ -v
```

## Project Structure

```
app/
  playground.py              # Agno Playground server (demo UX)
  config.py                  # Model configuration (Gemini 2.0 Flash)
  models/
    schemas.py               # Pydantic models for typed agent state
  agents/
    research.py              # Research Agent definition
    analyst.py               # Analyst Agent definition
    critic.py                # Critic/Risk Agent definition
    decision.py              # Decision Agent definition
  team/
    investment_team.py       # Team with coordinator
  tools/
    search.py                # Tavily tool config
    finance.py               # YFinance tool config
  tests/
    test_schemas.py          # Pydantic model tests
    test_workflow.py         # Agent/Team creation tests
data/
  examples/
    sample_memo.md           # Example output
```

## Typed State

All agent inputs and outputs use Pydantic models defined in `app/models/schemas.py`:

- **CompanyResearch** / **CompanyResearchSet** - Research Agent output (financial data, news, negative news per company)
- **FinancialAnalysis** / **CompanyAnalysis** - Analyst Agent output (strengths, weaknesses, valuation, growth outlook)
- **RiskAssessment** / **RiskFactor** - Critic Agent output (categorized risks, challenged assumptions, contrarian view)
- **InvestmentDecision** / **CompanyDecision** - Decision Agent output (BUY/HOLD/SELL per company, top pick, investment thesis)

## Resilience

1. **Missing/partial research data**: Research Agent instructions handle tool failures gracefully - gaps are noted and the workflow continues with available data. The Critic Agent flags data gaps in its risk assessment.
2. **Transient LLM/tool failures**: Agno's built-in retry mechanism handles API rate limits, server errors, and timeouts with exponential backoff.

## Tradeoffs and Known Limitations

- **Sequential execution in coordinate mode**: Analyst and Critic agents run sequentially (not truly parallel) in Agno's coordinate mode. Both receive the Research Agent's output via shared interactions.
- **Model choice**: Gemini 2.0 Flash is used for cost efficiency. Can be swapped to a more capable model via the `MODEL_ID` env var.
- **No persistent storage**: Sessions are stored in SQLite locally. No PostgreSQL setup required for the demo.
- **Tool limitations**: YFinance data can be delayed or incomplete for some tickers. Tavily search results vary by region and time.

## Build Notes

- Used Claude Code for architecture planning, code generation, and iterative debugging
- AI tools helped most with: Agno API discovery (the framework's actual parameter names differ from documentation examples), project scaffolding, and Pydantic model design
- Manual debugging required for: Agno API mismatches (`response_model` vs `output_schema`, `stock_price` vs `enable_stock_price`, `leader` not being a valid Team param, `show_tool_calls` not valid on Agent)
- Iterated on architecture based on requirements review: started with manual orchestration, pivoted to Agno Team coordinate mode with Playground UI
- Kept scope tight: 5 agents (1 coordinator + 4 specialists), 2 tools, typed state, Playground demo - per the "do not overbuild" guidance
