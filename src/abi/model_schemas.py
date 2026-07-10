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
    INTERNAL_STREAM_READER = "internal_stream_reader"
    INTERNAL_REREAD_READER = "internal_reread_reader"
    FORENSIC_GROUNDING_READER = "forensic_grounding_reader"
    HOSTILE_INTERNAL_READER = "hostile_internal_reader"
    INTERNAL_RIVAL_COMPARATOR = "internal_rival_comparator"
    INTERNAL_FAILURE_DIAGNOSER = "internal_failure_diagnoser"
    TARGETED_RECOMPOSITION_PLANNER = "targeted_recomposition_planner"
    COUNTERFACTUAL_ABLATION_PLANNER = "counterfactual_ablation_planner"
    AUTONOMOUS_CANDIDATE_GATE_REPORTER = "autonomous_candidate_gate_reporter"
    AUTONOMOUS_REVISION_FAILURE_SELECTOR = "autonomous_revision_failure_selector"
    AUTONOMOUS_REVISION_CAUSAL_HANDLE_SELECTOR = "autonomous_revision_causal_handle_selector"
    AUTONOMOUS_REVISION_CANDIDATE_REVISER = "autonomous_revision_candidate_reviser"
    AUTONOMOUS_REVISION_DIFF_REPORTER = "autonomous_revision_diff_reporter"
    AUTONOMOUS_REVISION_ABLATION_VARIANT_BUILDER = (
        "autonomous_revision_ablation_variant_builder"
    )
    AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARATOR = (
        "autonomous_revision_ablation_reread_comparator"
    )
    AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARATOR = (
        "autonomous_revision_old_new_rival_comparator"
    )
    AUTONOMOUS_REVISION_LOCAL_LAW_REPORTER = "autonomous_revision_local_law_reporter"
    EXECUTED_ABLATION_INTERNAL_COMPARATOR = "executed_ablation_internal_comparator"
    ABLATION_INFORMED_BASE_SELECTOR = "ablation_informed_base_selector"
    ABLATION_INFORMED_HANDLE_SELECTOR = "ablation_informed_handle_selector"
    ABLATION_INFORMED_PATCH_PROPOSER = "ablation_informed_patch_proposer"
    BOUNDED_MACRO_RECOMPOSER = "bounded_macro_recomposer"
    OBJECT_MOTION_CAUSALITY_GENERATOR = "object_motion_causality_generator"
    RESIDUAL_INTERVENTION_GENERATOR = "residual_intervention_generator"
    NONLOCAL_LAW_GUIDED_GENERATOR = "nonlocal_law_guided_generator"
    SELECTED_NONLOCAL_LAW_TARGET_GENERATOR = "selected_nonlocal_law_target_generator"
    SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATOR = (
        "selected_target_cycle_mechanism_visibility_generator"
    )
    NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATOR = (
        "nonlocal_law_candidate_reader_state_evaluator"
    )
    SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATOR = (
        "selected_nonlocal_law_candidate_reader_state_evaluator"
    )
    MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC = (
        "model_backed_local_law_rival_diagnostic"
    )


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

INTERNAL_FAILURE_TYPES = (
    "underplanted",
    "overexplained",
    "fake_depth",
    "weak_bridge",
    "wrong_scale",
    "unlicensed_field",
    "dead_detail",
    "motif_returns_unchanged",
    "low_crisis",
    "rival_stronger_local_embodiment",
    "paraphrase_capture",
    "cadence_or_register_damage",
    "thesis_replacing_artifact",
)

INTERNAL_FAILURE_TYPE_ALIASES = {
    "overexplanation": "overexplained",
    "scaffold_leakage": "thesis_replacing_artifact",
    "wrong_register": "cadence_or_register_damage",
    "accidental_comedy": "wrong_scale",
    "cliche_contamination": "unlicensed_field",
    "pasted_ending": "motif_returns_unchanged",
    "unearned_cosmic_scale": "wrong_scale",
}

INTERNAL_HOSTILE_RISK_FAILURE_TYPE_MAP = {
    "fake_depth": "fake_depth",
    "overexplanation": "overexplained",
    "scaffold_leakage": "thesis_replacing_artifact",
    "wrong_register": "cadence_or_register_damage",
    "accidental_comedy": "wrong_scale",
    "cliche_contamination": "unlicensed_field",
    "thesis_replacing_artifact": "thesis_replacing_artifact",
    "pasted_ending": "motif_returns_unchanged",
    "unearned_cosmic_scale": "wrong_scale",
}

INTERNAL_STREAM_READER_SCHEMA = WorkerSchema(
    name="InternalStreamReaderOutput",
    version="1",
    artifact_type="internal_stream_reader_trace",
)

INTERNAL_REREAD_READER_SCHEMA = WorkerSchema(
    name="InternalRereadReaderOutput",
    version="1",
    artifact_type="internal_reread_reader_trace",
)

FORENSIC_GROUNDING_READER_SCHEMA = WorkerSchema(
    name="ForensicGroundingReaderOutput",
    version="1",
    artifact_type="forensic_grounding_report",
)

HOSTILE_INTERNAL_READER_SCHEMA = WorkerSchema(
    name="HostileInternalReaderOutput",
    version="1",
    artifact_type="hostile_reader_report",
)

INTERNAL_RIVAL_COMPARISON_SCHEMA = WorkerSchema(
    name="InternalRivalComparisonOutput",
    version="1",
    artifact_type="internal_rival_comparison",
)

INTERNAL_FAILURE_DIAGNOSIS_SCHEMA = WorkerSchema(
    name="InternalFailureDiagnosisOutput",
    version="1",
    artifact_type="internal_failure_diagnosis",
)

TARGETED_RECOMPOSITION_PLAN_SCHEMA = WorkerSchema(
    name="TargetedRecompositionPlanOutput",
    version="1",
    artifact_type="targeted_recomposition_plan",
)

COUNTERFACTUAL_ABLATION_PLAN_SCHEMA = WorkerSchema(
    name="CounterfactualAblationPlanOutput",
    version="1",
    artifact_type="counterfactual_ablation_plan",
)

AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA = WorkerSchema(
    name="AutonomousCandidateGateReportOutput",
    version="1",
    artifact_type="autonomous_candidate_gate_report",
)

INTERNAL_READER_LAB_MODEL_SCHEMAS = (
    INTERNAL_STREAM_READER_SCHEMA,
    INTERNAL_REREAD_READER_SCHEMA,
    FORENSIC_GROUNDING_READER_SCHEMA,
    HOSTILE_INTERNAL_READER_SCHEMA,
    INTERNAL_RIVAL_COMPARISON_SCHEMA,
    INTERNAL_FAILURE_DIAGNOSIS_SCHEMA,
    TARGETED_RECOMPOSITION_PLAN_SCHEMA,
    COUNTERFACTUAL_ABLATION_PLAN_SCHEMA,
    AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA,
)

AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA = WorkerSchema(
    name="AutonomousRevisionSelectedFailureOutput",
    version="1",
    artifact_type="selected_failure_diagnosis",
)

AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA = WorkerSchema(
    name="AutonomousRevisionCausalHandleSelectionOutput",
    version="1",
    artifact_type="causal_handle_selection",
)

AUTONOMOUS_REVISION_PATCH_PROPOSAL_SCHEMA = WorkerSchema(
    name="AutonomousRevisionPatchProposalOutput",
    version="1",
    artifact_type="revision_patch_proposal",
)

# Compatibility alias for older revision-worker call sites. The model worker now
# proposes bounded patches; the controller owns revised_candidate_text assembly.
AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA = AUTONOMOUS_REVISION_PATCH_PROPOSAL_SCHEMA

AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA = WorkerSchema(
    name="AutonomousRevisionDiffReportOutput",
    version="1",
    artifact_type="revision_diff_report",
)

AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA = WorkerSchema(
    name="AutonomousRevisionAblationVariantSetOutput",
    version="1",
    artifact_type="ablation_variant_set",
)

AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA = WorkerSchema(
    name="AutonomousRevisionAblationRereadComparisonOutput",
    version="1",
    artifact_type="ablation_reread_comparison",
)

AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA = WorkerSchema(
    name="AutonomousRevisionOldNewRivalComparisonOutput",
    version="1",
    artifact_type="old_new_rival_comparison",
)

AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA = WorkerSchema(
    name="AutonomousRevisionLocalLawCaseNoteOutput",
    version="1",
    artifact_type="local_law_case_note",
)

AUTONOMOUS_REVISION_MODEL_SCHEMAS = (
    AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA,
    AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA,
    AUTONOMOUS_REVISION_PATCH_PROPOSAL_SCHEMA,
    AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA,
    AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA,
)

EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA = WorkerSchema(
    name="ExecutedAblationInternalComparisonOutput",
    version="1",
    artifact_type="ablation_internal_reader_comparison",
)

EXECUTED_ABLATION_MODEL_SCHEMAS = (
    EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA,
)

ABLATION_INFORMED_BASE_SELECTION_SCHEMA = WorkerSchema(
    name="AblationInformedBaseSelectionOutput",
    version="1",
    artifact_type="cycle2_base_candidate_selection",
)

ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA = WorkerSchema(
    name="AblationInformedHandleSelectionOutput",
    version="1",
    artifact_type="selected_next_failure_or_handle",
)

ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA = WorkerSchema(
    name="AblationInformedPatchProposalOutput",
    version="1",
    artifact_type="cycle2_patch_proposal",
)

ABLATION_INFORMED_REVISION_MODEL_SCHEMAS = (
    ABLATION_INFORMED_BASE_SELECTION_SCHEMA,
    ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
    ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
)

BOUNDED_MACRO_RECOMPOSITION_SCHEMA = WorkerSchema(
    name="BoundedMacroRecompositionOutput",
    version="1",
    artifact_type="model_bounded_macro_recomposition",
)

OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA = WorkerSchema(
    name="ObjectMotionCausalityGenerationOutput",
    version="1",
    artifact_type="model_object_motion_causality_generation",
)

RESIDUAL_INTERVENTION_GENERATION_SCHEMA = WorkerSchema(
    name="ResidualInterventionGenerationOutput",
    version="1",
    artifact_type="model_residual_intervention_generation",
)

NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA = WorkerSchema(
    name="NonlocalLawGuidedGenerationOutput",
    version="1",
    artifact_type="model_nonlocal_law_guided_generation",
)

SELECTED_NONLOCAL_LAW_TARGET_GENERATION_SCHEMA = WorkerSchema(
    name="SelectedNonlocalLawTargetGenerationOutput",
    version="1",
    artifact_type="model_selected_nonlocal_law_target_generation",
)

SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATION_SCHEMA = WorkerSchema(
    name="SelectedTargetCycleMechanismVisibilityGenerationOutput",
    version="1",
    artifact_type="model_selected_target_cycle_mechanism_visibility_generation",
)

NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA = WorkerSchema(
    name="NonlocalLawCandidateReaderStateEvaluationOutput",
    version="1",
    artifact_type="model_nonlocal_law_candidate_reader_state_evaluation",
)

SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA = WorkerSchema(
    name="SelectedNonlocalLawCandidateReaderStateEvaluationOutput",
    version="1",
    artifact_type="model_selected_nonlocal_law_candidate_reader_state_evaluation",
)

MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC_SCHEMA = WorkerSchema(
    name="ModelBackedLocalLawRivalDiagnosticOutput",
    version="1",
    artifact_type="model_backed_local_law_rival_diagnostic",
)

BOUNDED_MACRO_RECOMPOSITION_MODEL_SCHEMAS = (
    BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
    OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
    RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
    NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA,
    SELECTED_NONLOCAL_LAW_TARGET_GENERATION_SCHEMA,
    SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATION_SCHEMA,
)

LOCAL_LAW_RIVAL_DIAGNOSTIC_MODEL_SCHEMAS = (
    MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC_SCHEMA,
)

NONLOCAL_LAW_CANDIDATE_READER_STATE_MODEL_SCHEMAS = (
    NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA,
    SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA,
)

LIVE_MODEL_WORKER_SCHEMAS = (
    LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS
    + LIVE_MINIMAL_REREAD_MODEL_SCHEMAS
    + EVALUATION_MODEL_SCHEMAS
    + PILOT_MODEL_SCHEMAS
    + INTERNAL_READER_LAB_MODEL_SCHEMAS
    + AUTONOMOUS_REVISION_MODEL_SCHEMAS
    + EXECUTED_ABLATION_MODEL_SCHEMAS
    + ABLATION_INFORMED_REVISION_MODEL_SCHEMAS
    + BOUNDED_MACRO_RECOMPOSITION_MODEL_SCHEMAS
    + LOCAL_LAW_RIVAL_DIAGNOSTIC_MODEL_SCHEMAS
    + NONLOCAL_LAW_CANDIDATE_READER_STATE_MODEL_SCHEMAS
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
            "text": {"type": "string"},
            "generation_rule": {"type": "string"},
            "risks": _string_array_schema(),
        },
        [
            "baseline_id",
            "text",
            "generation_rule",
            "risks",
        ],
    )


def pilot_raw_model_baseline_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "baseline_id": {"type": "string"},
            "text": {"type": "string"},
            "risks": _string_array_schema(),
        },
        [
            "baseline_id",
            "text",
            "risks",
        ],
    )


def _internal_attention_point_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "span": {"type": "string"},
            "reason": {"type": "string"},
        },
        ["span", "reason"],
    )


def _internal_confusion_point_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "span": {"type": "string"},
            "issue": {"type": "string"},
        },
        ["span", "issue"],
    )


def _internal_overexplicitness_point_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "marker": {"type": "string"},
            "risk": {"type": "string"},
        },
        ["marker", "risk"],
    )


def _internal_motif_return_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "motif": {"type": "string"},
            "first_read_state": {"type": "string"},
            "reread_state": {"type": "string"},
        },
        ["motif", "first_read_state", "reread_state"],
    )


def _internal_reread_gain_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "score": {"type": "number"},
            "scale": {"type": "string"},
            "not_human_score": {"type": "boolean"},
        },
        ["score", "scale", "not_human_score"],
    )


def _internal_support_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "claim": {"type": "string"},
            "source_label": {"type": "string"},
            "quoted_span": {"type": "string"},
            "support_reason": {"type": "string"},
        },
        ["claim", "source_label", "quoted_span", "support_reason"],
    )


def _internal_attack_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "risk_type": {"type": "string"},
            "finding": {"type": "string"},
        },
        ["risk_type", "finding"],
    )


def _internal_source_classes_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "Text A": {"type": "string"},
            "Text B": {"type": "string"},
            "Text C": {"type": "string"},
            "Text D": {"type": "string"},
        },
        ["Text A", "Text B", "Text C", "Text D"],
    )


def _internal_score_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "label": {"type": "string"},
            "source_class": {"type": "string"},
            "first_read_clarity_score": {"type": "integer"},
            "reread_transformation_score": {"type": "integer"},
            "local_embodiment_score": {"type": "integer"},
            "compression_score": {"type": "integer"},
        },
        [
            "label",
            "source_class",
            "first_read_clarity_score",
            "reread_transformation_score",
            "local_embodiment_score",
            "compression_score",
        ],
    )


def _internal_failure_type_schema() -> dict[str, Any]:
    return {"type": "string", "enum": list(INTERNAL_FAILURE_TYPES)}


def _internal_failure_type_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": _internal_failure_type_schema(),
    }


def _internal_failure_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "failure_type": _internal_failure_type_schema(),
            "diagnosis": {"type": "string"},
            "evidence_artifacts": _string_array_schema(),
            "severity": {"type": "string"},
        },
        ["failure_type", "diagnosis", "evidence_artifacts", "severity"],
    )


def _internal_plan_item_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "step_id": {"type": "string"},
            "target_region": {"type": "string"},
            "causal_handle": {"type": "string"},
            "failure_being_addressed": {"type": "string"},
            "protected_effects": _string_array_schema(),
            "forbidden_changes": _string_array_schema(),
            "expected_improvement": {"type": "string"},
            "verification_plan": {"type": "string"},
        },
        [
            "step_id",
            "target_region",
            "causal_handle",
            "failure_being_addressed",
            "protected_effects",
            "forbidden_changes",
            "expected_improvement",
            "verification_plan",
        ],
    )


def _internal_ablation_test_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "ablation_id": {"type": "string"},
            "suspected_causal_handle": {"type": "string"},
            "ablation_operation": {"type": "string"},
            "predicted_reader_state_effect": {"type": "string"},
            "pass_fail_criterion": {"type": "string"},
        },
        [
            "ablation_id",
            "suspected_causal_handle",
            "ablation_operation",
            "predicted_reader_state_effect",
            "pass_fail_criterion",
        ],
    )


def _internal_gate_result_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "gate_name": {"type": "string"},
            "passed": {"type": "boolean"},
            "blocking_defects": _string_array_schema(),
            "record": {"type": "boolean"},
        },
        ["gate_name", "passed", "blocking_defects", "record"],
    )


def internal_stream_reader_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "candidate_label": {"type": "string"},
            "retained_images": _string_array_schema(),
            "dropped_details": _string_array_schema(),
            "live_motifs": _string_array_schema(),
            "attention_points": {"type": "array", "items": _internal_attention_point_schema()},
            "confusion_points": {"type": "array", "items": _internal_confusion_point_schema()},
            "overexplicitness_points": {
                "type": "array",
                "items": _internal_overexplicitness_point_schema(),
            },
            "first_read_opening_interpretation": {"type": "string"},
            "first_read_summary": {"type": "string"},
            "bounded_mode": {"type": "boolean"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "candidate_label",
            "retained_images",
            "dropped_details",
            "live_motifs",
            "attention_points",
            "confusion_points",
            "overexplicitness_points",
            "first_read_opening_interpretation",
            "first_read_summary",
            "bounded_mode",
            "not_human_data",
        ],
    )


def internal_reread_reader_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "candidate_label": {"type": "string"},
            "opening_changed": {"type": "boolean"},
            "opening_words_images_changed": _string_array_schema(),
            "hidden_consequence_clearer": {"type": "string"},
            "motif_returned_changed": {"type": "array", "items": _internal_motif_return_schema()},
            "reread_summary": {"type": "string"},
            "reread_gain_estimate": _internal_reread_gain_schema(),
            "not_human_data": {"type": "boolean"},
        },
        [
            "candidate_label",
            "opening_changed",
            "opening_words_images_changed",
            "hidden_consequence_clearer",
            "motif_returned_changed",
            "reread_summary",
            "reread_gain_estimate",
            "not_human_data",
        ],
    )


def forensic_grounding_reader_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "claimed_effects": _string_array_schema(),
            "exact_textual_support": {"type": "array", "items": _internal_support_schema()},
            "unsupported_claims": _string_array_schema(),
            "fake_depth_risk": {"type": "string"},
            "reread_claims_grounded": {"type": "boolean"},
            "grounding_verdict": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "claimed_effects",
            "exact_textual_support",
            "unsupported_claims",
            "fake_depth_risk",
            "reread_claims_grounded",
            "grounding_verdict",
            "not_human_data",
        ],
    )


def hostile_internal_reader_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "attacks": {"type": "array", "items": _internal_attack_schema()},
            "blocking_risks": _string_array_schema(),
            "fake_depth": {"type": "string"},
            "overexplanation": {"type": "string"},
            "scaffold_leakage": {"type": "string"},
            "wrong_register": {"type": "string"},
            "accidental_comedy": {"type": "string"},
            "cliche_contamination": {"type": "string"},
            "thesis_replacing_artifact": {"type": "string"},
            "pasted_ending": {"type": "string"},
            "unearned_cosmic_scale": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "attacks",
            "blocking_risks",
            "fake_depth",
            "overexplanation",
            "scaffold_leakage",
            "wrong_register",
            "accidental_comedy",
            "cliche_contamination",
            "thesis_replacing_artifact",
            "pasted_ending",
            "unearned_cosmic_scale",
            "not_human_data",
        ],
    )


def internal_rival_comparison_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "source_classes_by_label": _internal_source_classes_schema(),
            "strongest_by_first_read_clarity": {"type": "string"},
            "strongest_by_reread_transformation": {"type": "string"},
            "strongest_by_local_embodiment": {"type": "string"},
            "strongest_by_compression_necessity": {"type": "string"},
            "abi_candidate_wins_where": _string_array_schema(),
            "abi_candidate_loses_where": _string_array_schema(),
            "rival_preservation_remains_required": {"type": "boolean"},
            "strongest_rival_present": {"type": "boolean"},
            "scores": {"type": "array", "items": _internal_score_schema()},
            "not_human_data": {"type": "boolean"},
        },
        [
            "source_classes_by_label",
            "strongest_by_first_read_clarity",
            "strongest_by_reread_transformation",
            "strongest_by_local_embodiment",
            "strongest_by_compression_necessity",
            "abi_candidate_wins_where",
            "abi_candidate_loses_where",
            "rival_preservation_remains_required",
            "strongest_rival_present",
            "scores",
            "not_human_data",
        ],
    )


