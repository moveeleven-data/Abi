"""Command line interface for Abi."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from abi.artifacts import artifact_to_dict, get_artifact, list_all_artifacts
from abi.config import AbiConfig
from abi.controller.control import inspect_active_run
from abi.controller.finalization import check_finalization
from abi.controller.state import ensure_active_run, get_latest_run, get_run, list_runs, run_to_dict
from abi.db import connect, get_counts, initialize_database
from abi.live_model import LIVE_WORKERS, run_live_abi_ear_worker
from abi.model_calls import get_model_call, list_model_calls, model_call_to_dict
from abi.model_driver import run_model_driver_demo
from abi.modules.abi_ear import run_abi_ear_demo
from abi.modules.human_calibration import run_human_calibration_demo
from abi.modules.live_abi_ear import (
    LIVE_ABI_EAR_CLIENTS,
    LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
    run_live_abi_ear_packet_demo,
)
from abi.modules.production_harness import run_production_harness_demo
from abi.modules.reread import run_reread_demo
from abi.packets import read_json_file


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
    ear_live_parser = ear_subparsers.add_parser(
        "live-demo",
        help="Run the guarded live Abi Ear packet pipeline",
    )
    ear_live_parser.add_argument(
        "--client",
        choices=LIVE_ABI_EAR_CLIENTS,
        required=True,
        help="Packet model client to use.",
    )
    ear_live_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the OpenAI client to make live model calls.",
    )
    ear_live_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for the packet.",
    )
    reread_parser = subparsers.add_parser("reread", help="Run deterministic minimal reread commands")
    reread_subparsers = reread_parser.add_subparsers(dest="reread_command", required=True)
    reread_subparsers.add_parser("demo", help="Run the deterministic minimal reread benchmark")
    harness_parser = subparsers.add_parser("harness", help="Run deterministic production harness commands")
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command", required=True)
    harness_subparsers.add_parser("demo", help="Run the deterministic production harness scaffold")
    calibration_parser = subparsers.add_parser(
        "calibration",
        help="Run deterministic human calibration commands",
    )
    calibration_subparsers = calibration_parser.add_subparsers(
        dest="calibration_command",
        required=True,
    )
    calibration_subparsers.add_parser("demo", help="Run the deterministic calibration scaffold")
    controller_parser = subparsers.add_parser("controller", help="Inspect fail-closed controller state")
    controller_subparsers = controller_parser.add_subparsers(
        dest="controller_command",
        required=True,
    )
    controller_subparsers.add_parser("status", help="Emit structured controller decision status")
    controller_subparsers.add_parser("blockers", help="Emit structured controller blocker report")
    controller_subparsers.add_parser("demo", help="Inspect or create a run and show refusal decision")
    artifact_parser = subparsers.add_parser("artifact", help="Inspect registered artifacts")
    artifact_subparsers = artifact_parser.add_subparsers(
        dest="artifact_command",
        required=True,
    )
    artifact_subparsers.add_parser("list", help="List registered artifacts")
    artifact_show_parser = artifact_subparsers.add_parser("show", help="Show one artifact")
    artifact_show_parser.add_argument("artifact_id", help="Registered artifact ID")
    run_parser = subparsers.add_parser("run", help="Inspect runs")
    run_subparsers = run_parser.add_subparsers(dest="run_command", required=True)
    run_subparsers.add_parser("list", help="List runs")
    run_show_parser = run_subparsers.add_parser("show", help="Show one run")
    run_show_parser.add_argument("run_id", help="Run ID")
    run_subparsers.add_parser("latest", help="Show the latest run")
    model_driver_parser = subparsers.add_parser(
        "model-driver",
        help="Run sealed fake-client model-driver commands",
    )
    model_driver_subparsers = model_driver_parser.add_subparsers(
        dest="model_driver_command",
        required=True,
    )
    model_driver_demo_parser = model_driver_subparsers.add_parser(
        "demo",
        help="Run the fake-client structured-output demo",
    )
    model_driver_demo_parser.add_argument(
        "--mode",
        choices=("valid", "minimal", "invalid_json", "malformed", "failure"),
        default="valid",
        help="Fake client mode.",
    )
    model_driver_live_parser = model_driver_subparsers.add_parser(
        "live-demo",
        help="Run the guarded live Abi Ear germ-analysis worker",
    )
    model_driver_live_parser.add_argument(
        "--worker",
        choices=LIVE_WORKERS,
        required=True,
        help="Live worker to run.",
    )
    model_driver_live_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the command to make a live model call.",
    )
    model_call_parser = subparsers.add_parser("model-call", help="Inspect model call records")
    model_call_subparsers = model_call_parser.add_subparsers(
        dest="model_call_command",
        required=True,
    )
    model_call_subparsers.add_parser("list", help="List model call records")
    model_call_show_parser = model_call_subparsers.add_parser("show", help="Show one model call")
    model_call_show_parser.add_argument("model_call_id", help="Model call ID")
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
    if args.command == "ear" and args.ear_command == "live-demo":
        return _cmd_ear_live_demo(
            config,
            client_name=args.client,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "reread" and args.reread_command == "demo":
        return _cmd_reread_demo(config)
    if args.command == "harness" and args.harness_command == "demo":
        return _cmd_harness_demo(config)
    if args.command == "calibration" and args.calibration_command == "demo":
        return _cmd_calibration_demo(config)
    if args.command == "controller" and args.controller_command == "status":
        return _cmd_controller_status(config)
    if args.command == "controller" and args.controller_command == "blockers":
        return _cmd_controller_blockers(config)
    if args.command == "controller" and args.controller_command == "demo":
        return _cmd_controller_demo(config)
    if args.command == "artifact" and args.artifact_command == "list":
        return _cmd_artifact_list(config)
    if args.command == "artifact" and args.artifact_command == "show":
        return _cmd_artifact_show(config, args.artifact_id)
    if args.command == "run" and args.run_command == "list":
        return _cmd_run_list(config)
    if args.command == "run" and args.run_command == "show":
        return _cmd_run_show(config, args.run_id)
    if args.command == "run" and args.run_command == "latest":
        return _cmd_run_latest(config)
    if args.command == "model-driver" and args.model_driver_command == "demo":
        return _cmd_model_driver_demo(config, args.mode)
    if args.command == "model-driver" and args.model_driver_command == "live-demo":
        return _cmd_model_driver_live_demo(
            config,
            worker=args.worker,
            allow_live_model=args.allow_live_model,
        )
    if args.command == "model-call" and args.model_call_command == "list":
        return _cmd_model_call_list(config)
    if args.command == "model-call" and args.model_call_command == "show":
        return _cmd_model_call_show(config, args.model_call_id)

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
        "latest_run": run_to_dict(latest_run) if latest_run is not None else None,
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


def _cmd_ear_live_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_live_abi_ear_packet_demo(
        config,
        client_name=client_name,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_reread_demo(config: AbiConfig) -> int:
    result = run_reread_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_harness_demo(config: AbiConfig) -> int:
    result = run_production_harness_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_calibration_demo(config: AbiConfig) -> int:
    result = run_human_calibration_demo(config)
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


def _cmd_artifact_list(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        artifacts = list_all_artifacts(connection)
    payload = {"artifacts": [artifact_to_dict(artifact) for artifact in artifacts]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_artifact_show(config: AbiConfig, artifact_id: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        artifact = get_artifact(connection, artifact_id)
    if artifact is None:
        payload = {
            "artifact": None,
            "message": f"Artifact not found: {artifact_id}",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    payload = {
        "artifact": artifact_to_dict(artifact),
        "content": None,
    }
    try:
        payload["content"] = read_json_file(artifact.path)
    except (OSError, json.JSONDecodeError):
        payload["content"] = None
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_run_list(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        runs = list_runs(connection)
    payload = {"runs": [run_to_dict(run) for run in runs]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_run_show(config: AbiConfig, run_id: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        run = get_run(connection, run_id)
    if run is None:
        payload = {
            "run": None,
            "message": f"Run not found: {run_id}",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"run": run_to_dict(run)}, indent=2, sort_keys=True))
    return 0


def _cmd_run_latest(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        run = get_latest_run(connection)
    if run is None:
        payload = {
            "run": None,
            "message": "No run exists.",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"run": run_to_dict(run)}, indent=2, sort_keys=True))
    return 0


def _cmd_model_driver_demo(config: AbiConfig, mode: str) -> int:
    result = run_model_driver_demo(config, mode=mode)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0 if result.accepted else 1


def _cmd_model_driver_live_demo(
    config: AbiConfig,
    *,
    worker: str,
    allow_live_model: bool,
) -> int:
    result = run_live_abi_ear_worker(
        config,
        worker=worker,
        allow_live_model=allow_live_model,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_model_call_list(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        records = list_model_calls(connection)
    payload = {"model_calls": [model_call_to_dict(record) for record in records]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_model_call_show(config: AbiConfig, model_call_id: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        record = get_model_call(connection, model_call_id)
    if record is None:
        payload = {
            "model_call": None,
            "message": f"Model call not found: {model_call_id}",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"model_call": model_call_to_dict(record)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
