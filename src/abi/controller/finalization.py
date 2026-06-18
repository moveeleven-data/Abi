"""Fail-closed finalization checks for Phase 0."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from abi.controller.gates import REQUIRED_PHASE0_GATES, GateRecord, required_gate_records


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
) -> FinalizationReport:
    gate_map = required_gate_records(
        connection,
        run_id=run_id,
        required_gates=required_gates,
        lineage_id=lineage_id,
    )
    missing_gates = [gate_name for gate_name, gate in gate_map.items() if gate is None]
    failed_gates = [
        gate_name
        for gate_name, gate in gate_map.items()
        if gate is not None and _gate_blocks_finalization(gate)
    ]

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


def _gate_blocks_finalization(gate: GateRecord) -> bool:
    return not gate.passed or bool(gate.blocking_defects)
