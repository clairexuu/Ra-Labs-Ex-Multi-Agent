# Build Notes

- I used Claude Code for architecture planning which gave me a minimum scaffold to start with, super helpful 
- Based on the minimum architecture Claude proposed, I added the different agents, what each does, and how they interact with each other. Then I had claude implement each one by one, given my detailed design. 
- I decided Analyst/Critic/Decision agents should have zero tools (pure reasoning only) to reduce hallucination and research is done by Research Agent
- Claude helped the most finding two that Agno API framework's actual parameter names differ from documentation examples
- Claude hallucinated Agno API framework's parameter name at first: `response_model` vs `output_schema`, `stock_price` vs `enable_stock_price`, `leader` not being a valid Team param, `show_tool_calls` not valid on Agent. I had to navigate to Agno source code to find out
- Claude implemented the company name extractor during discovery mode to pulled generic terms ("Leading", "AI", "Startup") as company names which does not give us "good" companies to compare.  I added a stop-word list and refined the regex to handle cases like `Pony.ai`
- Manual end-to-end testing through the Playground UI caught issues Claude written tests missed: coordinator print discovery rejections to UI, return raw JSON, etc
- I used separate chat windows per component so that context is focused
