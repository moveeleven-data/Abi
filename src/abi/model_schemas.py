"""Structured-output schemas for fake and guarded live model calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any


class ModelValidationError(ValueError):
    """Raised when structured output fails schema validation."""


class WorkerRole(str, Enum):
    ABI_EAR_GERM_ANALYZER = "abi_ear_germ_analyzer"
    ABI_EAR_FIELD_MODEL_BUILDER = "abi_ear_field_model_builder"
    ABI_EAR_VARIANT_GENERATOR = "abi_ear_variant_generator"
    ABI_EAR_MOVE_COMPOSER = "abi_ear_move_composer"
    ABI_EAR_MOVE_RANKER = "abi_ear_move_ranker"
    ABI_EAR_PROSE_INVENTOR = "abi_ear_prose_inventor"
    ABI_EAR_REFINER = "abi_ear_refiner"
    ABI_EAR_REREAD_TRACER = "abi_ear_reread_tracer"


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

ABI_EAR_VARIANTS_SCHEMA = WorkerSchema(
    name="AbiEarVariantsModelOutput",
    version="1",
    artifact_type="model_abi_ear_variants",
)

ABI_EAR_MOVES_SCHEMA = WorkerSchema(
    name="AbiEarMovesModelOutput",
    version="1",
    artifact_type="model_abi_ear_moves",
)

ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA = WorkerSchema(
    name="AbiEarRankedMoveSequenceModelOutput",
    version="1",
    artifact_type="model_abi_ear_ranked_move_sequence",
)

ABI_EAR_PROSE_INVENTIONS_SCHEMA = WorkerSchema(
    name="AbiEarProseInventionsModelOutput",
    version="1",
    artifact_type="model_abi_ear_prose_inventions",
)

ABI_EAR_REFINED_INVENTION_SCHEMA = WorkerSchema(
    name="AbiEarRefinedInventionModelOutput",
    version="1",
    artifact_type="model_abi_ear_refined_invention",
)

ABI_EAR_REREAD_TRACE_SCHEMA = WorkerSchema(
    name="AbiEarRereadTraceModelOutput",
    version="1",
    artifact_type="model_abi_ear_reread_trace",
)

LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS = (
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    ABI_EAR_FIELD_MODEL_SCHEMA,
    ABI_EAR_VARIANTS_SCHEMA,
    ABI_EAR_MOVES_SCHEMA,
    ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA,
    ABI_EAR_PROSE_INVENTIONS_SCHEMA,
    ABI_EAR_REFINED_INVENTION_SCHEMA,
    ABI_EAR_REREAD_TRACE_SCHEMA,
)


def abi_ear_germ_analysis_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "germ_text": {"type": "string"},
            "word_forces": {
                "type": "array",
                "items": _object_schema(
                    {
                        "word": {"type": "string"},
                        "force": {"type": "string"},
                    },
                    ["word", "force"],
                ),
            },
            "fertility_score": {"type": "number"},
            "risks": _string_array_schema(),
        },
        "required": ["germ_text", "word_forces", "fertility_score", "risks"],
    }


def abi_ear_field_model_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "germ_text": {"type": "string"},
            "objects": _string_array_schema(),
            "local_laws": _string_array_schema(),
            "latent_oppositions": _string_array_schema(),
            "negative_space": _string_array_schema(),
            "scale_ceiling": {"type": "string"},
            "forbidden_imports": _string_array_schema(),
            "possible_returns": _string_array_schema(),
            "risks": _string_array_schema(),
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


def abi_ear_variants_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "germ_text": {"type": "string"},
            "variants": {
                "type": "array",
                "items": _object_schema(
                    {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "rationale": {"type": "string"},
                        "predicted_field_shift": {"type": "string"},
                    },
                    ["id", "text", "rationale", "predicted_field_shift"],
                ),
            },
            "risks": _string_array_schema(),
        },
        "required": ["germ_text", "variants", "risks"],
    }


def abi_ear_moves_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "germ_text": {"type": "string"},
            "moves": {
                "type": "array",
                "items": _object_schema(
                    {
                        "id": {"type": "string"},
                        "operation_name": {"type": "string"},
                        "new_material": {"type": "string"},
                        "predicted_field_delta": {"type": "string"},
                        "risk": {"type": "string"},
                    },
                    ["id", "operation_name", "new_material", "predicted_field_delta", "risk"],
                ),
            },
            "risks": _string_array_schema(),
        },
        "required": ["germ_text", "moves", "risks"],
    }


def abi_ear_ranked_move_sequence_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ranked_moves": {
                "type": "array",
                "items": _object_schema(
                    {
                        "rank": {"type": "integer"},
                        "move_id": {"type": "string"},
                        "operation_name": {"type": "string"},
                        "combined_score": {"type": "number"},
                    },
                    ["rank", "move_id", "operation_name", "combined_score"],
                ),
            },
            "selected_sequence": _string_array_schema(),
            "risks": _string_array_schema(),
        },
        "required": ["ranked_moves", "selected_sequence", "risks"],
    }


def abi_ear_prose_inventions_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prose_inventions": {
                "type": "array",
                "items": _object_schema(
                    {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "used_move_ids": _string_array_schema(),
                        "text": {"type": "string"},
                    },
                    ["id", "title", "used_move_ids", "text"],
                ),
            },
            "risks": _string_array_schema(),
        },
        "required": ["prose_inventions", "risks"],
    }


def abi_ear_refined_invention_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "source_invention_ids": _string_array_schema(),
            "used_move_ids": _string_array_schema(),
            "text": {"type": "string"},
            "refinement_notes": _string_array_schema(),
            "risks": _string_array_schema(),
        },
        "required": [
            "source_invention_ids",
            "used_move_ids",
            "text",
            "refinement_notes",
            "risks",
        ],
    }


def abi_ear_reread_trace_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "first_read_opening_interpretation": {"type": "string"},
            "second_read_opening_interpretation": {"type": "string"},
            "changed_opening_words": _string_array_schema(),
            "supporting_lines_or_passages": _string_array_schema(),
            "reread_gain_estimate": {"type": "number"},
            "unsupported_claims": _string_array_schema(),
        },
        "required": [
            "first_read_opening_interpretation",
            "second_read_opening_interpretation",
            "changed_opening_words",
            "supporting_lines_or_passages",
            "reread_gain_estimate",
            "unsupported_claims",
        ],
    }


def json_schema_for_worker_schema(schema: WorkerSchema) -> dict[str, Any]:
    if schema == ABI_EAR_GERM_ANALYSIS_SCHEMA:
        return abi_ear_germ_analysis_json_schema()
    if schema == ABI_EAR_FIELD_MODEL_SCHEMA:
        return abi_ear_field_model_json_schema()
    if schema == ABI_EAR_VARIANTS_SCHEMA:
        return abi_ear_variants_json_schema()
    if schema == ABI_EAR_MOVES_SCHEMA:
        return abi_ear_moves_json_schema()
    if schema == ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA:
        return abi_ear_ranked_move_sequence_json_schema()
    if schema == ABI_EAR_PROSE_INVENTIONS_SCHEMA:
        return abi_ear_prose_inventions_json_schema()
    if schema == ABI_EAR_REFINED_INVENTION_SCHEMA:
        return abi_ear_refined_invention_json_schema()
    if schema == ABI_EAR_REREAD_TRACE_SCHEMA:
        return abi_ear_reread_trace_json_schema()
    raise ModelValidationError(f"unknown worker schema: {schema.name} v{schema.version}")


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
    if schema == ABI_EAR_VARIANTS_SCHEMA:
        return _validate_abi_ear_variants(payload)
    if schema == ABI_EAR_MOVES_SCHEMA:
        return _validate_abi_ear_moves(payload)
    if schema == ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA:
        return _validate_abi_ear_ranked_move_sequence(payload)
    if schema == ABI_EAR_PROSE_INVENTIONS_SCHEMA:
        return _validate_abi_ear_prose_inventions(payload)
    if schema == ABI_EAR_REFINED_INVENTION_SCHEMA:
        return _validate_abi_ear_refined_invention(payload)
    if schema == ABI_EAR_REREAD_TRACE_SCHEMA:
        return _validate_abi_ear_reread_trace(payload)
    raise ModelValidationError(f"unknown worker schema: {schema.name} v{schema.version}")


def _validate_abi_ear_germ_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "germ_text", str)
    _require_type(payload, "word_forces", list)
    _require_number(payload, "fertility_score")
    _require_string_list(payload, "risks")

    word_forces = []
    for index, word_force in enumerate(payload["word_forces"]):
        if not isinstance(word_force, dict):
            raise ModelValidationError(f"word_forces[{index}] must be an object")
        _require_type(word_force, "word", str, field_prefix=f"word_forces[{index}].")
        _require_type(word_force, "force", str, field_prefix=f"word_forces[{index}].")
        word_forces.append(
            {
                "word": word_force["word"],
                "force": word_force["force"],
            }
        )

    return {
        "germ_text": payload["germ_text"],
        "word_forces": word_forces,
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


def _validate_abi_ear_variants(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "germ_text", str)
    _require_type(payload, "variants", list)
    _require_string_list(payload, "risks")
    variants = [
        _validate_object(
            variant,
            f"variants[{index}]",
            ("id", "text", "rationale", "predicted_field_shift"),
        )
        for index, variant in enumerate(payload["variants"])
    ]
    return {
        "germ_text": payload["germ_text"],
        "variants": variants,
        "risks": payload["risks"],
    }


def _validate_abi_ear_moves(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "germ_text", str)
    _require_type(payload, "moves", list)
    _require_string_list(payload, "risks")
    moves = [
        _validate_object(
            move,
            f"moves[{index}]",
            ("id", "operation_name", "new_material", "predicted_field_delta", "risk"),
        )
        for index, move in enumerate(payload["moves"])
    ]
    return {
        "germ_text": payload["germ_text"],
        "moves": moves,
        "risks": payload["risks"],
    }


def _validate_abi_ear_ranked_move_sequence(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "ranked_moves", list)
    _require_string_list(payload, "selected_sequence")
    _require_string_list(payload, "risks")
    ranked_moves = []
    for index, ranked in enumerate(payload["ranked_moves"]):
        if not isinstance(ranked, dict):
            raise ModelValidationError(f"ranked_moves[{index}] must be an object")
        _require_integer(ranked, "rank", field_prefix=f"ranked_moves[{index}].")
        _require_type(ranked, "move_id", str, field_prefix=f"ranked_moves[{index}].")
        _require_type(ranked, "operation_name", str, field_prefix=f"ranked_moves[{index}].")
        _require_number(ranked, "combined_score", field_prefix=f"ranked_moves[{index}].")
        ranked_moves.append(
            {
                "rank": int(ranked["rank"]),
                "move_id": ranked["move_id"],
                "operation_name": ranked["operation_name"],
                "combined_score": float(ranked["combined_score"]),
            }
        )
    return {
        "ranked_moves": ranked_moves,
        "selected_sequence": payload["selected_sequence"],
        "risks": payload["risks"],
    }


def _validate_abi_ear_prose_inventions(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "prose_inventions", list)
    _require_string_list(payload, "risks")
    inventions = []
    for index, invention in enumerate(payload["prose_inventions"]):
        validated = _validate_object(invention, f"prose_inventions[{index}]", ("id", "title", "text"))
        _require_string_list(invention, "used_move_ids", field_prefix=f"prose_inventions[{index}].")
        validated["used_move_ids"] = invention["used_move_ids"]
        inventions.append(validated)
    return {
        "prose_inventions": inventions,
        "risks": payload["risks"],
    }


def _validate_abi_ear_refined_invention(payload: dict[str, Any]) -> dict[str, Any]:
    _require_string_list(payload, "source_invention_ids")
    _require_string_list(payload, "used_move_ids")
    _require_type(payload, "text", str)
    _require_string_list(payload, "refinement_notes")
    _require_string_list(payload, "risks")
    return {
        "source_invention_ids": payload["source_invention_ids"],
        "used_move_ids": payload["used_move_ids"],
        "text": payload["text"],
        "refinement_notes": payload["refinement_notes"],
        "risks": payload["risks"],
    }


def _validate_abi_ear_reread_trace(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "first_read_opening_interpretation",
        "second_read_opening_interpretation",
    ):
        _require_type(payload, key, str)
    for key in ("changed_opening_words", "supporting_lines_or_passages", "unsupported_claims"):
        _require_string_list(payload, key)
    _require_number(payload, "reread_gain_estimate")
    return {
        "first_read_opening_interpretation": payload["first_read_opening_interpretation"],
        "second_read_opening_interpretation": payload["second_read_opening_interpretation"],
        "changed_opening_words": payload["changed_opening_words"],
        "supporting_lines_or_passages": payload["supporting_lines_or_passages"],
        "reread_gain_estimate": float(payload["reread_gain_estimate"]),
        "unsupported_claims": payload["unsupported_claims"],
    }


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _string_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
    }


def _validate_object(
    value: object,
    label: str,
    required_string_fields: tuple[str, ...],
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{label} must be an object")
    validated = {}
    for field in required_string_fields:
        _require_type(value, field, str, field_prefix=f"{label}.")
        validated[field] = value[field]
    return validated


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


def _require_integer(payload: dict[str, Any], key: str, *, field_prefix: str = "") -> None:
    if key not in payload:
        raise ModelValidationError(f"missing required field: {field_prefix}{key}")
    if isinstance(payload[key], bool) or not isinstance(payload[key], int):
        raise ModelValidationError(f"{field_prefix}{key} must be an integer")


def _require_number(payload: dict[str, Any], key: str, *, field_prefix: str = "") -> None:
    if key not in payload:
        raise ModelValidationError(f"missing required field: {field_prefix}{key}")
    if isinstance(payload[key], bool) or not isinstance(payload[key], int | float):
        raise ModelValidationError(f"{field_prefix}{key} must be a number")


def _require_string_list(
    payload: dict[str, Any],
    key: str,
    *,
    field_prefix: str = "",
) -> None:
    _require_type(payload, key, list, field_prefix=field_prefix)
    for index, value in enumerate(payload[key]):
        if not isinstance(value, str):
            raise ModelValidationError(f"{field_prefix}{key}[{index}] must be a string")
