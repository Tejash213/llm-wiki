"""
src/skillopt/reflection.py — Backward pass: minibatch reflection and edit proposal.

The optimizer LLM receives:
  - The current skill document.
  - A minibatch of trajectory summaries (successes and failures).
  - The rejected-edit buffer from earlier in the epoch.

It returns structured ADD / DELETE / REPLACE edits.

Local merge then:
  1. Consolidates failure-driven edits and success-driven edits separately.
  2. Combines them (failure corrections take priority).
  3. Deduplicates and resolves conflicts.
  4. Ranks by score and clips to the edit budget.
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.skillopt.skill_state import Edit


# ── Optimizer prompts ─────────────────────────────────────────────────────────

_REFLECT_SYSTEM = """\
You are an expert wiki-generation skill optimizer.

You will receive:
1. The CURRENT skill document — the system prompt used by the wiki agent.
2. A set of FAILURE trajectories — documents where the agent produced poor wiki pages.
3. A set of SUCCESS trajectories — documents where the agent produced good wiki pages.
4. A REJECTED-EDIT BUFFER — edits tried earlier this epoch that hurt performance.

Your task: propose bounded ADD / DELETE / REPLACE edits to the skill document that:
- Fix recurring failure patterns seen across multiple failure trajectories.
- Preserve behaviours that led to successes.
- Avoid edits that are already in the rejected-edit buffer.

Return ONLY valid JSON — no markdown fences, no commentary:
{
  "edits": [
    {
      "type": "ADD",
      "target": "<heading or anchor text to insert after — use empty string to append>",
      "content": "<new content to add>",
      "score": <float 0-1, your confidence this edit will help>,
      "source": "failure"
    },
    {
      "type": "DELETE",
      "target": "<exact text to remove from the skill>",
      "content": "",
      "score": <float 0-1>,
      "source": "failure"
    },
    {
      "type": "REPLACE",
      "target": "<exact text to replace>",
      "content": "<replacement text>",
      "score": <float 0-1>,
      "source": "failure"
    }
  ],
  "analysis": "<one-paragraph summary of failure patterns and proposed fixes>"
}
"""

_MERGE_SYSTEM = """\
You are a skill-edit consolidator.

You will receive two lists of proposed edits:
  A) Failure-driven edits — aimed at fixing problems.
  B) Success-driven edits — aimed at preserving good behaviour.

Your task:
1. Merge the two lists into a single ranked list.
2. Remove duplicate or contradictory edits (keep the higher-score one).
3. Prioritize failure corrections over success preservation if they conflict.
4. Return ONLY valid JSON:
{
  "merged_edits": [ <same edit objects, ranked by score descending> ]
}
"""

_SLOW_UPDATE_SYSTEM = """\
You are an epoch-level wiki-skill advisor.

You will receive:
1. The PREVIOUS epoch's skill document.
2. The CURRENT epoch's skill document.
3. A comparison of task outcomes: improvements, regressions, persistent failures,
   stable successes.

Write a concise guidance block (100-200 words) summarizing:
- Which procedural changes helped across the epoch.
- Which failure patterns persist and need continued attention.
- What to preserve in future edits.

This block will be inserted into a protected section of the skill document.
Return ONLY the guidance text (no JSON, no headings).
"""


# ── Trajectory summarizer ─────────────────────────────────────────────────────

def _summarize_trajectory(traj, max_chars: int = 800) -> str:
    """Compact text representation of one trajectory for the optimizer prompt."""
    lines = [f"Document: {traj.doc_filename}",
             f"Score: {traj.score:.3f}"]
    if traj.subscores:
        lines.append("Subscores: " + ", ".join(
            f"{k}={v}" for k, v in traj.subscores.items() if k != "n_pages"
        ))
    lines.append(f"Pages created: {len(traj.pages_created)}")
    if traj.pages_created:
        titles = [p.get("title", "?") for p in traj.pages_created[:5]]
        lines.append("Titles: " + ", ".join(titles))
    if traj.error:
        lines.append(f"Error: {traj.error}")
    return "\n".join(lines)[:max_chars]


def _format_rejected_buffer(buffer: list[dict], max_items: int = 10) -> str:
    if not buffer:
        return "(none)"
    items = buffer[-max_items:]
    parts = []
    for item in items:
        e = item.get("edit", {})
        parts.append(
            f"- [{e.get('type','?')}] target='{e.get('target','')[:60]}' "
            f"→ score_drop={item.get('score_drop', '?')}"
        )
    return "\n".join(parts)


# ── LLM call wrapper ──────────────────────────────────────────────────────────

def _call_optimizer(system: str, user: str, max_tokens: int = 2048) -> str:
    """Call the optimizer LLM and return raw text.  Uses skillopt_llm_client."""
    from src.skillopt.llm_bridge import call_optimizer_llm
    return call_optimizer_llm(system, user, max_tokens=max_tokens)


# ── JSON parse helpers ────────────────────────────────────────────────────────

def _parse_edits_json(raw: str) -> list[Edit]:
    """Parse optimizer JSON output into Edit objects; returns [] on failure."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract just the JSON object
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    edits_raw = data.get("edits") or data.get("merged_edits", [])
    edits = []
    for e in edits_raw:
        try:
            edits.append(Edit.from_dict(e))
        except Exception:
            continue
    return edits


# ── Core reflection API ───────────────────────────────────────────────────────

