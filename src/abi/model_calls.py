"""SQLite-backed model call records for the sealed fake-client driver."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3


MODEL_CALL_SUCCESS = "success"
MODEL_CALL_VALIDATION_FAILED = "validation_failed"
MODEL_CALL_CLIENT_FAILED = "client_failed"


@dataclass(frozen=True)
class ModelCallRecord:
    id: str
    run_id: str
    worker_role: str
    prompt_contract_id: str
    input_artifact_ids: list[str]
    input_packet_path: str | None
    input_hash: str
    schema_name: str
    schema_version: str
    provider: str
    model: str
    raw_output_path: str | None
    parsed_output_artifact_id: str | None
    status: str
    error_message: str | None
    created_at: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_micros: int | None = None

    @property
    def input_artifact_ids_json(self) -> str:
        return json.dumps(self.input_artifact_ids, sort_keys=True, separators=(",", ":"))


def record_model_call(connection: sqlite3.Connection, record: ModelCallRecord) -> ModelCallRecord:
    connection.execute(
        """
        INSERT INTO model_calls (
            id,
            run_id,
            worker_role,
            prompt_contract_id,
            input_artifact_ids_json,
            input_packet_path,
            input_hash,
            schema_name,
            schema_version,
            provider,
            model,
            raw_output_path,
            parsed_output_artifact_id,
            status,
            error_message,
            created_at,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost_micros
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.id,
            record.run_id,
            record.worker_role,
            record.prompt_contract_id,
            record.input_artifact_ids_json,
            record.input_packet_path,
            record.input_hash,
            record.schema_name,
            record.schema_version,
            record.provider,
            record.model,
            record.raw_output_path,
            record.parsed_output_artifact_id,
            record.status,
            record.error_message,
            record.created_at,
            record.prompt_tokens,
            record.completion_tokens,
            record.total_tokens,
            record.cost_micros,
        ),
    )
    return record


def link_model_call_parsed_artifact(
    connection: sqlite3.Connection,
    *,
    model_call_id: str,
    parsed_output_artifact_id: str,
) -> ModelCallRecord:
    connection.execute(
        """
        UPDATE model_calls
        SET parsed_output_artifact_id = ?
        WHERE id = ?
        """,
        (parsed_output_artifact_id, model_call_id),
    )
    record = get_model_call(connection, model_call_id)
    if record is None:
        raise ValueError(f"model call not found: {model_call_id}")
    return record


def get_model_call(connection: sqlite3.Connection, model_call_id: str) -> ModelCallRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM model_calls
        WHERE id = ?
        """,
        (model_call_id,),
    ).fetchone()
    return row_to_model_call(row) if row is not None else None


def list_model_calls(
    connection: sqlite3.Connection,
    *,
    run_id: str | None = None,
) -> list[ModelCallRecord]:
    if run_id is None:
        rows = connection.execute(
            """
            SELECT *
            FROM model_calls
            ORDER BY created_at, id
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT *
            FROM model_calls
            WHERE run_id = ?
            ORDER BY created_at, id
            """,
            (run_id,),
        ).fetchall()
    return [row_to_model_call(row) for row in rows]


def model_call_to_dict(record: ModelCallRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "run_id": record.run_id,
        "worker_role": record.worker_role,
        "prompt_contract_id": record.prompt_contract_id,
        "input_artifact_ids": list(record.input_artifact_ids),
        "input_packet_path": record.input_packet_path,
        "input_hash": record.input_hash,
        "schema_name": record.schema_name,
        "schema_version": record.schema_version,
        "provider": record.provider,
        "model": record.model,
        "raw_output_path": record.raw_output_path,
        "parsed_output_artifact_id": record.parsed_output_artifact_id,
        "status": record.status,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "total_tokens": record.total_tokens,
        "cost_micros": record.cost_micros,
    }


def row_to_model_call(row: sqlite3.Row) -> ModelCallRecord:
    return ModelCallRecord(
        id=row["id"],
        run_id=row["run_id"],
        worker_role=row["worker_role"],
        prompt_contract_id=row["prompt_contract_id"],
        input_artifact_ids=json.loads(row["input_artifact_ids_json"]),
        input_packet_path=row["input_packet_path"],
        input_hash=row["input_hash"],
        schema_name=row["schema_name"],
        schema_version=row["schema_version"],
        provider=row["provider"],
        model=row["model"],
        raw_output_path=row["raw_output_path"],
        parsed_output_artifact_id=row["parsed_output_artifact_id"],
        status=row["status"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        total_tokens=row["total_tokens"],
        cost_micros=row["cost_micros"],
    )
