"""Policy-driven fail-closed finalization checks."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from abi.controller.gates import REQUIRED_PHASE0_GATES
from abi.controller.policy import DEFAULT_FINALIZATION_POLICY, GatePolicy, evaluate_gate_policy


@dataclass(frozen=True)
class FinalizationReport:
    run_id: str
    refused: bool
    missing_gates: list[str]
    failed_gates: list[str]
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "refused": self.refused,
            "missing_gates": self.missing_gates,
            "failed_gates": self.failed_gates,
            "message": self.message,
        }


def check_finalization(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    required_gates: tuple[str, ...] = REQUIRED_PHASE0_GATES,
    lineage_id: str | None = None,
    policy: GatePolicy | None = None,
) -> FinalizationReport:
    gate_policy = policy or GatePolicy(
        name=DEFAULT_FINALIZATION_POLICY.name,
        required_gates=required_gates,
        lineage_id=lineage_id,
    )
    evaluation = evaluate_gate_policy(
        connection,
        run_id=run_id,
        policy=gate_policy,
    )
    missing_gates = evaluation.missing_gates
    failed_gates = _legacy_failed_gates(evaluation.failed_gates, evaluation.blocking_defects)

    if missing_gates or failed_gates:
        details = []
        if missing_gates:
            details.append("missing gates: " + ", ".join(missing_gates))
        if failed_gates:
            details.append("failed gates: " + ", ".join(failed_gates))
        return FinalizationReport(
            run_id=run_id,
            refused=True,
            missing_gates=missing_gates,
            failed_gates=failed_gates,
            message="Finalization refused; " + "; ".join(details) + ".",
        )

    return FinalizationReport(
        run_id=run_id,
        refused=False,
        missing_gates=[],
        failed_gates=[],
        message="Finalization gates are satisfied.",
    )


def _legacy_failed_gates(
    failed_gates: list[str],
    blocking_defects: dict[str, list[str]],
) -> list[str]:
    legacy_failed = list(failed_gates)
    legacy_failed.extend(
        gate_name for gate_name in blocking_defects if gate_name not in legacy_failed
    )
    return legacy_failed