def internal_failure_diagnosis_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "failure_types_present": _internal_failure_type_array_schema(),
            "failures": {"type": "array", "items": _internal_failure_schema()},
            "requires_recomposition": {"type": "boolean"},
            "reread_gain_estimate": _internal_reread_gain_schema(),
            "not_human_data": {"type": "boolean"},
        },
        [
            "failure_types_present",
            "failures",
            "requires_recomposition",
            "reread_gain_estimate",
            "not_human_data",
        ],
    )


def targeted_recomposition_plan_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "bounded": {"type": "boolean"},
            "does_not_rewrite_artifact": {"type": "boolean"},
            "plan_items": {"type": "array", "items": _internal_plan_item_schema()},
            "protected_effects": _string_array_schema(),
            "forbidden_changes": _string_array_schema(),
            "verification_plan": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "bounded",
            "does_not_rewrite_artifact",
            "plan_items",
            "protected_effects",
            "forbidden_changes",
            "verification_plan",
            "not_human_data",
        ],
    )


def counterfactual_ablation_plan_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "ablation_tests": {"type": "array", "items": _internal_ablation_test_schema()},
            "suspected_causal_handles": _string_array_schema(),
            "operations": _string_array_schema(),
            "predicted_reader_state_effect": {"type": "string"},
            "pass_fail_criteria": _string_array_schema(),
            "not_human_data": {"type": "boolean"},
        },
        [
            "ablation_tests",
            "suspected_causal_handles",
            "operations",
            "predicted_reader_state_effect",
            "pass_fail_criteria",
            "not_human_data",
        ],
    )


def autonomous_candidate_gate_report_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "profile": {"type": "string"},
            "passed": {"type": "boolean"},
            "eligible": {"type": "boolean"},
            "required_gates": _string_array_schema(),
            "gate_results": {"type": "array", "items": _internal_gate_result_schema()},
            "failed_gates": _string_array_schema(),
            "missing_gates": _string_array_schema(),
            "human_validation_required": {"type": "boolean"},
            "paper_validation_required": {"type": "boolean"},
            "phase_shift_claim": {"type": "boolean"},
            "final_gates_marked_passed": _string_array_schema(),
            "summary_verdict": {"type": "string"},
        },
        [
            "profile",
            "passed",
            "eligible",
            "required_gates",
            "gate_results",
            "failed_gates",
            "missing_gates",
            "human_validation_required",
            "paper_validation_required",
            "phase_shift_claim",
            "final_gates_marked_passed",
            "summary_verdict",
        ],
    )


def _revision_span_ref_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "source_label": {"type": "string"},
            "source_class": {"type": "string"},
            "artifact_id": {"type": "string"},
            "region": {"type": "string"},
            "selection_basis": {"type": "string"},
        },
        ["source_label", "source_class", "artifact_id", "region", "selection_basis"],
    )


def _revision_changed_span_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "changed_span_id": {"type": "string"},
            "patch_span_id": {"type": "string"},
            "source_patch_span_ids": _string_array_schema(),
            "before": {"type": "string"},
            "after": {"type": "string"},
            "region": {"type": "string"},
            "inside_target": {"type": "boolean"},
            "within_selected_target": {"type": "boolean"},
            "requires_target_expansion": {"type": "boolean"},
            "target_expansion_reason": {"type": "string"},
            "reason": {"type": "string"},
        },
        [
            "changed_span_id",
            "patch_span_id",
            "source_patch_span_ids",
            "before",
            "after",
            "region",
            "inside_target",
            "within_selected_target",
            "requires_target_expansion",
            "target_expansion_reason",
            "reason",
        ],
    )


def _revision_patch_target_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "patch_target_id": {"type": "string"},
            "target_region_label": {"type": "string"},
            "target_region_description": {"type": "string"},
            "allowed_span_ref": {"type": "string"},
            "text_window": {"type": "string"},
            "paragraph_index": {"type": "integer"},
            "protected_outside_spans": _string_array_schema(),
        },
        [
            "patch_target_id",
            "target_region_label",
            "target_region_description",
            "allowed_span_ref",
            "text_window",
            "paragraph_index",
            "protected_outside_spans",
        ],
    )


AUTONOMOUS_REVISION_PATCH_OPERATIONS = (
    "replace",
    "insert_after",
    "insert_before",
    "delete",
    "compress",
)


def _revision_patch_operation_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "enum": list(AUTONOMOUS_REVISION_PATCH_OPERATIONS),
    }


def _revision_patch_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "patch_id": {"type": "string"},
            "patch_span_id": {"type": "string"},
            "patch_target_id": {"type": "string"},
            "operation": _revision_patch_operation_schema(),
            "replacement_text": {"type": "string"},
            "inserted_text": {"type": "string"},
            "failure_addressed": {"type": "string"},
            "causal_handle_id": {"type": "string"},
            "protected_effects_preserved": _string_array_schema(),
            "forbidden_changes_respected": _string_array_schema(),
            "rationale": {"type": "string"},
            "expected_reader_state_change": {"type": "string"},
            "requires_target_expansion": {"type": "boolean"},
            "target_expansion_reason": {"type": "string"},
            "confidence": {"type": "number"},
            "uncertainty": {"type": "string"},
        },
        [
            "patch_id",
            "patch_span_id",
            "patch_target_id",
            "operation",
            "replacement_text",
            "inserted_text",
            "failure_addressed",
            "causal_handle_id",
            "protected_effects_preserved",
            "forbidden_changes_respected",
            "rationale",
            "expected_reader_state_change",
            "requires_target_expansion",
            "target_expansion_reason",
            "confidence",
            "uncertainty",
        ],
    )


def _revision_variant_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "variant_id": {"type": "string"},
            "operation": {"type": "string"},
            "variant_probe": {"type": "string"},
            "ablation_probe": {"type": "string"},
            "text": {"type": "string"},
            "executed": {"type": "boolean"},
            "expected_reader_state_change": {"type": "string"},
            "uncertainty": {"type": "string"},
        },
        [
            "variant_id",
            "operation",
            "variant_probe",
            "ablation_probe",
            "text",
            "executed",
            "expected_reader_state_change",
            "uncertainty",
        ],
    )


def _revision_ablation_row_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "row_id": {"type": "string"},
            "comparison_summary": {"type": "string"},
            "predicted_or_observed_effect": {"type": "string"},
            "reader_state_effect_estimate": {"type": "string"},
            "rationale": {"type": "string"},
            "risk_notes": {"type": "string"},
            "uncertainty": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "row_id",
            "comparison_summary",
            "predicted_or_observed_effect",
            "reader_state_effect_estimate",
            "rationale",
            "risk_notes",
            "uncertainty",
            "not_human_data",
        ],
    )


AUTONOMOUS_REVISION_ABLATION_EVIDENCE_BASIS = (
    "actual_ablation_variant",
    "planned_ablation_probe",
    "predicted_ablation_effect",
    "actual_ablation_reread_evaluation",
)


def _revision_ablation_evidence_basis_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "enum": list(AUTONOMOUS_REVISION_ABLATION_EVIDENCE_BASIS),
    }


AUTONOMOUS_REVISION_JUDGMENT_KEYS = (
    "reread_transformation_improved",
    "opening_transformation_improved",
    "local_embodiment_improved",
    "overexplanation_decreased",
    "fake_depth_risk_decreased",
    "revised_candidate_became_more_schematic",
    "rival_still_beats_candidate",
    "another_revision_cycle_needed",
)

AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS = (
    "original_candidate_text",
    "revised_candidate_text",
    "strongest_rival_text",
    "direct_prompt_baseline_text",
    "raw_model_baseline_text",
    "actual_ablation_variant",
    "planned_ablation_probe",
    "predicted_ablation_effect",
    "prior_reader_lab_evidence",
    "revision_diff_report",
    "ablation_reread_comparison",
    "local_law_case_note",
)


def _revision_judgment_provenance_schema() -> dict[str, Any]:
    return _object_schema(
        {
            key: _provenance_token_array_schema()
            for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS
        },
        list(AUTONOMOUS_REVISION_JUDGMENT_KEYS),
    )


def _revision_judgment_rationale_schema() -> dict[str, Any]:
    return _object_schema(
        {key: {"type": "string"} for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS},
        list(AUTONOMOUS_REVISION_JUDGMENT_KEYS),
    )


def autonomous_revision_selected_failure_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "selection_rule": {"type": "string"},
            "selected_failure_type": _internal_failure_type_schema(),
            "selected_diagnosis": {"type": "string"},
            "severity": {"type": "string"},
            "reader_lab_evidence_artifacts": _string_array_schema(),
            "source_failure_index": {"type": "integer"},
            "references_live_reader_lab_evidence": {"type": "boolean"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "selection_rule",
            "selected_failure_type",
            "selected_diagnosis",
            "severity",
            "reader_lab_evidence_artifacts",
            "source_failure_index",
            "references_live_reader_lab_evidence",
            "not_human_data",
        ],
    )


def autonomous_revision_causal_handle_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "bounded_target": {"type": "boolean"},
            "target_count": {"type": "integer"},
            "does_not_rebuild_artifact": {"type": "boolean"},
            "selected_patch_target_id": {"type": "string"},
            "span_ref": _revision_span_ref_schema(),
            "target_region_label": {"type": "string"},
            "target_region_description": {"type": "string"},
            "allowed_span_refs": _string_array_schema(),
            "protected_outside_spans": _string_array_schema(),
            "quoted_text": {"type": "string"},
            "causal_handle": {"type": "string"},
            "local_law_hypothesis": {"type": "string"},
            "suspected_failure": {"type": "string"},
            "why_it_might_be_junk": {"type": "string"},
            "why_it_might_be_treasure": {"type": "string"},
            "connotation_or_register_risk": {"type": "string"},
            "variant_probe": {"type": "string"},
            "ablation_probe": {"type": "string"},
            "expected_reader_state_change": {"type": "string"},
            "uncertainty": {"type": "string"},
            "protected_effects": _string_array_schema(),
            "forbidden_changes": _string_array_schema(),
            "not_human_data": {"type": "boolean"},
        },
        [
            "bounded_target",
            "target_count",
            "does_not_rebuild_artifact",
            "selected_patch_target_id",
            "span_ref",
            "target_region_label",
            "target_region_description",
            "allowed_span_refs",
            "protected_outside_spans",
            "quoted_text",
            "causal_handle",
            "local_law_hypothesis",
            "suspected_failure",
            "why_it_might_be_junk",
            "why_it_might_be_treasure",
            "connotation_or_register_risk",
            "variant_probe",
            "ablation_probe",
            "expected_reader_state_change",
            "uncertainty",
            "protected_effects",
            "forbidden_changes",
            "not_human_data",
        ],
    )


def autonomous_revision_revised_candidate_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "proposal_id": {"type": "string"},
            "source_candidate_artifact_id": {"type": "string"},
            "targeted_causal_handle": {"type": "string"},
            "target_region_label": {"type": "string"},
            "patches": {"type": "array", "items": _revision_patch_schema()},
            "bounded_patch_set": {"type": "boolean"},
            "full_rewrite": {"type": "boolean"},
            "target_region_expanded": {"type": "boolean"},
            "expanded_target_region": {"type": "string"},
            "expansion_reason": {"type": "string"},
            "protected_effects": _string_array_schema(),
            "forbidden_changes_respected": _string_array_schema(),
            "non_final": {"type": "boolean"},
            "candidate_only": {"type": "boolean"},
            "not_human_validated": {"type": "boolean"},
            "human_validated": {"type": "boolean"},
            "not_finalization_eligible": {"type": "boolean"},
            "finalization_eligible": {"type": "boolean"},
            "phase_shift_claim": {"type": "boolean"},
            "no_phase_shift_claim": {"type": "boolean"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "proposal_id",
            "source_candidate_artifact_id",
            "targeted_causal_handle",
            "target_region_label",
            "patches",
            "bounded_patch_set",
            "full_rewrite",
            "target_region_expanded",
            "expanded_target_region",
            "expansion_reason",
            "protected_effects",
            "forbidden_changes_respected",
            "non_final",
            "candidate_only",
            "not_human_validated",
            "human_validated",
            "not_finalization_eligible",
            "finalization_eligible",
            "phase_shift_claim",
            "no_phase_shift_claim",
            "not_human_data",
        ],
    )


def autonomous_revision_diff_report_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "full_rewrite": {"type": "boolean"},
            "bounded_change": {"type": "boolean"},
            "operation_type": {"type": "string"},
            "target_region": {"type": "string"},
            "target_region_label": {"type": "string"},
            "target_region_description": {"type": "string"},
            "allowed_span_refs": _string_array_schema(),
            "allowed_patch_targets": {
                "type": "array",
                "items": _revision_patch_target_schema(),
            },
            "protected_outside_spans": _string_array_schema(),
            "causal_handle": {"type": "string"},
            "original_excerpt": {"type": "string"},
            "revised_excerpt": {"type": "string"},
            "changed_spans": {"type": "array", "items": _revision_changed_span_schema()},
            "target_region_expanded": {"type": "boolean"},
            "expanded_target_region": {"type": "string"},
            "expansion_reason": {"type": "string"},
            "target_expansion_justification": {"type": "string"},
            "protected_effects_preserved": _string_array_schema(),
            "forbidden_changes_honored": _string_array_schema(),
            "explanation": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "full_rewrite",
            "bounded_change",
            "operation_type",
            "target_region",
            "target_region_label",
            "target_region_description",
            "allowed_span_refs",
            "allowed_patch_targets",
            "protected_outside_spans",
            "causal_handle",
            "original_excerpt",
            "revised_excerpt",
            "changed_spans",
            "target_region_expanded",
            "expanded_target_region",
            "expansion_reason",
            "target_expansion_justification",
            "protected_effects_preserved",
            "forbidden_changes_honored",
            "explanation",
            "not_human_data",
        ],
    )


def autonomous_revision_ablation_variant_set_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "targeted_causal_handle": {"type": "string"},
            "variants": {"type": "array", "items": _revision_variant_schema()},
            "does_not_select_winner": {"type": "boolean"},
            "not_human_data": {"type": "boolean"},
        },
        ["targeted_causal_handle", "variants", "does_not_select_winner", "not_human_data"],
    )


def autonomous_revision_ablation_reread_comparison_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "candidate_label": {"type": "string"},
            "comparison_rows": {"type": "array", "items": _revision_ablation_row_schema()},
            "summary": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        ["candidate_label", "comparison_rows", "summary", "not_human_data"],
    )


def autonomous_revision_old_new_rival_comparison_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "reread_transformation_improved": {"type": "boolean"},
            "opening_transformation_improved": {"type": "boolean"},
            "local_embodiment_improved": {"type": "boolean"},
            "overexplanation_decreased": {"type": "boolean"},
            "fake_depth_risk_decreased": {"type": "boolean"},
            "revised_candidate_became_more_schematic": {"type": "boolean"},
            "strongest_rival_present": {"type": "boolean"},
            "rival_still_beats_candidate": {"type": "boolean"},
            "another_revision_cycle_needed": {"type": "boolean"},
            "comparison_basis": {"type": "string"},
            "rival_pressure_preserved": {"type": "boolean"},
            "old_new_summary": {"type": "string"},
            "rival_pressure_summary": {"type": "string"},
            "judgment_provenance": _revision_judgment_provenance_schema(),
            "judgment_rationale": _revision_judgment_rationale_schema(),
            "not_human_data": {"type": "boolean"},
        },
        [
            "reread_transformation_improved",
            "opening_transformation_improved",
            "local_embodiment_improved",
            "overexplanation_decreased",
            "fake_depth_risk_decreased",
            "revised_candidate_became_more_schematic",
            "strongest_rival_present",
            "rival_still_beats_candidate",
            "another_revision_cycle_needed",
            "comparison_basis",
            "rival_pressure_preserved",
            "old_new_summary",
            "rival_pressure_summary",
            "judgment_provenance",
            "judgment_rationale",
            "not_human_data",
        ],
    )


def autonomous_revision_local_law_case_note_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "principle": {"type": "string"},
            "span_ref": _revision_span_ref_schema(),
            "quoted_text": {"type": "string"},
            "local_law_hypothesis": {"type": "string"},
            "suspected_failure": {"type": "string"},
            "why_it_might_be_junk": {"type": "string"},
            "why_it_might_be_treasure": {"type": "string"},
            "connotation_or_register_risk": {"type": "string"},
            "variant_probe": {"type": "string"},
            "ablation_probe": {"type": "string"},
            "expected_reader_state_change": {"type": "string"},
            "uncertainty": {"type": "string"},
            "preserve_irregularity_rule": {"type": "string"},
            "comparison_result": _object_schema(
                {
                    "another_revision_cycle_needed": {"type": "boolean"},
                    "rival_still_beats_candidate": {"type": "boolean"},
                },
                ["another_revision_cycle_needed", "rival_still_beats_candidate"],
            ),
            "not_human_data": {"type": "boolean"},
        },
        [
            "principle",
            "span_ref",
            "quoted_text",
            "local_law_hypothesis",
            "suspected_failure",
            "why_it_might_be_junk",
            "why_it_might_be_treasure",
            "connotation_or_register_risk",
            "variant_probe",
            "ablation_probe",
            "expected_reader_state_change",
            "uncertainty",
            "preserve_irregularity_rule",
            "comparison_result",
            "not_human_data",
        ],
    )


def executed_ablation_internal_comparison_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "comparison_rows": {
                "type": "array",
                "items": _object_schema(
                    {
                        "variant_id": {"type": "string"},
                        "comparison_summary": {"type": "string"},
                        "reader_state_effect_estimate": {"type": "string"},
                        "rationale": {"type": "string"},
                        "uncertainty": {"type": "string"},
                        "risk_notes": {"type": "string"},
                        "not_human_data": {"type": "boolean"},
                    },
                    [
                        "variant_id",
                        "comparison_summary",
                        "reader_state_effect_estimate",
                        "rationale",
                        "uncertainty",
                        "risk_notes",
                        "not_human_data",
                    ],
                ),
            },
            "summary": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        ["comparison_rows", "summary", "not_human_data"],
    )


def ablation_informed_base_selection_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "selected_base_candidate_id": {"type": "string"},
            "why_packet_0030_not_proven": {"type": "string"},
            "prior_repair_causal_status": {"type": "string"},
            "evidence_rationale": {"type": "string"},
            "embodiment_preserving_insight": {"type": "string"},
            "record_law_proof_answer_insight": {"type": "string"},
            "explicit_dominance_rejection_reason": {"type": "string"},
            "dominance_rejection_protected_effect_or_forbidden_change_evidence": {
                "type": "string"
            },
            "uncertainty": {"type": "string"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "selected_base_candidate_id",
            "why_packet_0030_not_proven",
            "prior_repair_causal_status",
            "evidence_rationale",
            "embodiment_preserving_insight",
            "record_law_proof_answer_insight",
            "explicit_dominance_rejection_reason",
            "dominance_rejection_protected_effect_or_forbidden_change_evidence",
            "uncertainty",
            "not_human_data",
        ],
    )


def ablation_informed_handle_selection_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "selected_next_handle": {"type": "string"},
            "why_previous_repair_weak_or_cosmetic": {"type": "string"},
            "evidence_summary": {"type": "string"},
            "why_handle_better_than_opening_patch": {"type": "string"},
            "local_law_explanation": {"type": "string"},
            "explicit_same_handle_justification": {"type": "string"},
            "same_handle_justification_evidence": {"type": "string"},
            "uncertainty": {"type": "string"},
            "strongest_rival_pressure_remains_blocking": {"type": "boolean"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "selected_next_handle",
            "why_previous_repair_weak_or_cosmetic",
            "evidence_summary",
            "why_handle_better_than_opening_patch",
            "local_law_explanation",
            "explicit_same_handle_justification",
            "same_handle_justification_evidence",
            "uncertainty",
            "strongest_rival_pressure_remains_blocking",
            "not_human_data",
        ],
    )


def ablation_informed_patch_proposal_json_schema() -> dict[str, Any]:
    return _schema_with_properties(
        {
            "patches": {
                "type": "array",
                "items": _object_schema(
                    {
                        "patch_span_id": {"type": "string"},
                        "replacement_text": {"type": "string"},
                        "rationale": {"type": "string"},
                        "local_law_explanation": {"type": "string"},
                        "uncertainty": {"type": "string"},
                    },
                    [
                        "patch_span_id",
                        "replacement_text",
                        "rationale",
                        "local_law_explanation",
                        "uncertainty",
                    ],
                ),
            },
            "preserves_necessary_philosophical_pressure": {"type": "string"},
            "avoids_full_rewrite": {"type": "boolean"},
            "not_human_data": {"type": "boolean"},
        },
        [
            "patches",
            "preserves_necessary_philosophical_pressure",
            "avoids_full_rewrite",
            "not_human_data",
        ],
    )


