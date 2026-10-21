"""
main.py — Master runner for the Karpathy Wiki pipeline.

Usage:
    python main.py                   ← Full pipeline + interactive query
    python main.py --generate-only   ← Only Stage 2+3 (no cross-link, no query)
    python main.py --crosslink-only  ← Only Stage 4
    python main.py --query           ← Interactive AI query (Antigravity AI answers)
    python main.py --query --skillopt← Query with transparent SkillOpt learning
    python main.py --query --search  ← Keyword search (no AI, instant results)
    python main.py --update <file>   ← Stage 5: update with new document

SkillOpt flags (Stage 6 — no API key needed, uses Antigravity AI):

  Transparent mode (recommended): attach to your normal query session
    python main.py --query --skillopt
    python main.py --query --skillopt --min-queries 3
      └─ During queries: completely silent (just a one-liner per query).
         At session exit: ONE paste of the AI’s edit proposals → skill updated.

  Standalone training mode: runs full SkillOpt loop with explicit paste per step
    python main.py --skillopt-init   ← Create best_skill.md from seed
    python main.py --skillopt        ← Run full SkillOpt training
    python main.py --skillopt --dry-run
    python main.py --skillopt --epochs 2
    python main.py --skillopt --budget 4
    python main.py --skillopt --schedule cosine
    python main.py --skillopt-status ← Show last training run summary
    python main.py --generate-only --skill ← Generate wiki using best_skill.md

  Interactive bridge: SkillOpt sends each prompt to the Antigravity chat pane
  via agentapi.bat.  After the AI responds there, copy the reply and paste it
  into this terminal, then press ENTER on a blank line.  No API key needed.
"""

import sys
import os


def main():
    args = sys.argv[1:]
    args_set = set(args)

    # ── Web UI: Interactive Browser App ───────────────────────────────────────
    if "--ui" in args_set or "--server" in args_set:
        from app import app
        port = int(os.environ.get("PORT", 5000))
        print("=" * 65)
        print(f"[WEB UI] Launching Karpathy Wiki at: http://localhost:{port}")
        print("=" * 65)
        app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
        return

    # ── SkillOpt: initialise seed skill ───────────────────────────────────────
    if "--skillopt-init" in args_set:
        _run_skillopt_init()
        return

    # ── SkillOpt: show training status ────────────────────────────────────────
    if "--skillopt-status" in args_set:
        _run_skillopt_status()
        return

    # ── SkillOpt: training loop ───────────────────────────────────────────────
    if "--skillopt" in args_set:
        _run_skillopt(args)
        return

    # ── Stage 5: update with new document ─────────────────────────────────────
    if "--update" in args:
        idx = args.index("--update")
        doc_path = args[idx + 1] if idx + 1 < len(args) else None
        from src.update import run as update_run
        update_run(doc_path)
        return

    # ── Query only ───────────────────────────────────────────────────────────
    if "--query" in args_set:
        from src.query import run as query_run
        search_only  = "--search" in args_set or "-s" in args_set
        observer     = None

        # --query --skillopt  → attach transparent SkillOpt observer
        if "--skillopt" in args_set and not search_only:
            from src.skillopt.observer import QueryObserver
            import config
            min_q    = _get_int_arg(args, "--min-queries", 3)
            observer = QueryObserver(
                skill_path=config.SKILL_PATH,
                n_trigger=min_q,
            )
            if not os.path.isfile(config.SKILL_PATH):
                print("[SkillOpt] best_skill.md not found.")
                print("           Run: python main.py --skillopt-init  first.")
                observer = None

        query_run(search_only=search_only, observer=observer)
        return

    # ── Cross-link only ───────────────────────────────────────────────────────
    if "--crosslink-only" in args_set:
        from src.crosslink import run as crosslink_run
        crosslink_run()
        return

    # ── Generate only (optionally with learned skill) ─────────────────────────
    if "--generate-only" in args_set:
        from src.generate_wiki import run as gen_run
        if "--skill" in args_set:
            _apply_best_skill_and_run(gen_run)
        else:
            gen_run()
        return

    # ── Full pipeline (default) ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Karpathy Wiki — Full Pipeline")
    print("=" * 60 + "\n")

    from src.generate_wiki import run as gen_run
    gen_run()

    from src.crosslink import run as crosslink_run
    crosslink_run()

    print("\n" + "=" * 60)
    print("  Pipeline complete! Entering query mode...")
    print("=" * 60 + "\n")

    from src.query import run as query_run
    query_run()