def reflect_minibatch(
    successes: list,
    failures:  list,
    current_skill: str,
    rejected_buffer: list[dict],
    minibatch_size: int = 4,
    max_tokens: int = 2048,
    verbose: bool = True,
) -> tuple[list[Edit], str]:
    """
    Run one reflection minibatch over successes and failures.

    Returns (edit_list, analysis_text).
    """
    # Sample up to minibatch_size from each group
    fail_sample = failures[:minibatch_size]
    succ_sample  = successes[:minibatch_size]

    fail_summaries = "\n\n".join(_summarize_trajectory(t) for t in fail_sample) or "(none)"
    succ_summaries = "\n\n".join(_summarize_trajectory(t) for t in succ_sample)  or "(none)"
    buffer_text    = _format_rejected_buffer(rejected_buffer)

    user_prompt = f"""\
=== CURRENT SKILL DOCUMENT ===
{current_skill}

=== FAILURE TRAJECTORIES ===
{fail_summaries}

=== SUCCESS TRAJECTORIES ===
{succ_summaries}

=== REJECTED-EDIT BUFFER (avoid repeating these) ===
{buffer_text}
"""

    if verbose:
        print(f"      [Reflect] {len(fail_sample)} failures, {len(succ_sample)} successes")

    raw = _call_optimizer(_REFLECT_SYSTEM, user_prompt, max_tokens=max_tokens)
    edits = _parse_edits_json(raw)

    # Extract analysis text
    analysis = ""
    try:
        data = json.loads(raw.strip())
        analysis = data.get("analysis", "")
    except Exception:
        pass

    if verbose:
        print(f"      [Reflect] Proposed {len(edits)} edits")

    return edits, analysis


def merge_edits(
    failure_edits: list[Edit],
    success_edits: list[Edit],
    max_tokens: int = 1024,
    verbose: bool = True,
) -> list[Edit]:
    """
    Hierarchically merge failure-driven and success-driven edits.
    Deduplicates and resolves conflicts via the optimizer LLM.
    """
    if not failure_edits and not success_edits:
        return []

    # Fast path: if one group is empty, just return the other (sorted by score)
    if not failure_edits:
        return sorted(success_edits, key=lambda e: -e.score)
    if not success_edits:
        return sorted(failure_edits, key=lambda e: -e.score)

    failure_json = json.dumps([e.to_dict() for e in failure_edits], indent=2)
    success_json = json.dumps([e.to_dict() for e in success_edits], indent=2)

    user_prompt = f"""\
=== FAILURE-DRIVEN EDITS ===
{failure_json}

=== SUCCESS-DRIVEN EDITS ===
{success_json}
"""

    if verbose:
        print(f"      [Merge] Combining {len(failure_edits)} failure + "
              f"{len(success_edits)} success edits")

    raw    = _call_optimizer(_MERGE_SYSTEM, user_prompt, max_tokens=max_tokens)
    merged = _parse_edits_json(raw)

    if not merged:
        # Fallback: concatenate both lists, failure edits first, sort by score
        combined = failure_edits + success_edits
        combined.sort(key=lambda e: -e.score)
        merged = _deduplicate_edits(combined)

    if verbose:
        print(f"      [Merge] → {len(merged)} unique edits")

    return merged


def _deduplicate_edits(edits: list[Edit]) -> list[Edit]:
    """Remove edits with identical (type, target) pairs, keeping highest score."""
    seen: dict[tuple, Edit] = {}
    for e in edits:
        key = (e.type, e.target[:80])
        if key not in seen or e.score > seen[key].score:
            seen[key] = e
    return sorted(seen.values(), key=lambda e: -e.score)


def rank_and_clip(edits: list[Edit], budget: int) -> list[Edit]:
    """Sort edits by score descending and clip to the edit budget."""
    sorted_edits = sorted(edits, key=lambda e: -e.score)
    return sorted_edits[:budget]


# ── Slow / meta update ────────────────────────────────────────────────────────

def generate_slow_update_block(
    prev_skill: str,
    curr_skill: str,
    improvements: list,
    regressions:  list,
    persistent_failures: list,
    stable_successes: list,
    max_tokens: int = 512,
    verbose: bool = True,
) -> str:
    """
    Ask the optimizer to write a concise cross-epoch guidance block.
    Returns the text to be inserted into the slow-update protected region.
    """
    def _fmt_group(label: str, trajs: list) -> str:
        if not trajs:
            return f"{label}: (none)"
        parts = [f"  {t.doc_filename}: {t.score:.3f}" for t in trajs[:5]]
        return label + ":\n" + "\n".join(parts)

    user_prompt = f"""\
=== PREVIOUS EPOCH SKILL ===
{prev_skill[:1500]}

=== CURRENT EPOCH SKILL ===
{curr_skill[:1500]}

=== OUTCOME COMPARISON ===
{_fmt_group("Improvements (score rose)", improvements)}
{_fmt_group("Regressions (score fell)", regressions)}
{_fmt_group("Persistent failures", persistent_failures)}
{_fmt_group("Stable successes", stable_successes)}
"""

    if verbose:
        print(f"      [SlowUpdate] Generating cross-epoch guidance block...")

    guidance = _call_optimizer(_SLOW_UPDATE_SYSTEM, user_prompt, max_tokens=max_tokens)
    return guidance.strip()
