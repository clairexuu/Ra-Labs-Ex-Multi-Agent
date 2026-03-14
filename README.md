# Investment Team - Multi-Agent Analysis System

## Agent Architecture

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
                   │Research Agent│  Specialist #1
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

## Agent Roles

| Requirement | Agent | Description |
|-------------|-------|-------------|
| coordinating agent | **Investment Committee Lead** (Team coordinator) | Orchestrates the workflow sequence, collects all specialist outputs, and synthesizes the final investment memo |
| Specialist #1 | **Research Agent** | Comprehensive data gathering using Tavily (web search) and YFinance (financial data). Collects general info, financials, news, and negative news for all downstream agents |
| Specialist #2 | **Analyst Agent** | Pure-reasoning agent that produces comparative financial analysis from the research data: strengths, weaknesses, valuation assessment, growth outlook, and top pick. Runs concurrently with Critic via broadcast sub-team |
| Specialist #3 | **Critic/Risk Agent** | Pure-reasoning agent that identifies risks, challenges assumptions, finds data gaps, and provides a contrarian argument based on the research data. Runs concurrently with Analyst via broadcast sub-team |
| Specialist #4 | **Decision Agent** | Pure-reasoning agent that synthesizes the Analyst's findings and Critic's risks into explicit BUY/HOLD/SELL decisions for each company, identifies the top pick, and states the investment thesis |
| output/review step | **Investment Committee Lead** | Same coordinator agent collects all outputs and composes the structured final memo |

## Tools

| Tool | Module | Used By | Purpose |
|------|--------|---------|---------|
| **TavilyTools** | `app/tools/search.py` | Research Agent | Web search for company news, products, competitive position, lawsuits, regulatory issues |
| **YFinanceTools** | `app/tools/finance.py` | Research Agent | Stock prices, market cap, P/E ratio, analyst recommendations, company info, financial news |
| **CompanyValidationTool** | `app/tools/ticker_validation.py` | Research Agent | Classifies identifiers as public (via YFinance) or private companies, verifies private companies via Tavily web search with confidence scoring. Also discovers companies in a sector/niche when users don't provide specific names |

## AI-assisted coding
I used Claude to build this project. I started by designing the rough architecture in one chat window, then opened separate chat windows for each component (agents, tools, schemas, resilience, and tests) so that context is focused and not overwhelmed. For each component, I described the desired behavior and constraints, reviewed the generated code, and revised where needed. I used Claude to write unit tests and e2e tests, then did several rounds of manual testing through the UI. When I found bugs or limitations, I went back to the architecture, refined the design, and had Claude implement the changes.

## Tradeoffs and Known Limitations

- Validate searched companies across multiple platforms to avoid hallucination
- Show more informative status updates in the UI during the agent workflow, e.g., searching for company, doing research, analyzing, finding risks, writing memo
- Allow the Critic agent to reject an Analyst's output with specific feedback, sending it back for a repair iteration