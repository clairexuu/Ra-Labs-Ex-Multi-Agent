"""Run the investment team workflow and save the output memos to examples/.

Usage:
    python scripts/save_example_output.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.team.investment_team import create_investment_team

PROMPTS = [
    (
        "Analyze NVDA, AMD, and INTC in the Semiconductors sector "
        "and produce an investment memo",
        Path("examples/sample_memo_given_public.md"),
    ),
    (
        "Find 3 AI startups in autonomous driving and compare them",
        Path("examples/sample_memo_search_private.md"),
    ),
    (
        "Search for 3 public companies in cloud computing and compare",
        Path("examples/sample_memo_search_public.md"),
    ),
]


def main():
    team = create_investment_team()

    for prompt, output_path in PROMPTS:
        print(f"Running investment team with prompt:\n  {prompt}\n")

        result = team.run(prompt)

        if result.content is None or len(result.content) < 100:
            print(
                f"ERROR: Workflow produced no meaningful output for: {prompt}",
                file=sys.stderr,
            )
            sys.exit(1)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.content)
        print(f"Memo saved to {output_path} ({len(result.content)} characters)\n")

    print("All memos saved successfully.")


if __name__ == "__main__":
    main()
