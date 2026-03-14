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
                   │ Tavily +     │  Gathers company data + financial data + 
                   │ YFinance     │  news + risk-relevant info
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

The system supports two entry modes: **direct** (user provides company names/tickers) and **discovery** (user asks to find companies in a sector/niche). Both converge into the same downstream pipeline.

0. **Discovery** *(optional)* — If the user asks to find or discover companies (e.g., "find 3 AI startups in autonomous driving"), the Research Agent uses its `discover_companies` tool to search Tavily for companies in the sector, extract candidate names from search results, classify each as PUBLIC or PRIVATE via YFinance, verify private companies, and filter by the requested type. Discovery failures (rejected candidates, unverified companies) are handled silently — neither the Research Agent nor the Coordinator reports them to the user. The successfully discovered companies then enter the standard pipeline below as if the user had named them explicitly.
1. **Research** — Coordinator delegates to Research Agent, which classifies companies via `validate_companies` (or uses the already-classified results from discovery), then gathers comprehensive data using Tavily + YFinance for public companies and Tavily-only for private companies (general info, financials, news, negative news/lawsuits/regulatory issues)
2. **Parallel Analysis** — Coordinator delegates to the Analysis Team (a `TeamMode.broadcast` sub-team), which runs Analyst Agent and Critic Agent **concurrently**. Both receive the research data (via `share_member_interactions=True` on the outer team) and produce their specialized outputs in parallel: `FinancialAnalysis` and `RiskAssessment`
3. **Decision** — Coordinator delegates to Decision Agent, which receives the combined financial analysis and risk assessment (via `share_member_interactions=True`) and produces a typed `InvestmentDecision` with per-company BUY/HOLD/SELL recommendations, top pick, investment thesis, and key conditions
4. **Final Memo** — Coordinator synthesizes all specialist outputs into a markdown investment memo, using the Decision Agent's recommendations as the basis for the Investment Decisions and Top Pick sections


## Tools

| Tool | Module | Used By | Purpose |
|------|--------|---------|---------|
| **TavilyTools** | `app/tools/search.py` | Research Agent | Web search for company news, products, competitive position, lawsuits, regulatory issues |
| **YFinanceTools** | `app/tools/finance.py` | Research Agent | Stock prices, market cap, P/E ratio, analyst recommendations, company info, financial news |
| **CompanyValidationTool** | `app/tools/ticker_validation.py` | Research Agent | Classifies identifiers as public (via YFinance) or private companies, verifies private companies via Tavily web search with confidence scoring. Also discovers companies in a sector/niche when users don't provide specific names |

All tools are configured in `app/tools/` and imported by the Research Agent. Tavily and YFinance tools are wrapped with resilient subclasses (`ResilientTavilyTools`, `ResilientYFinanceTools` in `app/tools/resilient_wrappers.py`) that add retry with exponential backoff and a circuit breaker. The Analyst and Critic agents have no tools — they perform pure reasoning on the research data passed to them by the coordinator.

## Typed State (Pydantic Models)

All agent inputs/outputs use strongly typed Pydantic models defined in `app/models/schemas.py`:

### Research Agent Output
- **`CompanyResearch`** — Single company data: company_name, company_type (`PUBLIC`/`PRIVATE`), ticker (optional, null for private companies), sector, public-company financials (current_price, market_cap, pe_ratio, revenue_growth, analyst_consensus), private-company fields (latest_funding_round, total_funding, latest_valuation, key_investors, estimated_revenue, funding_stage), verification fields (verification_status, confidence_score), and shared fields (recent_news, key_products, competitive_position, negative_news)
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

All retry attempts and circuit breaker state changes are logged via Python's `logging` module (`investment_team.tools` logger) with structured fields (`event`, `tool`, `error_type`, `attempts`). Each tool call is also recorded in the `ToolMetricsCollector` with wall-clock duration, success/failure, attempt count, and error details (see Observability section).

**Implementation:** `app/tools/resilient_wrappers.py` (CircuitBreaker class, `_resilient_method` wrapper, `_is_error_response` detector). Tool factories in `app/tools/search.py` and `app/tools/finance.py` return the resilient subclasses.

**Tests:** `TestCircuitBreaker`, `TestIsErrorResponse`, `TestResilientMethod`, `TestResilientMethodMetrics`, `TestResilientToolsIntegration` in `app/tests/test_resilience.py` — 26 tests covering breaker lifecycle (closed → open → half-open → closed), error-string detection, retry behavior, tool metric recording, timeline event emission, and integration with the tool factories.

### Scenario 3: Malformed user input — company classification & verification

`CompanyValidationTool` classifies and verifies every identifier before research begins. **Stage 1 — Classify:** Each identifier is resolved against YFinance via direct ticker lookup then fuzzy name search (handling typos like `Appel` → `AAPL`). Matches are classified as PUBLIC with a resolved ticker; non-matches are classified as PRIVATE. **Stage 2 — Verify private companies:** Private companies are verified via Tavily web search with a confidence score from four signals (result count, relevance, name match frequency, source quality). Companies score ≥ 0.4 are VERIFIED; below are UNVERIFIED with a hallucination warning. Public companies use YFinance + Tavily; private companies use Tavily-only; unverified companies proceed with a prominent warning.

