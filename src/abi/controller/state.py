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
