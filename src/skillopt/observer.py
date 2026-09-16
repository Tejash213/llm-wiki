"""
src/skillopt/observer.py — Transparent background SkillOpt observer.

Plugs silently into the normal --query flow:

  During queries (completely transparent):
    • Each time answer_question() is called, the observer records which wiki
      pages were retrieved and scores their structural quality (heuristic).
    • No interruption, no paste, no extra UI.

  At session end (when user types 'exit' / 'quit'):
    • If enough queries have been observed (default ≥ 3), the observer builds
      a reflection prompt summarising what was queried and how the retrieved
      pages scored.
    • It sends that prompt to the Antigravity chat pane (via agentapi.bat).
    • It asks for ONE paste of the AI's edit proposals.
    • It applies bounded ADD/DELETE/REPLACE edits to best_skill.md.
    • It prints a brief summary of what changed.

  Result: the skill document improves with each query session, using the same
  Antigravity AI the user is already talking to — no API key needed.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config


# ── Reflection prompt for query-session evidence ──────────────────────────────

_REFLECT_SYSTEM = """\
You are an expert wiki-generation skill optimizer.

You will receive:
1. The CURRENT skill document — the system prompt used when generating wiki pages.
2. A QUERY SESSION LOG — questions real users asked, the wiki pages retrieved for
   each question, and a quality score (0–1) for those pages.

A low quality score means the wiki pages for that topic are poorly structured:
missing frontmatter fields, no wikilinks, thin Key Points, or empty summaries.
A low relevance score means no good pages existed for what the user asked about.

Your task: propose ADD / DELETE / REPLACE edits to the skill document so that
future wiki page generation produces better-quality, better-linked pages for the
topics users actually query.