**Implementation:** `CompanyValidationTool` in `app/tools/ticker_validation.py`, added as the 3rd tool on the Research Agent.

**Tests:** 11 tests in `app/tests/test_resilience.py` (classification, fuzzy matching, edge cases); 19 tests in `app/tests/test_verification.py` (confidence scoring, verification statuses, integration).

### Scenario 4: Company discovery — sector-based search with name extraction & filtering

`discover_companies` lets users find companies by sector (e.g., "find 3 AI startups in autonomous driving") instead of providing explicit names. A year-biased Tavily query surfaces recent companies, then candidate names are extracted from the AI answer and titles using regex with weighted scoring (answer text 2×, titles 1×), stop-word filtering, and deduplication (capped at 10). Each candidate is classified via the same YFinance pipeline as Scenario 3, filtered by requested type (PUBLIC/PRIVATE), and private candidates must pass Tavily verification to be included. Discovery failures are handled silently — the user sees only successfully discovered companies in the final memo.

**Implementation:** `discover_companies` and `_extract_company_names` in `app/tools/ticker_validation.py`. Discovery instructions in `app/agents/research.py` (STEP 0a) and `app/team/investment_team.py`.

**Tests:** `app/tests/test_discovery.py` — 21 tests covering name extraction (7), discovery pipeline (12), and tool registration (2).

## Observability and Instrumentation

The system provides structured, multi-layer observability via `app/observability.py`. It uses Python's `logging` module with two handlers (stderr for human-readable output, `logs/events.jsonl` for structured JSON). Each workflow run gets a unique **trace ID** (via `contextvars`) that propagates through all log records, tool calls, and the final JSONL metrics entry for end-to-end correlation. A **`ToolMetricsCollector`** records every tool invocation (name, duration, success, retry attempts, error) and produces per-tool aggregated stats in the final report. An **`EventTimeline`** accumulates timestamped events (agent starts/completions, tool calls, retries, circuit breaker trips, errors) into a chronological sequence for debugging. Errors are auto-categorized (`timeout`, `rate_limit`, `circuit_breaker`, `validation_error`, `api_error`, `unknown`) via `categorize_error()` and tagged on log records and timeline events. The team post-hook produces a comprehensive observability report (trace ID, per-agent breakdown, tool call stats, timeline) printed to stderr and written to `logs/metrics.jsonl`.

**Implementation:** `app/observability.py`, `app/tools/resilient_wrappers.py`, `app/team/investment_team.py`. **Tests:** 64 tests in `app/tests/test_observability.py` + 7 tests in `TestResilientMethodMetrics` (`app/tests/test_resilience.py`).

## File Structure

```
app/
  __init__.py
  playground.py              # Agno Playground server (port 7777)
  config.py                  # Gemini model config via env vars
  observability.py           # Structured logging, trace IDs, tool metrics, event timeline
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
    ticker_validation.py     # Ticker validation + company discovery tool
  tests/
    __init__.py
    test_schemas.py          # Pydantic model serialization + validation tests
    test_workflow.py         # Agent/Team creation + retry config tests
    test_resilience.py       # Circuit breaker, retry, ticker validation tests
    test_discovery.py        # Company discovery + name extraction tests
examples/
    sample_memo.md           # Example output artifact
scripts/
    save_example_output.py   # Script to run examples, then saved to examples/
pyproject.toml               # Dependencies
.env.example                 # Environment variable template
README.md                    # Project documentation
design.md                    # This file
```

## How to Run

### Prerequisites

- Python 3.11+
- Google Gemini API key — get one free at https://aistudio.google.com
- Tavily API key - get one free at https://app.tavily.com/home

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

### Demo Prompts

Enter one of these in the Playground chat:

> Analyze NVDA, AMD, and INTC in the Semiconductors sector and produce an investment memo

> Analyze Nvidia, AMD, and Intel in the Semiconductors sector and produce an investment memo

> Find 3 AI startups in autonomous driving and compare them

> Search for 2 public companies in cloud computing and compare

The first prompt uses direct company identifiers. The second and third use the **discovery** feature — the Research Agent searches for companies in the sector, classifies and verifies them, then proceeds with the standard pipeline. The coordinator will delegate to Research → Analysis Team (Analyst + Critic in parallel) → Decision, then synthesize the final memo. Each specialist's work is visible in the UI.

### Run Tests

```bash
# Unit tests only (fast, no API keys needed)
pytest app/tests/ -v -m "not e2e"

# End-to-end integration test (requires API keys, ~2 minutes)
pytest app/tests/test_e2e.py -v -s
```

Expected: 209 tests pass (51 schema tests + 9 agent/team creation tests + 64 observability tests + 41 resilience tests + 23 verification tests + 21 discovery tests).