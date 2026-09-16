"""
src/skillopt/rollout.py — Forward pass: execute tasks and collect scored trajectories.

For each document in the rollout batch, this module:
  1. Prepends the current skill to the wiki-generation system prompt.
  2. Calls generate_wiki_from_document() with the skill override.
  3. Scores the produced pages with a heuristic quality function.

Scoring (r ∈ [0, 1]):
  Heuristic subscores are averaged:
    - page_count_score:  sigmoid on number of pages created (saturates at 5+)
    - frontmatter_score: fraction of required frontmatter fields present
    - wikilink_score:    fraction of pages with ≥ 1 wikilink
    - sections_score:    fraction of pages with non-empty Summary + Key Points
    - richness_score:    average words-per-page (saturates at 150 words)

  Optionally, an LLM judge can be used instead (see llm_judge_score()).
"""

import math
import re
import sys
import os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ── Trajectory result ─────────────────────────────────────────────────────────

@dataclass
class TrajectoryResult:
    """One scored execution of wiki-generation on a single document."""
    doc_filename: str
    pages_created: list[dict]   # [{title, filename, content}]
    score: float                # r ∈ [0, 1]
    subscores: dict = field(default_factory=dict)
    skill_hash: str = ""
    error: str = ""


# ── Heuristic scorer ──────────────────────────────────────────────────────────

REQUIRED_FRONTMATTER = {"title", "type", "tags", "last_updated", "sources"}
REQUIRED_SECTIONS    = {"## Summary", "## Key Points"}


def _sigmoid(x: float, k: float = 1.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * x))


def score_pages(pages: list[dict]) -> tuple[float, dict]:
    """
    Score a list of generated wiki pages on a 0–1 heuristic scale.

    pages: list of { title, filename, content } dicts as returned by
           generate_wiki_from_document().
    """
    if not pages:
        return 0.0, {"page_count": 0, "note": "no pages created"}

    n = len(pages)

    # 1. Page count score — sigmoid centred at 3 pages, saturates at 5+
    page_count_score = _sigmoid(n - 3, k=0.7)

    # 2. Frontmatter completeness
    fm_scores = []
    for p in pages:
        content = p.get("content", "")
        found = sum(
            1 for field in REQUIRED_FRONTMATTER
            if re.search(rf"^{re.escape(field)}:", content, re.MULTILINE)
        )
        fm_scores.append(found / len(REQUIRED_FRONTMATTER))
    frontmatter_score = sum(fm_scores) / n

    # 3. Wikilink presence
    wl_scores = []
    for p in pages:
        content = p.get("content", "")
        has_links = bool(re.search(r'\[\[.+?\]\]', content))
        wl_scores.append(1.0 if has_links else 0.0)
    wikilink_score = sum(wl_scores) / n

    # 4. Required sections present and non-empty
    sec_scores = []
    for p in pages:
        content = p.get("content", "")
        found = 0
        for sec in REQUIRED_SECTIONS:
            idx = content.find(sec)
            if idx != -1:
                # Check that there's non-trivial content after the heading
                rest = content[idx + len(sec):].strip()
                next_sec = re.search(r'^##', rest, re.MULTILINE)
                snippet  = rest[:next_sec.start()].strip() if next_sec else rest[:300].strip()
                if len(snippet) > 20:
                    found += 1
        sec_scores.append(found / len(REQUIRED_SECTIONS))
    sections_score = sum(sec_scores) / n

    # 5. Content richness — average words per page (sigmoid, saturates ~150 words)
    richness_scores = []
    for p in pages:
        words = len(p.get("content", "").split())
        richness_scores.append(_sigmoid((words - 80) / 40, k=1.0))
    richness_score = sum(richness_scores) / n

    # Weighted average (equal weights, adjustable)
    weights = {
        "page_count":   0.20,
        "frontmatter":  0.25,
        "wikilinks":    0.20,
        "sections":     0.25,
        "richness":     0.10,
    }
    final = (
        weights["page_count"]  * page_count_score +
        weights["frontmatter"] * frontmatter_score +
        weights["wikilinks"]   * wikilink_score +
        weights["sections"]    * sections_score +
        weights["richness"]    * richness_score
    )

    subscores = {
        "page_count":   round(page_count_score, 4),
        "frontmatter":  round(frontmatter_score, 4),
        "wikilinks":    round(wikilink_score, 4),
        "sections":     round(sections_score, 4),
        "richness":     round(richness_score, 4),
        "n_pages":      n,
    }
    return round(final, 4), subscores


# ── Rollout runner ────────────────────────────────────────────────────────────

def run_rollout(
    docs: list[dict],
    skill_text: str,
    batch_size: int,
    skill_hash: str = "",
    verbose: bool = True,
) -> list[TrajectoryResult]:
    """
    Execute wiki generation on up to `batch_size` documents using `skill_text`
    as the system prompt override.

    Returns a list of TrajectoryResult, one per document.
    """
    # Lazy import to avoid circular dependency
    from src.generate_wiki import generate_wiki_from_document

    batch = docs[:batch_size]
    results: list[TrajectoryResult] = []

    for doc in batch:
        if verbose:
            print(f"    [Rollout] {doc['filename']}")
        try:
            pages = generate_wiki_from_document(doc, skill_override=skill_text)
            score, subscores = score_pages(pages)
        except Exception as exc:
            if verbose:
                print(f"      [ERROR] {exc}")
            results.append(TrajectoryResult(
                doc_filename=doc["filename"],
                pages_created=[],
                score=0.0,
                skill_hash=skill_hash,
                error=str(exc),
            ))
            continue

        results.append(TrajectoryResult(
            doc_filename=doc["filename"],
            pages_created=pages,
            score=score,
            subscores=subscores,
            skill_hash=skill_hash,
        ))
        if verbose:
            fm  = subscores.get('frontmatter')
            wl  = subscores.get('wikilinks')
            fm_s = f"{fm:.2f}" if isinstance(fm, float) else str(fm)
            wl_s = f"{wl:.2f}" if isinstance(wl, float) else str(wl)
            print(f"      score={score:.3f}  pages={len(pages)}  "
                  f"fm={fm_s}  wl={wl_s}")

    return results


# ── Batch statistics helpers ──────────────────────────────────────────────────

def batch_mean_score(results: list[TrajectoryResult]) -> float:
    """Mean score across all trajectories (ignoring errors)."""
    valid = [r.score for r in results if not r.error]
    return round(sum(valid) / len(valid), 4) if valid else 0.0


def partition_results(
    results: list[TrajectoryResult],
    threshold: float | None = None,
) -> tuple[list[TrajectoryResult], list[TrajectoryResult]]:
    """
    Split trajectories into (successes, failures).
    threshold defaults to the batch mean; trajectories above → success.
    """
    valid = [r for r in results if not r.error]
    if not valid:
        return [], []
    if threshold is None:
        threshold = batch_mean_score(valid)
    successes = [r for r in valid if r.score >= threshold]
    failures  = [r for r in valid if r.score <  threshold]
    return successes, failures