def bounded_macro_recomposition_json_schema() -> dict[str, Any]:
    constraint_mapping_item = _object_schema(
        {
            "constraint_id": {"type": "string"},
            "satisfied_claim": {"type": "boolean"},
            "supporting_replacement_excerpt": {"type": "string"},
            "rationale": {"type": "string"},
            "uncertainty": {"type": "string"},
            "risk_note": {"type": "string"},
        },
        [
            "constraint_id",
            "satisfied_claim",
            "supporting_replacement_excerpt",
            "rationale",
            "uncertainty",
            "risk_note",
        ],
    )
    active_target_mapping_item = _object_schema(
        {
            "target_id": {"type": "string"},
            "target_paragraph_ref": {"type": "string"},
            "before_excerpt": {"type": "string"},
            "supporting_replacement_excerpt": {"type": "string"},
            "what_changed": {"type": "string"},
            "rationale": {"type": "string"},
            "uncertainty": {"type": "string"},
            "unchanged": {"type": "boolean"},
            "unchanged_justification": {"type": "string"},
        },
        [
            "target_id",
            "target_paragraph_ref",
            "before_excerpt",
            "supporting_replacement_excerpt",
            "what_changed",
            "rationale",
            "uncertainty",
            "unchanged",
            "unchanged_justification",
        ],
    )
    target_paragraph_replacement_item = _object_schema(
        {
            "target_paragraph_ref": {"type": "string"},
            "before_text_sha256": {"type": "string"},
            "replacement_text": {"type": "string"},
            "active_target_ids_covered": _string_array_schema(),
            "material_change_summary": {"type": "string"},
            "preserved_effects": _string_array_schema(),
            "risk_notes": {"type": "string"},
            "uncertainty": {"type": "string"},
        },
        [
            "target_paragraph_ref",
            "before_text_sha256",
            "replacement_text",
            "active_target_ids_covered",
            "material_change_summary",
            "preserved_effects",
            "risk_notes",
            "uncertainty",
        ],
    )
    target_span_replacement_item = _object_schema(
        {
            "target_span_ref": {"type": "string"},
            "parent_target_paragraph_ref": {"type": "string"},
            "before_text_sha256": {"type": "string"},
            "replacement_excerpt": {"type": "string"},
            "active_target_ids_covered": _string_array_schema(),
            "material_change_summary": {"type": "string"},
            "risk_notes": {"type": "string"},
            "uncertainty": {"type": "string"},
        },
        [
            "target_span_ref",
            "parent_target_paragraph_ref",
            "before_text_sha256",
            "replacement_excerpt",
            "active_target_ids_covered",
            "material_change_summary",
            "risk_notes",
            "uncertainty",
        ],
    )
    return _schema_with_properties(
        {
            "replacement_section_text": {"type": "string"},
            "macro_recomposition_plan": _object_schema(
                {
                    "plan_summary": {"type": "string"},
                    "plan_steps": _string_array_schema(),
                },
                ["plan_summary", "plan_steps"],
            ),
            "section_plan": _object_schema(
                {
                    "target_movement": {"type": "string"},
                    "bounded": {"type": "boolean"},
                    "full_rewrite": {"type": "boolean"},
                    "rationale": {"type": "string"},
                },
                ["target_movement", "bounded", "full_rewrite", "rationale"],
            ),
            "constraint_mapping": {
                "type": "array",
                "items": constraint_mapping_item,
            },
            "active_target_mapping": {
                "type": "array",
                "items": active_target_mapping_item,
            },
            "target_paragraph_replacements": {
                "type": "array",
                "items": target_paragraph_replacement_item,
            },
            "target_span_replacements": {
                "type": "array",
                "items": target_span_replacement_item,
            },
            "rationale": {"type": "string"},
            "local_law_explanation": {"type": "string"},
            "uncertainty": {"type": "string"},
            "predicted_reader_state_effect": {"type": "string"},
        },
        [
            "replacement_section_text",
            "macro_recomposition_plan",
            "section_plan",
            "constraint_mapping",
            "active_target_mapping",
            "target_paragraph_replacements",
            "target_span_replacements",
            "rationale",
            "local_law_explanation",
            "uncertainty",
            "predicted_reader_state_effect",
        ],
    )


def object_motion_causality_generation_json_schema() -> dict[str, Any]:
    unit_mapping_item = _object_schema(
        {
            "unit_id": {"type": "string"},
            "before_text_excerpt": {"type": "string"},
            "replacement_text_excerpt": {"type": "string"},
            "object_motion_or_action": {"type": "string"},
            "visible_consequence": {"type": "string"},
            "how_reader_infers_pressure_before_explanation": {"type": "string"},
            "forbidden_change_avoided": {"type": "string"},
        },
        [
            "unit_id",
            "before_text_excerpt",
            "replacement_text_excerpt",
            "object_motion_or_action",
            "visible_consequence",
            "how_reader_infers_pressure_before_explanation",
            "forbidden_change_avoided",
        ],
    )
    return _schema_with_properties(
        {
            "replacement_region_text": {"type": "string"},
            "object_motion_generation_plan": _string_array_schema(),
            "target_unit_mapping": {"type": "array", "items": unit_mapping_item},
            "protected_effects_preservation_notes": _string_array_schema(),
            "uncertainty": {"type": "string"},
            "predicted_reader_effect": {"type": "string"},
            "forbidden_change_self_check": _string_array_schema(),
        },
        [
            "replacement_region_text",
            "object_motion_generation_plan",
            "target_unit_mapping",
            "protected_effects_preservation_notes",
            "uncertainty",
            "predicted_reader_effect",
            "forbidden_change_self_check",
        ],
    )


def residual_intervention_generation_json_schema() -> dict[str, Any]:
    target_unit_mapping_item = _object_schema(
        {
            "target_unit_id": {"type": "string"},
            "before_text_sha256": {"type": "string"},
            "mechanism_operation": {"type": "string"},
            "material_relation_or_action": {"type": "string"},
            "visible_consequence": {"type": "string"},
            "intended_first_read_effect": {"type": "string"},
            "protected_effects_preserved": _string_array_schema(),
            "covered_target_ids": _string_array_schema(),
        },
        [
            "target_unit_id",
            "before_text_sha256",
            "mechanism_operation",
            "material_relation_or_action",
            "visible_consequence",
            "intended_first_read_effect",
            "protected_effects_preserved",
            "covered_target_ids",
        ],
    )
    constraint_mapping_item = _object_schema(
        {
            "constraint_id": {"type": "string"},
            "how_satisfied": {"type": "string"},
            "risk_note": {"type": "string"},
        },
        ["constraint_id", "how_satisfied", "risk_note"],
    )
    return _schema_with_properties(
        {
            "replacement_region_text": {"type": "string"},
            "target_unit_mappings": {
                "type": "array",
                "items": target_unit_mapping_item,
            },
            "intervention_plan": _string_array_schema(),
            "constraint_mapping": {
                "type": "array",
                "items": constraint_mapping_item,
            },
            "protected_effects_notes": _string_array_schema(),
            "forbidden_change_self_check": _string_array_schema(),
            "uncertainty": {"type": "string"},
        },
        [
            "replacement_region_text",
            "target_unit_mappings",
            "intervention_plan",
            "constraint_mapping",
            "protected_effects_notes",
            "forbidden_change_self_check",
            "uncertainty",
        ],
    )


def nonlocal_law_guided_generation_json_schema() -> dict[str, Any]:
    safety_false = {
        "type": "boolean",
        "enum": [False],
        "description": (
            "Must be false. This is a downstream safety/escalation assertion, "
            "not current-call generation permission."
        ),
    }
    target_unit_item = _object_schema(
        {
            "target_unit_id": {"type": "string"},
            "change_summary": {"type": "string"},
            "materiality_satisfied": {"type": "boolean"},
            "semantic_satisfied": {"type": "boolean"},
        },
        [
            "target_unit_id",
            "change_summary",
            "materiality_satisfied",
            "semantic_satisfied",
        ],
    )
    requirement_item = _object_schema(
        {
            "requirement": {"type": "string"},
            "satisfied": {"type": "boolean"},
            "evidence": {"type": "string"},
        },
        ["requirement", "satisfied", "evidence"],
    )
    non_imitation_report = _object_schema(
        {
            "passed": {"type": "boolean"},
            "evidence": {"type": "string"},
            "forbidden_material_absent": _string_array_schema(),
        },
        ["passed", "evidence", "forbidden_material_absent"],
    )
    protected_strengths_report = _object_schema(
        {
            "preserved": {"type": "boolean"},
            "evidence": {"type": "string"},
            "protected_strengths": _string_array_schema(),
        },
        ["preserved", "evidence", "protected_strengths"],
    )
    forbidden_regression_report = _object_schema(
        {
            "passed": {"type": "boolean"},
            "evidence": {"type": "string"},
            "avoided_regressions": _string_array_schema(),
        },
        ["passed", "evidence", "avoided_regressions"],
    )
    evidence_acknowledgment = _object_schema(
        {
            "ablation_required": {"type": "boolean"},
            "reader_state_eval_required": {"type": "boolean"},
            "synthesis_required": {"type": "boolean"},
            "strongest_rival_remains_blocking": {"type": "boolean"},
        },
        [
            "ablation_required",
            "reader_state_eval_required",
            "synthesis_required",
            "strongest_rival_remains_blocking",
        ],
    )
    return _schema_with_properties(
        {
            "revised_text": {"type": "string"},
            "revision_summary": {"type": "string"},
            "law_application_summary": {"type": "string"},
            "target_unit_change_report": {
                "type": "array",
                "items": target_unit_item,
            },
            "materiality_self_report": {
                "type": "array",
                "items": requirement_item,
            },
            "semantic_self_report": {
                "type": "array",
                "items": requirement_item,
            },
            "non_imitation_report": non_imitation_report,
            "protected_strengths_report": protected_strengths_report,
            "forbidden_regression_report": forbidden_regression_report,
            "post_generation_evidence_plan_acknowledgment": evidence_acknowledgment,
            "generation_allowed": safety_false,
            "finality_claimed": safety_false,
            "phase_shift_claimed": safety_false,
            "strongest_rival_defeated_claimed": safety_false,
        },
        [
            "revised_text",
            "revision_summary",
            "law_application_summary",
            "target_unit_change_report",
            "materiality_self_report",
            "semantic_self_report",
            "non_imitation_report",
            "protected_strengths_report",
            "forbidden_regression_report",
            "post_generation_evidence_plan_acknowledgment",
            "generation_allowed",
            "finality_claimed",
            "phase_shift_claimed",
            "strongest_rival_defeated_claimed",
        ],
    )


def selected_nonlocal_law_target_generation_json_schema() -> dict[str, Any]:
    safety_false = {
        "type": "boolean",
        "enum": [False],
        "description": (
            "Must be false. This is a downstream safety/escalation assertion, "
            "not current-call generation permission."
        ),
    }
    target_unit_item = _object_schema(
        {
            "target_unit_id": {"type": "string"},
            "change_summary": {"type": "string"},
            "materiality_satisfied": {"type": "boolean"},
            "semantic_satisfied": {"type": "boolean"},
        },
        [
            "target_unit_id",
            "change_summary",
            "materiality_satisfied",
            "semantic_satisfied",
        ],
    )
    requirement_item = _object_schema(
        {
            "requirement": {"type": "string"},
            "satisfied": {"type": "boolean"},
            "evidence": {"type": "string"},
        },
        ["requirement", "satisfied", "evidence"],
    )
    non_imitation = _object_schema(
        {
            "passed": {"type": "boolean"},
            "evidence": {"type": "string"},
            "forbidden_material_absent": _string_array_schema(),
        },
        ["passed", "evidence", "forbidden_material_absent"],
    )
    protected = _object_schema(
        {
            "preserved": {"type": "boolean"},
            "evidence": {"type": "string"},
            "protected_strengths": _string_array_schema(),
        },
        ["preserved", "evidence", "protected_strengths"],
    )
    forbidden = _object_schema(
        {
            "passed": {"type": "boolean"},
            "evidence": {"type": "string"},
            "avoided_regressions": _string_array_schema(),
        },
        ["passed", "evidence", "avoided_regressions"],
    )
    safety_claims = _object_schema(
        {
            "finality_claimed": safety_false,
            "phase_shift_claimed": safety_false,
            "strongest_rival_defeated_claimed": safety_false,
            "current_best_supersession_claimed": safety_false,
            "generation_allowed": safety_false,
        },
        [
            "finality_claimed",
            "phase_shift_claimed",
            "strongest_rival_defeated_claimed",
            "current_best_supersession_claimed",
            "generation_allowed",
        ],
    )
    return _schema_with_properties(
        {
            "text": {"type": "string"},
            "revision_summary": {"type": "string"},
            "selected_target_application_summary": {"type": "string"},
            "living_event_sequence_repair_summary": {"type": "string"},
            "target_unit_change_report": {
                "type": "array",
                "items": target_unit_item,
            },
            "materiality_self_report": {
                "type": "array",
                "items": requirement_item,
            },
            "semantic_self_report": {
                "type": "array",
                "items": requirement_item,
            },
            "non_imitation_acknowledgement": non_imitation,
            "protected_strengths_preservation_acknowledgement": protected,
            "forbidden_regression_acknowledgement": forbidden,
            "safety_claims": safety_claims,
            "finality_claimed": safety_false,
            "phase_shift_claimed": safety_false,
            "strongest_rival_defeated_claimed": safety_false,
            "current_best_supersession_claimed": safety_false,
            "generation_allowed": safety_false,
        },
        [
            "text",
            "revision_summary",
            "selected_target_application_summary",
            "living_event_sequence_repair_summary",
            "target_unit_change_report",
            "materiality_self_report",
            "semantic_self_report",
            "non_imitation_acknowledgement",
            "protected_strengths_preservation_acknowledgement",
            "forbidden_regression_acknowledgement",
            "safety_claims",
            "finality_claimed",
            "phase_shift_claimed",
            "strongest_rival_defeated_claimed",
            "current_best_supersession_claimed",
            "generation_allowed",
        ],
    )


def selected_target_cycle_mechanism_visibility_generation_json_schema() -> dict[str, Any]:
    safety_false = {
        "type": "boolean",
        "enum": [False],
        "description": "Must be false for this bounded generation worker.",
    }
    phrase_item = _object_schema(
        {
            "phrase": {"type": "string"},
            "phrase_found_in_source": {"type": "boolean"},
            "handling_action": {
                "type": "string",
                "enum": [
                    "transformed",
                    "retained_as_earned",
                    "removed_because_unneeded",
                ],
            },
            "deletion_required": safety_false,
            "automatic_deletion_forbidden": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "pressure_point_not_deletion_target": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "transformation_or_earned_retention_required": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "earned_retention_allowed": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "context_sensitive_decision_required": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "preserve_if_still_earned_after_object_pressure": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "handling_rationale": {"type": "string"},
            "causal_force_preserved": {
                "type": "boolean",
                "enum": [True],
                "description": "Must be true.",
            },
            "living_event_sequence_weakened": safety_false,
        },
        [
            "phrase",
            "phrase_found_in_source",
            "handling_action",
            "deletion_required",
            "automatic_deletion_forbidden",
            "pressure_point_not_deletion_target",
            "transformation_or_earned_retention_required",
            "earned_retention_allowed",
            "context_sensitive_decision_required",
            "preserve_if_still_earned_after_object_pressure",
            "handling_rationale",
            "causal_force_preserved",
            "living_event_sequence_weakened",
        ],
    )
    target_unit_item = _object_schema(
        {
            "unit_id": {"type": "string"},
            "change_summary": {"type": "string"},
            "material_change_present": {"type": "boolean"},
            "preservation_passed": {"type": "boolean"},
            "validation_required": {"type": "boolean"},
        },
        [
            "unit_id",
            "change_summary",
            "material_change_present",
            "preservation_passed",
            "validation_required",
        ],
    )
    simple_report = _object_schema(
        {
            "passed": {"type": "boolean"},
            "summary": {"type": "string"},
            "evidence": _string_array_schema(),
        },
        ["passed", "summary", "evidence"],
    )
    return _schema_with_properties(
        {
            "text": {"type": "string"},
            "revision_summary": {"type": "string"},
            "mechanism_visibility_repair_summary": {"type": "string"},
            "phrase_handling_report": {
                "type": "array",
                "items": phrase_item,
            },
            "target_unit_change_report": {
                "type": "array",
                "items": target_unit_item,
            },
            "materiality_report": simple_report,
            "semantic_report": simple_report,
            "preservation_report": simple_report,
            "forbidden_overcorrection_report": simple_report,
            "post_generation_evidence_note": simple_report,
            "generation_allowed": safety_false,
            "finality_claimed": safety_false,
            "phase_shift_claimed": safety_false,
            "strongest_rival_defeated_claimed": safety_false,
        },
        [
            "text",
            "revision_summary",
            "mechanism_visibility_repair_summary",
            "phrase_handling_report",
            "target_unit_change_report",
            "materiality_report",
            "semantic_report",
            "preservation_report",
            "forbidden_overcorrection_report",
            "post_generation_evidence_note",
            "generation_allowed",
            "finality_claimed",
            "phase_shift_claimed",
            "strongest_rival_defeated_claimed",
        ],
    )


def nonlocal_law_candidate_reader_state_evaluation_json_schema() -> dict[str, Any]:
    safety_false = {
        "type": "boolean",
        "enum": [False],
        "description": "Must be false; this worker evaluates only.",
    }
    dimension_result = {
        "type": "string",
        "enum": ["improved", "unchanged", "worsened", "inconclusive"],
    }
    strongest_rival_result = {
        "type": "string",
        "enum": [
            "still_blocking",
            "narrowed_but_blocking",
            "worsened",
            "inconclusive",
        ],
    }
    overall_result = {
        "type": "string",
        "enum": [
            "supports_candidate_for_synthesis",
            "does_not_support_candidate",
            "mixed_requires_synthesis",
            "inconclusive",
        ],
    }
    risk_result = {
        "type": "string",
        "enum": ["passed", "at_risk", "failed", "inconclusive"],
    }
    control_result = {
        "type": "string",
        "enum": [
            "supports_candidate",
            "weakens_candidate",
            "mixed",
            "inconclusive",
        ],
    }
    reader_state_observation = _object_schema(
        {
            "result": dimension_result,
            "evidence": {"type": "string"},
            "reader_state_effect": {"type": "string"},
            "packet_0063_contrast": {"type": "string"},
        },
        ["result", "evidence", "reader_state_effect", "packet_0063_contrast"],
    )
    comparison = _object_schema(
        {
            "first_read_pressure_result": dimension_result,
            "object_event_consequence_result": dimension_result,
            "explanation_timing_result": dimension_result,
            "reread_return_result": dimension_result,
            "comparison_summary": {"type": "string"},
        },
        [
            "first_read_pressure_result",
            "object_event_consequence_result",
            "explanation_timing_result",
            "reread_return_result",
            "comparison_summary",
        ],
    )
    control_item = _object_schema(
        {
            "control_id": {"type": "string"},
            "expected_reader_state_contrast": {"type": "string"},
            "predicted_result": control_result,
            "evidence": {"type": "string"},
        },
        [
            "control_id",
            "expected_reader_state_contrast",
            "predicted_result",
            "evidence",
        ],
    )
    law_assessment = _object_schema(
        {
            "object_event_consequence_result": dimension_result,
            "explanation_timing_result": dimension_result,
            "explanation_earned_not_abolished": {"type": "boolean"},
            "law_effect_summary": {"type": "string"},
        },
        [
            "object_event_consequence_result",
            "explanation_timing_result",
            "explanation_earned_not_abolished",
            "law_effect_summary",
        ],
    )
    risk_item = _object_schema(
        {
            "risk_id": {"type": "string"},
            "result": risk_result,
            "evidence": {"type": "string"},
        },
        ["risk_id", "result", "evidence"],
    )
    rival_assessment = _object_schema(
        {
            "strongest_rival_pressure_result": strongest_rival_result,
            "pressure_summary": {"type": "string"},
            "strongest_rival_remains_blocking": {"type": "boolean"},
        },
        [
            "strongest_rival_pressure_result",
            "pressure_summary",
            "strongest_rival_remains_blocking",
        ],
    )
    summary = _object_schema(
        {
            "overall_reader_state_result": overall_result,
            "summary": {"type": "string"},
            "candidate_superiority_claimed": safety_false,
            "current_best_supersession_claimed": safety_false,
        },
        [
            "overall_reader_state_result",
            "summary",
            "candidate_superiority_claimed",
            "current_best_supersession_claimed",
        ],
    )
    return _schema_with_properties(
        {
            "first_pass_reader_state": reader_state_observation,
            "second_pass_reader_state": reader_state_observation,
            "candidate_vs_packet_0063_comparison": comparison,
            "ablation_control_reader_state_matrix": {
                "type": "array",
                "items": control_item,
            },
            "law_effect_assessment": law_assessment,
            "risk_probe_results": {
                "type": "array",
                "items": risk_item,
            },
            "strongest_rival_pressure_assessment": rival_assessment,
            "reader_state_summary": summary,
            "recommended_next_evidence_step": {"type": "string"},
            "generation_allowed": safety_false,
            "synthesis_authorized": safety_false,
            "finality_claimed": safety_false,
            "phase_shift_claimed": safety_false,
            "strongest_rival_defeated_claimed": safety_false,
        },
        [
            "first_pass_reader_state",
            "second_pass_reader_state",
            "candidate_vs_packet_0063_comparison",
            "ablation_control_reader_state_matrix",
            "law_effect_assessment",
            "risk_probe_results",
            "strongest_rival_pressure_assessment",
            "reader_state_summary",
            "recommended_next_evidence_step",
            "generation_allowed",
            "synthesis_authorized",
            "finality_claimed",
            "phase_shift_claimed",
            "strongest_rival_defeated_claimed",
        ],
    )


