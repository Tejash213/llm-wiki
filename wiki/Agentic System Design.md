---
title: Agentic System Design
aliases:
  - "Agentic System Design"
type: theme
tags: []
last_updated: 2026-10-13
sources: []
---

## Summary
Agentic System Design is an approach to architecting [[Integrated AI Systems]] by defining explicit agent roles, flows, and operating models that mirror organizational structures for clarity, efficiency, and governance.

## Key Points
- Agents are assigned clear [[Agent Contracts]] and responsibilities.
- Delegation and payload handoff are enforced to prevent resource monopolization.
- Supports both solo-agent and orchestrated team modes.
- Incorporates [[Transparency]], cost observability, and [[Security and Permissions]] from the outset.
- Treats agent procedural knowledge as explicit, inspectable artifacts (agent skills) that can be trained, validated, exported, and reused across models and execution harnesses — enabling a separation between frozen model weights and trainable external state ([[Agent Skills]], [[SkillOpt]]).
- Applies controlled text-space optimization to skill documents: bounded add/delete/replace edits, a textual learning-rate budget, a rejected-edit buffer, and a held-out acceptance gate to provide stable, auditable, and low-risk updates to deployed procedure artifacts ([[Text-Space Optimization]], [[Held-out Validation]], [[Rejected-edit Buffer]], [[Slow/Meta Update]]).
- Optimization-as-text keeps deployment inference costs stable (zero extra inference-time model calls for the deployed agent) while improving task performance, aiding [[Cost Governance]].

## Related Concepts
[[Multi-Agent AI Orchestration]], [[General - Coordinator Agent|General/Coordinator Agent]], [[Agent Contracts]], [[Cost Governance]], [[Transparency]], [[Security and Permissions]], [[Agent Skills]], [[SkillOpt]], [[Text-Space Optimization]], [[Prompt Optimization]], [[Trace2Skill]], [[EvoSkill]], [[TextGrad]], [[GEPA]], [[Codex]], [[Claude Code]]

## Source Documents
- 03-06 Workshop_ Multi-Agent AI Orchestration, Pseudocode Interface, and Cost Governance-Summary.docx
- SkillOpt Paper (2).pdf — "SkillOpt: Executive Strategy for Self-Evolving Agent Skills", Yifan Yang et al., May 2026 (SkillOpt introduces a controllable text-space optimizer for agent skills with bounded edits, held-out validation, rejected-edit buffer, and epoch-wise slow/meta updates; broad empirical study across benchmarks, models, and harnesses)

## New Developments / Integration Notes
- SkillOpt formalizes the idea that a skill document is the trainable external state of a frozen agent and provides an operational analogy to deep-learning optimization: rollout/reflection batch sizes, textual learning rates and schedules, validation gates, and epoch-wise momentum-like slow/meta updates. This aligns with Agentic System Design's emphasis on explicit artifacts and governance for agent behavior ([[SkillOpt]], [[Text-Space Optimization]], [[Held-out Validation]]).
- SkillOpt's optimizer is a separate frontier model that converts scored rollouts into structured add/delete/replace edits on a single skill document; edits are accepted only if they improve held-out validation performance. Accepted edits are exported as compact, reusable skill artifacts (typically 300–2,000 tokens), while rejected edits populate a rejected-edit buffer used for later meta-updates ([[SkillOpt]], [[Rejected-edit Buffer]], [[Slow/Meta Update]]).
- The approach is harness-agnostic: the same optimization loop is effective across execution modes (direct chat and agentic loops such as [[Codex]] and [[Claude Code]]), enabling skills to be trained once, audited as text, and reused across related models and execution environments without changing model weights.
- Empirical claims from the SkillOpt study: across six benchmarks (including SearchQA, SpreadsheetBench, OfficeQA, DocVQA, LiveMathematicianBench, ALFWorld), seven target models, and three execution harnesses, SkillOpt was best or tied-best on all 52 evaluated (model, benchmark, harness) cells. Reported gains on GPT–5.5 include an average +23.5 point lift over no-skill in direct chat, +24.8 inside the Codex agentic loop, and +19.1 inside Claude Code. These results illustrate the potential for skill-level optimization to substantially improve agent performance while preserving deployability and inspectability.
- Ablations reported in the SkillOpt work attribute effectiveness to (a) bounded textual learning (vs. uncontrolled rewriting), (b) held-out gating to prevent harmful proposals, (c) a rejected-step buffer that converts failed edits into negative feedback, and (d) epoch-wise slow/meta updates that preserve long-horizon editing directions without expanding the deployed artifact.
- Transferability: SkillOpt shows cross-model, cross-harness, and cross-benchmark transfer — optimized skill artifacts retain value when moved across model scales, between [[Codex]] and [[Claude Code]] execution environments, and to nearby benchmarks without further optimization. This supports Agentic System Design goals around reuse, auditability, and lower-cost iteration.
- Implications for governance and operations: treating skills as explicit, versioned, and validated artifacts facilitates auditing, approval workflows, and cost-aware deployment. Because optimization happens off-line and the deployed skill adds zero inference-time optimizer calls, skill updates can be integrated into existing [[Cost Governance]] and [[Security and Permissions]] practices with minimal runtime overhead.
- Relationship to existing methods: SkillOpt complements and, in reported evaluations, outperforms prior approaches to prompt- and skill-level evolution such as human-written skills, one-shot LLM skill generation, Trace2Skill, TextGrad, GEPA, and EvoSkill on the tested cells. It generalizes prompt-optimization ideas to a persistent skill document intended for domain adaptation and reuse.

Notes on potential discrepancies:
- The existing Agentic System Design content emphasizes explicit agent roles and operating models. SkillOpt focuses specifically on optimizing [[Agent Skills]] (procedural textual artifacts) for a frozen agent model. These perspectives are complementary: Agentic System Design prescribes artifact and governance structures, and SkillOpt provides a concrete, controllable method for improving the contents of one such artifact class (skills). No direct contradiction was found between the sources; both advocate explicit, auditable procedural artifacts for agent behavior.

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*