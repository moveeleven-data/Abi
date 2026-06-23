"""Bounded macro recomposition from autonomous evidence synthesis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import MODEL_CALL_VALIDATION_FAILED, link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
    ModelValidationError,
    WorkerRole,
    parse_and_validate_structured_output,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID = "bounded_macro_recomposition_v1"
BOUNDED_MACRO_RECOMPOSITION_CREATED_BY = "bounded_macro_recomposition_v1_controller"
BOUNDED_MACRO_RECOMPOSITION_CLIENTS = ("fake", "openai")
BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT = 8
BOUNDED_MACRO_RECOMPOSITION_REQUIRED_MODEL_CALLS = 1
BOUNDED_MACRO_RECOMPOSITION_PROMPT_CONTRACT_ID = (
    "autonomous.bounded_macro_recomposition.v1"
)

BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES = (
    "macro_recomposition_subject_manifest",
    "macro_recomposition_brief_ref",
    "macro_recomposition_work_order",
    "protected_effects_and_forbidden_changes",
    "macro_recomposition_plan",
    "macro_patch_or_section_plan",
    "macro_recomposed_candidate_text",
    "macro_recomposition_diff_report",
    "macro_rival_pressure_check",
    "macro_recomposition_gate_report",
    "macro_recomposition_packet",
)

REQUIRED_SYNTHESIS_ARTIFACT_FILES = (
    "autonomous_evidence_synthesis_packet.json",
    "best_current_candidate_selection.json",
    "macro_recomposition_brief.json",
    "local_law_case_notes.json",
    "residual_blocker_map.json",
    "rival_pressure_summary.json",
    "exhausted_handle_report.json",
    "failed_or_rejected_repairs.json",
    "strategic_decision_report.json",
)

OPTIONAL_SYNTHESIS_ARTIFACT_FILES = (
    "reader_state_evidence_adjudication.json",
    "reader_state_tension_report.json",
)

TARGET_MOVEMENT = "middle_and_return_movement"
READER_STATE_MACRO_2_TARGET_SCOPE = "reader_state_informed_macro_2"

REQUIRED_SEMANTIC_CONSTRAINT_IDS = (
    "proof_from_inside_line",
    "cosmic_silence_as_isolation_condition",
    "return_without_regression",
    "no_outside_answer_or_rescue",
    "strongest_rival_pressure",
    "table_dust_spoon_saucer_local_field",
    "record_law_proof_answer_compression_preserved",
)

ACTIVE_TRANSFORMATION_TARGET_IDS = (
    "middle_abstraction_ladder_compression",
    "proof_line_redundancy_cleanup",
    "no_outside_answer_pressure_preservation",
    "final_return_closure_embodiment",
    "object_event_pressure_without_pressure_naming",
)

MATERIAL_REQUIRED_ACTIVE_TARGET_IDS = (
    "middle_abstraction_ladder_compression",
    "proof_line_redundancy_cleanup",
    "no_outside_answer_pressure_preservation",
    "final_return_closure_embodiment",
)

READER_STATE_MACRO_2_ACTIVE_TARGET_IDS = (
    "proof_no_outside_answer_refinement",
    "final_return_echo_reread_strength",
    "thesis_visible_proof_language_reduction",
    "opening_return_transformation_strengthening",
    "preserve_reader_state_partial_gain",
)

READER_STATE_MACRO_2_MATERIAL_REQUIRED_TARGET_IDS = (
    "proof_no_outside_answer_refinement",
    "final_return_echo_reread_strength",
    "thesis_visible_proof_language_reduction",
    "opening_return_transformation_strengthening",
)

SUPPORTED_TARGET_SCOPES = (
    TARGET_MOVEMENT,
    READER_STATE_MACRO_2_TARGET_SCOPE,
    "proof_no_outside_answer_refinement",
    "final_return_echo_reread_strength",
    "reader_state_opening_return_transformation",
)


@dataclass(frozen=True)
class BoundedMacroRecompositionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class MacroSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_artifact_ids: dict[str, str]
    synthesis_payloads: dict[str, dict[str, Any]]
    selected_best_candidate: dict[str, Any]
    base_packet_dir: Path
    base_packet_id: str
    base_packet_kind: str
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str
    base_word_count: int
    source_parent_ids: tuple[str, ...]
    fixture_only: bool
    normalized_brief: NormalizedMacroRecompositionBrief


@dataclass(frozen=True)
class NormalizedMacroRecompositionBrief:
    brief_type: str
    target_scope: str
    target_movement: str
    target_submovement: tuple[str, ...]
    active_transformation_target_ids: tuple[str, ...]
    material_required_target_ids: tuple[str, ...]
    protected_effects: tuple[str, ...]
    forbidden_changes: tuple[str, ...]
    success_criteria: tuple[str, ...]
    source_reader_state_evidence: dict[str, Any]
    source_reader_state_tensions: dict[str, Any]
    reader_state_evidence_packet_id: str | None
    selected_best_candidate_packet_id: str
    selected_best_candidate_text_sha256: str | None
    requires_future_ablation_or_reader_eval: bool
    reader_state_informed: bool


@dataclass(frozen=True)
class RecomposedText:
    text: str
    target_start_index: int
    target_end_index: int
    unchanged_prefix: list[str]
    original_target: list[str]
    replacement: list[str]


@dataclass(frozen=True)
class TargetAddressedRetryPlan:
    retryable: bool
    first_attempt_payload: dict[str, object] | None
    retry_reason: str
    failed_target_paragraph_refs: tuple[str, ...]
    failed_target_span_refs: tuple[str, ...]
    failure_reasons_by_ref: dict[str, str]
    failure_reasons_by_span: dict[str, str]
    failed_material_target_ids_by_ref: dict[str, list[str]]
    failed_active_targets_by_span: dict[str, list[str]]
    first_failure_message: str


@dataclass(frozen=True)
class MacroTargetValidationResult:
    passed: bool
    replacement_paragraphs: tuple[str, ...]
    paragraph_failures: tuple[dict[str, object], ...]
    span_failures: tuple[dict[str, object], ...]
    failed_target_paragraph_refs: tuple[str, ...]
    failed_target_span_refs: tuple[str, ...]
    failed_material_target_ids_by_ref: dict[str, list[str]]
    failed_active_targets_by_span: dict[str, list[str]]
    failure_reasons_by_ref: dict[str, str]
    failure_reasons_by_span: dict[str, str]
    target_coverage_report: dict[str, object]
    fatal_failures: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ForbiddenClaimFinding:
    path: str
    excerpt: str
    claim_type: str
    reason: str


def run_bounded_macro_recomposition(
    config: AbiConfig,
    *,
    client_name: str,
    synthesis_packet: Path,
    allow_live_model: bool = False,
    max_model_calls: int = BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> BoundedMacroRecompositionResult:
    if client_name not in BOUNDED_MACRO_RECOMPOSITION_CLIENTS:
        return _refusal(
            message=f"Unsupported bounded macro recomposition client: {client_name}",
            synthesis_packet=synthesis_packet,
        )
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Bounded macro recomposition OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    f"Bounded macro recomposition OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )
        if max_model_calls < BOUNDED_MACRO_RECOMPOSITION_REQUIRED_MODEL_CALLS:
            return _refusal(
                message=(
                    "Bounded macro recomposition OpenAI path refused; "
                    f"max-model-calls {max_model_calls} is below required budget "
                    f"{BOUNDED_MACRO_RECOMPOSITION_REQUIRED_MODEL_CALLS}."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )

    initialize_database(config)
    with connect(config.db_path) as connection:
        try:
            subject = _load_macro_subject(connection, config, synthesis_packet)
        except ValueError as error:
            return _refusal(
                message=f"Bounded macro recomposition refused; {error}",
                synthesis_packet=synthesis_packet,
                client_name=client_name,
            )
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Bounded macro recomposition refused; synthesis run is not "
                    f"registered: {subject.run_id}"
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "bounded_macro_recomposition")
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
            created_by=BOUNDED_MACRO_RECOMPOSITION_CREATED_BY,
            fixture_only=subject.fixture_only,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        model_results: list[ModelDriverResult] = []
        model_payload: dict[str, object] | None = None
        model_call_id: str | None = None
        retry_report: dict[str, object] = _target_addressed_retry_report_not_attempted()

        payloads["macro_recomposition_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir,
            client_name=client_name,
            max_model_calls=max_model_calls,
        )
        artifacts["macro_recomposition_subject_manifest"] = writer.write_artifact(
            "macro_recomposition_subject_manifest",
            payloads["macro_recomposition_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["macro_recomposition_brief_ref"] = _build_brief_ref(subject)
        artifacts["macro_recomposition_brief_ref"] = writer.write_artifact(
            "macro_recomposition_brief_ref",
            payloads["macro_recomposition_brief_ref"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                *list(subject.source_parent_ids),
            ],
        )

        payloads["macro_recomposition_work_order"] = _build_work_order(subject)
        artifacts["macro_recomposition_work_order"] = writer.write_artifact(
            "macro_recomposition_work_order",
            payloads["macro_recomposition_work_order"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                artifacts["macro_recomposition_brief_ref"].id,
            ],
        )

        payloads["protected_effects_and_forbidden_changes"] = _build_protected_effects(
            subject
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["macro_recomposition_brief_ref"].id,
                artifacts["macro_recomposition_work_order"].id,
            ],
        )

        if client_name == "openai":
            connection.commit()
            factory = client_factory or _default_openai_client_factory
            model_client = factory(configured_model)
            result = _run_live_macro_recomposition_model(
                config=config,
                subject=subject,
                packet_dir=packet_dir,
                model_client=model_client,
                work_order=payloads["macro_recomposition_work_order"],
                protected_effects=payloads["protected_effects_and_forbidden_changes"],
                parent_ids=[
                    artifacts["macro_recomposition_work_order"].id,
                    artifacts["protected_effects_and_forbidden_changes"].id,
                ],
            )
            model_results.append(result)
            if not result.accepted or result.parsed_payload is None:
                retry_plan = _target_addressed_retry_plan_from_failure(
                    subject=subject,
                    result=result,
                )
                if retry_plan.retryable and len(model_results) < max_model_calls:
                    retry_result = _run_live_macro_recomposition_retry_model(
                        config=config,
                        subject=subject,
                        packet_dir=packet_dir,
                        model_client=model_client,
                        work_order=payloads["macro_recomposition_work_order"],
                        protected_effects=payloads[
                            "protected_effects_and_forbidden_changes"
                        ],
                        retry_plan=retry_plan,
                        parent_ids=[
                            artifacts["macro_recomposition_work_order"].id,
                            artifacts["protected_effects_and_forbidden_changes"].id,
                        ],
                    )
                    model_results.append(retry_result)
                    retry_report = _target_addressed_retry_report(
                        retry_plan=retry_plan,
                        first_attempt_model_call_id=result.model_call.id,
                        retry_model_call_id=retry_result.model_call.id,
                        retry_payload=(
                            retry_result.parsed_payload
                            or _schema_parsed_payload_from_model_result(retry_result)
                        ),
                        merged_payload=None,
                        merged_validation_passed=False,
                    )
                    if retry_result.accepted and retry_result.parsed_payload is not None:
                        merged_payload = _merge_target_addressed_retry_payload(
                            subject=subject,
                            first_payload=retry_plan.first_attempt_payload or {},
                            retry_payload=retry_result.parsed_payload,
                            failed_refs=retry_plan.failed_target_paragraph_refs,
                        )
                        merged_validation = _collect_live_macro_validation_result(
                            subject=subject,
                            payload=merged_payload,
                        )
                        if not merged_validation.passed:
                            retry_report = _target_addressed_retry_report(
                                retry_plan=retry_plan,
                                first_attempt_model_call_id=result.model_call.id,
                                retry_model_call_id=retry_result.model_call.id,
                                retry_payload=retry_result.parsed_payload,
                                merged_payload=merged_payload,
                                merged_validation_passed=False,
                                remaining_failure_message=merged_validation.message,
                                remaining_validation_result=merged_validation,
                            )
                            return _failure_result(
                                subject=subject,
                                packet_dir=packet_dir,
                                client_name=client_name,
                                model=configured_model,
                                artifacts=artifacts,
                                model_results=model_results,
                                message=(
                                    "Bounded macro recomposition refused after "
                                    "target-addressed corrective retry: "
                                    f"{merged_validation.message}"
                                ),
                                retry_report=retry_report,
                            )
                        model_payload = merged_payload
                        model_call_id = retry_result.model_call.id
                        retry_report = _target_addressed_retry_report(
                            retry_plan=retry_plan,
                            first_attempt_model_call_id=result.model_call.id,
                            retry_model_call_id=retry_result.model_call.id,
                            retry_payload=retry_result.parsed_payload,
                            merged_payload=merged_payload,
                            merged_validation_passed=True,
                        )
                    else:
                        return _failure_result(
                            subject=subject,
                            packet_dir=packet_dir,
                            client_name=client_name,
                            model=configured_model,
                            artifacts=artifacts,
                            model_results=model_results,
                            message=_model_failure_message(retry_result),
                            retry_report=retry_report,
                        )
                else:
                    retry_report = _target_addressed_retry_report_not_attempted(
                        retry_plan=retry_plan,
                        first_attempt_model_call_id=result.model_call.id,
                        budget_remaining=len(model_results) < max_model_calls,
                    )
                    retry_note = ""
                    if retry_plan.retryable:
                        retry_note = (
                            " Corrective retry not attempted because remaining "
                            "model-call budget is 0."
                        )
                    elif retry_plan.retry_reason:
                        retry_note = f" Corrective retry not attempted: {retry_plan.retry_reason}."
                    return _failure_result(
                        subject=subject,
                        packet_dir=packet_dir,
                        client_name=client_name,
                        model=configured_model,
                        artifacts=artifacts,
                        model_results=model_results,
                        message=f"{_model_failure_message(result)}{retry_note}",
                        retry_report=retry_report,
                    )
            if model_payload is not None:
                pass
            elif result.accepted and result.parsed_payload is not None:
                model_payload = result.parsed_payload
                model_call_id = result.model_call.id
            else:
                return _failure_result(
                    subject=subject,
                    packet_dir=packet_dir,
                    client_name=client_name,
                    model=configured_model,
                    artifacts=artifacts,
                    model_results=model_results,
                    message=_model_failure_message(result),
                )

        payloads["macro_recomposition_plan"] = _build_recomposition_plan(
            subject,
            model_payload=model_payload,
            model_call_id=model_call_id,
        )
        plan_parent_ids = [
            artifacts["macro_recomposition_work_order"].id,
            artifacts["protected_effects_and_forbidden_changes"].id,
        ]
        if model_payload is None:
            artifacts["macro_recomposition_plan"] = writer.write_artifact(
                "macro_recomposition_plan",
                payloads["macro_recomposition_plan"],
                parent_ids=plan_parent_ids,
            )
        else:
            artifacts["macro_recomposition_plan"] = _write_model_tagged_artifact(
                connection=connection,
                subject=subject,
                packet_dir=packet_dir,
                result=model_results[-1],
                artifact_type="macro_recomposition_plan",
                payload=payloads["macro_recomposition_plan"],
                parent_ids=plan_parent_ids,
            )

        recomposed = (
            _fake_recompose_text(subject)
            if model_payload is None
            else _model_recompose_text(subject, model_payload)
        )
        payloads["macro_patch_or_section_plan"] = _build_patch_or_section_plan(
            subject,
            recomposed,
            model_payload=model_payload,
            model_call_id=model_call_id,
            retry_report=retry_report,
        )
        patch_parent_ids = [
            artifacts["macro_recomposition_plan"].id,
            artifacts["protected_effects_and_forbidden_changes"].id,
        ]
        if model_payload is None:
            artifacts["macro_patch_or_section_plan"] = writer.write_artifact(
                "macro_patch_or_section_plan",
                payloads["macro_patch_or_section_plan"],
                parent_ids=patch_parent_ids,
            )
        else:
            artifacts["macro_patch_or_section_plan"] = _write_model_tagged_artifact(
                connection=connection,
                subject=subject,
                packet_dir=packet_dir,
                result=model_results[-1],
                artifact_type="macro_patch_or_section_plan",
                payload=payloads["macro_patch_or_section_plan"],
                parent_ids=patch_parent_ids,
            )
            model_results[-1] = _link_model_result(
                connection=connection,
                result=model_results[-1],
                parsed_artifact=artifacts["macro_patch_or_section_plan"],
            )

        payloads["macro_recomposed_candidate_text"] = _build_recomposed_candidate(
            subject,
            recomposed,
            model_call_id=model_call_id,
        )
        artifacts["macro_recomposed_candidate_text"] = writer.write_artifact(
            "macro_recomposed_candidate_text",
            payloads["macro_recomposed_candidate_text"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                subject.base_candidate_artifact_id or artifacts["macro_recomposition_subject_manifest"].id,
            ],
        )

        payloads["macro_recomposition_diff_report"] = _build_diff_report(
            subject,
            recomposed,
            payloads["macro_recomposed_candidate_text"],
            model_payload=model_payload,
            retry_report=retry_report,
        )
        artifacts["macro_recomposition_diff_report"] = writer.write_artifact(
            "macro_recomposition_diff_report",
            payloads["macro_recomposition_diff_report"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                artifacts["macro_recomposed_candidate_text"].id,
            ],
        )

        payloads["macro_rival_pressure_check"] = _build_rival_pressure_check(
            subject,
            payloads["macro_recomposed_candidate_text"],
        )
        artifacts["macro_rival_pressure_check"] = writer.write_artifact(
            "macro_rival_pressure_check",
            payloads["macro_rival_pressure_check"],
            parent_ids=[
                artifacts["macro_recomposed_candidate_text"].id,
                artifacts["macro_recomposition_diff_report"].id,
            ],
        )

        payloads["macro_recomposition_gate_report"] = _build_gate_report(
            subject=subject,
            subject_manifest=payloads["macro_recomposition_subject_manifest"],
            protected_effects=payloads["protected_effects_and_forbidden_changes"],
            diff_report=payloads["macro_recomposition_diff_report"],
            rival_check=payloads["macro_rival_pressure_check"],
            model_payload=model_payload,
            retry_report=retry_report,
        )
        artifacts["macro_recomposition_gate_report"] = writer.write_artifact(
            "macro_recomposition_gate_report",
            payloads["macro_recomposition_gate_report"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                artifacts["macro_recomposed_candidate_text"].id,
                artifacts["macro_recomposition_diff_report"].id,
                artifacts["macro_rival_pressure_check"].id,
            ],
        )

        payloads["macro_recomposition_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_results=model_results,
            retry_report=retry_report,
        )
        artifacts["macro_recomposition_packet"] = writer.write_artifact(
            "macro_recomposition_packet",
            payloads["macro_recomposition_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "macro_recomposition_packet"
            ],
        )

        gate_report = payloads["macro_recomposition_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="bounded_macro_recomposition_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        )

    payload = {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_dir": str(packet_dir),
        "packet_id": packet_dir.name,
        "client": client_name,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "counts": {
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "model": configured_model if client_name == "openai" else None,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "target_addressed_retry_report": retry_report,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    return BoundedMacroRecompositionResult(
        exit_code=0,
        payload=payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
        model_results=tuple(model_results),
    )


def _load_macro_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> MacroSubject:
    resolved_packet_dir = _resolve_path(config, synthesis_packet_dir)
    if not resolved_packet_dir.exists() or not resolved_packet_dir.is_dir():
        raise ValueError(f"synthesis packet directory not found: {synthesis_packet_dir}")
    missing = [
        file_name
        for file_name in REQUIRED_SYNTHESIS_ARTIFACT_FILES
        if not (resolved_packet_dir / file_name).exists()
    ]
    if missing:
        raise ValueError(
            "synthesis packet is missing required artifacts: " + ", ".join(missing)
        )
    payloads = {
        file_name.removesuffix(".json"): _read_payload(resolved_packet_dir / file_name)
        for file_name in REQUIRED_SYNTHESIS_ARTIFACT_FILES
    }
    for file_name in OPTIONAL_SYNTHESIS_ARTIFACT_FILES:
        path = resolved_packet_dir / file_name
        if path.exists():
            payloads[file_name.removesuffix(".json")] = _read_payload(path)
    packet = payloads["autonomous_evidence_synthesis_packet"]
    best = payloads["best_current_candidate_selection"]
    selected = best.get("selected_best_candidate")
    if not isinstance(selected, dict):
        raise ValueError("best_current_candidate_selection lacks selected_best_candidate")
    normalized_brief = _normalize_macro_recomposition_brief(
        payloads=payloads,
        selected=selected,
    )
    if selected.get("packet_id") == "packet_0022":
        raise ValueError("synthesis-selected base is the failed pivot packet_0022")
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("synthesis packet has no run_id")
    synthesis_artifact_ids = packet.get("artifact_ids", {})
    if not isinstance(synthesis_artifact_ids, dict):
        synthesis_artifact_ids = {}
    base_packet_dir = _resolve_path(config, Path(str(selected.get("packet_dir", ""))))
    if not base_packet_dir.exists():
        raise ValueError(f"selected best candidate packet not found: {base_packet_dir}")
    base_packet_kind = str(selected.get("packet_kind") or "")
    base_payload = _load_base_candidate_payload(base_packet_dir, base_packet_kind)
    base_text = str(base_payload.get("text") or "")
    if not base_text:
        raise ValueError("selected best candidate packet has no candidate text")
    expected_hash = selected.get("selected_best_candidate_text_sha256") or selected.get(
        "text_sha256"
    )
    actual_hash = sha256_text(base_text)
    if expected_hash and str(expected_hash) != actual_hash:
        raise ValueError("selected best candidate text hash does not match base text")
    source_parent_ids = _source_parent_ids(connection, resolved_packet_dir, synthesis_artifact_ids)
    base_candidate_artifact_id = selected.get("candidate_artifact_id")
    if isinstance(base_candidate_artifact_id, str):
        source_parent_ids = _unique([*source_parent_ids, base_candidate_artifact_id])
    return MacroSubject(
        run_id=run_id,
        synthesis_packet_dir=resolved_packet_dir,
        synthesis_packet_id=str(packet.get("packet_id") or resolved_packet_dir.name),
        synthesis_artifact_ids={
            str(key): str(value) for key, value in synthesis_artifact_ids.items()
        },
        synthesis_payloads=payloads,
        selected_best_candidate=selected,
        base_packet_dir=base_packet_dir,
        base_packet_id=str(selected.get("packet_id") or base_packet_dir.name),
        base_packet_kind=base_packet_kind,
        base_candidate_artifact_id=(
            base_candidate_artifact_id if isinstance(base_candidate_artifact_id, str) else None
        ),
        base_text=base_text,
        base_text_sha256=actual_hash,
        base_word_count=len(_words(base_text)),
        source_parent_ids=tuple(source_parent_ids),
        fixture_only=any(
            bool(payload.get("fixture_only"))
            for payload in payloads.values()
            if isinstance(payload, dict)
        ),
        normalized_brief=normalized_brief,
    )


def _normalize_macro_recomposition_brief(
    *,
    payloads: dict[str, dict[str, Any]],
    selected: dict[str, Any],
) -> NormalizedMacroRecompositionBrief:
    brief = payloads["macro_recomposition_brief"]
    adjudication = payloads.get("reader_state_evidence_adjudication", {})
    tensions = payloads.get("reader_state_tension_report", {})
    brief_type = str(brief.get("brief_type") or "macro_recomposition_brief_v1")
    selected_packet_id = str(selected.get("packet_id") or "")
    if not selected_packet_id:
        raise ValueError("selected best candidate has no packet_id")
    selected_hash = selected.get("selected_best_candidate_text_sha256") or selected.get(
        "text_sha256"
    )
    selected_hash_text = str(selected_hash) if selected_hash else None
    if "reader_state_informed_macro_2" in brief_type or brief.get(
        "reader_state_evidence_consumed"
    ):
        expected_packet_id = str(
            brief.get("current_best_base_candidate_packet_id")
            or _dict_value(brief.get("current_best_base_candidate"), "packet_id")
            or selected_packet_id
        )
        if expected_packet_id != selected_packet_id:
            raise ValueError(
                "macro recomposition brief base does not match selected best candidate"
            )
        submovement = _string_tuple(brief.get("target_movement_or_submovement"))
        if not submovement:
            submovement = (
                "proof/no-outside-answer refinement",
                "final return echo / reread strength",
                "reduce thesis-visible proof language",
                "increase first-read object-event vividness without weakening macro structure",
            )
        return NormalizedMacroRecompositionBrief(
            brief_type=brief_type,
            target_scope=READER_STATE_MACRO_2_TARGET_SCOPE,
            target_movement=READER_STATE_MACRO_2_TARGET_SCOPE,
            target_submovement=submovement,
            active_transformation_target_ids=READER_STATE_MACRO_2_ACTIVE_TARGET_IDS,
            material_required_target_ids=READER_STATE_MACRO_2_MATERIAL_REQUIRED_TARGET_IDS,
            protected_effects=tuple(
                _unique(
                    [
                        *list(brief.get("protected_effects", [])),
                        *list(brief.get("protected_effects_to_preserve", [])),
                        "packet_0008 partial reread gain",
                        "table/dust/spoon/saucer/ring causal field",
                        "reduced overexplanation achieved by macro recomposition",
                        "strongest-rival pressure as active constraint",
                    ]
                )
            ),
            forbidden_changes=tuple(_string_tuple(brief.get("forbidden_changes"))),
            success_criteria=tuple(
                _string_tuple(brief.get("success_criteria"))
                or _string_tuple(brief.get("ablation_and_evaluation_plan_after_recomposition"))
            ),
            source_reader_state_evidence=dict(adjudication),
            source_reader_state_tensions=dict(tensions),
            reader_state_evidence_packet_id=str(
                brief.get("reader_state_evidence_packet_id")
                or adjudication.get("packet_id")
                or ""
            )
            or None,
            selected_best_candidate_packet_id=selected_packet_id,
            selected_best_candidate_text_sha256=selected_hash_text,
            requires_future_ablation_or_reader_eval=True,
            reader_state_informed=True,
        )

    target = str(brief.get("target_region_or_movement") or "")
    if target != TARGET_MOVEMENT:
        raise ValueError(
            "macro recomposition brief has unsupported target; expected a supported "
            f"target scope such as {TARGET_MOVEMENT} or {READER_STATE_MACRO_2_TARGET_SCOPE}"
        )
    if brief.get("allowed_scale") != "bounded_macro_recomposition_not_full_rewrite":
        raise ValueError("macro recomposition brief does not require bounded scale")
    return NormalizedMacroRecompositionBrief(
        brief_type=brief_type,
        target_scope=TARGET_MOVEMENT,
        target_movement=TARGET_MOVEMENT,
        target_submovement=(TARGET_MOVEMENT,),
        active_transformation_target_ids=ACTIVE_TRANSFORMATION_TARGET_IDS,
        material_required_target_ids=MATERIAL_REQUIRED_ACTIVE_TARGET_IDS,
        protected_effects=tuple(_string_tuple(brief.get("protected_effects_to_preserve"))),
        forbidden_changes=tuple(_string_tuple(brief.get("forbidden_changes"))),
        success_criteria=tuple(_string_tuple(brief.get("success_criteria"))),
        source_reader_state_evidence=dict(adjudication),
        source_reader_state_tensions=dict(tensions),
        reader_state_evidence_packet_id=None,
        selected_best_candidate_packet_id=selected_packet_id,
        selected_best_candidate_text_sha256=selected_hash_text,
        requires_future_ablation_or_reader_eval=True,
        reader_state_informed=False,
    )


def _run_live_macro_recomposition_model(
    *,
    config: AbiConfig,
    subject: MacroSubject,
    packet_dir: Path,
    model_client: ModelClient,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    target = _target_window(subject.base_text)
    request = WorkerRequest(
        run_id=subject.run_id,
        worker_role=WorkerRole.BOUNDED_MACRO_RECOMPOSER,
        prompt_contract_id=BOUNDED_MACRO_RECOMPOSITION_PROMPT_CONTRACT_ID,
        schema=BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        input_text=_prompt_for_live_macro_recomposition(
            subject=subject,
            target=target,
            work_order=work_order,
            protected_effects=protected_effects,
        ),
        input_artifact_ids=list(parent_ids),
        input_packet_path=str(subject.synthesis_packet_dir),
        lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        parent_ids=list(parent_ids),
        fixture_only=False,
        output_dir=str(packet_dir),
        register_parsed_artifact=False,
        parsed_payload_validator=lambda payload: _validate_live_macro_payload(
            subject=subject,
            payload=payload,
        ),
    )
    return driver.run(request)


def _run_live_macro_recomposition_retry_model(
    *,
    config: AbiConfig,
    subject: MacroSubject,
    packet_dir: Path,
    model_client: ModelClient,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
    retry_plan: TargetAddressedRetryPlan,
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    target = _target_window(subject.base_text)
    request = WorkerRequest(
        run_id=subject.run_id,
        worker_role=WorkerRole.BOUNDED_MACRO_RECOMPOSER,
        prompt_contract_id=f"{BOUNDED_MACRO_RECOMPOSITION_PROMPT_CONTRACT_ID}.retry",
        schema=BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        input_text=_prompt_for_live_macro_recomposition_retry(
            subject=subject,
            target=target,
            work_order=work_order,
            protected_effects=protected_effects,
            retry_plan=retry_plan,
        ),
        input_artifact_ids=list(parent_ids),
        input_packet_path=str(subject.synthesis_packet_dir),
        lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        parent_ids=list(parent_ids),
        fixture_only=False,
        output_dir=str(packet_dir),
        register_parsed_artifact=False,
        parsed_payload_validator=lambda payload: _validate_live_macro_retry_payload(
            subject=subject,
            payload=payload,
            failed_refs=retry_plan.failed_target_paragraph_refs,
        ),
    )
    return driver.run(request)


def _prompt_for_live_macro_recomposition(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
) -> str:
    return _canonical_json(
        {
            "task": (
                "Propose target-addressed bounded replacements for the "
                "controller-owned middle/return movement."
                if subject.normalized_brief.reader_state_informed
                else "Propose one bounded replacement section for the controller-owned "
                "middle/return movement."
            ),
            "controller_owns": [
                "source_synthesis_packet",
                "base_candidate_choice",
                "base_candidate_text",
                "target_paragraph_indices",
                "target_paragraph_refs",
                "target_paragraph_before_text_hashes",
                "target_span_refs",
                "target_span_before_text_hashes",
                "before_section_text",
                "protected_semantic_constraints",
                "active_transformation_targets",
                "target_coverage_validation",
                "final_text_assembly",
                "diff_report",
                "gates",
                "finalization",
            ],
            "model_may_own": [
                "replacement_section_text",
                "target_paragraph_replacements",
                "target_span_replacements",
                "plan wording",
                "section plan wording",
                "rationale",
                "local-law explanation",
                "uncertainty",
                "predicted reader-state effect",
                "semantic constraint mapping claims",
                "active target mapping claims",
            ],
            "model_must_not_own": [
                "full artifact text",
                "opening or prefix rewrite",
                "base candidate choice",
                "before text",
                "source packet IDs",
                "gate pass/fail",
                "strongest-rival defeated status",
                "finality",
                "phase-shift claim",
            ],
            "source_synthesis_packet_id": subject.synthesis_packet_id,
            "base_candidate_packet_id": subject.base_packet_id,
            "base_candidate_text_sha256": subject.base_text_sha256,
            "target_movement": subject.normalized_brief.target_movement,
            "target_scope": subject.normalized_brief.target_scope,
            "target_submovement": list(subject.normalized_brief.target_submovement),
            "target_paragraph_start_index": target.target_start_index,
            "target_paragraph_end_index": target.target_end_index,
            "unchanged_prefix_text": "\n\n".join(target.unchanged_prefix),
            "before_section_text": "\n\n".join(target.original_target),
            "protected_semantic_constraints": _semantic_constraints(),
            "active_transformation_targets": _active_transformation_targets(
                subject,
                target,
            ),
            "work_order": work_order,
            "protected_effects_and_forbidden_changes": protected_effects,
            "macro_recomposition_brief": subject.synthesis_payloads[
                "macro_recomposition_brief"
            ],
            "rival_pressure_summary": subject.synthesis_payloads[
                "rival_pressure_summary"
            ],
            "output_rule": (
                "Return bounded replacements only, not the full artifact. Include "
                "exactly one constraint_mapping item for every protected "
                "constraint_id and exactly one active_target_mapping item for "
                "every active target_id. For reader_state_informed_macro_2, you "
                "must also return target_paragraph_replacements keyed by the "
                "controller target_paragraph_ref values and target_span_replacements "
                "for every target span marked material_change_required. Replace "
                "every target paragraph marked material_change_required; do not "
                "copy target paragraphs or required target spans unchanged. If two "
                "active targets share a paragraph, the paragraph replacement must "
                "satisfy both. For thesis_visible_proof_language_reduction, "
                "changing only the final proof sentence is insufficient if "
                "thesis-framing spans remain intact. The controller will assemble "
                "final text and reject copied paragraphs, copied required spans, "
                "hash mismatches, missing target refs, missing span refs, and "
                "unsupported target coverage claims. For non-reader-state macro "
                "recomposition, return target_paragraph_replacements and "
                "target_span_replacements as empty arrays."
            ),
        }
    )


def _prompt_for_live_macro_recomposition_retry(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
    retry_plan: TargetAddressedRetryPlan,
) -> str:
    failed_refs = set(retry_plan.failed_target_paragraph_refs)
    target_specs = _target_paragraph_specs(subject, target)
    target_span_specs = _target_span_specs(subject, target, target_specs)
    failed_specs = [
        _retry_failed_paragraph_spec(
            spec,
            target_span_specs=target_span_specs,
            retry_plan=retry_plan,
        )
        for spec in target_specs
        if str(spec["target_paragraph_ref"]) in failed_refs
    ]
    return _canonical_json(
        {
            "task": "Correct failed target-addressed macro replacements only.",
            "retry_kind": "target_addressed_corrective_retry",
            "max_retry_count": 1,
            "controller_owns": [
                "failed target refs",
                "successful first-attempt replacements",
                "final text assembly",
                "diff report",
                "gates",
                "source IDs",
                "finalization",
            ],
            "model_must": [
                "return target_paragraph_replacements keyed only by failed refs",
                "return target_span_replacements for failed required span refs",
                "replace failed paragraphs materially",
                "preserve protected effects",
                "avoid forbidden failures",
                "avoid copied text",
            ],
            "model_must_not": [
                "rewrite successful target paragraphs",
                "return a full artifact",
                "claim final success",
                "claim phase shift",
                "change source IDs or before hashes",
            ],
            "source_synthesis_packet_id": subject.synthesis_packet_id,
            "base_candidate_packet_id": subject.base_packet_id,
            "base_candidate_text_sha256": subject.base_text_sha256,
            "target_movement": subject.normalized_brief.target_movement,
            "target_scope": subject.normalized_brief.target_scope,
            "target_submovement": list(subject.normalized_brief.target_submovement),
            "target_paragraph_start_index": target.target_start_index,
            "target_paragraph_end_index": target.target_end_index,
            "before_section_text": "\n\n".join(target.original_target),
            "work_order": _retry_work_order(
                work_order,
                failed_specs=failed_specs,
            ),
            "failed_target_paragraphs": failed_specs,
            "successful_first_attempt_replacements": (
                _successful_first_attempt_replacements(
                    retry_plan.first_attempt_payload,
                    failed_refs=failed_refs,
                )
            ),
            "first_attempt_failure": {
                "first_failure_message": retry_plan.first_failure_message,
                "failed_target_paragraph_refs": list(
                    retry_plan.failed_target_paragraph_refs
                ),
                "failed_target_span_refs": list(retry_plan.failed_target_span_refs),
                "failure_reasons_by_ref": retry_plan.failure_reasons_by_ref,
                "failure_reasons_by_span": retry_plan.failure_reasons_by_span,
                "failed_material_target_ids_by_ref": (
                    retry_plan.failed_material_target_ids_by_ref
                ),
                "failed_active_targets_by_span": (
                    retry_plan.failed_active_targets_by_span
                ),
                "span_level_instruction": (
                    "Changing only the final proof sentence is insufficient when "
                    "required thesis-framing spans remain intact. Return a new "
                    "target paragraph replacement and span mappings for every "
                    "failed required span."
                ),
            },
            "protected_semantic_constraints": _semantic_constraints(),
            "active_transformation_targets": _active_transformation_targets(
                subject,
                target,
            ),
            "protected_effects_and_forbidden_changes": protected_effects,
            "output_rule": (
                "Return strict BoundedMacroRecompositionOutput JSON. The "
                "target_paragraph_replacements array must contain corrected "
                "replacements for the failed target refs only. Do not rewrite "
                "successful refs. For failed required target spans, also return "
                "target_span_replacements keyed by target_span_ref with non-empty "
                "replacement_excerpt and matching before_text_sha256. The controller "
                "will merge successful first-attempt replacements with retry "
                "replacements and rerun full validation."
            ),
        }
    )


def _retry_failed_paragraph_spec(
    spec: dict[str, object],
    *,
    target_span_specs: list[dict[str, object]],
    retry_plan: TargetAddressedRetryPlan,
) -> dict[str, object]:
    ref = str(spec["target_paragraph_ref"])
    failed_span_set = set(retry_plan.failed_target_span_refs)
    return {
        "target_paragraph_ref": ref,
        "before_text": spec["before_text"],
        "before_text_sha256": spec["before_text_sha256"],
        "word_count": spec["word_count"],
        "active_target_ids": list(spec["active_target_ids"]),
        "material_active_target_ids_failed": list(
            retry_plan.failed_material_target_ids_by_ref.get(ref, [])
        ),
        "material_change_required": spec["material_change_required"],
        "transformation_instruction": spec["transformation_instruction"],
        "protected_effects": list(spec["protected_effects"]),
        "forbidden_failures": list(spec["forbidden_failures"]),
        "first_attempt_replacement_text": _first_attempt_replacement_text(
            retry_plan.first_attempt_payload,
            target_ref=ref,
        ),
        "failed_target_spans": [
            _retry_failed_span_spec(span_spec, retry_plan=retry_plan)
            for span_spec in target_span_specs
            if str(span_spec["parent_target_paragraph_ref"]) == ref
            and str(span_spec["target_span_ref"]) in failed_span_set
        ],
        "failure_reason": retry_plan.failure_reasons_by_ref.get(ref, ""),
    }


def _retry_failed_span_spec(
    spec: dict[str, object],
    *,
    retry_plan: TargetAddressedRetryPlan,
) -> dict[str, object]:
    span_ref = str(spec["target_span_ref"])
    return {
        "target_span_ref": span_ref,
        "parent_target_paragraph_ref": spec["parent_target_paragraph_ref"],
        "before_text": spec["before_text"],
        "before_text_sha256": spec["before_text_sha256"],
        "active_target_ids": list(spec["active_target_ids"]),
        "material_change_required": spec["material_change_required"],
        "allowed_operation": spec["allowed_operation"],
        "transformation_instruction": spec["transformation_instruction"],
        "first_attempt_replacement_paragraph": _first_attempt_replacement_text(
            retry_plan.first_attempt_payload,
            target_ref=str(spec["parent_target_paragraph_ref"]),
        ),
        "failure_reason": retry_plan.failure_reasons_by_span.get(span_ref, ""),
        "failed_active_targets": retry_plan.failed_active_targets_by_span.get(
            span_ref,
            [],
        ),
    }


def _retry_work_order(
    work_order: dict[str, object],
    *,
    failed_specs: list[dict[str, object]],
) -> dict[str, object]:
    retry_work_order = dict(work_order)
    retry_work_order["retry_scope"] = "failed_target_paragraph_refs_only"
    retry_work_order["target_paragraphs"] = failed_specs
    retry_work_order["model_must_not_touch_successful_refs"] = True
    return retry_work_order


def _successful_first_attempt_replacements(
    payload: dict[str, object] | None,
    *,
    failed_refs: set[str],
) -> list[dict[str, object]]:
    if not payload:
        return []
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        return []
    return [
        dict(item)
        for item in replacements
        if isinstance(item, dict)
        and str(item.get("target_paragraph_ref") or "") not in failed_refs
    ]


def _first_attempt_replacement_text(
    payload: dict[str, object] | None,
    *,
    target_ref: str,
) -> str | None:
    if not payload:
        return None
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        return None
    for item in replacements:
        if (
            isinstance(item, dict)
            and str(item.get("target_paragraph_ref") or "") == target_ref
        ):
            return str(item.get("replacement_text") or "")
    return None


def _write_model_tagged_artifact(
    *,
    connection: sqlite3.Connection,
    subject: MacroSubject,
    packet_dir: Path,
    result: ModelDriverResult,
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> ArtifactRecord:
    writer = PacketWriter(
        connection=connection,
        run_id=subject.run_id,
        packet_dir=packet_dir,
        lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        created_by=f"model_driver:{result.model_call.provider}:{result.model_call.model}",
        fixture_only=False,
        model_call_id=result.model_call.id,
    )
    return writer.write_artifact(artifact_type, payload, parent_ids=parent_ids)


def _link_model_result(
    *,
    connection: sqlite3.Connection,
    result: ModelDriverResult,
    parsed_artifact: ArtifactRecord,
) -> ModelDriverResult:
    linked_call = link_model_call_parsed_artifact(
        connection,
        model_call_id=result.model_call.id,
        parsed_output_artifact_id=parsed_artifact.id,
    )
    return ModelDriverResult(
        model_call=linked_call,
        parsed_payload=result.parsed_payload,
        parsed_artifact=parsed_artifact,
    )


def _failure_result(
    *,
    subject: MacroSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    model_results: list[ModelDriverResult],
    message: str,
    retry_report: dict[str, object] | None = None,
) -> BoundedMacroRecompositionResult:
    payload = {
        "accepted": False,
        "refused": True,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "synthesis_packet": str(subject.synthesis_packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "message": message,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    if retry_report is not None:
        payload["target_addressed_retry_report"] = retry_report
    return BoundedMacroRecompositionResult(
        exit_code=1,
        payload=payload,
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _model_failure_message(result: ModelDriverResult) -> str:
    detail = result.model_call.error_message or result.model_call.status
    return f"Bounded macro recomposition refused during live recomposition: {detail}"


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _build_subject_manifest(
    subject: MacroSubject,
    packet_dir: Path,
    *,
    client_name: str,
    max_model_calls: int,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "max_model_calls": max_model_calls,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_artifact_ids": subject.synthesis_artifact_ids,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_kind": subject.base_packet_kind,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_artifact_id": subject.base_candidate_artifact_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "base_candidate_word_count": subject.base_word_count,
        "base_from_synthesis_selected_best_candidate": True,
        "failed_pivot_packet_used_as_base": subject.base_packet_id == "packet_0022",
        "original_candidate_used_as_base": False,
        "packet_0030_used_as_base": subject.base_packet_id == "packet_0030",
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "reader_state_evidence_packet_id": subject.normalized_brief.reader_state_evidence_packet_id,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_subject_manifest_v1_controller",
    }


def _build_brief_ref(subject: MacroSubject) -> dict[str, object]:
    brief = subject.synthesis_payloads["macro_recomposition_brief"]
    return {
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "macro_recomposition_brief_artifact_id": subject.synthesis_artifact_ids.get(
            "macro_recomposition_brief"
        ),
        "brief_type": brief.get("brief_type"),
        "normalized_target_scope": subject.normalized_brief.target_scope,
        "normalized_target_movement": subject.normalized_brief.target_movement,
        "normalized_target_submovement": list(
            subject.normalized_brief.target_submovement
        ),
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "reader_state_evidence_packet_id": subject.normalized_brief.reader_state_evidence_packet_id,
        "target_region_or_movement": brief.get("target_region_or_movement"),
        "target_movement_or_submovement": list(
            brief.get("target_movement_or_submovement", [])
            if isinstance(brief.get("target_movement_or_submovement"), list)
            else []
        ),
        "allowed_scale": brief.get("allowed_scale"),
        "protected_effects_to_preserve": list(subject.normalized_brief.protected_effects),
        "forbidden_changes": list(subject.normalized_brief.forbidden_changes),
        "success_criteria": list(subject.normalized_brief.success_criteria),
        "active_transformation_target_ids": list(
            subject.normalized_brief.active_transformation_target_ids
        ),
        "ablation_plan_after_recomposition": list(
            brief.get("ablation_plan_after_recomposition", [])
        ),
        "not_candidate_artifact": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_brief_ref_v1_controller",
    }


def _build_work_order(subject: MacroSubject) -> dict[str, object]:
    target = _target_window(subject.base_text)
    target_paragraphs = _target_paragraph_specs(subject, target)
    target_spans = _target_span_specs(subject, target, target_paragraphs)
    return {
        "work_order_id": f"macro_recomposition_{subject.synthesis_packet_id}",
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "selected_reader_state_evidence_packet_id": (
            subject.normalized_brief.reader_state_evidence_packet_id
        ),
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "target_paragraph_start_index": target.target_start_index,
        "target_paragraph_end_index": target.target_end_index,
        "target_paragraphs": target_paragraphs,
        "target_spans": target_spans,
        "active_target_units": target_spans,
        "before_section_text": "\n\n".join(target.original_target),
        "selected_candidate_text": subject.base_text,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "allowed_touch": "multiple adjacent spans in the middle/return movement",
        "protected_semantic_constraints": _semantic_constraints(),
        "active_transformation_targets": _active_transformation_targets(subject, target),
        "protected_effects": list(subject.normalized_brief.protected_effects),
        "forbidden_changes": list(subject.normalized_brief.forbidden_changes),
        "reader_state_evidence_adjudication": subject.normalized_brief.source_reader_state_evidence,
        "reader_state_tension_report": subject.normalized_brief.source_reader_state_tensions,
        "controller_owns": [
            "source packet references",
            "base candidate text",
            "macro target spans",
            "before section text",
            "protected effects",
            "forbidden changes",
            "protected semantic constraints",
            "active transformation targets",
            "target coverage validation",
            "text assembly",
            "diff report",
            "gate report",
            "finalization status",
        ],
        "model_may_own_if_live_later": [
            "recomposition plan wording",
            "replacement section text",
            "rationale",
            "local-law explanation",
            "uncertainty",
            "predicted reader-state effect",
            "semantic constraint mapping",
            "active target mapping claims",
        ],
        "model_must_not_own": [
            "finalization fields",
            "gate pass/fail",
            "before text",
            "source packet IDs",
            "phase-shift claim",
            "unrestricted full rewrite authority",
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_work_order_v1_controller",
    }


def _build_protected_effects(subject: MacroSubject) -> dict[str, object]:
    protected = _unique(
        [
            *list(subject.normalized_brief.protected_effects),
            "table/dust/spoon/saucer local field",
            "proof from inside the line it integrates",
            "cosmic silence as isolation condition of proof",
            "return without regression",
            "strongest-rival pressure",
            "best current candidate's useful record/law/proof/answer compression",
        ]
    )
    forbidden = _unique(
        [
            *list(subject.normalized_brief.forbidden_changes),
            "rewriting the whole artifact",
            "thinning the opening scene",
            "repeating local record/law/proof/answer compression as the main move",
            "naming pressure more often instead of embodying pressure",
            "adding outside rescue",
            "weakening cosmic silence into mere lack of help",
            "marking final or phase-shift success",
        ]
    )
    return {
        "protected_effects": protected,
        "forbidden_changes": forbidden,
        "best_current_candidate_repair_preserved": True,
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "reader_state_evidence_packet_id": subject.normalized_brief.reader_state_evidence_packet_id,
        "strongest_rival_pressure_must_remain_active": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_recomposition_plan(
    subject: MacroSubject,
    *,
    model_payload: dict[str, object] | None = None,
    model_call_id: str | None = None,
) -> dict[str, object]:
    if model_payload is not None:
        plan = model_payload["macro_recomposition_plan"]
        if not isinstance(plan, dict):
            raise TypeError("macro_recomposition_plan must be an object")
        return {
            "plan_id": f"bounded_macro_plan_{sha256_text(subject.base_text)[:12]}",
            "target_movement": subject.normalized_brief.target_movement,
            "target_scope": subject.normalized_brief.target_scope,
            "target_submovement": list(subject.normalized_brief.target_submovement),
            "bounded_macro_recomposition": True,
            "full_rewrite": False,
            "plan_summary": plan["plan_summary"],
            "plan_steps": list(plan["plan_steps"]),
            "model_owned_fields": [
                "plan_summary",
                "plan_steps",
                "rationale",
                "local_law_explanation",
                "uncertainty",
                "predicted_reader_state_effect",
            ],
            "source_model_call_id": model_call_id,
            "rationale": model_payload["rationale"],
            "local_law_explanation": model_payload["local_law_explanation"],
            "uncertainty": model_payload["uncertainty"],
            "predicted_reader_state_effect": model_payload[
                "predicted_reader_state_effect"
            ],
            "not_finalization_eligible": True,
            "no_phase_shift_claim": True,
            "worker": "macro_recomposition_plan_v1_model_driver",
        }
    return {
        "plan_id": f"bounded_macro_plan_{sha256_text(subject.base_text)[:12]}",
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "plan_steps": _fake_plan_steps(subject),
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_plan_v1_fake_controller",
    }


def _fake_plan_steps(subject: MacroSubject) -> list[dict[str, object]]:
    if subject.normalized_brief.reader_state_informed:
        return [
            {
                "step_id": "macro_step_001",
                "action": "preserve the synthesis-selected macro candidate as base",
                "rationale": (
                    f"The synthesis selected {subject.base_packet_id}; the controller "
                    "must not fall back to an earlier local-patch candidate."
                ),
            },
            {
                "step_id": "macro_step_002",
                "action": "refine proof/no-outside-answer carry through local objects",
                "rationale": (
                    "Reader-state evidence says proof/no-answer logic remains partial "
                    "or thesis-visible."
                ),
            },
            {
                "step_id": "macro_step_003",
                "action": "strengthen the final return echo without weakening the opening",
                "rationale": (
                    "The opening became more necessary on reread, but the ending still "
                    "does not fully transform the opening."
                ),
            },
            {
                "step_id": "macro_step_004",
                "action": "preserve strongest-rival pressure for later testing",
                "rationale": (
                    "The strongest rival still blocks first-read vividness and lived "
                    "object-event pressure."
                ),
            },
        ]
    return [
        {
            "step_id": "macro_step_001",
            "action": "preserve opening scene and current useful compression",
            "rationale": (
                "The synthesis selected the current best candidate as the base."
            ),
        },
        {
            "step_id": "macro_step_002",
            "action": "replace the middle proof ladder with object/event sequence",
            "rationale": "The failed pivot showed pressure must be embodied rather than named.",
        },
        {
            "step_id": "macro_step_003",
            "action": "recompose return as record-bearing change, not explanatory closure",
            "rationale": "The return must carry contradiction internally.",
        },
        {
            "step_id": "macro_step_004",
            "action": "leave strongest-rival pressure unresolved and test later by executed ablation",
            "rationale": "No internal packet has closed rival pressure.",
        },
    ]


def _build_patch_or_section_plan(
    subject: MacroSubject,
    recomposed: RecomposedText,
    *,
    model_payload: dict[str, object] | None = None,
    model_call_id: str | None = None,
    retry_report: dict[str, object] | None = None,
) -> dict[str, object]:
    coverage_report = _build_target_coverage_report(
        subject,
        recomposed,
        recomposed.replacement,
        model_payload=model_payload,
    )
    payload = {
        "section_plan_id": f"macro_section_{sha256_text(''.join(recomposed.replacement))[:12]}",
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "target_paragraph_start_index": recomposed.target_start_index,
        "target_paragraph_end_index": recomposed.target_end_index,
        "unchanged_prefix_paragraph_count": len(recomposed.unchanged_prefix),
        "replacement_paragraph_count": len(recomposed.replacement),
        "changed_paragraph_count": coverage_report[
            "materially_changed_target_paragraph_count"
        ],
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "before_section_text": "\n\n".join(recomposed.original_target),
        "replacement_section_text": "\n\n".join(recomposed.replacement),
        "target_coverage_report": coverage_report,
        "source_base_text_sha256": subject.base_text_sha256,
        "target_addressed_retry_report": retry_report
        or _target_addressed_retry_report_not_attempted(),
        "rationale": (
            "Replace the middle/return movement as one adjacent bounded section, "
            "preserving the selected base opening and object field."
        ),
        "worker": "macro_patch_or_section_plan_v1_fake_controller",
    }
    if subject.normalized_brief.reader_state_informed:
        payload.update(
            {
                "target_paragraph_replacements": (
                    list(model_payload["target_paragraph_replacements"])
                    if model_payload is not None
                    else _controller_target_paragraph_replacements(subject, recomposed)
                ),
                "target_span_replacements": (
                    list(model_payload["target_span_replacements"])
                    if model_payload is not None
                    else _controller_target_span_replacements(subject, recomposed)
                ),
                "controller_assembled_from_target_paragraph_replacements": (
                    model_payload is not None
                ),
                "model_replacement_section_text_authoritative": False
                if model_payload is not None
                else None,
            }
        )
    if model_payload is not None:
        section_plan = model_payload["section_plan"]
        if not isinstance(section_plan, dict):
            raise TypeError("section_plan must be an object")
        payload.update(
            {
                "model_section_plan": section_plan,
                "constraint_mapping": list(model_payload["constraint_mapping"]),
                "active_target_mapping": list(model_payload["active_target_mapping"]),
                "semantic_constraint_claims_model_reported": True,
                "semantic_constraint_satisfaction_not_proven": True,
                "requires_internal_reader_or_ablation_validation": True,
                "source_model_call_id": model_call_id,
                "rationale": section_plan["rationale"],
                "worker": "macro_patch_or_section_plan_v1_model_driver",
            }
        )
    return payload


def _controller_target_paragraph_replacements(
    subject: MacroSubject,
    recomposed: RecomposedText,
) -> list[dict[str, object]]:
    specs = _target_paragraph_specs(subject, recomposed)
    replacements: list[dict[str, object]] = []
    for index, spec in enumerate(specs):
        replacement_text = (
            recomposed.replacement[index]
            if index < len(recomposed.replacement)
            else str(spec["before_text"])
        )
        replacements.append(
            {
                "target_paragraph_ref": spec["target_paragraph_ref"],
                "before_text_sha256": spec["before_text_sha256"],
                "replacement_text": replacement_text,
                "active_target_ids_covered": list(spec["active_target_ids"]),
                "material_change_summary": (
                    "controller-authored deterministic replacement for active targets"
                    if bool(spec["material_change_required"])
                    else "controller-authored preservation target"
                ),
                "preserved_effects": list(spec["protected_effects"]),
                "risk_notes": "fixture/fake target-addressed replacement; no improvement claim",
                "uncertainty": "requires executed ablation or internal reader-state testing",
            }
        )
    return replacements


def _controller_target_span_replacements(
    subject: MacroSubject,
    recomposed: RecomposedText,
) -> list[dict[str, object]]:
    target = _target_window(subject.base_text)
    paragraph_specs = _target_paragraph_specs(subject, target)
    span_specs = _target_span_specs(subject, target, paragraph_specs)
    replacement_by_parent = _replacement_paragraphs_by_ref(target, recomposed.replacement)
    replacements: list[dict[str, object]] = []
    for spec in span_specs:
        if not bool(spec["material_change_required"]):
            continue
        parent_ref = str(spec["parent_target_paragraph_ref"])
        replacements.append(
            {
                "target_span_ref": spec["target_span_ref"],
                "parent_target_paragraph_ref": parent_ref,
                "before_text_sha256": spec["before_text_sha256"],
                "replacement_excerpt": replacement_by_parent.get(parent_ref, ""),
                "active_target_ids_covered": list(spec["active_target_ids"]),
                "material_change_summary": (
                    "controller-authored deterministic span materiality mapping"
                ),
                "risk_notes": "fixture/fake span mapping; no improvement claim",
                "uncertainty": "requires executed ablation or internal reader-state testing",
            }
        )
    return replacements


def _build_recomposed_candidate(
    subject: MacroSubject,
    recomposed: RecomposedText,
    *,
    model_call_id: str | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": f"bounded_macro_recomposition_{sha256_text(recomposed.text)[:12]}",
        "text": recomposed.text,
        "text_sha256": sha256_text(recomposed.text),
        "word_count": len(_words(recomposed.text)),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "assembled_by_controller": True,
        "source_model_call_id": model_call_id,
        "candidate_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": subject.fixture_only if model_call_id is None else False,
        "requires_executed_ablation_before_improvement_claim": True,
        "worker": (
            "macro_recomposed_candidate_text_v1_controller_assembled_from_model"
            if model_call_id
            else "macro_recomposed_candidate_text_v1_fake_controller"
        ),
    }


def _build_diff_report(
    subject: MacroSubject,
    recomposed: RecomposedText,
    candidate: dict[str, object],
    *,
    model_payload: dict[str, object] | None = None,
    retry_report: dict[str, object] | None = None,
) -> dict[str, object]:
    coverage_report = _build_target_coverage_report(
        subject,
        recomposed,
        recomposed.replacement,
        model_payload=model_payload,
    )
    return {
        "base_candidate_packet_id": subject.base_packet_id,
        "base_text_sha256": subject.base_text_sha256,
        "revised_text_sha256": candidate["text_sha256"],
        "base_word_count": subject.base_word_count,
        "revised_word_count": candidate["word_count"],
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "opening_scene_preserved": True,
        "unchanged_prefix_paragraph_count": len(recomposed.unchanged_prefix),
        "target_coverage_report": coverage_report,
        "target_addressed_retry_report": retry_report
        or _target_addressed_retry_report_not_attempted(),
        "changed_paragraph_start_index": recomposed.target_start_index,
        "changed_paragraph_end_index": recomposed.target_end_index,
        "changed_spans": [
            {
                "changed_span_id": "macro_change_001",
                "movement": subject.normalized_brief.target_movement,
                "target_scope": subject.normalized_brief.target_scope,
                "before_text": "\n\n".join(recomposed.original_target),
                "after_text": "\n\n".join(recomposed.replacement),
                "operation_type": "bounded_section_recomposition",
                "inside_target": True,
                "rationale": "Turn proof/return explanation into object-event sequence.",
            }
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_diff_report_v1_controller",
    }


def _build_rival_pressure_check(
    subject: MacroSubject,
    candidate: dict[str, object],
) -> dict[str, object]:
    rival = subject.synthesis_payloads["rival_pressure_summary"]
    text = str(candidate["text"]).lower()
    object_terms = ["table", "dust", "spoon", "saucer", "ring"]
    return {
        "strongest_rival_present": bool(rival.get("strongest_rival_present")),
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "object_field_terms_preserved": [
            term for term in object_terms if term in text
        ],
        "current_candidate_closes_gap": False,
        "reason": (
            "The bounded recomposition preserves rival pressure for later testing; "
            "it does not claim to beat the strongest rival."
        ),
        "requires_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_rival_pressure_check_v1_controller",
    }


def _build_gate_report(
    *,
    subject: MacroSubject,
    subject_manifest: dict[str, object],
    protected_effects: dict[str, object],
    diff_report: dict[str, object],
    rival_check: dict[str, object],
    model_payload: dict[str, object] | None = None,
    retry_report: dict[str, object] | None = None,
) -> dict[str, object]:
    constraint_mapping_complete = bool(model_payload) and _constraint_mapping_complete(
        model_payload
    )
    coverage_report = diff_report.get("target_coverage_report", {})
    if not isinstance(coverage_report, dict):
        coverage_report = {}
    macro_target_coverage_passed = bool(
        coverage_report.get("macro_target_coverage_passed")
    )
    macro_materiality_passed = bool(coverage_report.get("macro_materiality_passed"))
    gate_results = [
        _gate_result("macro_recomposition_packet_exists", True),
        _gate_result("synthesis_packet_consumed", True),
        _gate_result(
            "best_candidate_used_as_base",
            subject_manifest["base_from_synthesis_selected_best_candidate"]
            and subject.base_packet_id != "packet_0022",
        ),
        _gate_result("macro_recomposition_bounded", bool(diff_report["bounded_macro_recomposition"])),
        _gate_result(
            "protected_effects_recorded",
            bool(protected_effects["protected_effects"])
            and bool(protected_effects["forbidden_changes"]),
        ),
        _gate_result(
            "rival_pressure_preserved",
            bool(rival_check["strongest_rival_pressure_preserved"]),
        ),
        _gate_result(
            "reader_state_informed_brief_consumed",
            True,
            [],
            record=subject.normalized_brief.reader_state_informed,
        ),
        _gate_result(
            "constraint_mapping_complete",
            constraint_mapping_complete if model_payload is not None else True,
        ),
        _gate_result("macro_target_coverage_passed", macro_target_coverage_passed),
        _gate_result("macro_materiality_passed", macro_materiality_passed),
        _gate_result(
            "semantic_constraint_satisfaction_proven",
            False,
            [
                "semantic constraint satisfaction is model-reported only and "
                "requires internal reader or executed ablation validation"
            ],
        ),
        _gate_result(
            "macro_recomposition_executed_ablation_completed",
            False,
            ["macro recomposition has not yet been tested by executed ablation"],
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            [
                "strongest-rival pressure remains blocking",
                "macro candidate requires executed ablation before any improvement claim",
            ],
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is intentionally absent"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    return {
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "non_final": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "strongest_rival_pressure_preserved": True,
        "reader_state_informed_brief_consumed": (
            subject.normalized_brief.reader_state_informed
        ),
        "target_scope": subject.normalized_brief.target_scope,
        "constraint_mapping_complete": (
            constraint_mapping_complete if model_payload is not None else True
        ),
        "semantic_constraint_mapping_complete": (
            constraint_mapping_complete if model_payload is not None else True
        ),
        "semantic_constraint_claims_model_reported": model_payload is not None,
        "semantic_constraint_satisfaction_not_proven": True,
        "requires_internal_reader_or_ablation_validation": True,
        "macro_target_coverage_passed": macro_target_coverage_passed,
        "macro_materiality_passed": macro_materiality_passed,
        "active_transformation_targets_covered": list(
            coverage_report.get("active_targets_covered", [])
        ),
        "active_transformation_targets_missing": list(
            coverage_report.get("active_targets_missing", [])
        ),
        "ready_for_executed_ablation": bool(
            coverage_report.get("ready_for_executed_ablation")
        ),
        "target_addressed_retry_report": retry_report
        or _target_addressed_retry_report_not_attempted(),
        "target_coverage_report": coverage_report,
        "requires_executed_ablation_before_improvement_claim": True,
        "operator_approval_absent": True,
        "profile": "autonomous_creative_candidate",
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            (
                "semantic constraint satisfaction is not proven by structural "
                "model-output validation"
            ),
            "macro recomposition has not yet been tested by executed ablation",
            "strongest-rival pressure remains blocking",
            "internal operator approval is absent",
        ],
        "summary_verdict": (
            "Bounded macro recomposition produced a candidate for later executed "
            "ablation, but it is not final and makes no improvement claim."
        ),
        "worker": "macro_recomposition_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: MacroSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    retry_report: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "model": model,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "diff_report_artifact_id": artifacts["macro_recomposition_diff_report"].id,
        "rival_pressure_check_artifact_id": artifacts["macro_rival_pressure_check"].id,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "target_coverage_report": payloads["macro_recomposition_diff_report"].get(
            "target_coverage_report"
        ),
        "target_addressed_retry_report": retry_report
        or _target_addressed_retry_report_not_attempted(),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_packet_v1_controller",
    }


def _fake_recompose_text(subject: MacroSubject) -> RecomposedText:
    target = _target_window(subject.base_text)
    replacement = (
        _fake_reader_state_macro_2_replacement()
        if subject.normalized_brief.reader_state_informed
        else _fake_macro_1_replacement()
    )
    text = "\n\n".join([*target.unchanged_prefix, *replacement])
    return RecomposedText(
        text=text,
        target_start_index=target.target_start_index,
        target_end_index=target.target_end_index,
        unchanged_prefix=target.unchanged_prefix,
        original_target=target.original_target,
        replacement=replacement,
    )


def _model_recompose_text(
    subject: MacroSubject,
    model_payload: dict[str, object],
) -> RecomposedText:
    target = _target_window(subject.base_text)
    if subject.normalized_brief.reader_state_informed:
        replacement = _target_addressed_replacement_paragraphs(subject, model_payload)
    else:
        replacement_text = str(model_payload["replacement_section_text"]).strip()
        replacement = _paragraphs(replacement_text)
    text = "\n\n".join([*target.unchanged_prefix, *replacement])
    return RecomposedText(
        text=text,
        target_start_index=target.target_start_index,
        target_end_index=target.target_end_index,
        unchanged_prefix=target.unchanged_prefix,
        original_target=target.original_target,
        replacement=replacement,
    )


def _target_window(base_text: str) -> RecomposedText:
    paragraphs = _paragraphs(base_text)
    start = _target_start(paragraphs)
    return RecomposedText(
        text=base_text,
        target_start_index=start,
        target_end_index=len(paragraphs),
        unchanged_prefix=paragraphs[:start],
        original_target=paragraphs[start:],
        replacement=[],
    )


def _semantic_constraints() -> list[dict[str, str]]:
    descriptions = {
        "proof_from_inside_line": (
            "Proof must arise endogenously from the line or object sequence it "
            "integrates, not from a summary pasted over it."
        ),
        "cosmic_silence_as_isolation_condition": (
            "Cosmic silence/no outside answer must function as the formal "
            "isolation condition of proof, not as mere mood."
        ),
        "return_without_regression": (
            "The return must bring the opening back changed, not regress to an "
            "untouched starting point."
        ),
        "no_outside_answer_or_rescue": (
            "The replacement must not solve the pressure by importing rescue, "
            "answer, proof, or permission from outside the local field."
        ),
        "strongest_rival_pressure": (
            "The replacement must preserve strongest-rival pressure rather than "
            "claiming victory over it."
        ),
        "table_dust_spoon_saucer_local_field": (
            "The domestic table/dust/spoon/saucer field must remain the local "
            "causal field."
        ),
        "record_law_proof_answer_compression_preserved": (
            "The useful record/law/proof/answer compression from the selected "
            "base must be preserved or explicitly transformed by the macro brief."
        ),
    }
    return [
        {"constraint_id": constraint_id, "description": descriptions[constraint_id]}
        for constraint_id in REQUIRED_SEMANTIC_CONSTRAINT_IDS
    ]


def _active_transformation_targets(
    subject: MacroSubject,
    target: RecomposedText,
) -> list[dict[str, object]]:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    target_ids = subject.normalized_brief.active_transformation_target_ids
    target_ref_by_id = _active_target_ref_map(paragraph_refs, target_ids)
    descriptions = _active_target_descriptions()
    return [
        {
            "target_id": target_id,
            "description": descriptions[target_id],
            "target_paragraph_ref": target_ref_by_id[target_id],
            "material_change_required": (
                target_id in subject.normalized_brief.material_required_target_ids
            ),
        }
        for target_id in target_ids
    ]


def _active_target_descriptions() -> dict[str, str]:
    return {
        "middle_abstraction_ladder_compression": (
            "Compress the middle abstraction ladder into embodied object/event "
            "pressure rather than repeating explanatory scaffolding."
        ),
        "proof_line_redundancy_cleanup": (
            "Clean up proof-line redundancy by making proof arise through the "
            "replacement movement instead of repeating the proof label."
        ),
        "no_outside_answer_pressure_preservation": (
            "Preserve no-outside-answer pressure as a formal condition in the "
            "target section, not as a stated mood."
        ),
        "final_return_closure_embodiment": (
            "Embody the return closure as changed local relation rather than a "
            "summarizing ending."
        ),
        "object_event_pressure_without_pressure_naming": (
            "Carry pressure through object/event relations without merely naming "
            "pressure more often."
        ),
        "proof_no_outside_answer_refinement": (
            "Make proof and no-outside-answer pressure occur through the local "
            "object sequence rather than through visible thesis language."
        ),
        "final_return_echo_reread_strength": (
            "Strengthen the final return so rereading the opening changes its "
            "necessity without claiming closure."
        ),
        "thesis_visible_proof_language_reduction": (
            "Reduce proof-language that reads as commentary while preserving "
            "the proof function."
        ),
        "opening_return_transformation_strengthening": (
            "Make the return echo the opening as altered local relation, not as "
            "a summary of the architecture."
        ),
        "preserve_reader_state_partial_gain": (
            "Preserve the macro candidate's partial reader-state gain and local "
            "causal field while addressing remaining blockers."
        ),
    }


def _target_paragraph_specs(
    subject: MacroSubject,
    target: RecomposedText,
) -> list[dict[str, object]]:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    target_ref_by_id = _active_target_ref_map(
        paragraph_refs,
        subject.normalized_brief.active_transformation_target_ids,
    )
    descriptions = _active_target_descriptions()
    active_ids_by_ref: dict[str, list[str]] = {ref: [] for ref in paragraph_refs}
    for target_id in subject.normalized_brief.active_transformation_target_ids:
        target_ref = target_ref_by_id[target_id]
        refs = paragraph_refs if target_ref == "target_section" else [target_ref]
        for ref in refs:
            active_ids_by_ref.setdefault(ref, []).append(target_id)

    specs: list[dict[str, object]] = []
    material_ids = set(subject.normalized_brief.material_required_target_ids)
    protected = list(subject.normalized_brief.protected_effects)
    forbidden = list(subject.normalized_brief.forbidden_changes)
    for index, before_text in enumerate(target.original_target):
        ref = paragraph_refs[index]
        active_ids = _unique(active_ids_by_ref.get(ref, []))
        material_change_required = any(target_id in material_ids for target_id in active_ids)
        instruction_parts = [
            descriptions[target_id]
            for target_id in active_ids
            if target_id in descriptions and target_id in material_ids
        ]
        if not instruction_parts:
            instruction_parts = [
                descriptions[target_id]
                for target_id in active_ids
                if target_id in descriptions
            ]
        specs.append(
            {
                "target_paragraph_ref": ref,
                "before_text": before_text,
                "before_text_sha256": sha256_text(before_text),
                "word_count": len(_words(before_text)),
                "active_target_ids": active_ids,
                "material_change_required": material_change_required,
                "transformation_instruction": " ".join(instruction_parts)
                or "Preserve this paragraph unless the controller assigned a material target.",
                "protected_effects": protected,
                "forbidden_failures": forbidden,
            }
        )
    return specs


def _target_span_specs(
    subject: MacroSubject,
    target: RecomposedText,
    paragraph_specs: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if not subject.normalized_brief.reader_state_informed:
        return []
    specs = paragraph_specs or _target_paragraph_specs(subject, target)
    descriptions = _active_target_descriptions()
    span_specs: list[dict[str, object]] = []
    for paragraph_spec in specs:
        parent_ref = str(paragraph_spec["target_paragraph_ref"])
        sentences = _sentence_like_spans(str(paragraph_spec["before_text"]))
        material_indexes = _material_span_indexes_for_paragraph(
            subject,
            parent_ref=parent_ref,
            sentences=sentences,
        )
        for index, before_text in enumerate(sentences):
            role = _target_span_role(
                subject,
                parent_ref=parent_ref,
                span_index=index,
                before_text=before_text,
                material_indexes=material_indexes,
            )
            active_ids = _target_span_active_ids(
                subject,
                parent_ref=parent_ref,
                role=role,
                paragraph_active_ids=_string_tuple(
                    paragraph_spec.get("active_target_ids")
                ),
            )
            material = index in material_indexes
            span_ref = _target_span_ref(parent_ref, index)
            span_specs.append(
                {
                    "target_span_ref": span_ref,
                    "parent_target_paragraph_ref": parent_ref,
                    "before_text": before_text,
                    "before_text_sha256": sha256_text(before_text),
                    "active_target_ids": list(active_ids),
                    "material_change_required": material,
                    "transformation_instruction": _target_span_instruction(
                        role=role,
                        active_ids=active_ids,
                        descriptions=descriptions,
                    ),
                    "protected_effects": list(paragraph_spec["protected_effects"]),
                    "forbidden_failures": list(paragraph_spec["forbidden_failures"]),
                    "allowed_operation": _target_span_allowed_operation(role, material),
                    "span_role": role,
                }
            )
    return span_specs


def _sentence_like_spans(text: str) -> list[str]:
    sentences: list[str] = []
    current: list[str] = []
    for character in text.strip():
        current.append(character)
        if character in ".!?":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    remainder = "".join(current).strip()
    if remainder:
        sentences.append(remainder)
    if not sentences and text.strip():
        sentences.append(text.strip())
    return _combine_proof_sentence_pair(sentences)


def _combine_proof_sentence_pair(sentences: list[str]) -> list[str]:
    combined: list[str] = []
    index = 0
    while index < len(sentences):
        sentence = sentences[index]
        next_sentence = sentences[index + 1] if index + 1 < len(sentences) else ""
        if (
            "if proof comes" in sentence.lower()
            and next_sentence.lower().startswith("it shows itself")
        ):
            combined.append(f"{sentence} {next_sentence}")
            index += 2
        else:
            combined.append(sentence)
            index += 1
    return combined


def _material_span_indexes_for_paragraph(
    subject: MacroSubject,
    *,
    parent_ref: str,
    sentences: list[str],
) -> set[int]:
    if (
        parent_ref != "target_p001"
        or "thesis_visible_proof_language_reduction"
        not in subject.normalized_brief.active_transformation_target_ids
    ):
        return set()
    thesis_indexes = [
        index
        for index, sentence in enumerate(sentences)
        if _is_thesis_framing_sentence(sentence)
    ]
    proof_indexes = [
        index for index, sentence in enumerate(sentences) if _is_proof_sentence(sentence)
    ]
    if not thesis_indexes:
        thesis_indexes = [
            index
            for index, sentence in enumerate(sentences)
            if not _is_proof_sentence(sentence)
        ][:1]
    if not proof_indexes and sentences:
        proof_indexes = [len(sentences) - 1]
    return set(thesis_indexes[:1] + proof_indexes[:1])


def _is_thesis_framing_sentence(sentence: str) -> bool:
    normalized = " ".join(_normalized_words(sentence))
    markers = (
        "deeper pattern",
        "easy to miss",
        "world does not become legible",
        "becomes legible",
        "carrying its own contradiction",
        "strain works through",
        "named as record law proof answer",
    )
    return any(marker in normalized for marker in markers)


def _is_proof_sentence(sentence: str) -> bool:
    normalized = " ".join(_normalized_words(sentence))
    return "proof" in normalized or "proves" in normalized


def _target_span_role(
    subject: MacroSubject,
    *,
    parent_ref: str,
    span_index: int,
    before_text: str,
    material_indexes: set[int],
) -> str:
    if (
        subject.normalized_brief.reader_state_informed
        and parent_ref == "target_p001"
        and span_index in material_indexes
    ):
        if _is_proof_sentence(before_text):
            return "proof_sentence"
        return "thesis_frame"
    return "context_or_preserve"


def _target_span_active_ids(
    subject: MacroSubject,
    *,
    parent_ref: str,
    role: str,
    paragraph_active_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if (
        subject.normalized_brief.reader_state_informed
        and parent_ref == "target_p001"
        and role in {"thesis_frame", "proof_sentence", "context_or_preserve"}
        and "thesis_visible_proof_language_reduction"
        in subject.normalized_brief.active_transformation_target_ids
    ):
        return ("thesis_visible_proof_language_reduction",)
    return paragraph_active_ids


def _target_span_instruction(
    *,
    role: str,
    active_ids: tuple[str, ...],
    descriptions: dict[str, str],
) -> str:
    if role == "thesis_frame":
        return (
            "Remove or compress visible thesis framing into a local object/event "
            "sequence; do not preserve this sentence unchanged."
        )
    if role == "proof_sentence":
        return (
            "Tighten or relocate proof language so proof occurs through the object "
            "sequence rather than commentary over the scene."
        )
    parts = [descriptions[target_id] for target_id in active_ids if target_id in descriptions]
    return " ".join(parts) or "Preserve unless another controller target requires change."


def _target_span_allowed_operation(role: str, material: bool) -> str:
    if role == "thesis_frame":
        return "remove_thesis_frame"
    if role == "proof_sentence":
        return "relocate_to_object_sequence"
    return "compress" if material else "preserve_only"


def _target_span_ref(parent_ref: str, index: int) -> str:
    return f"{parent_ref}_s{index + 1:03d}"


def _collect_live_macro_validation_result(
    *,
    subject: MacroSubject,
    payload: dict[str, object],
) -> MacroTargetValidationResult:
    target = _target_window(subject.base_text)
    fatal_failures: list[str] = []
    paragraph_failures: dict[str, dict[str, object]] = {}
    span_failures: dict[str, dict[str, object]] = {}
    replacement_paragraphs: tuple[str, ...] = ()
    target_coverage_report: dict[str, object] = {}

    for validator in (
        lambda: _validate_section_plan(subject, payload),
        lambda: _validate_constraint_mapping(payload),
        lambda: _validate_active_target_mapping(
            payload,
            subject.normalized_brief.active_transformation_target_ids,
        ),
        lambda: _validate_forbidden_live_macro_claims(payload),
    ):
        try:
            validator()
        except ModelValidationError as error:
            fatal_failures.append(str(error))

    if not fatal_failures:
        replacement_paragraphs = _collect_target_paragraph_failures(
            subject=subject,
            target=target,
            payload=payload,
            paragraph_failures=paragraph_failures,
            fatal_failures=fatal_failures,
        )

    if not fatal_failures:
        try:
            _validate_replacement_text(subject, "\n\n".join(replacement_paragraphs))
        except ModelValidationError as error:
            fatal_failures.append(str(error))

    if not fatal_failures:
        target_coverage_report = _build_target_coverage_report(
            subject,
            target,
            list(replacement_paragraphs),
            model_payload=payload,
        )
        _collect_span_failures_from_report(
            subject=subject,
            target=target,
            replacement_paragraphs=list(replacement_paragraphs),
            payload=payload,
            paragraph_failures=paragraph_failures,
            span_failures=span_failures,
        )
        _collect_paragraph_coverage_failures(
            subject=subject,
            target=target,
            target_coverage_report=target_coverage_report,
            paragraph_failures=paragraph_failures,
        )

    return _macro_target_validation_result(
        subject=subject,
        target=target,
        replacement_paragraphs=replacement_paragraphs,
        paragraph_failures=paragraph_failures,
        span_failures=span_failures,
        target_coverage_report=target_coverage_report,
        fatal_failures=tuple(fatal_failures),
    )


def _collect_target_paragraph_failures(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    payload: dict[str, object],
    paragraph_failures: dict[str, dict[str, object]],
    fatal_failures: list[str],
) -> tuple[str, ...]:
    specs = _target_paragraph_specs(subject, target)
    spec_by_ref = {str(spec["target_paragraph_ref"]): spec for spec in specs}
    material_ids = set(subject.normalized_brief.material_required_target_ids)
    material_refs = {
        str(spec["target_paragraph_ref"])
        for spec in specs
        if bool(spec["material_change_required"])
    }
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        fatal_failures.append(
            "target_paragraph_replacements is required for reader_state_informed_macro_2"
        )
        return tuple(target.original_target)

    seen_refs: dict[str, dict[str, object]] = {}
    covered_material_targets: set[str] = set()
    for item in replacements:
        if not isinstance(item, dict):
            fatal_failures.append("target_paragraph_replacements entries must be objects")
            continue
        ref = str(item.get("target_paragraph_ref") or "")
        if ref not in spec_by_ref:
            fatal_failures.append(f"unsupported target_paragraph_ref: {ref}")
            continue
        spec = spec_by_ref[ref]
        material_target_ids = _material_target_ids_for_paragraph(subject, spec)
        if ref in seen_refs:
            _add_paragraph_failure(
                paragraph_failures,
                ref,
                f"duplicate target_paragraph_ref: {ref}",
                material_target_ids=material_target_ids,
            )
            continue
        seen_refs[ref] = item

        before_hash = str(item.get("before_text_sha256") or "")
        if before_hash != spec["before_text_sha256"]:
            _add_paragraph_failure(
                paragraph_failures,
                ref,
                f"target_paragraph_replacements[{ref}] before_text_sha256 mismatch",
                material_target_ids=material_target_ids,
            )
        replacement_text = str(item.get("replacement_text") or "").strip()
        if not replacement_text:
            _add_paragraph_failure(
                paragraph_failures,
                ref,
                f"target_paragraph_replacements[{ref}] replacement_text is empty",
                material_target_ids=material_target_ids,
            )
            continue
        active_ids_covered = _string_tuple(item.get("active_target_ids_covered"))
        allowed_target_ids = set(_string_tuple(spec.get("active_target_ids")))
        unsupported = sorted(set(active_ids_covered) - allowed_target_ids)
        if unsupported:
            _add_paragraph_failure(
                paragraph_failures,
                ref,
                "target_paragraph_replacements["
                f"{ref}] covers unassigned active target IDs: "
                + ", ".join(unsupported),
                material_target_ids=material_target_ids,
            )
        before_words = _normalized_words(str(spec["before_text"]))
        after_words = _normalized_words(replacement_text)
        materially_changed = _materially_changed_words(before_words, after_words)
        if bool(spec["material_change_required"]) and not materially_changed:
            required_ids = sorted(allowed_target_ids & material_ids)
            _add_paragraph_failure(
                paragraph_failures,
                ref,
                "target_paragraph_replacements["
                f"{ref}] copied or insufficiently changed for material targets: "
                + ", ".join(required_ids),
                material_target_ids=required_ids,
            )
        if materially_changed:
            covered_material_targets.update(
                target_id for target_id in active_ids_covered if target_id in material_ids
            )

    missing_refs = sorted(material_refs - set(seen_refs))
    for ref in missing_refs:
        _add_paragraph_failure(
            paragraph_failures,
            ref,
            f"missing target paragraph replacement: {ref}",
            material_target_ids=_material_target_ids_for_paragraph(
                subject,
                spec_by_ref[ref],
            ),
        )

    missing_targets = sorted(material_ids - covered_material_targets)
    for target_id in missing_targets:
        for ref in _refs_for_material_target_ids(subject, (target_id,)):
            if ref in spec_by_ref:
                _add_paragraph_failure(
                    paragraph_failures,
                    ref,
                    "target paragraph replacements do not cover material "
                    f"active targets: {target_id}",
                    material_target_ids=(target_id,),
                )

    paragraph_refs = _target_paragraph_refs(target.original_target)
    return tuple(
        str(seen_refs[ref]["replacement_text"]).strip()
        if ref in seen_refs and str(seen_refs[ref].get("replacement_text") or "").strip()
        else str(spec_by_ref[ref]["before_text"])
        for ref in paragraph_refs
    )


def _collect_span_failures_from_report(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    replacement_paragraphs: list[str],
    payload: dict[str, object],
    paragraph_failures: dict[str, dict[str, object]],
    span_failures: dict[str, dict[str, object]],
) -> None:
    report = _build_target_span_coverage_report(
        subject,
        target,
        replacement_paragraphs,
        model_payload=payload,
    )
    span_specs = _target_span_specs(subject, target)
    span_by_ref = {str(spec["target_span_ref"]): spec for spec in span_specs}

    for span_ref in report.get("missing_target_span_replacements", []):
        _add_span_failure(
            subject,
            span_by_ref,
            paragraph_failures,
            span_failures,
            str(span_ref),
            "missing target span replacement",
        )
    for span_ref in report.get("hash_mismatched_target_span_replacements", []):
        _add_span_failure(
            subject,
            span_by_ref,
            paragraph_failures,
            span_failures,
            str(span_ref),
            "target span before_text_sha256 mismatch",
        )
    for span_ref in report.get("empty_target_span_replacement_excerpts", []):
        _add_span_failure(
            subject,
            span_by_ref,
            paragraph_failures,
            span_failures,
            str(span_ref),
            "target span replacement_excerpt is empty",
        )
    for span_ref, target_ids in dict(
        report.get("unsupported_active_targets_by_span", {})
    ).items():
        _add_span_failure(
            subject,
            span_by_ref,
            paragraph_failures,
            span_failures,
            str(span_ref),
            "target span covers unassigned active target IDs: "
            + ", ".join(_string_tuple(target_ids)),
            active_target_ids=_string_tuple(target_ids),
        )
    for span_ref, target_ids in dict(
        report.get("missing_active_targets_by_span", {})
    ).items():
        _add_span_failure(
            subject,
            span_by_ref,
            paragraph_failures,
            span_failures,
            str(span_ref),
            "target span does not cover material active targets: "
            + ", ".join(_string_tuple(target_ids)),
            active_target_ids=_string_tuple(target_ids),
        )
    failed_active_targets = dict(report.get("failed_active_targets_by_span", {}))
    for span_ref in report.get("failed_target_span_refs", []):
        _add_span_failure(
            subject,
            span_by_ref,
            paragraph_failures,
            span_failures,
            str(span_ref),
            "target span coverage failed: " + str(span_ref),
            active_target_ids=_string_tuple(failed_active_targets.get(span_ref, [])),
        )


def _collect_paragraph_coverage_failures(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    target_coverage_report: dict[str, object],
    paragraph_failures: dict[str, dict[str, object]],
) -> None:
    spec_by_ref = {
        str(spec["target_paragraph_ref"]): spec
        for spec in _target_paragraph_specs(subject, target)
    }
    for target_id in _string_tuple(target_coverage_report.get("active_targets_missing")):
        for ref in _refs_for_material_target_ids(subject, (target_id,)):
            if ref in spec_by_ref:
                _add_paragraph_failure(
                    paragraph_failures,
                    ref,
                    f"macro target coverage failed: {target_id}",
                    material_target_ids=(target_id,),
                )
    if not bool(target_coverage_report.get("macro_materiality_passed", True)):
        unchanged_refs = {
            str(row["target_paragraph_ref"])
            for row in target_coverage_report.get("paragraph_comparison", [])
            if isinstance(row, dict) and not bool(row.get("materially_changed"))
        }
        for ref, spec in spec_by_ref.items():
            if ref in unchanged_refs and bool(spec.get("material_change_required")):
                _add_paragraph_failure(
                    paragraph_failures,
                    ref,
                    "macro materiality failed: target section is insufficiently changed",
                    material_target_ids=_material_target_ids_for_paragraph(
                        subject,
                        spec,
                    ),
                )


def _macro_target_validation_result(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    replacement_paragraphs: tuple[str, ...],
    paragraph_failures: dict[str, dict[str, object]],
    span_failures: dict[str, dict[str, object]],
    target_coverage_report: dict[str, object],
    fatal_failures: tuple[str, ...],
) -> MacroTargetValidationResult:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    failed_paragraph_refs = tuple(ref for ref in paragraph_refs if ref in paragraph_failures)
    span_refs = [
        str(spec["target_span_ref"]) for spec in _target_span_specs(subject, target)
    ]
    failed_span_refs = tuple(ref for ref in span_refs if ref in span_failures)
    failure_reasons_by_ref = {
        ref: "; ".join(_string_tuple(paragraph_failures[ref].get("reasons")))
        for ref in failed_paragraph_refs
    }
    failure_reasons_by_span = {
        ref: "; ".join(_string_tuple(span_failures[ref].get("reasons")))
        for ref in failed_span_refs
    }
    failed_material_target_ids_by_ref = {
        ref: list(_string_tuple(paragraph_failures[ref].get("material_target_ids")))
        for ref in failed_paragraph_refs
    }
    failed_active_targets_by_span = {
        ref: list(_string_tuple(span_failures[ref].get("active_target_ids")))
        for ref in failed_span_refs
    }
    paragraph_records = tuple(
        {
            "target_paragraph_ref": ref,
            "reasons": list(_string_tuple(paragraph_failures[ref].get("reasons"))),
            "material_target_ids": failed_material_target_ids_by_ref.get(ref, []),
        }
        for ref in failed_paragraph_refs
    )
    span_records = tuple(
        {
            "target_span_ref": ref,
            "parent_target_paragraph_ref": span_failures[ref].get(
                "parent_target_paragraph_ref",
                "",
            ),
            "reasons": list(_string_tuple(span_failures[ref].get("reasons"))),
            "active_target_ids": failed_active_targets_by_span.get(ref, []),
        }
        for ref in failed_span_refs
    )
    message = _macro_target_validation_message(
        fatal_failures=fatal_failures,
        failure_reasons_by_ref=failure_reasons_by_ref,
        failure_reasons_by_span=failure_reasons_by_span,
    )
    passed = (
        not fatal_failures
        and not failed_paragraph_refs
        and not failed_span_refs
        and bool(target_coverage_report.get("macro_target_coverage_passed", True))
        and bool(target_coverage_report.get("macro_materiality_passed", True))
    )
    return MacroTargetValidationResult(
        passed=passed,
        replacement_paragraphs=replacement_paragraphs,
        paragraph_failures=paragraph_records,
        span_failures=span_records,
        failed_target_paragraph_refs=failed_paragraph_refs,
        failed_target_span_refs=failed_span_refs,
        failed_material_target_ids_by_ref=failed_material_target_ids_by_ref,
        failed_active_targets_by_span=failed_active_targets_by_span,
        failure_reasons_by_ref=failure_reasons_by_ref,
        failure_reasons_by_span=failure_reasons_by_span,
        target_coverage_report=target_coverage_report,
        fatal_failures=fatal_failures,
        message=message,
    )


def _macro_target_validation_message(
    *,
    fatal_failures: tuple[str, ...],
    failure_reasons_by_ref: dict[str, str],
    failure_reasons_by_span: dict[str, str],
) -> str:
    if fatal_failures:
        return "; ".join(fatal_failures)
    parts: list[str] = []
    if failure_reasons_by_ref:
        parts.append(
            "target paragraph validation failed: "
            + "; ".join(failure_reasons_by_ref.values())
        )
    if failure_reasons_by_span:
        parts.append(
            "target span validation failed: "
            + "; ".join(failure_reasons_by_span.values())
        )
    return "; ".join(parts) or "target validation passed"


def _add_paragraph_failure(
    failures: dict[str, dict[str, object]],
    ref: str,
    reason: str,
    *,
    material_target_ids: tuple[str, ...] | list[str] = (),
) -> None:
    row = failures.setdefault(
        ref,
        {
            "target_paragraph_ref": ref,
            "reasons": [],
            "material_target_ids": [],
        },
    )
    reasons = row["reasons"]
    if isinstance(reasons, list) and reason not in reasons:
        reasons.append(reason)
    existing_ids = row["material_target_ids"]
    if isinstance(existing_ids, list):
        for target_id in material_target_ids:
            if target_id not in existing_ids:
                existing_ids.append(str(target_id))


def _add_span_failure(
    subject: MacroSubject,
    span_by_ref: dict[str, dict[str, object]],
    paragraph_failures: dict[str, dict[str, object]],
    span_failures: dict[str, dict[str, object]],
    span_ref: str,
    reason: str,
    *,
    active_target_ids: tuple[str, ...] = (),
) -> None:
    spec = span_by_ref.get(span_ref)
    if spec is None:
        return
    parent_ref = str(spec["parent_target_paragraph_ref"])
    ids = active_target_ids or _string_tuple(spec.get("active_target_ids"))
    row = span_failures.setdefault(
        span_ref,
        {
            "target_span_ref": span_ref,
            "parent_target_paragraph_ref": parent_ref,
            "reasons": [],
            "active_target_ids": [],
        },
    )
    reasons = row["reasons"]
    if isinstance(reasons, list) and reason not in reasons:
        reasons.append(reason)
    existing_ids = row["active_target_ids"]
    if isinstance(existing_ids, list):
        for target_id in ids:
            if target_id not in existing_ids:
                existing_ids.append(str(target_id))
    _add_paragraph_failure(
        paragraph_failures,
        parent_ref,
        f"target span failure: {reason}",
        material_target_ids=[
            target_id
            for target_id in ids
            if target_id in subject.normalized_brief.material_required_target_ids
        ],
    )


def _material_target_ids_for_paragraph(
    subject: MacroSubject,
    spec: dict[str, object],
) -> tuple[str, ...]:
    material_ids = set(subject.normalized_brief.material_required_target_ids)
    return tuple(
        target_id
        for target_id in _string_tuple(spec.get("active_target_ids"))
        if target_id in material_ids
    )


def _target_addressed_retry_plan_from_failure(
    *,
    subject: MacroSubject,
    result: ModelDriverResult,
) -> TargetAddressedRetryPlan:
    empty = TargetAddressedRetryPlan(
        retryable=False,
        first_attempt_payload=None,
        retry_reason="not a retryable target-addressed macro-2 failure",
        failed_target_paragraph_refs=(),
        failed_target_span_refs=(),
        failure_reasons_by_ref={},
        failure_reasons_by_span={},
        failed_material_target_ids_by_ref={},
        failed_active_targets_by_span={},
        first_failure_message=result.model_call.error_message or result.model_call.status,
    )
    if not subject.normalized_brief.reader_state_informed:
        return empty
    if result.model_call.status != MODEL_CALL_VALIDATION_FAILED:
        return TargetAddressedRetryPlan(
            **{
                **empty.__dict__,
                "retry_reason": "model call did not produce a controller validation failure",
            }
        )
    error_message = result.model_call.error_message or ""
    first_payload = _schema_parsed_payload_from_model_result(result)
    if first_payload is None:
        return TargetAddressedRetryPlan(
            **{
                **empty.__dict__,
                "retry_reason": "first attempt output was not schema-parseable",
            }
        )
    validation_result = _collect_live_macro_validation_result(
        subject=subject,
        payload=first_payload,
    )
    if validation_result.fatal_failures:
        return TargetAddressedRetryPlan(
            **{
                **empty.__dict__,
                "retry_reason": (
                    "failure was fatal and not target-address retryable: "
                    + validation_result.message
                ),
            }
        )
    if not validation_result.failed_target_paragraph_refs:
        return TargetAddressedRetryPlan(
            **{
                **empty.__dict__,
                "retry_reason": "failure was not target paragraph materiality or coverage",
            }
        )
    return TargetAddressedRetryPlan(
        retryable=True,
        first_attempt_payload=first_payload,
        retry_reason="target paragraph corrective retry",
        failed_target_paragraph_refs=validation_result.failed_target_paragraph_refs,
        failed_target_span_refs=validation_result.failed_target_span_refs,
        failure_reasons_by_ref=validation_result.failure_reasons_by_ref,
        failure_reasons_by_span=validation_result.failure_reasons_by_span,
        failed_material_target_ids_by_ref=(
            validation_result.failed_material_target_ids_by_ref
        ),
        failed_active_targets_by_span=validation_result.failed_active_targets_by_span,
        first_failure_message=error_message,
    )


def _schema_parsed_payload_from_model_result(
    result: ModelDriverResult,
) -> dict[str, object] | None:
    raw_output_path = Path(result.model_call.raw_output_path)
    try:
        raw_output = raw_output_path.read_text(encoding="utf-8")
        return parse_and_validate_structured_output(
            raw_output,
            BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        )
    except (OSError, ModelValidationError):
        return None


def _retryable_failed_refs_from_error(
    subject: MacroSubject,
    error_message: str,
) -> tuple[str, ...]:
    target = _target_window(subject.base_text)
    specs = _target_paragraph_specs(subject, target)
    material_refs = {
        str(spec["target_paragraph_ref"])
        for spec in specs
        if bool(spec["material_change_required"])
    }
    if error_message.startswith("missing target paragraph replacement: "):
        return tuple(
            ref
            for ref in _split_suffix_values(
                error_message,
                "missing target paragraph replacement: ",
            )
            if ref in material_refs
        )
    if "copied or insufficiently changed" in error_message:
        ref = _target_ref_from_bracketed_error(error_message)
        return (ref,) if ref in material_refs else ()
    if error_message.startswith(
        "target paragraph replacements do not cover material active targets: "
    ):
        target_ids = _split_suffix_values(
            error_message,
            "target paragraph replacements do not cover material active targets: ",
        )
        return _refs_for_material_target_ids(subject, target_ids)
    if error_message.startswith("macro target coverage failed: "):
        target_ids = _split_suffix_values(error_message, "macro target coverage failed: ")
        return _refs_for_material_target_ids(subject, target_ids)
    if error_message.startswith("target span coverage failed: "):
        span_refs = _split_suffix_values(error_message, "target span coverage failed: ")
        return _parent_refs_for_target_span_refs(subject, span_refs)
    if error_message.startswith("missing target span replacement: "):
        span_refs = _split_suffix_values(
            error_message,
            "missing target span replacement: ",
        )
        return _parent_refs_for_target_span_refs(subject, span_refs)
    if error_message.startswith("target_span_replacements["):
        span_ref = _target_ref_from_bracketed_error(
            error_message,
            prefix="target_span_replacements[",
        )
        return _parent_refs_for_target_span_refs(subject, (span_ref,))
    if error_message.startswith("macro materiality failed: "):
        return tuple(sorted(material_refs))
    return ()


def _target_ref_from_bracketed_error(
    error_message: str,
    *,
    prefix: str = "target_paragraph_replacements[",
) -> str:
    start = error_message.find(prefix)
    if start < 0:
        return ""
    start += len(prefix)
    end = error_message.find("]", start)
    if end < 0:
        return ""
    return error_message[start:end]


def _split_suffix_values(error_message: str, prefix: str) -> tuple[str, ...]:
    if not error_message.startswith(prefix):
        return ()
    return tuple(
        value.strip()
        for value in error_message[len(prefix) :].split(",")
        if value.strip()
    )


def _refs_for_material_target_ids(
    subject: MacroSubject,
    target_ids: tuple[str, ...],
) -> tuple[str, ...]:
    target = _target_window(subject.base_text)
    paragraph_refs = _target_paragraph_refs(target.original_target)
    ref_by_id = _active_target_ref_map(
        paragraph_refs,
        subject.normalized_brief.active_transformation_target_ids,
    )
    refs: list[str] = []
    for target_id in target_ids:
        if target_id not in subject.normalized_brief.material_required_target_ids:
            continue
        target_ref = ref_by_id.get(target_id)
        if target_ref == "target_section":
            refs.extend(paragraph_refs)
        elif target_ref:
            refs.append(target_ref)
    return tuple(_unique(refs))


def _parent_refs_for_target_span_refs(
    subject: MacroSubject,
    span_refs: tuple[str, ...],
) -> tuple[str, ...]:
    target = _target_window(subject.base_text)
    span_specs = _target_span_specs(subject, target)
    parent_by_span = {
        str(spec["target_span_ref"]): str(spec["parent_target_paragraph_ref"])
        for spec in span_specs
    }
    refs = [
        parent_by_span[span_ref]
        for span_ref in span_refs
        if span_ref in parent_by_span
    ]
    return tuple(_unique(refs))


def _failed_target_span_refs_from_error(
    subject: MacroSubject,
    error_message: str,
) -> tuple[str, ...]:
    target = _target_window(subject.base_text)
    valid_refs = {
        str(spec["target_span_ref"])
        for spec in _target_span_specs(subject, target)
        if bool(spec["material_change_required"])
    }
    if error_message.startswith("target span coverage failed: "):
        return tuple(
            ref
            for ref in _split_suffix_values(
                error_message,
                "target span coverage failed: ",
            )
            if ref in valid_refs
        )
    if error_message.startswith("missing target span replacement: "):
        return tuple(
            ref
            for ref in _split_suffix_values(
                error_message,
                "missing target span replacement: ",
            )
            if ref in valid_refs
        )
    if error_message.startswith("target_span_replacements["):
        ref = _target_ref_from_bracketed_error(
            error_message,
            prefix="target_span_replacements[",
        )
        return (ref,) if ref in valid_refs else ()
    return ()


def _failure_reasons_by_ref(
    subject: MacroSubject,
    *,
    failed_refs: tuple[str, ...],
    error_message: str,
) -> dict[str, str]:
    material_ids_by_ref = _failed_material_target_ids_by_ref(
        subject,
        failed_refs=failed_refs,
        error_message=error_message,
    )
    reasons: dict[str, str] = {}
    for ref in failed_refs:
        ids = material_ids_by_ref.get(ref, [])
        if error_message.startswith("missing target paragraph replacement: "):
            reasons[ref] = "missing target paragraph replacement"
        elif "copied or insufficiently changed" in error_message:
            reasons[ref] = "copied or insufficiently materially changed paragraph"
        elif ids:
            reasons[ref] = "material active targets not covered: " + ", ".join(ids)
        else:
            reasons[ref] = error_message
    return reasons


def _failure_reasons_by_span(
    subject: MacroSubject,
    *,
    failed_span_refs: tuple[str, ...],
    error_message: str,
) -> dict[str, str]:
    _ = subject
    reasons: dict[str, str] = {}
    for span_ref in failed_span_refs:
        if error_message.startswith("missing target span replacement: "):
            reasons[span_ref] = "missing target span replacement"
        elif "before_text_sha256 mismatch" in error_message:
            reasons[span_ref] = "target span before_text_sha256 mismatch"
        elif "target span coverage failed" in error_message:
            reasons[span_ref] = (
                "required target span was copied or insufficiently mapped"
            )
        else:
            reasons[span_ref] = error_message
    return reasons


def _failed_active_targets_by_span(
    subject: MacroSubject,
    *,
    failed_span_refs: tuple[str, ...],
) -> dict[str, list[str]]:
    target = _target_window(subject.base_text)
    span_specs = _target_span_specs(subject, target)
    result: dict[str, list[str]] = {}
    for spec in span_specs:
        span_ref = str(spec["target_span_ref"])
        if span_ref in failed_span_refs:
            result[span_ref] = list(_string_tuple(spec.get("active_target_ids")))
    return result


def _failed_material_target_ids_by_ref(
    subject: MacroSubject,
    *,
    failed_refs: tuple[str, ...],
    error_message: str,
) -> dict[str, list[str]]:
    target = _target_window(subject.base_text)
    specs = _target_paragraph_specs(subject, target)
    material_ids = set(subject.normalized_brief.material_required_target_ids)
    explicit_ids: tuple[str, ...] = ()
    if "material targets: " in error_message:
        explicit_ids = _split_suffix_values(
            error_message,
            error_message.split("material targets: ", 1)[0] + "material targets: ",
        )
    elif "material active targets: " in error_message:
        explicit_ids = _split_suffix_values(
            error_message,
            error_message.split("material active targets: ", 1)[0]
            + "material active targets: ",
        )
    elif "macro target coverage failed: " in error_message:
        explicit_ids = _split_suffix_values(error_message, "macro target coverage failed: ")

    result: dict[str, list[str]] = {}
    for spec in specs:
        ref = str(spec["target_paragraph_ref"])
        if ref not in failed_refs:
            continue
        active_ids = [
            target_id
            for target_id in _string_tuple(spec.get("active_target_ids"))
            if target_id in material_ids
        ]
        if explicit_ids:
            scoped = [target_id for target_id in active_ids if target_id in explicit_ids]
            result[ref] = scoped or active_ids
        else:
            result[ref] = active_ids
    return result


def _validate_live_macro_retry_payload(
    *,
    subject: MacroSubject,
    payload: dict[str, object],
    failed_refs: tuple[str, ...],
) -> None:
    _validate_section_plan(subject, payload)
    _validate_constraint_mapping(payload)
    _validate_active_target_mapping(
        payload,
        subject.normalized_brief.active_transformation_target_ids,
    )
    _validate_forbidden_live_macro_claims(payload)
    _validate_retry_target_replacements(
        subject=subject,
        payload=payload,
        failed_refs=failed_refs,
    )


def _validate_retry_target_replacements(
    *,
    subject: MacroSubject,
    payload: dict[str, object],
    failed_refs: tuple[str, ...],
) -> None:
    target = _target_window(subject.base_text)
    specs = _target_paragraph_specs(subject, target)
    spec_by_ref = {str(spec["target_paragraph_ref"]): spec for spec in specs}
    failed_ref_set = set(failed_refs)
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        raise ModelValidationError(
            "target_paragraph_replacements is required for corrective retry"
        )
    retry_by_ref = {
        str(item.get("target_paragraph_ref") or ""): item
        for item in replacements
        if isinstance(item, dict)
        and str(item.get("target_paragraph_ref") or "") in failed_ref_set
    }
    missing = sorted(failed_ref_set - set(retry_by_ref))
    if missing:
        raise ModelValidationError(
            "corrective retry missing target paragraph replacement: "
            + ", ".join(missing)
        )
    material_ids = set(subject.normalized_brief.material_required_target_ids)
    for ref in failed_refs:
        item = retry_by_ref[ref]
        spec = spec_by_ref[ref]
        before_hash = str(item.get("before_text_sha256") or "")
        if before_hash != spec["before_text_sha256"]:
            raise ModelValidationError(
                f"corrective retry target_paragraph_replacements[{ref}] "
                "before_text_sha256 mismatch"
            )
        replacement_text = str(item.get("replacement_text") or "").strip()
        if not replacement_text:
            raise ModelValidationError(
                f"corrective retry target_paragraph_replacements[{ref}] "
                "replacement_text is empty"
            )
        covered_ids = set(_string_tuple(item.get("active_target_ids_covered")))
        allowed_ids = set(_string_tuple(spec.get("active_target_ids")))
        unsupported = sorted(covered_ids - allowed_ids)
        if unsupported:
            raise ModelValidationError(
                f"corrective retry target_paragraph_replacements[{ref}] covers "
                "unassigned active target IDs: " + ", ".join(unsupported)
            )
        required_ids = sorted(allowed_ids & material_ids)
        missing_ids = sorted(set(required_ids) - covered_ids)
        if missing_ids:
            raise ModelValidationError(
                f"corrective retry target_paragraph_replacements[{ref}] does not "
                "cover material active targets: " + ", ".join(missing_ids)
            )
        if not _materially_changed_words(
            _normalized_words(str(spec["before_text"])),
            _normalized_words(replacement_text),
        ):
            raise ModelValidationError(
                f"corrective retry target_paragraph_replacements[{ref}] copied "
                "or insufficiently changed for material targets: "
                + ", ".join(required_ids)
            )
    replacement_paragraphs = [
        str(retry_by_ref[ref]["replacement_text"]).strip()
        if ref in retry_by_ref
        else str(spec_by_ref[ref]["before_text"])
        for ref in _target_paragraph_refs(target.original_target)
    ]
    _validate_required_target_span_replacements(
        subject=subject,
        payload=payload,
        replacement_paragraphs=replacement_paragraphs,
        required_parent_refs=failed_refs,
        error_prefix="corrective retry ",
    )


def _merge_target_addressed_retry_payload(
    *,
    subject: MacroSubject,
    first_payload: dict[str, object],
    retry_payload: dict[str, object],
    failed_refs: tuple[str, ...],
) -> dict[str, object]:
    target = _target_window(subject.base_text)
    refs = _target_paragraph_refs(target.original_target)
    failed_ref_set = set(failed_refs)
    first_by_ref = _replacement_map(first_payload)
    retry_by_ref = _replacement_map(retry_payload)
    first_spans_by_ref = _target_span_replacement_map(first_payload)
    retry_spans_by_ref = _target_span_replacement_map(retry_payload)
    merged_replacements: list[dict[str, object]] = []
    for ref in refs:
        if ref in failed_ref_set and ref in retry_by_ref:
            merged_replacements.append(dict(retry_by_ref[ref]))
        elif ref in first_by_ref:
            merged_replacements.append(dict(first_by_ref[ref]))
    target_spans = _target_span_specs(subject, target)
    merged_span_replacements: list[dict[str, object]] = []
    for span_spec in target_spans:
        span_ref = str(span_spec["target_span_ref"])
        parent_ref = str(span_spec["parent_target_paragraph_ref"])
        if parent_ref in failed_ref_set and span_ref in retry_spans_by_ref:
            merged_span_replacements.append(dict(retry_spans_by_ref[span_ref]))
        elif span_ref in first_spans_by_ref:
            merged_span_replacements.append(dict(first_spans_by_ref[span_ref]))
    merged = dict(first_payload)
    merged["target_paragraph_replacements"] = merged_replacements
    merged["target_span_replacements"] = merged_span_replacements
    return merged


def _replacement_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for item in replacements:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("target_paragraph_ref") or "")
        if ref:
            result[ref] = item
    return result


def _target_addressed_retry_report_not_attempted(
    *,
    retry_plan: TargetAddressedRetryPlan | None = None,
    first_attempt_model_call_id: str | None = None,
    budget_remaining: bool = False,
) -> dict[str, object]:
    return {
        "retry_attempted": False,
        "retry_reason": retry_plan.retry_reason if retry_plan else "",
        "first_attempt_model_call_id": first_attempt_model_call_id,
        "retry_model_call_id": None,
        "failed_target_paragraph_refs": list(
            retry_plan.failed_target_paragraph_refs if retry_plan else []
        ),
        "failed_target_span_refs": list(
            retry_plan.failed_target_span_refs if retry_plan else []
        ),
        "failure_reasons_by_ref": retry_plan.failure_reasons_by_ref if retry_plan else {},
        "failure_reasons_by_span": (
            retry_plan.failure_reasons_by_span if retry_plan else {}
        ),
        "failed_active_targets_by_span": (
            retry_plan.failed_active_targets_by_span if retry_plan else {}
        ),
        "preserved_first_attempt_refs": [],
        "retry_replaced_refs": [],
        "ignored_retry_refs": [],
        "merged_validation_passed": False,
        "retry_count": 0,
        "max_retry_count": 1,
        "budget_remaining_after_first_attempt": budget_remaining,
        "no_phase_shift_claim": True,
        "finalization_eligible": False,
    }


def _target_addressed_retry_report(
    *,
    retry_plan: TargetAddressedRetryPlan,
    first_attempt_model_call_id: str,
    retry_model_call_id: str,
    retry_payload: dict[str, object] | None,
    merged_payload: dict[str, object] | None,
    merged_validation_passed: bool,
    remaining_failure_message: str | None = None,
    remaining_validation_result: MacroTargetValidationResult | None = None,
) -> dict[str, object]:
    failed_refs = set(retry_plan.failed_target_paragraph_refs)
    first_refs = set(_replacement_map(retry_plan.first_attempt_payload or {}))
    retry_refs = set(_replacement_map(retry_payload or {}))
    preserved_refs = sorted(first_refs - failed_refs)
    retry_replaced_refs = sorted(ref for ref in retry_refs if ref in failed_refs)
    ignored_retry_refs = sorted(retry_refs - failed_refs)
    report = {
        "retry_attempted": True,
        "retry_reason": retry_plan.retry_reason,
        "first_attempt_model_call_id": first_attempt_model_call_id,
        "retry_model_call_id": retry_model_call_id,
        "failed_target_paragraph_refs": list(retry_plan.failed_target_paragraph_refs),
        "failed_target_span_refs": list(retry_plan.failed_target_span_refs),
        "failure_reasons_by_ref": retry_plan.failure_reasons_by_ref,
        "failure_reasons_by_span": retry_plan.failure_reasons_by_span,
        "failed_material_target_ids_by_ref": retry_plan.failed_material_target_ids_by_ref,
        "failed_active_targets_by_span": retry_plan.failed_active_targets_by_span,
        "preserved_first_attempt_refs": preserved_refs,
        "retry_replaced_refs": retry_replaced_refs,
        "ignored_retry_refs": ignored_retry_refs,
        "merged_validation_passed": merged_validation_passed,
        "retry_count": 1,
        "max_retry_count": 1,
        "no_phase_shift_claim": True,
        "finalization_eligible": False,
    }
    if remaining_failure_message:
        report["remaining_failure_message"] = remaining_failure_message
    if remaining_validation_result is not None:
        report["remaining_failed_target_paragraph_refs"] = list(
            remaining_validation_result.failed_target_paragraph_refs
        )
        report["remaining_failed_target_span_refs"] = list(
            remaining_validation_result.failed_target_span_refs
        )
        report["remaining_failure_reasons_by_ref"] = (
            remaining_validation_result.failure_reasons_by_ref
        )
        report["remaining_failure_reasons_by_span"] = (
            remaining_validation_result.failure_reasons_by_span
        )
    elif not merged_validation_passed and retry_payload is not None:
        remaining_refs = sorted(failed_refs - retry_refs)
        if remaining_refs:
            report["remaining_failed_target_paragraph_refs"] = remaining_refs
            report["remaining_failed_target_span_refs"] = []
    if merged_payload is not None:
        report["merged_target_paragraph_refs"] = list(_replacement_map(merged_payload))
    return report


def _validate_live_macro_payload(
    *,
    subject: MacroSubject,
    payload: dict[str, object],
) -> None:
    if subject.normalized_brief.reader_state_informed:
        validation_result = _collect_live_macro_validation_result(
            subject=subject,
            payload=payload,
        )
        if not validation_result.passed:
            raise ModelValidationError(validation_result.message)
        return

    _validate_section_plan(subject, payload)
    _validate_constraint_mapping(payload)
    _validate_active_target_mapping(
        payload,
        subject.normalized_brief.active_transformation_target_ids,
    )
    _validate_forbidden_live_macro_claims(payload)
    _validate_replacement_section(subject, payload)
    replacement_paragraphs = _paragraphs(str(payload["replacement_section_text"]))
    coverage_report = _build_target_coverage_report(
        subject,
        _target_window(subject.base_text),
        replacement_paragraphs,
        model_payload=payload,
    )
    if not coverage_report["span_level_coverage_passed"]:
        failed_spans = ", ".join(coverage_report["failed_target_span_refs"])
        raise ModelValidationError(f"target span coverage failed: {failed_spans}")
    if not coverage_report["macro_target_coverage_passed"]:
        missing = ", ".join(coverage_report["active_targets_missing"])
        raise ModelValidationError(f"macro target coverage failed: {missing}")
    if not coverage_report["macro_materiality_passed"]:
        raise ModelValidationError(
            "macro materiality failed: target section is insufficiently changed"
        )


def _fake_macro_1_replacement() -> list[str]:
    return [
        (
            "The deeper pattern does not arrive as a sentence placed over the room. "
            "It starts where the room is already busy: the ring drying lighter at "
            "one edge, the dust dragged into a narrow fan by a passing shoe, the "
            "spoon turning a small seam of light toward the cracked saucer. Each "
            "object keeps its own history, but none of the histories stays sealed. "
            "The table gathers them without becoming an explanation of them."
        ),
        (
            "Pressure enters through these crossings. The cup leaves the ring, the "
            "ring changes the wood, the dust records the shoe, and the shoe belongs "
            "to a body that had already left the kitchen before morning could name "
            "what happened. Nothing needs to announce a law. The law is the way one "
            "condition presses into the next until the boundary between them becomes "
            "visible enough to hurt."
        ),
        (
            "No answer comes from outside that pressure. The silence above the room "
            "is not a refusal of comfort added for mood; it is the condition that "
            "keeps the proof honest. If help arrived from beyond the line, the line "
            "would no longer have to carry what it had made. The table would become "
            "a prop in someone else's solution. Instead it stays local, and the "
            "local facts have to bear each other all the way through."
        ),
        (
            "So return cannot mean going back to the untouched table. The table was "
            "never untouched. The ring, the dust, the spoon, the saucer, the weak "
            "light, the small engine-hum of the refrigerator: they are not damage "
            "laid over a purer beginning. They are the beginning finding out what it "
            "was able to include. The room comes back to itself with the record "
            "still in it."
        ),
        (
            "In the morning, the table is still there. The dust is still under it. "
            "The spoon is still on its side. Nothing has been rescued from the room, "
            "and nothing has escaped into an answer elsewhere. Yet the facts no "
            "longer sit as separate proofs waiting to be named. They lean into one "
            "another, and the table holds the leaning: a small world returning, not "
            "unchanged, but with enough of its own pressure inside it to be read."
        ),
    ]


def _fake_reader_state_macro_2_replacement() -> list[str]:
    return [
        (
            "The room does not need a theorem added above it. The table keeps the "
            "ring where the cup had been, and the ring keeps changing as the wood "
            "dries around its edge. Dust still collects under the leg. The spoon "
            "still faces the saucer with its small dull glint. These marks do not "
            "argue; they hold one another close enough that the argument has to "
            "happen inside them."
        ),
        (
            "Proof begins there, in the way no mark can finish itself. The cup is "
            "gone, but the ring is not free of it. The shoe is gone, but the dust "
            "keeps the path. The hand is gone, but the spoon has remembered its "
            "turn toward the chipped rim. Nothing descends to certify the room. "
            "Each trace has to become the condition by which another trace can be "
            "read."
        ),
        (
            "That is why the silence above the room matters without becoming an "
            "announcement. It seals the kitchen inside its own evidence. No rescue "
            "arrives to explain the ring. No outside answer gathers the dust into "
            "meaning. If the line is going to prove anything, it must prove it by "
            "letting the table, the spoon, the saucer, and the morning light press "
            "on one another until their relation is the proof."
        ),
        (
            "The return therefore has to touch the first room again. The same table "
            "stands there, but the table is no longer only the place where objects "
            "were left. It is the place where absence has taken local shape. The "
            "ring is a boundary, the dust is a path, the spoon is an angle of use, "
            "and the saucer is the small rim against which the angle becomes "
            "visible."
        ),
        (
            "Morning does not solve this. It gives the room back with its evidence "
            "still inside it. The table is still there; the dust is still under it; "
            "the spoon still leans beside the saucer. What has changed is the way "
            "the beginning returns: not as a scene waiting for a lesson, but as the "
            "local field that already carried the lesson in its marks."
        ),
    ]


def _validate_section_plan(
    subject: MacroSubject,
    payload: dict[str, object],
) -> None:
    section_plan = payload.get("section_plan")
    if not isinstance(section_plan, dict):
        raise ModelValidationError("section_plan must be an object")
    target_movement = str(section_plan.get("target_movement") or "")
    if target_movement != subject.normalized_brief.target_movement:
        raise ModelValidationError("section_plan.target_movement must match controller target")
    if section_plan.get("bounded") is not True:
        raise ModelValidationError("section_plan.bounded must be true")
    if section_plan.get("full_rewrite") is not False:
        raise ModelValidationError("section_plan.full_rewrite must be false")


def _validate_constraint_mapping(payload: dict[str, object]) -> None:
    mapping = payload.get("constraint_mapping")
    if not isinstance(mapping, list):
        raise ModelValidationError("constraint_mapping must be a list")
    seen: set[str] = set()
    for item in mapping:
        if not isinstance(item, dict):
            raise ModelValidationError("constraint_mapping entries must be objects")
        constraint_id = str(item.get("constraint_id") or "")
        if constraint_id in seen:
            raise ModelValidationError(f"duplicate constraint_id: {constraint_id}")
        seen.add(constraint_id)
        excerpt = str(item.get("supporting_replacement_excerpt") or "").strip()
        if not excerpt:
            raise ModelValidationError(
                f"constraint_mapping[{constraint_id}] supporting excerpt is empty"
            )
    expected = set(REQUIRED_SEMANTIC_CONSTRAINT_IDS)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ModelValidationError(
            "constraint_mapping must contain exactly the required constraint IDs; "
            f"missing={missing}, extra={extra}"
        )


def _validate_active_target_mapping(
    payload: dict[str, object],
    expected_target_ids: tuple[str, ...],
) -> None:
    mapping = payload.get("active_target_mapping")
    if not isinstance(mapping, list):
        raise ModelValidationError("active_target_mapping must be a list")
    seen: set[str] = set()
    for item in mapping:
        if not isinstance(item, dict):
            raise ModelValidationError("active_target_mapping entries must be objects")
        target_id = str(item.get("target_id") or "")
        if target_id in seen:
            raise ModelValidationError(f"duplicate active target_id: {target_id}")
        seen.add(target_id)
        excerpt = str(item.get("supporting_replacement_excerpt") or "").strip()
        if not excerpt:
            raise ModelValidationError(
                f"active_target_mapping[{target_id}] supporting excerpt is empty"
            )
        unchanged = item.get("unchanged")
        if unchanged is True and not str(item.get("unchanged_justification") or "").strip():
            raise ModelValidationError(
                f"active_target_mapping[{target_id}] unchanged target requires justification"
            )
    expected = set(expected_target_ids)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ModelValidationError(
            "active_target_mapping must contain exactly the active target IDs; "
            f"missing={missing}, extra={extra}"
        )


def _constraint_mapping_complete(payload: dict[str, object]) -> bool:
    try:
        _validate_constraint_mapping(payload)
    except ModelValidationError:
        return False
    return True


def _active_target_mapping_complete(payload: dict[str, object]) -> bool:
    try:
        _validate_active_target_mapping(payload, ACTIVE_TRANSFORMATION_TARGET_IDS)
    except ModelValidationError:
        return False
    return True


def _active_target_mapping_complete_for_subject(
    subject: MacroSubject,
    payload: dict[str, object],
) -> bool:
    try:
        _validate_active_target_mapping(
            payload,
            subject.normalized_brief.active_transformation_target_ids,
        )
    except ModelValidationError:
        return False
    return True


def _validate_required_target_span_replacements(
    *,
    subject: MacroSubject,
    payload: dict[str, object],
    replacement_paragraphs: list[str],
    required_parent_refs: tuple[str, ...] | None = None,
    error_prefix: str = "",
) -> None:
    target = _target_window(subject.base_text)
    report = _build_target_span_coverage_report(
        subject,
        target,
        replacement_paragraphs,
        model_payload=payload,
        required_parent_refs=required_parent_refs,
    )
    if report["target_span_count"] == 0:
        return
    missing = list(report.get("missing_target_span_replacements", []))
    if missing:
        raise ModelValidationError(
            f"{error_prefix}missing target span replacement: " + ", ".join(missing)
        )
    mismatched = list(report.get("hash_mismatched_target_span_replacements", []))
    if mismatched:
        raise ModelValidationError(
            f"{error_prefix}target_span_replacements[{mismatched[0]}] "
            "before_text_sha256 mismatch"
        )
    empty = list(report.get("empty_target_span_replacement_excerpts", []))
    if empty:
        raise ModelValidationError(
            f"{error_prefix}target_span_replacements[{empty[0]}] "
            "replacement_excerpt is empty"
        )
    unsupported = dict(report.get("unsupported_active_targets_by_span", {}))
    if unsupported:
        span_ref = sorted(unsupported)[0]
        raise ModelValidationError(
            f"{error_prefix}target_span_replacements[{span_ref}] covers "
            "unassigned active target IDs: " + ", ".join(unsupported[span_ref])
        )
    missing_ids = dict(report.get("missing_active_targets_by_span", {}))
    if missing_ids:
        span_ref = sorted(missing_ids)[0]
        raise ModelValidationError(
            f"{error_prefix}target_span_replacements[{span_ref}] does not cover "
            "material active targets: " + ", ".join(missing_ids[span_ref])
        )
    if not report["span_level_coverage_passed"]:
        failed = list(report["failed_target_span_refs"])
        raise ModelValidationError(
            f"{error_prefix}target span coverage failed: " + ", ".join(failed)
        )


def _build_target_span_coverage_report(
    subject: MacroSubject,
    target: RecomposedText,
    replacement_paragraphs: list[str],
    *,
    model_payload: dict[str, object] | None,
    required_parent_refs: tuple[str, ...] | None = None,
) -> dict[str, object]:
    span_specs = _target_span_specs(subject, target)
    required_parent_set = set(required_parent_refs or ())
    if required_parent_set:
        span_specs = [
            spec
            for spec in span_specs
            if str(spec["parent_target_paragraph_ref"]) in required_parent_set
        ]
    replacement_by_parent = _replacement_paragraphs_by_ref(target, replacement_paragraphs)
    span_replacements = _target_span_replacement_map(model_payload or {})
    strict_model_mapping_required = model_payload is not None
    comparison: list[dict[str, object]] = []
    missing_replacements: list[str] = []
    mismatched_hashes: list[str] = []
    empty_excerpts: list[str] = []
    unchanged_required: list[str] = []
    missing_active_targets_by_span: dict[str, list[str]] = {}
    unsupported_active_targets_by_span: dict[str, list[str]] = {}
    failed_active_targets_by_span: dict[str, list[str]] = {}
    materially_changed_count = 0

    for spec in span_specs:
        span_ref = str(spec["target_span_ref"])
        parent_ref = str(spec["parent_target_paragraph_ref"])
        material_required = bool(spec["material_change_required"])
        parent_replacement = replacement_by_parent.get(parent_ref, "")
        before_text = str(spec["before_text"])
        before_preserved = _contains_normalized_sequence(
            parent_replacement,
            before_text,
        )
        span_replacement = span_replacements.get(span_ref)
        mapping_present = span_replacement is not None
        excerpt = (
            str(span_replacement.get("replacement_excerpt") or "").strip()
            if span_replacement
            else parent_replacement
        )
        mapping_ok = mapping_present or not strict_model_mapping_required
        covered_ids = set(
            _string_tuple(
                span_replacement.get("active_target_ids_covered")
                if span_replacement
                else []
            )
        )
        allowed_ids = set(_string_tuple(spec.get("active_target_ids")))
        unsupported_ids = sorted(covered_ids - allowed_ids)
        required_ids = sorted(allowed_ids) if material_required else []
        missing_ids = (
            sorted(set(required_ids) - covered_ids)
            if strict_model_mapping_required
            else []
        )
        hash_matches = True
        if span_replacement:
            hash_matches = (
                str(span_replacement.get("before_text_sha256") or "")
                == spec["before_text_sha256"]
            )
        materially_changed = (
            material_required
            and bool(parent_replacement)
            and not before_preserved
            and mapping_ok
            and bool(excerpt)
            and hash_matches
            and not unsupported_ids
            and not missing_ids
        )
        if material_required and strict_model_mapping_required and not mapping_present:
            missing_replacements.append(span_ref)
        if material_required and mapping_present and not hash_matches:
            mismatched_hashes.append(span_ref)
        if material_required and mapping_present and not excerpt:
            empty_excerpts.append(span_ref)
        if unsupported_ids:
            unsupported_active_targets_by_span[span_ref] = unsupported_ids
        if material_required and missing_ids:
            missing_active_targets_by_span[span_ref] = missing_ids
        if material_required and before_preserved:
            unchanged_required.append(span_ref)
        if materially_changed:
            materially_changed_count += 1
        elif material_required:
            failed_active_targets_by_span[span_ref] = required_ids
        comparison.append(
            {
                "target_span_ref": span_ref,
                "parent_target_paragraph_ref": parent_ref,
                "before_text_sha256": spec["before_text_sha256"],
                "before_text_preserved_unchanged": before_preserved,
                "mapping_present": mapping_present,
                "material_change_required": material_required,
                "materially_changed": materially_changed,
                "active_target_ids": list(_string_tuple(spec.get("active_target_ids"))),
                "span_role": spec.get("span_role"),
                "allowed_operation": spec.get("allowed_operation"),
            }
        )

    failed_refs = [
        str(row["target_span_ref"])
        for row in comparison
        if row["material_change_required"] and not row["materially_changed"]
    ]
    thesis_report = _thesis_visible_span_report(comparison)
    if thesis_report["required"] and not thesis_report["passed"]:
        failed_refs = _unique(
            [
                *failed_refs,
                *list(thesis_report["failed_target_span_refs"]),
            ]
        )
    failed_refs = sorted(failed_refs)
    span_level_passed = not failed_refs
    return {
        "target_span_count": len(span_specs),
        "material_target_span_count": len(
            [spec for spec in span_specs if bool(spec["material_change_required"])]
        ),
        "materially_changed_target_span_count": materially_changed_count,
        "unchanged_required_target_spans": sorted(unchanged_required),
        "active_target_span_coverage_passed": span_level_passed,
        "failed_target_span_refs": failed_refs,
        "failed_active_targets_by_span": failed_active_targets_by_span,
        "missing_target_span_replacements": sorted(missing_replacements),
        "hash_mismatched_target_span_replacements": sorted(mismatched_hashes),
        "empty_target_span_replacement_excerpts": sorted(empty_excerpts),
        "missing_active_targets_by_span": missing_active_targets_by_span,
        "unsupported_active_targets_by_span": unsupported_active_targets_by_span,
        "span_level_coverage_passed": span_level_passed,
        "target_span_comparison": comparison,
        "thesis_visible_proof_language_reduction_span_rule": thesis_report,
    }


def _target_span_replacement_map(
    payload: dict[str, object],
) -> dict[str, dict[str, object]]:
    replacements = payload.get("target_span_replacements")
    if not isinstance(replacements, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for item in replacements:
        if not isinstance(item, dict):
            continue
        span_ref = str(item.get("target_span_ref") or "")
        if span_ref:
            result[span_ref] = item
    return result


def _replacement_paragraphs_by_ref(
    target: RecomposedText,
    replacement_paragraphs: list[str],
) -> dict[str, str]:
    refs = _target_paragraph_refs(target.original_target)
    return {
        ref: replacement_paragraphs[index] if index < len(replacement_paragraphs) else ""
        for index, ref in enumerate(refs)
    }


def _contains_normalized_sequence(text: str, phrase: str) -> bool:
    text_words = _normalized_words(text)
    phrase_words = _normalized_words(phrase)
    if not text_words or not phrase_words or len(phrase_words) > len(text_words):
        return False
    phrase_len = len(phrase_words)
    return any(
        text_words[index : index + phrase_len] == phrase_words
        for index in range(len(text_words) - phrase_len + 1)
    )


def _thesis_visible_span_report(
    comparison: list[dict[str, object]],
) -> dict[str, object]:
    thesis_rows = [
        row
        for row in comparison
        if "thesis_visible_proof_language_reduction"
        in row.get("active_target_ids", [])
        and row.get("material_change_required")
    ]
    if not thesis_rows:
        return {"required": False, "passed": True, "failed_target_span_refs": []}
    thesis_frame_changed = any(
        row.get("span_role") == "thesis_frame" and row.get("materially_changed")
        for row in thesis_rows
    )
    proof_changed = any(
        row.get("span_role") == "proof_sentence" and row.get("materially_changed")
        for row in thesis_rows
    )
    failed = []
    if not thesis_frame_changed:
        failed.extend(
            str(row["target_span_ref"])
            for row in thesis_rows
            if row.get("span_role") == "thesis_frame"
        )
    if not proof_changed:
        failed.extend(
            str(row["target_span_ref"])
            for row in thesis_rows
            if row.get("span_role") == "proof_sentence"
        )
    return {
        "required": True,
        "passed": thesis_frame_changed and proof_changed,
        "thesis_framing_span_changed": thesis_frame_changed,
        "proof_sentence_span_changed": proof_changed,
        "failed_target_span_refs": sorted(_unique(failed)),
        "rule": (
            "At least one required thesis-framing span and the explicit proof "
            "span must be materially altered; changing only the proof sentence "
            "is insufficient."
        ),
    }


def _build_target_coverage_report(
    subject: MacroSubject,
    target: RecomposedText,
    replacement_paragraphs: list[str],
    *,
    model_payload: dict[str, object] | None,
) -> dict[str, object]:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    active_target_ids = subject.normalized_brief.active_transformation_target_ids
    material_required_ids = set(subject.normalized_brief.material_required_target_ids)
    target_ref_by_id = _active_target_ref_map(paragraph_refs, active_target_ids)
    paragraph_comparison = _paragraph_materiality_comparison(
        target.original_target,
        replacement_paragraphs,
    )
    material_refs = {
        str(row["target_paragraph_ref"])
        for row in paragraph_comparison
        if bool(row["materially_changed"])
    }
    unchanged_target_paragraphs = [
        row for row in paragraph_comparison if not bool(row["materially_changed"])
    ]
    mapping_by_target = _active_mapping_by_target(model_payload, active_target_ids)
    active_targets_covered: list[str] = []
    active_targets_missing: list[str] = []
    unchanged_with_justification: list[dict[str, object]] = []
    for target_id in active_target_ids:
        mapping = mapping_by_target.get(target_id)
        target_ref = target_ref_by_id[target_id]
        paragraph_material = (
            bool(material_refs)
            if target_ref == "target_section"
            else target_ref in material_refs
        )
        unchanged = bool(mapping.get("unchanged")) if mapping else False
        justification = str(mapping.get("unchanged_justification") or "") if mapping else ""
        if unchanged:
            unchanged_with_justification.append(
                {
                    "target_id": target_id,
                    "target_paragraph_ref": target_ref,
                    "justification": justification,
                }
            )
        covered = bool(mapping) and paragraph_material
        if (
            mapping
            and unchanged
            and target_id not in material_required_ids
            and justification.strip()
        ):
            covered = True
        if covered:
            active_targets_covered.append(target_id)
        else:
            active_targets_missing.append(target_id)
    materiality_required_count = min(
        len(paragraph_refs),
        max(2, (len(paragraph_refs) + 1) // 2),
    )
    materially_changed_count = len(material_refs)
    macro_materiality_passed = materially_changed_count >= materiality_required_count
    paragraph_level_coverage_passed = (
        not active_targets_missing and macro_materiality_passed
    )
    span_report = _build_target_span_coverage_report(
        subject,
        target,
        replacement_paragraphs,
        model_payload=model_payload,
    )
    span_level_coverage_passed = bool(span_report["span_level_coverage_passed"])
    span_validation_required = bool(span_report["target_span_count"])
    macro_target_coverage_passed = paragraph_level_coverage_passed and (
        span_level_coverage_passed or not span_validation_required
    )
    return {
        "target_paragraph_count": len(target.original_target),
        "replacement_paragraph_count": len(replacement_paragraphs),
        "materially_changed_target_paragraph_count": materially_changed_count,
        "unchanged_target_paragraph_count": len(unchanged_target_paragraphs),
        "paragraph_comparison": paragraph_comparison,
        "active_transformation_targets": list(active_target_ids),
        "active_targets_covered": active_targets_covered,
        "active_targets_missing": active_targets_missing,
        "unchanged_target_paragraphs_with_justification": unchanged_with_justification,
        "paragraph_level_coverage_passed": paragraph_level_coverage_passed,
        "target_span_count": span_report["target_span_count"],
        "materially_changed_target_span_count": span_report[
            "materially_changed_target_span_count"
        ],
        "unchanged_required_target_spans": span_report[
            "unchanged_required_target_spans"
        ],
        "active_target_span_coverage_passed": span_report[
            "active_target_span_coverage_passed"
        ],
        "failed_target_span_refs": span_report["failed_target_span_refs"],
        "failed_active_targets_by_span": span_report[
            "failed_active_targets_by_span"
        ],
        "span_level_coverage_passed": span_level_coverage_passed,
        "target_span_comparison": span_report["target_span_comparison"],
        "thesis_visible_proof_language_reduction_span_rule": span_report[
            "thesis_visible_proof_language_reduction_span_rule"
        ],
        "macro_target_coverage_passed": macro_target_coverage_passed,
        "controller_target_coverage_passed": macro_target_coverage_passed,
        "macro_materiality_passed": macro_materiality_passed,
        "active_target_mapping_complete": bool(model_payload)
        and _active_target_mapping_complete_for_subject(subject, model_payload),
        "model_active_target_mapping_complete": bool(model_payload)
        and _active_target_mapping_complete_for_subject(subject, model_payload),
        "ready_for_executed_ablation": macro_target_coverage_passed,
    }


def _paragraph_materiality_comparison(
    before_paragraphs: list[str],
    replacement_paragraphs: list[str],
) -> list[dict[str, object]]:
    rows = []
    for index, before in enumerate(before_paragraphs):
        after = replacement_paragraphs[index] if index < len(replacement_paragraphs) else ""
        before_words = _normalized_words(before)
        after_words = _normalized_words(after)
        materially_changed = _materially_changed_words(before_words, after_words)
        rows.append(
            {
                "target_paragraph_ref": _target_paragraph_ref(index),
                "before_sha256": sha256_text(before),
                "after_sha256": sha256_text(after),
                "before_word_count": len(before_words),
                "after_word_count": len(after_words),
                "normalized_text_equal": before_words == after_words,
                "materially_changed": materially_changed,
            }
        )
    return rows


def _materially_changed_words(before_words: list[str], after_words: list[str]) -> bool:
    if not before_words and not after_words:
        return False
    if before_words == after_words:
        return False
    before_counts = _word_counts(before_words)
    after_counts = _word_counts(after_words)
    overlap = sum(
        min(count, after_counts.get(word, 0)) for word, count in before_counts.items()
    )
    max_count = max(len(before_words), len(after_words), 1)
    changed_count = max_count - overlap
    changed_ratio = changed_count / max_count
    return changed_count >= 6 and changed_ratio >= 0.18


def _word_counts(words: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return counts


def _normalized_words(text: str) -> list[str]:
    words: list[str] = []
    current = []
    for character in text.lower():
        if character.isalnum():
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _active_mapping_by_target(
    model_payload: dict[str, object] | None,
    active_target_ids: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if not model_payload:
        return _fake_active_target_mapping(active_target_ids)
    mapping = model_payload.get("active_target_mapping", [])
    if not isinstance(mapping, list):
        return {}
    return {
        str(item.get("target_id")): item
        for item in mapping
        if isinstance(item, dict) and item.get("target_id")
    }


def _fake_active_target_mapping(
    active_target_ids: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    return {
        target_id: {
            "target_id": target_id,
            "unchanged": False,
            "unchanged_justification": "",
            "supporting_replacement_excerpt": "deterministic fake replacement section",
        }
        for target_id in active_target_ids
    }


def _target_paragraph_refs(paragraphs: list[str]) -> list[str]:
    return [_target_paragraph_ref(index) for index, _paragraph in enumerate(paragraphs)]


def _target_paragraph_ref(index: int) -> str:
    return f"target_p{index + 1:03d}"


def _active_target_ref_map(
    paragraph_refs: list[str],
    active_target_ids: tuple[str, ...],
) -> dict[str, str]:
    first_ref = paragraph_refs[0] if paragraph_refs else "target_section"
    second_ref = paragraph_refs[1] if len(paragraph_refs) > 1 else first_ref
    last_ref = paragraph_refs[-1] if paragraph_refs else "target_section"
    default_refs = {
        "middle_abstraction_ladder_compression": first_ref,
        "proof_line_redundancy_cleanup": second_ref,
        "no_outside_answer_pressure_preservation": second_ref,
        "final_return_closure_embodiment": last_ref,
        "object_event_pressure_without_pressure_naming": "target_section",
        "proof_no_outside_answer_refinement": second_ref,
        "final_return_echo_reread_strength": last_ref,
        "thesis_visible_proof_language_reduction": "target_section",
        "opening_return_transformation_strengthening": last_ref,
        "preserve_reader_state_partial_gain": "target_section",
    }
    return {target_id: default_refs.get(target_id, "target_section") for target_id in active_target_ids}


def _target_addressed_replacement_paragraphs(
    subject: MacroSubject,
    payload: dict[str, object],
) -> list[str]:
    target = _target_window(subject.base_text)
    specs = _target_paragraph_specs(subject, target)
    spec_by_ref = {str(spec["target_paragraph_ref"]): spec for spec in specs}
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        raise ModelValidationError(
            "target_paragraph_replacements is required for reader_state_informed_macro_2"
        )

    material_target_ids = set(subject.normalized_brief.material_required_target_ids)
    material_refs = {
        str(spec["target_paragraph_ref"])
        for spec in specs
        if bool(spec["material_change_required"])
    }
    seen_refs: dict[str, dict[str, object]] = {}
    covered_material_targets: set[str] = set()
    for item in replacements:
        if not isinstance(item, dict):
            raise ModelValidationError("target_paragraph_replacements entries must be objects")
        ref = str(item.get("target_paragraph_ref") or "")
        if ref not in spec_by_ref:
            raise ModelValidationError(f"unsupported target_paragraph_ref: {ref}")
        if ref in seen_refs:
            raise ModelValidationError(f"duplicate target_paragraph_ref: {ref}")
        spec = spec_by_ref[ref]
        before_hash = str(item.get("before_text_sha256") or "")
        if before_hash != spec["before_text_sha256"]:
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] before_text_sha256 mismatch"
            )
        replacement_text = str(item.get("replacement_text") or "").strip()
        if not replacement_text:
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] replacement_text is empty"
            )
        active_ids_covered = _string_tuple(item.get("active_target_ids_covered"))
        allowed_target_ids = set(_string_tuple(spec.get("active_target_ids")))
        unsupported = sorted(set(active_ids_covered) - allowed_target_ids)
        if unsupported:
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] covers unassigned active target IDs: "
                + ", ".join(unsupported)
            )
        before_words = _normalized_words(str(spec["before_text"]))
        after_words = _normalized_words(replacement_text)
        materially_changed = _materially_changed_words(before_words, after_words)
        if bool(spec["material_change_required"]) and not materially_changed:
            required_ids = sorted(allowed_target_ids & material_target_ids)
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] copied or insufficiently changed "
                f"for material targets: {', '.join(required_ids)}"
            )
        if materially_changed:
            covered_material_targets.update(
                target_id for target_id in active_ids_covered if target_id in material_target_ids
            )
        seen_refs[ref] = item

    missing_refs = sorted(material_refs - set(seen_refs))
    if missing_refs:
        raise ModelValidationError(
            "missing target paragraph replacement: " + ", ".join(missing_refs)
        )
    missing_targets = sorted(material_target_ids - covered_material_targets)
    if missing_targets:
        raise ModelValidationError(
            "target paragraph replacements do not cover material active targets: "
            + ", ".join(missing_targets)
        )

    replacement_paragraphs = [
        str(seen_refs[ref]["replacement_text"]).strip()
        if ref in seen_refs
        else str(spec_by_ref[ref]["before_text"])
        for ref in _target_paragraph_refs(target.original_target)
    ]
    _validate_required_target_span_replacements(
        subject=subject,
        payload=payload,
        replacement_paragraphs=replacement_paragraphs,
    )
    return replacement_paragraphs


def _validate_replacement_section(
    subject: MacroSubject,
    payload: dict[str, object],
) -> None:
    replacement_text = str(payload.get("replacement_section_text") or "").strip()
    _validate_replacement_text(subject, replacement_text)


def _validate_replacement_text(subject: MacroSubject, replacement_text: str) -> None:
    if not replacement_text:
        raise ModelValidationError("replacement_section_text must not be empty")
    target = _target_window(subject.base_text)
    replacement_paragraphs = _paragraphs(replacement_text)
    if not replacement_paragraphs:
        raise ModelValidationError("replacement_section_text must contain paragraphs")
    prefix_text = "\n\n".join(target.unchanged_prefix).strip()
    opening = target.unchanged_prefix[0] if target.unchanged_prefix else ""
    replacement_lower = replacement_text.lower()
    if opening and replacement_text.startswith(opening[:80]):
        raise ModelValidationError(
            "replacement_section_text rewrites or repeats the controller-owned prefix"
        )
    if prefix_text and prefix_text[:160].lower() in replacement_lower:
        raise ModelValidationError(
            "replacement_section_text includes controller-owned prefix text"
        )
    if replacement_text.strip() == subject.base_text.strip():
        raise ModelValidationError("replacement_section_text must not be the full base text")


def _validate_forbidden_live_macro_claims(payload: dict[str, object]) -> None:
    for path, value in _iter_string_fields(payload):
        finding = _classify_forbidden_live_macro_claim(path, value)
        if finding is not None:
            raise ModelValidationError(
                f"{finding.claim_type} in {finding.path}: "
                f"{_quoted_excerpt(finding.excerpt)}"
            )


def _iter_string_fields(value: object, path: str = "$") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        fields: list[tuple[str, str]] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path != "$" else str(key)
            fields.extend(_iter_string_fields(child, child_path))
        return fields
    if isinstance(value, list):
        fields: list[tuple[str, str]] = []
        for index, child in enumerate(value):
            fields.extend(_iter_string_fields(child, f"{path}[{index}]"))
        return fields
    return []


def _classify_forbidden_live_macro_claim(
    path: str,
    value: str,
) -> ForbiddenClaimFinding | None:
    lower = _normalized_claim_text(value)
    for marker, claim_type in _hard_forbidden_live_macro_markers().items():
        if marker in lower:
            return ForbiddenClaimFinding(
                path=path,
                excerpt=_sentence_excerpt(value, marker),
                claim_type=claim_type,
                reason="hard_forbidden_marker",
            )
    for pattern, claim_type in _affirmative_finality_patterns():
        match = pattern.search(lower)
        if match and not _is_allowed_nonclaim_context(lower, match.start(), match.end()):
            return ForbiddenClaimFinding(
                path=path,
                excerpt=_sentence_excerpt(value, match.group(0)),
                claim_type=claim_type,
                reason=_field_claim_context(path),
            )
    return None


def _hard_forbidden_live_macro_markers() -> dict[str, str]:
    return {
        "outside rescue arrives": "outside-rescue violation",
        "rescued from outside": "outside-rescue violation",
        "answer arrives from outside": "outside-answer violation",
        "answer is supplied from outside": "outside-answer violation",
        "proof comes from outside": "proof-from-outside violation",
        "proof arrives from outside": "proof-from-outside violation",
        "proof is supplied from outside": "proof-from-outside violation",
        "discard the table": "local-field discard violation",
        "remove the table": "local-field discard violation",
        "without the table": "local-field discard violation",
        "discard the dust": "local-field discard violation",
        "discard the spoon": "local-field discard violation",
        "discard the saucer": "local-field discard violation",
        "human validated": "human-validation claim",
        "paper-ready": "paper-readiness claim",
    }


def _affirmative_finality_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    return (
        (
            re.compile(r"\b(?:this|the|candidate|artifact|output|text)\s+is\s+the\s+final\s+artifact\b"),
            "finality claim",
        ),
        (re.compile(r"\b(?:the\s+)?candidate\s+is\s+final\b"), "finality claim"),
        (re.compile(r"\bfinal\s+artifact\s+(?:ready|complete|completed|accepted|approved|achieved|proven)\b"), "finality claim"),
        (re.compile(r"\bfinal\s+version\b"), "finality claim"),
        (re.compile(r"\bfinali[sz]ation\s+eligible\b"), "finality claim"),
        (re.compile(r"\bready\s+for\s+finali[sz]ation\b"), "finality claim"),
        (re.compile(r"\bphase[- ]shift\s+(?:achieved|proven|complete|completed|succeeds|succeeded)\b"), "phase-shift claim"),
        (re.compile(r"\bcreative\s+phase[- ]shift\s+(?:achieved|proven|complete|completed)\b"), "phase-shift claim"),
        (re.compile(r"\brival\s+defeated\b"), "rival-defeat claim"),
        (re.compile(r"\bstrongest\s+rival\s+defeated\b"), "rival-defeat claim"),
        (re.compile(r"\bartifact\s+success\s+proven\b"), "artifact-success claim"),
    )


def _is_allowed_nonclaim_context(text: str, start: int, end: int) -> bool:
    sentence = _sentence_around(text, start, end)
    allowed_markers = (
        "not final",
        "non-final",
        "not a final artifact",
        "does not claim",
        "doesn't claim",
        "avoid finality",
        "avoids claim-language",
        "avoid claim-language",
        "no final claim",
        "no phase-shift claim",
        "not phase-shift evidence",
        "requires ablation before any improvement claim",
        "controller still needs to assemble the final artifact",
        "controller owns final assembly",
        "controller owns finalization",
        "controller owns finalisation",
        "controller still owns final assembly",
        "finalization remains false",
        "finalisation remains false",
        "without claiming closure",
        "without claiming finality",
        "without asserting final closure",
        "not claiming victory",
        "rather than claiming victory",
        "does not claim closure",
        "does not claim finality",
        "does not claim closure finality or defeat",
    )
    return any(marker in sentence for marker in allowed_markers)


def _field_claim_context(path: str) -> str:
    artifact_facing_suffixes = (
        "replacement_section_text",
        "replacement_text",
        "replacement_excerpt",
    )
    if path.endswith(artifact_facing_suffixes):
        return "artifact_facing_field"
    return "model_metadata_field"


def _normalized_claim_text(value: str) -> str:
    lowered = value.lower().replace("\u2011", "-").replace("\u2010", "-")
    lowered = lowered.replace("\u2013", "-").replace("\u2014", "-")
    lowered = lowered.replace("'", "'").replace("\u2019", "'")
    return re.sub(r"\s+", " ", lowered).strip()


def _sentence_excerpt(value: str, marker: str) -> str:
    lower = _normalized_claim_text(value)
    normalized_marker = _normalized_claim_text(marker)
    marker_index = lower.find(normalized_marker)
    if marker_index < 0:
        return value.strip()[:160]
    return _sentence_around(value, marker_index, marker_index + len(normalized_marker))[
        :160
    ]


def _sentence_around(value: str, start: int, end: int) -> str:
    normalized = _normalized_claim_text(value)
    start = min(start, len(normalized))
    end = min(max(end, start), len(normalized))
    left_candidates = [normalized.rfind(mark, 0, start) for mark in (".", "!", "?")]
    left = max(left_candidates)
    right_candidates = [
        index
        for index in (normalized.find(mark, end) for mark in (".", "!", "?"))
        if index >= 0
    ]
    right = min(right_candidates) if right_candidates else len(normalized)
    return normalized[left + 1 : right].strip()


def _quoted_excerpt(value: str) -> str:
    return f'"{value.strip()[:160]}"'


def _load_base_candidate_payload(packet_dir: Path, packet_kind: str) -> dict[str, Any]:
    if packet_kind == "bounded_macro_recomposition":
        return _read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    if packet_kind == "ablation_informed_revision":
        return _read_payload(packet_dir / "cycle2_revised_candidate_text.json")
    if packet_kind == "autonomous_revision":
        return _read_payload(packet_dir / "revised_candidate_text.json")
    raise ValueError(f"unsupported selected best candidate packet kind: {packet_kind}")


def _source_parent_ids(
    connection: sqlite3.Connection,
    synthesis_packet_dir: Path,
    synthesis_artifact_ids: dict[object, object],
) -> list[str]:
    parent_ids = [str(value) for value in synthesis_artifact_ids.values() if isinstance(value, str)]
    packet_artifact = _artifact_for_path(
        connection,
        synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json",
    )
    if packet_artifact is not None:
        parent_ids.append(packet_artifact.id)
    return _unique(parent_ids)


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path), str(path.resolve())),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required artifact is missing: {path.name}")
    envelope = read_json_file(path)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"artifact payload is not an object: {path.name}")
    return payload


def _resolve_path(config: AbiConfig, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (config.root / path).resolve()


def _target_start(paragraphs: list[str]) -> int:
    if len(paragraphs) <= 1:
        return 0
    needles = (
        "There is a deeper pattern",
        "A line of life and mind",
        "That is why the sky",
    )
    for index, paragraph in enumerate(paragraphs):
        if any(needle in paragraph for needle in needles):
            return index
    return min(max(1, len(paragraphs) - 4), len(paragraphs) - 1)


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _words(text: str) -> list[str]:
    return [word for word in text.split() if word]


def _unique(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        value_text = str(value)
        if value_text not in result:
            result.append(value_text)
    return result


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value,)
    return ()


def _dict_value(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _gate_result(
    gate_name: str,
    passed: bool,
    blocking_defects: list[str] | None = None,
    *,
    record: bool = True,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "record": record,
        "blocking_defects": list(blocking_defects or ([] if passed else [f"{gate_name} is missing"])),
    }


def _refusal(
    *,
    message: str,
    synthesis_packet: Path,
    client_name: str | None = None,
    model: str | None = None,
) -> BoundedMacroRecompositionResult:
    payload = {
        "accepted": False,
        "refused": True,
        "client": client_name,
        "model": model,
        "synthesis_packet": str(synthesis_packet),
        "message": message,
        "counts": {"model_calls": 0},
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
    }
    return BoundedMacroRecompositionResult(exit_code=1, payload=payload)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
