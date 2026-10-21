"""
src/skillopt/trainer.py — Top-level SkillOpt training harness.

Usage (from main.py):
    from src.skillopt.trainer import train
    train(cfg=SkillOptConfig(...))

Or directly:
    python -m src.skillopt.trainer

The trainer:
  1. Loads / creates the initial skill document (wiki/initial_skill.md or
     wiki/best_skill.md if it already exists).
  2. Splits the available wiki source documents into train / selection / test.
  3. Runs N epochs of the SkillOpt optimization loop.
  4. Exports the best validated skill to wiki/best_skill.md.
  5. Writes a full training log to wiki/_skillopt_log.json.
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.skillopt.config_defaults import SkillOptConfig, DEFAULT_CONFIG
from src.skillopt.skill_state import load_skill, save_skill, hash_skill
from src.skillopt.optimizer import run_epoch, _evaluate_on_split


# ── Paths ─────────────────────────────────────────────────────────────────────

def _initial_skill_path() -> str:
    return os.path.join(config.WIKI_DIR, "initial_skill.md")


def _best_skill_path() -> str:
    return getattr(config, "SKILL_PATH", os.path.join(config.WIKI_DIR, "best_skill.md"))


def _log_path() -> str:
    return getattr(config, "SKILLOPT_LOG", os.path.join(config.WIKI_DIR, "_skillopt_log.json"))


# ── Document split ────────────────────────────────────────────────────────────

def _split_docs(
    docs: list[dict],
    ratio: tuple,
    seed: int,
    dry_run: bool = False,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Split docs into (train, selection, test) using the given ratio.
    With dry_run, cap each split to 3 docs for a fast smoke test.
    """
    rng = random.Random(seed)
    shuffled = docs[:]
    rng.shuffle(shuffled)

    n   = len(shuffled)
    n_tr  = max(1, round(n * ratio[0]))
    n_sel = max(1, round(n * ratio[1]))
    # Test gets the remainder
    train = shuffled[:n_tr]
    sel   = shuffled[n_tr: n_tr + n_sel]
    test  = shuffled[n_tr + n_sel:]

    if dry_run:
        train = train[:3]
        sel   = sel[:2]
        test  = test[:2]

    return train, sel, test


# ── Log helpers ───────────────────────────────────────────────────────────────

def _load_log(path: str) -> dict:
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"runs": []}


