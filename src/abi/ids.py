"""Deterministic identifier helpers for Phase 0 records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_id(prefix: str, payload: dict[str, Any], length: int = 16) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def run_id(created_at: str) -> str:
    return stable_id("run", {"created_at": created_at})


def artifact_id(
    run_id_value: str,
    artifact_type: str,
    path: str,
    content_hash: str,
    parent_ids: list[str],
    lineage_id: str | None = None,
) -> str:
    return stable_id(
        "artifact",
        {
            "run_id": run_id_value,
            "lineage_id": lineage_id,
            "type": artifact_type,
            "path": path,
            "hash": content_hash,
            "parent_ids": parent_ids,
        },
    )


def gate_id(run_id_value: str, gate_name: str, lineage_id: str | None = None) -> str:
    return stable_id(
        "gate",
        {
            "run_id": run_id_value,
            "lineage_id": lineage_id,
            "gate_name": gate_name,
        },
    )
