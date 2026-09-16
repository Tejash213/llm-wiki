"""
src/skillopt/llm_bridge.py — SkillOpt optimizer LLM calls.

Routes all optimizer calls through the Antigravity IDE via the shared
call_llm() function in src/llm_client.py.

When config.SKILLOPT_BACKEND == "interactive" (the default):
  • The prompt is sent to the Antigravity chat pane via agentapi.bat.
  • SkillOpt pauses and waits for you to paste the AI's response into the
    terminal.  The pasted JSON is returned for parsing.

No API keys are needed.  The Antigravity IDE is the sole LLM backend.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.llm_client import call_llm


def call_optimizer_llm(
    system: str,
    user: str,
    max_tokens: int = 2048,
) -> str:
    """
    Run an optimizer call (reflection / merge / slow-update) through
    the Antigravity IDE.

    In interactive mode (default):
      1. The combined system+user prompt is sent to the Antigravity chat pane.
      2. Execution pauses while you read the AI's response there.
      3. Paste the response into the terminal and press ENTER on a blank line.
      4. The pasted text is returned for JSON parsing.
    """
    return call_llm(system, user, max_tokens=max_tokens)
