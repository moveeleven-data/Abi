"""Isolated OpenAI live adapter for the Phase 7A guarded worker."""

from __future__ import annotations

from collections.abc import Mapping
import importlib
import json
from typing import Any

from abi.model_driver import ModelClientError, WorkerRequest
from abi.model_schemas import (
    ABI_EAR_FIELD_MODEL_SCHEMA,
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    abi_ear_field_model_json_schema,
    abi_ear_germ_analysis_json_schema,
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
    if request.schema == ABI_EAR_GERM_ANALYSIS_SCHEMA:
        return {
            "label": "Abi Ear germ analysis",
            "json_schema": abi_ear_germ_analysis_json_schema(),
            "prompt_builder": _build_germ_analysis_prompt,
        }
    if request.schema == ABI_EAR_FIELD_MODEL_SCHEMA:
        return {
            "label": "Abi Ear field model",
            "json_schema": abi_ear_field_model_json_schema(),
            "prompt_builder": _build_field_model_prompt,
        }
    return None


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
