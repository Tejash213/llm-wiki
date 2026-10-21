---
---
title: AI Training Framework
aliases:
  - "AI Training Framework"
type: concept
tags: []
last_updated: 2026-10-13
sources:
  - "AI Training and Concepts Overview 2025-09-11.docx"
  - "SkillOpt Paper (2).pdf"
---

## Summary
The [[AI Training Framework]] outlines four key areas for implementing [[Agentic AI|AI]] in organizations: [[Initiating Action]], [[Data Access]], [[AI Model]]/platform selection, and [[Results Handling]].

Skill optimization research introduces a complementary, operational approach to the framework: treat a skill as an external, trainable text artifact and optimize it with a separate text-space optimizer. [[SkillOpt]] is an example of this approach — a controllable [[Text-space Optimization]] method that uses an [[Optimizer Model]] to convert scored rollouts into bounded [[Add/Delete/Replace Edits]] on a single skill document, accepts edits only when they strictly improve a held-out validation score, and relies on controls like a [[Textual Learning Rate]], [[Rejected-edit Buffer]], and [[Epoch-wise Slow/Meta Update]] to stabilize training. This positions skills as a trainable interface between the frozen execution [[AI Model]] and observed rollout data from [[Data Access]] while leaving deployment-time inference unchanged.

## Key Points
- The framework consists of four areas: activation, data input, model/platform, and results handling.
- Each area has multiple options and must be understood for effective [[AI Applications]].
- The framework applies to both basic and advanced [[AI Solutions Inventory|AI solutions]].
- Skills may be treated as the mutable activation artifact under [[Initiating Action]] and trained using rollout evidence from [[Data Access]] without modifying frozen [[AI Model]] weights.
- SkillOpt operationalizes skill training with: an [[Optimizer Model]] that proposes bounded [[Add/Delete/Replace Edits]]; rollout and reflection minibatches as evidence; a [[Textual Learning Rate]] to bound edit magnitude; a held-out [[Results Handling]] validation gate to accept only improving edits; a [[Rejected-edit Buffer]] to convert failed proposals into negative feedback; and an [[Epoch-wise Slow/Meta Update]] to carry stable editing directions across epochs.
- Skill optimization can add zero inference-time calls at deployment because edits are applied to the skill document (exported as a compact [[best_skill.md]] artifact) while the target model remains frozen.
- Empirical results reported for [[SkillOpt]]: across six benchmarks (SearchQA, SpreadsheetBench, OfficeQA, DocVQA, LiveMathematicianBench, ALFWorld), seven target models, and three execution [[Execution Harnesses]] (direct chat, [[Codex]], [[Claude Code]]), SkillOpt was best or tied-best on all 52 evaluated (model, benchmark, harness) cells and substantially outperformed human-written skills, one-shot LLM skills, and prior methods like Trace2Skill, TextGrad, GEPA, and EvoSkill.
- Reported gains on GPT–5.5 (direct chat) included average lifts of +23.5 points over no-skill across the six benchmarks (with specific boosts reported for SearchQA, SpreadsheetBench, OfficeQA, DocVQA, LiveMathematicianBench, ALFWorld). Similar uplifts were reported inside [[Codex]] and [[Claude Code]] harnesses, and optimized skill artifacts transfer across model scales, harnesses, and related benchmarks without further optimization.
- Mapping to the AI Training Framework: skill optimization affects [[Initiating Action]] (how agents start procedures), [[Data Access]] (the rollout and validation splits used as training evidence), [[AI Model]] (the optimizer operates with a frozen target model and a separate optimizer model), and [[Results Handling]] (held-out validation gate, rejected-edit buffer, and export of validated skill artifacts).

## Related Concepts
[[Initiating Action]], [[Data Access]], [[AI Model]], [[Results Handling]], [[AI Orchestration]], [[SkillOpt]], [[Agent Skills]], [[Text-space Optimization]], [[Optimizer Model]], [[Textual Learning Rate]], [[Rejected-edit Buffer]], [[Epoch-wise Slow/Meta Update]], [[Add/Delete/Replace Edits]], [[Execution Harnesses]], [[Codex]], [[Claude Code]], [[best_skill.md]]

## Source Documents
- AI Training and Concepts Overview 2025-09-11.docx
- SkillOpt Paper (2).pdf

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*

---