Rules:
- Fix recurring structural weaknesses (missing fields, thin content).
- Add procedural guidance the current skill lacks (e.g. "always include at least
  3 Key Points", "always link related entities").
- Do NOT add topic-specific content — the skill is procedural, not factual.
- Limit proposals to the most impactful edits.

Return ONLY valid JSON — no markdown fences:
{
  "edits": [
    {
      "type": "ADD|DELETE|REPLACE",
      "target": "<exact anchor text in the skill, or empty string to append>",
      "content": "<new content>",
      "score": <float 0.0-1.0 confidence this helps>,
      "source": "failure"
    }
  ],
  "analysis": "<1-paragraph summary of what patterns you observed and what you changed>"
}
"""


# ── Query trace ───────────────────────────────────────────────────────────────

@dataclass
class QueryTrace:
    query:            str
    retrieved_fnames: list[str]
    relevance_scores: list[float]   # keyword-overlap score per page
    quality_score:    float         # heuristic structural quality (0-1)
    quality_detail:   dict          # subscores from rollout.score_pages
    timestamp:        str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ── Observer ──────────────────────────────────────────────────────────────────

class QueryObserver:
    """
    Transparently attached to the query loop.  Call .observe() after every
    answer_question() call and .reflect_and_update() at session end.
    """

    def __init__(
        self,
        skill_path: str | None = None,
        n_trigger: int = 3,
        edit_budget: int = 4,
    ):
        self.skill_path  = skill_path or config.SKILL_PATH
        self.n_trigger   = n_trigger    # reflect after this many queries
        self.edit_budget = edit_budget
        self.traces: list[QueryTrace] = []

        # Load the current skill (or empty if none yet)
        self.current_skill = ""
        if os.path.isfile(self.skill_path):
            with open(self.skill_path, "r", encoding="utf-8") as f:
                self.current_skill = f.read()

    # ── Called transparently after every answer_question() ────────────────────

    def observe(
        self,
        query: str,
        retrieved_pages: list[tuple[str, str]],   # [(filename, content), ...]
        relevance_scores: list[float],
    ) -> None:
        """
        Record one query + its retrieved pages.  Called silently inside
        answer_question(); the user sees nothing extra.
        """
        from src.skillopt.rollout import score_pages

        page_dicts = [
            {"title":    fname.replace(".md", "").replace("-", " ").title(),
             "filename": fname,
             "content":  content}
            for fname, content in retrieved_pages
        ]
        quality, subscores = score_pages(page_dicts) if page_dicts else (0.0, {})

        trace = QueryTrace(
            query=query,
            retrieved_fnames=[fn for fn, _ in retrieved_pages],
            relevance_scores=relevance_scores[:len(retrieved_pages)],
            quality_score=quality,
            quality_detail=subscores,
        )
        self.traces.append(trace)

        # Print a tiny one-liner so the user knows SkillOpt is watching
        q_label = query[:50] + ("…" if len(query) > 50 else "")
        print(f"  [SkillOpt] Observed query #{len(self.traces)}: "
              f"'{q_label}'  page_quality={quality:.2f}")

    # ── Called at session exit ─────────────────────────────────────────────────

    def has_evidence(self) -> bool:
        return len(self.traces) >= self.n_trigger

    def reflect_and_update(self) -> bool:
        """
        Build a reflection prompt from accumulated query traces, send it to
        the Antigravity chat pane, collect the pasted response, apply bounded
        edits to best_skill.md.

        Returns True if the skill was updated.
        """
        if not self.traces:
            return False

        if not self.current_skill:
            print("\n  [SkillOpt] No skill document found — run --skillopt-init first.")
            return False

        n = len(self.traces)
        print(f"\n{'=' * 60}")
        print(f"  SkillOpt: Reflecting on {n} queries from this session...")
        print(f"  The prompt will be sent to Antigravity chat.")
        print(f"  Paste the AI's response here when it's ready.")
        print(f"{'=' * 60}\n")

        user_prompt = self._build_reflection_prompt()

        # Switch to interactive mode for this one call, then restore
        import config as _cfg
        old_backend           = _cfg.SKILLOPT_BACKEND
        _cfg.SKILLOPT_BACKEND = "interactive"

        from src.llm_client import call_llm
        try:
            raw = call_llm(_REFLECT_SYSTEM, user_prompt, max_tokens=2048)
        finally:
            _cfg.SKILLOPT_BACKEND = old_backend

        # Parse edits
        from src.skillopt.reflection import _parse_edits_json, rank_and_clip
        from src.skillopt.skill_state import apply_edits, save_skill

        edits = _parse_edits_json(raw)
        if not edits:
            print("  [SkillOpt] No edits parsed — skill unchanged.")
            return False

        top_edits  = rank_and_clip(edits, self.edit_budget)
        new_skill, report = apply_edits(self.current_skill, top_edits)

        applied   = [r for r in report if r["status"] == "applied"]
        skipped   = [r for r in report if r["status"] == "skipped"]

        if not applied:
            print("  [SkillOpt] All proposed edits were skipped (targets not found).")
            print("             Skill unchanged.")
            return False

        # Save updated skill
        if not _cfg.dry_run if hasattr(_cfg, "dry_run") else True:
            save_skill(self.skill_path, new_skill)
            self.current_skill = new_skill

        print(f"\n  [SkillOpt] ✓ Skill updated: {len(applied)} edit(s) applied, "
              f"{len(skipped)} skipped.")
        print(f"             → {self.skill_path}")

        # Show analysis if present
        try:
            import json, re
            raw_stripped = raw.strip()
            if raw_stripped.startswith("```"):
                raw_stripped = re.sub(r"^```[a-zA-Z]*\n?", "", raw_stripped)
                raw_stripped = re.sub(r"\n?```$", "", raw_stripped)
            data = json.loads(raw_stripped)
            if "analysis" in data:
                print(f"\n  [SkillOpt Analysis]\n  {data['analysis']}\n")
        except Exception:
            pass

        return True

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_reflection_prompt(self) -> str:
        """Format all accumulated traces into a reflection prompt for the AI."""
        lines = [
            "=== CURRENT SKILL DOCUMENT ===",
            self.current_skill[:2000] +
            ("...[truncated]" if len(self.current_skill) > 2000 else ""),
            "",
            "=== QUERY SESSION LOG ===",
        ]

        for i, tr in enumerate(self.traces, 1):
            lines.append(f"\n--- Query {i}: \"{tr.query}\" ---")

            if tr.retrieved_fnames:
                lines.append(f"Pages retrieved: {', '.join(tr.retrieved_fnames[:5])}")
            else:
                lines.append("Pages retrieved: (none — no matching pages found)")

            lines.append(f"Page quality score: {tr.quality_score:.3f} "
                         f"(0=poor, 1=excellent)")

            if tr.quality_detail:
                detail = ", ".join(
                    f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                    for k, v in tr.quality_detail.items()
                    if k != "n_pages"
                )
                lines.append(f"Quality breakdown: {detail}")

            if not tr.retrieved_fnames:
                lines.append("Issue: no pages exist for this topic yet.")
            elif tr.quality_score < 0.5:
                lines.append("Issue: retrieved pages are low quality.")
            else:
                lines.append("Status: pages look adequate.")

        lines += [
            "",
            "=== INSTRUCTION ===",
            f"Total queries: {len(self.traces)}",
            f"Mean quality: {sum(t.quality_score for t in self.traces)/len(self.traces):.3f}",
            "",
            "Propose bounded ADD/DELETE/REPLACE edits to improve the skill.",
            "Focus on structural rules that would raise the quality scores above.",
        ]

        return "\n".join(lines)

    # ── Session summary ────────────────────────────────────────────────────────

    def print_summary(self) -> None:
        """Print a brief summary of what was observed this session."""
        if not self.traces:
            return
        mean_q = sum(t.quality_score for t in self.traces) / len(self.traces)
        no_pages = sum(1 for t in self.traces if not t.retrieved_fnames)
        low_q    = sum(1 for t in self.traces if t.quality_score < 0.5 and t.retrieved_fnames)

        print(f"\n  [SkillOpt Session Summary]")
        print(f"    Queries observed : {len(self.traces)}")
        print(f"    Mean page quality: {mean_q:.3f}")
        print(f"    Queries with no pages  : {no_pages}")
        print(f"    Queries with low-quality pages: {low_q}")
        if not self.has_evidence():
            remaining = self.n_trigger - len(self.traces)
            print(f"    ({remaining} more quer{'y' if remaining == 1 else 'ies'} "
                  f"needed to trigger skill reflection)")
