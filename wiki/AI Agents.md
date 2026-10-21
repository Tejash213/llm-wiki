---
---
title: AI Agents
aliases:
  - "AI Agents"
type: concept
tags: []
last_updated: 2026-10-13
sources:
  - "SkillOpt Paper (2).pdf"
---

## Summary
[[AI Agents]] are configurable artificial intelligence tools embedded into business workflows to automate routine tasks and support higher-value work.

Recent research (May 2026) introduces [[SkillOpt]]—a systematic, controllable text-space optimizer for agent skills that treats a skill document as the external, trainable state for a frozen agent. [[SkillOpt]] uses an external optimizer model to convert scored rollouts into bounded add/delete/replace edits, applies a textual learning-rate budget, and accepts edits only when they strictly improve a held-out validation score. The approach produces compact, inspectable skill artifacts (roughly 300–2,000 tokens) that transfer across model scales and execution harnesses without changing model weights.

## Key Points
- [[Boxer Property]] uses [[AI Agents]] to automate repetitive tasks and streamline operations.
- [[AI Agents]] are delivered and managed via platforms like [[Brava Systems]].
- Their integration frees employees to focus on uniquely human tasks, enhancing [[Employee Fulfillment]].
- [[SkillOpt]] frames skill editing as a controlled optimization loop: rollout evidence → optimizer-model reflection → bounded add/delete/replace textual edits → held-out validation gate → accepted skill artifact.
- Core controls in [[SkillOpt]] include a textual learning-rate budget, a rejected-edit buffer that turns failed edits into negative feedback, and an epoch-wise slow/meta update to stabilize long-horizon refinement.
- Across six benchmarks, seven target models, and three execution harnesses, [[SkillOpt]] is reported as best-or-tied on all 52 evaluated (model, benchmark, harness) cells; on [[GPT–5.5]] it lifts average no-skill accuracy by +23.5 points in direct chat, by +24.8 points inside a [[Codex]]-style agentic loop, and by +19.1 points inside [[Claude Code]].
- Optimized skill artifacts remain compact, procedural rather than instance-specific, inspectable as text, and reusable across models and harnesses—supporting low-cost transfer and iteration without model-weight updates.
- The paper reports that [[SkillOpt]] outperforms human-written skills, one-shot LLM skills, and other skill/prompt optimization methods such as [[Trace2Skill]], [[TextGrad]], [[GEPA]], and [[EvoSkill]] on the evaluated cells.

## Related Concepts
[[Boxer Property]], [[Brava Systems]], [[Incremental AI Rollout]], [[Employee Fulfillment]], [[Innovation Platform]], [[SkillOpt]], [[EvoSkill]], [[Trace2Skill]], [[TextGrad]], [[GEPA]], [[Codex]], [[Claude Code]], [[GPT–5.5]]

## Source Documents
- Podcast about Data [[Global Teams]] and [[Brava Systems]] AI to Transform [[Boxer]].docx
- [[SkillOpt]] Paper (2).pdf

---


---

*Part of the [[_index|FutureSense Knowledge Wiki]]*

---