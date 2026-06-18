"""SQLite initialization and connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from abi.config import AbiConfig


SCHEMA_VERSION = "1"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    active_phase TEXT NOT NULL,
    best_lineage_id TEXT,
    strongest_rival_lineage_id TEXT,
    final_artifact_id TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    lineage_id TEXT,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    parent_ids_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    lineage_id TEXT,
    gate_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    blocking_defects_json TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    UNIQUE (run_id, lineage_id, gate_name)
);

CREATE TABLE IF NOT EXISTS model_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    worker_role TEXT NOT NULL,
    prompt_contract_id TEXT NOT NULL,
    input_artifact_ids_json TEXT NOT NULL,
    input_packet_path TEXT,
    input_hash TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    raw_output_path TEXT,
    parsed_output_artifact_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    cost_micros INTEGER,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (parsed_output_artifact_id) REFERENCES artifacts(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_gates_run_id ON gates(run_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_run_id ON model_calls(run_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(config: AbiConfig) -> None:
    config.ensure_directories()
    with connect(config.db_path) as connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )


def get_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "runs": _count(connection, "runs"),
        "artifacts": _count(connection, "artifacts"),
        "gates": _count(connection, "gates"),
    }


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])
