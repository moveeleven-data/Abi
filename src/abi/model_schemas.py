"""Narrow structured-output schemas for Phase 6B fake model calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any


class ModelValidationError(ValueError):
    """Raised when fake structured output fails schema validation."""


class WorkerRole(str, Enum):
    ABI_EAR_GERM_ANALYZER = "abi_ear_germ_analyzer"
    ABI_EAR_FIELD_MODEL_BUILDER = "abi_ear_field_model_builder"


@dataclass(frozen=True)
class WorkerSchema:
    name: str
    version: str
    artifact_type: str


ABI_EAR_GERM_ANALYSIS_SCHEMA = WorkerSchema(
    name="AbiEarGermAnalysisModelOutput",
    version="1",
    artifact_type="model_abi_ear_germ_analysis",
)

ABI_EAR_FIELD_MODEL_SCHEMA = WorkerSchema(
    name="AbiEarFieldModelOutput",
    version="1",
    artifact_type="model_abi_ear_field_model",
)


def abi_ear_germ_analysis_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "germ_text": {"type": "string"},
            "word_forces": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "word": {"type": "string"},
                        "force": {"type": "string"},
                    },
                    "required": ["word", "force"],
                },
            },
            "fertility_score": {"type": "number"},
            "risks": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["germ_text", "word_forces", "fertility_score", "risks"],
    }


def abi_ear_field_model_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "germ_text": {"type": "string"},
            "objects": {
                "type": "array",
                "items": {"type": "string"},
            },
            "local_laws": {
                "type": "array",
                "items": {"type": "string"},
            },
            "latent_oppositions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "negative_space": {
                "type": "array",
                "items": {"type": "string"},
            },
            "scale_ceiling": {"type": "string"},
            "forbidden_imports": {
                "type": "array",
                "items": {"type": "string"},
            },
            "possible_returns": {
                "type": "array",
                "items": {"type": "string"},
            },
            "risks": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "germ_text",
            "objects",
            "local_laws",
            "latent_oppositions",
            "negative_space",
            "scale_ceiling",
            "forbidden_imports",
            "possible_returns",
            "risks",
        ],
    }


def parse_and_validate_structured_output(raw_output: str, schema: WorkerSchema) -> dict[str, Any]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as error:
        raise ModelValidationError(f"invalid JSON: {error.msg}") from error

    if not isinstance(payload, dict):
        raise ModelValidationError("structured output must be a JSON object")
    if schema == ABI_EAR_GERM_ANALYSIS_SCHEMA:
        return _validate_abi_ear_germ_analysis(payload)
    if schema == ABI_EAR_FIELD_MODEL_SCHEMA:
        return _validate_abi_ear_field_model(payload)
    raise ModelValidationError(f"unknown worker schema: {schema.name} v{schema.version}")


def _validate_abi_ear_germ_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "germ_text", str)
    _require_type(payload, "word_forces", list)
    _require_number(payload, "fertility_score")
    _require_type(payload, "risks", list)

    for index, word_force in enumerate(payload["word_forces"]):
        if not isinstance(word_force, dict):
            raise ModelValidationError(f"word_forces[{index}] must be an object")
        _require_type(word_force, "word", str, field_prefix=f"word_forces[{index}].")
        _require_type(word_force, "force", str, field_prefix=f"word_forces[{index}].")

    for index, risk in enumerate(payload["risks"]):
        if not isinstance(risk, str):
            raise ModelValidationError(f"risks[{index}] must be a string")

    return {
        "germ_text": payload["germ_text"],
        "word_forces": payload["word_forces"],
        "fertility_score": float(payload["fertility_score"]),
        "risks": payload["risks"],
    }


def _validate_abi_ear_field_model(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "germ_text", str)
    for key in (
        "objects",
        "local_laws",
        "latent_oppositions",
        "negative_space",
        "forbidden_imports",
        "possible_returns",
        "risks",
    ):
        _require_string_list(payload, key)
    _require_type(payload, "scale_ceiling", str)

    return {
        "germ_text": payload["germ_text"],
        "objects": payload["objects"],
        "local_laws": payload["local_laws"],
        "latent_oppositions": payload["latent_oppositions"],
        "negative_space": payload["negative_space"],
        "scale_ceiling": payload["scale_ceiling"],
        "forbidden_imports": payload["forbidden_imports"],
        "possible_returns": payload["possible_returns"],
        "risks": payload["risks"],
    }


def _require_type(
    payload: dict[str, Any],
    key: str,
    expected_type: type,
    *,
    field_prefix: str = "",
) -> None:
    if key not in payload:
        raise ModelValidationError(f"missing required field: {field_prefix}{key}")
    if not isinstance(payload[key], expected_type):
        raise ModelValidationError(f"{field_prefix}{key} must be {expected_type.__name__}")


def _require_number(payload: dict[str, Any], key: str) -> None:
    if key not in payload:
        raise ModelValidationError(f"missing required field: {key}")
    if isinstance(payload[key], bool) or not isinstance(payload[key], int | float):
        raise ModelValidationError(f"{key} must be a number")


def _require_string_list(payload: dict[str, Any], key: str) -> None:
    _require_type(payload, key, list)
    for index, value in enumerate(payload[key]):
        if not isinstance(value, str):
            raise ModelValidationError(f"{key}[{index}] must be a string")
