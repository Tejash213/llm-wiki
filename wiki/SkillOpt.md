---
title: SkillOpt
aliases:
  - SkillOpt
type: entity
tags: []
last_updated: 2026-10-13
sources:
  - SkillOpt Paper (2).pdf
---

## Summary
[[SkillOpt]] is a text-space optimizer that trains reusable agent skills as external natural-language documents. A separate optimizer model converts scored execution rollouts into bounded add/delete/replace edits, and edits are accepted only when they strictly improve a held-out validation score, producing compact, deployable skill artifacts without changing model weights.

## Key Points
- Treats a skill document as the external trainable state for a frozen agent and applies optimization-style controls (batching, learning rate, validation) to text editing.
- An optimizer model proposes structured atomic edits (add/delete/replace) from rollout reflection; edits are ranked and clipped under a textual learning-rate budget before application.
- A held-out validation gate accepts only edits that improve performance; rejected edits are stored as negative feedback in a rejected-edit buffer for later optimizer updates.
- Epoch-wise slow/meta update carries stable editing directions across epochs (like momentum), improving long-horizon refinement without bloating the exported skill.
- Design choices (bounded textual learning, validation gating, rejected-step buffer, slow updates) enable stable, repeatable improvement and make optimized skills compact (≈300–2,000 tokens).
- Demonstrated broad empirical gains: evaluated across six benchmarks, seven target models, and three execution harnesses; SkillOpt was best or tied on all 52 evaluated (model, benchmark, harness) cells and provided large accuracy lifts (e.g., +23.5 pts avg on GPT–5.5 in direct chat).
- Learned skills transfer across model scales, execution harnesses (Codex ↔ Claude Code), and related benchmarks without further optimization; deployment incurs zero extra inference-time model calls.

## Related Concepts
[[Agent Skills]], [[Text-space Optimization]], [[Optimizer Model]], [[Held-Out Validation]], [[Textual Learning Rate]], [[Rejected-Edit Buffer]], [[Epoch-wise Slow/Meta Update]], [[Prompt Optimization]], [[Skill Artifact]], [[Trace2Skill]], [[EvoSkill]], [[TextGrad]], [[GEPA]]

## Source Documents
- [[SkillOpt]] Paper (2).pdf

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*