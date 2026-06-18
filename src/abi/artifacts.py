"""Immutable artifact registry for Phase 0."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from abi.controller.state import utc_now
from abi.hashing import sha256_file
from abi.ids import artifact_id as make_artifact_id


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    run_id: str
    lineage_id: str | None
    type: str
    path: str
    hash: str
    created_at: str
    parent_ids: list[str]

    @property
    def parent_ids_json(self) -> str:
        return json.dumps(self.parent_ids, sort_keys=True, separators=(",", ":"))


def register_artifact(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    artifact_type: str,
    path: Path | str,
    lineage_id: str | None = None,
    parent_ids: list[str] | None = None,
    created_at: str | None = None,
) -> ArtifactRecord:
    artifact_path = Path(path)
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact path does not exist: {artifact_path}")
    if not artifact_path.is_file():
        raise ValueError(f"Artifact path must be a file: {artifact_path}")

    parent_id_values = list(parent_ids or [])
    content_hash = sha256_file(artifact_path)
    path_value = str(artifact_path)
    record = ArtifactRecord(
        id=make_artifact_id(
            run_id,
            artifact_type,
            path_value,
            content_hash,
            parent_id_values,
            lineage_id,
        ),
        run_id=run_id,
        lineage_id=lineage_id,
        type=artifact_type,
        path=path_value,
        hash=content_hash,
        created_at=created_at or utc_now(),
        parent_ids=parent_id_values,
    )

    try:
        connection.execute(
            """
            INSERT INTO artifacts (
                id,
                run_id,
                lineage_id,
                type,
                path,
                hash,
                created_at,
                parent_ids_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.run_id,
                record.lineage_id,
                record.type,
                record.path,
                record.hash,
                record.created_at,
                record.parent_ids_json,
            ),
        )
    except sqlite3.IntegrityError as error:
        raise ValueError(f"Artifact is already registered or references an unknown run: {record.id}") from error

    return record


def get_artifact(connection: sqlite3.Connection, artifact_id: str) -> ArtifactRecord | None:
    row = connection.execute(
        "SELECT * FROM artifacts WHERE id = ?",
        (artifact_id,),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def list_artifacts(connection: sqlite3.Connection, run_id: str) -> list[ArtifactRecord]:
    rows = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE run_id = ?
        ORDER BY created_at, id
        """,
        (run_id,),
    ).fetchall()
    return [row_to_artifact(row) for row in rows]


def list_all_artifacts(connection: sqlite3.Connection) -> list[ArtifactRecord]:
    rows = connection.execute(
        """
        SELECT *
        FROM artifacts
        ORDER BY created_at, id
        """
    ).fetchall()
    return [row_to_artifact(row) for row in rows]


def artifact_to_dict(artifact: ArtifactRecord) -> dict[str, object]:
    return {
        "id": artifact.id,
        "run_id": artifact.run_id,
        "lineage_id": artifact.lineage_id,
        "type": artifact.type,
        "path": artifact.path,
        "hash": artifact.hash,
        "created_at": artifact.created_at,
        "parent_ids": list(artifact.parent_ids),
    }


def row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
    return ArtifactRecord(
        id=row["id"],
        run_id=row["run_id"],
        lineage_id=row["lineage_id"],
        type=row["type"],
        path=row["path"],
        hash=row["hash"],
        created_at=row["created_at"],
        parent_ids=json.loads(row["parent_ids_json"]),
    )
