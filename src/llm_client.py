"""
LLM client - Azure OpenAI primary backend; Antigravity IDE bridge as fallback.

Priority order for every call_llm() call:
  1. Azure OpenAI API  - if AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT are
                         present in .env  (this is the default when credentials are set).
  2. Interactive bridge - SkillOpt paste mode (config.SKILLOPT_BACKEND = "interactive").
  3. agentapi.bat      - Antigravity fire-and-forget (legacy fallback).

Credentials are loaded from .env at project root.  Never hard-code them here.

Note: This endpoint uses max_completion_tokens instead of max_tokens.
"""

import os
import sys
import subprocess
import requests as _requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


# -- Locate agentapi.bat --

def _find_agentapi():
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


# -- Load .env credentials --

def _load_env():
    """Load variables from .env into os.environ."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.isfile(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        # Manual parse fallback
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val


_load_env()

_AZURE_API_KEY    = os.environ.get("AZURE_OPENAI_API_KEY", "")
_AZURE_ENDPOINT   = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
_AZURE_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini-2")
_AZURE_API_VER    = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

_USE_AZURE = bool(_AZURE_API_KEY and _AZURE_ENDPOINT)


# -- Azure OpenAI direct REST call --

def _call_azure(system_prompt, user_prompt, max_tokens=None, temperature=0.3):
    """
    Call Azure OpenAI via REST API using requests.
    Uses max_completion_tokens (required by this model/endpoint).
    For reasoning models (like gpt-5-mini-2), reasoning tokens count towards this limit,
    so we ensure a minimum floor of 4096 tokens, default to 16384, and use reasoning_effort='low'.
    """
    default_tokens = getattr(config, "MAX_TOKENS_GENERATE", 16384)
    effective_tokens = max(max_tokens or default_tokens, 4096)
    reasoning_effort = getattr(config, "REASONING_EFFORT", "low")

    url = (
        f"{_AZURE_ENDPOINT}/openai/deployments/{_AZURE_DEPLOYMENT}"
        f"/chat/completions?api-version={_AZURE_API_VER}"
    )
    headers = {
        "api-key": _AZURE_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_completion_tokens": effective_tokens,
        "reasoning_effort": reasoning_effort,
    }

    try:
        resp = _requests.post(url, json=body, headers=headers, timeout=180)
    except _requests.exceptions.Timeout:
        raise RuntimeError("Azure OpenAI request timed out (180s)")
    except _requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Azure OpenAI connection error: {e}")

    if resp.status_code != 200:
        raise RuntimeError(
            f"Azure OpenAI error {resp.status_code}: {resp.text[:400]}"
        )

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
        return content or ""
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Azure OpenAI response shape: {e}\n{data}")


# -- agentapi helpers (legacy) --

def _agentapi_send(text):
    if not _AGENTAPI or not _CONV_ID:
        return False
    if len(text) > config.AGENTAPI_MAX_CHARS:
        return False
    try:
        result = subprocess.run(
            [_AGENTAPI, "send-message", _CONV_ID, text],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _deliver_prompt(full_prompt):
    if _agentapi_send(full_prompt):
        return "Antigravity chat pane (sent automatically via agentapi)"
    os.makedirs(os.path.dirname(config.SKILLOPT_PROMPT_FILE), exist_ok=True)
    with open(config.SKILLOPT_PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(full_prompt)
    notice = (
        "[SkillOpt] The full prompt is in:\n"
        f"  {config.SKILLOPT_PROMPT_FILE}\n\n"
        "Please open that file, copy its contents, paste here, and respond."
    )
    _agentapi_send(notice)
    return f"file  ->  {config.SKILLOPT_PROMPT_FILE}  (prompt too long for direct send)"


# -- Multi-line paste collector (SkillOpt interactive mode) --

def _collect_paste(label="AI response"):
    sep = "-" * 60
    print(f"\n{sep}")
    print(f"  Paste the {label} from the Antigravity chat pane below.")
    print(f"  Then press ENTER on a blank line to continue.")
    print(sep)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip() and lines:
            break
        lines.append(line)
    result = "\n".join(lines).strip()
    print(f"  [OK] Response received ({len(result)} chars)\n")
    return result


# -- Public API --

def call_llm(system_prompt, user_prompt, max_tokens=None, temperature=None):
    """
    Send a prompt and return the LLM response as a string.

    Priority:
      1. Azure OpenAI  (when .env has AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT)
      2. SkillOpt interactive bridge  (config.SKILLOPT_BACKEND == "interactive")
      3. Antigravity agentapi fire-and-forget  (legacy)
    """
    _max_tokens  = max_tokens  if max_tokens  is not None else config.MAX_TOKENS_GENERATE
    _temperature = temperature if temperature is not None else config.TEMPERATURE

    # 1. Azure OpenAI (primary)
    if _USE_AZURE:
        return _call_azure(system_prompt, user_prompt, _max_tokens, _temperature)

    # 2. Interactive bridge (SkillOpt, no API key needed)
    backend = getattr(config, "SKILLOPT_BACKEND", "agentapi")
    if backend == "interactive":
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
        delivery = _deliver_prompt(full_prompt)
        print(f"\n  [SkillOpt] Prompt delivered via: {delivery}")
        return _collect_paste()

    # 3. Antigravity agentapi (legacy fire-and-forget)
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    if not _AGENTAPI:
        raise RuntimeError(
            "No Azure credentials found in .env AND agentapi.bat not found.\n"
            "Add AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT to .env and retry."
        )
    if not _CONV_ID:
        raise RuntimeError(
            "No Azure credentials in .env AND ANTIGRAVITY_TRAJECTORY_ID not set.\n"
            "Add AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT to .env and retry."
        )
    sent = _agentapi_send(full_prompt)
    if not sent:
        short = full_prompt[:config.AGENTAPI_MAX_CHARS] + "\n...[truncated]"
        result = subprocess.run(
            [_AGENTAPI, "send-message", _CONV_ID, short],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"agentapi send-message failed: {result.stderr.strip()}")
    return "\n[OK] Query sent to Antigravity AI - see the Antigravity chat pane.\n"


# Aliases - kept for compatibility with generate_wiki, crosslink, update, query
call_llm_generate  = call_llm
call_llm_query     = call_llm
call_llm_crosslink = call_llm
