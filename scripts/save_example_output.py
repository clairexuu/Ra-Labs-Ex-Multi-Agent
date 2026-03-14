"""Run the investment team workflow and save the output memo to data/examples/.

Usage:
    python scripts/save_example_output.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.team.investment_team import create_investment_team

DEMO_PROMPT = (
    "Analyze NVDA, AMD, and INTC in the Semiconductors sector "
    "and produce an investment memo"
)

# Alternative prompt for private companies:
# DEMO_PROMPT = (
#     "Analyze Anthropic, OpenAI, and Cohere in the AI sector "
#     "and produce an investment memo"
# )

OUTPUT_PATH = Path("examples/sample_memo.md")


def main():
    print(f"Running investment team with prompt:\n  {DEMO_PROMPT}\n")

    team = create_investment_team()
    result = team.run(DEMO_PROMPT)

    if result.content is None or len(result.content) < 100:
        print("ERROR: Workflow produced no meaningful output.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(result.content)
    print(f"\nMemo saved to {OUTPUT_PATH} ({len(result.content)} characters)")


if __name__ == "__main__":
    main()
