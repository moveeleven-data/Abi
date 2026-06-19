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
    REREAD_FORMAL_PROBLEM_BUILDER = "reread_formal_problem_builder"
    REREAD_GERM_AFTERIMAGE_PAIRER = "reread_germ_afterimage_pairer"
    REREAD_CONSEQUENCE_GRAPH_BUILDER = "reread_consequence_graph_builder"
    REREAD_DRAFT_COMPOSER = "reread_draft_composer"
    REREAD_FIRST_READ_TRACER = "reread_first_read_tracer"
    REREAD_REREAD_TRACER = "reread_reread_tracer"
    REREAD_FAILURE_DIAGNOSER = "reread_failure_diagnoser"
    REREAD_INTERVENTION_BUILDER = "reread_intervention_builder"
    REREAD_RECOMPOSER = "reread_recomposer"
    REREAD_COUNTERFACTUAL_EVALUATOR = "reread_counterfactual_evaluator"
    REREAD_IRREDUCIBILITY_REPORTER = "reread_irreducibility_reporter"
    REREAD_GATE_EVALUATOR = "reread_gate_evaluator"
    EVALUATION_BASELINE_SUMMARIZER = "evaluation_baseline_summarizer"
    EVALUATION_COMPARISON_REPORTER = "evaluation_comparison_reporter"
    PILOT_ABI_CANDIDATE_BUILDER = "pilot_abi_candidate_builder"
    PILOT_DIRECT_PROMPT_BASELINE_BUILDER = "pilot_direct_prompt_baseline_builder"
    PILOT_RAW_MODEL_BASELINE_BUILDER = "pilot_raw_model_baseline_builder"


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

REREAD_FORMAL_PROBLEM_SCHEMA = WorkerSchema(
    name="MinimalRereadFormalProblemModelOutput",
    version="1",
    artifact_type="live_reread_formal_problem",
)

REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA = WorkerSchema(
    name="MinimalRereadGermAfterimagePairModelOutput",
    version="1",
    artifact_type="live_reread_germ_afterimage_pair",
)

REREAD_CONSEQUENCE_GRAPH_SCHEMA = WorkerSchema(
    name="MinimalRereadConsequenceGraphModelOutput",
    version="1",
    artifact_type="live_reread_consequence_graph",
)

REREAD_DRAFT_VERSION_SCHEMA = WorkerSchema(
    name="MinimalRereadDraftVersionModelOutput",
    version="1",
    artifact_type="live_reread_draft_version",
)

REREAD_FIRST_READ_TRACE_SCHEMA = WorkerSchema(
    name="MinimalRereadFirstReadTraceModelOutput",
    version="1",
    artifact_type="live_reread_first_read_trace",
)

REREAD_REREAD_TRACE_SCHEMA = WorkerSchema(
    name="MinimalRereadRereadTraceModelOutput",
    version="1",
    artifact_type="live_reread_reread_trace",
)

REREAD_FAILURE_DIAGNOSIS_SCHEMA = WorkerSchema(
    name="MinimalRereadFailureDiagnosisModelOutput",
    version="1",
    artifact_type="live_reread_failure_diagnosis",
)

REREAD_INTERVENTION_SCHEMA = WorkerSchema(
    name="MinimalRereadInterventionModelOutput",
    version="1",
    artifact_type="live_reread_intervention",
)

REREAD_RECOMPOSED_DRAFT_SCHEMA = WorkerSchema(
    name="MinimalRereadRecomposedDraftModelOutput",
    version="1",
    artifact_type="live_reread_recomposed_draft",
)

REREAD_COUNTERFACTUAL_RESULT_SCHEMA = WorkerSchema(
    name="MinimalRereadCounterfactualResultModelOutput",
    version="1",
    artifact_type="live_reread_counterfactual_result",
)

REREAD_IRREDUCIBILITY_REPORT_SCHEMA = WorkerSchema(
    name="MinimalRereadIrreducibilityReportModelOutput",
    version="1",
    artifact_type="live_reread_irreducibility_report",
)

REREAD_GATE_REPORT_SCHEMA = WorkerSchema(
    name="MinimalRereadGateReportModelOutput",
    version="1",
    artifact_type="live_reread_gate_report",
)

