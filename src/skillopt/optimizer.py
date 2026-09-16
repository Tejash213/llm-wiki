"""
src/skillopt/optimizer.py — Core SkillOpt optimization loop (one epoch).

Paper algorithm (Section 3):
  For each step in an epoch:
    1. [Rollout]     Run target model on train batch → scored trajectories.
    2. [Reflection]  Partition into successes / failures → minibatch reflection
                     → structured ADD/DELETE/REPLACE edits.
    3. [Merge]       Consolidate edits from all minibatches.
    4. [Rank/Clip]   Sort edits by score; clip to edit budget L_t.
    5. [Apply]       Produce candidate skill S_candidate.
    6. [Gate]        Evaluate candidate on selection split.
                     If score > best → accept as new current + best_skill.
                     Else → reject; add edits to rejected-edit buffer.

  At epoch end:
    7. [Slow update] Compare previous-epoch skill vs. current-epoch skill on a
                     sample of training tasks → write cross-epoch guidance block
                     into the protected <!-- SLOW_UPDATE --> region.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.skillopt.config_defaults import SkillOptConfig
from src.skillopt.skill_state import (
    Edit, apply_edits, write_slow_update,
    hash_skill, save_skill, load_skill,
    compute_edit_budget,
)
from src.skillopt.rollout import (
    run_rollout, batch_mean_score, partition_results, TrajectoryResult,
)
from src.skillopt.reflection import (
    reflect_minibatch, merge_edits, rank_and_clip,
    generate_slow_update_block,
)


# ── Epoch result dataclass ────────────────────────────────────────────────────

class EpochResult:
    def __init__(
        self,
        epoch: int,
        skill_text: str,
        train_score: float,
        val_score: float,
        accepted: bool,
        n_edits_applied: int,
        n_edits_rejected_total: int,
        apply_report: list[dict],
    ):
        self.epoch              = epoch
        self.skill_text         = skill_text
        self.train_score        = train_score
        self.val_score          = val_score
        self.accepted           = accepted
        self.n_edits_applied    = n_edits_applied
        self.n_edits_rejected_total = n_edits_rejected_total
        self.apply_report       = apply_report
        self.timestamp          = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "epoch":              self.epoch,
            "train_score":        self.train_score,
            "val_score":          self.val_score,
            "accepted":           self.accepted,
            "n_edits_applied":    self.n_edits_applied,
            "n_rejected_buffer":  self.n_edits_rejected_total,
            "skill_hash":         hash_skill(self.skill_text),
            "timestamp":          self.timestamp,
        }


# ── Validation scoring ────────────────────────────────────────────────────────

def _evaluate_on_split(
    docs_val: list[dict],
    skill_text: str,
    cfg: SkillOptConfig,
    label: str = "val",
) -> float:
    """Run rollout on validation/selection split and return mean score."""
    print(f"    [{label.upper()}] Evaluating on {len(docs_val)} docs...")
    results = run_rollout(
        docs_val, skill_text,
        batch_size=len(docs_val),
        skill_hash=hash_skill(skill_text),
        verbose=cfg.verbose,
    )
    score = batch_mean_score(results)
    print(f"    [{label.upper()}] Mean score: {score:.4f}")
    return score


# ── One optimization step (within an epoch) ───────────────────────────────────

def _optimization_step(
    docs_train_batch: list[dict],
    docs_val: list[dict],
    current_skill: str,
    best_val_score: float,
    rejected_buffer: list[dict],
    epoch: int,
    step: int,
    cfg: SkillOptConfig,
) -> tuple[str, float, list[dict], list[dict]]:
    """
    Run one full optimization step.

    Returns:
        (new_current_skill, new_best_val_score, updated_rejected_buffer, apply_report)
    """
    skill_h = hash_skill(current_skill)

    # 1. Rollout ──────────────────────────────────────────────────────────────
    print(f"\n  [Step {step}] Rollout on {len(docs_train_batch)} docs...")
    train_results = run_rollout(
        docs_train_batch, current_skill,
        batch_size=cfg.rollout_batch_size,
        skill_hash=skill_h,
        verbose=cfg.verbose,
    )
    train_score = batch_mean_score(train_results)
    print(f"  [Step {step}] Train mean score: {train_score:.4f}")

    # 2. Reflection ───────────────────────────────────────────────────────────
    successes, failures = partition_results(train_results)
    print(f"  [Step {step}] Successes: {len(successes)}, Failures: {len(failures)}")

    # Split into minibatches and gather edits
    all_fail_edits: list[Edit] = []
    all_succ_edits: list[Edit] = []

    # Process failure minibatches
    for mb_start in range(0, max(len(failures), 1), cfg.minibatch_size):
        mb_fail = failures[mb_start: mb_start + cfg.minibatch_size]
        mb_succ = successes[mb_start: mb_start + cfg.minibatch_size]
        if not mb_fail and not mb_succ:
            break
        edits, _ = reflect_minibatch(
            successes=mb_succ,
            failures=mb_fail,
            current_skill=current_skill,
            rejected_buffer=rejected_buffer,
            minibatch_size=cfg.minibatch_size,
            max_tokens=cfg.max_tokens_reflection,
            verbose=cfg.verbose,
        )
        for e in edits:
            (all_fail_edits if e.source == "failure" else all_succ_edits).append(e)

    # 3. Merge ────────────────────────────────────────────────────────────────
    merged = merge_edits(
        failure_edits=all_fail_edits,
        success_edits=all_succ_edits,
        verbose=cfg.verbose,
    )

    # 4. Rank / clip to edit budget ───────────────────────────────────────────
    budget = compute_edit_budget(
        epoch=epoch,
        total_epochs=cfg.epochs,
        base_budget=cfg.edit_budget,
        floor_budget=cfg.lr_floor,
        schedule=cfg.lr_schedule,
    )
    top_edits = rank_and_clip(merged, budget)
    print(f"  [Step {step}] Edit budget L_t={budget}, selected {len(top_edits)} edits")

    if not top_edits:
        print(f"  [Step {step}] No edits proposed — skill unchanged this step.")
        return current_skill, best_val_score, rejected_buffer, []

    # 5. Apply edits → candidate skill ────────────────────────────────────────
    candidate_skill, apply_report = apply_edits(current_skill, top_edits)

    # 6. Validation gate ──────────────────────────────────────────────────────
    val_score = _evaluate_on_split(docs_val, candidate_skill, cfg, label="val")

    gate_passed = (
        val_score > best_val_score
        if cfg.strict_gate else
        val_score >= best_val_score
    )

    if gate_passed:
        print(f"  [Step {step}] ✓ ACCEPTED  val {best_val_score:.4f} → {val_score:.4f}")
        new_skill      = candidate_skill
        new_best_val   = val_score
        new_buffer     = rejected_buffer  # keep buffer unchanged on accept
    else:
        score_drop = round(val_score - best_val_score, 4)
        print(f"  [Step {step}] ✗ REJECTED  val {best_val_score:.4f} ≥ {val_score:.4f} "
              f"(drop={score_drop})")
        new_skill    = current_skill
        new_best_val = best_val_score
        # Append rejected edits to buffer
        if cfg.rejected_buffer_enabled:
            for e in top_edits:
                rejected_buffer.append({"edit": e.to_dict(), "score_drop": score_drop})
            # Trim buffer to max size
            new_buffer = rejected_buffer[-cfg.rejected_buffer_max:]
        else:
            new_buffer = rejected_buffer

    return new_skill, new_best_val, new_buffer, apply_report


# ── Epoch-wise slow / meta update ─────────────────────────────────────────────

def _slow_meta_update(
    prev_skill: str,
    curr_skill: str,
    docs_train: list[dict],
    best_val_score: float,
    docs_val: list[dict],
    cfg: SkillOptConfig,
) -> tuple[str, float]:
    """
    Compare prev_skill vs curr_skill on a sample of training docs,
    generate a guidance block, and insert it into the protected region.

    Returns (updated_skill, new_val_score_after_slow_update).
    """
    import random
    rng = random.Random(cfg.split_seed)
    sample = rng.sample(docs_train, min(cfg.slow_update_n, len(docs_train)))

    print(f"\n  [SlowUpdate] Sampling {len(sample)} docs for cross-epoch comparison...")

    prev_results = run_rollout(
        sample, prev_skill, batch_size=len(sample),
        skill_hash=hash_skill(prev_skill), verbose=False,
    )
    curr_results = run_rollout(
        sample, curr_skill, batch_size=len(sample),
        skill_hash=hash_skill(curr_skill), verbose=False,
    )

    # Classify each doc's outcome
    improvements     = []
    regressions      = []
    persistent_fail  = []
    stable_success   = []

    prev_map = {r.doc_filename: r for r in prev_results}
    for cr in curr_results:
        pr = prev_map.get(cr.doc_filename)
        if pr is None:
            continue
        delta = cr.score - pr.score
        if delta > 0.05:
            improvements.append(cr)
        elif delta < -0.05:
            regressions.append(cr)
        elif cr.score < 0.4:
            persistent_fail.append(cr)
        else:
            stable_success.append(cr)

    guidance = generate_slow_update_block(
        prev_skill=prev_skill,
        curr_skill=curr_skill,
        improvements=improvements,
        regressions=regressions,
        persistent_failures=persistent_fail,
        stable_successes=stable_success,
        max_tokens=cfg.max_tokens_slow_update,
        verbose=cfg.verbose,
    )

    candidate_with_slow = write_slow_update(curr_skill, guidance)

    # Gate the slow-update candidate too
    val_score = _evaluate_on_split(docs_val, candidate_with_slow, cfg, label="slow-gate")
    gate_passed = (
        val_score > best_val_score if cfg.strict_gate else val_score >= best_val_score
    )

    if gate_passed:
        print(f"  [SlowUpdate] ✓ Slow update ACCEPTED  val {best_val_score:.4f} → {val_score:.4f}")
        return candidate_with_slow, val_score
    else:
        print(f"  [SlowUpdate] ✗ Slow update rejected  val stayed {best_val_score:.4f}")
        return curr_skill, best_val_score


# ── Full epoch ────────────────────────────────────────────────────────────────

def run_epoch(
    docs_train: list[dict],
    docs_val: list[dict],
    skill_text: str,
    best_val_score: float,
    epoch: int,
    cfg: SkillOptConfig,
    rejected_buffer: list[dict],
    prev_epoch_skill: str | None = None,
) -> tuple[str, float, list[dict], list[EpochResult]]:
    """
    Run one complete SkillOpt epoch.

    Returns:
        (new_skill, new_best_val_score, updated_rejected_buffer, step_results)
    """
    import math

    n_steps  = max(1, math.ceil(len(docs_train) / cfg.rollout_batch_size))
    results  = []

    print(f"\n{'='*60}")
    print(f"  EPOCH {epoch + 1}/{cfg.epochs}  |  {n_steps} step(s)  |  "
          f"{len(docs_train)} train docs  |  {len(docs_val)} val docs")
    print(f"{'='*60}")

    current_skill = skill_text

    for step in range(n_steps):
        start = step * cfg.rollout_batch_size
        batch = docs_train[start: start + cfg.rollout_batch_size]
        if not batch:
            break

        prev_skill_for_gate = current_skill

        current_skill, best_val_score, rejected_buffer, apply_report = \
            _optimization_step(
                docs_train_batch=batch,
                docs_val=docs_val,
                current_skill=current_skill,
                best_val_score=best_val_score,
                rejected_buffer=rejected_buffer,
                epoch=epoch,
                step=step + 1,
                cfg=cfg,
            )

        accepted = (current_skill != prev_skill_for_gate)
        results.append(EpochResult(
            epoch=epoch,
            skill_text=current_skill,
            train_score=0.0,       # updated in trainer
            val_score=best_val_score,
            accepted=accepted,
            n_edits_applied=len(apply_report),
            n_edits_rejected_total=len(rejected_buffer),
            apply_report=apply_report,
        ))

        if cfg.dry_run:
            print("  [DryRun] Stopping after 1 step.")
            break

    # Epoch-wise slow / meta update
    if cfg.slow_update_enabled and prev_epoch_skill is not None:
        current_skill, best_val_score = _slow_meta_update(
            prev_skill=prev_epoch_skill,
            curr_skill=current_skill,
            docs_train=docs_train,
            best_val_score=best_val_score,
            docs_val=docs_val,
            cfg=cfg,
        )

    return current_skill, best_val_score, rejected_buffer, results