def _save_log(path: str, log: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


# ── Main training entry point ─────────────────────────────────────────────────

def train(cfg: SkillOptConfig = None) -> str:
    """
    Run the full SkillOpt training loop.

    Returns the path to the exported best_skill.md.
    """
    if cfg is None:
        cfg = DEFAULT_CONFIG

    # Force interactive bridge mode for all LLM calls during this run.
    # This makes call_llm() send each prompt to the Antigravity chat pane and
    # then pause to collect your pasted response — no API key required.
    import config as _cfg
    _original_backend    = _cfg.SKILLOPT_BACKEND
    _cfg.SKILLOPT_BACKEND = "interactive"

    print("\n" + "=" * 60)
    print("  SkillOpt — Self-Evolving Wiki Skill Optimizer")
    print("  Based on: arXiv:2605.23904  (Yang et al., May 2026)")
    print("  Backend:  Antigravity IDE (interactive bridge mode)")
    print("="* 60)
    print()
    print("  How this works:")
    print("    Each LLM prompt is sent to your Antigravity chat pane.")
    print("    After the AI responds there, COPY its reply and PASTE")
    print("    it into this terminal, then press ENTER on a blank line.")
    print("    SkillOpt reads your paste and continues automatically.")
    print()

    if cfg.dry_run:
        print("  [DryRun] Running with 1 epoch, max 3 train docs.\n")

    # ── 1. Load source documents ───────────────────────────────────────────────
    from src.ingest import ingest_documents
    docs = ingest_documents()
    if not docs:
        print("[ERROR] No documents found. Check DOCUMENTS_DIR in config.py")
        return ""

    # ── 2. Split into train / selection / test ─────────────────────────────────
    epochs_to_run = 1 if cfg.dry_run else cfg.epochs
    docs_train, docs_sel, docs_test = _split_docs(
        docs, cfg.split_ratio, cfg.split_seed, dry_run=cfg.dry_run
    )
    print(f"  Split: {len(docs_train)} train / {len(docs_sel)} selection / "
          f"{len(docs_test)} test docs")

    if not docs_sel:
        print("[ERROR] Selection split is empty — add more documents.")
        return ""

    # ── 3. Load initial skill ──────────────────────────────────────────────────
    # Priority: existing best_skill.md > initial_skill.md > embedded default
    best_path    = _best_skill_path()
    initial_path = _initial_skill_path()

    if os.path.isfile(best_path):
        skill_text = load_skill(best_path)
        print(f"  Resuming from existing best_skill.md ({len(skill_text)} chars)")
    elif os.path.isfile(initial_path):
        skill_text = load_skill(initial_path)
        print(f"  Starting from initial_skill.md ({len(skill_text)} chars)")
    else:
        print("[ERROR] Neither best_skill.md nor initial_skill.md found in wiki/.")
        print("        Run: python main.py --skillopt-init  to create the seed skill.")
        return ""

    # ── 4. Compute baseline selection score ────────────────────────────────────
    print("\n[Baseline] Evaluating initial skill on selection split...")
    best_val_score = _evaluate_on_split(docs_sel, skill_text, cfg, label="baseline")
    best_skill     = skill_text
    print(f"[Baseline] Initial selection score: {best_val_score:.4f}\n")

    # ── 5. Training loop ───────────────────────────────────────────────────────
    rejected_buffer: list[dict] = []
    all_epoch_results = []
    run_log = {
        "started":      datetime.utcnow().isoformat(),
        "config":       cfg.__dict__,
        "n_train":      len(docs_train),
        "n_sel":        len(docs_sel),
        "n_test":       len(docs_test),
        "baseline_val": best_val_score,
        "epochs":       [],
    }

    prev_epoch_skill: str | None = None

    for epoch in range(epochs_to_run):
        skill_before_epoch = skill_text

        skill_text, best_val_score, rejected_buffer, step_results = run_epoch(
            docs_train=docs_train,
            docs_val=docs_sel,
            skill_text=skill_text,
            best_val_score=best_val_score,
            epoch=epoch,
            cfg=cfg,
            rejected_buffer=rejected_buffer,
            prev_epoch_skill=prev_epoch_skill,
        )

        # Update best skill if this epoch improved it
        if skill_text != best_skill:
            best_skill = skill_text
            if not cfg.dry_run:
                save_skill(best_path, best_skill)
                print(f"\n  [Saved] best_skill.md updated "
                      f"(hash={hash_skill(best_skill)})")

        # Log epoch summary
        epoch_log = {
            "epoch":       epoch + 1,
            "val_score":   best_val_score,
            "skill_hash":  hash_skill(skill_text),
            "steps":       [r.to_dict() for r in step_results],
        }
        run_log["epochs"].append(epoch_log)

        # Save log after every epoch (safe resume)
        if not cfg.dry_run:
            log = _load_log(_log_path())
            log.setdefault("runs", [])
            # Upsert current run (find by started timestamp)
            existing = [r for r in log["runs"]
                        if r.get("started") == run_log["started"]]
            if existing:
                existing[0].update(run_log)
            else:
                log["runs"].append(run_log)
            _save_log(_log_path(), log)

        prev_epoch_skill = skill_before_epoch

        if cfg.dry_run:
            print("\n  [DryRun] Finished 1-epoch smoke test successfully.")
            break

    # ── 6. Final test-split evaluation ────────────────────────────────────────
    if docs_test and not cfg.dry_run:
        print("\n[Test] Evaluating best skill on held-out test split...")
        test_score = _evaluate_on_split(docs_test, best_skill, cfg, label="test")
        run_log["test_score"] = test_score
        print(f"[Test] Final test score: {test_score:.4f}  "
              f"(baseline was {run_log['baseline_val']:.4f}, "
              f"delta={test_score - run_log['baseline_val']:+.4f})\n")

        # Persist final test score to log
        log = _load_log(_log_path())
        for r in log.get("runs", []):
            if r.get("started") == run_log["started"]:
                r["test_score"] = test_score
        _save_log(_log_path(), log)

    # ── 7. Summary ─────────────────────────────────────────────────────────────
    print("=" * 60)
    print("  SkillOpt training complete!")
    print(f"  Best skill:  {best_path}")
    print(f"  Train log:   {_log_path()}")
    print(f"  Val score:   {best_val_score:.4f}  "
          f"(baseline: {run_log['baseline_val']:.4f}, "
          f"delta={best_val_score - run_log['baseline_val']:+.4f})")
    print("=" * 60 + "\n")

    # Restore the original backend so --query mode is unaffected.
    _cfg.SKILLOPT_BACKEND = _original_backend

    return best_path


# ── Standalone ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SkillOpt training harness")
    parser.add_argument("--epochs",    type=int,   default=DEFAULT_CONFIG.epochs)
    parser.add_argument("--batch",     type=int,   default=DEFAULT_CONFIG.rollout_batch_size)
    parser.add_argument("--budget",    type=int,   default=DEFAULT_CONFIG.edit_budget)
    parser.add_argument("--schedule",  type=str,   default=DEFAULT_CONFIG.lr_schedule)
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    cfg = SkillOptConfig(
        epochs=args.epochs,
        rollout_batch_size=args.batch,
        edit_budget=args.budget,
        lr_schedule=args.schedule,
        dry_run=args.dry_run,
    )
    train(cfg)