LIVE_MINIMAL_REREAD_MODEL_SCHEMAS = (
    REREAD_FORMAL_PROBLEM_SCHEMA,
    REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA,
    REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    REREAD_DRAFT_VERSION_SCHEMA,
    REREAD_FIRST_READ_TRACE_SCHEMA,
    REREAD_REREAD_TRACE_SCHEMA,
    REREAD_FAILURE_DIAGNOSIS_SCHEMA,
    REREAD_INTERVENTION_SCHEMA,
    REREAD_RECOMPOSED_DRAFT_SCHEMA,
    REREAD_COUNTERFACTUAL_RESULT_SCHEMA,
    REREAD_IRREDUCIBILITY_REPORT_SCHEMA,
    REREAD_GATE_REPORT_SCHEMA,
)

EVALUATION_BEST_OF_N_BASELINE_SCHEMA = WorkerSchema(
    name="EvaluationBestOfNBaselineSummaryModelOutput",
    version="1",
    artifact_type="evaluation_best_of_n_baseline_summary",
)

EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA = WorkerSchema(
    name="EvaluationBaselineComparisonReportModelOutput",
    version="1",
    artifact_type="evaluation_baseline_comparison_report",
)

EVALUATION_MODEL_SCHEMAS = (
    EVALUATION_BEST_OF_N_BASELINE_SCHEMA,
    EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA,
)

PILOT_ABI_CANDIDATE_SCHEMA = WorkerSchema(
    name="PilotAbiCandidateModelOutput",
    version="1",
    artifact_type="pilot_abi_candidate_ref",
)

PILOT_DIRECT_PROMPT_BASELINE_SCHEMA = WorkerSchema(
    name="PilotDirectPromptBaselineModelOutput",
    version="1",
    artifact_type="pilot_direct_prompt_baseline",
)

PILOT_RAW_MODEL_BASELINE_SCHEMA = WorkerSchema(
    name="PilotRawModelBaselineModelOutput",
    version="1",
    artifact_type="pilot_raw_model_baseline",
)

PILOT_MODEL_SCHEMAS = (
    PILOT_ABI_CANDIDATE_SCHEMA,
    PILOT_DIRECT_PROMPT_BASELINE_SCHEMA,
    PILOT_RAW_MODEL_BASELINE_SCHEMA,
)

LIVE_MODEL_WORKER_SCHEMAS = (
    LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS
    + LIVE_MINIMAL_REREAD_MODEL_SCHEMAS
    + EVALUATION_MODEL_SCHEMAS
    + PILOT_MODEL_SCHEMAS
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


def minimal_reread_formal_problem_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "benchmark_input": {"type": "string"},
            "problem_statement": {"type": "string"},
            "initial_reader_state": _free_object_schema(),
            "target_reader_state": _free_object_schema(),
            "success_conditions": _string_array_schema(),
            "forbidden_shortcuts": _string_array_schema(),
        },
        [
            "benchmark_input",
            "problem_statement",
            "initial_reader_state",
            "target_reader_state",
            "success_conditions",
            "forbidden_shortcuts",
        ],
    )


def minimal_reread_germ_afterimage_pair_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "germ": {"type": "string"},
            "afterimage": {"type": "string"},
            "reader_state_delta": _free_object_schema(),
            "load_bearing_words": _string_array_schema(),
        },
        ["germ", "afterimage", "reader_state_delta", "load_bearing_words"],
    )


def minimal_reread_consequence_graph_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "problem_statement": {"type": "string"},
            "germ": {"type": "string"},
            "nodes": {
                "type": "array",
                "items": _object_schema(
                    {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "kind": {"type": "string"},
                    },
                    ["id", "label", "kind"],
                ),
            },
            "edges": {
                "type": "array",
                "items": _object_schema(
                    {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "relation": {"type": "string"},
                    },
                    ["from", "to", "relation"],
                ),
            },
            "cycle": _string_array_schema(),
            "structural_claim": {"type": "string"},
        },
        ["problem_statement", "germ", "nodes", "edges", "cycle", "structural_claim"],
    )


def minimal_reread_draft_version_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "version_id": {"type": "string"},
            "used_graph_nodes": _string_array_schema(),
            "text": {"type": "string"},
            "intended_afterimage": {"type": "string"},
            "known_weakness": {"type": "string"},
        },
        ["version_id", "used_graph_nodes", "text", "intended_afterimage", "known_weakness"],
    )


def minimal_reread_first_read_trace_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "draft_version_id": {"type": "string"},
            "opening_read": {"type": "string"},
            "noticed_evidence": _string_array_schema(),
            "missed_evidence": _string_array_schema(),
            "reader_state": _free_object_schema(),
            "blind_spots": _string_array_schema(),
        },
        [
            "draft_version_id",
            "opening_read",
            "noticed_evidence",
            "missed_evidence",
            "reader_state",
            "blind_spots",
        ],
    )


def minimal_reread_reread_trace_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "draft_version_id": {"type": "string"},
            "opening_reread": {"type": "string"},
            "changed_opening_words": _string_array_schema(),
            "supporting_nodes": _string_array_schema(),
            "supporting_passages": _string_array_schema(),
            "reader_state": _free_object_schema(),
            "cycle_used": _string_array_schema(),
        },
        [
            "draft_version_id",
            "opening_reread",
            "changed_opening_words",
            "supporting_nodes",
            "supporting_passages",
            "reader_state",
            "cycle_used",
        ],
    )


def minimal_reread_failure_diagnosis_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "failure_id": {"type": "string"},
            "diagnosed_failure": {"type": "string"},
            "evidence": _free_object_schema(),
            "severity": {"type": "string"},
            "repair_requirement": {"type": "string"},
        },
        ["failure_id", "diagnosed_failure", "evidence", "severity", "repair_requirement"],
    )


def minimal_reread_intervention_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "intervention_id": {"type": "string"},
            "targets_failure_id": {"type": "string"},
            "operation": {"type": "string"},
            "target_passage": {"type": "string"},
            "replacement_strategy": _string_array_schema(),
            "affected_graph_nodes": _string_array_schema(),
            "expected_effect": {"type": "string"},
        },
        [
            "intervention_id",
            "targets_failure_id",
            "operation",
            "target_passage",
            "replacement_strategy",
            "affected_graph_nodes",
            "expected_effect",
        ],
    )


def minimal_reread_recomposed_draft_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "version_id": {"type": "string"},
            "source_version_id": {"type": "string"},
            "intervention_id": {"type": "string"},
            "text": {"type": "string"},
            "change_log": _string_array_schema(),
        },
        ["version_id", "source_version_id", "intervention_id", "text", "change_log"],
    )


def minimal_reread_counterfactual_result_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "counterfactual_id": {"type": "string"},
            "tested_condition": {"type": "string"},
            "baseline_version_id": {"type": "string"},
            "intervention_version_id": {"type": "string"},
            "predicted_without_intervention": _free_object_schema(),
            "predicted_with_intervention": _free_object_schema(),
            "delta": _free_object_schema(),
            "intervention_id": {"type": "string"},
            "uses_previous_reread_trace_confidence": {"type": "number"},
        },
        [
            "counterfactual_id",
            "tested_condition",
            "baseline_version_id",
            "intervention_version_id",
            "predicted_without_intervention",
            "predicted_with_intervention",
            "delta",
            "intervention_id",
            "uses_previous_reread_trace_confidence",
        ],
    )


def minimal_reread_irreducibility_report_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "load_bearing_elements": {
                "type": "array",
                "items": _object_schema(
                    {
                        "element": {"type": "string"},
                        "why_irreducible": {"type": "string"},
                    },
                    ["element", "why_irreducible"],
                ),
            },
            "germ_afterimage_dependency": _free_object_schema(),
            "counterfactual_delta": _free_object_schema(),
            "verdict": {"type": "string"},
        },
        [
            "load_bearing_elements",
            "germ_afterimage_dependency",
            "counterfactual_delta",
            "verdict",
        ],
    )


def minimal_reread_gate_report_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "gate_name": {"type": "string"},
            "passed": {"type": "boolean"},
            "blocking_defects": _string_array_schema(),
            "gate_scores": _free_object_schema(),
            "summary_verdict": {"type": "string"},
        },
        ["gate_name", "passed", "blocking_defects", "gate_scores", "summary_verdict"],
    )


def evaluation_best_of_n_baseline_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "baseline_set_id": {"type": "string"},
            "fixture_only": {"type": "boolean"},
            "not_real_validation": {"type": "boolean"},
            "generated_by": {"type": "string"},
            "n": {"type": "integer"},
            "baseline_candidates": {
                "type": "array",
                "items": _object_schema(
                    {
                        "id": {"type": "string"},
                        "summary": {"type": "string"},
                        "known_limit": {"type": "string"},
                    },
                    ["id", "summary", "known_limit"],
                ),
            },
            "selected_baseline_id": {"type": "string"},
            "selection_rationale": {"type": "string"},
            "risks": _string_array_schema(),
        },
        [
            "baseline_set_id",
            "fixture_only",
            "not_real_validation",
            "generated_by",
            "n",
            "baseline_candidates",
            "selected_baseline_id",
            "selection_rationale",
            "risks",
        ],
    )


def evaluation_baseline_comparison_report_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "comparison_id": {"type": "string"},
            "fixture_only": {"type": "boolean"},
            "not_real_validation": {"type": "boolean"},
            "candidate_id": {"type": "string"},
            "baseline_ids": _string_array_schema(),
            "observed_reader_state_delta": _free_object_schema(),
            "comparison_summary": {"type": "string"},
            "claims_not_made": _string_array_schema(),
            "risks": _string_array_schema(),
        },
        [
            "comparison_id",
            "fixture_only",
            "not_real_validation",
            "candidate_id",
            "baseline_ids",
            "observed_reader_state_delta",
            "comparison_summary",
            "claims_not_made",
            "risks",
        ],
    )


def pilot_abi_candidate_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "candidate_id": {"type": "string"},
            "text": {"type": "string"},
            "source_file_count": {"type": "integer"},
            "source_set_hashes": _string_array_schema(),
            "non_final": {"type": "boolean"},
            "candidate_only": {"type": "boolean"},
            "not_human_validated": {"type": "boolean"},
            "not_finalization_eligible": {"type": "boolean"},
            "finalization_eligible": {"type": "boolean"},
            "human_validated": {"type": "boolean"},
            "human_validation_claim": {"type": "boolean"},
            "phase_shift_claim": {"type": "boolean"},
            "no_phase_shift_claim": {"type": "boolean"},
            "risks": _string_array_schema(),
        },
        [
            "candidate_id",
            "text",
            "source_file_count",
            "source_set_hashes",
            "non_final",
            "candidate_only",
            "not_human_validated",
            "not_finalization_eligible",
            "finalization_eligible",
            "human_validated",
            "human_validation_claim",
            "phase_shift_claim",
            "no_phase_shift_claim",
            "risks",
        ],
    )


def pilot_direct_prompt_baseline_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "baseline_id": {"type": "string"},
            "baseline_type": {"type": "string"},
            "text": {"type": "string"},
            "fixture_or_fake": {"type": "boolean"},
            "not_real_validation": {"type": "boolean"},
            "generation_rule": {"type": "string"},
            "final_gate_satisfied": {"type": "boolean"},
            "risks": _string_array_schema(),
        },
        [
            "baseline_id",
            "baseline_type",
            "text",
            "fixture_or_fake",
            "not_real_validation",
            "generation_rule",
            "final_gate_satisfied",
            "risks",
        ],
    )


def pilot_raw_model_baseline_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "baseline_id": {"type": "string"},
            "baseline_type": {"type": "string"},
            "text": {"type": "string"},
            "fixture_or_fake": {"type": "boolean"},
            "not_real_validation": {"type": "boolean"},
            "raw_model_baseline_gate_satisfied": {"type": "boolean"},
            "model_calls_used": {"type": "integer"},
            "risks": _string_array_schema(),
        },
        [
            "baseline_id",
            "baseline_type",
            "text",
            "fixture_or_fake",
            "not_real_validation",
            "raw_model_baseline_gate_satisfied",
            "model_calls_used",
            "risks",
        ],
    )


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
    if schema == REREAD_FORMAL_PROBLEM_SCHEMA:
        return minimal_reread_formal_problem_json_schema()
    if schema == REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA:
        return minimal_reread_germ_afterimage_pair_json_schema()
    if schema == REREAD_CONSEQUENCE_GRAPH_SCHEMA:
        return minimal_reread_consequence_graph_json_schema()
    if schema == REREAD_DRAFT_VERSION_SCHEMA:
        return minimal_reread_draft_version_json_schema()
    if schema == REREAD_FIRST_READ_TRACE_SCHEMA:
        return minimal_reread_first_read_trace_json_schema()
    if schema == REREAD_REREAD_TRACE_SCHEMA:
        return minimal_reread_reread_trace_json_schema()
    if schema == REREAD_FAILURE_DIAGNOSIS_SCHEMA:
        return minimal_reread_failure_diagnosis_json_schema()
    if schema == REREAD_INTERVENTION_SCHEMA:
        return minimal_reread_intervention_json_schema()
    if schema == REREAD_RECOMPOSED_DRAFT_SCHEMA:
        return minimal_reread_recomposed_draft_json_schema()
    if schema == REREAD_COUNTERFACTUAL_RESULT_SCHEMA:
        return minimal_reread_counterfactual_result_json_schema()
    if schema == REREAD_IRREDUCIBILITY_REPORT_SCHEMA:
        return minimal_reread_irreducibility_report_json_schema()
    if schema == REREAD_GATE_REPORT_SCHEMA:
        return minimal_reread_gate_report_json_schema()
    if schema == EVALUATION_BEST_OF_N_BASELINE_SCHEMA:
        return evaluation_best_of_n_baseline_json_schema()
    if schema == EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA:
        return evaluation_baseline_comparison_report_json_schema()
    if schema == PILOT_ABI_CANDIDATE_SCHEMA:
        return pilot_abi_candidate_json_schema()
    if schema == PILOT_DIRECT_PROMPT_BASELINE_SCHEMA:
        return pilot_direct_prompt_baseline_json_schema()
    if schema == PILOT_RAW_MODEL_BASELINE_SCHEMA:
        return pilot_raw_model_baseline_json_schema()
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
    if schema == REREAD_FORMAL_PROBLEM_SCHEMA:
        return _validate_reread_formal_problem(payload)
    if schema == REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA:
        return _validate_reread_germ_afterimage_pair(payload)
    if schema == REREAD_CONSEQUENCE_GRAPH_SCHEMA:
        return _validate_reread_consequence_graph(payload)
    if schema == REREAD_DRAFT_VERSION_SCHEMA:
        return _validate_reread_draft_version(payload)
    if schema == REREAD_FIRST_READ_TRACE_SCHEMA:
        return _validate_reread_first_read_trace(payload)
    if schema == REREAD_REREAD_TRACE_SCHEMA:
        return _validate_reread_reread_trace(payload)
    if schema == REREAD_FAILURE_DIAGNOSIS_SCHEMA:
        return _validate_reread_failure_diagnosis(payload)
    if schema == REREAD_INTERVENTION_SCHEMA:
        return _validate_reread_intervention(payload)
    if schema == REREAD_RECOMPOSED_DRAFT_SCHEMA:
        return _validate_reread_recomposed_draft(payload)
    if schema == REREAD_COUNTERFACTUAL_RESULT_SCHEMA:
        return _validate_reread_counterfactual_result(payload)
    if schema == REREAD_IRREDUCIBILITY_REPORT_SCHEMA:
        return _validate_reread_irreducibility_report(payload)
    if schema == REREAD_GATE_REPORT_SCHEMA:
        return _validate_reread_gate_report(payload)
    if schema == EVALUATION_BEST_OF_N_BASELINE_SCHEMA:
        return _validate_evaluation_best_of_n_baseline(payload)
    if schema == EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA:
        return _validate_evaluation_baseline_comparison_report(payload)
    if schema == PILOT_ABI_CANDIDATE_SCHEMA:
        return _validate_pilot_abi_candidate(payload)
    if schema == PILOT_DIRECT_PROMPT_BASELINE_SCHEMA:
        return _validate_pilot_direct_prompt_baseline(payload)
    if schema == PILOT_RAW_MODEL_BASELINE_SCHEMA:
        return _validate_pilot_raw_model_baseline(payload)
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


def _validate_reread_formal_problem(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("benchmark_input", "problem_statement"):
        _require_type(payload, key, str)
    for key in ("initial_reader_state", "target_reader_state"):
        _require_type(payload, key, dict)
    for key in ("success_conditions", "forbidden_shortcuts"):
        _require_string_list(payload, key)
    return {
        "benchmark_input": payload["benchmark_input"],
        "problem_statement": payload["problem_statement"],
        "initial_reader_state": payload["initial_reader_state"],
        "target_reader_state": payload["target_reader_state"],
        "success_conditions": payload["success_conditions"],
        "forbidden_shortcuts": payload["forbidden_shortcuts"],
    }


def _validate_reread_germ_afterimage_pair(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("germ", "afterimage"):
        _require_type(payload, key, str)
    _require_type(payload, "reader_state_delta", dict)
    _require_string_list(payload, "load_bearing_words")
    return {
        "germ": payload["germ"],
        "afterimage": payload["afterimage"],
        "reader_state_delta": payload["reader_state_delta"],
        "load_bearing_words": payload["load_bearing_words"],
    }


def _validate_reread_consequence_graph(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("problem_statement", "germ", "structural_claim"):
        _require_type(payload, key, str)
    _require_type(payload, "nodes", list)
    _require_type(payload, "edges", list)
    _require_string_list(payload, "cycle")
    nodes = [
        _validate_object(node, f"nodes[{index}]", ("id", "label", "kind"))
        for index, node in enumerate(payload["nodes"])
    ]
    edges = [
        _validate_object(edge, f"edges[{index}]", ("from", "to", "relation"))
        for index, edge in enumerate(payload["edges"])
    ]
    return {
        "problem_statement": payload["problem_statement"],
        "germ": payload["germ"],
        "nodes": nodes,
        "edges": edges,
        "cycle": payload["cycle"],
        "structural_claim": payload["structural_claim"],
    }


def _validate_reread_draft_version(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("version_id", "text", "intended_afterimage", "known_weakness"):
        _require_type(payload, key, str)
    _require_string_list(payload, "used_graph_nodes")
    return {
        "version_id": payload["version_id"],
        "used_graph_nodes": payload["used_graph_nodes"],
        "text": payload["text"],
        "intended_afterimage": payload["intended_afterimage"],
        "known_weakness": payload["known_weakness"],
    }


def _validate_reread_first_read_trace(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("draft_version_id", "opening_read"):
        _require_type(payload, key, str)
    for key in ("noticed_evidence", "missed_evidence", "blind_spots"):
        _require_string_list(payload, key)
    _require_type(payload, "reader_state", dict)
    return {
        "draft_version_id": payload["draft_version_id"],
        "opening_read": payload["opening_read"],
        "noticed_evidence": payload["noticed_evidence"],
        "missed_evidence": payload["missed_evidence"],
        "reader_state": payload["reader_state"],
        "blind_spots": payload["blind_spots"],
    }


def _validate_reread_reread_trace(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("draft_version_id", "opening_reread"):
        _require_type(payload, key, str)
    for key in ("changed_opening_words", "supporting_nodes", "supporting_passages", "cycle_used"):
        _require_string_list(payload, key)
    _require_type(payload, "reader_state", dict)
    return {
        "draft_version_id": payload["draft_version_id"],
        "opening_reread": payload["opening_reread"],
        "changed_opening_words": payload["changed_opening_words"],
        "supporting_nodes": payload["supporting_nodes"],
        "supporting_passages": payload["supporting_passages"],
        "reader_state": payload["reader_state"],
        "cycle_used": payload["cycle_used"],
    }


def _validate_reread_failure_diagnosis(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("failure_id", "diagnosed_failure", "severity", "repair_requirement"):
        _require_type(payload, key, str)
    _require_type(payload, "evidence", dict)
    return {
        "failure_id": payload["failure_id"],
        "diagnosed_failure": payload["diagnosed_failure"],
        "evidence": payload["evidence"],
        "severity": payload["severity"],
        "repair_requirement": payload["repair_requirement"],
    }


def _validate_reread_intervention(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "intervention_id",
        "targets_failure_id",
        "operation",
        "target_passage",
        "expected_effect",
    ):
        _require_type(payload, key, str)
    for key in ("replacement_strategy", "affected_graph_nodes"):
        _require_string_list(payload, key)
    return {
        "intervention_id": payload["intervention_id"],
        "targets_failure_id": payload["targets_failure_id"],
        "operation": payload["operation"],
        "target_passage": payload["target_passage"],
        "replacement_strategy": payload["replacement_strategy"],
        "affected_graph_nodes": payload["affected_graph_nodes"],
        "expected_effect": payload["expected_effect"],
    }


def _validate_reread_recomposed_draft(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("version_id", "source_version_id", "intervention_id", "text"):
        _require_type(payload, key, str)
    _require_string_list(payload, "change_log")
    return {
        "version_id": payload["version_id"],
        "source_version_id": payload["source_version_id"],
        "intervention_id": payload["intervention_id"],
        "text": payload["text"],
        "change_log": payload["change_log"],
    }


def _validate_reread_counterfactual_result(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "counterfactual_id",
        "tested_condition",
        "baseline_version_id",
        "intervention_version_id",
        "intervention_id",
    ):
        _require_type(payload, key, str)
    for key in ("predicted_without_intervention", "predicted_with_intervention", "delta"):
        _require_type(payload, key, dict)
    _require_number(payload, "uses_previous_reread_trace_confidence")
    delta = payload["delta"]
    if "targeted_failure_reduced" not in delta:
        raise ModelValidationError("delta.targeted_failure_reduced is required")
    if not isinstance(delta["targeted_failure_reduced"], bool):
        raise ModelValidationError("delta.targeted_failure_reduced must be bool")
    return {
        "counterfactual_id": payload["counterfactual_id"],
        "tested_condition": payload["tested_condition"],
        "baseline_version_id": payload["baseline_version_id"],
        "intervention_version_id": payload["intervention_version_id"],
        "predicted_without_intervention": payload["predicted_without_intervention"],
        "predicted_with_intervention": payload["predicted_with_intervention"],
        "delta": payload["delta"],
        "intervention_id": payload["intervention_id"],
        "uses_previous_reread_trace_confidence": float(
            payload["uses_previous_reread_trace_confidence"]
        ),
    }


def _validate_reread_irreducibility_report(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "load_bearing_elements", list)
    load_bearing_elements = [
        _validate_object(
            element,
            f"load_bearing_elements[{index}]",
            ("element", "why_irreducible"),
        )
        for index, element in enumerate(payload["load_bearing_elements"])
    ]
    _require_type(payload, "germ_afterimage_dependency", dict)
    _require_type(payload, "counterfactual_delta", dict)
    _require_type(payload, "verdict", str)
    return {
        "load_bearing_elements": load_bearing_elements,
        "germ_afterimage_dependency": payload["germ_afterimage_dependency"],
        "counterfactual_delta": payload["counterfactual_delta"],
        "verdict": payload["verdict"],
    }


def _validate_reread_gate_report(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "gate_name", str)
    _require_type(payload, "passed", bool)
    _require_string_list(payload, "blocking_defects")
    _require_type(payload, "gate_scores", dict)
    _require_type(payload, "summary_verdict", str)
    return {
        "gate_name": payload["gate_name"],
        "passed": payload["passed"],
        "blocking_defects": payload["blocking_defects"],
        "gate_scores": payload["gate_scores"],
        "summary_verdict": payload["summary_verdict"],
    }


def _validate_evaluation_best_of_n_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "baseline_set_id", str)
    _require_type(payload, "fixture_only", bool)
    _require_type(payload, "not_real_validation", bool)
    _require_type(payload, "generated_by", str)
    _require_integer(payload, "n")
    _require_type(payload, "baseline_candidates", list)
    _require_type(payload, "selected_baseline_id", str)
    _require_type(payload, "selection_rationale", str)
    _require_string_list(payload, "risks")
    if not payload["not_real_validation"]:
        raise ModelValidationError("not_real_validation must be true for evaluation baselines")
    candidates = [
        _validate_object(candidate, f"baseline_candidates[{index}]", ("id", "summary", "known_limit"))
        for index, candidate in enumerate(payload["baseline_candidates"])
    ]
    if payload["selected_baseline_id"] not in {candidate["id"] for candidate in candidates}:
        raise ModelValidationError("selected_baseline_id must match a baseline candidate")
    return {
        "baseline_set_id": payload["baseline_set_id"],
        "fixture_only": payload["fixture_only"],
        "not_real_validation": payload["not_real_validation"],
        "generated_by": payload["generated_by"],
        "n": int(payload["n"]),
        "baseline_candidates": candidates,
        "selected_baseline_id": payload["selected_baseline_id"],
        "selection_rationale": payload["selection_rationale"],
        "risks": payload["risks"],
    }


def _validate_evaluation_baseline_comparison_report(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "comparison_id", str)
    _require_type(payload, "fixture_only", bool)
    _require_type(payload, "not_real_validation", bool)
    _require_type(payload, "candidate_id", str)
    _require_string_list(payload, "baseline_ids")
    _require_type(payload, "observed_reader_state_delta", dict)
    _require_type(payload, "comparison_summary", str)
    _require_string_list(payload, "claims_not_made")
    _require_string_list(payload, "risks")
    if not payload["not_real_validation"]:
        raise ModelValidationError("not_real_validation must be true for evaluation reports")
    for required_claim in (
        "no phase-shift claim",
        "no real human validation claim",
        "no final artifact claim",
    ):
        if required_claim not in payload["claims_not_made"]:
            raise ModelValidationError(f"claims_not_made must include {required_claim}")
    return {
        "comparison_id": payload["comparison_id"],
        "fixture_only": payload["fixture_only"],
        "not_real_validation": payload["not_real_validation"],
        "candidate_id": payload["candidate_id"],
        "baseline_ids": payload["baseline_ids"],
        "observed_reader_state_delta": payload["observed_reader_state_delta"],
        "comparison_summary": payload["comparison_summary"],
        "claims_not_made": payload["claims_not_made"],
        "risks": payload["risks"],
    }


def _validate_pilot_abi_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("candidate_id", "text"):
        _require_type(payload, key, str)
    _require_integer(payload, "source_file_count")
    _require_string_list(payload, "source_set_hashes")
    _require_string_list(payload, "risks")
    for key in (
        "non_final",
        "candidate_only",
        "not_human_validated",
        "not_finalization_eligible",
        "finalization_eligible",
        "human_validated",
        "human_validation_claim",
        "phase_shift_claim",
        "no_phase_shift_claim",
    ):
        _require_type(payload, key, bool)
    if not payload["non_final"]:
        raise ModelValidationError("pilot candidate must be non_final")
    if not payload["candidate_only"]:
        raise ModelValidationError("pilot candidate must be candidate_only")
    if not payload["not_human_validated"]:
        raise ModelValidationError("pilot candidate must be not_human_validated")
    if not payload["not_finalization_eligible"]:
        raise ModelValidationError("pilot candidate must be not_finalization_eligible")
    if payload["finalization_eligible"]:
        raise ModelValidationError("pilot candidate must not be finalization_eligible")
    if payload["human_validated"] or payload["human_validation_claim"]:
        raise ModelValidationError("pilot candidate must not claim human validation")
    if payload["phase_shift_claim"] or not payload["no_phase_shift_claim"]:
        raise ModelValidationError("pilot candidate must not make a phase-shift claim")
    return {
        "candidate_id": payload["candidate_id"],
        "text": payload["text"],
        "source_file_count": int(payload["source_file_count"]),
        "source_set_hashes": payload["source_set_hashes"],
        "non_final": payload["non_final"],
        "candidate_only": payload["candidate_only"],
        "not_human_validated": payload["not_human_validated"],
        "not_finalization_eligible": payload["not_finalization_eligible"],
        "finalization_eligible": payload["finalization_eligible"],
        "human_validated": payload["human_validated"],
        "human_validation_claim": payload["human_validation_claim"],
        "phase_shift_claim": payload["phase_shift_claim"],
        "no_phase_shift_claim": payload["no_phase_shift_claim"],
        "risks": payload["risks"],
    }


def _validate_pilot_direct_prompt_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("baseline_id", "baseline_type", "text", "generation_rule"):
        _require_type(payload, key, str)
    for key in ("fixture_or_fake", "not_real_validation", "final_gate_satisfied"):
        _require_type(payload, key, bool)
    _require_string_list(payload, "risks")
    if payload["baseline_type"] != "direct_prompt":
        raise ModelValidationError("pilot direct baseline must have baseline_type direct_prompt")
    if not payload["not_real_validation"]:
        raise ModelValidationError("pilot direct baseline must remain not_real_validation")
    if payload["final_gate_satisfied"]:
        raise ModelValidationError("pilot direct baseline must not satisfy a final gate")
    return {
        "baseline_id": payload["baseline_id"],
        "baseline_type": payload["baseline_type"],
        "text": payload["text"],
        "fixture_or_fake": payload["fixture_or_fake"],
        "not_real_validation": payload["not_real_validation"],
        "generation_rule": payload["generation_rule"],
        "final_gate_satisfied": payload["final_gate_satisfied"],
        "risks": payload["risks"],
    }


def _validate_pilot_raw_model_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("baseline_id", "baseline_type", "text"):
        _require_type(payload, key, str)
    for key in (
        "fixture_or_fake",
        "not_real_validation",
        "raw_model_baseline_gate_satisfied",
    ):
        _require_type(payload, key, bool)
    _require_integer(payload, "model_calls_used")
    _require_string_list(payload, "risks")
    if payload["baseline_type"] != "raw_model":
        raise ModelValidationError("pilot raw baseline must have baseline_type raw_model")
    if not payload["not_real_validation"]:
        raise ModelValidationError("pilot raw baseline must remain not_real_validation")
    if payload["raw_model_baseline_gate_satisfied"]:
        raise ModelValidationError("pilot raw baseline must not satisfy the raw-model gate")
    return {
        "baseline_id": payload["baseline_id"],
        "baseline_type": payload["baseline_type"],
        "text": payload["text"],
        "fixture_or_fake": payload["fixture_or_fake"],
        "not_real_validation": payload["not_real_validation"],
        "raw_model_baseline_gate_satisfied": payload["raw_model_baseline_gate_satisfied"],
        "model_calls_used": int(payload["model_calls_used"]),
        "risks": payload["risks"],
    }


def _schema_with_properties(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _free_object_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
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