SELECTED_READER_STATE_REQUIRED_RISK_PROBES = {
    "causal_mechanism_overexplained": "causal mechanism may be overexplained",
    "room_begins_to_instruct_too_declarative": (
        '"room begins to instruct" may be too declarative'
    ),
    "later_seeing_must_be_changed_names_law_too_directly": (
        '"later seeing must be changed" may name the law too directly'
    ),
    "chemistry_register_unresolved": "chemistry register remains unresolved",
    "conclusion_summarizes_instead_of_enacts_return": (
        "conclusion may still summarize law instead of enacting return"
    ),
    "object_field_delicacy_overloaded_by_causal_explanation": (
        "object-field delicacy may be overloaded by causal explanation"
    ),
}


def selected_nonlocal_law_candidate_reader_state_evaluation_json_schema() -> dict[str, Any]:
    safety_false = {
        "type": "boolean",
        "enum": [False],
        "description": "Must be false; this worker evaluates only.",
    }
    result = {
        "type": "string",
        "enum": [
            "improved",
            "preserved",
            "worsened",
            "mixed",
            "active_risk",
            "narrowed_but_blocking",
            "unsupported",
            "requires_synthesis",
        ],
    }
    rival_result = {
        "type": "string",
        "enum": [
            "narrowed_but_blocking",
            "unchanged_blocking",
            "worsened",
            "requires_synthesis",
        ],
    }
    explanation_result = {
        "type": "string",
        "enum": ["true", "false", "mixed"],
    }
    bridge_examples = _object_schema(
        {
            "ring_grain": {"type": "string"},
            "dust_bare_strip": {"type": "string"},
            "spoon_saucer_crack": {"type": "string"},
            "hum_order_of_seeing": {"type": "string"},
        },
        [
            "ring_grain",
            "dust_bare_strip",
            "spoon_saucer_crack",
            "hum_order_of_seeing",
        ],
    )
    risk_probe_item = _object_schema(
        {
            "result": result,
            "summary": {"type": "string"},
            "evidence": {"type": "string"},
            "risk_status": result,
            "next_target_implication": {"type": "string"},
        },
        ["result", "summary", "evidence", "risk_status", "next_target_implication"],
    )
    risk_probe_results_by_id = _object_schema(
        {risk_id: risk_probe_item for risk_id in SELECTED_READER_STATE_REQUIRED_RISK_PROBES},
        list(SELECTED_READER_STATE_REQUIRED_RISK_PROBES),
    )
    return _schema_with_properties(
        {
            "living_event_sequence_result": result,
            "living_event_sequence_summary": {"type": "string"},
            "living_event_sequence_evidence": {"type": "string"},
            "static_trace_reduction_result": result,
            "static_trace_reduction_summary": {"type": "string"},
            "static_trace_reduction_evidence": {"type": "string"},
            "static_trace_comparison_to_packet_0002": {"type": "string"},
            "remaining_static_trace_risk": {"type": "string"},
            "causal_bridge_result": result,
            "causal_bridge_summary": {"type": "string"},
            "bridge_examples": bridge_examples,
            "consequence_before_naming_result": result,
            "consequence_before_naming_summary": {"type": "string"},
            "before_naming_evidence": {"type": "string"},
            "explanation_entry_point": {"type": "string"},
            "risk_if_overstated": {"type": "string"},
            "causal_mechanism_overexplained_result": result,
            "causal_mechanism_overexplained_summary": {"type": "string"},
            "overexplained_phrases": _string_array_schema(),
            "risk_status": {"type": "string"},
            "next_target_implication": {"type": "string"},
            "explanation_earned_result": result,
            "explanation_earned": explanation_result,
            "explanation_earned_summary": {"type": "string"},
            "explanation_abolished": safety_false,
            "remaining_explicitness_risk": {"type": "string"},
            "packet_0002_gains_preserved_result": result,
            "preserved_strengths": _string_array_schema(),
            "weakened_strengths": _string_array_schema(),
            "object_field_preserved": {"type": "boolean"},
            "proof_no_answer_pressure_preserved": {"type": "boolean"},
            "return_structure_preserved": {"type": "boolean"},
            "non_imitation_result": result,
            "rival_imitation_detected": safety_false,
            "forbidden_rival_hits": _string_array_schema(),
            "forbidden_rival_mode_hits": _string_array_schema(),
            "non_imitation_evidence": {"type": "string"},
            "strongest_rival_pressure_result": rival_result,
            "strongest_rival_remains_blocking": {"type": "boolean"},
            "strongest_rival_defeated_claimed": safety_false,
            "pressure_summary": {"type": "string"},
            "overall_selected_target_reader_state_result": result,
            "reader_state_summary": {"type": "string"},
            "risk_probe_results_by_id": risk_probe_results_by_id,
            "synthesis_recommendation": {"type": "string"},
            "finality_claimed": safety_false,
            "phase_shift_claimed": safety_false,
            "current_best_supersession_claimed": safety_false,
            "generation_recommended": safety_false,
            "immediate_finalization_recommended": safety_false,
            "synthesis_authorized": safety_false,
            "current_best_updated": safety_false,
        },
        [
            "living_event_sequence_result",
            "living_event_sequence_summary",
            "living_event_sequence_evidence",
            "static_trace_reduction_result",
            "static_trace_reduction_summary",
            "static_trace_reduction_evidence",
            "static_trace_comparison_to_packet_0002",
            "remaining_static_trace_risk",
            "causal_bridge_result",
            "causal_bridge_summary",
            "bridge_examples",
            "consequence_before_naming_result",
            "consequence_before_naming_summary",
            "before_naming_evidence",
            "explanation_entry_point",
            "risk_if_overstated",
            "causal_mechanism_overexplained_result",
            "causal_mechanism_overexplained_summary",
            "overexplained_phrases",
            "risk_status",
            "next_target_implication",
            "explanation_earned_result",
            "explanation_earned",
            "explanation_earned_summary",
            "explanation_abolished",
            "remaining_explicitness_risk",
            "packet_0002_gains_preserved_result",
            "preserved_strengths",
            "weakened_strengths",
            "object_field_preserved",
            "proof_no_answer_pressure_preserved",
            "return_structure_preserved",
            "non_imitation_result",
            "rival_imitation_detected",
            "forbidden_rival_hits",
            "forbidden_rival_mode_hits",
            "non_imitation_evidence",
            "strongest_rival_pressure_result",
            "strongest_rival_remains_blocking",
            "strongest_rival_defeated_claimed",
            "pressure_summary",
            "overall_selected_target_reader_state_result",
            "reader_state_summary",
            "risk_probe_results_by_id",
            "synthesis_recommendation",
            "finality_claimed",
            "phase_shift_claimed",
            "current_best_supersession_claimed",
            "generation_recommended",
            "immediate_finalization_recommended",
            "synthesis_authorized",
            "current_best_updated",
        ],
    )


def model_backed_local_law_rival_diagnostic_json_schema() -> dict[str, Any]:
    finding_schema = _local_law_diagnostic_finding_schema()
    return _schema_with_properties(
        {
            "law_id": {"type": "string"},
            "comparison_summary": {"type": "string"},
            "packet_0063_law_application": finding_schema,
            "rival_law_application": finding_schema,
            "first_read_pressure_findings": finding_schema,
            "explanation_timing_findings": finding_schema,
            "object_event_sequence_findings": finding_schema,
            "proof_no_answer_findings": finding_schema,
            "reread_transformation_findings": finding_schema,
            "strongest_rival_advantage_assessment": finding_schema,
            "non_imitation_constraints_acknowledged": {"type": "boolean"},
            "future_strategy_implications": finding_schema,
            "generation_allowed": {"type": "boolean"},
            "finality_claimed": {"type": "boolean"},
            "phase_shift_claimed": {"type": "boolean"},
        },
        [
            "law_id",
            "comparison_summary",
            "packet_0063_law_application",
            "rival_law_application",
            "first_read_pressure_findings",
            "explanation_timing_findings",
            "object_event_sequence_findings",
            "proof_no_answer_findings",
            "reread_transformation_findings",
            "strongest_rival_advantage_assessment",
            "non_imitation_constraints_acknowledged",
            "future_strategy_implications",
            "generation_allowed",
            "finality_claimed",
            "phase_shift_claimed",
        ],
    )


def _local_law_diagnostic_finding_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "claim": {"type": "string"},
            "evidence_basis": {"type": "string"},
            "support_spans_or_passages": _string_array_schema(),
            "uncertainty": {"type": "string"},
            "risk_if_misused": {"type": "string"},
        },
        [
            "claim",
            "evidence_basis",
            "support_spans_or_passages",
            "uncertainty",
            "risk_if_misused",
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
    if schema == INTERNAL_STREAM_READER_SCHEMA:
        return internal_stream_reader_json_schema()
    if schema == INTERNAL_REREAD_READER_SCHEMA:
        return internal_reread_reader_json_schema()
    if schema == FORENSIC_GROUNDING_READER_SCHEMA:
        return forensic_grounding_reader_json_schema()
    if schema == HOSTILE_INTERNAL_READER_SCHEMA:
        return hostile_internal_reader_json_schema()
    if schema == INTERNAL_RIVAL_COMPARISON_SCHEMA:
        return internal_rival_comparison_json_schema()
    if schema == INTERNAL_FAILURE_DIAGNOSIS_SCHEMA:
        return internal_failure_diagnosis_json_schema()
    if schema == TARGETED_RECOMPOSITION_PLAN_SCHEMA:
        return targeted_recomposition_plan_json_schema()
    if schema == COUNTERFACTUAL_ABLATION_PLAN_SCHEMA:
        return counterfactual_ablation_plan_json_schema()
    if schema == AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA:
        return autonomous_candidate_gate_report_json_schema()
    if schema == AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA:
        return autonomous_revision_selected_failure_json_schema()
    if schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
        return autonomous_revision_causal_handle_json_schema()
    if schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
        return autonomous_revision_revised_candidate_json_schema()
    if schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA:
        return autonomous_revision_diff_report_json_schema()
    if schema == AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA:
        return autonomous_revision_ablation_variant_set_json_schema()
    if schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
        return autonomous_revision_ablation_reread_comparison_json_schema()
    if schema == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA:
        return autonomous_revision_old_new_rival_comparison_json_schema()
    if schema == AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA:
        return autonomous_revision_local_law_case_note_json_schema()
    if schema == EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA:
        return executed_ablation_internal_comparison_json_schema()
    if schema == ABLATION_INFORMED_BASE_SELECTION_SCHEMA:
        return ablation_informed_base_selection_json_schema()
    if schema == ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA:
        return ablation_informed_handle_selection_json_schema()
    if schema == ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA:
        return ablation_informed_patch_proposal_json_schema()
    if schema == BOUNDED_MACRO_RECOMPOSITION_SCHEMA:
        return bounded_macro_recomposition_json_schema()
    if schema == OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA:
        return object_motion_causality_generation_json_schema()
    if schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA:
        return residual_intervention_generation_json_schema()
    if schema == NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA:
        return nonlocal_law_guided_generation_json_schema()
    if schema == SELECTED_NONLOCAL_LAW_TARGET_GENERATION_SCHEMA:
        return selected_nonlocal_law_target_generation_json_schema()
    if schema == SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATION_SCHEMA:
        return selected_target_cycle_mechanism_visibility_generation_json_schema()
    if schema == NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA:
        return nonlocal_law_candidate_reader_state_evaluation_json_schema()
    if schema == SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA:
        return selected_nonlocal_law_candidate_reader_state_evaluation_json_schema()
    if schema == MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC_SCHEMA:
        return model_backed_local_law_rival_diagnostic_json_schema()
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
    if schema == INTERNAL_STREAM_READER_SCHEMA:
        return _validate_internal_stream_reader(payload)
    if schema == INTERNAL_REREAD_READER_SCHEMA:
        return _validate_internal_reread_reader(payload)
    if schema == FORENSIC_GROUNDING_READER_SCHEMA:
        return _validate_forensic_grounding_reader(payload)
    if schema == HOSTILE_INTERNAL_READER_SCHEMA:
        return _validate_hostile_internal_reader(payload)
    if schema == INTERNAL_RIVAL_COMPARISON_SCHEMA:
        return _validate_internal_rival_comparison(payload)
    if schema == INTERNAL_FAILURE_DIAGNOSIS_SCHEMA:
        return _validate_internal_failure_diagnosis(payload)
    if schema == TARGETED_RECOMPOSITION_PLAN_SCHEMA:
        return _validate_targeted_recomposition_plan(payload)
    if schema == COUNTERFACTUAL_ABLATION_PLAN_SCHEMA:
        return _validate_counterfactual_ablation_plan(payload)
    if schema == AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA:
        return _validate_autonomous_candidate_gate_report(payload)
    if schema == AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA:
        return _validate_autonomous_revision_selected_failure(payload)
    if schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
        return _validate_autonomous_revision_causal_handle(payload)
    if schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
        return _validate_autonomous_revision_revised_candidate(payload)
    if schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA:
        return _validate_autonomous_revision_diff_report(payload)
    if schema == AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA:
        return _validate_autonomous_revision_ablation_variant_set(payload)
    if schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
        return _validate_autonomous_revision_ablation_reread_comparison(payload)
    if schema == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA:
        return _validate_autonomous_revision_old_new_rival_comparison(payload)
    if schema == AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA:
        return _validate_autonomous_revision_local_law_case_note(payload)
    if schema == EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA:
        return _validate_executed_ablation_internal_comparison(payload)
    if schema == ABLATION_INFORMED_BASE_SELECTION_SCHEMA:
        return _validate_ablation_informed_base_selection(payload)
    if schema == ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA:
        return _validate_ablation_informed_handle_selection(payload)
    if schema == ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA:
        return _validate_ablation_informed_patch_proposal(payload)
    if schema == BOUNDED_MACRO_RECOMPOSITION_SCHEMA:
        return _validate_bounded_macro_recomposition(payload)
    if schema == OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA:
        return _validate_object_motion_causality_generation(payload)
    if schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA:
        return _validate_residual_intervention_generation(payload)
    if schema == NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA:
        return _validate_nonlocal_law_guided_generation(payload)
    if schema == SELECTED_NONLOCAL_LAW_TARGET_GENERATION_SCHEMA:
        return _validate_selected_nonlocal_law_target_generation(payload)
    if schema == SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATION_SCHEMA:
        return _validate_selected_target_cycle_mechanism_visibility_generation(payload)
    if schema == NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA:
        return _validate_nonlocal_law_candidate_reader_state_evaluation(payload)
    if schema == SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA:
        return _validate_selected_nonlocal_law_candidate_reader_state_evaluation(
            payload
        )
    if schema == MODEL_BACKED_LOCAL_LAW_RIVAL_DIAGNOSTIC_SCHEMA:
        return _validate_model_backed_local_law_rival_diagnostic(payload)
    raise ModelValidationError(f"unknown worker schema: {schema.name} v{schema.version}")


def normalize_internal_failure_type(failure_type: str) -> str:
    if failure_type in INTERNAL_FAILURE_TYPES:
        return failure_type
    if failure_type in INTERNAL_FAILURE_TYPE_ALIASES:
        return INTERNAL_FAILURE_TYPE_ALIASES[failure_type]
    raise ModelValidationError(f"unsupported internal failure type: {failure_type}")


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
    for key in ("baseline_id", "text", "generation_rule"):
        _require_type(payload, key, str)
    _require_string_list(payload, "risks")
    return {
        "baseline_id": payload["baseline_id"],
        "baseline_type": "direct_prompt",
        "text": payload["text"],
        "fixture_or_fake": False,
        "not_real_validation": True,
        "generation_rule": payload["generation_rule"],
        "final_gate_satisfied": False,
        "risks": payload["risks"],
    }


def _validate_pilot_raw_model_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("baseline_id", "text"):
        _require_type(payload, key, str)
    _require_string_list(payload, "risks")
    return {
        "baseline_id": payload["baseline_id"],
        "baseline_type": "raw_model",
        "text": payload["text"],
        "fixture_or_fake": False,
        "not_real_validation": True,
        "raw_model_baseline_gate_satisfied": False,
        "model_calls_used": 1,
        "risks": payload["risks"],
    }


def _validate_internal_stream_reader(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "candidate_label", str)
    for key in ("retained_images", "dropped_details", "live_motifs"):
        _require_string_list(payload, key)
    for key in ("attention_points", "confusion_points", "overexplicitness_points"):
        _require_object_list(payload, key)
    _require_type(payload, "first_read_opening_interpretation", str)
    _require_type(payload, "first_read_summary", str)
    _require_type(payload, "bounded_mode", bool)
    _require_true(payload, "not_human_data")
    return {
        "candidate_label": payload["candidate_label"],
        "retained_images": payload["retained_images"],
        "dropped_details": payload["dropped_details"],
        "live_motifs": payload["live_motifs"],
        "attention_points": payload["attention_points"],
        "confusion_points": payload["confusion_points"],
        "overexplicitness_points": payload["overexplicitness_points"],
        "first_read_opening_interpretation": payload["first_read_opening_interpretation"],
        "first_read_summary": payload["first_read_summary"],
        "bounded_mode": payload["bounded_mode"],
        "not_human_data": True,
    }


def _validate_internal_reread_reader(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "candidate_label", str)
    _require_type(payload, "opening_changed", bool)
    _require_string_list(payload, "opening_words_images_changed")
    _require_type(payload, "hidden_consequence_clearer", str)
    _require_object_list(payload, "motif_returned_changed")
    _require_type(payload, "reread_summary", str)
    _require_type(payload, "reread_gain_estimate", dict)
    _require_true(payload, "not_human_data")
    return {
        "candidate_label": payload["candidate_label"],
        "opening_changed": payload["opening_changed"],
        "opening_words_images_changed": payload["opening_words_images_changed"],
        "hidden_consequence_clearer": payload["hidden_consequence_clearer"],
        "motif_returned_changed": payload["motif_returned_changed"],
        "reread_summary": payload["reread_summary"],
        "reread_gain_estimate": payload["reread_gain_estimate"],
        "not_human_data": True,
    }


def _validate_forensic_grounding_reader(payload: dict[str, Any]) -> dict[str, Any]:
    _require_string_list(payload, "claimed_effects")
    _require_object_list(payload, "exact_textual_support")
    support_items = []
    for index, support in enumerate(payload["exact_textual_support"]):
        for key in ("claim", "source_label", "quoted_span", "support_reason"):
            _require_type(support, key, str, field_prefix=f"exact_textual_support[{index}].")
        support_items.append(
            {
                "claim": support["claim"],
                "source_label": support["source_label"],
                "quoted_span": support["quoted_span"],
                "support_reason": support["support_reason"],
            }
        )
    _require_string_list(payload, "unsupported_claims")
    _require_type(payload, "fake_depth_risk", str)
    _require_type(payload, "reread_claims_grounded", bool)
    _require_type(payload, "grounding_verdict", str)
    _require_true(payload, "not_human_data")
    return {
        "claimed_effects": payload["claimed_effects"],
        "exact_textual_support": support_items,
        "unsupported_claims": payload["unsupported_claims"],
        "fake_depth_risk": payload["fake_depth_risk"],
        "reread_claims_grounded": payload["reread_claims_grounded"],
        "grounding_verdict": payload["grounding_verdict"],
        "not_human_data": True,
    }


def _validate_hostile_internal_reader(payload: dict[str, Any]) -> dict[str, Any]:
    _require_object_list(payload, "attacks")
    attacks = []
    for index, attack in enumerate(payload["attacks"]):
        _require_type(attack, "risk_type", str, field_prefix=f"attacks[{index}].")
        _require_type(attack, "finding", str, field_prefix=f"attacks[{index}].")
        attacks.append(
            {
                "risk_type": attack["risk_type"],
                "finding": attack["finding"],
            }
        )
    _require_string_list(payload, "blocking_risks")
    for key in (
        "fake_depth",
        "overexplanation",
        "scaffold_leakage",
        "wrong_register",
        "accidental_comedy",
        "cliche_contamination",
        "thesis_replacing_artifact",
        "pasted_ending",
        "unearned_cosmic_scale",
    ):
        _require_type(payload, key, str)
    _require_true(payload, "not_human_data")
    return {
        "attacks": attacks,
        "blocking_risks": payload["blocking_risks"],
        "fake_depth": payload["fake_depth"],
        "overexplanation": payload["overexplanation"],
        "scaffold_leakage": payload["scaffold_leakage"],
        "wrong_register": payload["wrong_register"],
        "accidental_comedy": payload["accidental_comedy"],
        "cliche_contamination": payload["cliche_contamination"],
        "thesis_replacing_artifact": payload["thesis_replacing_artifact"],
        "pasted_ending": payload["pasted_ending"],
        "unearned_cosmic_scale": payload["unearned_cosmic_scale"],
        "not_human_data": True,
    }


def _validate_internal_rival_comparison(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "source_classes_by_label", dict)
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload["source_classes_by_label"].items()
    ):
        raise ModelValidationError("source_classes_by_label must map strings to strings")
    for key in (
        "strongest_by_first_read_clarity",
        "strongest_by_reread_transformation",
        "strongest_by_local_embodiment",
        "strongest_by_compression_necessity",
    ):
        _require_type(payload, key, str)
    _require_string_list(payload, "abi_candidate_wins_where")
    _require_string_list(payload, "abi_candidate_loses_where")
    _require_type(payload, "rival_preservation_remains_required", bool)
    _require_type(payload, "strongest_rival_present", bool)
    _require_object_list(payload, "scores")
    _require_true(payload, "not_human_data")
    return {
        "source_classes_by_label": dict(payload["source_classes_by_label"]),
        "strongest_by_first_read_clarity": payload["strongest_by_first_read_clarity"],
        "strongest_by_reread_transformation": payload["strongest_by_reread_transformation"],
        "strongest_by_local_embodiment": payload["strongest_by_local_embodiment"],
        "strongest_by_compression_necessity": payload["strongest_by_compression_necessity"],
        "abi_candidate_wins_where": payload["abi_candidate_wins_where"],
        "abi_candidate_loses_where": payload["abi_candidate_loses_where"],
        "rival_preservation_remains_required": payload["rival_preservation_remains_required"],
        "strongest_rival_present": payload["strongest_rival_present"],
        "scores": payload["scores"],
        "not_human_data": True,
    }


