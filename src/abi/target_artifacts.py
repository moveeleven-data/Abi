"""Preferred loaders for residual target artifacts.

Residual work-order packets kept object-motion filenames for historical
compatibility after additional target adapters were introduced. New packets write
generic aliases; these helpers prefer the generic names and fall back to legacy
names for old packets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from abi.packets import read_json_file


GENERIC_TARGET_UNIT_MAP_ARTIFACT = "target_unit_map"
LEGACY_TARGET_UNIT_MAP_ARTIFACT = "object_motion_target_unit_map"
GENERIC_TARGET_DIAGNOSTIC_ARTIFACT = "target_diagnostic"
LEGACY_TARGET_DIAGNOSTIC_ARTIFACT = "object_motion_causality_diagnostic"


@dataclass(frozen=True)
class TargetArtifactLoadResult:
    payload: dict[str, Any]
    generic_artifact_used: bool
    legacy_fallback_used: bool
    source_artifact_name: str
    target_adapter_id: str | None
    selected_residual_target_id: str | None
    unit_map_kind: str | None = None
    diagnostic_kind: str | None = None

    def metadata(self) -> dict[str, object]:
        data: dict[str, object] = {
            "generic_artifact_used": self.generic_artifact_used,
            "legacy_fallback_used": self.legacy_fallback_used,
            "source_artifact_name": self.source_artifact_name,
            "target_adapter_id": self.target_adapter_id,
            "selected_residual_target_id": self.selected_residual_target_id,
        }
        if self.unit_map_kind is not None:
            data["unit_map_kind"] = self.unit_map_kind
        if self.diagnostic_kind is not None:
            data["diagnostic_kind"] = self.diagnostic_kind
        return data


def read_target_unit_map(packet_dir: Path | str) -> TargetArtifactLoadResult:
    result = _read_preferred_target_artifact(
        packet_dir=packet_dir,
        generic_artifact_type=GENERIC_TARGET_UNIT_MAP_ARTIFACT,
        legacy_artifact_type=LEGACY_TARGET_UNIT_MAP_ARTIFACT,
    )
    return TargetArtifactLoadResult(
        **result,
        unit_map_kind=_first_string(
            result["payload"].get("unit_map_kind"),
            result["payload"].get("target_adapter_id"),
        ),
    )


def read_target_diagnostic(packet_dir: Path | str) -> TargetArtifactLoadResult:
    result = _read_preferred_target_artifact(
        packet_dir=packet_dir,
        generic_artifact_type=GENERIC_TARGET_DIAGNOSTIC_ARTIFACT,
        legacy_artifact_type=LEGACY_TARGET_DIAGNOSTIC_ARTIFACT,
    )
    return TargetArtifactLoadResult(
        **result,
        diagnostic_kind=_first_string(
            result["payload"].get("diagnostic_kind"),
            result["payload"].get("target_adapter_id"),
        ),
    )


def _read_preferred_target_artifact(
    *,
    packet_dir: Path | str,
    generic_artifact_type: str,
    legacy_artifact_type: str,
) -> dict[str, Any]:
    directory = Path(packet_dir)
    generic_path = directory / f"{generic_artifact_type}.json"
    legacy_path = directory / f"{legacy_artifact_type}.json"
    if generic_path.exists():
        payload = _read_payload(generic_path)
        source_artifact_name = generic_artifact_type
        generic_artifact_used = True
    elif legacy_path.exists():
        payload = _read_payload(legacy_path)
        source_artifact_name = legacy_artifact_type
        generic_artifact_used = False
    else:
        raise FileNotFoundError(
            f"missing {generic_path.name} and fallback {legacy_path.name}"
        )
    return {
        "payload": payload,
        "generic_artifact_used": generic_artifact_used,
        "legacy_fallback_used": not generic_artifact_used,
        "source_artifact_name": source_artifact_name,
        "target_adapter_id": _first_string(payload.get("target_adapter_id")),
        "selected_residual_target_id": _first_string(
            payload.get("selected_residual_target_id"),
            payload.get("target_scope"),
            payload.get("target_movement"),
        ),
    }


def _read_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} has no object payload")
    return payload


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None
