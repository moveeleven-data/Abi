"""Command line interface for Abi Phase 0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.state import ensure_active_run, get_latest_run
from abi.db import connect, get_counts, initialize_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abi", description="Abi Phase 0 infrastructure CLI")
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


if __name__ == "__main__":
    sys.exit(main())
