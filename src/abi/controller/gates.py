"""Gate records for fail-closed Phase 0 finalization."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3

from abi.controller.state import utc_now
from abi.ids import gate_id as make_gate_id


REQUIRED_PHASE0_GATES = (
    "infrastructure_initialized",
    "artifact_registry_ready",
    "required_phase0_tests_passed",
)


@dataclass(frozen=True)
class GateRecord:
    id: str
    run_id: str
    lineage_id: str | None
    gate_name: str
    passed: bool
    blocking_defects: list[str]
    evaluated_at: str

    @property
    def blocking_defects_json(self) -> str:
        return json.dumps(self.blocking_defects, sort_keys=True, separators=(",", ":"))


def record_gate(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    gate_name: str,
    passed: bool,
    blocking_defects: list[str] | None = None,
    lineage_id: str | None = None,
    evaluated_at: str | None = None,
) -> GateRecord:
    defects = list(blocking_defects or [])
    record = GateRecord(
        id=make_gate_id(run_id, gate_name, lineage_id),
        run_id=run_id,
        lineage_id=lineage_id,
        gate_name=gate_name,
        passed=passed,
        blocking_defects=defects,
        evaluated_at=evaluated_at or utc_now(),
    )
    connection.execute(
        """
        INSERT INTO gates (
            id,
            run_id,
            lineage_id,
            gate_name,
            passed,
            blocking_defects_json,
            evaluated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id)
        DO UPDATE SET
            passed = excluded.passed,
            blocking_defects_json = excluded.blocking_defects_json,
            evaluated_at = excluded.evaluated_at
        """,
        (
            record.id,
            record.run_id,
            record.lineage_id,
            record.gate_name,
            int(record.passed),
            record.blocking_defects_json,
            record.evaluated_at,
        ),
    )
    return record


def get_gate(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    gate_name: str,
    lineage_id: str | None = None,
) -> GateRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM gates
        WHERE run_id = ?
          AND gate_name = ?
          AND (
              (lineage_id IS NULL AND ? IS NULL)
              OR lineage_id = ?
          )
        """,
        (run_id, gate_name, lineage_id, lineage_id),
    ).fetchone()
    return row_to_gate(row) if row is not None else None


def list_gates(connection: sqlite3.Connection, run_id: str) -> list[GateRecord]:
    rows = connection.execute(
        """
        SELECT *
        FROM gates
        WHERE run_id = ?
        ORDER BY evaluated_at, gate_name
        """,
        (run_id,),
    ).fetchall()
    return [row_to_gate(row) for row in rows]


def required_gate_records(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    required_gates: tuple[str, ...] = REQUIRED_PHASE0_GATES,
    lineage_id: str | None = None,
) -> dict[str, GateRecord | None]:
    return {
        gate_name: get_gate(
            connection,
            run_id=run_id,
            gate_name=gate_name,
            lineage_id=lineage_id,
        )
        for gate_name in required_gates
    }


def row_to_gate(row: sqlite3.Row) -> GateRecord:
    return GateRecord(
        id=row["id"],
        run_id=row["run_id"],
        lineage_id=row["lineage_id"],
        gate_name=row["gate_name"],
        passed=bool(row["passed"]),
        blocking_defects=json.loads(row["blocking_defects_json"]),
        evaluated_at=row["evaluated_at"],
    )
