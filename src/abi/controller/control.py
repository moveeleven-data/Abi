"""Controller inspection helpers for Phase 3."""

from __future__ import annotations

import sqlite3

from abi.controller.decision import BlockerReport, ControllerDecision
from abi.controller.policy import DEFAULT_FINALIZATION_POLICY, GatePolicy, evaluate_gate_policy
from abi.controller.state import RunRecord, get_active_run, get_latest_run


def inspect_active_run(
    connection: sqlite3.Connection,
    *,
    policy: GatePolicy = DEFAULT_FINALIZATION_POLICY,
) -> ControllerDecision | None:
    run = get_active_run(connection) or get_latest_run(connection)
    if run is None:
        return None
    return decide_run(connection, run=run, policy=policy)


def decide_run(
    connection: sqlite3.Connection,
    *,
    run: RunRecord,
    policy: GatePolicy = DEFAULT_FINALIZATION_POLICY,
) -> ControllerDecision:
    evaluation = evaluate_gate_policy(connection, run_id=run.id, policy=policy)
    blockers = _blockers_from_evaluation(evaluation.missing_gates, evaluation.failed_gates)
    blockers.extend(_blockers_from_blocking_defects(evaluation.blocking_defects))

    if evaluation.eligible:
        decision = "finalize"
        eligible_to_finalize = True
        recommended_next_action = "finalize"
        message = "Run is eligible for controller-owned finalization."
    else:
        decision = "refuse_finalization"
        eligible_to_finalize = False
        recommended_next_action = "resolve required gate blockers before finalization"
        message = "Finalization refused by controller policy."

    blocker_report = BlockerReport(
        run_id=run.id,
        active_phase=run.active_phase,
        status=run.status,
        blockers=blockers,
        missing_gates=evaluation.missing_gates,
        failed_gates=evaluation.failed_gates,
        blocking_defects=evaluation.blocking_defects,
        recommended_next_action=recommended_next_action,
    )
    return ControllerDecision(
        run_id=run.id,
        decision=decision,
        active_phase=run.active_phase,
        status=run.status,
        eligible_to_finalize=eligible_to_finalize,
        missing_gates=evaluation.missing_gates,
        failed_gates=evaluation.failed_gates,
        blocking_defects=evaluation.blocking_defects,
        recommended_next_action=recommended_next_action,
        message=message,
        blocker_report=blocker_report,
    )


def _blockers_from_evaluation(missing_gates: list[str], failed_gates: list[str]) -> list[str]:
    blockers = []
    blockers.extend(f"missing required gate: {gate_name}" for gate_name in missing_gates)
    blockers.extend(f"failed required gate: {gate_name}" for gate_name in failed_gates)
    return blockers


def _blockers_from_blocking_defects(blocking_defects: dict[str, list[str]]) -> list[str]:
    return [
        f"blocking defects on gate {gate_name}: {', '.join(defects)}"
        for gate_name, defects in blocking_defects.items()
    ]
