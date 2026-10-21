"""
Configuration for the Karpathy Wiki pipeline.
All LLM calls go through the Antigravity IDE CLI — no external API keys required.

SkillOpt works in "interactive bridge" mode:
  - Each optimizer prompt is sent to the Antigravity chat pane via agentapi.bat.
  - SkillOpt then pauses and waits for you to paste the AI's response back into
    the terminal.  The pasted response is parsed as structured JSON and used for
    scoring / edit proposals — no API key needed.
"""

import os

# ── Paths ─────────────────────────────────────────────────────────────────────
DOCUMENTS_DIR = r"C:\Users\TrevorSingaladevi\Downloads\FutureSense Individual Documents for Knowledge Source 2026-02-25"
WIKI_DIR      = os.path.join(os.path.dirname(__file__), "wiki")
PROCESSED_LOG = os.path.join(WIKI_DIR, "_processed.json")

# ── Generation settings ───────────────────────────────────────────────────────
MAX_TOKENS_GENERATE = 16384
MAX_TOKENS_QUERY    = 4096
TEMPERATURE         = 0.3
DOC_CHUNK_CHARS     = 10000
REASONING_EFFORT    = "low"   # "low" | "medium" | "high" for Azure reasoning models

# ── SkillOpt paths ────────────────────────────────────────────────────────────
SKILL_PATH    = os.path.join(WIKI_DIR, "best_skill.md")
SKILLOPT_LOG  = os.path.join(WIKI_DIR, "_skillopt_log.json")
SKILLOPT_PROMPT_FILE = os.path.join(WIKI_DIR, "_prompt.txt")  # for long prompts

# ── SkillOpt backend ──────────────────────────────────────────────────────────
# "interactive" — send via agentapi.bat, then pause and wait for you to paste
#                 the AI response back into the terminal.  No API key needed.
# "agentapi"   — fire-and-forget via agentapi.bat (original non-SkillOpt mode;
#                 responses are not captured, so SkillOpt edits will be empty).
SKILLOPT_BACKEND = "interactive"

# Max characters to send in a single agentapi.bat command-line argument.
# Prompts longer than this are written to SKILLOPT_PROMPT_FILE instead.
AGENTAPI_MAX_CHARS = 4000
