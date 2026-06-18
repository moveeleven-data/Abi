"""Shared packet-writing helpers for deterministic artifact modules."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, get_artifact, register_artifact
from abi.hashing import sha256_file
from abi.ids import artifact_id as make_artifact_id


PACKET_SCHEMA_VERSION = "1"


def create_packet_dir(base_dir: Path | str) -> Path:
    packet_base = Path(base_dir)
    packet_base.mkdir(parents=True, exist_ok=True)
    used_numbers = []
    for child in packet_base.iterdir():
        if child.is_dir() and child.name.startswith("packet_"):
            suffix = child.name.removeprefix("packet_")
            if suffix.isdecimal():
                used_numbers.append(int(suffix))
    next_number = max(used_numbers, default=0) + 1
    return packet_base / f"packet_{next_number:04d}"


def build_artifact_envelope(
    *,
    artifact_type: str,
    run_id: str,
    lineage_id: str | None,
    parent_ids: list[str],
    created_by: str,
    payload: object,
    fixture_only: bool | None = None,
) -> dict[str, object]:
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "run_id": run_id,
        "lineage_id": lineage_id,
        "parent_ids": list(parent_ids),
        "created_by": created_by,
        "fixture_only": fixture_only,
        "model_call_id": None,
        "payload": payload,
    }


class PacketWriter:
    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        run_id: str,
        packet_dir: Path | str,
        lineage_id: str | None,
        created_by: str,
        fixture_only: bool | None = None,
    ) -> None:
        self.connection = connection
        self.run_id = run_id
        self.packet_dir = Path(packet_dir)
        self.lineage_id = lineage_id
        self.created_by = created_by
        self.fixture_only = fixture_only
        self.packet_dir.mkdir(parents=True, exist_ok=True)

    def write_artifact(
        self,
        artifact_type: str,
        payload: object,
        parent_ids: list[str] | None = None,
    ) -> ArtifactRecord:
        parent_id_values = list(parent_ids or [])
        path = self.packet_dir / f"{artifact_type}.json"
        envelope = build_artifact_envelope(
            artifact_type=artifact_type,
            run_id=self.run_id,
            lineage_id=self.lineage_id,
            parent_ids=parent_id_values,
            created_by=self.created_by,
            fixture_only=self.fixture_only,
            payload=payload,
        )
        path.write_text(_canonical_json(envelope), encoding="utf-8", newline="\n")
        return self._register_or_get_artifact(
            artifact_type=artifact_type,
            path=path,
            parent_ids=parent_id_values,
        )

    def _register_or_get_artifact(
        self,
        *,
        artifact_type: str,
        path: Path,
        parent_ids: list[str],
    ) -> ArtifactRecord:
        content_hash = sha256_file(path)
        expected_id = make_artifact_id(
            self.run_id,
            artifact_type,
            str(path),
            content_hash,
            parent_ids,
            self.lineage_id,
        )
        existing = get_artifact(self.connection, expected_id)
        if existing is not None:
            return existing
        return register_artifact(
            self.connection,
            run_id=self.run_id,
            artifact_type=artifact_type,
            path=path,
            lineage_id=self.lineage_id,
            parent_ids=parent_ids,
        )


def read_json_file(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