# ── SkillOpt helpers ──────────────────────────────────────────────────────────

def _get_int_arg(args: list[str], flag: str, default: int) -> int:
    """Parse --flag <int> from args list, return default if not found."""
    try:
        idx = args.index(flag)
        return int(args[idx + 1])
    except (ValueError, IndexError):
        return default


def _run_skillopt_init():
    """Copy initial_skill.md → best_skill.md to create the seed skill."""
    import shutil
    import config

    initial = os.path.join(config.WIKI_DIR, "initial_skill.md")
    best    = config.SKILL_PATH

    if not os.path.isfile(initial):
        print(f"[ERROR] initial_skill.md not found at: {initial}")
        print("        Run the full pipeline first to create the wiki/ directory.")
        return

    if os.path.isfile(best):
        ans = input(f"best_skill.md already exists. Overwrite? (y/N): ").strip().lower()
        if ans != "y":
            print("[Aborted]")
            return

    shutil.copy(initial, best)
    print(f"[SkillOpt] Seed skill created: {best}")
    print("           Now run: python main.py --skillopt  to start training.")


def _run_skillopt(args: list[str]):
    """Parse args and run the SkillOpt training loop."""
    from src.skillopt.config_defaults import SkillOptConfig
    from src.skillopt.trainer import train

    def _get_arg(flag: str, default):
        try:
            idx = args.index(flag)
            return type(default)(args[idx + 1])
        except (ValueError, IndexError):
            return default

    cfg = SkillOptConfig(
        epochs             = _get_arg("--epochs",   4),
        rollout_batch_size = _get_arg("--batch",   10),
        edit_budget        = _get_arg("--budget",   4),
        lr_schedule        = _get_arg("--schedule", "cosine"),
        dry_run            = "--dry-run" in args,
        verbose            = "--quiet" not in args,
    )

    train(cfg)


def _run_skillopt_status():
    """Print a summary of the last SkillOpt training run."""
    import json
    import config

    log_path = config.SKILLOPT_LOG
    if not os.path.isfile(log_path):
        print("[SkillOpt] No training log found. Run --skillopt first.")
        return

    with open(log_path, "r", encoding="utf-8") as f:
        log = json.load(f)

    runs = log.get("runs", [])
    if not runs:
        print("[SkillOpt] Log exists but contains no runs.")
        return

    last = runs[-1]
    print("\n" + "=" * 60)
    print("  SkillOpt — Last Training Run Summary")
    print("=" * 60)
    print(f"  Started:    {last.get('started', '?')}")
    print(f"  Docs:       train={last.get('n_train','?')}  "
          f"sel={last.get('n_sel','?')}  test={last.get('n_test','?')}")
    print(f"  Baseline:   {last.get('baseline_val', 0):.4f}")

    epochs = last.get("epochs", [])
    for ep in epochs:
        print(f"  Epoch {ep['epoch']:>2}:  val={ep['val_score']:.4f}  "
              f"hash={ep.get('skill_hash','?')}")

    if "test_score" in last:
        baseline = last.get("baseline_val", 0)
        test     = last["test_score"]
        print(f"\n  Test score: {test:.4f}  (Δ={test - baseline:+.4f} vs baseline)")

    skill_path = config.SKILL_PATH
    if os.path.isfile(skill_path):
        size = os.path.getsize(skill_path)
        print(f"\n  Best skill: {skill_path}  ({size:,} bytes)")
    print("=" * 60 + "\n")


def _apply_best_skill_and_run(gen_run_fn):
    """Patch generate_wiki.SYSTEM_PROMPT with best_skill.md, then run."""
    import config
    import src.generate_wiki as gw

    skill_path = config.SKILL_PATH
    if not os.path.isfile(skill_path):
        print(f"[WARN] best_skill.md not found at {skill_path}. "
              f"Using default skill.")
        gen_run_fn()
        return

    with open(skill_path, "r", encoding="utf-8") as f:
        skill_text = f.read()

    original_prompt = gw.SYSTEM_PROMPT
    gw.SYSTEM_PROMPT = skill_text
    print(f"[Skill] Loaded best_skill.md ({len(skill_text)} chars) as system prompt.")
    try:
        gen_run_fn()
    finally:
        gw.SYSTEM_PROMPT = original_prompt


if __name__ == "__main__":
    main()
