---
title: Skill Optimization
aliases:
  - Skill Optimization
type: concept
tags: []
last_updated: 2026-10-13
sources: []
---

## Summary
[[Skill Optimization]] is the practice of training an agent's procedural knowledge (a skill document) as an external, editable natural-language state using a controllable text-space optimizer. [[SkillOpt]] is a concrete instantiation: a separate optimizer model turns scored rollouts into bounded add/delete/replace edits, gated by held-out validation, producing compact, reusable skill artifacts without changing the deployed model weights.

## Key Points
- Treats a skill document as the trainable external state of a frozen agent, enabling reproducible, audit-able domain adaptation without weight updates.
- Uses a separate optimizer model that analyzes trajectory batches and proposes structured atomic edits (add / delete / replace) to the skill.
- Enforces a textual learning-rate budget and schedule to bound edit magnitude and stabilize successive revisions.
- Applies a held-out validation gate: proposed edits are accepted only if they strictly improve a validation score; rejected edits are stored as negative feedback.
- Incorporates an epoch-wise slow/meta update (momentum-like) to carry stable editing directions across epochs and improve long-horizon refinement.
- Produces compact exported skill artifacts (~300–2,000 tokens) that add zero inference-time cost at deployment and remain inspectable and procedural.
- Demonstrated broad empirical gains: across six benchmarks, seven target models, and three execution harnesses [[SkillOpt]] was best or tied on all evaluated cells (52/52) and delivered large accuracy lifts (e.g., average +23.5 points on GPT–5.5 in direct chat across several tasks).
- Optimized skills transfer across model scales, between execution harnesses (e.g., Codex <> Claude Code), and to nearby benchmarks without further optimization.

## Related Concepts
[[SkillOpt]], [[Agent Skills]], [[Text-Space Optimization]], [[Prompt Optimization]], [[Validation Gate]], [[Rejected-Edit Buffer]], [[Epoch-wise Slow Update]], [[Transfer Learning]]

## Source Documents
- SkillOpt Paper (2).pdf

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*