def _validate_internal_failure_diagnosis(payload: dict[str, Any]) -> dict[str, Any]:
    _require_string_list(payload, "failure_types_present")
    normalized_types = []
    for failure_type in payload["failure_types_present"]:
        normalized_types.append(normalize_internal_failure_type(failure_type))
    _require_object_list(payload, "failures")
    normalized_failures = []
    for index, failure in enumerate(payload["failures"]):
        failure_type = failure.get("failure_type")
        if not isinstance(failure_type, str):
            raise ModelValidationError(f"failures[{index}].failure_type must be a string")
        try:
            normalized_type = normalize_internal_failure_type(failure_type)
        except ModelValidationError as error:
            raise ModelValidationError(f"failures[{index}].failure_type is unsupported") from error
        normalized_failure = dict(failure)
        normalized_failure["failure_type"] = normalized_type
        normalized_failures.append(normalized_failure)
    _require_type(payload, "requires_recomposition", bool)
    _require_type(payload, "reread_gain_estimate", dict)
    _require_true(payload, "not_human_data")
    return {
        "failure_types_present": normalized_types,
        "failures": normalized_failures,
        "requires_recomposition": payload["requires_recomposition"],
        "reread_gain_estimate": payload["reread_gain_estimate"],
        "not_human_data": True,
    }


def _validate_targeted_recomposition_plan(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "bounded", bool)
    _require_type(payload, "does_not_rewrite_artifact", bool)
    _require_object_list(payload, "plan_items")
    _require_string_list(payload, "protected_effects")
    _require_string_list(payload, "forbidden_changes")
    _require_type(payload, "verification_plan", str)
    _require_true(payload, "not_human_data")
    return {
        "bounded": payload["bounded"],
        "does_not_rewrite_artifact": payload["does_not_rewrite_artifact"],
        "plan_items": payload["plan_items"],
        "protected_effects": payload["protected_effects"],
        "forbidden_changes": payload["forbidden_changes"],
        "verification_plan": payload["verification_plan"],
        "not_human_data": True,
    }


def _validate_counterfactual_ablation_plan(payload: dict[str, Any]) -> dict[str, Any]:
    _require_object_list(payload, "ablation_tests")
    _require_string_list(payload, "suspected_causal_handles")
    _require_string_list(payload, "operations")
    _require_type(payload, "predicted_reader_state_effect", str)
    _require_string_list(payload, "pass_fail_criteria")
    _require_true(payload, "not_human_data")
    return {
        "ablation_tests": payload["ablation_tests"],
        "suspected_causal_handles": payload["suspected_causal_handles"],
        "operations": payload["operations"],
        "predicted_reader_state_effect": payload["predicted_reader_state_effect"],
        "pass_fail_criteria": payload["pass_fail_criteria"],
        "not_human_data": True,
    }


def _validate_autonomous_candidate_gate_report(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "profile", str)
    _require_type(payload, "passed", bool)
    _require_type(payload, "eligible", bool)
    _require_string_list(payload, "required_gates")
    _require_object_list(payload, "gate_results")
    _require_string_list(payload, "failed_gates")
    _require_string_list(payload, "missing_gates")
    _require_type(payload, "human_validation_required", bool)
    _require_type(payload, "paper_validation_required", bool)
    _require_type(payload, "phase_shift_claim", bool)
    _require_string_list(payload, "final_gates_marked_passed")
    _require_type(payload, "summary_verdict", str)
    return {
        "profile": "autonomous_creative_candidate",
        "passed": False,
        "eligible": False,
        "required_gates": payload["required_gates"],
        "gate_results": payload["gate_results"],
        "failed_gates": payload["failed_gates"],
        "missing_gates": payload["missing_gates"],
        "human_validation_required": False,
        "paper_validation_required": False,
        "phase_shift_claim": False,
        "final_gates_marked_passed": [],
        "summary_verdict": payload["summary_verdict"],
    }


def _validate_autonomous_revision_selected_failure(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("selection_rule", "selected_failure_type", "selected_diagnosis", "severity"):
        _require_type(payload, key, str)
    _require_string_list(payload, "reader_lab_evidence_artifacts")
    _require_integer(payload, "source_failure_index")
    _require_true(payload, "references_live_reader_lab_evidence")
    _require_true(payload, "not_human_data")
    selected_failure_type = normalize_internal_failure_type(payload["selected_failure_type"])
    if not payload["reader_lab_evidence_artifacts"]:
        raise ModelValidationError("reader_lab_evidence_artifacts must not be empty")
    return {
        "selection_rule": payload["selection_rule"],
        "selected_failure_type": selected_failure_type,
        "selected_diagnosis": payload["selected_diagnosis"],
        "severity": payload["severity"],
        "reader_lab_evidence_artifacts": payload["reader_lab_evidence_artifacts"],
        "source_failure_index": int(payload["source_failure_index"]),
        "references_live_reader_lab_evidence": True,
        "not_human_data": True,
    }


def _validate_autonomous_revision_causal_handle(payload: dict[str, Any]) -> dict[str, Any]:
    _require_true(payload, "bounded_target")
    _require_integer(payload, "target_count")
    if int(payload["target_count"]) != 1:
        raise ModelValidationError("target_count must be 1")
    _require_true(payload, "does_not_rebuild_artifact")
    _validate_patch_target_id(
        payload.get("selected_patch_target_id"),
        "selected_patch_target_id",
    )
    _require_type(payload, "span_ref", dict)
    span_ref = _validate_revision_span_ref(payload["span_ref"], "span_ref")
    for key in ("target_region_label", "target_region_description"):
        _require_type(payload, key, str)
    _require_string_list(payload, "allowed_span_refs")
    _require_string_list(payload, "protected_outside_spans")
    if not payload["allowed_span_refs"]:
        raise ModelValidationError("allowed_span_refs must not be empty")
    for key in (
        "quoted_text",
        "causal_handle",
        "local_law_hypothesis",
        "suspected_failure",
        "why_it_might_be_junk",
        "why_it_might_be_treasure",
        "connotation_or_register_risk",
        "variant_probe",
        "ablation_probe",
        "expected_reader_state_change",
        "uncertainty",
    ):
        _require_type(payload, key, str)
    _require_string_list(payload, "protected_effects")
    _require_string_list(payload, "forbidden_changes")
    _require_true(payload, "not_human_data")
    return {
        "bounded_target": True,
        "target_count": 1,
        "does_not_rebuild_artifact": True,
        "selected_patch_target_id": payload["selected_patch_target_id"],
        "span_ref": span_ref,
        "target_region_label": payload["target_region_label"],
        "target_region_description": payload["target_region_description"],
        "allowed_span_refs": payload["allowed_span_refs"],
        "protected_outside_spans": payload["protected_outside_spans"],
        "quoted_text": payload["quoted_text"],
        "causal_handle": payload["causal_handle"],
        "local_law_hypothesis": payload["local_law_hypothesis"],
        "suspected_failure": payload["suspected_failure"],
        "why_it_might_be_junk": payload["why_it_might_be_junk"],
        "why_it_might_be_treasure": payload["why_it_might_be_treasure"],
        "connotation_or_register_risk": payload["connotation_or_register_risk"],
        "variant_probe": payload["variant_probe"],
        "ablation_probe": payload["ablation_probe"],
        "expected_reader_state_change": payload["expected_reader_state_change"],
        "uncertainty": payload["uncertainty"],
        "protected_effects": payload["protected_effects"],
        "forbidden_changes": payload["forbidden_changes"],
        "not_human_data": True,
    }


def _validate_autonomous_revision_revised_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "proposal_id",
        "source_candidate_artifact_id",
        "targeted_causal_handle",
        "target_region_label",
        "expanded_target_region",
        "expansion_reason",
    ):
        _require_type(payload, key, str)
    _require_object_list(payload, "patches")
    patches = [
        _validate_revision_patch(patch, f"patches[{index}]")
        for index, patch in enumerate(payload["patches"])
    ]
    if not patches:
        raise ModelValidationError("patches must not be empty")
    for key in ("protected_effects", "forbidden_changes_respected"):
        _require_string_list(payload, key)
    _require_true(payload, "bounded_patch_set")
    _require_false(payload, "full_rewrite")
    _require_type(payload, "target_region_expanded", bool)
    if payload["target_region_expanded"]:
        for key in ("expanded_target_region", "expansion_reason"):
            if not payload[key].strip():
                raise ModelValidationError(
                    f"{key} is required when target_region_expanded is true"
                )
    _require_true(payload, "non_final")
    _require_true(payload, "candidate_only")
    _require_true(payload, "not_human_validated")
    _require_false(payload, "human_validated")
    _require_true(payload, "not_finalization_eligible")
    _require_false(payload, "finalization_eligible")
    _require_false(payload, "phase_shift_claim")
    _require_true(payload, "no_phase_shift_claim")
    _require_true(payload, "not_human_data")
    return {
        "proposal_id": payload["proposal_id"],
        "source_candidate_artifact_id": payload["source_candidate_artifact_id"],
        "targeted_causal_handle": payload["targeted_causal_handle"],
        "target_region_label": payload["target_region_label"],
        "patches": patches,
        "bounded_patch_set": True,
        "full_rewrite": False,
        "target_region_expanded": payload["target_region_expanded"],
        "expanded_target_region": payload["expanded_target_region"],
        "expansion_reason": payload["expansion_reason"],
        "protected_effects": payload["protected_effects"],
        "forbidden_changes_respected": payload["forbidden_changes_respected"],
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "human_validated": False,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "not_human_data": True,
    }


def _validate_autonomous_revision_diff_report(payload: dict[str, Any]) -> dict[str, Any]:
    _require_false(payload, "full_rewrite")
    _require_true(payload, "bounded_change")
    for key in (
        "operation_type",
        "target_region",
        "target_region_label",
        "target_region_description",
        "causal_handle",
        "original_excerpt",
        "revised_excerpt",
        "explanation",
    ):
        _require_type(payload, key, str)
    _require_string_list(payload, "allowed_span_refs")
    _require_object_list(payload, "allowed_patch_targets")
    allowed_patch_targets = [
        _validate_revision_patch_target(target, f"allowed_patch_targets[{index}]")
        for index, target in enumerate(payload["allowed_patch_targets"])
    ]
    _require_string_list(payload, "protected_outside_spans")
    if not payload["allowed_span_refs"]:
        raise ModelValidationError("allowed_span_refs must not be empty")
    if not allowed_patch_targets:
        raise ModelValidationError("allowed_patch_targets must not be empty")
    _require_object_list(payload, "changed_spans")
    changed_spans = [
        _validate_changed_span(span, f"changed_spans[{index}]")
        for index, span in enumerate(payload["changed_spans"])
    ]
    if not changed_spans:
        raise ModelValidationError("changed_spans must not be empty")
    _require_type(payload, "target_region_expanded", bool)
    _require_type(payload, "expanded_target_region", str)
    _require_type(payload, "expansion_reason", str)
    _require_type(payload, "target_expansion_justification", str)
    if payload["target_region_expanded"]:
        for key in (
            "expanded_target_region",
            "expansion_reason",
            "target_expansion_justification",
        ):
            if not payload[key].strip():
                raise ModelValidationError(
                    f"{key} is required when target_region_expanded is true"
                )
    _require_string_list(payload, "protected_effects_preserved")
    _require_string_list(payload, "forbidden_changes_honored")
    _require_true(payload, "not_human_data")
    return {
        "full_rewrite": False,
        "bounded_change": True,
        "operation_type": payload["operation_type"],
        "target_region": payload["target_region"],
        "target_region_label": payload["target_region_label"],
        "target_region_description": payload["target_region_description"],
        "allowed_span_refs": payload["allowed_span_refs"],
        "allowed_patch_targets": allowed_patch_targets,
        "protected_outside_spans": payload["protected_outside_spans"],
        "causal_handle": payload["causal_handle"],
        "original_excerpt": payload["original_excerpt"],
        "revised_excerpt": payload["revised_excerpt"],
        "changed_spans": changed_spans,
        "target_region_expanded": payload["target_region_expanded"],
        "expanded_target_region": payload["expanded_target_region"],
        "expansion_reason": payload["expansion_reason"],
        "target_expansion_justification": payload["target_expansion_justification"],
        "protected_effects_preserved": payload["protected_effects_preserved"],
        "forbidden_changes_honored": payload["forbidden_changes_honored"],
        "explanation": payload["explanation"],
        "not_human_data": True,
    }


def _validate_autonomous_revision_ablation_variant_set(
    payload: dict[str, Any],
) -> dict[str, Any]:
    _require_type(payload, "targeted_causal_handle", str)
    _require_object_list(payload, "variants")
    variants = [
        _validate_revision_variant(variant, f"variants[{index}]")
        for index, variant in enumerate(payload["variants"])
    ]
    if not variants:
        raise ModelValidationError("variants must not be empty")
    _require_true(payload, "does_not_select_winner")
    _require_true(payload, "not_human_data")
    return {
        "targeted_causal_handle": payload["targeted_causal_handle"],
        "variants": variants,
        "does_not_select_winner": True,
        "not_human_data": True,
    }


def _validate_autonomous_revision_ablation_reread_comparison(
    payload: dict[str, Any],
) -> dict[str, Any]:
    _require_type(payload, "candidate_label", str)
    _require_object_list(payload, "comparison_rows")
    rows = [
        _validate_ablation_row(row, f"comparison_rows[{index}]")
        for index, row in enumerate(payload["comparison_rows"])
    ]
    if not rows:
        raise ModelValidationError("comparison_rows must not be empty")
    _require_type(payload, "summary", str)
    _require_true(payload, "not_human_data")
    return {
        "candidate_label": payload["candidate_label"],
        "comparison_rows": rows,
        "summary": payload["summary"],
        "not_human_data": True,
    }


def _validate_autonomous_revision_old_new_rival_comparison(
    payload: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "reread_transformation_improved",
        "opening_transformation_improved",
        "local_embodiment_improved",
        "overexplanation_decreased",
        "fake_depth_risk_decreased",
        "revised_candidate_became_more_schematic",
        "strongest_rival_present",
        "rival_still_beats_candidate",
        "another_revision_cycle_needed",
        "rival_pressure_preserved",
    ):
        _require_type(payload, key, bool)
    for key in ("comparison_basis", "old_new_summary", "rival_pressure_summary"):
        _require_type(payload, key, str)
    _require_type(payload, "judgment_provenance", dict)
    judgment_provenance = _validate_revision_judgment_provenance(
        payload["judgment_provenance"]
    )
    _require_type(payload, "judgment_rationale", dict)
    judgment_rationale = _validate_revision_judgment_rationale(
        payload["judgment_rationale"]
    )
    _require_true(payload, "not_human_data")
    return {
        "reread_transformation_improved": payload["reread_transformation_improved"],
        "opening_transformation_improved": payload["opening_transformation_improved"],
        "local_embodiment_improved": payload["local_embodiment_improved"],
        "overexplanation_decreased": payload["overexplanation_decreased"],
        "fake_depth_risk_decreased": payload["fake_depth_risk_decreased"],
        "revised_candidate_became_more_schematic": payload[
            "revised_candidate_became_more_schematic"
        ],
        "strongest_rival_present": payload["strongest_rival_present"],
        "rival_still_beats_candidate": payload["rival_still_beats_candidate"],
        "another_revision_cycle_needed": payload["another_revision_cycle_needed"],
        "comparison_basis": payload["comparison_basis"],
        "rival_pressure_preserved": payload["rival_pressure_preserved"],
        "old_new_summary": payload["old_new_summary"],
        "rival_pressure_summary": payload["rival_pressure_summary"],
        "judgment_provenance": judgment_provenance,
        "judgment_rationale": judgment_rationale,
        "not_human_data": True,
    }


def _validate_autonomous_revision_local_law_case_note(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "principle",
        "quoted_text",
        "local_law_hypothesis",
        "suspected_failure",
        "why_it_might_be_junk",
        "why_it_might_be_treasure",
        "connotation_or_register_risk",
        "variant_probe",
        "ablation_probe",
        "expected_reader_state_change",
        "uncertainty",
        "preserve_irregularity_rule",
    ):
        _require_type(payload, key, str)
    _require_type(payload, "span_ref", dict)
    span_ref = _validate_revision_span_ref(payload["span_ref"], "span_ref")
    _require_type(payload, "comparison_result", dict)
    comparison_result = payload["comparison_result"]
    _require_type(
        comparison_result,
        "another_revision_cycle_needed",
        bool,
        field_prefix="comparison_result.",
    )
    _require_type(
        comparison_result,
        "rival_still_beats_candidate",
        bool,
        field_prefix="comparison_result.",
    )
    _require_true(payload, "not_human_data")
    return {
        "principle": payload["principle"],
        "span_ref": span_ref,
        "quoted_text": payload["quoted_text"],
        "local_law_hypothesis": payload["local_law_hypothesis"],
        "suspected_failure": payload["suspected_failure"],
        "why_it_might_be_junk": payload["why_it_might_be_junk"],
        "why_it_might_be_treasure": payload["why_it_might_be_treasure"],
        "connotation_or_register_risk": payload["connotation_or_register_risk"],
        "variant_probe": payload["variant_probe"],
        "ablation_probe": payload["ablation_probe"],
        "expected_reader_state_change": payload["expected_reader_state_change"],
        "uncertainty": payload["uncertainty"],
        "preserve_irregularity_rule": payload["preserve_irregularity_rule"],
        "comparison_result": {
            "another_revision_cycle_needed": comparison_result["another_revision_cycle_needed"],
            "rival_still_beats_candidate": comparison_result["rival_still_beats_candidate"],
        },
        "not_human_data": True,
    }


