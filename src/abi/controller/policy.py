"""Gate policies for fail-closed controller decisions."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from abi.controller.gates import REQUIRED_PHASE0_GATES, GateRecord, required_gate_records


@dataclass(frozen=True)
class GatePolicy:
    name: str
    required_gates: tuple[str, ...]
    lineage_id: str | None = None


@dataclass(frozen=True)
class GatePolicyEvaluation:
    policy: GatePolicy
    run_id: str
    gate_records: dict[str, GateRecord | None]
    missing_gates: list[str]
    failed_gates: list[str]
    blocking_defects: dict[str, list[str]]

    @property
    def eligible(self) -> bool:
        return not self.missing_gates and not self.failed_gates and not self.blocking_defects

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": {
                "name": self.policy.name,
                "required_gates": list(self.policy.required_gates),
                "lineage_id": self.policy.lineage_id,
            },
            "run_id": self.run_id,
            "missing_gates": self.missing_gates,
            "failed_gates": self.failed_gates,
            "blocking_defects": self.blocking_defects,
            "eligible": self.eligible,
        }


DEFAULT_FINALIZATION_POLICY = GatePolicy(
    name="phase0_finalization",
    required_gates=REQUIRED_PHASE0_GATES,
)


def evaluate_gate_policy(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    policy: GatePolicy = DEFAULT_FINALIZATION_POLICY,
) -> GatePolicyEvaluation:
    gate_records = required_gate_records(
        connection,
        run_id=run_id,
        required_gates=policy.required_gates,
        lineage_id=policy.lineage_id,
    )
    missing_gates = [gate_name for gate_name, gate in gate_records.items() if gate is None]
    failed_gates = [
        gate_name
        for gate_name, gate in gate_records.items()
        if gate is not None and not gate.passed
    ]
    blocking_defects = {
        gate_name: list(gate.blocking_defects)
        for gate_name, gate in gate_records.items()
        if gate is not None and gate.blocking_defects
    }
    return GatePolicyEvaluation(
        policy=policy,
        run_id=run_id,
        gate_records=gate_records,
        missing_gates=missing_gates,
        failed_gates=failed_gates,
        blocking_defects=blocking_defects,
    )
