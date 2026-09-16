"""
src/skillopt/config_defaults.py — Default hyperparameters for the SkillOpt optimizer.

All values mirror the paper's defaults (Section 4 "Setting") but are scaled
down where appropriate so a local run with agentapi.bat / OpenAI finishes in
minutes rather than hours.

Override any of these by passing an explicit SkillOptConfig object to trainer.train().
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SkillOptConfig:
    # ── Training schedule ──────────────────────────────────────────────────────
    epochs: int = 4
    """Number of full passes over the training split."""

    rollout_batch_size: int = 10
    """Documents sampled per step for rollout evidence.
    Paper default: 40; scaled to 10 for local use."""

    minibatch_size: int = 4
    """Trajectories per reflection minibatch.
    Paper default: 8; scaled to 4 for local use."""

    # ── Edit budget (textual learning rate) ───────────────────────────────────
    edit_budget: int = 4
    """Max number of ADD/DELETE/REPLACE edits applied at each step (L_t).
    Paper default: 4 with cosine decay."""

    lr_schedule: Literal["constant", "linear", "cosine"] = "cosine"
    """Learning-rate schedule for edit budget.
    cosine: starts at edit_budget, decays to lr_floor.
    linear: linear decay to lr_floor.
    constant: edit_budget is fixed throughout."""

    lr_floor: int = 2
    """Minimum edit budget after schedule decay."""

    # ── Data split ─────────────────────────────────────────────────────────────
    split_ratio: tuple = (0.4, 0.1, 0.5)
    """(train, selection, test) fraction of available documents.
    Paper default: 4:1:5."""

    split_seed: int = 42
    """Seed for reproducible train/selection/test split."""

    # ── Validation gate ────────────────────────────────────────────────────────
    strict_gate: bool = True
    """If True (paper default), ties are rejected — candidate must be strictly
    better than the current best.  If False, ties are accepted."""

    # ── Slow / meta update ────────────────────────────────────────────────────
    slow_update_enabled: bool = True
    """Run epoch-wise slow/meta update at the end of each epoch."""

    slow_update_n: int = 10
    """Number of tasks sampled to compare previous vs current skill.
    Paper default: 20; scaled to 10."""

    meta_skill_enabled: bool = True
    """Maintain an optimizer-side meta-skill that summarizes which edit patterns
    helped / failed / persist — prepended to future optimizer calls."""

    # ── Rejected-edit buffer ──────────────────────────────────────────────────
    rejected_buffer_enabled: bool = True
    """Retain rejected edits as negative feedback for later reflections."""

    rejected_buffer_max: int = 20
    """Maximum number of rejected edits to keep in the epoch-local buffer."""

    # ── Edit mode ─────────────────────────────────────────────────────────────
    edit_mode: Literal["patch", "rewrite"] = "patch"
    """patch: localized ADD/DELETE/REPLACE operations (default).
    rewrite: optimizer suggests a full rewrite in one shot."""

    # ── LLM / backend settings ────────────────────────────────────────────────
    optimizer_model: str = "gpt-4.1"
    """Model identifier passed to the LLM backend for optimizer calls.
    Ignored when using the agentapi.bat backend (which routes to the IDE AI)."""

    max_tokens_reflection: int = 2048
    """Max tokens for a single reflection / edit-proposal call."""

    max_tokens_slow_update: int = 1024
    """Max tokens for the slow/meta update call."""

    # ── Dry-run / debug ───────────────────────────────────────────────────────
    dry_run: bool = False
    """If True: run 1 epoch with up to 3 training docs and do not write files.
    Used for smoke-testing the pipeline without spending many API calls."""

    verbose: bool = True
    """Print detailed progress to stdout."""


# Singleton default — import this in other modules for convenience
DEFAULT_CONFIG = SkillOptConfig()
