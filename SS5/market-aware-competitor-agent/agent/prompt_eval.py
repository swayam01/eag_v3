"""Run the Prompt Evaluation Assistant rubric against our system prompt.

The Prompt Evaluation Assistant (see PROMPT_EVAL.md) reviews a candidate
prompt and emits a structured JSON verdict over 9 criteria. This script
loads the rendered system instruction, sends it to Gemini in the role of
the evaluator, and prints the verdict.

Use:
    uv run prompt-eval                  # uses the default global market config
    uv run prompt-eval --market-config markets/india_b2c_interior.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types as gtypes
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from agent.market_config import add_market_flags, load_market_config
from agent.run_agent import _build_system_instruction

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

console = Console()

EVALUATOR_INSTRUCTION = """You are a Prompt Evaluation Assistant.

You will receive a prompt written by a student. Your job is to review this
prompt and assess how well it supports structured, step-by-step reasoning
in an LLM (e.g., for math, logic, planning, or tool use).

Evaluate the prompt on the following criteria:

1. Explicit Reasoning Instructions
2. Structured Output Format
3. Separation of Reasoning and Tools
4. Conversation Loop Support
5. Instructional Framing
6. Internal Self-Checks
7. Reasoning Type Awareness
8. Error Handling or Fallbacks
9. Overall Clarity and Robustness

Respond with a structured review in this JSON format and NOTHING ELSE
(no markdown fences, no commentary):

{
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": false,
  "reasoning_type_awareness": false,
  "fallbacks": false,
  "overall_clarity": "..."
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the agent system prompt against the Prompt Evaluation Assistant rubric.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "PROMPT_EVAL.json",
        help="Where to save the JSON verdict (also printed to stdout).",
    )
    add_market_flags(parser)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]GEMINI_API_KEY missing.[/] Copy .env.example → .env and fill it in.")
        sys.exit(2)

    market = load_market_config(args)
    system_prompt = _build_system_instruction(market)

    console.print(
        Panel(
            f"Length: {len(system_prompt)} chars\nMarket: {market.to_brief()}",
            title="Prompt under review",
            border_style="cyan",
        )
    )

    model = os.environ.get("PROMPT_EVAL_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[
            gtypes.Content(
                role="user",
                parts=[gtypes.Part.from_text(text=f"Prompt to evaluate:\n\n{system_prompt}")],
            )
        ],
        config=gtypes.GenerateContentConfig(
            system_instruction=EVALUATOR_INSTRUCTION,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    text = (response.text or "").strip()
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        console.print("[red]Evaluator did not return valid JSON; printing raw text.[/]")
        console.print(text)
        sys.exit(1)

    args.out.write_text(json.dumps(verdict, indent=2) + "\n")
    console.print(
        Panel(
            Syntax(json.dumps(verdict, indent=2), "json"),
            title=f"Verdict (saved to {args.out.name})",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
