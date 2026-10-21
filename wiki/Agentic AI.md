---
---
title: Agentic AI
aliases:
  - "Agentic AI"
type: concept
tags: []
last_updated: 2026-10-13
sources:
  - "SkillOpt Paper (2).pdf"
---

## Summary
[[Agentic AI]] refers to [[Artificial Intelligence Integration|artificial intelligence]] systems capable of autonomously directing workflows and coordinating activities to achieve specific goals.

## Key Points
- [[Agentic AI]] can create and manage agents that operate independently or in coordination with other agents.
- It may incorporate various AI types, including generative, predictive, and [[Automation]].
- Agentic AI is seen as a powerful advancement in [[AI in Real Estate|real estate]] and other industries.
- Agentic systems increasingly rely on explicit, reusable procedural artifacts often called [[Agent Skills]] or "skills" — compact natural-language documents that encode procedures, heuristics, tool policies, and output constraints that a frozen model can follow as external state.

## Research: [[SkillOpt]] (May 2026)
- SkillOpt is a text-space optimizer for [[Agent Skills]] that treats a skill document as the external, trainable state for a frozen agent. It introduces a separate optimizer model that converts scored rollouts into bounded add/delete/replace edits on a skill document and only accepts edits that strictly improve a held-out validation score.
- Core controls and mechanisms:
  - Bounded add/delete/replace edits (atomic textual edits) and a textual learning-rate budget that limit how far a skill can move in one update.
  - A held-out validation gate that accepts candidate skills only when they improve held-out performance.
  - A rejected-edit buffer that stores rejected proposals as negative feedback for later optimizer updates.
  - An epoch-wise slow/meta update (momentum-like slow update) to carry stable editing directions across epochs.
  - Batch/minibatch rollout and reflection sizes to control evidence noise and make updates reproducible.
- Practical properties and empirical findings:
  - SkillOpt is described as harness-agnostic and was evaluated across six benchmarks (QA, spreadsheets, documents, math, embodied decision making, etc.), seven target models (from frontier-scale GPT variants to smaller models), and three execution harnesses (direct chat, [[Codex]], and [[Claude Code]]).
  - Across 52 evaluated (model, benchmark, harness) cells SkillOpt was reported as best or tied-best on all 52 cells, outperforming baselines including human-written skills, one-shot LLM skills, Trace2Skill, TextGrad, GEPA, and EvoSkill.
  - On [[GPT–5.5]] (reported target model), SkillOpt lifted average no-skill accuracy by +23.5 points in direct chat, by +24.8 points inside the [[Codex]] agentic loop, and by +19.1 points inside [[Claude Code]].
  - Learned skill artifacts are compact (roughly 300–2,000 tokens after only 1–4 accepted edits), inspectable, and procedural rather than instance-specific.
  - Skills optimized by SkillOpt transfer across model scales, between execution harnesses (e.g., Codex → Claude Code), and to nearby benchmarks without further optimization, offering low-cost transfer and iteration.
- Conceptual framing:
  - SkillOpt frames skill editing as text-space optimization analogous to parameter-space optimization: rollouts provide gradients-like signals, textual learning rate controls step size, the validation gate plays the role of held-out selection, and slow/meta updates provide momentum.
  - The method emphasizes stability: bounded edits and validation gating prevent large semantic jumps and accumulation of harmful changes.
- Contributions claimed in the paper:
  - The first systematic controllable text-space optimizer for agent skills, with rollout batches, reflection minibatches, add/delete/replace edits, textual learning rates, schedules, held-out acceptance, rejected-edit buffers, and epoch-wise slow/meta updates.
  - Broad empirical support across benchmarks, models, and harnesses showing consistent improvement and transferability of optimized skills.

## Related Concepts
[[AI in Real Estate]], [[Boxer]], [[Boxer AI Philosophy]], [[AI Adoption Roadmap]], [[Large Language Model]], [[Agent Skills]], [[SkillOpt]], [[Codex]], [[Claude Code]], [[EvoSkill]], [[TextGrad]], [[GEPA]], [[Trace2Skill]]

## Source Documents
- Boxer AI Show and Tell.docx
- SkillOpt Paper (2).pdf

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*