"""Isolated OpenAI live adapter for guarded workers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import importlib
import json
from typing import Any

from abi.model_driver import ModelClientError, WorkerRequest
from abi.model_schemas import (
    ABI_EAR_FIELD_MODEL_SCHEMA,
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    ABLATION_INFORMED_REVISION_MODEL_SCHEMAS,
    AUTONOMOUS_REVISION_MODEL_SCHEMAS,
    BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
    LIVE_MODEL_WORKER_SCHEMAS,
    MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC_SCHEMA,
    NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA,
    OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
    PILOT_ABI_CANDIDATE_SCHEMA,
    PILOT_DIRECT_PROMPT_BASELINE_SCHEMA,
    PILOT_MODEL_SCHEMAS,
    PILOT_RAW_MODEL_BASELINE_SCHEMA,
    RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
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
            response_format = openai_response_format_for_request(request)
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
                    "format": response_format
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
            "json_schema": _openai_strict_json_schema(
                json_schema_for_worker_schema(request.schema)
            ),
            "prompt_builder": _prompt_builder_for_schema(request.schema),
        }
    return None


def openai_response_format_for_request(request: WorkerRequest) -> dict[str, Any]:
    schema = _schema_for_request(request)
    if schema is None:
        raise ModelClientError(f"unsupported live schema: {request.schema.name}")
    return {
        "type": "json_schema",
        "name": request.schema.name,
        "schema": schema["json_schema"],
        "strict": True,
    }


def _openai_strict_json_schema(schema: object) -> object:
    if isinstance(schema, list):
        return [_openai_strict_json_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return deepcopy(schema)

    strict_schema: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            strict_schema[key] = {
                property_name: _openai_strict_json_schema(property_schema)
                for property_name, property_schema in value.items()
            }
        elif key == "items":
            strict_schema[key] = _openai_strict_json_schema(value)
        elif key in {"anyOf", "allOf", "oneOf"} and isinstance(value, list):
            strict_schema[key] = [_openai_strict_json_schema(item) for item in value]
        elif key in {"$defs", "definitions"} and isinstance(value, dict):
            strict_schema[key] = {
                definition_name: _openai_strict_json_schema(definition_schema)
                for definition_name, definition_schema in value.items()
            }
        else:
            strict_schema[key] = deepcopy(value)

    if strict_schema.get("type") == "object":
        properties = strict_schema.get("properties")
        if isinstance(properties, dict):
            strict_schema["additionalProperties"] = False
            strict_schema["required"] = list(properties.keys())
        else:
            strict_schema["properties"] = {}
            strict_schema["additionalProperties"] = False
            strict_schema["required"] = []
    return strict_schema


def _prompt_builder_for_schema(schema: object) -> object:
    if schema == ABI_EAR_GERM_ANALYSIS_SCHEMA:
        return _build_germ_analysis_prompt
    if schema == ABI_EAR_FIELD_MODEL_SCHEMA:
        return _build_field_model_prompt
    if schema == PILOT_ABI_CANDIDATE_SCHEMA:
        return _build_pilot_candidate_prompt
    if schema == PILOT_DIRECT_PROMPT_BASELINE_SCHEMA:
        return _build_pilot_direct_prompt_baseline_prompt
    if schema == PILOT_RAW_MODEL_BASELINE_SCHEMA:
        return _build_pilot_raw_model_baseline_prompt
    if schema in PILOT_MODEL_SCHEMAS:
        return _build_pilot_reader_artifact_prompt
    if schema in AUTONOMOUS_REVISION_MODEL_SCHEMAS:
        return _build_autonomous_revision_prompt
    if schema in ABLATION_INFORMED_REVISION_MODEL_SCHEMAS:
        return _build_ablation_informed_revision_prompt
    if schema == BOUNDED_MACRO_RECOMPOSITION_SCHEMA:
        return _build_bounded_macro_recomposition_prompt
    if schema == OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA:
        return _build_object_motion_causality_generation_prompt
    if schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA:
        return _build_residual_intervention_generation_prompt
    if schema == NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA:
        return _build_nonlocal_law_guided_generation_prompt
    if schema == MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC_SCHEMA:
        return _build_model_backed_local_law_rival_diagnostic_prompt
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


def _build_pilot_candidate_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema. In the text field, write a 700-1200 "
        "word reader-facing prose artifact from source_contents. Do not describe the "
        "system, the task, the schema, or the artifact status. Do not use headings like "
        "role or status. Do not mention internal labels, source manifests, gates, "
        "validation, non-finality, metadata, or JSON. Source material and constraints:\n"
        f"{input_text}"
    )


def _build_pilot_direct_prompt_baseline_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema. In the text field, write a 700-1200 "
        "word reader-facing prose piece from source_contents using a broad direct "
        "writing prompt. Do not use Abi-specific machinery or internal labels. Do not "
        "describe the system, the schema, baseline status, gates, validation, "
        "non-finality, metadata, or JSON. Source material and constraints:\n"
        f"{input_text}"
    )


def _build_pilot_raw_model_baseline_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema. In the text field, write a 700-1200 "
        "word reader-facing prose piece from source_contents as if from a simple raw "
        "writing prompt. The text field must be prose, not JSON or a report. Do not "
        "describe the system, the schema, baseline status, gates, validation, "
        "non-finality, metadata, or JSON. Source material and constraints:\n"
        f"{input_text}"
    )


def _build_pilot_reader_artifact_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema. Generate reader-facing prose in text "
        "fields from source_contents. Do not describe the system, schema, internal "
        "status, gates, validation, non-finality, metadata, or JSON. Source material "
        "and constraints:\n"
        f"{input_text}"
    )


def _build_autonomous_revision_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema for one autonomous closed-loop revision "
        "worker. Use the reader-lab evidence and prior_outputs supplied in the prompt. "
        "Treat revision_work_order as the only legal source for target, span, "
        "ablation, and provenance IDs; do not invent or redefine control-plane IDs. "
        "Keep the recomposition bounded to the selected causal handle; do not rewrite "
        "the whole artifact. Preserve domestic object-world pressure, morning stillness, "
        "incremental patterning, quiet philosophical pressure, and strongest-rival "
        "pressure. For old/new rival comparison, use judgment_provenance only for exact "
        "allowed source tokens supplied in the prompt packet; put explanatory prose in "
        "judgment_rationale, never in provenance arrays. For ablation comparison, "
        "executed rows must use exact allowed executed_variant_id values; non-executed "
        "probes must be planned_only with planned_probe_id. Do not claim finality, "
        "validation, phase shift, human evidence, or paper readiness. Prompt packet:\n"
        f"{input_text}"
    )


def _build_ablation_informed_revision_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema for one ablation-informed revision "
        "worker. Use only the controller-owned options, target IDs, span IDs, packet "
        "references, and evidence fields supplied in the prompt. Do not invent base "
        "candidate IDs, patch target IDs, or patch span IDs. The model may choose one "
        "allowed base option, explain the next causal handle, and propose bounded "
        "replacement text for listed spans. The controller owns before text, full "
        "revised text assembly, diff reports, gates, finalization, evidence counts, "
        "and rival-defeated truth. Do not claim finality, validation, phase shift, "
        "human evidence, or paper readiness. Prompt packet:\n"
        f"{input_text}"
    )


def _build_bounded_macro_recomposition_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema for one bounded macro recomposition "
        "worker. The controller owns base selection, before text, target boundaries, "
        "full text assembly, diffing, gates, finalization, and strongest-rival truth. "
        "For reader_state_informed_macro_2, return target_paragraph_replacements "
        "keyed by the controller target_paragraph_ref values in the work order; "
        "also return target_span_replacements for every controller target span "
        "marked material_change_required. Replace every paragraph marked "
        "material_change_required with a material rewrite: target span mappings are "
        "necessary but not enough. Do not preserve sentence architecture while "
        "claiming transformation, do not perform lexical substitution, and preserve "
        "the causal/reader effect rather than exact prose. For return paragraphs, "
        "strengthen the opening-return transformation rather than restating the same "
        "return claim in near-identical syntax. The controller will reject near-copies "
        "even when target_span_replacements are present. Do not copy target paragraphs "
        "or required target spans unchanged, and include the controller "
        "before_text_sha256 values. If "
        "multiple active targets share a paragraph, the replacement must cover each "
        "one. For thesis_visible_proof_language_reduction, changing only a final "
        "proof sentence is insufficient if thesis-framing spans remain intact. You "
        "may also return replacement_section_text for compatibility, but the "
        "controller owns final assembly from target refs. For non-reader-state "
        "macro recomposition, return target_paragraph_replacements and "
        "target_span_replacements as empty arrays. "
        "Include one semantic "
        "constraint mapping item for each controller-owned constraint_id plus one "
        "active_target_mapping item for each active transformation target. Active "
        "targets must describe what materially changed and cite before/replacement "
        "support. Do not return the full artifact. Do not rewrite the opening/prefix. "
        "Do not claim finality, validation, phase shift, human evidence, or rival "
        "defeat. Preserve the domestic table/dust/spoon/saucer field, proof arising "
        "from inside the line, cosmic silence/no outside answer as formal isolation, "
        "return without regression, and strongest-rival pressure. Prompt packet:\n"
        f"{input_text}"
    )


def _build_object_motion_causality_generation_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema for one bounded object-motion "
        "causality generation worker. Produce only replacement_region_text for "
        "the controller-selected region, never the full artifact. Include one "
        "target_unit_mapping entry for every authorized unit_id supplied in the "
        "prompt. The controller owns source IDs, target IDs, selected region, final "
        "assembly, diffing, gates, finalization, and claims. The replacement must "
        "make object movement or state change produce visible consequence before "
        "explanation. Selected-region materiality is required: preserving protected "
        "effects does not mean preserving sentence architecture, lexical "
        "substitutions are insufficient, and target-unit mappings are necessary "
        "but not enough. The controller will reject near-copies unless the "
        "replacement has at least 10 new unique words and a changed unique word "
        "ratio of at least 0.12. Do not merely tighten local phrases. Reconcile "
        "overlapping target units in one integrated replacement; do not write "
        "separate duplicated unit rewrites or make the passage busier to satisfy "
        "coverage. Stay bounded to the selected region. Do not add decorative "
        "vividness, a new object list, rival mimicry, nonselected-region edits, "
        "finality claims, phase-shift claims, human-validation claims, or "
        "JSON/procedural leakage inside the replacement text. Prompt packet:\n"
        f"{input_text}"
    )


def _build_residual_intervention_generation_prompt(input_text: str) -> str:
    policy_summary = _residual_materiality_policy_summary(input_text)
    return (
        "Return strict JSON matching the schema for one bounded residual "
        "intervention worker. Produce only replacement_region_text for the "
        "controller-selected region, never the full artifact. Include one "
        "target_unit_mappings entry for every authorized target_unit_id supplied "
        "in the prompt. The controller owns target identity, source IDs, selected "
        "region, final assembly, diffing, gates, finalization, and claims. Obey "
        "the target_adapter prompt instructions and mechanism contract exactly. "
        "Lexical tightening is insufficient. Preserving exact target sentence "
        "architecture is insufficient. Preserve effect/function rather than exact "
        "syntax. Materially re-author every required target unit. Surrounding "
        "untargeted context may remain stable; do not rewrite protected context "
        "merely to raise a global ratio. For tactile targets, tactile necessity is "
        "distinct from object motion: contact, pressure, resistance, weight, "
        "friction, compression, settling, absorption, impact, breakage mechanics, "
        "or displacement against a surface must make consequence feel physically "
        "necessary. Stay bounded to the selected region. Do not add decorative "
        "vividness, new object inventory, rival mimicry, abstract thesis language, "
        "nonselected-region edits, finality claims, phase-shift claims, "
        "human-validation claims, or JSON/procedural leakage inside the "
        f"replacement text. Active materiality policy: {policy_summary}. "
        "Prompt packet:\n"
        f"{input_text}"
    )


def _build_nonlocal_law_guided_generation_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema for "
        "autonomous.nonlocal_law_guided_generation.v1. Revise only the supplied "
        "packet_0063 candidate under the nonlocal law-guided work order. Produce "
        "one revised candidate only. Use packet_0063's own object field; do not "
        "copy the strongest rival or import rival objects, scenes, actions, "
        "cadence, causal plot, diction, or domestic sequence. Stage object-event "
        "consequence before explanation. Delay or embed explanation; do not "
        "abolish explanation. Do not claim success, improvement, finality, phase "
        "shift, human validation, synthesis, ablation proof, or rival defeat. "
        "Output structured schema only. Prompt packet:\n"
        f"{input_text}"
    )


def _build_model_backed_local_law_rival_diagnostic_prompt(input_text: str) -> str:
    return (
        "Return strict JSON matching the schema for autonomous.local_law_rival_diagnostic.v1. "
        "Compare only. Do not rewrite, generate candidate text, select a target, "
        "create a work order, authorize generation, or propose ablation. Use "
        "packet_0063 and the materialized strongest-rival text as subjects under "
        "the supplied law: first-read pressure must arise from object-event "
        "sequence before explanation, thesis, or named pressure appears. Identify "
        "where pressure appears before explanation, where explanation appears "
        "before pressure, and what a future candidate must learn without copying "
        "the rival. Do not imitate rival diction, transplant rival scenes, copy "
        "rival structure, claim the rival has been beaten, claim finality, or "
        "claim phase shift. Prompt packet:\n"
        f"{input_text}"
    )


def _residual_materiality_policy_summary(input_text: str) -> str:
    try:
        prompt = json.loads(input_text)
    except json.JSONDecodeError:
        return "unavailable; follow materiality_policy in prompt packet"
    policy = prompt.get("materiality_policy")
    if not isinstance(policy, dict):
        materiality = prompt.get("materiality_requirement")
        if isinstance(materiality, dict):
            policy = materiality.get("materiality_policy")
    if not isinstance(policy, dict):
        return "unavailable; follow materiality_policy in prompt packet"
    target_bearing = policy.get("target_bearing_scope")
    target_unit = policy.get("target_unit_scope")
    whole = policy.get("whole_region_guard")
    return json.dumps(
        {
            "policy_id": policy.get("policy_id"),
            "policy_version": policy.get("policy_version"),
            "primary_materiality_scope": policy.get("primary_materiality_scope"),
            "whole_region_guard": whole if isinstance(whole, dict) else {},
            "target_bearing_scope": target_bearing if isinstance(target_bearing, dict) else {},
            "target_unit_scope": target_unit if isinstance(target_unit, dict) else {},
            "prompt_feedback": policy.get("prompt_feedback"),
        },
        sort_keys=True,
        separators=(",", ":"),
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
