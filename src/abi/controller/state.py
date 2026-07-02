"""Run state helpers owned by the controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3

from abi.config import AbiConfig
from abi.db import connect, initialize_database
from abi.ids import run_id as make_run_id


ACTIVE_STATUSES = ("initialized", "active")
PHASE0_ACTIVE_PHASE = "phase0"
PHASE1_ABI_EAR_ACTIVE_PHASE = "phase1_abi_ear"
PHASE2_MINIMAL_REREAD_ACTIVE_PHASE = "phase2_minimal_reread"
PHASE4_PRODUCTION_HARNESS_ACTIVE_PHASE = "phase4_production_harness"
PHASE5_HUMAN_CALIBRATION_ACTIVE_PHASE = "phase5_human_calibration"
PHASE8_LIVE_ABI_EAR_PACKET_ACTIVE_PHASE = "phase8_live_abi_ear_packet"
PHASE9_LIVE_MINIMAL_REREAD_ACTIVE_PHASE = "phase9_live_minimal_reread"
PHASE10_PRODUCTION_RUN_ACTIVE_PHASE = "phase10_source_to_artifact_production_run"
PHASE11_EVALUATION_BASELINES_ACTIVE_PHASE = "phase11_evaluation_baselines"
PHASE13_FINAL_ARTIFACT_PACKET_ACTIVE_PHASE = "phase13_final_artifact_packet"
PHASE16_FIRST_REAL_CANDIDATE_SET_ACTIVE_PHASE = "phase16_first_real_candidate_set"
AUTONOMOUS_INTERNAL_READER_LAB_ACTIVE_PHASE = "autonomous_internal_reader_lab_v1"
AUTONOMOUS_INTERNAL_READER_STATE_EVALUATION_ACTIVE_PHASE = (
    "autonomous_internal_reader_state_evaluation_v1"
)
AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE = "autonomous_closed_loop_revision_v1"
AUTONOMOUS_EVIDENCE_SYNTHESIS_ACTIVE_PHASE = "autonomous_evidence_synthesis_v1"
AUTONOMOUS_EVIDENCE_LOOP_REVIEW_ACTIVE_PHASE = "evidence_loop_review_v1"
AUTONOMOUS_LOOP_INTEGRITY_CLEANUP_ACTIVE_PHASE = "loop_integrity_cleanup_v1"
AUTONOMOUS_SUPERVISED_CYCLE_AUTHORIZATION_ACTIVE_PHASE = (
    "supervised_cycle_authorization_v1"
)
AUTONOMOUS_ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_ACTIVE_PHASE = (
    "architecture_evidence_risk_checkpoint_v1"
)
AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE = "bounded_macro_recomposition_v1"
AUTONOMOUS_NEXT_TARGET_STRATEGY_ACTIVE_PHASE = "autonomous_next_target_strategy_v1"
AUTONOMOUS_CHECKPOINT_STRATEGY_DIRECTION_REVIEW_ACTIVE_PHASE = (
    "checkpoint_strategy_direction_review_v1"
)
AUTONOMOUS_POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_ACTIVE_PHASE = (
    "post_local_residual_strategy_synthesis_v1"
)
AUTONOMOUS_RESIDUAL_TARGET_SELECTION_ACTIVE_PHASE = "residual_target_selection_v1"
AUTONOMOUS_RESIDUAL_WORK_ORDER_ACTIVE_PHASE = "residual_work_order_v1"
AUTONOMOUS_RESIDUAL_GENERATION_AUTHORIZATION_ACTIVE_PHASE = (
    "residual_generation_authorization_v1"
)
AUTONOMOUS_RESIDUAL_CANDIDATE_GENERATION_ACTIVE_PHASE = (
    "residual_candidate_generation_v1"
)
AUTONOMOUS_OBJECT_EVENT_RECOMPOSITION_ACTIVE_PHASE = "object_event_recomposition_v1"


@dataclass(frozen=True)
class RunRecord:
    id: str
    created_at: str
    status: str
    active_phase: str
    best_lineage_id: str | None
    strongest_rival_lineage_id: str | None
    final_artifact_id: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def ensure_active_run(config: AbiConfig) -> tuple[RunRecord, bool]:
    initialize_database(config)
    with connect(config.db_path) as connection:
        existing = get_active_run(connection)
        if existing is not None:
            ensure_run_folders(config, existing.id)
            return existing, False
        return create_run(connection, config), True


def create_run(
    connection: sqlite3.Connection,
    config: AbiConfig,
    *,
    created_at: str | None = None,
) -> RunRecord:
    created_at_value = created_at or utc_now()
    record = RunRecord(
        id=make_run_id(created_at_value),
        created_at=created_at_value,
        status="initialized",
        active_phase=PHASE0_ACTIVE_PHASE,
        best_lineage_id=None,
        strongest_rival_lineage_id=None,
        final_artifact_id=None,
    )
    connection.execute(
        """
        INSERT INTO runs (
            id,
            created_at,
            status,
            active_phase,
            best_lineage_id,
            strongest_rival_lineage_id,
            final_artifact_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.id,
            record.created_at,
            record.status,
            record.active_phase,
            record.best_lineage_id,
            record.strongest_rival_lineage_id,
            record.final_artifact_id,
        ),
    )
    ensure_run_folders(config, record.id)
    return record


def ensure_run_folders(config: AbiConfig, run_id: str) -> None:
    config.run_dir(run_id).mkdir(parents=True, exist_ok=True)
    config.output_dir(run_id).mkdir(parents=True, exist_ok=True)


def get_active_run(connection: sqlite3.Connection) -> RunRecord | None:
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    row = connection.execute(
        f"""
        SELECT *
        FROM runs
        WHERE status IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ACTIVE_STATUSES,
    ).fetchone()
    return row_to_run(row) if row is not None else None


def get_latest_run(connection: sqlite3.Connection) -> RunRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM runs
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    return row_to_run(row) if row is not None else None


def get_run(connection: sqlite3.Connection, run_id: str) -> RunRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    return row_to_run(row) if row is not None else None


def list_runs(connection: sqlite3.Connection) -> list[RunRecord]:
    rows = connection.execute(
        """
        SELECT *
        FROM runs
        ORDER BY created_at, id
        """
    ).fetchall()
    return [row_to_run(row) for row in rows]


def set_active_phase(connection: sqlite3.Connection, run_id: str, active_phase: str) -> None:
    connection.execute(
        """
        UPDATE runs
        SET active_phase = ?
        WHERE id = ?
        """,
        (active_phase, run_id),
    )


def run_to_dict(run: RunRecord) -> dict[str, object]:
    return {
        "id": run.id,
        "created_at": run.created_at,
        "status": run.status,
        "active_phase": run.active_phase,
        "best_lineage_id": run.best_lineage_id,
        "strongest_rival_lineage_id": run.strongest_rival_lineage_id,
        "final_artifact_id": run.final_artifact_id,
    }


def row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=row["id"],
        created_at=row["created_at"],
        status=row["status"],
        active_phase=row["active_phase"],
        best_lineage_id=row["best_lineage_id"],
        strongest_rival_lineage_id=row["strongest_rival_lineage_id"],
        final_artifact_id=row["final_artifact_id"],
    )
