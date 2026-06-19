"""Isolated OpenAI live adapter for guarded workers."""

from __future__ import annotations

from collections.abc import Mapping
import importlib
import json
from typing import Any

from abi.model_driver import ModelClientError, WorkerRequest
from abi.model_schemas import (
    ABI_EAR_FIELD_MODEL_SCHEMA,
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    LIVE_MODEL_WORKER_SCHEMAS,
    PILOT_MODEL_SCHEMAS,
    json_schema_for_worker_schema,
)


class OpenAIResponsesClient:
    provider = "openai"

    def __init__(self, *, model: str) -> None:
        self.model = model

    def generate(self, request: WorkerRequest) -> str:
        schema = _schema_for_request(request)
        if schema is None:
            raise ModelClientError(f"unsupported live schema: {request.schema.name}")
        try:
            openai_module = importlib.import_module("openai")
        except ImportError as error:
            raise ModelClientError(
                "OpenAI SDK is not installed; install the optional live dependencies."
            ) from error

        try:
            client = openai_module.OpenAI()
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            f"Return only structured JSON for {schema['label']}. "
                            "Do not write prose outside the requested schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": schema["prompt_builder"](request.input_text),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": request.schema.name,
                        "schema": schema["json_schema"],
                        "strict": True,
                    }
                },
            )
        except Exception as error:
            raise ModelClientError(f"OpenAI live request failed: {error}") from error

        output_text = _extract_output_text(response)
        if not output_text:
            raise ModelClientError("OpenAI live response did not contain output text")
        return output_text


def _schema_for_request(request: WorkerRequest) -> dict[str, Any] | None:
    if request.schema in LIVE_MODEL_WORKER_SCHEMAS:
        return {
            "label": request.schema.name,
            "json_schema": json_schema_for_worker_schema(request.schema),
            "prompt_builder": _prompt_builder_for_schema(request.schema),
        }
    return None


def _prompt_builder_for_schema(schema: object) -> object:
    if schema == ABI_EAR_GERM_ANALYSIS_SCHEMA:
        return _build_germ_analysis_prompt
    if schema == ABI_EAR_FIELD_MODEL_SCHEMA:
        return _build_field_model_prompt
    if schema in PILOT_MODEL_SCHEMAS:
        return _build_pilot_artifact_set_prompt
    return _build_live_packet_prompt


def _build_germ_analysis_prompt(germ_text: str) -> str:
    return (
        "Analyze this germ sentence at word level using the requested schema. "
        "Keep the output compact and structural. Germ sentence:\n"
        f"{germ_text}"
    )


def _build_field_model_prompt(germ_text: str) -> str:
    return (
        "Build a compact Abi Ear field model for this germ sentence using the requested "
        "schema. Include only structural lists and a scale ceiling; do not compose prose. "
        "Germ sentence:\n"
        f"{germ_text}"
    )


def _build_live_packet_prompt(germ_text: str) -> str:
    return (
        "Produce the requested Abi Ear packet component as compact structured JSON. "
        "Stay within the supplied schema and use fixture-level benchmark reasoning only. "
        "Germ sentence:\n"
        f"{germ_text}"
    )


def _build_pilot_artifact_set_prompt(input_text: str) -> str:
    return (
        "Produce the requested pilot artifact-set component as strict structured JSON. "
        "For baseline components, generate baseline content only; Abi assigns the "
        "baseline role and no-validation/no-final-gate metadata deterministically. "
        "The output must remain non-final, must not claim human validation, must not "
        "claim phase shift, and must not satisfy final-artifact gates. Source manifest "
        "and task context:\n"
        f"{input_text}"
    )


def _extract_output_text(response: object) -> str | None:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = _get_value(response, "output")
    if not isinstance(output, list):
        return None
    for item in output:
        content_items = _get_value(item, "content")
        if not isinstance(content_items, list):
            continue
        for content_item in content_items:
            text = _get_value(content_item, "text")
            if isinstance(text, str) and text.strip():
                return text
            parsed = _get_value(content_item, "parsed")
            if parsed is not None:
                return json.dumps(parsed, sort_keys=True)
    return None


def _get_value(value: object, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)
