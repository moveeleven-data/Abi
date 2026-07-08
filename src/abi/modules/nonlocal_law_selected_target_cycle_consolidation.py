"""Deterministic selected-target loop consolidation packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.evidence_loop_review import SELECTED_TARGET_LOOP_REVIEW_ARTIFACT_TYPES
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_LINEAGE_ID = (
    "nonlocal_law_selected_target_cycle_consolidation_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_CREATED_BY = (
    "nonlocal_law_selected_target_cycle_consolidation_v1_controller"
)
NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_cycle_consolidation_packet",
    "source_selected_target_loop_review_intake_summary",
    "learned_selected_target_cycle_lesson",
    "non_universalization_guard_report",
    "working_current_best_transition_memory",
    "selected_target_evidence_memory",
    "active_risk_memory",
    "abi_ear_signal_memory",
    "strongest_rival_pressure_memory",
    "next_loop_constraint_memory",
    "next_target_selection_readiness_report",
    "selected_target_cycle_consolidation_gate_report",
    "project_health_scope_guard_report",
)

EXPECTED_LOOP_REVIEW_PACKET_ID = "packet_0002"
EXPECTED_SUPERSEDED_LOOP_REVIEW_PACKET_ID = "packet_0001"
EXPECTED_SUPERSESSION_REASON = "selected_target_loop_review_consolidation_surface_missing"
EXPECTED_SOURCE_SYNTHESIS_PACKET_ID = "packet_0001"
EXPECTED_SOURCE_READER_STATE_PACKET_ID = "packet_0005"
EXPECTED_SOURCE_ABLATION_PACKET_ID = "packet_0001"
EXPECTED_SOURCE_CANDIDATE_PACKET_ID = "packet_0001"
EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID = "packet_0002"
EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID = "packet_0063"
EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID = "packet_0001"
EXPECTED_UPDATE_METHOD = "selected_target_loop_review_packet_only"
EXPECTED_DECISION = "promote_packet_0001_to_working_current_best_for_next_loop"
EXPECTED_SELECTED_TARGET_SEED_ID = (
    "convert_static_retrospective_trace_to_living_event_sequence"
)
EXPECTED_SELECTED_RISK_ID = "event_sequence_may_remain_static"
EXPECTED_SELECTED_TARGET_EFFECT = "supported_but_incomplete"
EXPECTED_READER_STATE_SUPPORT = "supportive_with_active_risks"
EXPECTED_STRONGEST_RIVAL_STATUS = "narrowed_but_blocking"
EXPECTED_EVIDENCE_STRENGTH = "supportive_but_incomplete"

LEARNED_CYCLE_LESSON_ID = (
    "living_event_sequence_improves_selected_target_but_overexplained_mechanism_remains"
)
LESSON_SCOPE = "work_local"
TRANSFERABLE_PRINCIPLE_STATUS = "provisional_context_bound"
NEXT_RECOMMENDED_ACTION = "select_next_target_from_selected_target_cycle_consolidation"

EXPECTED_ACTIVE_RISK_IDS = (
    "causal_mechanism_overexplained",
    "room_begins_to_instruct_too_declarative",
    "later_seeing_must_be_changed_names_law_too_directly",
    "chemistry_register_unresolved",
    "conclusion_summarizes_instead_of_enacts_return",
    "object_field_delicacy_overloaded_by_causal_explanation",
    "strongest_rival_remains_blocking",
    "finalization_not_allowed",
)
ALLOWED_TARGET_SEED_IDS = (
    "reduce_causal_mechanism_naming",
    "enact_return_instead_of_summarizing_law",
    "integrate_or_remove_chemistry_register",
    "protect_object_field_delicacy",
)
RISK_TO_TARGET_SEED = {
    "causal_mechanism_overexplained": "reduce_causal_mechanism_naming",
    "room_begins_to_instruct_too_declarative": "reduce_causal_mechanism_naming",
    "later_seeing_must_be_changed_names_law_too_directly": (
        "reduce_causal_mechanism_naming"
    ),
    "chemistry_register_unresolved": "integrate_or_remove_chemistry_register",
    "conclusion_summarizes_instead_of_enacts_return": (
        "enact_return_instead_of_summarizing_law"
    ),
    "object_field_delicacy_overloaded_by_causal_explanation": (
        "protect_object_field_delicacy"
    ),
    "strongest_rival_remains_blocking": "protect_object_field_delicacy",
    "finalization_not_allowed": "reduce_causal_mechanism_naming",
}

PACKET_0001_ADVANTAGES = (
    "living-event sequence improved",
    "static trace reduction improved",
    "causal bridge improved",
    "consequence before naming improved",
    "packet_0002 gains preserved",
    "non-imitation preserved",
)
PACKET_0001_COSTS = (
    "causal mechanism overexplained",
    "explanation earned mixed",
    "room begins to instruct too declarative",
    "later seeing must be changed names law too directly",
    "chemistry register unresolved",
    "conclusion summarizes instead of enacts return",
    "object-field delicacy overloaded",
)
LESSON_STATEMENT = (
    "In this work, packet_0001 improved the selected target by making object "
    "traces more often feel like active conditions for later perception, but "
    "the repair remains incomplete because causal mechanism naming, declarative "
    "instruction, return-summary, register, and object-field overload risks remain."
)
TRANSFERABLE_PRINCIPLE = (
    "Preserve the living-event sequence gain, but future repair should reduce "
    "explicit mechanism naming and make causality felt through object relation "
    "rather than declared by the prose."
)
TRANSFER_WARNING = (
    "Do not universalize into \"always make object traces causally active\" or "
    "\"always add more causal links.\" The lesson applies only when a work "
    "already needs object traces to condition later perception and when explicit "
    "mechanism naming threatens delicacy."
)
STRONGEST_RIVAL_PRESSURE_SUMMARY = (
    "packet_0001 narrowed the selected-target gap, but strongest-rival pressure "
    "remains because mechanism naming, return-summary, chemistry-register, and "
    "object-field delicacy risks remain."
)
NEXT_LOOP_CONSTRAINTS = (
    "use packet_0001 as working current best for next loop",
    "preserve packet_0001's living-event sequence gain",
    "do not restore packet_0002 merely because packet_0001 has active risks",
    "do not finalise",
    "do not select target before consolidation",
    "do not create work order before target selection",
    "do not generate before target selection and authorization",
    "keep strongest-rival pressure blocking",
    "carry all active risks into next target selection",
)


@dataclass(frozen=True)
class SelectedTargetCycleConsolidationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SelectedTargetCycleConsolidationSubject:
    run_id: str
    loop_review_packet_dir: Path
    loop_review_packet_id: str
    loop_review_packet_artifact_id: str | None
    loop_review_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    active_risks: tuple[dict[str, Any], ...]
    target_options: tuple[dict[str, Any], ...]


def run_selected_target_cycle_consolidation(
    config: AbiConfig,
    *,
    loop_review_packet: Path | str,
    operator_reviewed: bool,
) -> SelectedTargetCycleConsolidationResult:
    initialize_database(config)
    loop_review_packet_dir = _resolve_path(config, loop_review_packet)
    if not operator_reviewed:
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Selected-target cycle consolidation refused; --operator-reviewed "
                "is required."
            ),
        )
    if not loop_review_packet_dir.exists() or not loop_review_packet_dir.is_dir():
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Selected-target cycle consolidation refused; loop-review packet "
                f"directory not found: {loop_review_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, loop_review_packet_dir)
        _validate_subject_for_consolidation(config, subject)
    except ValueError as error:
        return _refusal(loop_review_packet=loop_review_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                loop_review_packet=loop_review_packet_dir,
                message=(
                    "Selected-target cycle consolidation refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_consolidation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads, artifacts = _write_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_report = payloads["selected_target_cycle_consolidation_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_cycle_consolidation_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    return SelectedTargetCycleConsolidationResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    loop_review_packet_dir: Path,
) -> SelectedTargetCycleConsolidationSubject:
    payloads = _load_required_payloads(loop_review_packet_dir)
    loop_packet = payloads["nonlocal_law_selected_target_loop_review_packet"]
    run_id = _required_text(loop_packet.get("run_id"), "loop-review missing run_id")

    with connect(config.db_path) as connection:
        loop_artifact = _artifact_for_path(
            connection,
            loop_review_packet_dir / "nonlocal_law_selected_target_loop_review_packet.json",
        )

    artifact_ids = _string_dict(loop_packet.get("artifact_ids"))
    source_parent_ids = _unique(
        [
            loop_artifact.id if loop_artifact else None,
            *artifact_ids.values(),
        ]
    )
    loop_review_packet_id = str(loop_packet.get("packet_id") or loop_review_packet_dir.name)
    return SelectedTargetCycleConsolidationSubject(
        run_id=run_id,
        loop_review_packet_dir=loop_review_packet_dir,
        loop_review_packet_id=loop_review_packet_id,
        loop_review_packet_artifact_id=loop_artifact.id if loop_artifact else None,
        loop_review_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        active_risks=tuple(_active_risks(payloads)),
        target_options=tuple(_target_options(payloads)),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in SELECTED_TARGET_LOOP_REVIEW_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Selected-target cycle consolidation refused; loop-review packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Selected-target cycle consolidation refused; malformed "
                f"loop-review artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_subject_for_consolidation(
    config: AbiConfig,
    subject: SelectedTargetCycleConsolidationSubject,
) -> None:
    packet = _loop_packet(subject)
    _validate_no_forbidden_claims(subject.payloads)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Selected-target cycle consolidation refused; loop-review packet is not accepted."
        )
    if subject.loop_review_packet_id != EXPECTED_LOOP_REVIEW_PACKET_ID:
        raise ValueError(
            "Selected-target cycle consolidation refused; stale or unsupported "
            f"loop-review packet {subject.loop_review_packet_id}."
        )
    if _has_newer_matching_loop_review(config, subject):
        raise ValueError(
            "Selected-target cycle consolidation refused; loop-review packet is "
            "stale or superseded by a newer current-valid selected-target loop-review."
        )
    expected_pairs = (
        ("superseded_loop_review_packet_id", EXPECTED_SUPERSEDED_LOOP_REVIEW_PACKET_ID),
        ("supersession_reason", EXPECTED_SUPERSESSION_REASON),
        ("source_synthesis_packet_id", EXPECTED_SOURCE_SYNTHESIS_PACKET_ID),
        ("source_reader_state_packet_id", EXPECTED_SOURCE_READER_STATE_PACKET_ID),
        ("source_ablation_packet_id", EXPECTED_SOURCE_ABLATION_PACKET_ID),
        ("source_candidate_packet_id", EXPECTED_SOURCE_CANDIDATE_PACKET_ID),
        ("source_base_candidate_packet_id", EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID),
        (
            "prior_working_current_best_candidate_packet_id",
            EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID,
        ),
        ("current_best_for_next_loop_packet_id", EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID),
        (
            "prior_historical_current_best_candidate_packet_id",
            EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID,
        ),
        ("prior_current_best_candidate_packet_id", EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID),
        ("decision", EXPECTED_DECISION),
        ("current_best_update_method", EXPECTED_UPDATE_METHOD),
        ("selected_target_seed_id", EXPECTED_SELECTED_TARGET_SEED_ID),
        ("selected_risk_id", EXPECTED_SELECTED_RISK_ID),
        ("selected_target_effect", EXPECTED_SELECTED_TARGET_EFFECT),
        ("reader_state_support", EXPECTED_READER_STATE_SUPPORT),
        ("strongest_rival_status", EXPECTED_STRONGEST_RIVAL_STATUS),
    )
    for field_name, expected_value in expected_pairs:
        if packet.get(field_name) != expected_value:
            raise ValueError(
                "Selected-target cycle consolidation refused; "
                f"{field_name} must be {expected_value}."
            )
    bool_expectations = (
        ("current_best_updated", True),
        ("current_best_state_mutation_performed", False),
        ("global_state_mutation_performed", False),
        ("current_best_decision_packet_is_source_of_truth", True),
        ("strongest_rival_remains_blocking", True),
        ("strongest_rival_defeated_claimed", False),
        ("target_seed_options_exposed", True),
        ("next_target_not_selected", True),
        ("consolidation_required_before_next_target_selection", True),
        ("generation_authorized", False),
        ("candidate_generated", False),
        ("work_order_created", False),
        ("target_selected_for_next_cycle", False),
        ("finalization_eligible", False),
        ("no_final_claim", True),
        ("no_phase_shift_claim", True),
        ("no_strongest_rival_defeat_claim", True),
    )
    for field_name, expected_value in bool_expectations:
        if packet.get(field_name) is not expected_value:
            raise ValueError(
                "Selected-target cycle consolidation refused; "
                f"{field_name} must be {expected_value}."
            )
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError(
            "Selected-target cycle consolidation refused; loop review made model calls."
        )
    target_seed_option_ids = packet.get("target_seed_option_ids")
    if target_seed_option_ids != list(ALLOWED_TARGET_SEED_IDS):
        raise ValueError(
            "Selected-target cycle consolidation refused; target seed options mismatch."
        )
    if len(subject.active_risks) != len(EXPECTED_ACTIVE_RISK_IDS):
        raise ValueError(
            "Selected-target cycle consolidation refused; active risk count must be 8."
        )
    risk_ids = [str(risk.get("risk_id") or "") for risk in subject.active_risks]
    missing = [risk_id for risk_id in EXPECTED_ACTIVE_RISK_IDS if risk_id not in risk_ids]
    if missing:
        raise ValueError(
            "Selected-target cycle consolidation refused; active risks missing: "
            + ", ".join(missing)
        )
    option_ids = [str(option.get("target_seed_id") or "") for option in subject.target_options]
    if option_ids != list(ALLOWED_TARGET_SEED_IDS):
        raise ValueError(
            "Selected-target cycle consolidation refused; next target seed options mismatch."
        )
    if _accepted_consolidation_exists(config, subject):
        raise ValueError(
            "Selected-target cycle consolidation refused; selected-target "
            "consolidation already exists for this loop-review packet."
        )


def _write_artifacts(
    *,
    writer: PacketWriter,
    subject: SelectedTargetCycleConsolidationSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_selected_target_loop_review_intake_summary"] = (
        _build_source_intake(subject, packet_dir)
    )
    artifacts["source_selected_target_loop_review_intake_summary"] = writer.write_artifact(
        "source_selected_target_loop_review_intake_summary",
        payloads["source_selected_target_loop_review_intake_summary"],
        parent_ids=list(subject.source_parent_ids),
    )

    payloads["learned_selected_target_cycle_lesson"] = _build_lesson(subject)
    artifacts["learned_selected_target_cycle_lesson"] = writer.write_artifact(
        "learned_selected_target_cycle_lesson",
        payloads["learned_selected_target_cycle_lesson"],
        parent_ids=[artifacts["source_selected_target_loop_review_intake_summary"].id],
    )

    payloads["non_universalization_guard_report"] = (
        _build_non_universalization_guard(subject)
    )
    artifacts["non_universalization_guard_report"] = writer.write_artifact(
        "non_universalization_guard_report",
        payloads["non_universalization_guard_report"],
        parent_ids=[artifacts["learned_selected_target_cycle_lesson"].id],
    )

    payloads["working_current_best_transition_memory"] = _build_transition_memory(subject)
    artifacts["working_current_best_transition_memory"] = writer.write_artifact(
        "working_current_best_transition_memory",
        payloads["working_current_best_transition_memory"],
        parent_ids=[
            artifacts["source_selected_target_loop_review_intake_summary"].id,
            artifacts["learned_selected_target_cycle_lesson"].id,
        ],
    )

    payloads["selected_target_evidence_memory"] = _build_evidence_memory(subject)
    artifacts["selected_target_evidence_memory"] = writer.write_artifact(
        "selected_target_evidence_memory",
        payloads["selected_target_evidence_memory"],
        parent_ids=[
            artifacts["working_current_best_transition_memory"].id,
            artifacts["learned_selected_target_cycle_lesson"].id,
        ],
    )

    payloads["active_risk_memory"] = _build_active_risk_memory(subject)
    artifacts["active_risk_memory"] = writer.write_artifact(
        "active_risk_memory",
        payloads["active_risk_memory"],
        parent_ids=[
            artifacts["selected_target_evidence_memory"].id,
            artifacts["working_current_best_transition_memory"].id,
        ],
    )

    payloads["abi_ear_signal_memory"] = _build_abi_ear_signal_memory(subject)
    artifacts["abi_ear_signal_memory"] = writer.write_artifact(
        "abi_ear_signal_memory",
        payloads["abi_ear_signal_memory"],
        parent_ids=[
            artifacts["selected_target_evidence_memory"].id,
            artifacts["active_risk_memory"].id,
        ],
    )

    payloads["strongest_rival_pressure_memory"] = _build_strongest_rival_memory(subject)
    artifacts["strongest_rival_pressure_memory"] = writer.write_artifact(
        "strongest_rival_pressure_memory",
        payloads["strongest_rival_pressure_memory"],
        parent_ids=[
            artifacts["active_risk_memory"].id,
            artifacts["abi_ear_signal_memory"].id,
        ],
    )

    payloads["next_loop_constraint_memory"] = _build_next_loop_constraint_memory(subject)
    artifacts["next_loop_constraint_memory"] = writer.write_artifact(
        "next_loop_constraint_memory",
        payloads["next_loop_constraint_memory"],
        parent_ids=[
            artifacts["active_risk_memory"].id,
            artifacts["strongest_rival_pressure_memory"].id,
        ],
    )

    payloads["next_target_selection_readiness_report"] = _build_readiness_report(subject)
    artifacts["next_target_selection_readiness_report"] = writer.write_artifact(
        "next_target_selection_readiness_report",
        payloads["next_target_selection_readiness_report"],
        parent_ids=[
            artifacts["next_loop_constraint_memory"].id,
            artifacts["non_universalization_guard_report"].id,
        ],
    )

    payloads["selected_target_cycle_consolidation_gate_report"] = _build_gate_report(
        subject,
        payloads,
    )
    artifacts["selected_target_cycle_consolidation_gate_report"] = writer.write_artifact(
        "selected_target_cycle_consolidation_gate_report",
        payloads["selected_target_cycle_consolidation_gate_report"],
        parent_ids=[
            artifacts["source_selected_target_loop_review_intake_summary"].id,
            artifacts["learned_selected_target_cycle_lesson"].id,
            artifacts["active_risk_memory"].id,
            artifacts["next_target_selection_readiness_report"].id,
        ],
    )

    payloads["project_health_scope_guard_report"] = _build_health_report(subject)
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[
            artifacts["selected_target_cycle_consolidation_gate_report"].id,
            artifacts["strongest_rival_pressure_memory"].id,
        ],
    )

    payloads["nonlocal_law_selected_target_cycle_consolidation_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
    )
    artifacts["nonlocal_law_selected_target_cycle_consolidation_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_cycle_consolidation_packet",
            payloads["nonlocal_law_selected_target_cycle_consolidation_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type
                != "nonlocal_law_selected_target_cycle_consolidation_packet"
            ],
        )
    )

    return payloads, artifacts


def _build_source_intake(
    subject: SelectedTargetCycleConsolidationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _loop_packet(subject)
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_loop_review_packet_artifact_id": subject.loop_review_packet_artifact_id,
        "source_loop_review_artifact_ids": dict(subject.loop_review_artifact_ids),
        "loop_review_accepted": True,
        "loop_review_decision": packet.get("decision"),
        "source_loop_review_current_valid": True,
        "operator_reviewed": True,
        "consolidation_executed": True,
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "target_selection_requires_separate_command": True,
        "target_selected": False,
        "work_order_created": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_selected_target_loop_review_intake_summary_v1_controller",
    }


def _build_lesson(subject: SelectedTargetCycleConsolidationSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "lesson_id": LEARNED_CYCLE_LESSON_ID,
        "learned_cycle_lesson_id": LEARNED_CYCLE_LESSON_ID,
        "lesson_scope": LESSON_SCOPE,
        "lesson_statement": LESSON_STATEMENT,
        "evidence_basis": [
            "selected-target candidate packet_0001 accepted",
            "ablation packet_0001 defined living-event sequence controls",
            "live reader-state packet_0005 found living-event sequence improved",
            "live reader-state packet_0005 found static trace reduction improved",
            "live reader-state packet_0005 found causal bridge improved",
            "synthesis packet_0001 classified selected_target_effect supported_but_incomplete",
            "loop-review packet_0002 promoted packet_0001 to working current best for next loop",
        ],
        "lesson_limitations": [
            "not final proof",
            "strongest rival remains blocking",
            "explanation earned remains mixed",
            "causal mechanism overexplained",
            "conclusion still risks summarizing law instead of enacting return",
            "chemistry register unresolved",
            "object-field delicacy may be overloaded",
        ],
        "transferable_principle": TRANSFERABLE_PRINCIPLE,
        "transfer_warning": TRANSFER_WARNING,
        "transferable_principle_status": TRANSFERABLE_PRINCIPLE_STATUS,
        "universalized_rule_created": False,
        "memory_not_final_proof": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "learned_selected_target_cycle_lesson_v1_controller",
    }


def _build_non_universalization_guard(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "universalized_rule_created": False,
        "forbidden_universalizations": [
            "always add causal object sequences",
            "always make every object into a causal mechanism",
            "always explain that objects condition perception",
            "always prefer packet_0001 over packet_0002 in all dimensions",
            "strongest rival defeated",
            "finalization allowed",
        ],
        "correct_generalization_level": "work_local_selected_target_lesson",
        "apply_only_when": [
            "current work preserves packet_0001 as working current best",
            "selected target remains living-event sequence / overexplanation refinement",
            "object-field causality is needed but overnamed",
        ],
        "do_not_apply_when": [
            "future evidence says packet_0001 regresses",
            "next target concerns chemistry/register or return rather than mechanism naming",
            "a different artifact has different local physics",
        ],
        "target_selected": False,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "non_universalization_guard_report_v1_controller",
    }


def _build_transition_memory(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "prior_working_current_best_candidate_packet_id": (
            EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "current_best_for_next_loop_packet_id": (
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ),
        "prior_historical_current_best_candidate_packet_id": (
            EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID
        ),
        "transition_method": EXPECTED_UPDATE_METHOD,
        "global_state_mutation_performed": False,
        "current_best_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "packet_0002_preserved_as_prior_working_history": True,
        "packet_0063_preserved_as_historical_prior_best": True,
        "packet_0001_not_final": True,
        "not_finalization_evidence": True,
        "worker": "working_current_best_transition_memory_v1_controller",
    }


def _build_evidence_memory(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "selected_target_effect": EXPECTED_SELECTED_TARGET_EFFECT,
        "reader_state_support": EXPECTED_READER_STATE_SUPPORT,
        "evidence_strength": EXPECTED_EVIDENCE_STRENGTH,
        "packet_0001_advantages": list(PACKET_0001_ADVANTAGES),
        "packet_0001_costs": list(PACKET_0001_COSTS),
        "packet_0002_preserved_as_reference": True,
        "not_finalization_evidence": True,
        "strongest_rival_remains_blocking": True,
        "worker": "selected_target_evidence_memory_v1_controller",
    }


def _build_active_risk_memory(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    source = {str(risk.get("risk_id") or ""): risk for risk in subject.active_risks}
    risks: list[dict[str, object]] = []
    for risk_id in EXPECTED_ACTIVE_RISK_IDS:
        source_risk = source.get(risk_id, {})
        risks.append(
            {
                "risk_id": risk_id,
                "risk": source_risk.get("risk") or risk_id.replace("_", " "),
                "source_loop_review_packet_id": subject.loop_review_packet_id,
                "source_synthesis_packet_id": EXPECTED_SOURCE_SYNTHESIS_PACKET_ID,
                "source_reader_state_packet_id": EXPECTED_SOURCE_READER_STATE_PACKET_ID,
                "blocks_finalization": True,
                "carried_forward_to_next_loop": True,
                "not_selected_yet": True,
                "possible_next_target_seed": RISK_TO_TARGET_SEED[risk_id],
                "recommended_next_handling": source_risk.get(
                    "recommended_next_handling"
                )
                or "carry forward into selected-target target selection",
            }
        )
    return {
        **_source_fields(subject),
        "active_risk_count": len(risks),
        "active_risks": risks,
        "all_risks_block_finalization": True,
        "target_selected": False,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "active_risk_memory_v1_controller",
    }


def _build_abi_ear_signal_memory(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "living_event_sequence_signal": "improved_but_incomplete",
        "overexplained_mechanism_signal": "active_risk",
        "declarative_instruction_signal": "active_risk",
        "law_naming_signal": "active_risk",
        "chemistry_register_signal": "unresolved",
        "return_enactment_signal": "active_risk",
        "object_field_delicacy_signal": "mixed_or_active_risk",
        "non_imitation_signal": "preserved",
        "strongest_rival_signal": EXPECTED_STRONGEST_RIVAL_STATUS,
        "memory_not_final_proof": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "abi_ear_signal_memory_v1_controller",
    }


def _build_strongest_rival_memory(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "strongest_rival_status": EXPECTED_STRONGEST_RIVAL_STATUS,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "pressure_summary": STRONGEST_RIVAL_PRESSURE_SUMMARY,
        "blocks_finalization": True,
        "worker": "strongest_rival_pressure_memory_v1_controller",
    }


def _build_next_loop_constraint_memory(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "next_loop_constraints": list(NEXT_LOOP_CONSTRAINTS),
        "target_selection_must_use_consolidated_risk_memory": True,
        "do_not_generate_before_target_selection": True,
        "do_not_create_work_order_before_target_selection": True,
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "target_selection_requires_separate_command": True,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "next_loop_constraint_memory_v1_controller",
    }


def _build_readiness_report(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "target_selection_requires_separate_command": True,
        "allowed_target_seed_ids": list(ALLOWED_TARGET_SEED_IDS),
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "work_order_authorized": False,
        "generation_authorized": False,
        "target_selected": False,
        "work_order_created": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "next_target_selection_readiness_report_v1_controller",
    }


def _build_gate_report(
    subject: SelectedTargetCycleConsolidationSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    pass_gates = (
        "source_loop_review_accepted",
        "source_loop_review_current_valid",
        "packet_0001_working_current_best",
        "packet_0002_preserved",
        "packet_0063_preserved",
        "lesson_recorded",
        "risks_carried_forward",
        "target_seed_options_preserved",
        "no_target_selected",
        "no_work_order",
        "no_generation",
        "no_candidate",
        "no_model_calls",
        "no_final_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    )
    block_gates = (
        "target_selection_authorized",
        "work_order_authorized",
        "generation_authorized",
        "finalization_eligible",
        "strongest_rival_resolved",
    )
    gate_results = [
        _gate_result(gate_name, True) for gate_name in pass_gates
    ] + [
        _gate_result(gate_name, False, [f"{gate_name} remains blocked"])
        for gate_name in block_gates
    ]
    blockers = [
        "target selection requires a separate command",
        "work order is not authorized",
        "generation is not authorized",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "consolidation_executed": True,
        "learned_cycle_lesson_id": LEARNED_CYCLE_LESSON_ID,
        "lesson_scope": payloads["learned_selected_target_cycle_lesson"]["lesson_scope"],
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "target_selected": False,
        "work_order_created": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_results": gate_results,
        "passed_gates": list(pass_gates),
        "failed_gates": list(block_gates),
        "unresolved_blockers": blockers,
        "worker": "selected_target_cycle_consolidation_gate_report_v1_controller",
    }


def _build_health_report(
    subject: SelectedTargetCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "source_loop_review_accepted": True,
        "source_loop_review_current_valid": True,
        "no_openai_calls": True,
        "no_target_selection_introduced": True,
        "no_work_order_introduced": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_introduced": True,
        "no_global_state_mutation": True,
        "global_state_mutation_performed": False,
        "current_best_state_mutation_performed": False,
        "no_finality_claim": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "strongest_rival_defeated_claimed": False,
        "consolidation_only": True,
        "finalization_eligible": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: SelectedTargetCycleConsolidationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=(
            NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_ARTIFACT_TYPES
        ),
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_cycle_consolidation_packet",
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
            "nonlocal_law_selected_target_cycle_consolidation_packet",
        ],
        "counts": {**counts, "model_calls": 0, "candidate_artifacts_created": 0},
        "consolidation_executed": True,
        "learned_cycle_lesson_id": LEARNED_CYCLE_LESSON_ID,
        "lesson_scope": LESSON_SCOPE,
        "transferable_principle_status": TRANSFERABLE_PRINCIPLE_STATUS,
        "universalized_rule_created": False,
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "target_selection_requires_separate_command": True,
        "work_order_authorized": False,
        "generation_authorized": False,
        "target_selected": False,
        "work_order_created": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "allowed_target_seed_ids": list(ALLOWED_TARGET_SEED_IDS),
        "active_risk_count": len(payloads["active_risk_memory"]["active_risks"]),
        "gate_report": payloads["selected_target_cycle_consolidation_gate_report"],
        "worker": (
            "nonlocal_law_selected_target_cycle_consolidation_packet_v1_controller"
        ),
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_cycle_consolidation_packet"]
    return {
        **packet,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
    }


def _source_fields(subject: SelectedTargetCycleConsolidationSubject) -> dict[str, object]:
    packet = _loop_packet(subject)
    return {
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_ablation_packet_id": packet.get("source_ablation_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_base_candidate_packet_id": packet.get("source_base_candidate_packet_id"),
        "prior_working_current_best_candidate_packet_id": packet.get(
            "prior_working_current_best_candidate_packet_id"
        ),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "prior_historical_current_best_candidate_packet_id": packet.get(
            "prior_historical_current_best_candidate_packet_id"
        ),
        "selected_target_seed_id": packet.get("selected_target_seed_id"),
        "selected_risk_id": packet.get("selected_risk_id"),
        "law_id": packet.get("law_id") or DISCOVERED_LOCAL_LAW_ID,
    }


def _loop_packet(subject: SelectedTargetCycleConsolidationSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_selected_target_loop_review_packet"]


def _active_risks(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    risks = payloads["active_risk_carry_forward_report"].get("active_risks")
    if not isinstance(risks, list):
        return []
    return [risk for risk in risks if isinstance(risk, dict)]


def _target_options(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    options = payloads["next_cycle_target_seed_report"].get("next_cycle_target_options")
    if isinstance(options, list):
        return [option for option in options if isinstance(option, dict)]
    return []


def _has_newer_matching_loop_review(
    config: AbiConfig,
    subject: SelectedTargetCycleConsolidationSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_selected_target_loop_review"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= subject.loop_review_packet_id:
            continue
        path = packet_dir / "nonlocal_law_selected_target_loop_review_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_synthesis_packet_id")
            == _loop_packet(subject).get("source_synthesis_packet_id")
            and payload.get("current_best_decision_packet_is_source_of_truth") is True
            and payload.get("current_best_for_next_loop_packet_id")
            == EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
            and payload.get("target_seed_options_exposed") is True
        ):
            return True
    return False


def _accepted_consolidation_exists(
    config: AbiConfig,
    subject: SelectedTargetCycleConsolidationSubject,
) -> bool:
    root = (
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_cycle_consolidation"
    )
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        path = packet_dir / "nonlocal_law_selected_target_cycle_consolidation_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_loop_review_packet_id")
            == subject.loop_review_packet_id
            and payload.get("consolidation_executed") is True
            and payload.get("target_selected") is False
            and payload.get("work_order_created") is False
            and payload.get("generation_authorized") is False
            and payload.get("candidate_generated") is False
            and int(payload.get("model_calls") or 0) == 0
            and payload.get("finalization_eligible") is False
        ):
            return True
    return False


def _validate_no_forbidden_claims(payloads: dict[str, dict[str, Any]]) -> None:
    if _payload_has_forbidden_claim(payloads):
        raise ValueError(
            "Selected-target cycle consolidation refused; finality, phase-shift, "
            "rival-defeat, generation, target-selection, or work-order claim appears."
        )


def _payload_has_forbidden_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finality_claimed",
                "phase_shift_claimed",
                "strongest_rival_defeated_claimed",
                "candidate_superiority_claimed",
                "final_artifact",
                "final_claim",
            } and item is True:
                return True
            if key in {
                "generation_authorized",
                "candidate_generated",
                "work_order_created",
                "target_selected",
                "target_selected_for_next_cycle",
            } and item is True:
                return True
            if key == "finalization_eligible" and item is True:
                return True
            if _payload_has_forbidden_claim(item):
                return True
    if isinstance(value, list):
        return any(_payload_has_forbidden_claim(item) for item in value)
    return False


def _read_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(f"Malformed packet artifact: {path.name}")
    return envelope["payload"]


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _gate_result(
    gate_name: str,
    passed: bool,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": list(blockers or []),
    }


def _required_text(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Selected-target cycle consolidation refused; {message}.")


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(item, str) and item
    }


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config.root / candidate


def _refusal(
    *,
    loop_review_packet: Path,
    message: str,
) -> SelectedTargetCycleConsolidationResult:
    return SelectedTargetCycleConsolidationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "message": message,
            "loop_review_packet": str(loop_review_packet),
            "consolidation_executed": False,
            "ready_for_next_target_selection": False,
            "target_selection_authorized": False,
            "target_selected": False,
            "work_order_created": False,
            "work_order_authorized": False,
            "generation_authorized": False,
            "candidate_generated": False,
            "model_calls": 0,
            "counts": {"model_calls": 0},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )
