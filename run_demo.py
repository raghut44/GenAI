"""
run_demo.py

End-to-end demo of the Graph Engineering Agent:
  1. Index examples/sample_repo/billing.py -> build CPG (AST+CFG+DFG)
  2. Slice on the `apply_discount` function (backward slice: everything it
     depends on) and on a specific line (forward slice: everything that
     depends on it)
  3. Print the minimal context block and token savings vs. the full file

Run with:  python run_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.agent.graph_engineering_agent import GraphEngineeringAgent


def banner(text):
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


def report(result):
    print(f"Target: {result.target_description}")
    print(f"File:   {result.filename}")
    print(f"Line ranges selected: {result.line_ranges}")
    print(f"\n--- Minimal context sent to Copilot/LLM ---\n")
    print(result.context)
    print(f"\n--- Token budget ---")
    print(f"Full file tokens:   {result.full_file_tokens}")
    print(f"Sliced context:     {result.sliced_tokens}")
    print(f"Tokens saved:       {result.tokens_saved} ({result.reduction_pct:.1f}% reduction)")


def main():
    agent = GraphEngineeringAgent()
    path = "examples/sample_repo/billing.py"

    banner("SLICE 1: backward slice on function 'apply_discount'")
    result = agent.get_context_for_function(path, "apply_discount", direction="backward")
    report(result)

    banner("SLICE 2: backward slice on the single line `discounted = subtotal * (1 - discount_rate)`")
    # that statement is on line 26 of billing.py
    result2 = agent.get_context_for_line(path, lineno=26, direction="backward")
    report(result2)

    banner("SLICE 3: forward slice from TAX_RATE definition (line 9) -- what does it affect?")
    result3 = agent.get_context_for_line(path, lineno=9, direction="forward")
    report(result3)


if __name__ == "__main__":
    main()
