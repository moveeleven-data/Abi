"""Controller authorization for one selected nonlocal law target generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_consolidated_target_selection import (
    SELECTED_RISK_ID,
    SELECTED_TARGET_SEED_ID,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
)
from abi.modules.nonlocal_law_selected_target_work_order import (
    ABLATION_CONTROLS,
    CORE_REPAIR_PRINCIPLE,
    GENERATION_AUTHORIZATION_ALLOWED_DECISIONS,
    GENERATION_CONTRACT_VERSION,
    MATERIALITY_POLICY_ID,
    NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_ARTIFACT_TYPES,
    NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
    PROMPT_CONTRACT_ID,
    READER_STATE_FOCUS,
    SEMANTIC_VALIDATOR_ID,
    TARGET_UNIT_IDS,
    WORK_ORDER_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_LINEAGE_ID = (
    "nonlocal_law_selected_target_generation_authorization_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_CREATED_BY = (
    "nonlocal_law_selected_target_generation_authorization_v1_controller"
)

AUTHORIZATION_DECISION_AUTHORIZE_ONE = (
    "authorize_one_bounded_selected_target_generation"
)
AUTHORIZATION_DECISION_REFUSE = "refuse_generation_authorization"
NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_DECISIONS = (
    AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    AUTHORIZATION_DECISION_REFUSE,
)

NEXT_ACTION_AUTHORIZE = "generate_selected_nonlocal_law_candidate"
NEXT_ACTION_REFUSE = "review_selected_target_work_order_before_generation_authorization"
NEXT_ACTION_GENERATOR_NOT_IMPLEMENTED = (
    "implement_selected_nonlocal_law_candidate_generation"
)
SUPERSESSION_REASON_AUTHORIZATION_SURFACE_MISSING = (
    "nonlocal_law_selected_target_generation_authorization_surface_missing"
)

MATERIAL_GENERATION_UNIT_IDS = (
    "static_trace_to_active_condition",
    "causal_bridge_between_object_events",
    "living_consequence_before_naming",
)
CONSTRAINT_UNIT_IDS = (
    "preserve_earned_explanation_timing",
    "preserve_packet_0002_object_field",
    "non_imitation_and_rival_guard",
    "carry_forward_unselected_risks",
)

NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_generation_authorization_packet",
    "source_work_order_intake_summary",
    "authorization_decision_record",
    "selected_target_generation_scope_review",
    "target_unit_authorization_scope",
    "materiality_semantic_validation_readiness_report",
    "forbidden_rival_and_regression_review",
    "protected_strengths_review",
    "post_generation_evidence_plan",
    "model_call_budget_report",
    "generation_lock_transition_report",
    "selected_target_generation_authorization_gate_report",
    "project_health_scope_guard_report",
)

REQUIRED_WORK_ORDER_ARTIFACTS = NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_ARTIFACT_TYPES


@dataclass(frozen=True)
class NonlocalLawSelectedTargetGenerationAuthorizationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawSelectedTargetGenerationAuthorizationSubject:
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


def run_nonlocal_law_selected_target_generation_authorization(
    config: AbiConfig,
    *,
    work_order_packet: Path | str,
    operator_reviewed: bool,
    decision: str | None,
) -> NonlocalLawSelectedTargetGenerationAuthorizationResult:
    initialize_database(config)
    work_order_packet_dir = _resolve_path(config, work_order_packet)
    if not operator_reviewed:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected nonlocal law generation authorization refused; "
                "--operator-reviewed is required."
            ),
        )
    if decision not in NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_DECISIONS:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected nonlocal law generation authorization refused; "
                "--decision must be one of: "
                + ", ".join(
                    NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_DECISIONS
                )
                + "."
            ),
        )
    if not work_order_packet_dir.exists() or not work_order_packet_dir.is_dir():
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected nonlocal law generation authorization refused; "
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

    if decision == AUTHORIZATION_DECISION_REFUSE:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Selected nonlocal law generation authorization refused by "
                "operator decision."
            ),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                work_order_packet=work_order_packet_dir,
                decision=decision,
                message=(
                    "Selected nonlocal law generation authorization refused; "
                    f"run is not registered: {subject.run_id}"
                ),
            )
        if subject.superseded_authorization_packet_id is None:
            duplicate = _unconsumed_authorization_for_work_order(connection, subject)
        else:
            duplicate = None
        if duplicate is not None:
            return _refusal(
                work_order_packet=work_order_packet_dir,
                decision=decision,
                message=(
                    "Selected nonlocal law generation authorization refused; "
                    "an unconsumed current-valid authorization already exists "
                    f"for this work order: {duplicate.id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_generation_authorization"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="source_work_order_intake_summary",
            payload=_build_source_work_order_intake_summary(subject, packet_dir),
            parent_ids=list(subject.source_parent_ids),
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="authorization_decision_record",
            payload=_build_authorization_decision_record(subject),
            parent_ids=[artifacts["source_work_order_intake_summary"].id],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="selected_target_generation_scope_review",
            payload=_build_selected_target_generation_scope_review(subject),
            parent_ids=[artifacts["authorization_decision_record"].id],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="target_unit_authorization_scope",
            payload=_build_target_unit_authorization_scope(subject),
            parent_ids=[artifacts["selected_target_generation_scope_review"].id],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="materiality_semantic_validation_readiness_report",
            payload=_build_materiality_semantic_validation_readiness_report(subject),
            parent_ids=[artifacts["target_unit_authorization_scope"].id],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="forbidden_rival_and_regression_review",
            payload=_build_forbidden_rival_and_regression_review(subject),
            parent_ids=[
                artifacts["materiality_semantic_validation_readiness_report"].id
            ],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="protected_strengths_review",
            payload=_build_protected_strengths_review(subject),
            parent_ids=[artifacts["forbidden_rival_and_regression_review"].id],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="post_generation_evidence_plan",
            payload=_build_post_generation_evidence_plan(subject),
            parent_ids=[artifacts["protected_strengths_review"].id],
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
            artifact_type="selected_target_generation_authorization_gate_report",
            payload=_build_gate_report(subject),
            parent_ids=[artifacts["generation_lock_transition_report"].id],
        )
        _write_artifact(
            writer=writer,
            artifacts=artifacts,
            payloads=payloads,
            artifact_type="project_health_scope_guard_report",
            payload=_build_project_health_scope_guard_report(subject, payloads),
            parent_ids=[
                artifacts["selected_target_generation_authorization_gate_report"].id
            ],
        )

        payloads["nonlocal_law_selected_target_generation_authorization_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["nonlocal_law_selected_target_generation_authorization_packet"] = (
            writer.write_artifact(
                "nonlocal_law_selected_target_generation_authorization_packet",
                payloads[
                    "nonlocal_law_selected_target_generation_authorization_packet"
                ],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type
                    != "nonlocal_law_selected_target_generation_authorization_packet"
                ],
            )
        )

        gate_report = payloads["selected_target_generation_authorization_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_generation_authorization_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_LINEAGE_ID,
        )

    return NonlocalLawSelectedTargetGenerationAuthorizationResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def run_selected_nonlocal_law_candidate_generation_placeholder(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path | str,
    allow_live_model: bool,
) -> NonlocalLawSelectedTargetGenerationAuthorizationResult:
    initialize_database(config)
    resolved_packet = _resolve_path(config, authorization_packet)
    stale_message = _stale_authorization_message(resolved_packet)
    if stale_message is not None:
        return NonlocalLawSelectedTargetGenerationAuthorizationResult(
            exit_code=1,
            payload={
                "accepted": False,
                "refused": True,
                "message": stale_message,
                "client": client_name,
                "authorization_packet": str(resolved_packet),
                "generation_authorized": True,
                "next_generation_authorized": True,
                "authorization_consumed": False,
                "candidate_generated": False,
                "model_calls": 0,
                "finalization_eligible": False,
                "no_final_claim": True,
                "no_phase_shift_claim": True,
                "strongest_rival_defeated_claimed": False,
                "next_recommended_action": NEXT_ACTION_GENERATOR_NOT_IMPLEMENTED,
            },
        )
    if not allow_live_model:
        message = (
            "Selected nonlocal law candidate generation refused; "
            "--allow-live-model is required."
        )
    else:
        message = (
            "Selected nonlocal law candidate generation refused; full generation "
            "worker is not implemented in this task."
        )
    return NonlocalLawSelectedTargetGenerationAuthorizationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "client": client_name,
            "authorization_packet": str(resolved_packet),
            "generation_authorized": True,
            "next_generation_authorized": True,
            "authorization_consumed": False,
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "next_recommended_action": NEXT_ACTION_GENERATOR_NOT_IMPLEMENTED,
        },
    )


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
) -> NonlocalLawSelectedTargetGenerationAuthorizationSubject:
    payloads = _load_required_payloads(work_order_packet_dir)
    packet = payloads["nonlocal_law_selected_target_work_order_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Selected nonlocal law generation authorization refused; "
        "work-order packet missing run_id.",
    )
    work_order_packet_id = str(packet.get("packet_id") or work_order_packet_dir.name)
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
            "Selected nonlocal law generation authorization refused; work-order "
            f"packet is stale or superseded by newer corrected packet: {superseding_packet}."
        )
    _validate_work_order_payloads(payloads)

    packet_path = (
        work_order_packet_dir / "nonlocal_law_selected_target_work_order_packet.json"
    )
    with connect(config.db_path) as connection:
        work_order_artifact = _artifact_for_path(connection, packet_path)
    work_order_artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [
            work_order_artifact.id if work_order_artifact else None,
            *work_order_artifact_ids.values(),
        ]
    )
    supersession = _authorization_supersession_context(
        config,
        run_id=run_id,
        source_work_order_packet_id=work_order_packet_id,
    )
    if supersession.corrected_current_valid_authorization_exists:
        raise ValueError(
            "Selected nonlocal law generation authorization refused; an "
            "unconsumed current-valid authorization already exists for this "
            "work order."
        )
    return NonlocalLawSelectedTargetGenerationAuthorizationSubject(
        run_id=run_id,
        work_order_packet_dir=work_order_packet_dir,
        work_order_packet_id=work_order_packet_id,
        work_order_packet_artifact_id=work_order_artifact.id
        if work_order_artifact
        else None,
        work_order_artifact_ids=work_order_artifact_ids,
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
    for artifact_type in REQUIRED_WORK_ORDER_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Selected nonlocal law generation authorization refused; "
                f"work-order packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; malformed "
            f"work-order artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_work_order_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["nonlocal_law_selected_target_work_order_packet"]
    scope = payloads["selected_target_work_order_scope"]
    repair = payloads["living_event_sequence_repair_map"]
    forbidden = payloads["forbidden_rival_imitation_inventory"]
    units = payloads["selected_target_unit_map"]
    contract = payloads["future_generation_contract"]
    validation = payloads["materiality_and_semantic_validation_plan"]
    evidence = payloads["ablation_and_reader_eval_plan"]
    health = payloads["project_health_scope_guard_report"]

    _require_bool(packet, "accepted", True)
    _require_equal(packet, "work_order_kind", NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND)
    _require_equal(packet, "work_order_scope", WORK_ORDER_SCOPE)
    _require_bool(packet, "work_order_created", True)
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(
        packet,
        "current_best_for_next_loop_packet_id",
        EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    )
    _require_equal(
        packet,
        "prior_current_best_candidate_packet_id",
        EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    )
    _require_bool(packet, "source_chain_coherent", True)
    _require_bool(packet, "ready_for_selected_target_generation_authorization", True)
    _require_bool(packet, "free_rewrite_allowed", False)
    _require_bool(packet, "generation_allowed", False)
    _require_bool(packet, "generation_authorized", False)
    _require_bool(packet, "candidate_generated", False)
    _require_equal(packet, "model_calls", 0)
    if packet.get("future_generation_authorized", False) is not False:
        _require_bool(packet, "future_generation_authorized", False)
    if int(packet.get("generation_attempt_budget") or 0) != 0:
        _require_equal(packet, "generation_attempt_budget", 0)

    _require_equal(scope, "work_order_scope", WORK_ORDER_SCOPE)
    _require_bool(scope, "free_rewrite_allowed", False)
    _require_bool(scope, "generation_allowed", False)
    _require_bool(scope, "work_order_bounded", True)
    _require_bool(scope, "work_order_authorizes_generation", False)
    _require_bool(scope, "generation_requires_separate_authorization", True)
    _require_equal(repair, "core_repair_principle", CORE_REPAIR_PRINCIPLE)
    _require_bool(repair, "causal_sequence_not_object_inventory", True)
    _require_bool(repair, "object_events_must_condition_later_perception", True)
    _require_bool(repair, "explanation_must_remain_earned", True)
    _require_bool(repair, "rival_imitation_forbidden", True)

    _require_equal(contract, "generation_contract_version", GENERATION_CONTRACT_VERSION)
    _require_equal(contract, "prompt_contract_id", PROMPT_CONTRACT_ID)
    _require_equal(contract, "materiality_policy_id", MATERIALITY_POLICY_ID)
    _require_equal(contract, "semantic_validator_id", SEMANTIC_VALIDATOR_ID)
    _require_bool(contract, "future_generation_requires_separate_authorization", True)
    _require_bool(contract, "future_generation_authorized", False)
    _require_equal(contract, "generation_attempt_budget", 0)
    _require_bool(contract, "ready_for_selected_target_generation_authorization", True)
    _require_bool(contract, "generation_authorization_requires_operator_review", True)
    if contract.get("generation_authorization_allowed_decisions") != list(
        GENERATION_AUTHORIZATION_ALLOWED_DECISIONS
    ):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; "
            "generation_authorization_allowed_decisions must match source contract."
        )

    target_unit_ids = _string_list(units.get("target_unit_ids"))
    missing_units = [
        unit_id for unit_id in TARGET_UNIT_IDS if unit_id not in target_unit_ids
    ]
    if missing_units:
        raise ValueError(
            "Selected nonlocal law generation authorization refused; target units "
            f"missing required units: {', '.join(missing_units)}."
        )
    if not _string_list(validation.get("materiality_requirements")):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; materiality "
            "requirements are missing."
        )
    if not _string_list(validation.get("semantic_validation_requirements")):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; semantic "
            "validation requirements are missing."
        )
    _require_bool(validation, "validation_required_before_candidate_evidence", True)
    if not _string_list(forbidden.get("forbidden_rival_objects_or_sequence")):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; forbidden "
            "rival inventory is missing."
        )
    if not _string_list(forbidden.get("forbidden_rival_imitation_modes")):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; forbidden "
            "rival inventory is missing."
        )
    _require_bool(forbidden, "rival_imitation_forbidden", True)
    _require_bool(forbidden, "selected_target_must_not_copy_rival_causal_sequence", True)
    if not set(ABLATION_CONTROLS) <= set(_string_list(evidence.get("ablation_controls"))):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; ablation "
            "controls are missing."
        )
    if not set(READER_STATE_FOCUS) <= set(_string_list(evidence.get("reader_state_focus"))):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; reader-state "
            "focus is missing."
        )
    _require_bool(health, "source_chain_coherent", True)
    _require_bool(health, "no_generation_path_introduced", True)
    _require_bool(health, "no_model_call_introduced", True)
    _require_bool(health, "no_candidate_introduced", True)
    _require_bool(health, "no_finality_claim", True)
    _require_bool(health, "no_phase_shift_claim", True)
    _require_bool(health, "no_strongest_rival_defeat_claim", True)

    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Selected nonlocal law generation authorization refused; finality, "
            "phase-shift, or strongest-rival defeat claim appears in the work "
            "order packet."
        )


def _build_source_work_order_intake_summary(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        **_source_fields(subject),
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_work_order_packet_dir": str(subject.work_order_packet_dir),
        "source_work_order_packet_artifact_id": subject.work_order_packet_artifact_id,
        "source_work_order_artifact_ids": dict(subject.work_order_artifact_ids),
        "source_work_order_accepted": True,
        "source_work_order_current_valid": True,
        "source_chain_coherent": True,
        "work_order_kind": packet.get("work_order_kind"),
        "work_order_scope": packet.get("work_order_scope"),
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
        "worker": "source_work_order_intake_summary_v1_controller",
    }


def _build_authorization_decision_record(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "decision": AUTHORIZATION_DECISION_AUTHORIZE_ONE,
        "operator_reviewed": True,
        "authorization_scope": "one_bounded_selected_target_generation",
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_allowed": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "authorization_decision_record_v1_controller",
    }


def _build_selected_target_generation_scope_review(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "work_order_scope": WORK_ORDER_SCOPE,
        "free_rewrite_allowed": False,
        "generation_allowed_by_this_authorization": True,
        "generation_limited_to_selected_target": True,
        "generation_must_not_expand_target_scope": True,
        "generation_must_preserve_packet_0002_object_field": True,
        "generation_must_preserve_earned_explanation_timing": True,
        "generation_must_not_copy_rival": True,
        "generation_must_not_claim_finality": True,
        "living_event_sequence_repair_only": True,
        "free_rewrite_forbidden": True,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "selected_target_generation_scope_review_v1_controller",
    }


def _build_target_unit_authorization_scope(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    units_payload = subject.payloads["selected_target_unit_map"]
    source_units = units_payload.get("target_units")
    if not isinstance(source_units, list):
        source_units = []
    target_units = []
    for unit in source_units:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("unit_id") or "")
        authorized_for_generation = unit_id in MATERIAL_GENERATION_UNIT_IDS
        target_units.append(
            {
                "unit_id": unit_id,
                "target_requirement": unit.get("target_requirement"),
                "material_change_required": unit.get("material_change_required"),
                "semantic_validation_requirement": unit.get(
                    "semantic_validation_requirement"
                ),
                "protected_strengths": _string_list(unit.get("protected_strengths")),
                "forbidden_regressions": _string_list(unit.get("forbidden_regressions")),
                "evidence_basis": _string_list(unit.get("evidence_basis")),
                "authorized_for_generation": authorized_for_generation,
                "authorized_role": (
                    "material_generation_unit"
                    if authorized_for_generation
                    else "preservation_or_guard_constraint"
                ),
                "authorization_role": (
                    "material_generation"
                    if authorized_for_generation
                    else "constraint_preservation_guard"
                ),
                "free_change_allowed": False,
                "must_preserve_if_constraint": unit_id in CONSTRAINT_UNIT_IDS,
            }
        )
    return {
        **_source_fields(subject),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "target_units": target_units,
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(CONSTRAINT_UNIT_IDS),
        "constraint_unit_ids": list(CONSTRAINT_UNIT_IDS),
        "target_unit_count": len(target_units),
        "generation_limited_to_selected_target": True,
        "generation_must_not_expand_target_scope": True,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "target_unit_authorization_scope_v1_controller",
    }


def _build_materiality_semantic_validation_readiness_report(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    validation = subject.payloads["materiality_and_semantic_validation_plan"]
    return {
        **_source_fields(subject),
        "materiality_requirements": list(validation["materiality_requirements"]),
        "semantic_validation_requirements": list(
            validation["semantic_validation_requirements"]
        ),
        "required_validation_checks": list(validation["required_validation_checks"]),
        "validation_required_before_candidate_evidence": True,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "validation_must_pass_before_authorization_consumed": True,
        "failed_validation_does_not_consume_authorization": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "materiality_semantic_validation_readiness_report_v1_controller",
    }


def _build_forbidden_rival_and_regression_review(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    forbidden = subject.payloads["forbidden_rival_imitation_inventory"]
    return {
        **_source_fields(subject),
        "forbidden_rival_sequence": list(forbidden["forbidden_rival_sequence"]),
        "forbidden_rival_modes": list(forbidden["forbidden_rival_modes"]),
        "forbidden_rival_objects_or_sequence": list(
            forbidden["forbidden_rival_objects_or_sequence"]
        ),
        "forbidden_rival_imitation_modes": list(
            forbidden["forbidden_rival_imitation_modes"]
        ),
        "forbidden_regressions": list(forbidden["forbidden_regressions"]),
        "rival_imitation_forbidden": True,
        "selected_target_must_not_copy_rival_causal_sequence": True,
        "generic_incident_addition_forbidden": True,
        "object_inventory_as_living_causality_forbidden": True,
        "strongest_rival_comparison_passed": False,
        "strongest_rival_pressure_remains_blocking": True,
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "forbidden_rival_and_regression_review_v1_controller",
    }


def _build_protected_strengths_review(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    protected = subject.payloads["protected_current_best_packet_0002_strengths"]
    protected_strengths = _unique(
        [
            *_string_list(protected.get("protected_strengths")),
            "source-chain through loop-review/consolidation/target-selection/work-order",
            "packet_0063 preserved as prior-current-best history",
        ]
    )
    return {
        **_source_fields(subject),
        "protected_strengths": protected_strengths,
        "protected_object_field": list(protected["protected_object_field"]),
        "packet_0063_preserved_as_prior_current_best_history": True,
        "packet_0002_object_field_protected": True,
        "earned_explanation_timing_protected": True,
        "proof_packet_id": protected.get("proof_packet_id"),
        "prior_reader_state_packet_id": protected.get("prior_reader_state_packet_id"),
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "protected_strengths_review_v1_controller",
    }


def _build_post_generation_evidence_plan(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    evidence = subject.payloads["ablation_and_reader_eval_plan"]
    return {
        **_source_fields(subject),
        "required_next_steps_after_generation": [
            "ablate_selected_nonlocal_law_candidate",
            "evaluate_selected_nonlocal_law_candidate_reader_state",
            "synthesize_selected_nonlocal_law_candidate_evidence",
        ],
        "ablation_controls": list(evidence["ablation_controls"]),
        "reader_state_focus": list(evidence["reader_state_focus"]),
        "synthesis_required_before_current_best_update": True,
        "finalization_forbidden_after_generation": True,
        "strongest_rival_pressure_remains_active_until_synthesis": True,
        "generation_authorized": True,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "post_generation_evidence_plan_v1_controller",
    }


def _build_model_call_budget_report(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
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
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "model_call_budget_report_v1_controller",
    }


def _build_generation_lock_transition_report(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "prior_generation_authorized": False,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "lock_transition": "selected_target_generation_unlocked_for_one_attempt",
        "generation_requires_separate_generate_command": True,
        "authorization_packet_does_not_run_generation": True,
        "worker": "generation_lock_transition_report_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_work_order_accepted", True),
        _gate_result("source_work_order_current_valid", True),
        _gate_result("source_chain_coherent", True),
        _gate_result("work_order_ready_for_generation_authorization", True),
        _gate_result("selected_target_exact", True),
        _gate_result("selected_risk_exact", True),
        _gate_result("generation_decision_valid", True),
        _gate_result("exactly_one_attempt_authorized", True),
        _gate_result("authorization_unconsumed", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result("no_strongest_rival_defeat_claim", True),
        _gate_result(
            "candidate_generated",
            False,
            ["candidate has not been generated"],
            record=False,
        ),
        _gate_result(
            "authorization_consumed",
            False,
            ["authorization remains unconsumed"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["generation authorization is not finalization evidence"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival remains blocking"],
            record=False,
        ),
    ]
    failed = [str(gate["gate_name"]) for gate in gate_results if not gate["passed"]]
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
        "decision": AUTHORIZATION_DECISION_AUTHORIZE_ONE,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_pressure_remains_blocking": True,
        "gate_results": gate_results,
        "failed_gates": failed,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "One bounded selected-target generation attempt is authorized but "
            "unconsumed; no candidate evidence exists yet."
        ),
        "worker": "selected_target_generation_authorization_gate_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
    payloads: dict[str, dict[str, object]],
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
        "source_work_order_accepted": True,
        "source_work_order_current_valid": True,
        "no_candidate_introduced": True,
        "no_model_call_introduced": True,
        "no_finality_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "authorization_does_not_create_candidate": True,
        "authorization_does_not_call_model": True,
        "authorization_does_not_finalize": True,
        "authorization_unconsumed": True,
        "one_attempt_only": True,
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "gate_report_available": "selected_target_generation_authorization_gate_report"
        in payloads,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_generation_authorization_packet",
    )
    validation = payloads["materiality_semantic_validation_readiness_report"]
    forbidden = payloads["forbidden_rival_and_regression_review"]
    protected = payloads["protected_strengths_review"]
    evidence = payloads["post_generation_evidence_plan"]
    units = payloads["target_unit_authorization_scope"]
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
            "nonlocal_law_selected_target_generation_authorization_packet",
        ],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "authorization_artifacts": counts["produced_artifacts"],
        },
        "decision": AUTHORIZATION_DECISION_AUTHORIZE_ONE,
        "authorization_scope": "one_bounded_selected_target_generation",
        "generation_authorized": True,
        "next_generation_authorized": True,
        "generation_attempt_budget": 1,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(CONSTRAINT_UNIT_IDS),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "target_units": list(units["target_units"]),
        "materiality_requirements": list(validation["materiality_requirements"]),
        "semantic_validation_requirements": list(
            validation["semantic_validation_requirements"]
        ),
        "forbidden_rival_sequence": list(forbidden["forbidden_rival_sequence"]),
        "forbidden_rival_modes": list(forbidden["forbidden_rival_modes"]),
        "forbidden_regressions": list(forbidden["forbidden_regressions"]),
        "protected_strengths": list(protected["protected_strengths"]),
        "post_generation_evidence_plan": evidence,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "no_candidate_introduced": True,
        "no_model_call_introduced": True,
        "no_finality_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "authorization_does_not_create_candidate": True,
        "authorization_does_not_call_model": True,
        "model_calls_made_by_authorization": 0,
        "model_call_budget_for_future_generate_command_only": True,
        "authorization_packet_does_not_run_generation": True,
        "ready_for_selected_target_candidate_generation": True,
        "generate_command_requires_allow_live_model": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_pressure_remains_blocking": True,
        "next_recommended_action": NEXT_ACTION_AUTHORIZE,
        "gate_report": payloads[
            "selected_target_generation_authorization_gate_report"
        ],
        "worker": (
            "nonlocal_law_selected_target_generation_authorization_packet_v1_controller"
        ),
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_generation_authorization_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _source_fields(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_work_order_packet_id": subject.work_order_packet_id,
        "superseded_authorization_packet_id": (
            subject.superseded_authorization_packet_id
        ),
        "supersession_reason": subject.supersession_reason,
        "stale_authorization_surface_failures": list(
            subject.stale_authorization_surface_failures
        ),
        "source_target_selection_packet_id": packet.get(
            "source_target_selection_packet_id"
        ),
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "law_id": packet.get("law_id"),
        "selected_target_seed_id": packet.get("selected_target_seed_id"),
        "selected_risk_id": packet.get("selected_risk_id"),
        "work_order_kind": packet.get("work_order_kind"),
        "work_order_scope": packet.get("work_order_scope"),
    }


def _packet(
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_selected_target_work_order_packet"]


def _newer_corrected_work_order_packet_id(
    *,
    config: AbiConfig,
    run_id: str,
    work_order_packet_dir: Path,
    source_target_selection_packet_id: str,
) -> str | None:
    current_number = _packet_number(work_order_packet_dir.name)
    root = config.run_dir(run_id) / "nonlocal_law_selected_target_work_order"
    if current_number is None or not root.exists():
        return None
    for packet_dir in sorted(root.glob("packet_*"), reverse=True):
        packet_number = _packet_number(packet_dir.name)
        if packet_number is None or packet_number <= current_number:
            continue
        path = packet_dir / "nonlocal_law_selected_target_work_order_packet.json"
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
            and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
            and payload.get("selected_risk_id") == SELECTED_RISK_ID
            and _work_order_has_authorization_surface(payload)
        ):
            return str(payload.get("packet_id") or packet_dir.name)
    return None


def _work_order_has_authorization_surface(payload: dict[str, Any]) -> bool:
    return (
        payload.get("ready_for_selected_target_generation_authorization") is True
        and payload.get("future_generation_authorized", False) is False
        and payload.get("generation_authorized") is False
        and payload.get("candidate_generated") is False
        and int(payload.get("generation_attempt_budget") or 0) == 0
        and bool(_string_list(payload.get("materiality_requirements")))
        and bool(_string_list(payload.get("semantic_validation_requirements")))
    )


def _authorization_supersession_context(
    config: AbiConfig,
    *,
    run_id: str,
    source_work_order_packet_id: str,
) -> AuthorizationSupersessionContext:
    root = config.run_dir(run_id) / "nonlocal_law_selected_target_generation_authorization"
    if not root.exists():
        return AuthorizationSupersessionContext(False)
    stale_packet_id: str | None = None
    stale_failures: tuple[str, ...] = ()
    for packet_dir in sorted(root.glob("packet_*")):
        packet = _optional_authorization_payload(
            packet_dir / "nonlocal_law_selected_target_generation_authorization_packet.json"
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
                return AuthorizationSupersessionContext(
                    corrected_current_valid_authorization_exists=True
                )
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
    packet = _optional_authorization_payload(
        packet_dir / "nonlocal_law_selected_target_generation_authorization_packet.json"
    )
    units = _optional_authorization_payload(
        packet_dir / "target_unit_authorization_scope.json"
    )
    health = _optional_authorization_payload(
        packet_dir / "project_health_scope_guard_report.json"
    )
    budget = _optional_authorization_payload(packet_dir / "model_call_budget_report.json")
    lock = _optional_authorization_payload(
        packet_dir / "generation_lock_transition_report.json"
    )

    _require_authorization_bool(packet, "accepted", True, "packet", failures)
    _require_authorization_bool(
        packet,
        "generation_authorized",
        True,
        "packet",
        failures,
    )
    _require_authorization_bool(
        packet,
        "authorization_consumed",
        False,
        "packet",
        failures,
    )
    _require_authorization_bool(
        packet,
        "candidate_generated",
        False,
        "packet",
        failures,
    )
    _require_authorization_int(packet, "model_calls", 0, "packet", failures)
    for field_name in (
        "no_candidate_introduced",
        "no_model_call_introduced",
        "no_finality_claim",
        "no_strongest_rival_defeat_claim",
        "authorization_does_not_create_candidate",
        "authorization_does_not_call_model",
        "model_call_budget_for_future_generate_command_only",
        "authorization_packet_does_not_run_generation",
        "ready_for_selected_target_candidate_generation",
        "generate_command_requires_allow_live_model",
    ):
        _require_authorization_bool(packet, field_name, True, "packet", failures)
    _require_authorization_int(
        packet,
        "model_calls_made_by_authorization",
        0,
        "packet",
        failures,
    )
    _require_authorization_list(
        packet,
        "material_generation_unit_ids",
        list(MATERIAL_GENERATION_UNIT_IDS),
        "packet",
        failures,
    )
    _require_authorization_list(
        packet,
        "preservation_or_guard_unit_ids",
        list(CONSTRAINT_UNIT_IDS),
        "packet",
        failures,
    )

    unit_rows = units.get("target_units")
    if not isinstance(unit_rows, list):
        failures.append("target_unit_authorization_scope.target_units")
    else:
        roles_by_unit = {
            str(row.get("unit_id")): row.get("authorized_role")
            for row in unit_rows
            if isinstance(row, dict)
        }
        for unit_id in MATERIAL_GENERATION_UNIT_IDS:
            if roles_by_unit.get(unit_id) != "material_generation_unit":
                failures.append(f"target_unit:{unit_id}.authorized_role")
        for unit_id in CONSTRAINT_UNIT_IDS:
            if roles_by_unit.get(unit_id) != "preservation_or_guard_constraint":
                failures.append(f"target_unit:{unit_id}.authorized_role")
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
        list(CONSTRAINT_UNIT_IDS),
        "target_unit_authorization_scope",
        failures,
    )

    for field_name in (
        "project_health_scope_guard_passed",
        "source_chain_coherent",
        "source_work_order_accepted",
        "source_work_order_current_valid",
        "no_candidate_introduced",
        "no_model_call_introduced",
        "no_finality_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
        "authorization_does_not_create_candidate",
        "authorization_does_not_call_model",
        "authorization_does_not_finalize",
        "authorization_unconsumed",
        "one_attempt_only",
    ):
        _require_authorization_bool(health, field_name, True, "health", failures)

    _require_authorization_int(budget, "model_call_budget", 1, "budget", failures)
    _require_authorization_int(budget, "model_calls_consumed", 0, "budget", failures)
    _require_authorization_int(budget, "remaining_model_calls", 1, "budget", failures)
    _require_authorization_int(
        budget,
        "model_calls_made_by_authorization",
        0,
        "budget",
        failures,
    )
    _require_authorization_bool(
        budget,
        "model_call_budget_for_future_generate_command_only",
        True,
        "budget",
        failures,
    )
    _require_authorization_bool(budget, "client_must_be_explicit", True, "budget", failures)
    _require_authorization_bool(
        budget,
        "live_model_requires_allow_live_model",
        True,
        "budget",
        failures,
    )

    _require_authorization_bool(
        lock,
        "authorization_packet_does_not_run_generation",
        True,
        "lock",
        failures,
    )
    return failures


def _optional_authorization_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return _read_envelope_payload(path)
    except (OSError, ValueError, TypeError):
        return {}


def _require_authorization_bool(
    payload: dict[str, Any],
    field_name: str,
    expected: bool,
    prefix: str,
    failures: list[str],
) -> None:
    if payload.get(field_name) is not expected:
        failures.append(f"{prefix}.{field_name}")


def _require_authorization_int(
    payload: dict[str, Any],
    field_name: str,
    expected: int,
    prefix: str,
    failures: list[str],
) -> None:
    if field_name not in payload or int(payload.get(field_name) or 0) != expected:
        failures.append(f"{prefix}.{field_name}")


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


def _stale_authorization_message(packet_dir: Path) -> str | None:
    failures = _authorization_surface_failures(packet_dir)
    if not failures:
        return None
    return (
        "Selected nonlocal law candidate generation refused; authorization "
        "packet is stale for generator handoff because required surface fields "
        f"are missing: {', '.join(failures)}."
    )


def _unconsumed_authorization_for_work_order(
    connection: sqlite3.Connection,
    subject: NonlocalLawSelectedTargetGenerationAuthorizationSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if (
            artifact.type
            != "nonlocal_law_selected_target_generation_authorization_packet"
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


def _packet_number(packet_id: str) -> int | None:
    suffix = packet_id.removeprefix("packet_")
    return int(suffix) if suffix.isdecimal() else None


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
) -> NonlocalLawSelectedTargetGenerationAuthorizationResult:
    return NonlocalLawSelectedTargetGenerationAuthorizationResult(
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


def _require_equal(
    payload: dict[str, Any],
    field_name: str,
    expected: object,
) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(
            "Selected nonlocal law generation authorization refused; "
            f"{field_name} must be {expected}."
        )


def _require_bool(
    payload: dict[str, Any],
    field_name: str,
    expected: bool,
) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(
            "Selected nonlocal law generation authorization refused; "
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


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    return any(_payload_has_final_or_phase_claim(payload) for payload in payloads.values())


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"finalization_eligible", "final_artifact", "final_claim"}:
                if item is True:
                    return True
            if key in {
                "phase_shift_claim",
                "phase_shift_claimed",
                "strongest_rival_defeated",
                "strongest_rival_defeated_claimed",
                "strongest_rival_defeat_claim",
            }:
                if item is True:
                    return True
            if key in {
                "no_final_claim",
                "no_phase_shift_claim",
                "no_strongest_rival_defeat_claim",
            }:
                if item is False:
                    return True
            if _payload_has_final_or_phase_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_final_or_phase_claim(item) for item in value)
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