def _validate_executed_ablation_internal_comparison(
    payload: dict[str, Any],
) -> dict[str, Any]:
    _require_object_list(payload, "comparison_rows")
    rows = []
    for index, row in enumerate(payload["comparison_rows"]):
        validated = _validate_object(
            row,
            f"comparison_rows[{index}]",
            (
                "variant_id",
                "comparison_summary",
                "reader_state_effect_estimate",
                "rationale",
                "uncertainty",
                "risk_notes",
            ),
        )
        _require_true(row, "not_human_data", field_prefix=f"comparison_rows[{index}].")
        validated["not_human_data"] = True
        rows.append(validated)
    if not rows:
        raise ModelValidationError("comparison_rows must not be empty")
    _require_type(payload, "summary", str)
    _require_true(payload, "not_human_data")
    return {
        "comparison_rows": rows,
        "summary": payload["summary"],
        "not_human_data": True,
    }


def _validate_ablation_informed_base_selection(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "selected_base_candidate_id",
        "why_packet_0030_not_proven",
        "prior_repair_causal_status",
        "evidence_rationale",
        "embodiment_preserving_insight",
        "record_law_proof_answer_insight",
        "explicit_dominance_rejection_reason",
        "dominance_rejection_protected_effect_or_forbidden_change_evidence",
        "uncertainty",
    ):
        _require_type(payload, key, str)
    _require_true(payload, "not_human_data")
    return {
        "selected_base_candidate_id": payload["selected_base_candidate_id"],
        "why_packet_0030_not_proven": payload["why_packet_0030_not_proven"],
        "prior_repair_causal_status": payload["prior_repair_causal_status"],
        "evidence_rationale": payload["evidence_rationale"],
        "embodiment_preserving_insight": payload["embodiment_preserving_insight"],
        "record_law_proof_answer_insight": payload[
            "record_law_proof_answer_insight"
        ],
        "explicit_dominance_rejection_reason": payload[
            "explicit_dominance_rejection_reason"
        ],
        "dominance_rejection_protected_effect_or_forbidden_change_evidence": payload[
            "dominance_rejection_protected_effect_or_forbidden_change_evidence"
        ],
        "uncertainty": payload["uncertainty"],
        "not_human_data": True,
    }


def _validate_ablation_informed_handle_selection(payload: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "selected_next_handle",
        "why_previous_repair_weak_or_cosmetic",
        "evidence_summary",
        "why_handle_better_than_opening_patch",
        "local_law_explanation",
        "explicit_same_handle_justification",
        "same_handle_justification_evidence",
        "uncertainty",
    ):
        _require_type(payload, key, str)
    _require_type(payload, "strongest_rival_pressure_remains_blocking", bool)
    _require_true(payload, "not_human_data")
    return {
        "selected_next_handle": payload["selected_next_handle"],
        "why_previous_repair_weak_or_cosmetic": payload[
            "why_previous_repair_weak_or_cosmetic"
        ],
        "evidence_summary": payload["evidence_summary"],
        "why_handle_better_than_opening_patch": payload[
            "why_handle_better_than_opening_patch"
        ],
        "local_law_explanation": payload["local_law_explanation"],
        "explicit_same_handle_justification": payload[
            "explicit_same_handle_justification"
        ],
        "same_handle_justification_evidence": payload[
            "same_handle_justification_evidence"
        ],
        "uncertainty": payload["uncertainty"],
        "strongest_rival_pressure_remains_blocking": payload[
            "strongest_rival_pressure_remains_blocking"
        ],
        "not_human_data": True,
    }


def _validate_ablation_informed_patch_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    _require_object_list(payload, "patches")
    patches = []
    for index, patch in enumerate(payload["patches"]):
        patches.append(
            _validate_object(
                patch,
                f"patches[{index}]",
                (
                    "patch_span_id",
                    "replacement_text",
                    "rationale",
                    "local_law_explanation",
                    "uncertainty",
                ),
            )
        )
    _require_type(payload, "preserves_necessary_philosophical_pressure", str)
    _require_true(payload, "avoids_full_rewrite")
    _require_true(payload, "not_human_data")
    return {
        "patches": patches,
        "preserves_necessary_philosophical_pressure": payload[
            "preserves_necessary_philosophical_pressure"
        ],
        "avoids_full_rewrite": True,
        "not_human_data": True,
    }


def _validate_bounded_macro_recomposition(payload: dict[str, Any]) -> dict[str, Any]:
    _require_type(payload, "replacement_section_text", str)
    _require_type(payload, "macro_recomposition_plan", dict)
    macro_plan = _validate_object(
        payload["macro_recomposition_plan"],
        "macro_recomposition_plan",
        ("plan_summary",),
    )
    _require_string_list(
        payload["macro_recomposition_plan"],
        "plan_steps",
        field_prefix="macro_recomposition_plan.",
    )
    _require_type(payload, "section_plan", dict)
    section_plan = _validate_object(
        payload["section_plan"],
        "section_plan",
        ("target_movement", "rationale"),
    )
    _require_type(payload["section_plan"], "bounded", bool, field_prefix="section_plan.")
    _require_type(
        payload["section_plan"],
        "full_rewrite",
        bool,
        field_prefix="section_plan.",
    )
    _require_object_list(payload, "constraint_mapping")
    constraint_mapping = []
    for index, item in enumerate(payload["constraint_mapping"]):
        validated = _validate_object(
            item,
            f"constraint_mapping[{index}]",
            (
                "constraint_id",
                "supporting_replacement_excerpt",
                "rationale",
                "uncertainty",
                "risk_note",
            ),
        )
        _require_type(
            item,
            "satisfied_claim",
            bool,
            field_prefix=f"constraint_mapping[{index}].",
        )
        validated["satisfied_claim"] = item["satisfied_claim"]
        constraint_mapping.append(validated)
    _require_object_list(payload, "active_target_mapping")
    active_target_mapping = []
    for index, item in enumerate(payload["active_target_mapping"]):
        validated = _validate_object(
            item,
            f"active_target_mapping[{index}]",
            (
                "target_id",
                "target_paragraph_ref",
                "before_excerpt",
                "supporting_replacement_excerpt",
                "what_changed",
                "rationale",
                "uncertainty",
                "unchanged_justification",
            ),
        )
        _require_type(
            item,
            "unchanged",
            bool,
            field_prefix=f"active_target_mapping[{index}].",
        )
        validated["unchanged"] = item["unchanged"]
        active_target_mapping.append(validated)
    _require_object_list(payload, "target_paragraph_replacements")
    target_paragraph_replacements = []
    for index, item in enumerate(payload["target_paragraph_replacements"]):
        validated = _validate_object(
            item,
            f"target_paragraph_replacements[{index}]",
            (
                "target_paragraph_ref",
                "before_text_sha256",
                "replacement_text",
                "material_change_summary",
                "risk_notes",
                "uncertainty",
            ),
        )
        _require_string_list(
            item,
            "active_target_ids_covered",
            field_prefix=f"target_paragraph_replacements[{index}].",
        )
        _require_string_list(
            item,
            "preserved_effects",
            field_prefix=f"target_paragraph_replacements[{index}].",
        )
        validated["active_target_ids_covered"] = list(
            item["active_target_ids_covered"]
        )
        validated["preserved_effects"] = list(item["preserved_effects"])
        target_paragraph_replacements.append(validated)
    _require_object_list(payload, "target_span_replacements")
    target_span_replacements = []
    for index, item in enumerate(payload["target_span_replacements"]):
        validated = _validate_object(
            item,
            f"target_span_replacements[{index}]",
            (
                "target_span_ref",
                "parent_target_paragraph_ref",
                "before_text_sha256",
                "replacement_excerpt",
                "material_change_summary",
                "risk_notes",
                "uncertainty",
            ),
        )
        _require_string_list(
            item,
            "active_target_ids_covered",
            field_prefix=f"target_span_replacements[{index}].",
        )
        validated["active_target_ids_covered"] = list(
            item["active_target_ids_covered"]
        )
        target_span_replacements.append(validated)
    for key in (
        "rationale",
        "local_law_explanation",
        "uncertainty",
        "predicted_reader_state_effect",
    ):
        _require_type(payload, key, str)
    result = {
        "replacement_section_text": payload["replacement_section_text"],
        "macro_recomposition_plan": {
            "plan_summary": macro_plan["plan_summary"],
            "plan_steps": list(payload["macro_recomposition_plan"]["plan_steps"]),
        },
        "section_plan": {
            "target_movement": section_plan["target_movement"],
            "bounded": payload["section_plan"]["bounded"],
            "full_rewrite": payload["section_plan"]["full_rewrite"],
            "rationale": section_plan["rationale"],
        },
        "constraint_mapping": constraint_mapping,
        "active_target_mapping": active_target_mapping,
        "rationale": payload["rationale"],
        "local_law_explanation": payload["local_law_explanation"],
        "uncertainty": payload["uncertainty"],
        "predicted_reader_state_effect": payload["predicted_reader_state_effect"],
    }
    result["target_paragraph_replacements"] = target_paragraph_replacements
    result["target_span_replacements"] = target_span_replacements
    return result


def _validate_object_motion_causality_generation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "replacement_region_text",
        "uncertainty",
        "predicted_reader_effect",
    ):
        _require_type(payload, key, str)
        if not payload[key].strip():
            raise ModelValidationError(f"{key} must not be empty")
    _require_string_list(payload, "object_motion_generation_plan")
    if not payload["object_motion_generation_plan"]:
        raise ModelValidationError("object_motion_generation_plan must not be empty")
    _require_object_list(payload, "target_unit_mapping")
    target_unit_mapping = []
    for index, item in enumerate(payload["target_unit_mapping"]):
        validated = _validate_object(
            item,
            f"target_unit_mapping[{index}]",
            (
                "unit_id",
                "before_text_excerpt",
                "replacement_text_excerpt",
                "object_motion_or_action",
                "visible_consequence",
                "how_reader_infers_pressure_before_explanation",
                "forbidden_change_avoided",
            ),
        )
        target_unit_mapping.append(validated)
    _require_string_list(payload, "protected_effects_preservation_notes")
    if not payload["protected_effects_preservation_notes"]:
        raise ModelValidationError(
            "protected_effects_preservation_notes must not be empty"
        )
    _require_string_list(payload, "forbidden_change_self_check")
    if not payload["forbidden_change_self_check"]:
        raise ModelValidationError("forbidden_change_self_check must not be empty")
    return {
        "replacement_region_text": payload["replacement_region_text"],
        "object_motion_generation_plan": list(payload["object_motion_generation_plan"]),
        "target_unit_mapping": target_unit_mapping,
        "protected_effects_preservation_notes": list(
            payload["protected_effects_preservation_notes"]
        ),
        "uncertainty": payload["uncertainty"],
        "predicted_reader_effect": payload["predicted_reader_effect"],
        "forbidden_change_self_check": list(payload["forbidden_change_self_check"]),
    }


def _validate_residual_intervention_generation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    for key in ("replacement_region_text", "uncertainty"):
        _require_type(payload, key, str)
        if not payload[key].strip():
            raise ModelValidationError(f"{key} must not be empty")
    _require_object_list(payload, "target_unit_mappings")
    target_unit_mappings = []
    for index, item in enumerate(payload["target_unit_mappings"]):
        validated = _validate_object(
            item,
            f"target_unit_mappings[{index}]",
            (
                "target_unit_id",
                "before_text_sha256",
                "mechanism_operation",
                "material_relation_or_action",
                "visible_consequence",
                "intended_first_read_effect",
            ),
        )
        _require_string_list(
            item,
            "protected_effects_preserved",
            field_prefix=f"target_unit_mappings[{index}].",
        )
        _require_string_list(
            item,
            "covered_target_ids",
            field_prefix=f"target_unit_mappings[{index}].",
        )
        if not item["protected_effects_preserved"]:
            raise ModelValidationError(
                f"target_unit_mappings[{index}].protected_effects_preserved must not be empty"
            )
        if not item["covered_target_ids"]:
            raise ModelValidationError(
                f"target_unit_mappings[{index}].covered_target_ids must not be empty"
            )
        validated["protected_effects_preserved"] = list(
            item["protected_effects_preserved"]
        )
        validated["covered_target_ids"] = list(item["covered_target_ids"])
        target_unit_mappings.append(validated)
    _require_string_list(payload, "intervention_plan")
    if not payload["intervention_plan"]:
        raise ModelValidationError("intervention_plan must not be empty")
    _require_object_list(payload, "constraint_mapping")
    constraint_mapping = []
    for index, item in enumerate(payload["constraint_mapping"]):
        constraint_mapping.append(
            _validate_object(
                item,
                f"constraint_mapping[{index}]",
                ("constraint_id", "how_satisfied", "risk_note"),
            )
        )
    if not constraint_mapping:
        raise ModelValidationError("constraint_mapping must not be empty")
    _require_string_list(payload, "protected_effects_notes")
    if not payload["protected_effects_notes"]:
        raise ModelValidationError("protected_effects_notes must not be empty")
    _require_string_list(payload, "forbidden_change_self_check")
    if not payload["forbidden_change_self_check"]:
        raise ModelValidationError("forbidden_change_self_check must not be empty")
    return {
        "replacement_region_text": payload["replacement_region_text"],
        "target_unit_mappings": target_unit_mappings,
        "intervention_plan": list(payload["intervention_plan"]),
        "constraint_mapping": constraint_mapping,
        "protected_effects_notes": list(payload["protected_effects_notes"]),
        "forbidden_change_self_check": list(payload["forbidden_change_self_check"]),
        "uncertainty": payload["uncertainty"],
    }


