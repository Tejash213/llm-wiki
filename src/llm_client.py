"""
LLM client — powered by the Antigravity IDE CLI.

Two operating modes:

1. agentapi (fire-and-forget) — original default for interactive query / wiki gen.
   Sends the prompt to the Antigravity IDE chat pane via agentapi.bat.
   Returns a placeholder string; the AI answers appear in the chat pane.

2. interactive (SkillOpt mode) — no API key required.
   Sends the prompt to the Antigravity chat pane, then PAUSES and waits for
   you to paste the AI's response back into this terminal.
   The pasted text is returned as a real string so SkillOpt can parse it.

   Workflow:
     • SkillOpt prints the prompt → agentapi.bat sends it to the chat pane.
     • For prompts that exceed the Windows command-line limit, the prompt is
       written to  wiki/_prompt.txt  instead — open that file, copy it, and
       paste it into the Antigravity chat manually.
     • After the AI responds in the chat pane, copy its reply and paste it
       into this terminal, then press ENTER on a blank line to continue.

Mode is set by  config.SKILLOPT_BACKEND:
    "interactive" — SkillOpt interactive bridge (default)
    "agentapi"    — fire-and-forget (no response capture)

Usage: just call  call_llm(system_prompt, user_prompt)  as before.
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


# ── Locate agentapi.bat ───────────────────────────────────────────────────────

def _find_agentapi() -> str | None:
    """Return the full path to agentapi.bat, or None if not found."""
    gemini_bin = os.path.join(
        os.path.expanduser("~"), ".gemini", "antigravity-ide", "bin", "agentapi.bat"
    )
    if os.path.isfile(gemini_bin):
        return gemini_bin
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(p, "agentapi.bat")
        if os.path.isfile(candidate):
            return candidate
    return None


_AGENTAPI = _find_agentapi()
_CONV_ID  = (os.environ.get("ANTIGRAVITY_TRAJECTORY_ID") or
             os.environ.get("ANTIGRAVITY_CONVERSATION_ID") or "")


# ── agentapi.bat send helpers ─────────────────────────────────────────────────

def _agentapi_send(text: str) -> bool:
    """
    Try to send `text` via agentapi.bat send-message.
    Returns True on success, False on failure (e.g. text too long, no agentapi).
    """
    if not _AGENTAPI or not _CONV_ID:
        return False
    if len(text) > config.AGENTAPI_MAX_CHARS:
        return False   # Caller will fall back to file-based delivery
    try:
        result = subprocess.run(
            [_AGENTAPI, "send-message", _CONV_ID, text],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _deliver_prompt(full_prompt: str) -> str:
    """
    Deliver `full_prompt` to the Antigravity chat pane as reliably as possible.
    Returns a human-readable string describing HOW it was delivered (for the
    terminal message shown to the user).
    """
    if _agentapi_send(full_prompt):
        return "Antigravity chat pane (sent automatically via agentapi)"

    # Prompt too long or agentapi unavailable → write to file
    os.makedirs(os.path.dirname(config.SKILLOPT_PROMPT_FILE), exist_ok=True)
    with open(config.SKILLOPT_PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(full_prompt)

    # Try sending a short summary notice via agentapi so the chat pane
    # shows a hint about the pending prompt file.
    notice = (
        f"[SkillOpt] The full prompt is in:\n"
        f"  {config.SKILLOPT_PROMPT_FILE}\n\n"
        f"Please open that file, copy its contents, paste here, and respond."
    )
    _agentapi_send(notice)

    return f"file  →  {config.SKILLOPT_PROMPT_FILE}  (prompt too long for direct send)"


# ── Multi-line paste collector ────────────────────────────────────────────────

def _collect_paste(label: str = "AI response") -> str:
    """
    Interactive: wait for the user to paste multi-line text into the terminal.
    Ends when the user presses ENTER on an otherwise blank line.
    Returns the pasted text as a single string.
    """
    print(f"\n{'─' * 60}")
    print(f"  Paste the {label} from the Antigravity chat pane below.")
    print(f"  Then press ENTER on a blank line to continue.")
    print(f"{'─' * 60}")

    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        # A blank line *after* we have content signals end-of-paste
        if not line.strip() and lines:
            break
        lines.append(line)

    result = "\n".join(lines).strip()
    print(f"{'─' * 60}")
    print(f"  [✓] Response received ({len(result)} chars)")
    print(f"{'─' * 60}\n")
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = None,
    temperature: float = None,
) -> str:
    """
    Send a prompt and return the LLM response.

    Behaviour depends on  config.SKILLOPT_BACKEND:

    "interactive"  — Sends the prompt to the Antigravity chat pane (or saves it
                     to a file if it's too long), then pauses and waits for you
                     to paste the AI's response into this terminal.
                     Returns the pasted response as a real string.
                     Use this mode when running  python main.py --skillopt.

    "agentapi"     — Fire-and-forget: sends the prompt and returns a placeholder.
                     The AI responds in the chat pane; the response is NOT captured.
                     Use this mode for normal interactive query / wiki generation.
    """
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    backend     = getattr(config, "SKILLOPT_BACKEND", "agentapi")

    # ── Interactive bridge mode (SkillOpt) ─────────────────────────────────────
    if backend == "interactive":
        delivery = _deliver_prompt(full_prompt)
        print(f"\n  [SkillOpt] Prompt delivered via: {delivery}")
        return _collect_paste()

    # ── Fire-and-forget mode (normal usage) ───────────────────────────────────
    if not _AGENTAPI:
        raise RuntimeError(
            "agentapi.bat not found — make sure you are running inside "
            "the Antigravity IDE terminal."
        )
    if not _CONV_ID:
        raise RuntimeError(
            "ANTIGRAVITY_TRAJECTORY_ID not set — run this script from the "
            "Antigravity IDE terminal."
        )
    sent = _agentapi_send(full_prompt)
    if not sent:
        # Fallback: truncate to fit command-line limit
        short = full_prompt[:config.AGENTAPI_MAX_CHARS] + "\n...[truncated]"
        result = subprocess.run(
            [_AGENTAPI, "send-message", _CONV_ID, short],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"agentapi send-message failed: {result.stderr.strip()}")
    return "\n[✓] Query sent to Antigravity AI — see the Antigravity chat pane.\n"


# Aliases (used by generate_wiki, crosslink, update — kept for compatibility)
call_llm_generate  = call_llm
call_llm_query     = call_llm
call_llm_crosslink = call_llm
