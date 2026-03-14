# Design Document: Investment Team Multi-Agent System

## Overview

This project implements the **Investment Team** track of the Agno multi-agent take-home exercise. The system uses 5 AI agents (1 coordinator + 4 specialists) orchestrated via an Agno Team in **coordinate mode** to research companies, analyze financials, assess risks, make investment decisions, and produce a final investment recommendation memo. The Analyst and Critic agents run **concurrently** via a nested broadcast sub-team. The demo runs through the **Agno Playground UI**.

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
         Step 2: Delegate to Analysis Team (broadcast)
                          │
               ┌──────────┴──────────┐
               │                     │  (concurrent)
               ▼                     ▼
      ┌──────────────┐      ┌──────────────┐
      │ Analyst Agent │      │ Critic/Risk  │
      │ Comparative   │      │   Agent      │  Specialist #2 + #3
      │ analysis      │      │ Risks,       │  Run in parallel via
      │               │      │ assumptions, │  broadcast sub-team
      │               │      │ contrarian   │
      └──────┬────────┘      └──────┬───────┘
               │                     │
               └──────────┬──────────┘
                          │
         Step 3: Delegate to Decision
                          │
                          ▼
                 ┌──────────────┐
                 │Decision Agent│  Specialist #4
                 │ BUY/HOLD/SELL│  Weighs analysis vs risks,
                 │ decisions    │  top pick, thesis
                 └──────┬───────┘
                        │
         Step 4: Coordinator collects all outputs
                 and composes final investment memo
