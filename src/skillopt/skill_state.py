"""
src/skillopt/skill_state.py — Manages the skill document (S_t).

The skill document is a portable Markdown file that acts as the system prompt
for wiki generation.  SkillOpt treats it as an external trainable state:

  S_0  →  edit  →  S_1  →  (validation gate)  →  best_skill.md

Key responsibilities:
  - Load / save skill files.
  - Compute skill hash for deduplication.
  - Apply ADD / DELETE / REPLACE edits in patch mode.
  - Protect the <!-- SLOW_UPDATE --> ... <!-- /SLOW_UPDATE --> fenced region
    from step-level edits (only epoch-wise slow update may write to it).
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal


# ── Edit dataclass ─────────────────────────────────────────────────────────────

@dataclass
class Edit:
    """A single bounded skill edit proposed by the optimizer."""
    type: Literal["ADD", "DELETE", "REPLACE"]
    # For ADD: the section heading after which to insert content.
    # For DELETE / REPLACE: the exact text to find.
    target: str
    # For ADD / REPLACE: the new content.  Empty string for DELETE.
    content: str = ""
    # Confidence score assigned by the optimizer (used for ranking).
    score: float = 1.0
    # Source: "failure" | "success" (for logging / meta-skill)
    source: str = "failure"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "target": self.target,
            "content": self.content,
            "score": self.score,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edit":
        return cls(
            type=d.get("type", "ADD"),
            target=d.get("target", ""),
            content=d.get("content", ""),
            score=float(d.get("score", 1.0)),
            source=d.get("source", "failure"),
        )


# ── Slow-update region fences ──────────────────────────────────────────────────

_SLOW_OPEN  = "<!-- SLOW_UPDATE -->"
_SLOW_CLOSE = "<!-- /SLOW_UPDATE -->"


def _extract_slow_region(skill: str) -> tuple[str, str, str]:
    """Split skill into (before, slow_block, after).  slow_block may be empty."""
    start = skill.find(_SLOW_OPEN)
    end   = skill.find(_SLOW_CLOSE)
    if start == -1 or end == -1 or end < start:
        return skill, "", ""
    slow_block = skill[start: end + len(_SLOW_CLOSE)]
    before     = skill[:start]
    after      = skill[end + len(_SLOW_CLOSE):]
    return before, slow_block, after


def _reassemble_skill(before: str, slow_block: str, after: str) -> str:
    """Re-join the three parts (after applying step-level edits to before+after)."""
    if not slow_block:
        return before + after
    return before + slow_block + after


# ── Core helpers ───────────────────────────────────────────────────────────────

def load_skill(path: str) -> str:
    """Load a skill document from disk.  Returns empty string if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def save_skill(path: str, content: str) -> None:
    """Persist a skill document to disk."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def hash_skill(content: str) -> str:
    """SHA-256 fingerprint of the skill text (for deduplication)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ── Edit application ──────────────────────────────────────────────────────────

def apply_edits(skill_text: str, edits: list[Edit]) -> tuple[str, list[dict]]:
    """
    Apply a list of bounded edits to skill_text, skipping any that would touch
    the protected <!-- SLOW_UPDATE --> region.

    Returns:
        (updated_skill_text, apply_report)
    where apply_report is a list of { edit, status, reason } dicts.
    """
    before, slow_block, after = _extract_slow_region(skill_text)
    # Step-level edits operate on the non-protected body only.
    body = before + after

    report = []

    for edit in edits:
        status = "skipped"
        reason = ""

        if edit.type == "ADD":
            # Append after the target heading, or at end of body if not found.
            if edit.target and edit.target in body:
                idx = body.find(edit.target) + len(edit.target)
                body = body[:idx] + "\n\n" + edit.content.strip() + "\n" + body[idx:]
                status = "applied"
            else:
                # Append to end of body
                body = body.rstrip() + "\n\n" + edit.content.strip() + "\n"
                status = "applied"
                reason = "target heading not found; appended to end"

        elif edit.type == "DELETE":
            if edit.target and edit.target in body:
                body = body.replace(edit.target, "", 1)
                status = "applied"
            else:
                status = "skipped"
                reason = "target text not found"

        elif edit.type == "REPLACE":
            if edit.target and edit.target in body:
                body = body.replace(edit.target, edit.content, 1)
                status = "applied"
            else:
                status = "skipped"
                reason = "target text not found"

        report.append({
            "edit": edit.to_dict(),
            "status": status,
            "reason": reason,
        })

    updated = _reassemble_skill(before, slow_block, after.replace(before + after, body, 1)) \
              if slow_block else body

    # Fallback: if slow_block logic produced no change, use body directly
    if not slow_block:
        updated = body

    return updated.strip() + "\n", report


def write_slow_update(skill_text: str, slow_content: str) -> str:
    """
    Replace (or insert) the <!-- SLOW_UPDATE --> block with slow_content.
    This is the only function that may write to the protected region.
    """
    before, _, after = _extract_slow_region(skill_text)
    slow_block = f"\n{_SLOW_OPEN}\n{slow_content.strip()}\n{_SLOW_CLOSE}\n"
    return (before.rstrip() + slow_block + after.lstrip()).strip() + "\n"


def compute_edit_budget(
    epoch: int,
    total_epochs: int,
    base_budget: int,
    floor_budget: int,
    schedule: str,
) -> int:
    """
    Compute the edit budget L_t for the current epoch step.

    cosine:   starts at base_budget, decays to floor_budget via cosine curve.
    linear:   linear decay from base_budget to floor_budget.
    constant: always base_budget.
    """
    import math

    if total_epochs <= 1 or schedule == "constant":
        return base_budget

    t = epoch / max(total_epochs - 1, 1)  # 0.0 → 1.0

    if schedule == "cosine":
        cos_val = 0.5 * (1 + math.cos(math.pi * t))
        budget  = floor_budget + (base_budget - floor_budget) * cos_val
    elif schedule == "linear":
        budget = base_budget + (floor_budget - base_budget) * t
    else:
        budget = base_budget

    return max(floor_budget, round(budget))
