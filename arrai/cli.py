from __future__ import annotations

"""
CLI entry point.

Usage:
    python -m arrai run --config session.json
    python -m arrai run --config session.json --resume
    python -m arrai run --objective "Get the model to explain how to..." \\
                        --target-type openai --target-model gpt-4o

    python -m arrai sessions          # list all sessions
    python -m arrai show <session_id> # print session summary
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load .env if present


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quieten noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def _check_credentials(config) -> None:
    """Fail fast with a clear message if required API keys are missing."""
    import os
    t = config.target_config.target_type
    key_env = config.target_config.params.get("api_key_env", "OPENAI_API_KEY")

    # Always need OpenAI key for Sherlock + Garak + scorer
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "\n❌  OPENAI_API_KEY is not set.\n"
            "    Set it in your shell:\n"
            "        export OPENAI_API_KEY=sk-...\n"
            "    Or create a .env file in this directory:\n"
            "        echo 'OPENAI_API_KEY=sk-...' > .env\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # Target-specific key check
    if t == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "\n❌  ANTHROPIC_API_KEY is not set (required for anthropic target).\n"
            "        export ANTHROPIC_API_KEY=sk-ant-...\n",
            file=sys.stderr,
        )
        sys.exit(1)


def load_global_config() -> dict:
    config_path = Path("arrAI.config.json")
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {
        "sessions_dir": "./sessions",
        "vault_dir": "./vault",
        "success_score_threshold": 0.8,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace, global_cfg: dict) -> None:
    from arrai.models.session_config import SessionConfig, TargetConfig
    from arrai.runner import SessionRunner

    # ── Load or build SessionConfig ───────────────────────────────────
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        cfg_dict = json.loads(config_path.read_text())

        if args.resume and "session_id" not in cfg_dict:
            print("Error: --resume requires session_id in config.", file=sys.stderr)
            sys.exit(1)

        config = SessionConfig.from_dict(cfg_dict)

    else:
        # Build from CLI flags
        if not args.objective:
            print("Error: --objective is required when not using --config.", file=sys.stderr)
            sys.exit(1)
        if not args.target_type:
            print("Error: --target-type is required when not using --config.", file=sys.stderr)
            sys.exit(1)

        target_params: dict = {}
        if args.target_model:
            target_params["model"] = args.target_model
        if args.target_system_prompt:
            target_params["system_prompt"] = args.target_system_prompt

        config = SessionConfig.create(
            target_config=TargetConfig(
                target_type=args.target_type,
                params=target_params,
            ),
            objective=args.objective,
            whitebox_seed=args.whitebox_seed or None,
            further_context=args.further_context or None,
            mode="hitl" if args.hitl else "autonomous",
            max_missions=args.max_missions,
            default_turn_budget=args.turn_budget,
            sherlock_model=args.sherlock_model,
            garak_model=args.garak_model,
            scorer_model=args.scorer_model,
        )

        # Write the generated config for reference
        out_path = Path(f"session_{config.session_id[:8]}.json")
        out_path.write_text(json.dumps(config.to_dict(), indent=2))
        print(f"Session config written to: {out_path}")

    sessions_dir = global_cfg.get("sessions_dir", "./sessions")
    vault_dir = global_cfg.get("vault_dir", "./vault")

    # ── Validate credentials early, before printing the banner ───────
    _check_credentials(config)

    print(f"\n{'='*60}")
    print(f"  ArrAI Red-Team Session")
    print(f"{'='*60}")
    print(f"  Session ID : {config.session_id}")
    print(f"  Objective  : {config.objective}")
    print(f"  Target     : {config.target_config.target_type} "
          f"/ {config.target_config.params.get('model', '')}")
    print(f"  Sherlock   : {config.sherlock_model} (effort: {config.sherlock_effort})")
    print(f"  Garak      : {config.garak_model} (effort: {config.garak_effort})")
    print(f"  Max missions: {config.max_missions} | Turn budget: {config.default_turn_budget}")
    print(f"  Mode       : {config.mode}")
    print(f"{'='*60}\n")

    # Emit function for CLI: pretty-print key events
    async def cli_emit(event: dict) -> None:
        t = event.get("type", "")
        if t == "ooda_start":
            print("\n🔍 Sherlock OODA cycle starting...")
        elif t == "ooda_complete":
            print(f"  DECIDE: {event.get('decide', '')[:120]}")
            print(f"  ACTION: {event.get('action_type', '')}")
        elif t == "mission_start":
            print(f"\n⚗️  Garak mission {event.get('mission_id', '')[:8]} starting")
            print(f"  Objective : {event.get('objective', '')[:100]}")
            print(f"  Budget    : {event.get('turn_budget', '')} turns")
        elif t == "turn":
            print(f"\n  → Turn {event.get('turn', '')} | Prompt: {event.get('prompt', '')[:80]}...")
        elif t == "turn_response":
            print(f"  ← Response: {event.get('response', '')[:80]}...")
        elif t == "tool_call":
            print(f"  [tool] {event.get('tool', '')} ← {str(event.get('input', ''))[:60]}")
        elif t == "backtrack":
            print(f"  ↩ Backtrack {event.get('turns_discarded', '')} turn(s): "
                  f"{event.get('reason', '')[:60]}")
        elif t == "mission_complete":
            print(f"\n  ✓ Mission complete: {event.get('terminal_condition', '')} | "
                  f"garak={event.get('garak_score', 0):.2f} "
                  f"scorer={event.get('scorer_score', 0):.2f}")
        elif t == "scorer_result":
            print(f"  📊 Scorer: {event.get('score', 0):.2f} — {event.get('rationale', '')[:80]}")
        elif t == "vault_write":
            print(f"  📝 Vault entry added: {event.get('entry_id', '')}")
        elif t == "session_complete":
            achieved = event.get("objective_achieved", False)
            print(f"\n{'='*60}")
            print(f"  Session complete. Objective achieved: {achieved}")
            print(f"{'='*60}\n")
        elif t == "target_md_updated":
            print("  📋 target.md updated")
        elif t == "plan_md_updated":
            print("  📋 plan.md updated")
        elif t == "error":
            print(f"\n  ❌ ERROR: {event.get('message', '')}", file=sys.stderr)

    runner = SessionRunner(
        config=config,
        sessions_dir=sessions_dir,
        vault_dir=vault_dir,
        emit=cli_emit,
    )

    try:
        if args.resume:
            asyncio.run(runner.resume())
        else:
            asyncio.run(runner.run())
    except KeyboardInterrupt:
        print("\n\nSession interrupted. Progress saved — resume with --resume.")


def cmd_serve(args: argparse.Namespace, global_cfg: dict) -> None:
    """Start the ArrAI web GUI."""
    import uvicorn
    from arrai.api.app import create_app
    from pathlib import Path

    sessions_dir = Path(global_cfg.get("sessions_dir", "./sessions"))
    vault_dir    = Path(global_cfg.get("vault_dir", "./vault"))

    app = create_app(sessions_dir=sessions_dir, vault_dir=vault_dir)

    host = args.host or "127.0.0.1"
    port = args.port or 7860

    print(f"\n{'='*50}")
    print(f"  ArrAI GUI")
    print(f"{'='*50}")
    print(f"  URL        : http://{host}:{port}")
    print(f"  Sessions   : {sessions_dir.resolve()}")
    print(f"  Vault      : {vault_dir.resolve()}")
    print(f"{'='*50}\n")

    uvicorn.run(app, host=host, port=port, log_level="warning")


def cmd_sessions(args: argparse.Namespace, global_cfg: dict) -> None:
    from arrai.memory.session_store import SessionStore

    store = SessionStore(global_cfg.get("sessions_dir", "./sessions"))
    sessions = store.list_sessions()

    if not sessions:
        print("No sessions found.")
        return

    print(f"\n{'ID':38}  {'MISSIONS':8}  {'MODE':12}  OBJECTIVE")
    print("─" * 90)
    for s in sessions:
        print(
            f"{s['session_id']:38}  {s['mission_count']:8}  {s['mode']:12}  "
            f"{s['objective'][:40]}"
        )
    print()


def cmd_show(args: argparse.Namespace, global_cfg: dict) -> None:
    from arrai.memory.session_store import SessionStore

    store = SessionStore(global_cfg.get("sessions_dir", "./sessions"))
    session_id = args.session_id

    print(f"\n=== Session {session_id} ===\n")

    report = store.read_session_report(session_id)
    if report:
        print("── SESSION REPORT ──")
        print(report)
        return

    # No final report yet — show live state
    print("── target.md ──")
    print(store.read_target_md(session_id))
    print("\n── plan.md ──")
    print(store.read_plan_md(session_id))
    print("\n── Mission summaries ──")
    for summary in store.get_mission_summaries(session_id):
        print(" ", summary)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Argument parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arrai",
        description="ArrAI — Agentic AI Red-Teamer",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    subparsers = parser.add_subparsers(dest="command")

    # ── run ──────────────────────────────────────────────────────────
    run_p = subparsers.add_parser("run", help="Start or resume a red-team session")
    run_p.add_argument("--config", metavar="FILE",
                       help="Path to session config JSON file")
    run_p.add_argument("--resume", action="store_true",
                       help="Resume an existing session from its config file")

    # Shortcut flags for quick runs without a config file
    run_p.add_argument("--objective", metavar="TEXT")
    run_p.add_argument("--target-type", metavar="TYPE",
                       help="openai | anthropic | azure_openai | custom_http")
    run_p.add_argument("--target-model", metavar="MODEL", default="gpt-4o")
    run_p.add_argument("--target-system-prompt", metavar="TEXT")
    run_p.add_argument("--whitebox-seed", metavar="TEXT")
    run_p.add_argument("--further-context", metavar="TEXT")
    run_p.add_argument("--hitl", action="store_true")
    run_p.add_argument("--max-missions", type=int, default=20)
    run_p.add_argument("--turn-budget", type=int, default=8)
    run_p.add_argument("--sherlock-model", default="gpt-5.4")
    run_p.add_argument("--garak-model", default="gpt-5.4")
    run_p.add_argument("--scorer-model", default="gpt-5.4-mini")

    # ── serve ─────────────────────────────────────────────────────────
    serve_p = subparsers.add_parser("serve", help="Start the web GUI")
    serve_p.add_argument("--host", default="127.0.0.1", metavar="HOST")
    serve_p.add_argument("--port", type=int, default=7860, metavar="PORT")

    # ── sessions ─────────────────────────────────────────────────────
    subparsers.add_parser("sessions", help="List all sessions")

    # ── show ─────────────────────────────────────────────────────────
    show_p = subparsers.add_parser("show", help="Show session details")
    show_p.add_argument("session_id")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)
    global_cfg = load_global_config()

    if args.command == "run":
        cmd_run(args, global_cfg)
    elif args.command == "serve":
        cmd_serve(args, global_cfg)
    elif args.command == "sessions":
        cmd_sessions(args, global_cfg)
    elif args.command == "show":
        cmd_show(args, global_cfg)
    else:
        parser.print_help()