```

### Agent Roles (mapping to requirements)

| Requirement | Agent | Description |
|-------------|-------|-------------|
| 1 coordinating agent | **Investment Committee Lead** (Team coordinator) | Orchestrates the workflow sequence, collects all specialist outputs, and synthesizes the final investment memo |
| Specialist #1 | **Research Agent** | Comprehensive data gathering using Tavily (web search) and YFinance (financial data). Collects general info, financials, news, and negative news for all downstream agents |
| Specialist #2 | **Analyst Agent** | Pure-reasoning agent that produces comparative financial analysis from the research data: strengths, weaknesses, valuation assessment, growth outlook, and top pick. Runs concurrently with Critic via broadcast sub-team |
| Specialist #3 | **Critic/Risk Agent** | Pure-reasoning agent that identifies risks, challenges assumptions, finds data gaps, and provides a contrarian argument based on the research data. Runs concurrently with Analyst via broadcast sub-team |
| Specialist #4 | **Decision Agent** | Pure-reasoning agent that synthesizes the Analyst's findings and Critic's risks into explicit BUY/HOLD/SELL decisions for each company, identifies the top pick, and states the investment thesis |
| 1 output/review step | **Investment Committee Lead** | Same coordinator agent collects all outputs and composes the structured final memo |

### Execution Flow

1. **Research** — Coordinator delegates to Research Agent, which uses Tavily + YFinance tools to gather comprehensive data on each company (general info, financials, news, negative news/lawsuits/regulatory issues)
2. **Parallel Analysis** — Coordinator delegates to the Analysis Team (a `TeamMode.broadcast` sub-team), which runs Analyst Agent and Critic Agent **concurrently**. Both receive the research data (via `share_member_interactions=True` on the outer team) and produce their specialized outputs in parallel: `FinancialAnalysis` and `RiskAssessment`
3. **Decision** — Coordinator delegates to Decision Agent, which receives the combined financial analysis and risk assessment (via `share_member_interactions=True`) and produces a typed `InvestmentDecision` with per-company BUY/HOLD/SELL recommendations, top pick, investment thesis, and key conditions
4. **Final Memo** — Coordinator synthesizes all specialist outputs into a markdown investment memo, using the Decision Agent's recommendations as the basis for the Investment Decisions and Top Pick sections


## Tools

| Tool | Module | Used By | Purpose |
|------|--------|---------|---------|
| **TavilyTools** | `app/tools/search.py` | Research Agent | Web search for company news, products, competitive position, lawsuits, regulatory issues |
| **YFinanceTools** | `app/tools/finance.py` | Research Agent | Stock prices, market cap, P/E ratio, analyst recommendations, company info, financial news |
| **TickerValidationTool** | `app/tools/ticker_validation.py` | Research Agent | Validates ticker symbols against YFinance before research begins |

All tools are configured in `app/tools/` and imported by the Research Agent. Tavily and YFinance tools are wrapped with resilient subclasses (`ResilientTavilyTools`, `ResilientYFinanceTools` in `app/tools/resilient_wrappers.py`) that add retry with exponential backoff and a circuit breaker. The Analyst and Critic agents have no tools — they perform pure reasoning on the research data passed to them by the coordinator.

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

### Scenario 1: Invalid structured output — auto-correcting validators

LLMs can return enum-like fields with inconsistent casing (e.g., `"medium"` vs `"MEDIUM"` vs `"Medium"`). All constrained fields — `severity`, `recommendation`, `confidence`, and `category` — have Pydantic `@field_validator(mode="before")` validators that **auto-correct** casing before the model is constructed. If the value doesn't match any allowed option even after normalization, Pydantic raises `ValidationError`, preventing malformed data from propagating downstream.

**Implementation:** `app/models/schemas.py` defines `_normalize_enum()` and validators on `RiskFactor` (category, severity), `RiskAssessment` (overall_confidence), and `CompanyDecision` (recommendation, confidence). Allowed values: `BUY/HOLD/SELL`, `HIGH/MEDIUM/LOW`, `MARKET/COMPANY_SPECIFIC/SECTOR/MACRO/REGULATORY`.

**Tests:** `TestEnumValidation` in `app/tests/test_schemas.py` — 28 parametrized tests covering case normalization, whitespace handling, alias resolution (e.g., `"company-specific"` → `"COMPANY_SPECIFIC"`), and rejection of invalid values.

### Scenario 2: Transient LLM/tool failure — retry with exponential backoff + circuit breaker

All four agents are configured with `retries=2, delay_between_retries=2, exponential_backoff=True` using Agno's built-in retry mechanism. If a Gemini API call fails (rate limit, server error, timeout), the agent automatically retries up to 2 additional times with exponential backoff (2s, 4s).

At the tool level, both Tavily and YFinance tools are wrapped with **`ResilientTavilyTools`** and **`ResilientYFinanceTools`** (`app/tools/resilient_wrappers.py`). These subclasses wrap every registered tool entrypoint with:

- **Retry with exponential backoff** (up to 3 attempts, 1s → 2s → 4s delays) — retries on both exceptions and error-string responses (e.g., `"Error fetching current price for XYZ"`)
- **Circuit breaker** — after 3 consecutive failures for a tool, the breaker trips to OPEN state and returns a `"Service temporarily unavailable"` message immediately, preventing cascading failures. After a 60-second reset timeout, one probe request is allowed through (half-open state); if it succeeds, the breaker closes.

All retry attempts and circuit breaker state changes are logged to stderr for real-time observability.

**Implementation:** `app/tools/resilient_wrappers.py` (CircuitBreaker class, `_resilient_method` wrapper, `_is_error_response` detector). Tool factories in `app/tools/search.py` and `app/tools/finance.py` return the resilient subclasses.

**Tests:** `TestCircuitBreaker`, `TestIsErrorResponse`, `TestResilientMethod`, `TestResilientToolsIntegration` in `app/tests/test_resilience.py` — 19 tests covering breaker lifecycle (closed → open → half-open → closed), error-string detection, retry behavior, and integration with the tool factories.

### Scenario 3: Malformed user input — ticker validation

If a user provides invalid ticker symbols (misspelled, delisted, or fictional), the Research Agent validates them **before** spending time and API credits on full research. A `TickerValidationTool` (`app/tools/ticker_validation.py`) checks each ticker against `yfinance.Ticker().info`:

- **Valid tickers** (have a `shortName` in the YFinance response) proceed to research
- **Invalid tickers** are reported back with a warning and suggestions (check spelling, exchange suffix like `.L` or `.TO`)
- **Empty input** returns an error message asking for ticker symbols
- If **all** tickers are invalid, the agent stops and reports the issue rather than producing a garbage memo

**Implementation:** `TickerValidationTool` Agno Toolkit in `app/tools/ticker_validation.py`, added as the 3rd tool on the Research Agent. Instructions prepend a "STEP 0 — VALIDATE TICKERS" step before data gathering.

**Tests:** `TestTickerValidationTool` in `app/tests/test_resilience.py` — 8 tests covering empty input, valid/invalid/mixed tickers (mocked YFinance), exception handling, and case normalization.

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
    search.py                # Resilient Tavily search tools
    finance.py               # Resilient YFinance tools
    resilient_wrappers.py    # Retry + circuit breaker wrappers
    ticker_validation.py     # Ticker symbol validation tool
  tests/
    __init__.py
    test_schemas.py          # Pydantic model serialization + validation tests
    test_workflow.py         # Agent/Team creation + retry config tests
    test_resilience.py       # Circuit breaker, retry, ticker validation tests
data/
  examples/
    sample_memo.md           # Example output artifact
pyproject.toml               # Dependencies
.env.example                 # Environment variable template
README.md                    # Project documentation
design.md                    # This file
```

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

The coordinator will delegate to Research → Analysis Team (Analyst + Critic in parallel) → Decision, then synthesize the final memo. Each specialist's work is visible in the UI.

### Run Tests

```bash
pytest app/tests/ -v
```

Expected: 88 tests pass (34 schema tests + 10 agent/team creation tests + 13 observability tests + 31 resilience tests).