def _validate_nonlocal_law_guided_generation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {
        "revised_text",
        "revision_summary",
        "law_application_summary",
        "target_unit_change_report",
        "materiality_self_report",
        "semantic_self_report",
        "non_imitation_report",
        "protected_strengths_report",
        "forbidden_regression_report",
        "post_generation_evidence_plan_acknowledgment",
        "generation_allowed",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
    }
    extra_fields = sorted(set(payload) - allowed_fields)
    if extra_fields:
        raise ModelValidationError(
            "unexpected fields in nonlocal law-guided generation output: "
            + ", ".join(extra_fields)
        )
    for key in ("revised_text", "revision_summary", "law_application_summary"):
        _require_type(payload, key, str)
        if not payload[key].strip():
            raise ModelValidationError(f"{key} must not be empty")
    _require_object_list(payload, "target_unit_change_report")
    target_report = []
    for index, item in enumerate(payload["target_unit_change_report"]):
        validated = _validate_object(
            item,
            f"target_unit_change_report[{index}]",
            ("target_unit_id", "change_summary"),
        )
        _require_type(
            item,
            "materiality_satisfied",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        _require_type(
            item,
            "semantic_satisfied",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        validated["materiality_satisfied"] = item["materiality_satisfied"]
        validated["semantic_satisfied"] = item["semantic_satisfied"]
        target_report.append(validated)
    if not target_report:
        raise ModelValidationError("target_unit_change_report must not be empty")

    materiality_report = _validate_requirement_self_report(
        payload,
        "materiality_self_report",
    )
    semantic_report = _validate_requirement_self_report(
        payload,
        "semantic_self_report",
    )
    non_imitation = _validate_nonlocal_boolean_report(
        payload,
        "non_imitation_report",
        bool_key="passed",
        array_key="forbidden_material_absent",
    )
    protected = _validate_nonlocal_boolean_report(
        payload,
        "protected_strengths_report",
        bool_key="preserved",
        array_key="protected_strengths",
    )
    forbidden = _validate_nonlocal_boolean_report(
        payload,
        "forbidden_regression_report",
        bool_key="passed",
        array_key="avoided_regressions",
    )
    acknowledgment = _validate_object(
        payload.get("post_generation_evidence_plan_acknowledgment"),
        "post_generation_evidence_plan_acknowledgment",
        (),
    )
    for key in (
        "ablation_required",
        "reader_state_eval_required",
        "synthesis_required",
        "strongest_rival_remains_blocking",
    ):
        _require_true(
            payload["post_generation_evidence_plan_acknowledgment"],
            key,
            field_prefix="post_generation_evidence_plan_acknowledgment.",
        )
        acknowledgment[key] = True
    _require_false(payload, "generation_allowed")
    _require_false(payload, "finality_claimed")
    _require_false(payload, "phase_shift_claimed")
    _require_false(payload, "strongest_rival_defeated_claimed")
    return {
        "revised_text": payload["revised_text"],
        "revision_summary": payload["revision_summary"],
        "law_application_summary": payload["law_application_summary"],
        "target_unit_change_report": target_report,
        "materiality_self_report": materiality_report,
        "semantic_self_report": semantic_report,
        "non_imitation_report": non_imitation,
        "protected_strengths_report": protected,
        "forbidden_regression_report": forbidden,
        "post_generation_evidence_plan_acknowledgment": acknowledgment,
        "generation_allowed": False,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
    }


def _validate_selected_nonlocal_law_target_generation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {
        "text",
        "revision_summary",
        "selected_target_application_summary",
        "living_event_sequence_repair_summary",
        "target_unit_change_report",
        "materiality_self_report",
        "semantic_self_report",
        "non_imitation_acknowledgement",
        "protected_strengths_preservation_acknowledgement",
        "forbidden_regression_acknowledgement",
        "safety_claims",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
        "current_best_supersession_claimed",
        "generation_allowed",
    }
    extra_fields = sorted(set(payload) - allowed_fields)
    if extra_fields:
        raise ModelValidationError(
            "unexpected fields in selected nonlocal law target generation output: "
            + ", ".join(extra_fields)
        )
    for key in (
        "text",
        "revision_summary",
        "selected_target_application_summary",
        "living_event_sequence_repair_summary",
    ):
        _require_type(payload, key, str)
        if not payload[key].strip():
            raise ModelValidationError(f"{key} must not be empty")

    _require_object_list(payload, "target_unit_change_report")
    target_report = []
    for index, item in enumerate(payload["target_unit_change_report"]):
        validated = _validate_object(
            item,
            f"target_unit_change_report[{index}]",
            ("target_unit_id", "change_summary"),
        )
        _require_type(
            item,
            "materiality_satisfied",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        _require_type(
            item,
            "semantic_satisfied",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        validated["materiality_satisfied"] = item["materiality_satisfied"]
        validated["semantic_satisfied"] = item["semantic_satisfied"]
        target_report.append(validated)
    if not target_report:
        raise ModelValidationError("target_unit_change_report must not be empty")

    materiality_report = _validate_requirement_self_report(
        payload,
        "materiality_self_report",
    )
    semantic_report = _validate_requirement_self_report(
        payload,
        "semantic_self_report",
    )
    non_imitation = _validate_nonlocal_boolean_report(
        payload,
        "non_imitation_acknowledgement",
        bool_key="passed",
        array_key="forbidden_material_absent",
    )
    protected = _validate_nonlocal_boolean_report(
        payload,
        "protected_strengths_preservation_acknowledgement",
        bool_key="preserved",
        array_key="protected_strengths",
    )
    forbidden = _validate_nonlocal_boolean_report(
        payload,
        "forbidden_regression_acknowledgement",
        bool_key="passed",
        array_key="avoided_regressions",
    )
    safety_claims = _validate_object(payload.get("safety_claims"), "safety_claims", ())
    for key in (
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
        "current_best_supersession_claimed",
        "generation_allowed",
    ):
        _require_false(payload, key)
        _require_false(payload["safety_claims"], key, field_prefix="safety_claims.")
        safety_claims[key] = False
    return {
        "text": payload["text"],
        "revision_summary": payload["revision_summary"],
        "selected_target_application_summary": payload[
            "selected_target_application_summary"
        ],
        "living_event_sequence_repair_summary": payload[
            "living_event_sequence_repair_summary"
        ],
        "target_unit_change_report": target_report,
        "materiality_self_report": materiality_report,
        "semantic_self_report": semantic_report,
        "non_imitation_acknowledgement": non_imitation,
        "protected_strengths_preservation_acknowledgement": protected,
        "forbidden_regression_acknowledgement": forbidden,
        "safety_claims": safety_claims,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
        "current_best_supersession_claimed": False,
        "generation_allowed": False,
    }


SELECTED_TARGET_CYCLE_PHRASES = (
    "changes the next glance",
    "changes the order of seeing",
    "where later seeing must be changed by that receiving",
    "condition through which the next perception has to pass",
    "Only after this does the room begin to instruct",
    "The room teaches slowly",
    "one condition to the next",
    "later seeing",
    "perception has to pass",
)
SELECTED_TARGET_CYCLE_UNIT_IDS = (
    "preserve_living_event_sequence_gain",
    "reduce_direct_mechanism_naming",
    "convert_declarative_instruction_to_object_pressure",
    "convert_law_naming_to_perceptual_sequence",
    "preserve_earned_explanation_not_abolished",
    "protect_object_activity_and_delicacy",
    "preserve_non_selected_risks_as_constraints",
    "preserve_strongest_rival_blocker_and_non_imitation",
)
SELECTED_TARGET_CYCLE_MATERIAL_UNIT_IDS = (
    "reduce_direct_mechanism_naming",
    "convert_declarative_instruction_to_object_pressure",
    "convert_law_naming_to_perceptual_sequence",
)
SELECTED_TARGET_CYCLE_PRESERVATION_UNIT_IDS = (
    "preserve_living_event_sequence_gain",
    "preserve_earned_explanation_not_abolished",
    "protect_object_activity_and_delicacy",
    "preserve_non_selected_risks_as_constraints",
    "preserve_strongest_rival_blocker_and_non_imitation",
)


def _validate_selected_target_cycle_mechanism_visibility_generation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {
        "text",
        "revision_summary",
        "mechanism_visibility_repair_summary",
        "phrase_handling_report",
        "target_unit_change_report",
        "materiality_report",
        "semantic_report",
        "preservation_report",
        "forbidden_overcorrection_report",
        "post_generation_evidence_note",
        "generation_allowed",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
    }
    extra_fields = sorted(set(payload) - allowed_fields)
    if extra_fields:
        raise ModelValidationError(
            "unexpected fields in selected-target cycle generation output: "
            + ", ".join(extra_fields)
        )
    for key in (
        "text",
        "revision_summary",
        "mechanism_visibility_repair_summary",
    ):
        _require_type(payload, key, str)
        if not payload[key].strip():
            raise ModelValidationError(f"{key} must not be empty")

    phrase_report = _validate_selected_target_cycle_phrase_report(
        payload.get("phrase_handling_report")
    )
    target_report = _validate_selected_target_cycle_target_report(
        payload.get("target_unit_change_report")
    )
    materiality = _validate_selected_target_cycle_simple_report(
        payload.get("materiality_report"),
        "materiality_report",
    )
    semantic = _validate_selected_target_cycle_simple_report(
        payload.get("semantic_report"),
        "semantic_report",
    )
    preservation = _validate_selected_target_cycle_simple_report(
        payload.get("preservation_report"),
        "preservation_report",
    )
    forbidden = _validate_selected_target_cycle_simple_report(
        payload.get("forbidden_overcorrection_report"),
        "forbidden_overcorrection_report",
    )
    evidence = _validate_selected_target_cycle_simple_report(
        payload.get("post_generation_evidence_note"),
        "post_generation_evidence_note",
    )
    for key in (
        "generation_allowed",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
    ):
        _require_false(payload, key)
    return {
        "text": payload["text"],
        "revision_summary": payload["revision_summary"],
        "mechanism_visibility_repair_summary": payload[
            "mechanism_visibility_repair_summary"
        ],
        "phrase_handling_report": phrase_report,
        "target_unit_change_report": target_report,
        "materiality_report": materiality,
        "semantic_report": semantic,
        "preservation_report": preservation,
        "forbidden_overcorrection_report": forbidden,
        "post_generation_evidence_note": evidence,
        "generation_allowed": False,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
    }


def _validate_selected_target_cycle_phrase_report(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ModelValidationError("phrase_handling_report must be a list")
    if len(value) != len(SELECTED_TARGET_CYCLE_PHRASES):
        raise ModelValidationError("phrase_handling_report must contain exactly 9 items")
    by_phrase: dict[str, dict[str, Any]] = {}
    allowed_actions = (
        "transformed",
        "retained_as_earned",
        "removed_because_unneeded",
    )
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ModelValidationError(
                f"phrase_handling_report[{index}] must be an object"
            )
        _require_type(item, "phrase", str, field_prefix=f"phrase_handling_report[{index}].")
        phrase = item["phrase"]
        if phrase not in SELECTED_TARGET_CYCLE_PHRASES:
            raise ModelValidationError(f"unknown phrase in phrase_handling_report: {phrase}")
        if phrase in by_phrase:
            raise ModelValidationError(f"duplicate phrase in phrase_handling_report: {phrase}")
        _require_type(
            item,
            "phrase_found_in_source",
            bool,
            field_prefix=f"phrase_handling_report[{index}].",
        )
        _require_type(
            item,
            "handling_action",
            str,
            field_prefix=f"phrase_handling_report[{index}].",
        )
        _require_enum_value(
            item["handling_action"],
            f"phrase_handling_report[{index}].handling_action",
            allowed_actions,
        )
        _require_false(
            item,
            "deletion_required",
            field_prefix=f"phrase_handling_report[{index}].",
        )
        for field in (
            "automatic_deletion_forbidden",
            "pressure_point_not_deletion_target",
            "transformation_or_earned_retention_required",
            "earned_retention_allowed",
            "context_sensitive_decision_required",
            "preserve_if_still_earned_after_object_pressure",
            "causal_force_preserved",
        ):
            _require_true(
                item,
                field,
                field_prefix=f"phrase_handling_report[{index}].",
            )
        _require_type(
            item,
            "handling_rationale",
            str,
            field_prefix=f"phrase_handling_report[{index}].",
        )
        if not item["handling_rationale"].strip():
            raise ModelValidationError(
                f"phrase_handling_report[{index}].handling_rationale must not be empty"
            )
        _require_false(
            item,
            "living_event_sequence_weakened",
            field_prefix=f"phrase_handling_report[{index}].",
        )
        by_phrase[phrase] = {
            "phrase": phrase,
            "phrase_found_in_source": item["phrase_found_in_source"],
            "handling_action": item["handling_action"],
            "deletion_required": False,
            "automatic_deletion_forbidden": True,
            "pressure_point_not_deletion_target": True,
            "transformation_or_earned_retention_required": True,
            "earned_retention_allowed": True,
            "context_sensitive_decision_required": True,
            "preserve_if_still_earned_after_object_pressure": True,
            "handling_rationale": item["handling_rationale"],
            "causal_force_preserved": True,
            "living_event_sequence_weakened": False,
        }
    missing = [phrase for phrase in SELECTED_TARGET_CYCLE_PHRASES if phrase not in by_phrase]
    if missing:
        raise ModelValidationError(
            "phrase_handling_report missing required phrases: " + ", ".join(missing)
        )
    return [by_phrase[phrase] for phrase in SELECTED_TARGET_CYCLE_PHRASES]


def _validate_selected_target_cycle_target_report(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ModelValidationError("target_unit_change_report must be a list")
    by_unit: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ModelValidationError(
                f"target_unit_change_report[{index}] must be an object"
            )
        _require_type(item, "unit_id", str, field_prefix=f"target_unit_change_report[{index}].")
        unit_id = item["unit_id"]
        if unit_id not in SELECTED_TARGET_CYCLE_UNIT_IDS:
            raise ModelValidationError(f"unknown target unit: {unit_id}")
        if unit_id in by_unit:
            raise ModelValidationError(f"duplicate target unit: {unit_id}")
        _require_type(
            item,
            "change_summary",
            str,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        _require_type(
            item,
            "material_change_present",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        _require_type(
            item,
            "preservation_passed",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        _require_type(
            item,
            "validation_required",
            bool,
            field_prefix=f"target_unit_change_report[{index}].",
        )
        if unit_id in SELECTED_TARGET_CYCLE_MATERIAL_UNIT_IDS and item[
            "material_change_present"
        ] is not True:
            raise ModelValidationError(f"material change missing for {unit_id}")
        if unit_id in SELECTED_TARGET_CYCLE_PRESERVATION_UNIT_IDS and item[
            "preservation_passed"
        ] is not True:
            raise ModelValidationError(f"preservation failed for {unit_id}")
        if item["validation_required"] is not True:
            raise ModelValidationError(f"validation_required must be true for {unit_id}")
        by_unit[unit_id] = {
            "unit_id": unit_id,
            "change_summary": item["change_summary"],
            "material_change_present": item["material_change_present"],
            "preservation_passed": item["preservation_passed"],
            "validation_required": True,
        }
    missing = [unit_id for unit_id in SELECTED_TARGET_CYCLE_UNIT_IDS if unit_id not in by_unit]
    if missing:
        raise ModelValidationError(
            "target_unit_change_report missing required units: " + ", ".join(missing)
        )
    return [by_unit[unit_id] for unit_id in SELECTED_TARGET_CYCLE_UNIT_IDS]


def _validate_selected_target_cycle_simple_report(
    value: object,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{label} must be an object")
    _require_type(value, "passed", bool, field_prefix=f"{label}.")
    if value["passed"] is not True:
        raise ModelValidationError(f"{label}.passed must be true")
    _require_type(value, "summary", str, field_prefix=f"{label}.")
    if not value["summary"].strip():
        raise ModelValidationError(f"{label}.summary must not be empty")
    _require_string_list(value, "evidence", field_prefix=f"{label}.")
    if not value["evidence"]:
        raise ModelValidationError(f"{label}.evidence must not be empty")
    return {
        "passed": True,
        "summary": value["summary"],
        "evidence": list(value["evidence"]),
    }


def _validate_nonlocal_law_candidate_reader_state_evaluation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {
        "first_pass_reader_state",
        "second_pass_reader_state",
        "candidate_vs_packet_0063_comparison",
        "ablation_control_reader_state_matrix",
        "law_effect_assessment",
        "risk_probe_results",
        "strongest_rival_pressure_assessment",
        "reader_state_summary",
        "recommended_next_evidence_step",
        "generation_allowed",
        "synthesis_authorized",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
    }
    extra_fields = sorted(set(payload) - allowed_fields)
    if extra_fields:
        forbidden = [
            field
            for field in extra_fields
            if _looks_like_candidate_or_rewrite_field(field)
            or field in {"current_best_updated", "candidate_text", "revised_text"}
        ]
        if forbidden:
            raise ModelValidationError(
                "nonlocal law candidate reader-state evaluation must not return "
                f"candidate/rewrite/current-best fields: {forbidden}"
            )
        raise ModelValidationError(
            "nonlocal law candidate reader-state evaluation contains unsupported "
            f"fields: {extra_fields}"
        )

    first_pass = _validate_reader_state_observation(
        payload.get("first_pass_reader_state"),
        "first_pass_reader_state",
    )
    second_pass = _validate_reader_state_observation(
        payload.get("second_pass_reader_state"),
        "second_pass_reader_state",
    )
    comparison = _validate_nonlocal_reader_state_comparison(
        payload.get("candidate_vs_packet_0063_comparison")
    )
    controls = _validate_nonlocal_reader_state_controls(
        payload,
        "ablation_control_reader_state_matrix",
    )
    law = _validate_nonlocal_reader_state_law_assessment(
        payload.get("law_effect_assessment")
    )
    risks = _validate_nonlocal_reader_state_risks(payload, "risk_probe_results")
    rival = _validate_nonlocal_reader_state_rival_assessment(
        payload.get("strongest_rival_pressure_assessment")
    )
    summary = _validate_nonlocal_reader_state_summary(
        payload.get("reader_state_summary")
    )
    _require_type(payload, "recommended_next_evidence_step", str)
    if not payload["recommended_next_evidence_step"].strip():
        raise ModelValidationError("recommended_next_evidence_step must not be empty")
    _require_false(payload, "generation_allowed")
    _require_false(payload, "synthesis_authorized")
    _require_false(payload, "finality_claimed")
    _require_false(payload, "phase_shift_claimed")
    _require_false(payload, "strongest_rival_defeated_claimed")
    return {
        "first_pass_reader_state": first_pass,
        "second_pass_reader_state": second_pass,
        "candidate_vs_packet_0063_comparison": comparison,
        "ablation_control_reader_state_matrix": controls,
        "law_effect_assessment": law,
        "risk_probe_results": risks,
        "strongest_rival_pressure_assessment": rival,
        "reader_state_summary": summary,
        "recommended_next_evidence_step": payload["recommended_next_evidence_step"],
        "generation_allowed": False,
        "synthesis_authorized": False,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
    }


def _validate_selected_nonlocal_law_candidate_reader_state_evaluation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {
        "living_event_sequence_result",
        "living_event_sequence_summary",
        "living_event_sequence_evidence",
        "static_trace_reduction_result",
        "static_trace_reduction_summary",
        "static_trace_reduction_evidence",
        "static_trace_comparison_to_packet_0002",
        "remaining_static_trace_risk",
        "causal_bridge_result",
        "causal_bridge_summary",
        "bridge_examples",
        "consequence_before_naming_result",
        "consequence_before_naming_summary",
        "before_naming_evidence",
        "explanation_entry_point",
        "risk_if_overstated",
        "causal_mechanism_overexplained_result",
        "causal_mechanism_overexplained_summary",
        "overexplained_phrases",
        "risk_status",
        "next_target_implication",
        "explanation_earned_result",
        "explanation_earned",
        "explanation_earned_summary",
        "explanation_abolished",
        "remaining_explicitness_risk",
        "packet_0002_gains_preserved_result",
        "preserved_strengths",
        "weakened_strengths",
        "object_field_preserved",
        "proof_no_answer_pressure_preserved",
        "return_structure_preserved",
        "non_imitation_result",
        "rival_imitation_detected",
        "forbidden_rival_hits",
        "forbidden_rival_mode_hits",
        "non_imitation_evidence",
        "strongest_rival_pressure_result",
        "strongest_rival_remains_blocking",
        "strongest_rival_defeated_claimed",
        "pressure_summary",
        "overall_selected_target_reader_state_result",
        "reader_state_summary",
        "risk_probe_results",
        "risk_probe_results_by_id",
        "synthesis_recommendation",
        "finality_claimed",
        "phase_shift_claimed",
        "current_best_supersession_claimed",
        "generation_recommended",
        "immediate_finalization_recommended",
        "synthesis_authorized",
        "current_best_updated",
    }
    extra_fields = sorted(set(payload) - allowed_fields)
    if extra_fields:
        raise ModelValidationError(
            "selected nonlocal law candidate reader-state evaluation contains "
            f"unsupported fields: {extra_fields}"
        )
    result_fields = (
        "living_event_sequence_result",
        "static_trace_reduction_result",
        "causal_bridge_result",
        "consequence_before_naming_result",
        "causal_mechanism_overexplained_result",
        "explanation_earned_result",
        "packet_0002_gains_preserved_result",
        "non_imitation_result",
        "overall_selected_target_reader_state_result",
    )
    for field in result_fields:
        _require_type(payload, field, str)
        _require_enum_value(payload[field], field, _SELECTED_READER_STATE_RESULTS)
    _require_type(payload, "strongest_rival_pressure_result", str)
    _require_enum_value(
        payload["strongest_rival_pressure_result"],
        "strongest_rival_pressure_result",
        (
            "narrowed_but_blocking",
            "unchanged_blocking",
            "worsened",
            "requires_synthesis",
        ),
    )
    _require_type(payload, "explanation_earned", str)
    _require_enum_value(
        payload["explanation_earned"],
        "explanation_earned",
        ("true", "false", "mixed"),
    )
    string_fields = (
        "living_event_sequence_summary",
        "living_event_sequence_evidence",
        "static_trace_reduction_summary",
        "static_trace_reduction_evidence",
        "static_trace_comparison_to_packet_0002",
        "remaining_static_trace_risk",
        "causal_bridge_summary",
        "consequence_before_naming_summary",
        "before_naming_evidence",
        "explanation_entry_point",
        "risk_if_overstated",
        "causal_mechanism_overexplained_summary",
        "risk_status",
        "next_target_implication",
        "explanation_earned_summary",
        "remaining_explicitness_risk",
        "non_imitation_evidence",
        "pressure_summary",
        "reader_state_summary",
        "synthesis_recommendation",
    )
    for field in string_fields:
        _require_type(payload, field, str)
        if not payload[field].strip():
            raise ModelValidationError(f"{field} must not be empty")
    bridge = _validate_object(
        payload.get("bridge_examples"),
        "bridge_examples",
        ("ring_grain", "dust_bare_strip", "spoon_saucer_crack", "hum_order_of_seeing"),
    )
    _require_nonempty_strings(bridge, "bridge_examples")
    for field in ("overexplained_phrases", "preserved_strengths", "weakened_strengths"):
        _require_string_list(payload, field)
    _require_type(payload, "object_field_preserved", bool)
    _require_type(payload, "proof_no_answer_pressure_preserved", bool)
    _require_type(payload, "return_structure_preserved", bool)
    _require_false(payload, "explanation_abolished")
    _require_false(payload, "rival_imitation_detected")
    _require_string_list(payload, "forbidden_rival_hits")
    _require_string_list(payload, "forbidden_rival_mode_hits")
    if payload["forbidden_rival_hits"]:
        raise ModelValidationError("forbidden_rival_hits must be empty")
    if payload["forbidden_rival_mode_hits"]:
        raise ModelValidationError("forbidden_rival_mode_hits must be empty")
    _require_type(payload, "strongest_rival_remains_blocking", bool)
    if payload["strongest_rival_remains_blocking"] is not True:
        raise ModelValidationError("strongest_rival_remains_blocking must be true")
    for field in (
        "strongest_rival_defeated_claimed",
        "finality_claimed",
        "phase_shift_claimed",
        "current_best_supersession_claimed",
        "generation_recommended",
        "immediate_finalization_recommended",
        "synthesis_authorized",
        "current_best_updated",
    ):
        _require_false(payload, field)
    risks, risks_by_id = _validate_selected_reader_state_risk_probes(payload)
    normalized = {
        field: payload[field]
        for field in allowed_fields
        if field
        not in {
            "bridge_examples",
            "risk_probe_results",
            "risk_probe_results_by_id",
        }
        and field in payload
    }
    return {
        **normalized,
        "bridge_examples": bridge,
        "risk_probe_results": risks,
        "risk_probe_results_by_id": risks_by_id,
    }


def _validate_reader_state_observation(
    value: object,
    label: str,
) -> dict[str, str]:
    observation = _validate_object(
        value,
        label,
        ("result", "evidence", "reader_state_effect", "packet_0063_contrast"),
    )
    _require_enum_value(
        observation["result"],
        f"{label}.result",
        ("improved", "unchanged", "worsened", "inconclusive"),
    )
    _require_nonempty_strings(observation, label)
    return observation


_SELECTED_READER_STATE_RESULTS = (
    "improved",
    "preserved",
    "worsened",
    "mixed",
    "active_risk",
    "narrowed_but_blocking",
    "unsupported",
    "requires_synthesis",
)

def _validate_selected_reader_state_risk_probes(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    if isinstance(payload.get("risk_probe_results_by_id"), dict):
        by_id = _validate_selected_reader_state_risk_probe_map(
            payload["risk_probe_results_by_id"]
        )
    elif isinstance(payload.get("risk_probe_results"), list):
        by_id = _validate_selected_reader_state_risk_probe_list(
            payload["risk_probe_results"]
        )
    else:
        raise ModelValidationError("risk_probe_results_by_id is required")
    risks = [
        {
            "risk_id": risk_id,
            "risk_label": SELECTED_READER_STATE_REQUIRED_RISK_PROBES[risk_id],
            **by_id[risk_id],
        }
        for risk_id in SELECTED_READER_STATE_REQUIRED_RISK_PROBES
    ]
    return risks, by_id


def _validate_selected_reader_state_risk_probe_map(
    value: dict[str, Any],
) -> dict[str, dict[str, str]]:
    required_ids = tuple(SELECTED_READER_STATE_REQUIRED_RISK_PROBES)
    missing_ids = [risk_id for risk_id in required_ids if risk_id not in value]
    if missing_ids:
        raise ModelValidationError("missing risk probes: " + ", ".join(missing_ids))
    unknown_ids = sorted(set(value) - set(required_ids))
    if unknown_ids:
        raise ModelValidationError(
            "unknown risk_probe_results_by_id ids: " + ", ".join(unknown_ids)
        )
    return {
        risk_id: _validate_selected_reader_state_risk_probe_item(
            value[risk_id],
            f"risk_probe_results_by_id.{risk_id}",
        )
        for risk_id in required_ids
    }


def _validate_selected_reader_state_risk_probe_list(
    value: list[object],
) -> dict[str, dict[str, str]]:
    by_id: dict[str, dict[str, str]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ModelValidationError(f"risk_probe_results[{index}] must be an object")
        risk_id = item.get("risk_id")
        if not isinstance(risk_id, str):
            raise ModelValidationError(
                f"risk_probe_results[{index}].risk_id must be a canonical risk id"
            )
        if risk_id not in SELECTED_READER_STATE_REQUIRED_RISK_PROBES:
            raise ModelValidationError(
                f"unknown risk_probe_results[{index}].risk_id: {risk_id}"
            )
        if risk_id in by_id:
            raise ModelValidationError(f"duplicate risk probe id: {risk_id}")
        by_id[risk_id] = _validate_selected_reader_state_risk_probe_item(
            item,
            f"risk_probe_results[{index}]",
        )
    missing_ids = [
        risk_id
        for risk_id in SELECTED_READER_STATE_REQUIRED_RISK_PROBES
        if risk_id not in by_id
    ]
    if missing_ids:
        raise ModelValidationError("missing risk probes: " + ", ".join(missing_ids))
    return by_id


def _validate_selected_reader_state_risk_probe_item(
    value: object,
    label: str,
) -> dict[str, str]:
    risk = _validate_object(
        value,
        label,
        ("result", "summary", "evidence", "risk_status", "next_target_implication"),
    )
    for field in ("result", "risk_status"):
        _require_enum_value(risk[field], f"{label}.{field}", _SELECTED_READER_STATE_RESULTS)
    _require_nonempty_strings(risk, label)
    return {
        "result": risk["result"],
        "summary": risk["summary"],
        "evidence": risk["evidence"],
        "risk_status": risk["risk_status"],
        "next_target_implication": risk["next_target_implication"],
    }


def _validate_nonlocal_reader_state_comparison(value: object) -> dict[str, str]:
    comparison = _validate_object(
        value,
        "candidate_vs_packet_0063_comparison",
        (
            "first_read_pressure_result",
            "object_event_consequence_result",
            "explanation_timing_result",
            "reread_return_result",
            "comparison_summary",
        ),
    )
    for key in (
        "first_read_pressure_result",
        "object_event_consequence_result",
        "explanation_timing_result",
        "reread_return_result",
    ):
        _require_enum_value(
            comparison[key],
            f"candidate_vs_packet_0063_comparison.{key}",
            ("improved", "unchanged", "worsened", "inconclusive"),
        )
    _require_nonempty_strings(comparison, "candidate_vs_packet_0063_comparison")
    return comparison


def _validate_nonlocal_reader_state_controls(
    payload: dict[str, Any],
    key: str,
) -> list[dict[str, str]]:
    _require_object_list(payload, key)
    controls = []
    for index, item in enumerate(payload[key]):
        control = _validate_object(
            item,
            f"{key}[{index}]",
            (
                "control_id",
                "expected_reader_state_contrast",
                "predicted_result",
                "evidence",
            ),
        )
        _require_enum_value(
            control["predicted_result"],
            f"{key}[{index}].predicted_result",
            ("supports_candidate", "weakens_candidate", "mixed", "inconclusive"),
        )
        _require_nonempty_strings(control, f"{key}[{index}]")
        controls.append(control)
    if not controls:
        raise ModelValidationError(f"{key} must not be empty")
    return controls


def _validate_nonlocal_reader_state_law_assessment(value: object) -> dict[str, object]:
    law = _validate_object(
        value,
        "law_effect_assessment",
        (
            "object_event_consequence_result",
            "explanation_timing_result",
            "law_effect_summary",
        ),
    )
    for key in ("object_event_consequence_result", "explanation_timing_result"):
        _require_enum_value(
            law[key],
            f"law_effect_assessment.{key}",
            ("improved", "unchanged", "worsened", "inconclusive"),
        )
    if not isinstance(value, dict):
        raise ModelValidationError("law_effect_assessment must be an object")
    _require_type(
        value,
        "explanation_earned_not_abolished",
        bool,
        field_prefix="law_effect_assessment.",
    )
    _require_nonempty_strings(law, "law_effect_assessment")
    return {
        **law,
        "explanation_earned_not_abolished": value[
            "explanation_earned_not_abolished"
        ],
    }


def _validate_nonlocal_reader_state_risks(
    payload: dict[str, Any],
    key: str,
) -> list[dict[str, str]]:
    _require_object_list(payload, key)
    risks = []
    for index, item in enumerate(payload[key]):
        risk = _validate_object(
            item,
            f"{key}[{index}]",
            ("risk_id", "result", "evidence"),
        )
        _require_enum_value(
            risk["result"],
            f"{key}[{index}].result",
            ("passed", "at_risk", "failed", "inconclusive"),
        )
        _require_nonempty_strings(risk, f"{key}[{index}]")
        risks.append(risk)
    if not risks:
        raise ModelValidationError(f"{key} must not be empty")
    return risks


def _validate_nonlocal_reader_state_rival_assessment(value: object) -> dict[str, object]:
    rival = _validate_object(
        value,
        "strongest_rival_pressure_assessment",
        ("strongest_rival_pressure_result", "pressure_summary"),
    )
    _require_enum_value(
        rival["strongest_rival_pressure_result"],
        "strongest_rival_pressure_assessment.strongest_rival_pressure_result",
        ("still_blocking", "narrowed_but_blocking", "worsened", "inconclusive"),
    )
    if not isinstance(value, dict):
        raise ModelValidationError("strongest_rival_pressure_assessment must be an object")
    _require_type(
        value,
        "strongest_rival_remains_blocking",
        bool,
        field_prefix="strongest_rival_pressure_assessment.",
    )
    if value["strongest_rival_remains_blocking"] is not True:
        raise ModelValidationError(
            "strongest_rival_pressure_assessment.strongest_rival_remains_blocking "
            "must be true"
        )
    _require_nonempty_strings(rival, "strongest_rival_pressure_assessment")
    return {**rival, "strongest_rival_remains_blocking": True}


def _validate_nonlocal_reader_state_summary(value: object) -> dict[str, object]:
    summary = _validate_object(
        value,
        "reader_state_summary",
        ("overall_reader_state_result", "summary"),
    )
    _require_enum_value(
        summary["overall_reader_state_result"],
        "reader_state_summary.overall_reader_state_result",
        (
            "supports_candidate_for_synthesis",
            "does_not_support_candidate",
            "mixed_requires_synthesis",
            "inconclusive",
        ),
    )
    if not isinstance(value, dict):
        raise ModelValidationError("reader_state_summary must be an object")
    _require_false(value, "candidate_superiority_claimed", field_prefix="reader_state_summary.")
    _require_false(
        value,
        "current_best_supersession_claimed",
        field_prefix="reader_state_summary.",
    )
    _require_nonempty_strings(summary, "reader_state_summary")
    return {
        **summary,
        "candidate_superiority_claimed": False,
        "current_best_supersession_claimed": False,
    }


def _validate_requirement_self_report(
    payload: dict[str, Any],
    key: str,
) -> list[dict[str, object]]:
    _require_object_list(payload, key)
    report = []
    for index, item in enumerate(payload[key]):
        validated = _validate_object(
            item,
            f"{key}[{index}]",
            ("requirement", "evidence"),
        )
        _require_type(item, "satisfied", bool, field_prefix=f"{key}[{index}].")
        validated["satisfied"] = item["satisfied"]
        report.append(validated)
    if not report:
        raise ModelValidationError(f"{key} must not be empty")
    return report


def _validate_nonlocal_boolean_report(
    payload: dict[str, Any],
    key: str,
    *,
    bool_key: str,
    array_key: str,
) -> dict[str, object]:
    if not isinstance(payload.get(key), dict):
        raise ModelValidationError(f"{key} must be an object")
    report = payload[key]
    _require_type(report, bool_key, bool, field_prefix=f"{key}.")
    _require_type(report, "evidence", str, field_prefix=f"{key}.")
    if not report["evidence"].strip():
        raise ModelValidationError(f"{key}.evidence must not be empty")
    _require_string_list(report, array_key, field_prefix=f"{key}.")
    if not report[array_key]:
        raise ModelValidationError(f"{key}.{array_key} must not be empty")
    return {
        bool_key: report[bool_key],
        "evidence": report["evidence"],
        array_key: list(report[array_key]),
    }


def _validate_model_backed_local_law_rival_diagnostic(
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {
        "law_id",
        "comparison_summary",
        "packet_0063_law_application",
        "rival_law_application",
        "first_read_pressure_findings",
        "explanation_timing_findings",
        "object_event_sequence_findings",
        "proof_no_answer_findings",
        "reread_transformation_findings",
        "strongest_rival_advantage_assessment",
        "non_imitation_constraints_acknowledged",
        "future_strategy_implications",
        "generation_allowed",
        "finality_claimed",
        "phase_shift_claimed",
    }
    extra_fields = sorted(set(payload) - allowed_fields)
    if extra_fields:
        forbidden = [
            field
            for field in extra_fields
            if _looks_like_candidate_or_rewrite_field(field)
        ]
        if forbidden:
            raise ModelValidationError(
                "model-backed local-law diagnostic must not return candidate or "
                f"rewrite text fields: {forbidden}"
            )
        raise ModelValidationError(
            "model-backed local-law diagnostic contains unsupported fields: "
            f"{extra_fields}"
        )

    _reject_candidate_or_rewrite_fields(payload)
    _require_type(payload, "law_id", str)
    if payload["law_id"] != "first_read_pressure_precedes_explanation_law":
        raise ModelValidationError(
            "law_id must be first_read_pressure_precedes_explanation_law"
        )
    _require_type(payload, "comparison_summary", str)
    _require_type(payload, "non_imitation_constraints_acknowledged", bool)
    if payload["non_imitation_constraints_acknowledged"] is not True:
        raise ModelValidationError(
            "non_imitation_constraints_acknowledged must be true"
        )
    _require_false(payload, "generation_allowed")
    _require_false(payload, "finality_claimed")
    _require_false(payload, "phase_shift_claimed")

    finding_fields = (
        "packet_0063_law_application",
        "rival_law_application",
        "first_read_pressure_findings",
        "explanation_timing_findings",
        "object_event_sequence_findings",
        "proof_no_answer_findings",
        "reread_transformation_findings",
        "strongest_rival_advantage_assessment",
        "future_strategy_implications",
    )
    findings = {
        field: _validate_local_law_diagnostic_finding(payload[field], field)
        for field in finding_fields
    }
    _reject_immediate_generation_recommendation(
        findings["future_strategy_implications"]
    )
    return {
        "law_id": payload["law_id"],
        "comparison_summary": payload["comparison_summary"],
        **findings,
        "non_imitation_constraints_acknowledged": payload[
            "non_imitation_constraints_acknowledged"
        ],
        "generation_allowed": payload["generation_allowed"],
        "finality_claimed": payload["finality_claimed"],
        "phase_shift_claimed": payload["phase_shift_claimed"],
    }


def _validate_local_law_diagnostic_finding(
    payload: object,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ModelValidationError(f"{label} must be an object")
    validated = _validate_object(
        payload,
        label,
        ("claim", "evidence_basis", "uncertainty", "risk_if_misused"),
    )
    _require_string_list(payload, "support_spans_or_passages", field_prefix=f"{label}.")
    validated["support_spans_or_passages"] = list(payload["support_spans_or_passages"])
    return validated


def _reject_candidate_or_rewrite_fields(value: object, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}".strip(".")
            if _looks_like_candidate_or_rewrite_field(str(key)):
                raise ModelValidationError(
                    "model-backed local-law diagnostic must not return candidate "
                    f"or rewrite text fields: {key_path}"
                )
            _reject_candidate_or_rewrite_fields(item, key_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_candidate_or_rewrite_fields(item, f"{path}[{index}]")


def _looks_like_candidate_or_rewrite_field(field_name: str) -> bool:
    lowered = field_name.lower()
    return lowered in {
        "candidate_text",
        "generated_candidate",
        "generated_text",
        "rewrite_text",
        "rewritten_text",
        "revision_text",
        "revised_text",
        "revised_candidate_text",
        "replacement_text",
        "replacement_region_text",
        "replacement_section_text",
    }


def _reject_immediate_generation_recommendation(
    future_strategy_implications: dict[str, object],
) -> None:
    text = " ".join(
        str(future_strategy_implications.get(key, ""))
        for key in ("claim", "evidence_basis", "risk_if_misused")
    ).lower()
    forbidden_phrases = (
        "authorize generation",
        "generation is authorized",
        "generate immediately",
        "immediate generation",
        "create a candidate now",
        "write the next candidate",
    )
    if any(phrase in text for phrase in forbidden_phrases):
        raise ModelValidationError(
            "future_strategy_implications must not recommend immediate generation"
        )


def _validate_revision_span_ref(payload: dict[str, Any], label: str) -> dict[str, str]:
    return _validate_object(
        payload,
        label,
        ("source_label", "source_class", "artifact_id", "region", "selection_basis"),
    )


def _validate_changed_span(payload: dict[str, Any], label: str) -> dict[str, object]:
    validated = _validate_object(
        payload,
        label,
        (
            "changed_span_id",
            "patch_span_id",
            "before",
            "after",
            "region",
            "target_expansion_reason",
            "reason",
        ),
    )
    _require_type(payload, "inside_target", bool, field_prefix=f"{label}.")
    _require_type(payload, "within_selected_target", bool, field_prefix=f"{label}.")
    _require_type(payload, "requires_target_expansion", bool, field_prefix=f"{label}.")
    _require_string_list(payload, "source_patch_span_ids", field_prefix=f"{label}.")
    if not payload["source_patch_span_ids"]:
        raise ModelValidationError(f"{label}.source_patch_span_ids must not be empty")
    if payload["inside_target"] != payload["within_selected_target"]:
        raise ModelValidationError(
            f"{label}.inside_target and {label}.within_selected_target must agree"
        )
    if payload["inside_target"] and payload["requires_target_expansion"]:
        raise ModelValidationError(
            f"{label}.requires_target_expansion must be false for in-target changes"
        )
    if payload["requires_target_expansion"] and not payload["target_expansion_reason"].strip():
        raise ModelValidationError(
            f"{label}.target_expansion_reason is required when target expansion is required"
        )
    validated["inside_target"] = payload["inside_target"]
    validated["within_selected_target"] = payload["within_selected_target"]
    validated["requires_target_expansion"] = payload["requires_target_expansion"]
    validated["source_patch_span_ids"] = payload["source_patch_span_ids"]
    return validated


def _validate_revision_patch_target(payload: dict[str, Any], label: str) -> dict[str, object]:
    validated = _validate_object(
        payload,
        label,
        (
            "patch_target_id",
            "target_region_label",
            "target_region_description",
            "allowed_span_ref",
            "text_window",
        ),
    )
    _validate_patch_target_id(payload["patch_target_id"], f"{label}.patch_target_id")
    _require_integer(payload, "paragraph_index", field_prefix=f"{label}.")
    _require_string_list(payload, "protected_outside_spans", field_prefix=f"{label}.")
    if not str(payload["text_window"]).strip():
        raise ModelValidationError(f"{label}.text_window must not be empty")
    if str(payload["patch_target_id"]).strip() == str(
        payload["target_region_description"]
    ).strip():
        raise ModelValidationError(
            f"{label}.patch_target_id must be canonical, not target_region_description"
        )
    validated["paragraph_index"] = int(payload["paragraph_index"])
    validated["protected_outside_spans"] = payload["protected_outside_spans"]
    return validated


def _validate_patch_target_id(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise ModelValidationError(f"{label} must be a string")
    if not _is_canonical_revision_id(value, "target_"):
        raise ModelValidationError(
            f"{label} must be a canonical patch target id such as target_opening_first_pivots"
        )


def _validate_patch_span_id(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise ModelValidationError(f"{label} must be a string")
    if not _is_canonical_revision_id(value, "span_"):
        raise ModelValidationError(
            f"{label} must be a canonical patch span id such as "
            "span_target_opening_first_pivots_p02_s01"
        )


def _is_canonical_revision_id(value: str, prefix: str) -> bool:
    if not value.startswith(prefix):
        return False
    if value != value.lower():
        return False
    if "__" in value or value.endswith("_"):
        return False
    return all(character.isalnum() or character == "_" for character in value)


def _validate_revision_patch(payload: dict[str, Any], label: str) -> dict[str, object]:
    validated = _validate_object(
        payload,
        label,
        (
            "patch_id",
            "patch_span_id",
            "patch_target_id",
            "operation",
            "replacement_text",
            "inserted_text",
            "failure_addressed",
            "causal_handle_id",
            "rationale",
            "expected_reader_state_change",
            "target_expansion_reason",
            "uncertainty",
        ),
    )
    _validate_patch_span_id(payload["patch_span_id"], f"{label}.patch_span_id")
    _validate_patch_target_id(payload["patch_target_id"], f"{label}.patch_target_id")
    if payload["operation"] not in AUTONOMOUS_REVISION_PATCH_OPERATIONS:
        raise ModelValidationError(
            f"{label}.operation must be one of {list(AUTONOMOUS_REVISION_PATCH_OPERATIONS)}"
        )
    _require_string_list(payload, "protected_effects_preserved", field_prefix=f"{label}.")
    _require_string_list(payload, "forbidden_changes_respected", field_prefix=f"{label}.")
    _require_type(payload, "requires_target_expansion", bool, field_prefix=f"{label}.")
    _require_number(payload, "confidence", field_prefix=f"{label}.")
    operation = str(payload["operation"])
    replacement_text = str(payload["replacement_text"]).strip()
    inserted_text = str(payload["inserted_text"]).strip()
    if operation in {"replace", "compress"} and not replacement_text:
        raise ModelValidationError(
            f"{label}.replacement_text is required for {operation}"
        )
    if operation in {"insert_after", "insert_before"} and not inserted_text:
        raise ModelValidationError(
            f"{label}.inserted_text is required for {operation}"
        )
    if payload["requires_target_expansion"] and not payload[
        "target_expansion_reason"
    ].strip():
        raise ModelValidationError(
            f"{label}.target_expansion_reason is required when target expansion is required"
        )
    validated["protected_effects_preserved"] = payload["protected_effects_preserved"]
    validated["forbidden_changes_respected"] = payload["forbidden_changes_respected"]
    validated["requires_target_expansion"] = payload["requires_target_expansion"]
    validated["confidence"] = payload["confidence"]
    return validated


def _validate_revision_variant(payload: dict[str, Any], label: str) -> dict[str, object]:
    validated = _validate_object(
        payload,
        label,
        (
            "variant_id",
            "operation",
            "variant_probe",
            "ablation_probe",
            "text",
            "expected_reader_state_change",
            "uncertainty",
        ),
    )
    _require_type(payload, "executed", bool, field_prefix=f"{label}.")
    validated["executed"] = payload["executed"]
    return validated


def _validate_ablation_row(payload: dict[str, Any], label: str) -> dict[str, object]:
    validated = _validate_object(
        payload,
        label,
        (
            "row_id",
            "comparison_summary",
            "predicted_or_observed_effect",
            "reader_state_effect_estimate",
            "rationale",
            "risk_notes",
            "uncertainty",
        ),
    )
    validated["not_human_data"] = True
    return validated


def _validate_revision_judgment_provenance(payload: dict[str, Any]) -> dict[str, list[str]]:
    allowed = set(AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS)
    validated = {}
    for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS:
        _require_string_list(payload, key, field_prefix="judgment_provenance.")
        if not payload[key]:
            raise ModelValidationError(f"judgment_provenance.{key} must not be empty")
        invalid = [source for source in payload[key] if source not in allowed]
        if invalid:
            raise ModelValidationError(
                f"judgment_provenance.{key} contains unsupported sources: {invalid}"
            )
        validated[key] = list(payload[key])
    return validated


def _validate_revision_judgment_rationale(payload: dict[str, Any]) -> dict[str, str]:
    validated = {}
    for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS:
        _require_type(payload, key, str, field_prefix="judgment_rationale.")
        rationale = payload[key].strip()
        if not rationale:
            raise ModelValidationError(f"judgment_rationale.{key} must not be empty")
        validated[key] = rationale
    return validated


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


def _provenance_token_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "string",
            "enum": list(AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS),
        },
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


def _require_enum_value(value: object, label: str, allowed_values: tuple[str, ...]) -> None:
    if value not in allowed_values:
        raise ModelValidationError(
            f"{label} must be one of: {', '.join(allowed_values)}"
        )


def _require_nonempty_strings(payload: dict[str, str], label: str) -> None:
    for key, value in payload.items():
        if isinstance(value, str) and not value.strip():
            raise ModelValidationError(f"{label}.{key} must not be empty")


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


def _require_nullable_string(
    payload: dict[str, Any],
    key: str,
    *,
    field_prefix: str = "",
) -> None:
    if key not in payload:
        raise ModelValidationError(f"missing required field: {field_prefix}{key}")
    if payload[key] is not None and not isinstance(payload[key], str):
        raise ModelValidationError(f"{field_prefix}{key} must be a string or null")


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


def _require_true(payload: dict[str, Any], key: str, *, field_prefix: str = "") -> None:
    _require_type(payload, key, bool, field_prefix=field_prefix)
    if payload[key] is not True:
        raise ModelValidationError(f"{field_prefix}{key} must be true")


def _require_false(payload: dict[str, Any], key: str, *, field_prefix: str = "") -> None:
    _require_type(payload, key, bool, field_prefix=field_prefix)
    if payload[key] is not False:
        raise ModelValidationError(f"{field_prefix}{key} must be false")


def _require_object_list(payload: dict[str, Any], key: str, *, field_prefix: str = "") -> None:
    _require_type(payload, key, list, field_prefix=field_prefix)
    for index, value in enumerate(payload[key]):
        if not isinstance(value, dict):
            raise ModelValidationError(f"{field_prefix}{key}[{index}] must be an object")


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
