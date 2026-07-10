"""Authorize one selected-target cycle mechanism-visibility generation attempt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_GENERATION_AUTHORIZATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.nonlocal_law_selected_target_cycle_work_order import (
    ABLATION_CONTROLS,
    GAINS_TO_PRESERVE,
    MATERIALITY_REQUIREMENTS,
    NONLOCAL_LAW_SELECTED_TARGET_CYCLE_WORK_ORDER_ARTIFACT_TYPES,
    PHRASE_INVENTORY,
    PHRASE_INVENTORY_POLICY,
    READER_STATE_FOCUS,
    SELECTED_RISK_ID,
    SELECTED_TARGET_CLASS,
    SELECTED_TARGET_SEED_ID,
    SEMANTIC_REQUIREMENTS,
    TARGET_UNIT_IDS,
    WORK_ORDER_KIND,
    WORK_ORDER_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


LINEAGE_ID = "nonlocal_law_selected_target_cycle_generation_authorization_v1"
CREATED_BY = (
    "nonlocal_law_selected_target_cycle_generation_authorization_v1_controller"
)
SOURCE_FAMILY = "nonlocal_law_selected_target_cycle_work_order"

AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE = (
    "authorize_one_bounded_selected_target_cycle_generation"
)
AUTHORIZATION_DECISION_REFUSE = "refuse_generation_authorization"
AUTHORIZATION_DECISION_REFUSE_SHORT = "refuse_generation"
DECISIONS = (
    AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE,
    AUTHORIZATION_DECISION_REFUSE,
    AUTHORIZATION_DECISION_REFUSE_SHORT,
)

NEXT_ACTION_AUTHORIZE = "generate_selected_target_cycle_candidate"
AUTHORIZATION_SCOPE = "one_bounded_mechanism_visibility_generation_attempt"
SUPERSESSION_REASON_AUTHORIZATION_SURFACE_MISSING = (
    "selected_target_cycle_generation_authorization_surface_missing"
)

MATERIAL_GENERATION_UNIT_IDS = (
    "reduce_direct_mechanism_naming",
    "convert_declarative_instruction_to_object_pressure",
    "convert_law_naming_to_perceptual_sequence",
)
PRESERVATION_OR_GUARD_UNIT_IDS = (
    "preserve_living_event_sequence_gain",
    "preserve_earned_explanation_not_abolished",
    "protect_object_activity_and_delicacy",
    "preserve_non_selected_risks_as_constraints",
    "preserve_strongest_rival_blocker_and_non_imitation",
)

ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_cycle_generation_authorization_packet",
    "source_cycle_work_order_intake_summary",
    "authorization_decision_record",
    "mechanism_visibility_generation_scope_review",
    "target_unit_authorization_scope",
    "phrase_handling_authorization_policy",
    "materiality_semantic_validation_readiness_report",
    "forbidden_overcorrection_and_regression_review",
    "protected_living_event_gain_review",
    "post_generation_evidence_plan",
    "model_call_budget_report",
    "generation_lock_transition_report",
    "selected_target_cycle_generation_authorization_gate_report",
    "project_health_scope_guard_report",
)


@dataclass(frozen=True)
class SelectedTargetCycleGenerationAuthorizationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SelectedTargetCycleGenerationAuthorizationSubject:
    run_id: str
    work_order_packet_dir: Path
    work_order_packet_id: str
    work_order_packet_artifact_id: str | None
    work_order_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    superseded_authorization_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_authorization_surface_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorizationSupersessionContext:
    corrected_current_valid_authorization_exists: bool
    superseded_authorization_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


def run_selected_target_cycle_generation_authorization(
    config: AbiConfig,
    *,
    work_order_packet: Path | str,
    operator_reviewed: bool,
    decision: str | None,
) -> SelectedTargetCycleGenerationAuthorizationResult:
    initialize_database(config)
    work_order_packet_dir = _resolve_path(config, work_order_packet)
    if not operator_reviewed:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected-target cycle generation authorization refused; "
                "--operator-reviewed is required."
            ),
        )
    if decision not in DECISIONS:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected-target cycle generation authorization refused; "
                "--decision must be "
                f"{AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE}."
            ),
        )
    if decision in {AUTHORIZATION_DECISION_REFUSE, AUTHORIZATION_DECISION_REFUSE_SHORT}:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message="Selected-target cycle generation authorization refused by operator decision.",
        )
    if not work_order_packet_dir.exists() or not work_order_packet_dir.is_dir():
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected-target cycle generation authorization refused; "
                f"work-order packet directory not found: {work_order_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, work_order_packet_dir)
    except ValueError as error:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                work_order_packet=work_order_packet_dir,
                decision=decision,
                message=(
                    "Selected-target cycle generation authorization refused; "
                    f"run is not registered: {subject.run_id}"
                ),
            )
        duplicate = _unconsumed_authorization_for_work_order(connection, subject)
        if duplicate is not None and subject.superseded_authorization_packet_id is None:
            return _refusal(
                work_order_packet=work_order_packet_dir,
                decision=decision,
                message=(
                    "Selected-target cycle generation authorization refused; "
                    "an unconsumed current-valid authorization already exists "
                    f"for this work order: {duplicate.id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_GENERATION_AUTHORIZATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_generation_authorization"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=LINEAGE_ID,
            created_by=CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_report = payloads[
            "selected_target_cycle_generation_authorization_gate_report"
        ]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_cycle_generation_authorization_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=LINEAGE_ID,
        )

    return SelectedTargetCycleGenerationAuthorizationResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _write_artifacts(
    *,
    writer: PacketWriter,
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="source_cycle_work_order_intake_summary",
        payload=_build_source_cycle_work_order_intake_summary(subject, packet_dir),
        parent_ids=list(subject.source_parent_ids),
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="authorization_decision_record",
        payload=_build_authorization_decision_record(subject),
        parent_ids=[artifacts["source_cycle_work_order_intake_summary"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="mechanism_visibility_generation_scope_review",
        payload=_build_mechanism_visibility_generation_scope_review(subject),
        parent_ids=[artifacts["authorization_decision_record"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="target_unit_authorization_scope",
        payload=_build_target_unit_authorization_scope(subject),
        parent_ids=[artifacts["mechanism_visibility_generation_scope_review"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="phrase_handling_authorization_policy",
        payload=_build_phrase_handling_authorization_policy(subject),
        parent_ids=[artifacts["target_unit_authorization_scope"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="materiality_semantic_validation_readiness_report",
        payload=_build_materiality_semantic_validation_readiness_report(subject),
        parent_ids=[artifacts["phrase_handling_authorization_policy"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="forbidden_overcorrection_and_regression_review",
        payload=_build_forbidden_overcorrection_and_regression_review(subject),
        parent_ids=[
            artifacts["materiality_semantic_validation_readiness_report"].id
        ],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="protected_living_event_gain_review",
        payload=_build_protected_living_event_gain_review(subject),
        parent_ids=[artifacts["forbidden_overcorrection_and_regression_review"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="post_generation_evidence_plan",
        payload=_build_post_generation_evidence_plan(subject),
        parent_ids=[artifacts["protected_living_event_gain_review"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="model_call_budget_report",
        payload=_build_model_call_budget_report(subject),
        parent_ids=[artifacts["post_generation_evidence_plan"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="generation_lock_transition_report",
        payload=_build_generation_lock_transition_report(subject),
        parent_ids=[artifacts["model_call_budget_report"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_cycle_generation_authorization_gate_report",
        payload=_build_gate_report(subject),
        parent_ids=[artifacts["generation_lock_transition_report"].id],
    )
    _write_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="project_health_scope_guard_report",
        payload=_build_project_health_scope_guard_report(subject),
        parent_ids=[
            artifacts[
                "selected_target_cycle_generation_authorization_gate_report"
            ].id
        ],
    )
    payloads["nonlocal_law_selected_target_cycle_generation_authorization_packet"] = (
        _build_packet_summary(subject=subject, packet_dir=packet_dir, payloads=payloads, artifacts=artifacts)
    )
    artifacts["nonlocal_law_selected_target_cycle_generation_authorization_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_cycle_generation_authorization_packet",
            payloads[
                "nonlocal_law_selected_target_cycle_generation_authorization_packet"
            ],
            parent_ids=[artifact.id for artifact in artifacts.values()],
        )
    )
    return payloads, artifacts


def _write_artifact(
    *,
    writer: PacketWriter,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> None:
    payloads[artifact_type] = payload
    artifacts[artifact_type] = writer.write_artifact(
        artifact_type,
        payload,
        parent_ids=parent_ids,
    )


def _load_subject(
    config: AbiConfig,
    work_order_packet_dir: Path,
) -> SelectedTargetCycleGenerationAuthorizationSubject:
    payloads = _load_required_payloads(work_order_packet_dir)
    packet = payloads["nonlocal_law_selected_target_cycle_work_order_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Selected-target cycle generation authorization refused; work-order packet missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or work_order_packet_dir.name)
    superseding_packet = _newer_corrected_work_order_packet_id(
        config=config,
        run_id=run_id,
        work_order_packet_dir=work_order_packet_dir,
        source_target_selection_packet_id=str(
            packet.get("source_target_selection_packet_id") or ""
        ),
    )
    if superseding_packet:
        raise ValueError(
            "Selected-target cycle generation authorization refused; work-order "
            f"packet is stale or superseded by newer corrected packet: {superseding_packet}."
        )
    _validate_work_order_payloads(payloads)
    packet_path = (
        work_order_packet_dir
        / "nonlocal_law_selected_target_cycle_work_order_packet.json"
    )
    with connect(config.db_path) as connection:
        work_order_artifact = _artifact_for_path(connection, packet_path)
    artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [work_order_artifact.id if work_order_artifact else None, *artifact_ids.values()]
    )
    supersession = _authorization_supersession_context(
        config,
        run_id=run_id,
        source_work_order_packet_id=packet_id,
    )
    if supersession.corrected_current_valid_authorization_exists:
        raise ValueError(
            "Selected-target cycle generation authorization refused; an "
            "unconsumed current-valid authorization already exists for this "
            "work order."
        )
    return SelectedTargetCycleGenerationAuthorizationSubject(
        run_id=run_id,
        work_order_packet_dir=work_order_packet_dir,
        work_order_packet_id=packet_id,
        work_order_packet_artifact_id=(
            work_order_artifact.id if work_order_artifact else None
        ),
        work_order_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        superseded_authorization_packet_id=(
            supersession.superseded_authorization_packet_id
        ),
        supersession_reason=supersession.supersession_reason,
        stale_authorization_surface_failures=supersession.stale_surface_failures,
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in NONLOCAL_LAW_SELECTED_TARGET_CYCLE_WORK_ORDER_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Selected-target cycle generation authorization refused; "
                f"work-order packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Selected-target cycle generation authorization refused; malformed "
            f"work-order artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_work_order_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["nonlocal_law_selected_target_cycle_work_order_packet"]
    scope = payloads["selected_mechanism_visibility_work_order_scope"]
    repair = payloads["mechanism_naming_reduction_repair_map"]
    inventory = payloads["explicit_mechanism_phrase_inventory"]
    units = payloads["selected_target_cycle_unit_map"]
    contract = payloads["future_generation_contract"]
    validation = payloads["materiality_and_semantic_validation_plan"]
    plan = payloads["ablation_and_reader_eval_plan"]
    gate = payloads["selected_target_cycle_work_order_gate_report"]
    health = payloads["project_health_scope_guard_report"]

    _require_bool(packet, "accepted", True)
    _require_equal(packet, "work_order_kind", WORK_ORDER_KIND)
    _require_equal(packet, "work_order_scope", WORK_ORDER_SCOPE)
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(packet, "selected_target_class", SELECTED_TARGET_CLASS)
    _require_bool(packet, "work_order_created", True)
    _require_bool(packet, "ready_for_generation_authorization_review", True)
    _require_bool(packet, "phrase_inventory_not_deletion_list", True)
    _require_bool(packet, "phrase_handling_required_for_future_generation", True)
    _require_bool(packet, "generation_schema_requires_phrase_handling_report", True)
    _require_bool(packet, "generation_authorization_surface_complete", True)
    _require_equal(packet, "phrase_inventory_policy", PHRASE_INVENTORY_POLICY)
    _require_bool(packet, "future_generation_authorized", False)
    _require_equal(packet, "generation_attempt_budget", 0)
    _require_bool(packet, "generation_authorized", False)
    _require_bool(packet, "candidate_generated", False)
    _require_equal(packet, "model_calls", 0)
    _require_bool(packet, "finalization_eligible", False)

    _require_equal(scope, "work_order_scope", WORK_ORDER_SCOPE)
    _require_bool(scope, "free_rewrite_allowed", False)
    _require_bool(scope, "generation_allowed", False)
    _require_equal(
        scope,
        "phrase_inventory_policy_consumed_by_future_generation",
        PHRASE_INVENTORY_POLICY,
    )
    for field_name in (
        "mechanism_naming_reduction_not_explanation_deletion",
        "mechanism_naming_reduction_not_causal_weakening",
        "mechanism_naming_reduction_not_vagueness",
        "phrase_pressure_points_require_contextual_repair",
    ):
        _require_bool(scope, field_name, True)

    for field_name in (
        "phrase_inventory_is_not_deletion_list",
        "repair_must_preserve_or_transform_each_pressure_point_contextually",
        "retained_explicit_phrase_allowed_if_earned",
        "transformed_phrase_must_preserve_causal_force",
        "deletion_only_allowed_if_not_needed_for_earned_explanation",
        "deletion_must_not_weaken_living_event_sequence",
    ):
        _require_bool(repair, field_name, True)

    _require_phrase_inventory_surface(inventory)
    if contract.get("allowed_authorization_decisions") != [
        AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE,
        AUTHORIZATION_DECISION_REFUSE_SHORT,
    ]:
        raise ValueError(
            "Selected-target cycle generation authorization refused; "
            "allowed_authorization_decisions must match cycle work-order contract."
        )
    _require_bool(contract, "generation_must_report_phrase_handling_decisions", True)
    _require_bool(
        contract,
        "generation_output_schema_requires_phrase_handling_report",
        True,
    )
    _require_bool(
        contract,
        "generation_must_treat_phrase_inventory_as_pressure_points_not_deletion_targets",
        True,
    )

    unit_ids = _string_list(units.get("target_unit_ids"))
    if unit_ids != list(TARGET_UNIT_IDS):
        raise ValueError(
            "Selected-target cycle generation authorization refused; target unit map is incomplete."
        )
    for requirement in MATERIALITY_REQUIREMENTS:
        _require_member(validation, "materiality_requirements", requirement)
    for requirement in SEMANTIC_REQUIREMENTS:
        _require_member(validation, "semantic_validation_requirements", requirement)
    _require_bool(validation, "phrase_handling_justification_required", True)
    _require_bool(validation, "phrase_inventory_not_deletion_list", True)
    for control_id in ABLATION_CONTROLS:
        _require_member(plan, "ablation_controls", control_id)
    for focus_item in READER_STATE_FOCUS:
        _require_member(plan, "reader_state_focus", focus_item)
    _require_bool(plan, "phrase_handling_ablation_required", True)
    for field_name in (
        "phrase_inventory_policy_present",
        "phrase_inventory_not_deletion_list",
        "phrase_handling_required_for_future_generation",
        "generation_schema_requires_phrase_handling_report",
    ):
        _require_bool(gate, field_name, True)
    for field_name in (
        "source_chain_coherent",
        "no_generation_path_introduced",
        "no_model_call_introduced",
        "no_candidate_introduced",
        "no_finality_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
        "generation_authorization_surface_complete",
        "phrase_inventory_safe_for_authorization",
    ):
        _require_bool(health, field_name, True)
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Selected-target cycle generation authorization refused; finality, "
            "phase-shift, strongest-rival defeat, candidate, or model-call leak "
            "appears in source work order."
        )


def _build_source_cycle_work_order_intake_summary(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_work_order_packet_dir": str(subject.work_order_packet_dir),
        "source_work_order_packet_artifact_id": subject.work_order_packet_artifact_id,
        "source_work_order_artifact_ids": dict(subject.work_order_artifact_ids),
        "source_family": SOURCE_FAMILY,
        "accepted_work_order": True,
        "work_order_current_valid": True,
        "source_chain_coherent": True,
        "operator_reviewed": True,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "source_cycle_work_order_intake_summary_v1_controller",
    }


def _build_authorization_decision_record(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "decision": AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "operator_reviewed": True,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "authorization_decision_record_v1_controller",
    }


def _build_mechanism_visibility_generation_scope_review(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "work_order_scope": WORK_ORDER_SCOPE,
        "generation_limited_to_selected_target": True,
        "free_rewrite_allowed": False,
        "generation_must_preserve_living_event_sequence_gain": True,
        "generation_must_reduce_mechanism_naming_materially": True,
        "generation_must_report_phrase_handling": True,
        "generation_must_treat_phrase_inventory_as_pressure_points_not_deletion_targets": True,
        "generation_must_not_delete_explanation_wholesale": True,
        "generation_must_not_reduce_object_activity": True,
        "generation_must_not_make_text_vague": True,
        "generation_must_not_expand_to_return_target": True,
        "generation_must_not_expand_to_chemistry_target": True,
        "generation_must_not_add_new_object_inventory": True,
        "generation_must_not_claim_finality": True,
        "generation_must_not_claim_strongest_rival_defeat": True,
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "mechanism_visibility_generation_scope_review_v1_controller",
    }


def _build_target_unit_authorization_scope(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    units_payload = subject.payloads["selected_target_cycle_unit_map"]
    rows = units_payload.get("target_units")
    if not isinstance(rows, list):
        rows = []
    target_units = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        unit_id = str(row.get("unit_id") or "")
        material = unit_id in MATERIAL_GENERATION_UNIT_IDS
        target_units.append(
            {
                "unit_id": unit_id,
                "authorized_for_generation": material,
                "authorized_role": (
                    "material_generation_unit"
                    if material
                    else "preservation_guard_unit"
                ),
                "material_change_allowed": material,
                "preservation_required": unit_id in PRESERVATION_OR_GUARD_UNIT_IDS,
                "validation_required": True,
            }
        )
    return {
        **_source_fields(subject),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "target_units": target_units,
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(PRESERVATION_OR_GUARD_UNIT_IDS),
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "target_unit_authorization_scope_v1_controller",
    }


def _build_phrase_handling_authorization_policy(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    inventory = subject.payloads["explicit_mechanism_phrase_inventory"]
    phrases = inventory.get("phrase_inventory")
    if not isinstance(phrases, list):
        phrases = []
    return {
        **_source_fields(subject),
        "phrase_inventory_policy": PHRASE_INVENTORY_POLICY,
        "phrase_inventory_not_deletion_list": True,
        "phrase_deletion_not_automatically_authorized": True,
        "generation_must_report_phrase_handling_decisions": True,
        "phrase_handling_report_required": True,
        "retained_explicit_phrases_allowed_if_earned": True,
        "transformed_phrases_must_preserve_causal_force": True,
        "deletion_only_allowed_if_not_needed_for_earned_explanation": True,
        "deletion_must_not_weaken_living_event_sequence": True,
        "all_phrase_pressure_points_carry_forward": True,
        "phrase_inventory_count": len(phrases),
        "phrase_inventory": [dict(item) for item in phrases if isinstance(item, dict)],
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "phrase_handling_authorization_policy_v1_controller",
    }


def _build_materiality_semantic_validation_readiness_report(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_requirements": list(SEMANTIC_REQUIREMENTS),
        "semantic_validation_requirements": list(SEMANTIC_REQUIREMENTS),
        "validation_required_before_candidate_evidence": True,
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "materiality_semantic_validation_readiness_report_v1_controller",
    }


def _build_forbidden_overcorrection_and_regression_review(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "delete_explanation_forbidden": True,
        "weaken_causality_forbidden": True,
        "reduce_object_activity_forbidden": True,
        "make_text_vague_forbidden": True,
        "generic_smoothing_forbidden": True,
        "new_object_inventory_forbidden": True,
        "phrase_inventory_as_deletion_list_forbidden": True,
        "return_target_expansion_forbidden": True,
        "chemistry_register_target_expansion_forbidden": True,
        "rival_imitation_forbidden": True,
        "strongest_rival_defeat_claim_forbidden": True,
        "finality_claim_forbidden": True,
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "forbidden_overcorrection_and_regression_review_v1_controller",
    }


def _build_protected_living_event_gain_review(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_0001_current_best_for_next_loop": True,
        "packet_0001_living_event_sequence_gain_must_be_preserved": True,
        "packet_0002_preserved_as_prior_working_reference": True,
        "packet_0063_preserved_as_historical_reference": True,
        "protected_gains": list(GAINS_TO_PRESERVE),
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "protected_living_event_gain_review_v1_controller",
    }


def _build_post_generation_evidence_plan(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "required_next_steps_after_generation": [
            "review_selected_target_cycle_candidate_before_ablation",
            "ablate_selected_target_cycle_candidate",
            "evaluate_selected_target_cycle_candidate_reader_state",
            "synthesize_selected_target_cycle_candidate_evidence",
            "loop_review_before_any_current_best_update",
        ],
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "post_generation_evidence_plan_v1_controller",
    }


def _build_model_call_budget_report(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "model_call_budget": 1,
        "model_calls_consumed": 0,
        "remaining_model_calls": 1,
        "model_calls_made_by_authorization": 0,
        "model_call_budget_for_future_generate_command_only": True,
        "client_must_be_explicit": True,
        "live_model_requires_allow_live_model": True,
        "worker": "model_call_budget_report_v1_controller",
    }


def _build_generation_lock_transition_report(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "generation_authorized": True,
        "next_generation_authorized": True,
        "authorization_packet_does_not_run_generation": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "future_generation_attempt_budget": 1,
        "generation_requires_separate_generate_command": True,
        "worker": "generation_lock_transition_report_v1_controller",
    }


def _build_gate_report(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    pass_gates = [
        "source_work_order_accepted",
        "source_work_order_current_valid",
        "mechanism_visibility_scope",
        "phrase_policy_present",
        "phrase_inventory_not_deletion_list",
        "phrase_handling_report_required",
        "material_generation_units_authorized",
        "preservation_units_guarded",
        "one_attempt_budget",
        "authorization_unconsumed",
        "no_candidate_generated",
        "no_model_calls",
        "no_final_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    ]
    failed_gates = [
        "authorization_consumed",
        "candidate_generated",
        "finalization_eligible",
        "strongest_rival_resolved",
    ]
    gate_results = [
        _gate_result(gate_name, True) for gate_name in pass_gates
    ] + [
        _gate_result(
            gate_name,
            False,
            [f"{gate_name} remains blocked"],
            record=False,
        )
        for gate_name in failed_gates
    ]
    blockers = [
        "authorization remains unconsumed",
        "candidate has not been generated",
        "ablation has not been executed",
        "reader-state evaluation has not been run",
        "synthesis has not been run",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "accepted": True,
        "passed": False,
        "eligible": False,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "strongest_rival_resolved": False,
        "strongest_rival_defeated_claimed": False,
        "passed_gates": pass_gates,
        "failed_gates": failed_gates,
        "gate_results": gate_results,
        "unresolved_blockers": blockers,
        "source_work_order_accepted": True,
        "source_work_order_current_valid": True,
        "mechanism_visibility_scope": True,
        "phrase_policy_present": True,
        "phrase_inventory_not_deletion_list": True,
        "phrase_handling_report_required": True,
        "material_generation_units_authorized": True,
        "preservation_units_guarded": True,
        "one_attempt_budget": True,
        "authorization_unconsumed": True,
        "no_candidate_generated": True,
        "no_model_calls": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "worker": "selected_target_cycle_generation_authorization_gate_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    checks = [
        _check("no_openai_calls", True),
        _check("no_text_generation", True),
        _check("no_candidate_created", True),
        _check("no_ablation_performed", True),
        _check("no_reader_state_evaluation_performed", True),
        _check("no_synthesis_performed", True),
        _check("authorization_unconsumed", True),
        _check("one_attempt_budget_only", True),
        _check("no_finalization", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
        _check("no_strongest_rival_defeat_claim", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "no_candidate_introduced": True,
        "no_model_call_introduced": True,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "authorization_does_not_create_candidate": True,
        "authorization_does_not_call_model": True,
        "one_attempt_only": True,
        "phrase_inventory_safe_for_generation_authorization": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type=(
            "nonlocal_law_selected_target_cycle_generation_authorization_packet"
        ),
    )
    return {
        **_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_cycle_generation_authorization_packet",
        ],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "authorization_artifacts": counts["produced_artifacts"],
        },
        "decision": AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(PRESERVATION_OR_GUARD_UNIT_IDS),
        "phrase_inventory_policy": PHRASE_INVENTORY_POLICY,
        "phrase_inventory_not_deletion_list": True,
        "phrase_handling_report_required": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_pressure_remains_blocking": True,
        "no_candidate_introduced": True,
        "no_model_call_introduced": True,
        "authorization_does_not_create_candidate": True,
        "authorization_does_not_call_model": True,
        "model_calls_made_by_authorization": 0,
        "model_call_budget_for_future_generate_command_only": True,
        "authorization_packet_does_not_run_generation": True,
        "ready_for_selected_target_cycle_candidate_generation": True,
        "next_recommended_action": NEXT_ACTION_AUTHORIZE,
        "gate_report": payloads[
            "selected_target_cycle_generation_authorization_gate_report"
        ],
        "worker": (
            "nonlocal_law_selected_target_cycle_generation_authorization_packet_v1_controller"
        ),
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads[
        "nonlocal_law_selected_target_cycle_generation_authorization_packet"
    ]
    return {
        **packet,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _source_fields(
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_work_order_packet_id": subject.work_order_packet_id,
        "superseded_authorization_packet_id": (
            subject.superseded_authorization_packet_id
        ),
        "supersession_reason": (
            subject.supersession_reason
            or packet.get("supersession_reason")
        ),
        "stale_authorization_surface_failures": list(
            subject.stale_authorization_surface_failures
        ),
        "superseded_work_order_packet_id": packet.get(
            "superseded_work_order_packet_id"
        ),
        "source_target_selection_packet_id": packet.get(
            "source_target_selection_packet_id"
        ),
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "prior_working_current_best_candidate_packet_id": packet.get(
            "prior_working_current_best_candidate_packet_id"
        ),
        "prior_historical_current_best_candidate_packet_id": packet.get(
            "prior_historical_current_best_candidate_packet_id"
        ),
        "selected_target_seed_id": packet.get("selected_target_seed_id"),
        "selected_risk_id": packet.get("selected_risk_id"),
        "selected_target_class": packet.get("selected_target_class"),
        "work_order_kind": packet.get("work_order_kind"),
        "work_order_scope": packet.get("work_order_scope"),
        "phrase_inventory_policy": packet.get("phrase_inventory_policy"),
        "phrase_inventory_not_deletion_list": packet.get(
            "phrase_inventory_not_deletion_list"
        ),
        "generation_schema_requires_phrase_handling_report": packet.get(
            "generation_schema_requires_phrase_handling_report"
        ),
        "generation_authorization_surface_complete": packet.get(
            "generation_authorization_surface_complete"
        ),
    }


def _packet(subject: SelectedTargetCycleGenerationAuthorizationSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_selected_target_cycle_work_order_packet"]


def _newer_corrected_work_order_packet_id(
    *,
    config: AbiConfig,
    run_id: str,
    work_order_packet_dir: Path,
    source_target_selection_packet_id: str,
) -> str | None:
    current_number = _packet_number(work_order_packet_dir.name)
    root = config.run_dir(run_id) / "nonlocal_law_selected_target_cycle_work_order"
    if current_number is None or not root.exists():
        return None
    for packet_dir in sorted(root.glob("packet_*"), reverse=True):
        packet_number = _packet_number(packet_dir.name)
        if packet_number is None or packet_number <= current_number:
            continue
        path = packet_dir / "nonlocal_law_selected_target_cycle_work_order_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_envelope_payload(path)
        except (OSError, ValueError, TypeError):
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_target_selection_packet_id")
            == source_target_selection_packet_id
            and _work_order_has_authorization_surface(payload)
        ):
            return str(payload.get("packet_id") or packet_dir.name)
    return None


def _work_order_has_authorization_surface(payload: dict[str, Any]) -> bool:
    return (
        payload.get("work_order_kind") == WORK_ORDER_KIND
        and payload.get("work_order_scope") == WORK_ORDER_SCOPE
        and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
        and payload.get("selected_risk_id") == SELECTED_RISK_ID
        and payload.get("phrase_inventory_policy") == PHRASE_INVENTORY_POLICY
        and payload.get("phrase_inventory_not_deletion_list") is True
        and payload.get("generation_schema_requires_phrase_handling_report") is True
        and payload.get("generation_authorization_surface_complete") is True
        and payload.get("future_generation_authorized") is False
        and payload.get("candidate_generated") is False
        and int(payload.get("model_calls") or 0) == 0
        and payload.get("finalization_eligible") is False
    )


def _authorization_supersession_context(
    config: AbiConfig,
    *,
    run_id: str,
    source_work_order_packet_id: str,
) -> AuthorizationSupersessionContext:
    root = (
        config.run_dir(run_id)
        / "nonlocal_law_selected_target_cycle_generation_authorization"
    )
    if not root.exists():
        return AuthorizationSupersessionContext(False)
    stale_packet_id: str | None = None
    stale_failures: tuple[str, ...] = ()
    for packet_dir in sorted(root.glob("packet_*")):
        packet = _optional_payload(
            packet_dir
            / "nonlocal_law_selected_target_cycle_generation_authorization_packet.json"
        )
        if (
            packet.get("accepted") is True
            and packet.get("source_work_order_packet_id") == source_work_order_packet_id
            and packet.get("generation_authorized") is True
            and packet.get("authorization_consumed") is False
            and packet.get("candidate_generated") is False
            and int(packet.get("model_calls") or 0) == 0
        ):
            failures = _authorization_surface_failures(packet_dir)
            if not failures:
                return AuthorizationSupersessionContext(True)
            stale_packet_id = str(packet.get("packet_id") or packet_dir.name)
            stale_failures = tuple(failures)
    if stale_packet_id is None:
        return AuthorizationSupersessionContext(False)
    return AuthorizationSupersessionContext(
        corrected_current_valid_authorization_exists=False,
        superseded_authorization_packet_id=stale_packet_id,
        supersession_reason=SUPERSESSION_REASON_AUTHORIZATION_SURFACE_MISSING,
        stale_surface_failures=stale_failures,
    )


def _authorization_surface_failures(packet_dir: Path) -> list[str]:
    failures: list[str] = []
    packet = _optional_payload(
        packet_dir
        / "nonlocal_law_selected_target_cycle_generation_authorization_packet.json"
    )
    units = _optional_payload(packet_dir / "target_unit_authorization_scope.json")
    phrase_policy = _optional_payload(
        packet_dir / "phrase_handling_authorization_policy.json"
    )
    budget = _optional_payload(packet_dir / "model_call_budget_report.json")
    lock = _optional_payload(packet_dir / "generation_lock_transition_report.json")
    health = _optional_payload(packet_dir / "project_health_scope_guard_report.json")
    for field_name, expected in (
        ("accepted", True),
        ("generation_authorized", True),
        ("authorization_consumed", False),
        ("candidate_generated", False),
        ("finalization_eligible", False),
        ("no_final_claim", True),
        ("no_phase_shift_claim", True),
        ("strongest_rival_defeated_claimed", False),
        ("ready_for_selected_target_cycle_candidate_generation", True),
    ):
        if packet.get(field_name) is not expected:
            failures.append(f"packet.{field_name}")
    if int(packet.get("model_calls") or 0) != 0:
        failures.append("packet.model_calls")
    if int(packet.get("generation_attempt_budget") or 0) != 1:
        failures.append("packet.generation_attempt_budget")
    if packet.get("material_generation_unit_ids") != list(MATERIAL_GENERATION_UNIT_IDS):
        failures.append("packet.material_generation_unit_ids")
    if packet.get("preservation_or_guard_unit_ids") != list(
        PRESERVATION_OR_GUARD_UNIT_IDS
    ):
        failures.append("packet.preservation_or_guard_unit_ids")
    _require_authorization_list(
        units,
        "material_generation_unit_ids",
        list(MATERIAL_GENERATION_UNIT_IDS),
        "target_unit_authorization_scope",
        failures,
    )
    _require_authorization_list(
        units,
        "preservation_or_guard_unit_ids",
        list(PRESERVATION_OR_GUARD_UNIT_IDS),
        "target_unit_authorization_scope",
        failures,
    )
    for field_name in (
        "phrase_inventory_not_deletion_list",
        "phrase_deletion_not_automatically_authorized",
        "generation_must_report_phrase_handling_decisions",
        "phrase_handling_report_required",
        "all_phrase_pressure_points_carry_forward",
    ):
        if phrase_policy.get(field_name) is not True:
            failures.append(f"phrase_policy.{field_name}")
    if phrase_policy.get("phrase_inventory_policy") != PHRASE_INVENTORY_POLICY:
        failures.append("phrase_policy.phrase_inventory_policy")
    if int(phrase_policy.get("phrase_inventory_count") or 0) != len(PHRASE_INVENTORY):
        failures.append("phrase_policy.phrase_inventory_count")
    for field_name, expected in (
        ("model_call_budget", 1),
        ("model_calls_consumed", 0),
        ("remaining_model_calls", 1),
        ("model_calls_made_by_authorization", 0),
    ):
        if int(budget.get(field_name) or 0) != expected:
            failures.append(f"budget.{field_name}")
    if lock.get("authorization_packet_does_not_run_generation") is not True:
        failures.append("lock.authorization_packet_does_not_run_generation")
    for field_name in (
        "project_health_scope_guard_passed",
        "no_candidate_introduced",
        "no_model_call_introduced",
        "no_finality_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
        "authorization_does_not_create_candidate",
        "authorization_does_not_call_model",
        "one_attempt_only",
        "phrase_inventory_safe_for_generation_authorization",
    ):
        if health.get(field_name) is not True:
            failures.append(f"health.{field_name}")
    return failures


def _unconsumed_authorization_for_work_order(
    connection: sqlite3.Connection,
    subject: SelectedTargetCycleGenerationAuthorizationSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if (
            artifact.type
            != "nonlocal_law_selected_target_cycle_generation_authorization_packet"
        ):
            continue
        payload = _artifact_payload(artifact)
        if (
            payload.get("accepted") is True
            and payload.get("source_work_order_packet_id")
            == subject.work_order_packet_id
            and payload.get("generation_authorized") is True
            and payload.get("authorization_consumed") is False
            and payload.get("candidate_generated") is False
            and not _authorization_surface_failures(Path(artifact.path).parent)
        ):
            return artifact
    return None


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        return {}
    return envelope["payload"]


def _artifact_for_path(
    connection: sqlite3.Connection,
    path: Path,
) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _artifact_ids_from_packet(packet_payload: dict[str, Any]) -> dict[str, str]:
    raw = packet_payload.get("artifact_ids")
    if not isinstance(raw, dict):
        return {}
    return {
        str(artifact_type): str(artifact_id)
        for artifact_type, artifact_id in raw.items()
        if isinstance(artifact_type, str)
        and isinstance(artifact_id, str)
        and artifact_id
    }


def _require_phrase_inventory_surface(payload: dict[str, Any]) -> None:
    _require_equal(payload, "phrase_inventory_policy", PHRASE_INVENTORY_POLICY)
    _require_bool(payload, "deletion_required", False)
    for field_name in (
        "all_phrases_require_transformation_or_earned_retention",
        "automatic_phrase_deletion_forbidden",
        "phrase_inventory_should_not_drive_wholesale_deletion",
        "future_generation_must_justify_retained_or_transformed_phrases",
        "transformation_or_earned_retention_required",
    ):
        _require_bool(payload, field_name, True)
    _require_bool(payload, "automatic_deletion_targets", False)
    phrases = payload.get("phrase_inventory")
    if not isinstance(phrases, list) or len(phrases) != len(PHRASE_INVENTORY):
        raise ValueError(
            "Selected-target cycle generation authorization refused; "
            "phrase inventory is incomplete."
        )
    expected_phrases = {str(item["phrase"]) for item in PHRASE_INVENTORY}
    actual_phrases = {
        str(item.get("phrase"))
        for item in phrases
        if isinstance(item, dict) and item.get("phrase")
    }
    if actual_phrases != expected_phrases:
        raise ValueError(
            "Selected-target cycle generation authorization refused; "
            "phrase inventory does not match source work order."
        )
    for item in phrases:
        if not isinstance(item, dict):
            raise ValueError(
                "Selected-target cycle generation authorization refused; "
                "phrase inventory item is malformed."
            )
        _require_bool(item, "deletion_required", False)
        for field_name in (
            "automatic_deletion_forbidden",
            "pressure_point_not_deletion_target",
            "transformation_or_earned_retention_required",
            "earned_retention_allowed",
            "context_sensitive_decision_required",
            "preserve_if_still_earned_after_object_pressure",
        ):
            _require_bool(item, field_name, True)


def _require_member(
    payload: dict[str, Any],
    field_name: str,
    expected_item: str,
) -> None:
    value = payload.get(field_name)
    if not isinstance(value, list) or expected_item not in value:
        raise ValueError(
            "Selected-target cycle generation authorization refused; "
            f"{field_name} is missing {expected_item}."
        )


def _require_equal(
    payload: dict[str, Any],
    field_name: str,
    expected: object,
) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(
            "Selected-target cycle generation authorization refused; "
            f"{field_name} must be {expected}."
        )


def _require_bool(
    payload: dict[str, Any],
    field_name: str,
    expected: bool,
) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(
            "Selected-target cycle generation authorization refused; "
            f"{field_name} must be {str(expected).lower()}."
        )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _optional_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return _read_envelope_payload(path)
    except (OSError, ValueError, TypeError):
        return {}


def _require_authorization_list(
    payload: dict[str, Any],
    field_name: str,
    expected: list[str],
    prefix: str,
    failures: list[str],
) -> None:
    value = payload.get(field_name)
    if not isinstance(value, list) or [str(item) for item in value] != expected:
        failures.append(f"{prefix}.{field_name}")


def _packet_number(packet_id: str) -> int | None:
    suffix = packet_id.removeprefix("packet_")
    return int(suffix) if suffix.isdecimal() else None


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    return any(_payload_has_forbidden_claim(payload) for payload in payloads.values())


def _payload_has_forbidden_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finalization_eligible",
                "final_artifact",
                "final_claim",
                "phase_shift_claim",
                "phase_shift_claimed",
                "strongest_rival_defeated",
                "strongest_rival_defeated_claimed",
                "strongest_rival_defeat_claim",
                "candidate_generated",
            } and item is True:
                return True
            if key == "model_calls" and isinstance(item, int) and item != 0:
                return True
            if key in {
                "no_final_claim",
                "no_phase_shift_claim",
                "no_strongest_rival_defeat_claim",
            } and item is False:
                return True
            if _payload_has_forbidden_claim(item):
                return True
    if isinstance(value, list):
        return any(_payload_has_forbidden_claim(item) for item in value)
    return False


def _check(
    check_id: str,
    passed: bool,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    return {
        "check_id": check_id,
        "passed": passed,
        "blocking_defects": blockers or ([] if passed else [f"{check_id} failed"]),
    }


def _gate_result(
    gate_name: str,
    passed: bool,
    blockers: list[str] | None = None,
    *,
    record: bool = True,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": blockers or ([] if passed else [f"{gate_name} failed"]),
        "recorded_as_passed_gate": record and passed,
    }


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _refusal(
    *,
    work_order_packet: Path,
    decision: str | None,
    message: str,
) -> SelectedTargetCycleGenerationAuthorizationResult:
    return SelectedTargetCycleGenerationAuthorizationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "work_order_packet": str(work_order_packet),
            "decision": decision,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "generation_attempt_budget": 0,
            "authorization_consumed": False,
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )
