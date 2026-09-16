"""
src/skillopt — SkillOpt: text-space optimizer for agent skills.

Based on: "SkillOpt: Executive Strategy for Self-Evolving Agent Skills"
Yang et al., Microsoft / SJTU / Tongji / Fudan, May 2026.
arXiv:2605.23904

The core idea: instead of fine-tuning model weights, treat the system-prompt
skill document as a trainable external state.  An offline optimizer model
proposes bounded ADD/DELETE/REPLACE edits; a held-out validation gate accepts
only edits that strictly improve a selection-split score.  The best validated
skill is exported as wiki/best_skill.md and can be dropped-in as the system
prompt for any future wiki-generation run.
"""
