"""Command line interface for Abi."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from abi.config import AbiConfig
from abi.controller.control import inspect_active_run
from abi.controller.finalization import check_finalization
from abi.controller.state import ensure_active_run, get_latest_run
from abi.db import connect, get_counts, initialize_database
from abi.modules.abi_ear import run_abi_ear_demo
from abi.modules.production_harness import run_production_harness_demo
from abi.modules.reread import run_reread_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abi", description="Abi infrastructure CLI")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create Phase 0 folders, database, and an active run")
    subparsers.add_parser("status", help="Report current Phase 0 state")
    subparsers.add_parser("finalize", help="Run fail-closed finalization checks")
    ear_parser = subparsers.add_parser("ear", help="Run deterministic Abi Ear commands")
    ear_subparsers = ear_parser.add_subparsers(dest="ear_command", required=True)
    ear_subparsers.add_parser("demo", help="Run the deterministic Abi Ear benchmark")
    reread_parser = subparsers.add_parser("reread", help="Run deterministic minimal reread commands")
    reread_subparsers = reread_parser.add_subparsers(dest="reread_command", required=True)
    reread_subparsers.add_parser("demo", help="Run the deterministic minimal reread benchmark")
    harness_parser = subparsers.add_parser("harness", help="Run deterministic production harness commands")
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command", required=True)
    harness_subparsers.add_parser("demo", help="Run the deterministic production harness scaffold")
    controller_parser = subparsers.add_parser("controller", help="Inspect fail-closed controller state")
    controller_subparsers = controller_parser.add_subparsers(
        dest="controller_command",
        required=True,
    )
    controller_subparsers.add_parser("status", help="Emit structured controller decision status")
    controller_subparsers.add_parser("blockers", help="Emit structured controller blocker report")
    controller_subparsers.add_parser("demo", help="Inspect or create a run and show refusal decision")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AbiConfig.from_env(root=args.root)

    if args.command == "init":
        return _cmd_init(config)
    if args.command == "status":
        return _cmd_status(config)
    if args.command == "finalize":
        return _cmd_finalize(config)
    if args.command == "ear" and args.ear_command == "demo":
        return _cmd_ear_demo(config)
    if args.command == "reread" and args.reread_command == "demo":
        return _cmd_reread_demo(config)
    if args.command == "harness" and args.harness_command == "demo":
        return _cmd_harness_demo(config)
    if args.command == "controller" and args.controller_command == "status":
        return _cmd_controller_status(config)
    if args.command == "controller" and args.controller_command == "blockers":
        return _cmd_controller_blockers(config)
    if args.command == "controller" and args.controller_command == "demo":
        return _cmd_controller_demo(config)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _cmd_init(config: AbiConfig) -> int:
    run, created = ensure_active_run(config)
    payload = {
        "database_path": str(config.db_path),
        "runs_dir": str(config.runs_dir),
        "outputs_dir": str(config.outputs_dir),
        "active_run_id": run.id,
        "created_run": created,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_status(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        counts = get_counts(connection)
        latest_run = get_latest_run(connection)
    payload = {
        "database_path": str(config.db_path),
        "run_count": counts["runs"],
        "latest_run": latest_run.__dict__ if latest_run is not None else None,
        "artifact_count": counts["artifacts"],
        "gate_count": counts["gates"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_finalize(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        latest_run = get_latest_run(connection)
        if latest_run is None:
            payload = {
                "run_id": None,
                "refused": True,
                "missing_gates": [],
                "failed_gates": [],
                "message": "Finalization refused; no run exists.",
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 1
        report = check_finalization(connection, run_id=latest_run.id)

    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 1 if report.refused else 0


def _cmd_ear_demo(config: AbiConfig) -> int:
    result = run_abi_ear_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_reread_demo(config: AbiConfig) -> int:
    result = run_reread_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_harness_demo(config: AbiConfig) -> int:
    result = run_production_harness_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_controller_status(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
    if decision is None:
        payload = {
            "decision": None,
            "message": "No active run exists.",
        }
    else:
        payload = decision.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_controller_blockers(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
    if decision is None:
        payload = {
            "blocker_report": None,
            "message": "No active run exists.",
        }
    else:
        payload = decision.blocker_report.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_controller_demo(config: AbiConfig) -> int:
    ensure_active_run(config)
    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
