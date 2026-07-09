"""Deterministic target selection from selected-target cycle consolidation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.nonlocal_law_selected_target_cycle_consolidation import (
    ALLOWED_TARGET_SEED_IDS,
    EXPECTED_ACTIVE_RISK_IDS,
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_LOOP_REVIEW_PACKET_ID as EXPECTED_SOURCE_LOOP_REVIEW_PACKET_ID,
    EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID,
    EXPECTED_READER_STATE_SUPPORT,
    EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID,
    EXPECTED_SOURCE_CANDIDATE_PACKET_ID,
    EXPECTED_SOURCE_READER_STATE_PACKET_ID,
    EXPECTED_SOURCE_SYNTHESIS_PACKET_ID,
    EXPECTED_STRONGEST_RIVAL_STATUS,
    EXPECTED_SELECTED_TARGET_EFFECT,
    LEARNED_CYCLE_LESSON_ID,
    LESSON_SCOPE,
    NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_ARTIFACT_TYPES,
    TRANSFERABLE_PRINCIPLE_STATUS,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_LINEAGE_ID = (
    "nonlocal_law_selected_target_cycle_target_selection_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_CREATED_BY = (
    "nonlocal_law_selected_target_cycle_target_selection_v1_controller"
)
NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_cycle_target_selection_packet",
    "source_selected_target_cycle_consolidation_intake_summary",
    "target_selection_criteria_report",
    "target_candidate_ranking_report",
    "selected_target_decision",
    "selected_risk_evidence_report",
    "non_selected_risk_carry_forward_report",
    "working_current_best_context_report",
    "non_universalization_guard_carry_forward_report",
    "strongest_rival_blocker_carry_forward_report",
    "next_work_order_readiness_report",
    "selected_target_cycle_target_selection_gate_report",
    "project_health_scope_guard_report",
)

EXPECTED_CONSOLIDATION_PACKET_ID = "packet_0001"
SELECTED_TARGET_SEED_ID = "reduce_causal_mechanism_naming"
SELECTED_RISK_ID = "causal_mechanism_overexplained"
SELECTED_TARGET_CLASS = "mechanism_naming_reduction_target"
TARGET_SCOPE = "selected_target_mechanism_visibility_repair"
WORK_ORDER_TARGET_SCOPE = "mechanism_visibility_repair"
TARGET_STATEMENT = (
    "Preserve packet_0001's living-event sequence gain while reducing explicit "
    "causal-mechanism language so object relations carry the perceptual change "
    "with less declaration."
)
CORE_REPAIR_PRINCIPLE = (
    "Make causality felt through the object field rather than repeatedly naming "
    "the law that perception is being conditioned."
)
WORK_ORDER_PLANNING_PRINCIPLE = (
    "The work order must not delete explanation, reduce object activity, or make "
    "the text vague. It must move causal meaning from explicit mechanism "
    "language into object relation, syntax, timing, and perceptual sequence."
)
NEXT_RECOMMENDED_ACTION = "plan_selected_target_cycle_work_order"
SUPERSESSION_REASON_WORK_ORDER_SURFACE_MISSING = (
    "selected_target_cycle_target_selection_work_order_surface_missing"
)
SELECTED_RISK_CLUSTER = (
    "causal_mechanism_overexplained",
    "room_begins_to_instruct_too_declarative",
    "later_seeing_must_be_changed_names_law_too_directly",
)
NON_SELECTED_TARGET_SEED_IDS = (
    "enact_return_instead_of_summarizing_law",
    "protect_object_field_delicacy",
    "integrate_or_remove_chemistry_register",
)
NON_SELECTED_RISK_IDS = (
    "conclusion_summarizes_instead_of_enacts_return",
    "chemistry_register_unresolved",
    "object_field_delicacy_overloaded_by_causal_explanation",
    "strongest_rival_remains_blocking",
    "finalization_not_allowed",
)
SELECTION_CRITERIA = (
    "preserve_packet_0001_living_event_sequence_gain",
    "address_most_central_remaining_violation",
    "increase_abi_ear_precision",
    "improve_whole_work_causal_path_without_finalization",
    "avoid_turning_diagnosis_into_prose",
)
SELECTION_NOT_BASED_ON = (
    "surface polish",
    "generic clarity",
    "new object inventory",
    "broader rewrite",
    "strongest-rival defeat",
    "finalization",
)
RANKED_TARGETS = (
    {
        "rank": 1,
        "target_seed_id": SELECTED_TARGET_SEED_ID,
        "source_risk_ids": list(SELECTED_RISK_CLUSTER),
        "reason": (
            "This is the central risk cluster produced by the successful "
            "living-event repair. It preserves the gain while testing whether "
            "causality can be felt through object relation rather than declared."
        ),
        "work_order_implication": (
            "Plan a bounded repair that preserves packet_0001's living-event "
            "sequence while reducing explicit causal-mechanism language."
        ),
    },
    {
        "rank": 2,
        "target_seed_id": "enact_return_instead_of_summarizing_law",
        "source_risk_ids": ["conclusion_summarizes_instead_of_enacts_return"],
        "reason": (
            "Structurally important and high priority, but should follow or be "
            "constrained by mechanism-naming reduction because return will "
            "continue to summarize if the law is still overdeclared."
        ),
        "work_order_implication": (
            "Carry forward as high-priority next-cycle risk; do not solve in "
            "this work order unless needed as preservation constraint."
        ),
    },
    {
        "rank": 3,
        "target_seed_id": "protect_object_field_delicacy",
        "source_risk_ids": ["object_field_delicacy_overloaded_by_causal_explanation"],
        "reason": (
            "Important constraint and potential later target, but partly "
            "overlaps with mechanism-naming reduction."
        ),
        "work_order_implication": (
            "Treat as a guard constraint on the selected work order: reduction "
            "of mechanism naming must not make objects less active or merely "
            "atmospheric."
        ),
    },
    {
        "rank": 4,
        "target_seed_id": "integrate_or_remove_chemistry_register",
        "source_risk_ids": ["chemistry_register_unresolved"],
        "reason": (
            "Real register issue, but narrower than the current central "
            "mechanism/return problem."
        ),
        "work_order_implication": (
            "Carry forward unchanged; do not solve in the selected work order."
        ),
    },
)


@dataclass(frozen=True)
class SelectedTargetCycleTargetSelectionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SelectedTargetCycleTargetSelectionSubject:
    run_id: str
    consolidation_packet_dir: Path
    consolidation_packet_id: str
    consolidation_packet_artifact_id: str | None
    consolidation_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    active_risks: tuple[dict[str, Any], ...]
    allowed_target_seed_ids: tuple[str, ...]
    superseded_target_selection_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetSelectionSupersessionContext:
    corrected_current_valid_target_selection_exists: bool
    superseded_target_selection_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


def run_selected_target_cycle_target_selection(
    config: AbiConfig,
    *,
    consolidation_packet: Path | str,
    operator_reviewed: bool,
) -> SelectedTargetCycleTargetSelectionResult:
    initialize_database(config)
    consolidation_packet_dir = _resolve_path(config, consolidation_packet)
    if not operator_reviewed:
        return _refusal(
            consolidation_packet=consolidation_packet_dir,
            message=(
                "Selected-target cycle target selection refused; "
                "--operator-reviewed is required."
            ),
        )
    if not consolidation_packet_dir.exists() or not consolidation_packet_dir.is_dir():
        return _refusal(
            consolidation_packet=consolidation_packet_dir,
            message=(
                "Selected-target cycle target selection refused; consolidation "
                f"packet directory not found: {consolidation_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, consolidation_packet_dir)
        _validate_subject_for_target_selection(config, subject)
        supersession = _target_selection_supersession_context(config, subject)
        if supersession.corrected_current_valid_target_selection_exists:
            return _refusal(
                consolidation_packet=consolidation_packet_dir,
                message=(
                    "Selected-target cycle target selection refused; corrected "
                    "current-valid target-selection packet already exists for "
                    f"consolidation packet {subject.consolidation_packet_id}."
                ),
            )
        subject = replace(
            subject,
            superseded_target_selection_packet_id=(
                supersession.superseded_target_selection_packet_id
            ),
            supersession_reason=supersession.supersession_reason,
            stale_surface_failures=supersession.stale_surface_failures,
        )
    except ValueError as error:
        return _refusal(
            consolidation_packet=consolidation_packet_dir,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                consolidation_packet=consolidation_packet_dir,
                message=(
                    "Selected-target cycle target selection refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_target_selection"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_report = payloads["selected_target_cycle_target_selection_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_cycle_target_selection_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    return SelectedTargetCycleTargetSelectionResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    consolidation_packet_dir: Path,
) -> SelectedTargetCycleTargetSelectionSubject:
    payloads = _load_required_payloads(consolidation_packet_dir)
    packet = payloads["nonlocal_law_selected_target_cycle_consolidation_packet"]
    run_id = _required_text(packet.get("run_id"), "consolidation packet missing run_id")
    packet_id = str(packet.get("packet_id") or consolidation_packet_dir.name)

    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(
            connection,
            consolidation_packet_dir
            / "nonlocal_law_selected_target_cycle_consolidation_packet.json",
        )
    artifact_ids = _string_dict(packet.get("artifact_ids"))
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    return SelectedTargetCycleTargetSelectionSubject(
        run_id=run_id,
        consolidation_packet_dir=consolidation_packet_dir,
        consolidation_packet_id=packet_id,
        consolidation_packet_artifact_id=(
            packet_artifact.id if packet_artifact else None
        ),
        consolidation_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        active_risks=tuple(_active_risks(payloads)),
        allowed_target_seed_ids=tuple(_allowed_target_seed_ids(payloads)),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in NONLOCAL_LAW_SELECTED_TARGET_CYCLE_CONSOLIDATION_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Selected-target cycle target selection refused; consolidation "
                f"packet missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Selected-target cycle target selection refused; malformed "
                f"consolidation artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_subject_for_target_selection(
    config: AbiConfig,
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> None:
    packet = _packet(subject)
    _validate_no_forbidden_source_claims(subject.payloads)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Selected-target cycle target selection refused; consolidation packet "
            "is not accepted."
        )
    if subject.consolidation_packet_id != EXPECTED_CONSOLIDATION_PACKET_ID:
        raise ValueError(
            "Selected-target cycle target selection refused; stale or unsupported "
            f"consolidation packet {subject.consolidation_packet_id}."
        )
    if _has_newer_current_valid_consolidation(config, subject):
        raise ValueError(
            "Selected-target cycle target selection refused; consolidation packet "
            "is stale or superseded by a newer current-valid consolidation packet."
        )
    expected_pairs = (
        ("source_loop_review_packet_id", EXPECTED_SOURCE_LOOP_REVIEW_PACKET_ID),
        ("source_synthesis_packet_id", EXPECTED_SOURCE_SYNTHESIS_PACKET_ID),
        ("source_reader_state_packet_id", EXPECTED_SOURCE_READER_STATE_PACKET_ID),
        ("source_candidate_packet_id", EXPECTED_SOURCE_CANDIDATE_PACKET_ID),
        (
            "prior_working_current_best_candidate_packet_id",
            EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID,
        ),
        (
            "current_best_for_next_loop_packet_id",
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
        ),
        (
            "prior_historical_current_best_candidate_packet_id",
            EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID,
        ),
        ("learned_cycle_lesson_id", LEARNED_CYCLE_LESSON_ID),
        ("lesson_scope", LESSON_SCOPE),
        ("transferable_principle_status", TRANSFERABLE_PRINCIPLE_STATUS),
    )
    for field_name, expected_value in expected_pairs:
        if packet.get(field_name) != expected_value:
            raise ValueError(
                "Selected-target cycle target selection refused; "
                f"{field_name} must be {expected_value}."
            )
    bool_expectations = (
        ("consolidation_executed", True),
        ("universalized_rule_created", False),
        ("ready_for_next_target_selection", True),
        ("target_selection_requires_separate_command", True),
        ("work_order_authorized", False),
        ("generation_authorized", False),
        ("candidate_generated", False),
        ("finalization_eligible", False),
        ("no_final_claim", True),
        ("no_phase_shift_claim", True),
        ("strongest_rival_defeated_claimed", False),
    )
    for field_name, expected_value in bool_expectations:
        if packet.get(field_name) is not expected_value:
            raise ValueError(
                "Selected-target cycle target selection refused; "
                f"{field_name} must be {expected_value}."
            )
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError(
            "Selected-target cycle target selection refused; consolidation made "
            "model calls."
        )
    if tuple(packet.get("allowed_target_seed_ids") or ()) != ALLOWED_TARGET_SEED_IDS:
        raise ValueError(
            "Selected-target cycle target selection refused; allowed target seeds "
            "must match the four selected-target cycle seed IDs."
        )
    if tuple(subject.allowed_target_seed_ids) != ALLOWED_TARGET_SEED_IDS:
        raise ValueError(
            "Selected-target cycle target selection refused; allowed target seed "
            "memory is missing or contains unknown target seeds."
        )
    if len(subject.active_risks) != len(EXPECTED_ACTIVE_RISK_IDS):
        raise ValueError(
            "Selected-target cycle target selection refused; active risk count must be 8."
        )
    risk_ids = {str(risk.get("risk_id") or "") for risk in subject.active_risks}
    missing_risks = [
        risk_id for risk_id in EXPECTED_ACTIVE_RISK_IDS if risk_id not in risk_ids
    ]
    if missing_risks:
        raise ValueError(
            "Selected-target cycle target selection refused; active risks missing: "
            + ", ".join(missing_risks)
        )
    evidence = subject.payloads["selected_target_evidence_memory"]
    if evidence.get("selected_target_effect") != EXPECTED_SELECTED_TARGET_EFFECT:
        raise ValueError(
            "Selected-target cycle target selection refused; selected target effect "
            "must be supported_but_incomplete."
        )
    if evidence.get("reader_state_support") != EXPECTED_READER_STATE_SUPPORT:
        raise ValueError(
            "Selected-target cycle target selection refused; reader-state support "
            "must be supportive_with_active_risks."
        )
    rival = subject.payloads["strongest_rival_pressure_memory"]
    if rival.get("strongest_rival_remains_blocking") is not True:
        raise ValueError(
            "Selected-target cycle target selection refused; strongest rival must "
            "remain blocking."
        )
    if rival.get("strongest_rival_status") != EXPECTED_STRONGEST_RIVAL_STATUS:
        raise ValueError(
            "Selected-target cycle target selection refused; strongest rival status "
            f"must be {EXPECTED_STRONGEST_RIVAL_STATUS}."
        )


def _write_artifacts(
    *,
    writer: PacketWriter,
    subject: SelectedTargetCycleTargetSelectionSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_selected_target_cycle_consolidation_intake_summary"] = (
        _build_source_intake(subject, packet_dir)
    )
    artifacts["source_selected_target_cycle_consolidation_intake_summary"] = (
        writer.write_artifact(
            "source_selected_target_cycle_consolidation_intake_summary",
            payloads["source_selected_target_cycle_consolidation_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )
    )

    payloads["target_selection_criteria_report"] = _build_criteria(subject)
    artifacts["target_selection_criteria_report"] = writer.write_artifact(
        "target_selection_criteria_report",
        payloads["target_selection_criteria_report"],
        parent_ids=[
            artifacts["source_selected_target_cycle_consolidation_intake_summary"].id
        ],
    )

    payloads["target_candidate_ranking_report"] = _build_ranking(subject)
    artifacts["target_candidate_ranking_report"] = writer.write_artifact(
        "target_candidate_ranking_report",
        payloads["target_candidate_ranking_report"],
        parent_ids=[artifacts["target_selection_criteria_report"].id],
    )

    payloads["selected_target_decision"] = _build_selected_target_decision(subject)
    artifacts["selected_target_decision"] = writer.write_artifact(
        "selected_target_decision",
        payloads["selected_target_decision"],
        parent_ids=[
            artifacts["target_selection_criteria_report"].id,
            artifacts["target_candidate_ranking_report"].id,
        ],
    )

    payloads["selected_risk_evidence_report"] = _build_selected_risk_evidence(subject)
    artifacts["selected_risk_evidence_report"] = writer.write_artifact(
        "selected_risk_evidence_report",
        payloads["selected_risk_evidence_report"],
        parent_ids=[artifacts["selected_target_decision"].id],
    )

    payloads["non_selected_risk_carry_forward_report"] = (
        _build_non_selected_risk_carry_forward(subject)
    )
    artifacts["non_selected_risk_carry_forward_report"] = writer.write_artifact(
        "non_selected_risk_carry_forward_report",
        payloads["non_selected_risk_carry_forward_report"],
        parent_ids=[
            artifacts["selected_risk_evidence_report"].id,
            artifacts["target_candidate_ranking_report"].id,
        ],
    )

    payloads["working_current_best_context_report"] = _build_current_best_context(
        subject
    )
    artifacts["working_current_best_context_report"] = writer.write_artifact(
        "working_current_best_context_report",
        payloads["working_current_best_context_report"],
        parent_ids=[artifacts["selected_target_decision"].id],
    )

    payloads["non_universalization_guard_carry_forward_report"] = (
        _build_non_universalization_guard(subject)
    )
    artifacts["non_universalization_guard_carry_forward_report"] = (
        writer.write_artifact(
            "non_universalization_guard_carry_forward_report",
            payloads["non_universalization_guard_carry_forward_report"],
            parent_ids=[
                artifacts["selected_target_decision"].id,
                artifacts["working_current_best_context_report"].id,
            ],
        )
    )

    payloads["strongest_rival_blocker_carry_forward_report"] = (
        _build_strongest_rival_carry_forward(subject)
    )
    artifacts["strongest_rival_blocker_carry_forward_report"] = (
        writer.write_artifact(
            "strongest_rival_blocker_carry_forward_report",
            payloads["strongest_rival_blocker_carry_forward_report"],
            parent_ids=[
                artifacts["selected_target_decision"].id,
                artifacts["non_universalization_guard_carry_forward_report"].id,
            ],
        )
    )

    payloads["next_work_order_readiness_report"] = _build_work_order_readiness(
        subject,
        packet_dir,
    )
    artifacts["next_work_order_readiness_report"] = writer.write_artifact(
        "next_work_order_readiness_report",
        payloads["next_work_order_readiness_report"],
        parent_ids=[
            artifacts["selected_target_decision"].id,
            artifacts["working_current_best_context_report"].id,
            artifacts["strongest_rival_blocker_carry_forward_report"].id,
        ],
    )

    payloads["selected_target_cycle_target_selection_gate_report"] = _build_gate_report(
        subject,
        payloads,
    )
    artifacts["selected_target_cycle_target_selection_gate_report"] = (
        writer.write_artifact(
            "selected_target_cycle_target_selection_gate_report",
            payloads["selected_target_cycle_target_selection_gate_report"],
            parent_ids=[
                artifacts["selected_target_decision"].id,
                artifacts["selected_risk_evidence_report"].id,
                artifacts["non_selected_risk_carry_forward_report"].id,
                artifacts["next_work_order_readiness_report"].id,
            ],
        )
    )

    payloads["project_health_scope_guard_report"] = _build_health_report(subject)
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[
            artifacts["selected_target_cycle_target_selection_gate_report"].id,
            artifacts["strongest_rival_blocker_carry_forward_report"].id,
        ],
    )

    payloads["nonlocal_law_selected_target_cycle_target_selection_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
    )
    artifacts["nonlocal_law_selected_target_cycle_target_selection_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_cycle_target_selection_packet",
            payloads["nonlocal_law_selected_target_cycle_target_selection_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type
                != "nonlocal_law_selected_target_cycle_target_selection_packet"
            ],
        )
    )

    return payloads, artifacts


def _build_source_intake(
    subject: SelectedTargetCycleTargetSelectionSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_consolidation_packet_dir": str(subject.consolidation_packet_dir),
        "source_consolidation_packet_artifact_id": (
            subject.consolidation_packet_artifact_id
        ),
        "superseded_target_selection_packet_id": (
            subject.superseded_target_selection_packet_id
        ),
        "supersession_reason": subject.supersession_reason,
        "stale_surface_failures": list(subject.stale_surface_failures),
        "source_consolidation_artifact_ids": dict(subject.consolidation_artifact_ids),
        "source_consolidation_accepted": True,
        "source_consolidation_current_valid": True,
        "target_selection_ready": True,
        "operator_reviewed": True,
        "target_selection_executed": True,
        "selected_target_count": 1,
        "work_order_created": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": (
            "source_selected_target_cycle_consolidation_intake_summary_v1_controller"
        ),
    }


def _build_criteria(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "selection_criteria": list(SELECTION_CRITERIA),
        "selection_not_based_on": list(SELECTION_NOT_BASED_ON),
        "target_selection_executed": True,
        "selected_target_count": 1,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "target_selection_criteria_report_v1_controller",
    }


def _build_ranking(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    rankings = []
    for item in RANKED_TARGETS:
        ranking = dict(item)
        ranking["selected"] = item["target_seed_id"] == SELECTED_TARGET_SEED_ID
        ranking["selected_now"] = ranking["selected"]
        ranking["work_order_created"] = False
        ranking["generation_authorized"] = False
        rankings.append(ranking)
    ranked_target_ids = [str(item["target_seed_id"]) for item in rankings]
    return {
        **_source_fields(subject),
        "summary": (
            "The selected next target is reduce_causal_mechanism_naming because "
            "it directly addresses the central mechanism-visibility cluster "
            "while preserving packet_0001's living-event sequence gain."
        ),
        "rankings": rankings,
        "ranked_targets": rankings,
        "ranked_target_seed_ids": ranked_target_ids,
        "ranked_target_ids": ranked_target_ids,
        "ranked_target_count": len(rankings),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_target_rank": 1,
        "selected_target_ranked_first": True,
        "ranking_method": "selected_target_cycle_controller_priority",
        "target_selection_executed": True,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "target_candidate_ranking_report_v1_controller",
    }


def _build_selected_target_decision(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_risk_cluster": list(SELECTED_RISK_CLUSTER),
        "selected_target_class": SELECTED_TARGET_CLASS,
        "target_scope": WORK_ORDER_TARGET_SCOPE,
        "target_statement": TARGET_STATEMENT,
        "core_repair_principle": CORE_REPAIR_PRINCIPLE,
        "work_order_planning_principle": WORK_ORDER_PLANNING_PRINCIPLE,
        "selected_target_count": 1,
        "why_selected_before_other_risks": [
            "It addresses the dominant risk cluster.",
            "It preserves the last real gain.",
            "It is bounded enough for ablation and reader-state evaluation.",
            "It prevents the system from converting its own diagnosis into prose.",
        ],
        "target_selection_authorized_by_consolidation": True,
        "target_selection_executed_by_this_packet": True,
        "ready_for_work_order_planning": True,
        "work_order_authorized": False,
        "work_order_requires_separate_command": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "selected_target_decision_v1_controller",
    }


def _build_selected_risk_evidence(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_risk_cluster": list(SELECTED_RISK_CLUSTER),
        "evidence_from_consolidation": [
            "overexplained_mechanism_signal active_risk",
            "declarative_instruction_signal active_risk",
            "law_naming_signal active_risk",
            "lesson statement says living-event sequence improved but mechanism naming remains",
            "transferable principle says reduce explicit mechanism naming",
        ],
        "selected_now": True,
        "target_seed": SELECTED_TARGET_SEED_ID,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "selected_risk_evidence_report_v1_controller",
    }


def _build_non_selected_risk_carry_forward(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    source = {str(risk.get("risk_id") or ""): risk for risk in subject.active_risks}
    carried = []
    for risk_id in NON_SELECTED_RISK_IDS:
        source_risk = source.get(risk_id, {})
        carried.append(
            {
                "risk_id": risk_id,
                "risk": source_risk.get("risk") or risk_id.replace("_", " "),
                "source_consolidation_packet_id": subject.consolidation_packet_id,
                "carried_forward_to_next_loop": True,
                "not_selected_yet": True,
                "blocks_finalization": True,
                "possible_next_target_seed": _risk_to_seed(risk_id),
                "recommended_next_handling": _risk_handling(risk_id),
                "work_order_constraint_role": _risk_constraint_role(risk_id),
            }
        )
    return {
        **_source_fields(subject),
        "carried_forward_target_seed_ids": list(NON_SELECTED_TARGET_SEED_IDS),
        "carried_forward_risk_ids": list(NON_SELECTED_RISK_IDS),
        "non_selected_risks": carried,
        "strongest_rival_remains_blocking": True,
        "finalization_eligible": False,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "non_selected_risk_carry_forward_report_v1_controller",
    }


def _build_current_best_context(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "current_best_for_next_loop_packet_id": (
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ),
        "prior_working_current_best_candidate_packet_id": (
            EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "prior_historical_current_best_candidate_packet_id": (
            EXPECTED_PRIOR_HISTORICAL_CURRENT_BEST_PACKET_ID
        ),
        "packet_0001_is_working_basis_not_final_artifact": True,
        "packet_0002_preserved_as_prior_working_reference": True,
        "packet_0063_preserved_as_historical_reference": True,
        "global_state_mutation_performed": False,
        "current_best_state_mutation_performed": False,
        "finalization_eligible": False,
        "worker": "working_current_best_context_report_v1_controller",
    }


def _build_non_universalization_guard(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "universalized_rule_created": False,
        "lesson_scope": LESSON_SCOPE,
        "selected_target_does_not_mean_always_reduce_explanation": True,
        "selected_target_does_not_mean_delete_causality": True,
        "selected_target_does_not_mean_make_objects_less_active": True,
        "selected_target_does_not_mean_prior_candidate_failed": True,
        "correct_generalization_level": "work_local_selected_target_refinement",
        "guard_statement": (
            "The selected target preserves the living-event sequence gain while "
            "reducing explicit mechanism naming; it does not universalize into a "
            "rule against explanation or causality."
        ),
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "non_universalization_guard_carry_forward_report_v1_controller",
    }


def _build_strongest_rival_carry_forward(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "strongest_rival_status": EXPECTED_STRONGEST_RIVAL_STATUS,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_pressure_must_remain_active": True,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "strongest_rival_blocker_carry_forward_report_v1_controller",
    }


def _build_work_order_readiness(
    subject: SelectedTargetCycleTargetSelectionSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ready_for_work_order_planning": True,
        "ready_for_selected_target_work_order_planning": True,
        "selected_target_selection_packet_id": packet_dir.name,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "work_order_authorized": False,
        "work_order_requires_separate_command": True,
        "work_order_planning_requires_operator_review": True,
        "generation_authorized": False,
        "generation_requires_future_work_order": True,
        "generation_requires_separate_authorization": True,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "next_work_order_readiness_report_v1_controller",
    }


def _build_gate_report(
    subject: SelectedTargetCycleTargetSelectionSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    pass_gates = (
        "source_consolidation_accepted",
        "source_consolidation_current_valid",
        "target_selection_ready",
        "allowed_target_seeds_present",
        "selected_target_allowed",
        "selected_target_ranked_first",
        "packet_0001_working_current_best_preserved",
        "packet_0002_preserved_as_prior_working_reference",
        "packet_0063_preserved_as_historical_reference",
        "non_universalization_guard_preserved",
        "strongest_rival_remains_blocking",
        "no_work_order",
        "no_generation",
        "no_candidate",
        "no_model_calls",
        "no_final_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    )
    block_gates = (
        "work_order_created",
        "generation_authorized",
        "candidate_generated",
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
        "work order requires a separate command",
        "generation remains unauthorized",
        "candidate is not generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "target_selection_executed": True,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_count": 1,
        "ready_for_work_order_planning": True,
        "target_selected": True,
        "selected_target_allowed": True,
        "selected_target_ranked_first": True,
        "work_order_created": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_resolved": False,
        "strongest_rival_defeated_claimed": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_results": gate_results,
        "passed_gates": list(pass_gates),
        "failed_gates": list(block_gates),
        "unresolved_blockers": blockers,
        "worker": "selected_target_cycle_target_selection_gate_report_v1_controller",
    }


def _build_health_report(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "source_consolidation_accepted": True,
        "source_consolidation_current_valid": True,
        "target_selection_only": True,
        "no_openai_calls": True,
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
        "finalization_eligible": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: SelectedTargetCycleTargetSelectionSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=(
            NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_ARTIFACT_TYPES
        ),
        produced_artifact_types=list(artifacts),
        packet_artifact_type=(
            "nonlocal_law_selected_target_cycle_target_selection_packet"
        ),
    )
    return {
        **_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "superseded_target_selection_packet_id": (
            subject.superseded_target_selection_packet_id
        ),
        "supersession_reason": subject.supersession_reason,
        "stale_surface_failures": list(subject.stale_surface_failures),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_cycle_target_selection_packet",
        ],
        "counts": {**counts, "model_calls": 0, "candidate_artifacts_created": 0},
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "selected_target_count": 1,
        "target_selection_executed": True,
        "ranked_target_ids": payloads["target_candidate_ranking_report"][
            "ranked_target_ids"
        ],
        "ranked_targets": payloads["target_candidate_ranking_report"][
            "ranked_targets"
        ],
        "ranked_target_count": payloads["target_candidate_ranking_report"][
            "ranked_target_count"
        ],
        "selected_target_rank": 1,
        "target_selected": True,
        "gate_target_selected": payloads[
            "selected_target_cycle_target_selection_gate_report"
        ]["target_selected"],
        "selected_target_allowed": True,
        "selected_target_ranked_first": True,
        "ready_for_work_order_planning": True,
        "ready_for_selected_target_work_order_planning": True,
        "work_order_authorized": False,
        "work_order_requires_separate_command": True,
        "work_order_planning_requires_operator_review": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "no_strongest_rival_defeat_claim": True,
        "no_work_order_introduced": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_introduced": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "ranking_report": payloads["target_candidate_ranking_report"],
        "gate_report": payloads["selected_target_cycle_target_selection_gate_report"],
        "worker": (
            "nonlocal_law_selected_target_cycle_target_selection_packet_v1_controller"
        ),
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_cycle_target_selection_packet"]
    return {
        **packet,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
    }


def _source_fields(
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_consolidation_packet_id": subject.consolidation_packet_id,
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "prior_working_current_best_candidate_packet_id": packet.get(
            "prior_working_current_best_candidate_packet_id"
        ),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "prior_historical_current_best_candidate_packet_id": packet.get(
            "prior_historical_current_best_candidate_packet_id"
        ),
        "learned_cycle_lesson_id": packet.get("learned_cycle_lesson_id"),
        "lesson_scope": packet.get("lesson_scope"),
    }


def _packet(subject: SelectedTargetCycleTargetSelectionSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_selected_target_cycle_consolidation_packet"]


def _active_risks(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    risks = payloads["active_risk_memory"].get("active_risks")
    if not isinstance(risks, list):
        return []
    return [risk for risk in risks if isinstance(risk, dict)]


def _allowed_target_seed_ids(payloads: dict[str, dict[str, Any]]) -> list[str]:
    readiness = payloads["next_target_selection_readiness_report"]
    seeds = readiness.get("allowed_target_seed_ids")
    if not isinstance(seeds, list):
        seeds = payloads["nonlocal_law_selected_target_cycle_consolidation_packet"].get(
            "allowed_target_seed_ids"
        )
    if not isinstance(seeds, list):
        return []
    return [str(seed) for seed in seeds if isinstance(seed, str)]


def _risk_to_seed(risk_id: str) -> str | None:
    if risk_id == "conclusion_summarizes_instead_of_enacts_return":
        return "enact_return_instead_of_summarizing_law"
    if risk_id == "chemistry_register_unresolved":
        return "integrate_or_remove_chemistry_register"
    if risk_id in {
        "object_field_delicacy_overloaded_by_causal_explanation",
        "strongest_rival_remains_blocking",
    }:
        return "protect_object_field_delicacy"
    if risk_id == "finalization_not_allowed":
        return None
    return None


def _risk_handling(risk_id: str) -> str:
    handling = {
        "conclusion_summarizes_instead_of_enacts_return": (
            "carry forward as the likely next return-enactment target after "
            "mechanism-visibility repair is tested"
        ),
        "chemistry_register_unresolved": (
            "carry forward unchanged as a later register integration or removal "
            "target"
        ),
        "object_field_delicacy_overloaded_by_causal_explanation": (
            "use as a guard constraint on the selected work order"
        ),
        "strongest_rival_remains_blocking": (
            "keep strongest-rival pressure active; do not claim rival resolution"
        ),
        "finalization_not_allowed": (
            "keep finalization locked until post-generation evidence and final "
            "profile gates exist"
        ),
    }
    return handling.get(risk_id, "carry forward for operator review")


def _risk_constraint_role(risk_id: str) -> str:
    roles = {
        "conclusion_summarizes_instead_of_enacts_return": (
            "future_target_after_selected_mechanism_visibility_repair"
        ),
        "chemistry_register_unresolved": "future_register_target",
        "object_field_delicacy_overloaded_by_causal_explanation": (
            "selected_work_order_guard_constraint"
        ),
        "strongest_rival_remains_blocking": "blocking_external_pressure",
        "finalization_not_allowed": "finalization_lock",
    }
    return roles.get(risk_id, "operator_review_constraint")


def _target_selection_supersession_context(
    config: AbiConfig,
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> TargetSelectionSupersessionContext:
    root = (
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_cycle_target_selection"
    )
    if not root.exists():
        return TargetSelectionSupersessionContext(
            corrected_current_valid_target_selection_exists=False
        )

    superseded_packet_id: str | None = None
    stale_surface_failures: tuple[str, ...] = ()
    for packet_dir in sorted(root.glob("packet_*")):
        packet_path = (
            packet_dir
            / "nonlocal_law_selected_target_cycle_target_selection_packet.json"
        )
        if not packet_path.exists():
            continue
        try:
            payload = _read_payload(packet_path)
        except ValueError:
            continue
        if not _is_matching_target_selection_payload(payload, subject):
            continue
        failures = _target_selection_surface_failures(packet_dir, payload)
        if not failures:
            return TargetSelectionSupersessionContext(
                corrected_current_valid_target_selection_exists=True
            )
        superseded_packet_id = packet_dir.name
        stale_surface_failures = tuple(failures)

    if superseded_packet_id:
        return TargetSelectionSupersessionContext(
            corrected_current_valid_target_selection_exists=False,
            superseded_target_selection_packet_id=superseded_packet_id,
            supersession_reason=SUPERSESSION_REASON_WORK_ORDER_SURFACE_MISSING,
            stale_surface_failures=stale_surface_failures,
        )
    return TargetSelectionSupersessionContext(
        corrected_current_valid_target_selection_exists=False
    )


def _is_matching_target_selection_payload(
    payload: dict[str, Any],
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> bool:
    return (
        payload.get("accepted") is True
        and payload.get("source_consolidation_packet_id")
        == subject.consolidation_packet_id
        and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
        and payload.get("target_selection_executed") is True
        and payload.get("work_order_authorized") is False
        and payload.get("generation_authorized") is False
        and payload.get("candidate_generated") is False
        and int(payload.get("model_calls") or 0) == 0
        and payload.get("finalization_eligible") is False
    )


def _target_selection_surface_failures(
    packet_dir: Path,
    packet_payload: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    expected_ids = [str(item["target_seed_id"]) for item in RANKED_TARGETS]
    if packet_payload.get("ranked_target_ids") != expected_ids:
        failures.append("packet.ranked_target_ids_missing_or_invalid")
    if packet_payload.get("ranked_target_count") != len(expected_ids):
        failures.append("packet.ranked_target_count_missing_or_invalid")
    packet_ranked_targets = packet_payload.get("ranked_targets")
    if not isinstance(packet_ranked_targets, list):
        failures.append("packet.ranked_targets_missing_or_invalid")
    elif [
        item.get("target_seed_id") if isinstance(item, dict) else None
        for item in packet_ranked_targets
    ] != expected_ids:
        failures.append("packet.ranked_targets_ids_invalid")
    if not isinstance(packet_payload.get("ranking_report"), dict):
        failures.append("packet.ranking_report_missing")
    if packet_payload.get("target_selected") is not True:
        failures.append("packet.target_selected_missing_or_invalid")
    if packet_payload.get("gate_target_selected") is not True:
        failures.append("packet.gate_target_selected_missing_or_invalid")
    if packet_payload.get("selected_target_allowed") is not True:
        failures.append("packet.selected_target_allowed_missing_or_invalid")
    if packet_payload.get("selected_target_ranked_first") is not True:
        failures.append("packet.selected_target_ranked_first_missing_or_invalid")
    if packet_payload.get("ready_for_work_order_planning") is not True:
        failures.append("packet.ready_for_work_order_planning_missing_or_invalid")
    if packet_payload.get("ready_for_selected_target_work_order_planning") is not True:
        failures.append(
            "packet.ready_for_selected_target_work_order_planning_missing_or_invalid"
        )

    ranking = _optional_target_selection_payload(
        packet_dir,
        "target_candidate_ranking_report",
        failures,
    )
    if ranking:
        ranked_targets = ranking.get("ranked_targets")
        if not isinstance(ranked_targets, list):
            failures.append("ranking.ranked_targets_missing")
        elif [
            item.get("target_seed_id") if isinstance(item, dict) else None
            for item in ranked_targets
        ] != expected_ids:
            failures.append("ranking.ranked_targets_ids_invalid")
        if ranking.get("ranked_target_ids") != expected_ids:
            failures.append("ranking.ranked_target_ids_missing_or_invalid")
        if ranking.get("ranked_target_count") != len(expected_ids):
            failures.append("ranking.ranked_target_count_missing_or_invalid")
        if ranking.get("selected_target_rank") != 1:
            failures.append("ranking.selected_target_rank_missing_or_invalid")
        if ranking.get("selected_target_ranked_first") is not True:
            failures.append("ranking.selected_target_ranked_first_missing_or_invalid")

    decision = _optional_target_selection_payload(
        packet_dir,
        "selected_target_decision",
        failures,
    )
    if decision:
        if decision.get("selected_risk_cluster") != list(SELECTED_RISK_CLUSTER):
            failures.append("decision.selected_risk_cluster_missing_or_invalid")
        if decision.get("target_scope") != WORK_ORDER_TARGET_SCOPE:
            failures.append("decision.target_scope_missing_or_invalid")
        if decision.get("core_repair_principle") != CORE_REPAIR_PRINCIPLE:
            failures.append("decision.core_repair_principle_missing_or_invalid")
        if (
            decision.get("work_order_planning_principle")
            != WORK_ORDER_PLANNING_PRINCIPLE
        ):
            failures.append("decision.work_order_planning_principle_missing")
        if decision.get("ready_for_work_order_planning") is not True:
            failures.append("decision.ready_for_work_order_planning_missing")

    carry = _optional_target_selection_payload(
        packet_dir,
        "non_selected_risk_carry_forward_report",
        failures,
    )
    if carry:
        risks = carry.get("non_selected_risks")
        if not isinstance(risks, list):
            failures.append("carry.non_selected_risks_missing")
        else:
            for risk in risks:
                if not isinstance(risk, dict):
                    failures.append("carry.non_selected_risk_malformed")
                    continue
                risk_id = str(risk.get("risk_id") or "unknown")
                if not risk.get("recommended_next_handling"):
                    failures.append(
                        f"carry.{risk_id}.recommended_next_handling_missing"
                    )
                if not risk.get("work_order_constraint_role"):
                    failures.append(
                        f"carry.{risk_id}.work_order_constraint_role_missing"
                    )

    readiness = _optional_target_selection_payload(
        packet_dir,
        "next_work_order_readiness_report",
        failures,
    )
    if readiness:
        if readiness.get("ready_for_work_order_planning") is not True:
            failures.append("readiness.ready_for_work_order_planning_missing")
        if readiness.get("ready_for_selected_target_work_order_planning") is not True:
            failures.append(
                "readiness.ready_for_selected_target_work_order_planning_missing"
            )
        if readiness.get("work_order_planning_requires_operator_review") is not True:
            failures.append(
                "readiness.work_order_planning_requires_operator_review_missing"
            )

    gate = _optional_target_selection_payload(
        packet_dir,
        "selected_target_cycle_target_selection_gate_report",
        failures,
    )
    if gate:
        if gate.get("target_selected") is not True:
            failures.append("gate.target_selected_missing_or_invalid")
        if gate.get("selected_target_allowed") is not True:
            failures.append("gate.selected_target_allowed_missing_or_invalid")
        if gate.get("selected_target_ranked_first") is not True:
            failures.append("gate.selected_target_ranked_first_missing_or_invalid")
        if gate.get("strongest_rival_resolved") is not False:
            failures.append("gate.strongest_rival_resolved_missing_or_invalid")
    return failures


def _optional_target_selection_payload(
    packet_dir: Path,
    artifact_type: str,
    failures: list[str],
) -> dict[str, Any] | None:
    path = packet_dir / f"{artifact_type}.json"
    if not path.exists():
        failures.append(f"{artifact_type}.missing")
        return None
    try:
        return _read_payload(path)
    except ValueError:
        failures.append(f"{artifact_type}.malformed")
        return None


def _has_newer_current_valid_consolidation(
    config: AbiConfig,
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> bool:
    root = (
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_cycle_consolidation"
    )
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= subject.consolidation_packet_id:
            continue
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
            == _packet(subject).get("source_loop_review_packet_id")
            and payload.get("ready_for_next_target_selection") is True
            and payload.get("universalized_rule_created") is False
        ):
            return True
    return False


def _accepted_target_selection_exists(
    config: AbiConfig,
    subject: SelectedTargetCycleTargetSelectionSubject,
) -> bool:
    root = (
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_cycle_target_selection"
    )
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        path = (
            packet_dir
            / "nonlocal_law_selected_target_cycle_target_selection_packet.json"
        )
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_consolidation_packet_id")
            == subject.consolidation_packet_id
            and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
            and payload.get("target_selection_executed") is True
            and payload.get("work_order_authorized") is False
            and payload.get("generation_authorized") is False
            and payload.get("candidate_generated") is False
            and int(payload.get("model_calls") or 0) == 0
        ):
            return True
    return False


def _validate_no_forbidden_source_claims(payloads: dict[str, dict[str, Any]]) -> None:
    if _payload_has_forbidden_claim(payloads):
        raise ValueError(
            "Selected-target cycle target selection refused; finality, phase-shift, "
            "rival-defeat, work-order, generation, candidate, or model-call claim "
            "appears in the source consolidation packet."
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
                "work_order_created",
                "work_order_authorized",
                "generation_authorized",
                "candidate_generated",
            } and item is True:
                return True
            if key == "model_calls" and isinstance(item, int) and item != 0:
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
    raise ValueError(f"Selected-target cycle target selection refused; {message}.")


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
    consolidation_packet: Path,
    message: str,
) -> SelectedTargetCycleTargetSelectionResult:
    return SelectedTargetCycleTargetSelectionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "message": message,
            "consolidation_packet": str(consolidation_packet),
            "target_selection_executed": False,
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
