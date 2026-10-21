---
title: Textual Learning Rate
aliases:
  - Textual Learning Rate
type: concept
tags: []
last_updated: 2026-10-13
sources:
  - SkillOpt Paper (2).pdf
---

## Summary
Textual learning rate is a bounded edit-budget mechanism in text-space optimization that controls how far a skill document may change in a single update. It functions as an analogue of a weight-space learning rate, limiting add/delete/replace edits and working with schedules and validation to ensure stable, incremental skill improvement.

## Key Points
- Defines an edit budget (often denoted L) that bounds the total magnitude of atomic add/delete/replace edits applied to a skill document in one update.
- Serves the same role as a learning rate in deep learning: constrains step size, prevents large semantic jumps, and reduces update instability.
- Employed with a schedule/decay so per-epoch or per-update budgets can shrink or adapt over training, improving convergence and stability.
- Candidate edits are aggregated, ranked, and clipped under the textual learning-rate budget before being applied; only budget-compliant edits are evaluated by the held-out validation gate.
- Works together with the rejected-edit buffer and held-out acceptance to convert failed proposals into negative feedback while preventing harmful accumulated changes.
- Enables transferable, compact skill artifacts by ensuring each accepted revision remains close enough to previous versions for later optimizer calls to learn from prior successes and failures.

## Related Concepts
[[SkillOpt]], [[Text-space Optimization]], [[Edit Budget]], [[Held-out Gate]], [[Rejected-edit Buffer]], [[Epoch-wise Slow/Meta Update]]

## Source Documents
- SkillOpt Paper (2).pdf

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*