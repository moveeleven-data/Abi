"""Deterministic evidence loop-level review packet."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_EVIDENCE_LOOP_REVIEW_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.loop_integrity import (
    build_proof_before_next_generation_guard,
    build_reader_state_before_synthesis_guard,
    build_repeated_target_drift_guard,
    detect_stale_recommendations,
)
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_candidate_evidence_synthesis import (
    CANDIDATE_LAW_EFFECT,
    CURRENT_BEST_RECOMMENDATION as NONLOCAL_SYNTHESIS_RECOMMENDATION,
    READER_STATE_SUPPORT,
    RECOMMENDED_NEXT_DECISION as NONLOCAL_RECOMMENDED_NEXT_DECISION,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


EVIDENCE_LOOP_REVIEW_LINEAGE_ID = "evidence_loop_review_v1"
EVIDENCE_LOOP_REVIEW_CREATED_BY = "evidence_loop_review_v1_controller"

EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES = (
    "evidence_loop_review_subject_manifest",
    "completed_cycle_map",
    "current_best_candidate_review",
    "evidence_quality_review",
    "reader_state_progress_review",
    "strongest_rival_status_review",
    "residual_blocker_taxonomy",
    "drift_risk_report",
    "loop_integrity_report",
    "next_action_decision",
    "loop_controller_readiness_report",
    "evidence_loop_review_gate_report",
    "evidence_loop_review_packet",
)

REQUIRED_SYNTHESIS_ARTIFACTS = (
    "autonomous_evidence_synthesis_packet",
    "best_current_candidate_selection",
    "causal_status_summary",
    "repair_history_table",
    "reader_state_evidence_adjudication",
    "reader_state_tension_report",
    "residual_blocker_map",
    "rival_pressure_summary",
    "strategic_decision_report",
    "synthesis_gate_report",
)

NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_LINEAGE_ID = (
    "nonlocal_law_candidate_loop_review_v1"
)
NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_CREATED_BY = (
    "nonlocal_law_candidate_loop_review_v1_controller"
)
NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_ARTIFACT_TYPES = (
    "source_synthesis_intake_summary",
    "current_best_transition_decision",
    "prior_current_best_preservation_report",
    "promoted_candidate_evidence_summary",
    "active_risk_carry_forward_report",
    "strongest_rival_blocker_status_report",
    "next_cycle_target_seed_report",
    "finalization_lock_report",
    "loop_review_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_candidate_loop_review_packet",
)
NONLOCAL_SYNTHESIS_PACKET_ARTIFACT = "nonlocal_law_candidate_evidence_synthesis_packet"
NONLOCAL_EXPECTED_SOURCE_READER_STATE_PACKET_ID = "packet_0002"
NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID = "packet_0002"
NONLOCAL_EXPECTED_SOURCE_ABLATION_PACKET_ID = "packet_0001"
NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID = "packet_0063"
NONLOCAL_EXPECTED_PROOF_PACKET_ID = "packet_0034"
NONLOCAL_EXPECTED_PRIOR_READER_STATE_PACKET_ID = "packet_0013"
NONLOCAL_LOOP_REVIEW_DECISION = "promote_packet_0002_to_current_best_pending_loop_review"
NONLOCAL_NEXT_RECOMMENDED_ACTION = (
    "consolidate_nonlocal_law_cycle_learning_before_next_repair"
)
NONLOCAL_LOOP_REVIEW_SUPERSESSION_REASON = (
    "nonlocal_loop_review_consolidation_surface_missing"
)
NONLOCAL_RECOMMENDED_NEXT_TARGET_SEED = (
    "cycle_consolidation_before_target_selection"
)
NONLOCAL_PRIOR_PRESERVATION_SUMMARY = (
    "Packet_0063 remains preserved as prior current-best history while packet_0002 "
    "becomes the packet-owned working current best for the next loop."
)
NONLOCAL_EVIDENCE_SUMMARY = (
    "Packet_0002 is promotable for the next loop because law-specific reader-state "
    "signals improved, but the evidence is not finalization evidence."
)
NONLOCAL_RIVAL_BLOCKER_WHY = (
    "The strongest rival pressure narrowed but remains unresolved; promotion to "
    "working current best does not claim rival defeat."
)
NONLOCAL_RIVAL_NEXT_CYCLE_IMPLICATION = (
    "Carry rival pressure forward as a blocker while consolidating the nonlocal law "
    "cycle before selecting a new repair target."
)
NONLOCAL_ACTIVE_RISK_HANDLING = {
    "explanation_may_arrive_too_explicitly": (
        "target explanation timing only after cycle consolidation"
    ),
    "event_sequence_may_remain_static": (
        "test whether object events become live consequences rather than retrospective trace"
    ),
    "chemistry_register_risk": (
        "repair register intrusion without weakening the object/tactile field"
    ),
    "conclusion_may_summarize_law": (
        "make return happen through object relation instead of explanatory summary"
    ),
}
NONLOCAL_NEXT_CYCLE_TARGET_OPTIONS = (
    "reduce_explanation_explicitness_after_initial_pressure",
    "convert_static_retrospective_trace_to_living_event_sequence",
    "repair_chemistry_register_intrusion",
    "enact_return_instead_of_summarizing_law",
)
NONLOCAL_TARGET_OPTION_RISK_MAP = {
    "reduce_explanation_explicitness_after_initial_pressure": (
        "explanation_may_arrive_too_explicitly"
    ),
    "convert_static_retrospective_trace_to_living_event_sequence": (
        "event_sequence_may_remain_static"
    ),
    "repair_chemistry_register_intrusion": "chemistry_register_risk",
    "enact_return_instead_of_summarizing_law": "conclusion_may_summarize_law",
}

SELECTED_TARGET_LOOP_REVIEW_LINEAGE_ID = (
    "nonlocal_law_selected_target_loop_review_v1"
)
SELECTED_TARGET_LOOP_REVIEW_CREATED_BY = (
    "nonlocal_law_selected_target_loop_review_v1_controller"
)
SELECTED_TARGET_LOOP_REVIEW_ARTIFACT_TYPES = (
    "source_selected_target_synthesis_intake_summary",
    "current_best_transition_decision",
    "prior_working_current_best_preservation_report",
    "selected_target_evidence_summary",
    "active_risk_carry_forward_report",
    "strongest_rival_blocker_status_report",
    "next_cycle_target_seed_report",
    "finalization_lock_report",
    "selected_target_loop_review_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_selected_target_loop_review_packet",
)
SELECTED_TARGET_SYNTHESIS_PACKET_ARTIFACT = (
    "nonlocal_law_selected_target_evidence_synthesis_packet"
)
SELECTED_TARGET_EXPECTED_SOURCE_READER_STATE_PACKET_ID = "packet_0005"
SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID = "packet_0001"
SELECTED_TARGET_EXPECTED_SOURCE_ABLATION_PACKET_ID = "packet_0001"
SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID = "packet_0002"
SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID = "packet_0063"
SELECTED_TARGET_SEED_ID = (
    "convert_static_retrospective_trace_to_living_event_sequence"
)
SELECTED_RISK_ID = "event_sequence_may_remain_static"
SELECTED_TARGET_EFFECT = "supported_but_incomplete"
SELECTED_TARGET_READER_STATE_SUPPORT = "supportive_with_active_risks"
SELECTED_TARGET_SYNTHESIS_CURRENT_BEST_DECISION = "do_not_finalize"
SELECTED_TARGET_SYNTHESIS_RECOMMENDATION = (
    "recommend_loop_review_consideration_not_direct_update"
)
SELECTED_TARGET_STRONGEST_RIVAL_STATUS = "narrowed_but_blocking"
SELECTED_TARGET_COMPARISON_RESULT = (
    "packet_0001_improves_selected_target_over_packet_0002"
)
SELECTED_TARGET_LOOP_REVIEW_DECISION = (
    "promote_packet_0001_to_working_current_best_for_next_loop"
)
SELECTED_TARGET_LOOP_REVIEW_UPDATE_METHOD = (
    "selected_target_loop_review_packet_only"
)
SELECTED_TARGET_NEXT_RECOMMENDED_ACTION = (
    "consolidate_selected_target_loop_before_next_target_selection"
)
SELECTED_TARGET_LOOP_REVIEW_SUPERSESSION_REASON = (
    "selected_target_loop_review_consolidation_surface_missing"
)
SELECTED_TARGET_EVIDENCE_SUMMARY = (
    "packet_0001 improves the selected target over packet_0002 by making object "
    "traces more often feel like active conditions for later perception, but "
    "active overexplanation and return/register risks remain."
)
SELECTED_TARGET_PROMOTION_BASIS = (
    "selected target effect supported_but_incomplete",
    "reader-state support supportive_with_active_risks",
    "packet_0001 improves selected target over packet_0002",
    "living-event sequence improved",
    "static trace reduction improved",
    "causal bridge improved",
    "consequence before naming improved",
    "packet_0002 gains preserved",
    "non-imitation preserved",
)
SELECTED_TARGET_PROMOTION_LIMITS = (
    "causal mechanism overexplained active risk",
    "explanation earned only mixed",
    "room begins to instruct too declarative",
    "later seeing must be changed names law too directly",
    "chemistry register unresolved",
    "conclusion summarizes instead of enacts return",
    "object-field delicacy may be overloaded",
    "strongest rival remains blocking",
    "candidate is not final proof",
)
SELECTED_TARGET_ACTIVE_RISK_HANDLING = {
    "causal_mechanism_overexplained": (
        "reduce explicit mechanism naming while preserving living-event sequence"
    ),
    "room_begins_to_instruct_too_declarative": (
        "make room pressure emerge through object relation rather than declaration"
    ),
    "later_seeing_must_be_changed_names_law_too_directly": (
        "avoid naming the law while preserving changed later seeing"
    ),
    "chemistry_register_unresolved": (
        "decide whether chemistry belongs to local physics or should be removed"
    ),
    "conclusion_summarizes_instead_of_enacts_return": (
        "make return happen through altered objects instead of summary"
    ),
    "object_field_delicacy_overloaded_by_causal_explanation": (
        "protect object-field delicacy from over-instrumented causality"
    ),
    "strongest_rival_remains_blocking": (
        "carry strongest-rival pressure through consolidation and target selection"
    ),
    "finalization_not_allowed": "keep finalization fail-closed",
}
SELECTED_TARGET_RISK_TARGET_SEEDS = {
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
SELECTED_TARGET_NEXT_CYCLE_TARGET_OPTIONS = (
    (
        "reduce_causal_mechanism_naming",
        "causal_mechanism_overexplained",
        "preserve living-event sequence while making causal relations felt with less explicit mechanism language.",
        "consolidate before selecting; likely first next target if consolidation preserves ranking.",
    ),
    (
        "enact_return_instead_of_summarizing_law",
        "conclusion_summarizes_instead_of_enacts_return",
        "make the ending return through the altered object field rather than restating the law.",
        "carry as high-priority next-cycle target option.",
    ),
    (
        "integrate_or_remove_chemistry_register",
        "chemistry_register_unresolved",
        "decide whether chemistry belongs to the local physics or imports an alien register.",
        "carry as register-risk target option.",
    ),
    (
        "protect_object_field_delicacy",
        "object_field_delicacy_overloaded_by_causal_explanation",
        "keep causal activity without over-instrumenting the object field.",
        "carry as delicacy-preservation target option.",
    ),
)
SELECTED_TARGET_RIVAL_BLOCKER_WHY = (
    "selected target gap narrowed, but explicit mechanism, return-summary, "
    "chemistry-register, and object-field overload risks remain."
)
SELECTED_TARGET_RIVAL_NEXT_CYCLE_IMPLICATION = (
    "strongest rival pressure must remain active through consolidation and next "
    "target selection."
)


@dataclass(frozen=True)
class EvidenceLoopReviewResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class LoopReviewSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_packet_artifact_id: str | None
    synthesis_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_chain: list[dict[str, Any]]
    selected_candidate: dict[str, Any]
    proof_packet: dict[str, Any] | None
    reader_state_packet: dict[str, Any] | None
    prior_best_packet: dict[str, Any] | None
    prior_proof_packet: dict[str, Any] | None
    prior_reader_state_packet: dict[str, Any] | None
    strategy_packet: dict[str, Any] | None
    source_parent_ids: tuple[str, ...]


@dataclass(frozen=True)
class NonlocalLawCandidateLoopReviewSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_packet_artifact_id: str | None
    payloads: dict[str, dict[str, Any]]
    synthesis_artifact_ids: dict[str, str]
    active_risks: tuple[dict[str, Any], ...]
    source_parent_ids: tuple[str, ...]
    superseded_loop_review_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectedTargetLoopReviewSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_packet_artifact_id: str | None
    payloads: dict[str, dict[str, Any]]
    synthesis_artifact_ids: dict[str, str]
    active_risks: tuple[dict[str, Any], ...]
    source_parent_ids: tuple[str, ...]
    superseded_loop_review_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class NonlocalLoopReviewSupersessionContext:
    corrected_current_valid_loop_review_exists: bool
    superseded_loop_review_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


def run_evidence_loop_review(
    config: AbiConfig,
    *,
    synthesis_packet: Path | str,
) -> EvidenceLoopReviewResult:
    initialize_database(config)
    synthesis_packet_dir = _resolve_path(config, synthesis_packet)
    if not synthesis_packet_dir.exists() or not synthesis_packet_dir.is_dir():
        return _refusal(
            synthesis_packet=synthesis_packet_dir,
            message=(
                "Evidence loop review refused; synthesis packet directory not found: "
                f"{synthesis_packet_dir}"
            ),
        )

    if (synthesis_packet_dir / f"{NONLOCAL_SYNTHESIS_PACKET_ARTIFACT}.json").exists():
        return _run_nonlocal_law_candidate_loop_review(config, synthesis_packet_dir)
    if (
        synthesis_packet_dir / f"{SELECTED_TARGET_SYNTHESIS_PACKET_ARTIFACT}.json"
    ).exists():
        return _run_selected_target_loop_review(config, synthesis_packet_dir)

    try:
        subject = _load_subject(config, synthesis_packet_dir)
    except ValueError as error:
        return _refusal(synthesis_packet=synthesis_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                synthesis_packet=synthesis_packet_dir,
                message=(
                    "Evidence loop review refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_EVIDENCE_LOOP_REVIEW_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "evidence_loop_review")
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=EVIDENCE_LOOP_REVIEW_LINEAGE_ID,
            created_by=EVIDENCE_LOOP_REVIEW_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["evidence_loop_review_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir,
        )
        artifacts["evidence_loop_review_subject_manifest"] = writer.write_artifact(
            "evidence_loop_review_subject_manifest",
            payloads["evidence_loop_review_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["completed_cycle_map"] = _build_completed_cycle_map(subject)
        artifacts["completed_cycle_map"] = writer.write_artifact(
            "completed_cycle_map",
            payloads["completed_cycle_map"],
            parent_ids=[artifacts["evidence_loop_review_subject_manifest"].id],
        )

        payloads["current_best_candidate_review"] = _build_current_best_candidate_review(
            subject
        )
        artifacts["current_best_candidate_review"] = writer.write_artifact(
            "current_best_candidate_review",
            payloads["current_best_candidate_review"],
            parent_ids=[
                artifacts["evidence_loop_review_subject_manifest"].id,
                artifacts["completed_cycle_map"].id,
            ],
        )

        payloads["evidence_quality_review"] = _build_evidence_quality_review(subject)
        artifacts["evidence_quality_review"] = writer.write_artifact(
            "evidence_quality_review",
            payloads["evidence_quality_review"],
            parent_ids=[
                artifacts["current_best_candidate_review"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["reader_state_progress_review"] = _build_reader_state_progress_review(
            subject
        )
        artifacts["reader_state_progress_review"] = writer.write_artifact(
            "reader_state_progress_review",
            payloads["reader_state_progress_review"],
            parent_ids=[artifacts["evidence_quality_review"].id],
        )

        payloads["strongest_rival_status_review"] = _build_strongest_rival_status_review(
            subject
        )
        artifacts["strongest_rival_status_review"] = writer.write_artifact(
            "strongest_rival_status_review",
            payloads["strongest_rival_status_review"],
            parent_ids=[
                artifacts["reader_state_progress_review"].id,
                artifacts["current_best_candidate_review"].id,
            ],
        )

        payloads["residual_blocker_taxonomy"] = _build_residual_blocker_taxonomy(
            subject
        )
        artifacts["residual_blocker_taxonomy"] = writer.write_artifact(
            "residual_blocker_taxonomy",
            payloads["residual_blocker_taxonomy"],
            parent_ids=[
                artifacts["reader_state_progress_review"].id,
                artifacts["strongest_rival_status_review"].id,
            ],
        )

        payloads["drift_risk_report"] = _build_drift_risk_report(subject)
        artifacts["drift_risk_report"] = writer.write_artifact(
            "drift_risk_report",
            payloads["drift_risk_report"],
            parent_ids=[
                artifacts["residual_blocker_taxonomy"].id,
                artifacts["current_best_candidate_review"].id,
            ],
        )

        payloads["loop_integrity_report"] = _build_loop_integrity_report(
            subject,
            payloads["drift_risk_report"],
        )
        artifacts["loop_integrity_report"] = writer.write_artifact(
            "loop_integrity_report",
            payloads["loop_integrity_report"],
            parent_ids=[
                artifacts["evidence_quality_review"].id,
                artifacts["drift_risk_report"].id,
            ],
        )

        payloads["next_action_decision"] = _build_next_action_decision(
            subject,
            payloads["drift_risk_report"],
            payloads["loop_integrity_report"],
        )
        artifacts["next_action_decision"] = writer.write_artifact(
            "next_action_decision",
            payloads["next_action_decision"],
            parent_ids=[
                artifacts["drift_risk_report"].id,
                artifacts["loop_integrity_report"].id,
                artifacts["residual_blocker_taxonomy"].id,
            ],
        )

        payloads["loop_controller_readiness_report"] = (
            _build_loop_controller_readiness_report(
                subject,
                payloads["drift_risk_report"],
                payloads["loop_integrity_report"],
            )
        )
        artifacts["loop_controller_readiness_report"] = writer.write_artifact(
            "loop_controller_readiness_report",
            payloads["loop_controller_readiness_report"],
            parent_ids=[
                artifacts["loop_integrity_report"].id,
                artifacts["next_action_decision"].id,
            ],
        )

        payloads["evidence_loop_review_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["evidence_loop_review_gate_report"] = writer.write_artifact(
            "evidence_loop_review_gate_report",
            payloads["evidence_loop_review_gate_report"],
            parent_ids=[
                artifacts["completed_cycle_map"].id,
                artifacts["residual_blocker_taxonomy"].id,
                artifacts["drift_risk_report"].id,
                artifacts["loop_integrity_report"].id,
                artifacts["next_action_decision"].id,
                artifacts["loop_controller_readiness_report"].id,
            ],
        )

        payloads["evidence_loop_review_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["evidence_loop_review_packet"] = writer.write_artifact(
            "evidence_loop_review_packet",
            payloads["evidence_loop_review_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "evidence_loop_review_packet"
            ],
        )

        gate_report = payloads["evidence_loop_review_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="evidence_loop_review_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=EVIDENCE_LOOP_REVIEW_LINEAGE_ID,
        )

    result_payload = {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "current_best_candidate_packet_id": subject.selected_candidate.get("packet_id"),
        "proof_packet_id": subject.selected_candidate.get("proof_packet_id"),
        "reader_state_packet_id": subject.selected_candidate.get("reader_state_packet_id")
        or subject.payloads["reader_state_evidence_adjudication"].get("packet_id"),
        "completed_cycles": payloads["completed_cycle_map"]["cycle_count"],
        "counts": payloads["evidence_loop_review_packet"]["counts"],
        "next_recommended_action": payloads["next_action_decision"][
            "recommended_next_action"
        ],
        "loop_controller_ready": payloads["loop_controller_readiness_report"][
            "ready_for_autonomous_loop_controller"
        ],
        "ready_for_full_autonomous_loop_controller": payloads[
            "loop_controller_readiness_report"
        ]["ready_for_full_autonomous_loop_controller"],
        "ready_for_supervised_next_cycle": payloads["loop_controller_readiness_report"][
            "ready_for_supervised_next_cycle"
        ],
        "loop_integrity_cleanup_required": payloads["loop_integrity_report"][
            "loop_integrity_cleanup_required"
        ],
        "next_generation_authorized": payloads["next_action_decision"][
            "next_generation_authorized"
        ],
        "next_generation_blockers": payloads["next_action_decision"][
            "next_generation_blockers"
        ],
        "stale_recommendation_detected": payloads["drift_risk_report"][
            "freshness_report"
        ]["stale_recommendation_detected"],
        "candidate_generated": False,
        "model_calls": 0,
        "gate_report": payloads["evidence_loop_review_gate_report"],
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
    }
    return EvidenceLoopReviewResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _run_nonlocal_law_candidate_loop_review(
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> EvidenceLoopReviewResult:
    try:
        subject = _load_nonlocal_subject(config, synthesis_packet_dir)
        _validate_nonlocal_subject(config, subject)
        supersession = _nonlocal_loop_review_supersession_context(config, subject)
        if supersession.corrected_current_valid_loop_review_exists:
            return _refusal(
                synthesis_packet=synthesis_packet_dir,
                message=(
                    "Evidence loop review refused; corrected current-valid "
                    "loop-review decision already exists for synthesis packet "
                    f"{subject.synthesis_packet_id}."
                ),
            )
        subject = replace(
            subject,
            superseded_loop_review_packet_id=(
                supersession.superseded_loop_review_packet_id
            ),
            supersession_reason=supersession.supersession_reason,
            stale_surface_failures=supersession.stale_surface_failures,
        )
    except ValueError as error:
        return _refusal(synthesis_packet=synthesis_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                synthesis_packet=synthesis_packet_dir,
                message=(
                    "Evidence loop review refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_EVIDENCE_LOOP_REVIEW_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_candidate_loop_review"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_nonlocal_loop_review_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_report = payloads["loop_review_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_candidate_loop_review_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_LINEAGE_ID,
        )

    packet = payloads["nonlocal_law_candidate_loop_review_packet"]
    result_payload = {
        **packet,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }
    return EvidenceLoopReviewResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _run_selected_target_loop_review(
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> EvidenceLoopReviewResult:
    try:
        subject = _load_selected_target_subject(config, synthesis_packet_dir)
        _validate_selected_target_subject(subject)
        supersession = _selected_target_loop_review_supersession_context(config, subject)
        if supersession.corrected_current_valid_loop_review_exists:
            return _refusal(
                synthesis_packet=synthesis_packet_dir,
                message=(
                    "Evidence loop review refused; corrected current-valid "
                    "selected-target loop-review decision already exists for "
                    f"synthesis packet {subject.synthesis_packet_id}."
                ),
            )
        subject = replace(
            subject,
            superseded_loop_review_packet_id=(
                supersession.superseded_loop_review_packet_id
            ),
            supersession_reason=supersession.supersession_reason,
            stale_surface_failures=supersession.stale_surface_failures,
        )
    except ValueError as error:
        return _refusal(synthesis_packet=synthesis_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                synthesis_packet=synthesis_packet_dir,
                message=(
                    "Evidence loop review refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_EVIDENCE_LOOP_REVIEW_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_selected_target_loop_review"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=SELECTED_TARGET_LOOP_REVIEW_LINEAGE_ID,
            created_by=SELECTED_TARGET_LOOP_REVIEW_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_selected_target_loop_review_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_report = payloads["selected_target_loop_review_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_loop_review_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=SELECTED_TARGET_LOOP_REVIEW_LINEAGE_ID,
        )

    packet = payloads["nonlocal_law_selected_target_loop_review_packet"]
    result_payload = {
        **packet,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }
    return EvidenceLoopReviewResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_selected_target_subject(
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> SelectedTargetLoopReviewSubject:
    payloads: dict[str, dict[str, Any]] = {}
    artifact_ids: dict[str, str] = {}
    artifact_types = (
        SELECTED_TARGET_SYNTHESIS_PACKET_ARTIFACT,
        "source_reader_state_intake_summary",
        "selected_target_effect_synthesis",
        "ablation_reader_state_alignment_report",
        "packet_0002_comparison_synthesis",
        "active_risk_synthesis_report",
        "strongest_rival_pressure_synthesis",
        "current_best_decision_recommendation",
        "future_repair_or_supersession_options",
        "loop_review_readiness_report",
        "selected_target_synthesis_gate_report",
        "project_health_scope_guard_report",
    )
    with connect(config.db_path) as connection:
        for artifact_type in artifact_types:
            path = synthesis_packet_dir / f"{artifact_type}.json"
            envelope = _read_payload_envelope(path, artifact_type)
            payloads[artifact_type] = envelope["payload"]
            artifact = _artifact_for_path(connection, path)
            if artifact is not None:
                artifact_ids[artifact_type] = artifact.id

    synthesis_packet = payloads[SELECTED_TARGET_SYNTHESIS_PACKET_ARTIFACT]
    run_id = synthesis_packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Evidence loop review refused; synthesis packet missing run_id.")
    active_risks = tuple(
        risk
        for risk in payloads["active_risk_synthesis_report"].get("active_risks", [])
        if isinstance(risk, dict)
    )
    packet_artifact_id = artifact_ids.get(SELECTED_TARGET_SYNTHESIS_PACKET_ARTIFACT)
    source_artifact_ids = [
        str(value)
        for value in synthesis_packet.get("artifact_ids", {}).values()
        if isinstance(value, str)
    ]
    parent_ids = _unique([packet_artifact_id, *source_artifact_ids, *artifact_ids.values()])
    return SelectedTargetLoopReviewSubject(
        run_id=run_id,
        synthesis_packet_dir=synthesis_packet_dir,
        synthesis_packet_id=str(
            synthesis_packet.get("packet_id") or synthesis_packet_dir.name
        ),
        synthesis_packet_artifact_id=packet_artifact_id,
        payloads=payloads,
        synthesis_artifact_ids=artifact_ids,
        active_risks=active_risks,
        source_parent_ids=tuple(parent_ids),
    )


def _validate_selected_target_subject(
    subject: SelectedTargetLoopReviewSubject,
) -> None:
    packet = _selected_target_packet(subject)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Evidence loop review refused; selected-target synthesis not accepted."
        )
    if packet.get("synthesis_executed") is not True:
        raise ValueError("Evidence loop review refused; synthesis_executed must be true.")
    expected_values = {
        "source_reader_state_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_READER_STATE_PACKET_ID
        ),
        "source_candidate_packet_id": SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID,
        "source_ablation_packet_id": SELECTED_TARGET_EXPECTED_SOURCE_ABLATION_PACKET_ID,
        "source_base_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_effect": SELECTED_TARGET_EFFECT,
        "reader_state_support": SELECTED_TARGET_READER_STATE_SUPPORT,
        "current_best_decision": SELECTED_TARGET_SYNTHESIS_CURRENT_BEST_DECISION,
        "current_best_update_recommendation": SELECTED_TARGET_SYNTHESIS_RECOMMENDATION,
        "strongest_rival_status": SELECTED_TARGET_STRONGEST_RIVAL_STATUS,
    }
    for key, expected in expected_values.items():
        if packet.get(key) != expected:
            raise ValueError(
                "Evidence loop review refused; selected-target synthesis "
                f"{key} must be {expected}."
            )
    comparison = subject.payloads["packet_0002_comparison_synthesis"]
    if comparison.get("comparison_result") != SELECTED_TARGET_COMPARISON_RESULT:
        raise ValueError(
            "Evidence loop review refused; selected-target synthesis comparison_result "
            f"must be {SELECTED_TARGET_COMPARISON_RESULT}."
        )
    for key in (
        "ready_for_loop_review",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        if packet.get(key) is not True:
            raise ValueError(
                "Evidence loop review refused; selected-target synthesis "
                f"{key} must be true."
            )
    false_expectations = (
        "loop_review_authorized",
        "current_best_updated",
        "candidate_generated",
        "generation_authorized",
        "finalization_eligible",
        "strongest_rival_defeated_claimed",
    )
    for key in false_expectations:
        if packet.get(key) is not False:
            raise ValueError(
                "Evidence loop review refused; selected-target synthesis "
                f"{key} must be false."
            )
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError("Evidence loop review refused; synthesis model_calls must be 0.")
    if comparison.get("packet_0001_not_final") is not True:
        raise ValueError(
            "Evidence loop review refused; selected-target packet_0001_not_final must be true."
        )
    if comparison.get("packet_0002_not_erased") is not True:
        raise ValueError(
            "Evidence loop review refused; selected-target packet_0002_not_erased must be true."
        )
    if _payload_has_forbidden_selected_target_claim(subject.payloads):
        raise ValueError(
            "Evidence loop review refused; selected-target synthesis carries "
            "finality, phase-shift, generation, current-best mutation, or "
            "rival-defeat claim."
        )
    risk_ids = {str(risk.get("risk_id") or "") for risk in subject.active_risks}
    expected_risks = set(SELECTED_TARGET_ACTIVE_RISK_HANDLING)
    missing = sorted(expected_risks - risk_ids)
    if missing:
        raise ValueError(
            "Evidence loop review refused; selected-target active risks missing: "
            + ", ".join(missing)
        )


def _write_selected_target_loop_review_artifacts(
    *,
    writer: PacketWriter,
    subject: SelectedTargetLoopReviewSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_selected_target_synthesis_intake_summary"] = (
        _build_selected_target_intake(subject, packet_dir)
    )
    artifacts["source_selected_target_synthesis_intake_summary"] = (
        writer.write_artifact(
            "source_selected_target_synthesis_intake_summary",
            payloads["source_selected_target_synthesis_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )
    )
    payloads["current_best_transition_decision"] = (
        _build_selected_target_current_best_transition(subject)
    )
    artifacts["current_best_transition_decision"] = writer.write_artifact(
        "current_best_transition_decision",
        payloads["current_best_transition_decision"],
        parent_ids=[artifacts["source_selected_target_synthesis_intake_summary"].id],
    )
    payloads["prior_working_current_best_preservation_report"] = (
        _build_selected_target_prior_working_preservation(subject)
    )
    artifacts["prior_working_current_best_preservation_report"] = writer.write_artifact(
        "prior_working_current_best_preservation_report",
        payloads["prior_working_current_best_preservation_report"],
        parent_ids=[artifacts["current_best_transition_decision"].id],
    )
    payloads["selected_target_evidence_summary"] = (
        _build_selected_target_evidence_summary(subject)
    )
    artifacts["selected_target_evidence_summary"] = writer.write_artifact(
        "selected_target_evidence_summary",
        payloads["selected_target_evidence_summary"],
        parent_ids=[artifacts["current_best_transition_decision"].id],
    )
    payloads["active_risk_carry_forward_report"] = (
        _build_selected_target_active_risk_carry_forward(subject)
    )
    artifacts["active_risk_carry_forward_report"] = writer.write_artifact(
        "active_risk_carry_forward_report",
        payloads["active_risk_carry_forward_report"],
        parent_ids=[artifacts["selected_target_evidence_summary"].id],
    )
    payloads["strongest_rival_blocker_status_report"] = (
        _build_selected_target_rival_blocker_status(subject)
    )
    artifacts["strongest_rival_blocker_status_report"] = writer.write_artifact(
        "strongest_rival_blocker_status_report",
        payloads["strongest_rival_blocker_status_report"],
        parent_ids=[artifacts["active_risk_carry_forward_report"].id],
    )
    payloads["next_cycle_target_seed_report"] = (
        _build_selected_target_next_cycle_seed(subject)
    )
    artifacts["next_cycle_target_seed_report"] = writer.write_artifact(
        "next_cycle_target_seed_report",
        payloads["next_cycle_target_seed_report"],
        parent_ids=[artifacts["active_risk_carry_forward_report"].id],
    )
    payloads["finalization_lock_report"] = _build_selected_target_finalization_lock(
        subject
    )
    artifacts["finalization_lock_report"] = writer.write_artifact(
        "finalization_lock_report",
        payloads["finalization_lock_report"],
        parent_ids=[artifacts["strongest_rival_blocker_status_report"].id],
    )
    payloads["selected_target_loop_review_gate_report"] = (
        _build_selected_target_gate_report(subject, payloads)
    )
    artifacts["selected_target_loop_review_gate_report"] = writer.write_artifact(
        "selected_target_loop_review_gate_report",
        payloads["selected_target_loop_review_gate_report"],
        parent_ids=[
            artifacts["current_best_transition_decision"].id,
            artifacts["active_risk_carry_forward_report"].id,
            artifacts["finalization_lock_report"].id,
        ],
    )
    payloads["project_health_scope_guard_report"] = _build_selected_target_health_report(
        subject
    )
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[artifacts["selected_target_loop_review_gate_report"].id],
    )
    payloads["nonlocal_law_selected_target_loop_review_packet"] = (
        _build_selected_target_loop_review_packet(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
    )
    artifacts["nonlocal_law_selected_target_loop_review_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_loop_review_packet",
            payloads["nonlocal_law_selected_target_loop_review_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "nonlocal_law_selected_target_loop_review_packet"
            ],
        )
    )
    return payloads, artifacts


def _build_selected_target_intake(
    subject: SelectedTargetLoopReviewSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _selected_target_packet(subject)
    return {
        **_selected_target_source_fields(subject),
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_packet_artifact_id": subject.synthesis_packet_artifact_id,
        "source_selected_target_synthesis_accepted": packet.get("accepted") is True,
        "source_selected_target_synthesis_executed": (
            packet.get("synthesis_executed") is True
        ),
        "source_selected_target_synthesis_ready_for_loop_review": (
            packet.get("ready_for_loop_review") is True
        ),
        "operator_reviewed": True,
        "local_operator_review_recorded": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "target_selected_for_next_cycle": False,
        "model_calls": 0,
        "current_best_state_mutation_performed": False,
        "global_state_mutation_performed": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_selected_target_synthesis_intake_summary_v1_controller",
    }


def _build_selected_target_current_best_transition(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_selected_target_source_fields(subject),
        "decision": SELECTED_TARGET_LOOP_REVIEW_DECISION,
        "prior_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "new_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_for_next_loop_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "promotion_basis": list(SELECTED_TARGET_PROMOTION_BASIS),
        "promotion_limits": list(SELECTED_TARGET_PROMOTION_LIMITS),
        "current_best_updated": True,
        "current_best_update_method": SELECTED_TARGET_LOOP_REVIEW_UPDATE_METHOD,
        "current_best_state_mutation_performed": False,
        "global_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "finalization_allowed": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "target_selected_for_next_cycle": False,
        "model_calls": 0,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "current_best_transition_decision_v1_controller",
    }


def _build_selected_target_prior_working_preservation(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_selected_target_source_fields(subject),
        "summary": (
            "packet_0002 is preserved as the prior working current best while "
            "packet_0001 becomes the packet-owned working current best for the "
            "next loop."
        ),
        "prior_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "new_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_for_next_loop_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "prior_working_current_best_preserved_as_history": True,
        "prior_current_best_preserved_as_history": True,
        "packet_0002_not_erased": True,
        "packet_0063_not_erased": True,
        "packet_0063_preserved_as_prior_current_best_history": True,
        "packet_0001_not_final": True,
        "current_best_transition_not_finalization": True,
        "preservation_reason": (
            "selected-target synthesis does not erase packet_0002 or mutate global "
            "current-best state."
        ),
        "retained_evidence_references": [
            "source selected-target synthesis packet",
            "source selected-target reader-state packet_0005",
            "source selected-target ablation packet_0001",
        ],
        "current_best_updated": True,
        "current_best_state_mutation_performed": False,
        "global_state_mutation_performed": False,
        "finalization_eligible": False,
        "not_finalization_evidence": True,
        "candidate_generated": False,
        "model_calls": 0,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "prior_working_current_best_preservation_report_v1_controller",
    }


def _build_selected_target_evidence_summary(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    packet = _selected_target_packet(subject)
    return {
        **_selected_target_source_fields(subject),
        "selected_target_effect": packet["selected_target_effect"],
        "reader_state_support": packet["reader_state_support"],
        "strongest_rival_status": packet["strongest_rival_status"],
        "evidence_strength": "supportive_but_incomplete",
        "summary": SELECTED_TARGET_EVIDENCE_SUMMARY,
        "promotion_basis": list(SELECTED_TARGET_PROMOTION_BASIS),
        "promotion_limits": list(SELECTED_TARGET_PROMOTION_LIMITS),
        "selected_target_effect_summary": subject.payloads[
            "selected_target_effect_synthesis"
        ].get("summary"),
        "comparison_result": subject.payloads["packet_0002_comparison_synthesis"].get(
            "comparison_result"
        ),
        "not_finalization_evidence": True,
        "candidate_superiority_not_final_proof": True,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "selected_target_evidence_summary_v1_controller",
    }


def _build_selected_target_active_risk_carry_forward(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    risks = []
    for risk in subject.active_risks:
        risk_id = str(risk.get("risk_id") or "")
        risks.append(
            {
                "risk_id": risk_id,
                "risk": risk.get("risk") or risk_id.replace("_", " "),
                "source_synthesis_packet_id": subject.synthesis_packet_id,
                "source_reader_state_packet_id": (
                    SELECTED_TARGET_EXPECTED_SOURCE_READER_STATE_PACKET_ID
                ),
                "blocks_finalization": True,
                "carried_forward_to_next_loop": True,
                "recommended_next_handling": (
                    SELECTED_TARGET_ACTIVE_RISK_HANDLING.get(
                        risk_id,
                        "carry forward as unresolved selected-target risk",
                    )
                ),
                "possible_next_target_seed": SELECTED_TARGET_RISK_TARGET_SEEDS.get(
                    risk_id
                ),
                "source_probe": risk.get("source_probe"),
            }
        )
    return {
        **_selected_target_source_fields(subject),
        "active_risks": risks,
        "active_risk_count": len(risks),
        "active_risks_remain": True,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "target_selected_for_next_cycle": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "active_risk_carry_forward_report_v1_controller",
    }


def _build_selected_target_rival_blocker_status(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    packet = _selected_target_packet(subject)
    return {
        **_selected_target_source_fields(subject),
        "strongest_rival_status": packet["strongest_rival_status"],
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_comparison_passed": False,
        "why_blocking": SELECTED_TARGET_RIVAL_BLOCKER_WHY,
        "next_cycle_implication": SELECTED_TARGET_RIVAL_NEXT_CYCLE_IMPLICATION,
        "finalization_blocked_by_rival_pressure": True,
        "rival_pressure_summary": subject.payloads[
            "strongest_rival_pressure_synthesis"
        ].get("pressure_summary"),
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "strongest_rival_blocker_status_report_v1_controller",
    }


def _build_selected_target_next_cycle_seed(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    options = _selected_target_next_cycle_target_options(subject)
    return {
        **_selected_target_source_fields(subject),
        "next_cycle_target_options": options,
        "target_seed_options_exposed": True,
        "target_seed_option_ids": [option["target_seed_id"] for option in options],
        "recommended_next_target_seed": None,
        "target_selected_for_next_cycle": False,
        "next_target_not_selected": True,
        "do_not_generate_yet": True,
        "do_not_create_work_order_yet": True,
        "cycle_consolidation_required_before_next_repair": True,
        "target_selection_requires_cycle_consolidation": True,
        "consolidation_required_before_next_target_selection": True,
        "recommended_next_action": SELECTED_TARGET_NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": SELECTED_TARGET_NEXT_RECOMMENDED_ACTION,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "next_cycle_target_seed_report_v1_controller",
    }


def _build_selected_target_finalization_lock(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_selected_target_source_fields(subject),
        "finalization_eligible": False,
        "do_not_finalize": True,
        "active_risks_remain": True,
        "strongest_rival_remains_blocking": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "candidate_superiority_not_final_proof": True,
        "current_best_transition_not_finalization": True,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "model_calls": 0,
        "worker": "finalization_lock_report_v1_controller",
    }


def _build_selected_target_gate_report(
    subject: SelectedTargetLoopReviewSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    pass_gates = (
        "source_selected_target_synthesis_accepted",
        "source_selected_target_synthesis_ready_for_loop_review",
        "selected_target_effect_supported_but_incomplete",
        "reader_state_support_supportive_with_active_risks",
        "packet_0001_improves_selected_target_over_packet_0002",
        "current_best_transition_packet_only",
        "prior_working_current_best_preserved",
        "active_risks_carried_forward",
        "strongest_rival_remains_blocking",
        "target_seed_options_exposed",
        "next_target_not_selected",
        "consolidation_required_before_next_target_selection",
        "no_generation",
        "no_candidate",
        "no_model_calls",
        "no_final_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    )
    block_gates = (
        "finalization_eligible",
        "strongest_rival_resolved",
        "generation_authorized",
        "work_order_created",
        "target_selected_for_next_cycle",
    )
    gate_results = [
        _gate_result(gate_name, True) for gate_name in pass_gates
    ] + [
        _gate_result(gate_name, False, [f"{gate_name} remains blocked"], record=False)
        for gate_name in block_gates
    ]
    blockers = [
        "finalization remains refused",
        "strongest rival remains blocking",
        "generation remains unauthorized",
        "work order is not created",
        "next target is not selected",
    ]
    return {
        **_selected_target_source_fields(subject),
        "passed": False,
        "eligible": False,
        "decision": SELECTED_TARGET_LOOP_REVIEW_DECISION,
        "current_best_updated": True,
        "new_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_for_next_loop_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "prior_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "active_risk_count": payloads["active_risk_carry_forward_report"][
            "active_risk_count"
        ],
        "strongest_rival_remains_blocking": True,
        "target_selected_for_next_cycle": False,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "target_seed_options_exposed": True,
        "next_target_not_selected": True,
        "consolidation_required_before_next_target_selection": True,
        "no_candidate_generated_by_loop_review": True,
        "no_model_calls_by_loop_review": True,
        "finalization_eligible": False,
        "gate_results": gate_results,
        "passed_gates": list(pass_gates),
        "failed_gates": list(block_gates),
        "unresolved_blockers": blockers,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "selected_target_loop_review_gate_report_v1_controller",
    }


def _build_selected_target_health_report(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_selected_target_source_fields(subject),
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_introduced": True,
        "no_candidate_text_mutation": True,
        "current_best_state_mutation_performed": False,
        "global_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "finalization_eligible": False,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "strongest_rival_remains_blocking": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": False,
        "no_work_order_introduced": True,
        "target_selected_for_next_cycle": False,
        "no_target_selection_introduced": True,
        "model_calls": 0,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_selected_target_loop_review_packet(
    *,
    subject: SelectedTargetLoopReviewSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=SELECTED_TARGET_LOOP_REVIEW_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_loop_review_packet",
    )
    return {
        **_selected_target_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "superseded_loop_review_packet_id": subject.superseded_loop_review_packet_id,
        "supersession_reason": subject.supersession_reason,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_loop_review_packet",
        ],
        "counts": {**counts, "model_calls": 0, "candidate_artifacts_created": 0},
        "decision": SELECTED_TARGET_LOOP_REVIEW_DECISION,
        "prior_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        ),
        "new_working_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "new_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_for_next_loop_packet_id": (
            SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": (
            SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "current_best_updated": True,
        "current_best_update_method": SELECTED_TARGET_LOOP_REVIEW_UPDATE_METHOD,
        "current_best_state_mutation_performed": False,
        "global_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "finalization_allowed": False,
        "prior_working_current_best_preserved_as_history": True,
        "prior_current_best_preserved_as_history": True,
        "prior_historical_current_best_preserved": True,
        "prior_preservation_summary": payloads[
            "prior_working_current_best_preservation_report"
        ]["summary"],
        "evidence_summary": payloads["selected_target_evidence_summary"]["summary"],
        "selected_target_effect": SELECTED_TARGET_EFFECT,
        "reader_state_support": SELECTED_TARGET_READER_STATE_SUPPORT,
        "active_risks_carried_forward": True,
        "active_risk_count": payloads["active_risk_carry_forward_report"][
            "active_risk_count"
        ],
        "active_risks_remain": True,
        "strongest_rival_status": SELECTED_TARGET_STRONGEST_RIVAL_STATUS,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "next_cycle_target_options": payloads["next_cycle_target_seed_report"][
            "next_cycle_target_options"
        ],
        "target_seed_options_exposed": True,
        "target_seed_option_ids": [
            option["target_seed_id"]
            for option in payloads["next_cycle_target_seed_report"][
                "next_cycle_target_options"
            ]
        ],
        "recommended_next_target_seed": None,
        "target_selected_for_next_cycle": False,
        "next_target_not_selected": True,
        "work_order_created": False,
        "cycle_consolidation_required_before_next_repair": True,
        "target_selection_requires_cycle_consolidation": True,
        "consolidation_required_before_next_target_selection": True,
        "ready_for_cycle_consolidation": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "no_candidate_introduced": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "next_recommended_action": SELECTED_TARGET_NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["selected_target_loop_review_gate_report"],
        "worker": "nonlocal_law_selected_target_loop_review_packet_v1_controller",
    }


def _load_nonlocal_subject(
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> NonlocalLawCandidateLoopReviewSubject:
    payloads: dict[str, dict[str, Any]] = {}
    artifact_ids: dict[str, str] = {}
    artifact_types = (
        NONLOCAL_SYNTHESIS_PACKET_ARTIFACT,
        "candidate_law_effect_synthesis",
        "packet_0063_comparison_synthesis",
        "ablation_reader_state_alignment_report",
        "active_risk_synthesis_report",
        "current_best_decision_recommendation",
        "future_repair_or_supersession_options",
        "strongest_rival_pressure_synthesis",
        "synthesis_gate_report",
        "project_health_scope_guard_report",
    )
    with connect(config.db_path) as connection:
        for artifact_type in artifact_types:
            path = synthesis_packet_dir / f"{artifact_type}.json"
            envelope = _read_payload_envelope(path, artifact_type)
            payloads[artifact_type] = envelope["payload"]
            artifact = _artifact_for_path(connection, path)
            if artifact is not None:
                artifact_ids[artifact_type] = artifact.id

    synthesis_packet = payloads[NONLOCAL_SYNTHESIS_PACKET_ARTIFACT]
    run_id = synthesis_packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Evidence loop review refused; synthesis packet missing run_id.")
    active_risks = tuple(
        risk
        for risk in payloads["active_risk_synthesis_report"].get("active_risks", [])
        if isinstance(risk, dict)
    )
    packet_artifact_id = artifact_ids.get(NONLOCAL_SYNTHESIS_PACKET_ARTIFACT)
    source_artifact_ids = [
        str(value)
        for value in synthesis_packet.get("artifact_ids", {}).values()
        if isinstance(value, str)
    ]
    parent_ids = _unique([packet_artifact_id, *source_artifact_ids, *artifact_ids.values()])
    return NonlocalLawCandidateLoopReviewSubject(
        run_id=run_id,
        synthesis_packet_dir=synthesis_packet_dir,
        synthesis_packet_id=str(
            synthesis_packet.get("packet_id") or synthesis_packet_dir.name
        ),
        synthesis_packet_artifact_id=packet_artifact_id,
        payloads=payloads,
        synthesis_artifact_ids=artifact_ids,
        active_risks=active_risks,
        source_parent_ids=tuple(parent_ids),
    )


def _validate_nonlocal_subject(
    config: AbiConfig,
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> None:
    packet = _nonlocal_packet(subject)
    if packet.get("accepted") is not True:
        raise ValueError("Evidence loop review refused; nonlocal synthesis not accepted.")
    if packet.get("synthesis_executed") is not True:
        raise ValueError("Evidence loop review refused; synthesis_executed must be true.")
    if _nonlocal_synthesis_is_superseded(config, subject):
        raise ValueError(
            "Evidence loop review refused; corrected synthesis packet was superseded "
            "by a newer corrected synthesis packet."
        )
    expected_values = {
        "source_reader_state_packet_id": NONLOCAL_EXPECTED_SOURCE_READER_STATE_PACKET_ID,
        "source_candidate_packet_id": NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID,
        "source_ablation_packet_id": NONLOCAL_EXPECTED_SOURCE_ABLATION_PACKET_ID,
        "prior_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "base_candidate_packet_id": NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
        "proof_packet_id": NONLOCAL_EXPECTED_PROOF_PACKET_ID,
        "prior_reader_state_packet_id": NONLOCAL_EXPECTED_PRIOR_READER_STATE_PACKET_ID,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "candidate_law_effect": CANDIDATE_LAW_EFFECT,
        "reader_state_support": READER_STATE_SUPPORT,
        "current_best_update_recommendation": NONLOCAL_SYNTHESIS_RECOMMENDATION,
        "recommended_next_decision": NONLOCAL_RECOMMENDED_NEXT_DECISION,
        "recommended_next_option": NONLOCAL_RECOMMENDED_NEXT_DECISION,
    }
    for key, expected in expected_values.items():
        if packet.get(key) != expected:
            raise ValueError(
                "Evidence loop review refused; "
                f"nonlocal synthesis {key} must be {expected}."
            )
    required_strings = (
        "strongest_rival_status",
        "law_effect_summary",
        "comparison_summary",
        "ablation_reader_state_alignment",
        "decision_summary",
    )
    for key in required_strings:
        if not _string_value(packet.get(key)):
            raise ValueError(
                "Evidence loop review refused; "
                f"nonlocal synthesis missing {key}."
            )
    required_lists = (
        "supportive_evidence",
        "incomplete_evidence",
        "packet_0002_advantages",
        "packet_0063_retained_advantages",
        "allowed_next_decisions",
        "future_options",
    )
    for key in required_lists:
        if not _string_list(packet.get(key)):
            raise ValueError(
                "Evidence loop review refused; "
                f"nonlocal synthesis missing {key}."
            )
    bool_expectations = {
        "ready_for_loop_review": True,
        "source_chain_coherent": True,
        "current_best_update_requires_separate_loop_review": True,
        "strongest_rival_defeated_claimed": False,
        "current_best_updated": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
    }
    for key, expected in bool_expectations.items():
        if packet.get(key) is not expected:
            raise ValueError(
                "Evidence loop review refused; "
                f"nonlocal synthesis {key} must be {str(expected).lower()}."
            )
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError("Evidence loop review refused; synthesis model_calls must be 0.")
    if _payload_has_forbidden_nonlocal_claim(subject.payloads):
        raise ValueError(
            "Evidence loop review refused; nonlocal synthesis carries finality, "
            "phase-shift, current-best update, or rival-defeat claim."
        )
    if len(subject.active_risks) < 4:
        raise ValueError("Evidence loop review refused; active risks are missing.")


def _write_nonlocal_loop_review_artifacts(
    *,
    writer: PacketWriter,
    subject: NonlocalLawCandidateLoopReviewSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_synthesis_intake_summary"] = _build_nonlocal_intake(
        subject,
        packet_dir,
    )
    artifacts["source_synthesis_intake_summary"] = writer.write_artifact(
        "source_synthesis_intake_summary",
        payloads["source_synthesis_intake_summary"],
        parent_ids=list(subject.source_parent_ids),
    )
    payloads["current_best_transition_decision"] = (
        _build_nonlocal_current_best_transition(subject)
    )
    artifacts["current_best_transition_decision"] = writer.write_artifact(
        "current_best_transition_decision",
        payloads["current_best_transition_decision"],
        parent_ids=[artifacts["source_synthesis_intake_summary"].id],
    )
    payloads["prior_current_best_preservation_report"] = (
        _build_nonlocal_prior_best_preservation(subject)
    )
    artifacts["prior_current_best_preservation_report"] = writer.write_artifact(
        "prior_current_best_preservation_report",
        payloads["prior_current_best_preservation_report"],
        parent_ids=[artifacts["current_best_transition_decision"].id],
    )
    payloads["promoted_candidate_evidence_summary"] = (
        _build_nonlocal_promoted_candidate_evidence(subject)
    )
    artifacts["promoted_candidate_evidence_summary"] = writer.write_artifact(
        "promoted_candidate_evidence_summary",
        payloads["promoted_candidate_evidence_summary"],
        parent_ids=[artifacts["current_best_transition_decision"].id],
    )
    payloads["active_risk_carry_forward_report"] = (
        _build_nonlocal_active_risk_carry_forward(subject, packet_dir)
    )
    artifacts["active_risk_carry_forward_report"] = writer.write_artifact(
        "active_risk_carry_forward_report",
        payloads["active_risk_carry_forward_report"],
        parent_ids=[artifacts["promoted_candidate_evidence_summary"].id],
    )
    payloads["strongest_rival_blocker_status_report"] = (
        _build_nonlocal_rival_blocker_status(subject)
    )
    artifacts["strongest_rival_blocker_status_report"] = writer.write_artifact(
        "strongest_rival_blocker_status_report",
        payloads["strongest_rival_blocker_status_report"],
        parent_ids=[artifacts["active_risk_carry_forward_report"].id],
    )
    payloads["next_cycle_target_seed_report"] = _build_nonlocal_next_cycle_seed(subject)
    artifacts["next_cycle_target_seed_report"] = writer.write_artifact(
        "next_cycle_target_seed_report",
        payloads["next_cycle_target_seed_report"],
        parent_ids=[artifacts["active_risk_carry_forward_report"].id],
    )
    payloads["finalization_lock_report"] = _build_nonlocal_finalization_lock(subject)
    artifacts["finalization_lock_report"] = writer.write_artifact(
        "finalization_lock_report",
        payloads["finalization_lock_report"],
        parent_ids=[artifacts["strongest_rival_blocker_status_report"].id],
    )
    payloads["loop_review_gate_report"] = _build_nonlocal_gate_report(
        subject,
        payloads,
    )
    artifacts["loop_review_gate_report"] = writer.write_artifact(
        "loop_review_gate_report",
        payloads["loop_review_gate_report"],
        parent_ids=[
            artifacts["current_best_transition_decision"].id,
            artifacts["active_risk_carry_forward_report"].id,
            artifacts["finalization_lock_report"].id,
        ],
    )
    payloads["project_health_scope_guard_report"] = _build_nonlocal_health_report(
        subject
    )
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[artifacts["loop_review_gate_report"].id],
    )
    payloads["nonlocal_law_candidate_loop_review_packet"] = (
        _build_nonlocal_loop_review_packet(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
    )
    artifacts["nonlocal_law_candidate_loop_review_packet"] = writer.write_artifact(
        "nonlocal_law_candidate_loop_review_packet",
        payloads["nonlocal_law_candidate_loop_review_packet"],
        parent_ids=[
            artifact.id
            for artifact_type, artifact in artifacts.items()
            if artifact_type != "nonlocal_law_candidate_loop_review_packet"
        ],
    )
    return payloads, artifacts


def _build_nonlocal_intake(
    subject: NonlocalLawCandidateLoopReviewSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _nonlocal_packet(subject)
    return {
        **_nonlocal_source_fields(subject),
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_packet_artifact_id": subject.synthesis_packet_artifact_id,
        "source_synthesis_accepted": packet.get("accepted") is True,
        "source_synthesis_executed": packet.get("synthesis_executed") is True,
        "source_chain_coherent": packet.get("source_chain_coherent") is True,
        "ready_for_loop_review": packet.get("ready_for_loop_review") is True,
        "operator_reviewed": True,
        "local_operator_review_recorded": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "current_best_state_mutation_performed": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_synthesis_intake_summary_v1_controller",
    }


def _build_nonlocal_current_best_transition(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    packet = _nonlocal_packet(subject)
    return {
        **_nonlocal_source_fields(subject),
        "decision": NONLOCAL_LOOP_REVIEW_DECISION,
        "prior_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "new_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "promotion_basis": [
            f"candidate_law_effect {packet['candidate_law_effect']}",
            f"reader_state_support {packet['reader_state_support']}",
            "first-read pressure improved",
            "object-event consequence improved",
            "explanation timing improved",
            "reread return improved",
            "non-imitation passed",
            "ablation identified coherent law-bearing choices",
            "synthesis recommended promotion",
        ],
        "promotion_limits": [
            "strongest rival remains blocking",
            "active risks remain",
            "finalization refused",
            "no strongest-rival defeat claim",
            "no phase-shift claim",
        ],
        "current_best_updated": True,
        "current_best_update_method": "loop_review_packet_only",
        "current_best_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "prior_current_best_preserved_as_history": True,
        "finalization_allowed": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "current_best_transition_decision_v1_controller",
    }


def _build_nonlocal_prior_best_preservation(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_nonlocal_source_fields(subject),
        "summary": NONLOCAL_PRIOR_PRESERVATION_SUMMARY,
        "prior_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "prior_current_best_preserved_as_history": True,
        "preservation_reason": (
            "packet_0063 remains the prior current-best historical baseline while "
            "packet_0002 becomes the working current best by loop-review packet."
        ),
        "retained_evidence_references": [
            "proof packet_0034",
            "prior reader-state packet_0013",
            "prior strongest-rival pressure context",
        ],
        "preserved_strengths": list(
            subject.payloads["packet_0063_comparison_synthesis"].get(
                "packet_0063_preserved_strengths",
                [],
            )
        ),
        "retained_advantages": list(
            subject.payloads["packet_0063_comparison_synthesis"].get(
                "packet_0063_retained_advantages",
                [],
            )
        ),
        "current_best_updated": True,
        "current_best_state_mutation_performed": False,
        "finalization_eligible": False,
        "not_finalization_evidence": True,
        "candidate_generated": False,
        "model_calls": 0,
        "no_phase_shift_claim": True,
        "worker": "prior_current_best_preservation_report_v1_controller",
    }


def _build_nonlocal_promoted_candidate_evidence(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    packet = _nonlocal_packet(subject)
    return {
        **_nonlocal_source_fields(subject),
        "summary": NONLOCAL_EVIDENCE_SUMMARY,
        "new_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "candidate_law_effect": packet["candidate_law_effect"],
        "reader_state_support": packet["reader_state_support"],
        "strongest_rival_status": packet["strongest_rival_status"],
        "law_effect_summary": packet["law_effect_summary"],
        "supportive_evidence": list(packet["supportive_evidence"]),
        "packet_0002_advantages": list(packet["packet_0002_advantages"]),
        "ablation_reader_state_alignment": packet["ablation_reader_state_alignment"],
        "promotion_basis": _nonlocal_promotion_basis(packet),
        "promotion_limits": _nonlocal_promotion_limits(),
        "evidence_strength": "loop_review_promotable_not_final",
        "promotion_classification": "working_current_best_for_next_loop_not_final",
        "not_finalization_evidence": True,
        "strongest_rival_defeated_claimed": False,
        "current_best_updated": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "promoted_candidate_evidence_summary_v1_controller",
    }


def _build_nonlocal_active_risk_carry_forward(
    subject: NonlocalLawCandidateLoopReviewSubject,
    packet_dir: Path,
) -> dict[str, object]:
    risks = []
    for risk in subject.active_risks:
        risk_id = str(risk.get("risk_id") or "")
        risks.append(
            {
                "risk_id": risk_id,
                "risk": risk.get("risk"),
                "reader_state_probe": risk.get("reader_state_probe", {}),
                "suggested_test_or_control": risk.get("test_with", []),
                "blocks_finalization": True,
                "recommended_next_handling": NONLOCAL_ACTIVE_RISK_HANDLING.get(
                    risk_id,
                    "carry forward as unresolved nonlocal-law candidate risk",
                ),
                "carried_forward_to_next_loop": True,
                "source_synthesis_packet_id": subject.synthesis_packet_id,
                "source_loop_review_packet_id": packet_dir.name,
            }
        )
    return {
        **_nonlocal_source_fields(subject),
        "active_risks": risks,
        "active_risk_count": len(risks),
        "active_risks_remain": True,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "active_risk_carry_forward_report_v1_controller",
    }


def _build_nonlocal_rival_blocker_status(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    packet = _nonlocal_packet(subject)
    return {
        **_nonlocal_source_fields(subject),
        "strongest_rival_status": packet["strongest_rival_status"],
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_comparison_passed": False,
        "why_blocking": NONLOCAL_RIVAL_BLOCKER_WHY,
        "next_cycle_implication": NONLOCAL_RIVAL_NEXT_CYCLE_IMPLICATION,
        "finalization_blocked_by_rival_pressure": True,
        "rival_pressure_summary": subject.payloads[
            "strongest_rival_pressure_synthesis"
        ].get("pressure_summary"),
        "current_best_updated": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "strongest_rival_blocker_status_report_v1_controller",
    }


def _build_nonlocal_next_cycle_seed(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_nonlocal_source_fields(subject),
        "seed_target_options": list(NONLOCAL_NEXT_CYCLE_TARGET_OPTIONS),
        "next_cycle_target_options": _nonlocal_next_cycle_target_options(subject),
        "recommended_next_action": NONLOCAL_NEXT_RECOMMENDED_ACTION,
        "recommended_next_target_seed": NONLOCAL_RECOMMENDED_NEXT_TARGET_SEED,
        "do_not_generate_yet": True,
        "do_not_create_work_order_yet": True,
        "cycle_consolidation_required_before_next_repair": True,
        "target_selection_requires_cycle_consolidation": True,
        "recommended_sequence": [
            "consolidate_nonlocal_law_cycle_learning_before_next_repair",
            "review_active_risks_before_target_selection",
            "select one narrow repair target only after operator review",
        ],
        "next_recommended_action": NONLOCAL_NEXT_RECOMMENDED_ACTION,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_cycle_target_seed_report_v1_controller",
    }


def _build_nonlocal_finalization_lock(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_nonlocal_source_fields(subject),
        "finalization_eligible": False,
        "do_not_finalize": True,
        "strongest_rival_remains_blocking": True,
        "active_risks_remain": True,
        "external_validation_missing_or_not_required_for_this_loop": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "current_best_updated": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "worker": "finalization_lock_report_v1_controller",
    }


def _build_nonlocal_gate_report(
    subject: NonlocalLawCandidateLoopReviewSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("source_synthesis_consumed", True),
        _gate_result("source_chain_coherent", True),
        _gate_result("ready_for_loop_review", True),
        _gate_result("current_best_transition_recorded", True),
        _gate_result("active_risks_carried_forward", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival remains blocking"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["loop review is not finalization evidence"],
            record=False,
        ),
    ]
    blockers = [
        "strongest rival remains blocking",
        "active risks remain",
        "finalization remains refused",
        "next repair target is not selected",
        "generation remains unauthorized",
    ]
    return {
        **_nonlocal_source_fields(subject),
        "passed": False,
        "eligible": False,
        "decision": NONLOCAL_LOOP_REVIEW_DECISION,
        "current_best_updated": True,
        "new_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        ),
        "active_risk_count": payloads["active_risk_carry_forward_report"][
            "active_risk_count"
        ],
        "strongest_rival_remains_blocking": True,
        "finalization_eligible": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "unresolved_blockers": blockers,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "loop_review_gate_report_v1_controller",
    }


def _build_nonlocal_health_report(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    return {
        **_nonlocal_source_fields(subject),
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_text_mutation": True,
        "current_best_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "finalization_eligible": False,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_remains_blocking": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_nonlocal_loop_review_packet(
    *,
    subject: NonlocalLawCandidateLoopReviewSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_candidate_loop_review_packet",
    )
    return {
        **_nonlocal_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "superseded_loop_review_packet_id": subject.superseded_loop_review_packet_id,
        "supersession_reason": subject.supersession_reason,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "nonlocal_law_candidate_loop_review_packet"],
        "counts": {**counts, "model_calls": 0, "candidate_artifacts_created": 0},
        "decision": NONLOCAL_LOOP_REVIEW_DECISION,
        "new_current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_candidate_packet_id": (
            NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "current_best_updated": True,
        "current_best_update_method": "loop_review_packet_only",
        "current_best_state_mutation_performed": False,
        "current_best_decision_packet_is_source_of_truth": True,
        "prior_current_best_preserved_as_history": True,
        "prior_preservation_summary": payloads[
            "prior_current_best_preservation_report"
        ]["summary"],
        "evidence_summary": payloads["promoted_candidate_evidence_summary"]["summary"],
        "active_risks_carried_forward": True,
        "active_risk_count": payloads["active_risk_carry_forward_report"][
            "active_risk_count"
        ],
        "active_risks_remain": True,
        "strongest_rival_status": payloads["strongest_rival_blocker_status_report"][
            "strongest_rival_status"
        ],
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "next_cycle_target_options": payloads["next_cycle_target_seed_report"][
            "next_cycle_target_options"
        ],
        "recommended_next_target_seed": payloads["next_cycle_target_seed_report"][
            "recommended_next_target_seed"
        ],
        "cycle_consolidation_required_before_next_repair": True,
        "target_selection_requires_cycle_consolidation": True,
        "ready_for_cycle_consolidation": True,
        "current_best_for_next_loop_packet_id": (
            NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        ),
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "next_recommended_action": NONLOCAL_NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["loop_review_gate_report"],
        "worker": "nonlocal_law_candidate_loop_review_packet_v1_controller",
    }


def _nonlocal_source_fields(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, object]:
    packet = _nonlocal_packet(subject)
    return {
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_ablation_packet_id": packet.get("source_ablation_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_strategy_packet_id": packet.get("source_strategy_packet_id"),
        "source_diagnostic_packet_id": packet.get("source_diagnostic_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "proof_packet_id": packet.get("proof_packet_id"),
        "prior_reader_state_packet_id": packet.get("prior_reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "superseded_loop_review_packet_id": (
            subject.superseded_loop_review_packet_id
        ),
        "supersession_reason": subject.supersession_reason,
    }


def _nonlocal_packet(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> dict[str, Any]:
    return subject.payloads[NONLOCAL_SYNTHESIS_PACKET_ARTIFACT]


def _nonlocal_promotion_basis(packet: dict[str, Any]) -> list[str]:
    return [
        f"candidate_law_effect {packet['candidate_law_effect']}",
        f"reader_state_support {packet['reader_state_support']}",
        "first-read pressure improved",
        "object-event consequence improved",
        "explanation timing improved",
        "reread return improved",
        "non-imitation passed",
        "ablation identified coherent law-bearing choices",
        "synthesis recommended promotion",
    ]


def _nonlocal_promotion_limits() -> list[str]:
    return [
        "strongest rival remains blocking",
        "active risks remain",
        "finalization refused",
        "no strongest-rival defeat claim",
        "no phase-shift claim",
    ]


def _nonlocal_next_cycle_target_options(
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> list[dict[str, object]]:
    risk_map = {str(risk.get("risk_id") or ""): risk for risk in subject.active_risks}
    options: list[dict[str, object]] = []
    for option_id in NONLOCAL_NEXT_CYCLE_TARGET_OPTIONS:
        risk_id = NONLOCAL_TARGET_OPTION_RISK_MAP[option_id]
        risk = risk_map.get(risk_id, {})
        options.append(
            {
                "option_id": option_id,
                "source_risk_id": risk_id,
                "source_risk": risk.get("risk"),
                "source_synthesis_packet_id": subject.synthesis_packet_id,
                "requires_cycle_consolidation_before_selection": True,
                "candidate_generation_authorized": False,
            }
        )
    return options


def _selected_target_source_fields(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, object]:
    packet = _selected_target_packet(subject)
    return {
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_ablation_packet_id": packet.get("source_ablation_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_target_selection_packet_id": packet.get("source_target_selection_packet_id"),
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_base_candidate_packet_id": packet.get("source_base_candidate_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "prior_historical_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "law_id": packet.get("law_id"),
        "selected_target_seed_id": packet.get("selected_target_seed_id"),
        "selected_risk_id": packet.get("selected_risk_id"),
        "superseded_loop_review_packet_id": (
            subject.superseded_loop_review_packet_id
        ),
        "supersession_reason": subject.supersession_reason,
    }


def _selected_target_packet(
    subject: SelectedTargetLoopReviewSubject,
) -> dict[str, Any]:
    return subject.payloads[SELECTED_TARGET_SYNTHESIS_PACKET_ARTIFACT]


def _selected_target_next_cycle_target_options(
    subject: SelectedTargetLoopReviewSubject,
) -> list[dict[str, object]]:
    _ = subject
    return [
        {
            "rank": rank,
            "option_id": option_id,
            "target_seed_id": option_id,
            "source_risk_id": source_risk_id,
            "target_summary": target_summary,
            "recommended_next_handling": recommended_next_handling,
            "requires_cycle_consolidation_before_selection": True,
            "candidate_generation_authorized": False,
            "work_order_created": False,
        }
        for rank, (
            option_id,
            source_risk_id,
            target_summary,
            recommended_next_handling,
        ) in enumerate(
            SELECTED_TARGET_NEXT_CYCLE_TARGET_OPTIONS,
            start=1,
        )
    ]


def _selected_target_loop_review_supersession_context(
    config: AbiConfig,
    subject: SelectedTargetLoopReviewSubject,
) -> NonlocalLoopReviewSupersessionContext:
    root = config.run_dir(subject.run_id) / "nonlocal_law_selected_target_loop_review"
    if not root.exists():
        return NonlocalLoopReviewSupersessionContext(
            corrected_current_valid_loop_review_exists=False
        )
    stale_packet_id: str | None = None
    stale_failures: tuple[str, ...] = ()
    for packet_dir in sorted(root.glob("packet_*"), reverse=True):
        path = packet_dir / "nonlocal_law_selected_target_loop_review_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload_envelope(
                path,
                "nonlocal_law_selected_target_loop_review_packet",
            )["payload"]
        except ValueError:
            continue
        if not _is_matching_selected_target_loop_review(
            payload,
            synthesis_packet_id=subject.synthesis_packet_id,
        ):
            continue
        failures = tuple(
            _selected_target_loop_review_surface_failures(packet_dir, payload)
        )
        if not failures:
            return NonlocalLoopReviewSupersessionContext(
                corrected_current_valid_loop_review_exists=True,
                superseded_loop_review_packet_id=str(
                    payload.get("packet_id") or packet_dir.name
                ),
            )
        if stale_packet_id is None:
            stale_packet_id = str(payload.get("packet_id") or packet_dir.name)
            stale_failures = failures
    if stale_packet_id is not None:
        return NonlocalLoopReviewSupersessionContext(
            corrected_current_valid_loop_review_exists=False,
            superseded_loop_review_packet_id=stale_packet_id,
            supersession_reason=SELECTED_TARGET_LOOP_REVIEW_SUPERSESSION_REASON,
            stale_surface_failures=stale_failures,
        )
    return NonlocalLoopReviewSupersessionContext(
        corrected_current_valid_loop_review_exists=False
    )


def _is_matching_selected_target_loop_review(
    payload: dict[str, Any],
    *,
    synthesis_packet_id: str,
) -> bool:
    return (
        payload.get("accepted") is True
        and payload.get("source_synthesis_packet_id") == synthesis_packet_id
        and payload.get("decision") == SELECTED_TARGET_LOOP_REVIEW_DECISION
        and payload.get("prior_working_current_best_candidate_packet_id")
        == SELECTED_TARGET_EXPECTED_SOURCE_BASE_CANDIDATE_PACKET_ID
        and payload.get("new_working_current_best_candidate_packet_id")
        == SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        and payload.get("current_best_for_next_loop_packet_id")
        == SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        and payload.get("prior_current_best_candidate_packet_id")
        == SELECTED_TARGET_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        and payload.get("current_best_updated") is True
        and payload.get("current_best_update_method")
        == SELECTED_TARGET_LOOP_REVIEW_UPDATE_METHOD
        and payload.get("current_best_state_mutation_performed") is False
        and payload.get("global_state_mutation_performed") is False
        and payload.get("current_best_decision_packet_is_source_of_truth") is True
        and payload.get("candidate_generated") is False
        and payload.get("generation_authorized") is False
        and payload.get("work_order_created") is False
        and payload.get("target_selected_for_next_cycle") is False
        and int(payload.get("model_calls") or 0) == 0
        and payload.get("finalization_eligible") is False
        and payload.get("no_final_claim") is True
        and payload.get("no_phase_shift_claim") is True
        and payload.get("strongest_rival_defeated_claimed") is False
    )


def _selected_target_loop_review_surface_failures(
    packet_dir: Path,
    packet_payload: dict[str, Any],
) -> list[str]:
    failures: list[str] = []

    def require_string(payload: dict[str, Any], field_name: str, label: str) -> None:
        if not _string_value(payload.get(field_name)):
            failures.append(f"{label}.{field_name}")

    def require_list(payload: dict[str, Any], field_name: str, label: str) -> None:
        value = payload.get(field_name)
        if not isinstance(value, list) or not value:
            failures.append(f"{label}.{field_name}")

    def require_bool(
        payload: dict[str, Any],
        field_name: str,
        expected: bool,
        label: str,
    ) -> None:
        if payload.get(field_name) is not expected:
            failures.append(f"{label}.{field_name}")

    def payload_for(artifact_type: str) -> dict[str, Any]:
        try:
            return _read_payload_envelope(packet_dir / f"{artifact_type}.json", artifact_type)[
                "payload"
            ]
        except ValueError:
            failures.append(f"{artifact_type}.missing_or_malformed")
            return {}

    if (
        packet_payload.get("current_best_update_method")
        != SELECTED_TARGET_LOOP_REVIEW_UPDATE_METHOD
    ):
        failures.append("packet.current_best_update_method")
    if (
        packet_payload.get("current_best_for_next_loop_packet_id")
        != SELECTED_TARGET_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
    ):
        failures.append("packet.current_best_for_next_loop_packet_id")
    require_bool(packet_payload, "global_state_mutation_performed", False, "packet")
    require_bool(
        packet_payload,
        "prior_historical_current_best_preserved",
        True,
        "packet",
    )
    require_bool(packet_payload, "target_seed_options_exposed", True, "packet")
    require_list(packet_payload, "target_seed_option_ids", "packet")
    require_bool(packet_payload, "next_target_not_selected", True, "packet")
    require_bool(
        packet_payload,
        "consolidation_required_before_next_target_selection",
        True,
        "packet",
    )
    require_bool(packet_payload, "no_candidate_introduced", True, "packet")
    require_bool(packet_payload, "no_generation_path_introduced", True, "packet")
    require_bool(packet_payload, "no_model_call_introduced", True, "packet")
    require_bool(packet_payload, "no_finality_claim", True, "packet")
    require_bool(
        packet_payload,
        "no_strongest_rival_defeat_claim",
        True,
        "packet",
    )
    require_bool(packet_payload, "target_selected_for_next_cycle", False, "packet")
    require_bool(packet_payload, "work_order_created", False, "packet")
    require_list(packet_payload, "next_cycle_target_options", "packet")
    packet_options = packet_payload.get("next_cycle_target_options")
    if isinstance(packet_options, list):
        expected_option_ids = [
            option[0] for option in SELECTED_TARGET_NEXT_CYCLE_TARGET_OPTIONS
        ]
        packet_option_ids: list[str] = []
        for option in packet_options:
            if not isinstance(option, dict):
                failures.append("packet.next_cycle_target_options.item")
                continue
            target_seed_id = _string_value(option.get("target_seed_id"))
            if not target_seed_id:
                failures.append("packet.next_cycle_target_options.target_seed_id")
            else:
                packet_option_ids.append(target_seed_id)
            if not _string_value(option.get("recommended_next_handling")):
                failures.append(
                    "packet.next_cycle_target_options.recommended_next_handling"
                )
        if packet_option_ids != expected_option_ids:
            failures.append("packet.next_cycle_target_options.order")
        if packet_payload.get("target_seed_option_ids") != expected_option_ids:
            failures.append("packet.target_seed_option_ids")
    if packet_payload.get("recommended_next_target_seed") is not None:
        failures.append("packet.recommended_next_target_seed")
    require_bool(
        packet_payload,
        "cycle_consolidation_required_before_next_repair",
        True,
        "packet",
    )
    require_bool(
        packet_payload,
        "target_selection_requires_cycle_consolidation",
        True,
        "packet",
    )
    require_bool(
        packet_payload,
        "strongest_rival_remains_blocking",
        True,
        "packet",
    )
    require_bool(packet_payload, "active_risks_remain", True, "packet")
    require_string(packet_payload, "prior_preservation_summary", "packet")
    require_string(packet_payload, "evidence_summary", "packet")

    preservation = payload_for("prior_working_current_best_preservation_report")
    require_string(
        preservation,
        "summary",
        "prior_working_current_best_preservation_report",
    )
    require_bool(
        preservation,
        "packet_0002_not_erased",
        True,
        "prior_working_current_best_preservation_report",
    )
    require_bool(
        preservation,
        "prior_working_current_best_preserved_as_history",
        True,
        "prior_working_current_best_preservation_report",
    )
    require_bool(
        preservation,
        "prior_current_best_preserved_as_history",
        True,
        "prior_working_current_best_preservation_report",
    )
    require_bool(
        preservation,
        "packet_0063_not_erased",
        True,
        "prior_working_current_best_preservation_report",
    )
    require_bool(
        preservation,
        "packet_0001_not_final",
        True,
        "prior_working_current_best_preservation_report",
    )
    require_bool(
        preservation,
        "current_best_transition_not_finalization",
        True,
        "prior_working_current_best_preservation_report",
    )

    evidence = payload_for("selected_target_evidence_summary")
    if evidence.get("evidence_strength") != "supportive_but_incomplete":
        failures.append("selected_target_evidence_summary.evidence_strength")
    require_list(evidence, "promotion_basis", "selected_target_evidence_summary")
    require_list(evidence, "promotion_limits", "selected_target_evidence_summary")
    require_bool(
        evidence,
        "not_finalization_evidence",
        True,
        "selected_target_evidence_summary",
    )

    risks = payload_for("active_risk_carry_forward_report")
    active_risks = risks.get("active_risks")
    if not isinstance(active_risks, list) or len(active_risks) < len(
        SELECTED_TARGET_ACTIVE_RISK_HANDLING
    ):
        failures.append("active_risk_carry_forward_report.active_risks")
    else:
        for risk in active_risks:
            if not isinstance(risk, dict):
                failures.append("active_risk_carry_forward_report.active_risks.item")
                continue
            for field_name in (
                "risk_id",
                "risk",
                "source_synthesis_packet_id",
                "source_reader_state_packet_id",
                "recommended_next_handling",
                "possible_next_target_seed",
            ):
                if field_name not in risk:
                    failures.append(
                        f"active_risk_carry_forward_report.active_risks.{field_name}"
                    )
            if risk.get("blocks_finalization") is not True:
                failures.append(
                    "active_risk_carry_forward_report.active_risks.blocks_finalization"
                )
            if risk.get("carried_forward_to_next_loop") is not True:
                failures.append(
                    "active_risk_carry_forward_report.active_risks.carried_forward_to_next_loop"
                )

    rival = payload_for("strongest_rival_blocker_status_report")
    if rival.get("strongest_rival_status") != SELECTED_TARGET_STRONGEST_RIVAL_STATUS:
        failures.append("strongest_rival_blocker_status_report.strongest_rival_status")
    require_bool(rival, "strongest_rival_remains_blocking", True, "rival")
    require_bool(rival, "strongest_rival_defeated_claimed", False, "rival")
    require_string(rival, "why_blocking", "strongest_rival_blocker_status_report")
    require_string(
        rival,
        "next_cycle_implication",
        "strongest_rival_blocker_status_report",
    )

    seed = payload_for("next_cycle_target_seed_report")
    require_list(seed, "next_cycle_target_options", "next_cycle_target_seed_report")
    require_bool(
        seed,
        "target_seed_options_exposed",
        True,
        "next_cycle_target_seed_report",
    )
    require_list(seed, "target_seed_option_ids", "next_cycle_target_seed_report")
    seed_options = seed.get("next_cycle_target_options")
    if isinstance(seed_options, list):
        expected_option_ids = [
            option[0] for option in SELECTED_TARGET_NEXT_CYCLE_TARGET_OPTIONS
        ]
        seed_option_ids: list[str] = []
        for option in seed_options:
            if not isinstance(option, dict):
                failures.append("next_cycle_target_seed_report.next_cycle_target_options.item")
                continue
            target_seed_id = _string_value(option.get("target_seed_id"))
            if not target_seed_id:
                failures.append(
                    "next_cycle_target_seed_report.next_cycle_target_options.target_seed_id"
                )
            else:
                seed_option_ids.append(target_seed_id)
            if not _string_value(option.get("recommended_next_handling")):
                failures.append(
                    "next_cycle_target_seed_report.next_cycle_target_options.recommended_next_handling"
                )
        if seed_option_ids != expected_option_ids:
            failures.append("next_cycle_target_seed_report.next_cycle_target_options.order")
        if seed.get("target_seed_option_ids") != expected_option_ids:
            failures.append("next_cycle_target_seed_report.target_seed_option_ids")
    if seed.get("recommended_next_target_seed") is not None:
        failures.append("next_cycle_target_seed_report.recommended_next_target_seed")
    require_bool(
        seed,
        "next_target_not_selected",
        True,
        "next_cycle_target_seed_report",
    )
    require_bool(
        seed,
        "consolidation_required_before_next_target_selection",
        True,
        "next_cycle_target_seed_report",
    )
    require_bool(seed, "do_not_generate_yet", True, "next_cycle_target_seed_report")
    require_bool(
        seed,
        "do_not_create_work_order_yet",
        True,
        "next_cycle_target_seed_report",
    )
    require_bool(
        seed,
        "target_selected_for_next_cycle",
        False,
        "next_cycle_target_seed_report",
    )

    gate = payload_for("selected_target_loop_review_gate_report")
    require_bool(gate, "target_seed_options_exposed", True, "gate")
    require_bool(gate, "next_target_not_selected", True, "gate")
    require_bool(
        gate,
        "consolidation_required_before_next_target_selection",
        True,
        "gate",
    )
    require_bool(gate, "no_candidate_generated_by_loop_review", True, "gate")
    require_bool(gate, "no_model_calls_by_loop_review", True, "gate")

    health = payload_for("project_health_scope_guard_report")
    require_bool(health, "project_health_scope_guard_passed", True, "health")
    require_bool(health, "source_chain_coherent", True, "health")
    require_bool(health, "no_generation_path_introduced", True, "health")
    require_bool(health, "no_model_call_introduced", True, "health")
    require_bool(health, "no_candidate_introduced", True, "health")
    require_bool(health, "no_finality_claim", True, "health")
    require_bool(health, "no_phase_shift_claim", True, "health")
    require_bool(health, "no_strongest_rival_defeat_claim", True, "health")
    require_bool(health, "no_work_order_introduced", True, "health")
    require_bool(health, "no_target_selection_introduced", True, "health")
    require_bool(health, "global_state_mutation_performed", False, "health")
    require_bool(health, "current_best_state_mutation_performed", False, "health")
    return failures


def _nonlocal_loop_review_supersession_context(
    config: AbiConfig,
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> NonlocalLoopReviewSupersessionContext:
    root = config.run_dir(subject.run_id) / "nonlocal_law_candidate_loop_review"
    if not root.exists():
        return NonlocalLoopReviewSupersessionContext(
            corrected_current_valid_loop_review_exists=False
        )
    stale_packet_id: str | None = None
    stale_failures: tuple[str, ...] = ()
    for packet_dir in sorted(root.glob("packet_*"), reverse=True):
        path = packet_dir / "nonlocal_law_candidate_loop_review_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload_envelope(
                path,
                "nonlocal_law_candidate_loop_review_packet",
            )["payload"]
        except ValueError:
            continue
        if not _is_matching_nonlocal_loop_review(
            payload,
            synthesis_packet_id=subject.synthesis_packet_id,
        ):
            continue
        failures = tuple(_nonlocal_loop_review_surface_failures(packet_dir, payload))
        if not failures:
            return NonlocalLoopReviewSupersessionContext(
                corrected_current_valid_loop_review_exists=True,
                superseded_loop_review_packet_id=str(
                    payload.get("packet_id") or packet_dir.name
                ),
            )
        if stale_packet_id is None:
            stale_packet_id = str(payload.get("packet_id") or packet_dir.name)
            stale_failures = failures
    if stale_packet_id is not None:
        return NonlocalLoopReviewSupersessionContext(
            corrected_current_valid_loop_review_exists=False,
            superseded_loop_review_packet_id=stale_packet_id,
            supersession_reason=NONLOCAL_LOOP_REVIEW_SUPERSESSION_REASON,
            stale_surface_failures=stale_failures,
        )
    return NonlocalLoopReviewSupersessionContext(
        corrected_current_valid_loop_review_exists=False
    )


def _is_matching_nonlocal_loop_review(
    payload: dict[str, Any],
    *,
    synthesis_packet_id: str,
) -> bool:
    return (
        payload.get("accepted") is True
        and payload.get("source_synthesis_packet_id") == synthesis_packet_id
        and payload.get("decision") == NONLOCAL_LOOP_REVIEW_DECISION
        and payload.get("prior_current_best_candidate_packet_id")
        == NONLOCAL_EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
        and payload.get("new_current_best_candidate_packet_id")
        == NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
        and payload.get("current_best_updated") is True
        and payload.get("current_best_update_method") == "loop_review_packet_only"
        and payload.get("current_best_state_mutation_performed") is False
        and payload.get("current_best_decision_packet_is_source_of_truth") is True
        and payload.get("candidate_generated") is False
        and payload.get("generation_authorized") is False
        and int(payload.get("model_calls") or 0) == 0
        and payload.get("finalization_eligible") is False
        and payload.get("no_final_claim") is True
        and payload.get("no_phase_shift_claim") is True
        and payload.get("strongest_rival_defeated_claimed") is False
    )


def _nonlocal_loop_review_surface_failures(
    packet_dir: Path,
    packet_payload: dict[str, Any],
) -> list[str]:
    failures: list[str] = []

    def require_string(payload: dict[str, Any], field_name: str, label: str) -> None:
        if not _string_value(payload.get(field_name)):
            failures.append(f"{label}.{field_name}")

    def require_list(payload: dict[str, Any], field_name: str, label: str) -> None:
        value = payload.get(field_name)
        if not isinstance(value, list) or not value:
            failures.append(f"{label}.{field_name}")

    def require_bool(
        payload: dict[str, Any],
        field_name: str,
        expected: bool,
        label: str,
    ) -> None:
        if payload.get(field_name) is not expected:
            failures.append(f"{label}.{field_name}")

    def payload_for(artifact_type: str) -> dict[str, Any]:
        try:
            return _read_payload_envelope(packet_dir / f"{artifact_type}.json", artifact_type)[
                "payload"
            ]
        except ValueError:
            failures.append(f"{artifact_type}.missing_or_malformed")
            return {}

    require_string(packet_payload, "prior_preservation_summary", "packet")
    require_string(packet_payload, "evidence_summary", "packet")
    if packet_payload.get("strongest_rival_status") != "narrowed_but_blocking":
        failures.append("packet.strongest_rival_status")
    require_list(packet_payload, "next_cycle_target_options", "packet")
    if (
        packet_payload.get("recommended_next_target_seed")
        != NONLOCAL_RECOMMENDED_NEXT_TARGET_SEED
    ):
        failures.append("packet.recommended_next_target_seed")
    require_bool(
        packet_payload,
        "cycle_consolidation_required_before_next_repair",
        True,
        "packet",
    )
    require_bool(
        packet_payload,
        "target_selection_requires_cycle_consolidation",
        True,
        "packet",
    )
    require_bool(packet_payload, "ready_for_cycle_consolidation", True, "packet")
    if (
        packet_payload.get("current_best_for_next_loop_packet_id")
        != NONLOCAL_EXPECTED_SOURCE_CANDIDATE_PACKET_ID
    ):
        failures.append("packet.current_best_for_next_loop_packet_id")
    require_bool(
        packet_payload,
        "prior_current_best_preserved_as_history",
        True,
        "packet",
    )
    require_bool(
        packet_payload,
        "strongest_rival_remains_blocking",
        True,
        "packet",
    )
    require_bool(packet_payload, "active_risks_remain", True, "packet")

    prior = payload_for("prior_current_best_preservation_report")
    require_string(prior, "summary", "prior_current_best_preservation_report")
    require_list(prior, "retained_evidence_references", "prior_current_best_preservation_report")
    require_bool(prior, "not_finalization_evidence", True, "prior_current_best_preservation_report")

    evidence = payload_for("promoted_candidate_evidence_summary")
    require_string(evidence, "summary", "promoted_candidate_evidence_summary")
    if evidence.get("strongest_rival_status") != "narrowed_but_blocking":
        failures.append("promoted_candidate_evidence_summary.strongest_rival_status")
    require_list(evidence, "promotion_basis", "promoted_candidate_evidence_summary")
    require_list(evidence, "promotion_limits", "promoted_candidate_evidence_summary")
    if evidence.get("evidence_strength") != "loop_review_promotable_not_final":
        failures.append("promoted_candidate_evidence_summary.evidence_strength")
    require_bool(evidence, "not_finalization_evidence", True, "promoted_candidate_evidence_summary")

    risks = payload_for("active_risk_carry_forward_report")
    active_risks = risks.get("active_risks")
    if not isinstance(active_risks, list) or len(active_risks) < 4:
        failures.append("active_risk_carry_forward_report.active_risks")
    else:
        for risk in active_risks:
            if not isinstance(risk, dict):
                failures.append("active_risk_carry_forward_report.active_risks.item")
                continue
            for field_name in (
                "risk_id",
                "risk",
                "reader_state_probe",
                "suggested_test_or_control",
                "recommended_next_handling",
            ):
                if field_name not in risk:
                    failures.append(
                        f"active_risk_carry_forward_report.active_risks.{field_name}"
                    )
            if risk.get("blocks_finalization") is not True:
                failures.append(
                    "active_risk_carry_forward_report.active_risks.blocks_finalization"
                )
            if risk.get("carried_forward_to_next_loop") is not True:
                failures.append(
                    "active_risk_carry_forward_report.active_risks.carried_forward_to_next_loop"
                )
            if risk.get("source_synthesis_packet_id") != packet_payload.get(
                "source_synthesis_packet_id"
            ):
                failures.append(
                    "active_risk_carry_forward_report.active_risks.source_synthesis_packet_id"
                )
            if risk.get("source_loop_review_packet_id") != packet_dir.name:
                failures.append(
                    "active_risk_carry_forward_report.active_risks.source_loop_review_packet_id"
                )

    rival = payload_for("strongest_rival_blocker_status_report")
    if rival.get("strongest_rival_status") != "narrowed_but_blocking":
        failures.append("strongest_rival_blocker_status_report.strongest_rival_status")
    require_bool(rival, "strongest_rival_remains_blocking", True, "rival")
    require_bool(rival, "strongest_rival_defeated_claimed", False, "rival")
    require_string(rival, "why_blocking", "strongest_rival_blocker_status_report")
    require_string(rival, "next_cycle_implication", "strongest_rival_blocker_status_report")
    require_bool(rival, "finalization_blocked_by_rival_pressure", True, "rival")

    seed = payload_for("next_cycle_target_seed_report")
    require_list(seed, "next_cycle_target_options", "next_cycle_target_seed_report")
    if seed.get("recommended_next_action") != NONLOCAL_NEXT_RECOMMENDED_ACTION:
        failures.append("next_cycle_target_seed_report.recommended_next_action")
    if seed.get("recommended_next_target_seed") != NONLOCAL_RECOMMENDED_NEXT_TARGET_SEED:
        failures.append("next_cycle_target_seed_report.recommended_next_target_seed")
    require_bool(seed, "do_not_generate_yet", True, "next_cycle_target_seed_report")
    require_bool(seed, "do_not_create_work_order_yet", True, "next_cycle_target_seed_report")
    require_bool(
        seed,
        "cycle_consolidation_required_before_next_repair",
        True,
        "next_cycle_target_seed_report",
    )
    require_bool(
        seed,
        "target_selection_requires_cycle_consolidation",
        True,
        "next_cycle_target_seed_report",
    )
    return failures


def _nonlocal_synthesis_is_superseded(
    config: AbiConfig,
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_candidate_evidence_synthesis"
    if not root.exists():
        return False
    current_id = subject.synthesis_packet_id
    packet = _nonlocal_packet(subject)
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= current_id:
            continue
        path = packet_dir / f"{NONLOCAL_SYNTHESIS_PACKET_ARTIFACT}.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload_envelope(
                path,
                NONLOCAL_SYNTHESIS_PACKET_ARTIFACT,
            )["payload"]
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("ready_for_loop_review") is True
            and payload.get("source_reader_state_packet_id")
            == packet.get("source_reader_state_packet_id")
            and payload.get("source_candidate_packet_id")
            == packet.get("source_candidate_packet_id")
            and payload.get("superseded_synthesis_packet_id") == current_id
        ):
            return True
    return False


def _accepted_nonlocal_loop_review_exists(
    config: AbiConfig,
    subject: NonlocalLawCandidateLoopReviewSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_candidate_loop_review"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        path = packet_dir / "nonlocal_law_candidate_loop_review_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload_envelope(
                path,
                "nonlocal_law_candidate_loop_review_packet",
            )["payload"]
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_synthesis_packet_id") == subject.synthesis_packet_id
            and payload.get("current_best_updated") is True
            and payload.get("candidate_generated") is False
            and payload.get("generation_authorized") is False
            and int(payload.get("model_calls") or 0) == 0
            and payload.get("finalization_eligible") is False
        ):
            return True
    return False


def _read_payload_envelope(path: Path, artifact_type: str) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(
            "Evidence loop review refused; synthesis packet missing "
            f"{path.name}."
        )
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Evidence loop review refused; malformed synthesis artifact: "
            f"{artifact_type}.json."
        )
    return envelope


def _payload_has_forbidden_nonlocal_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key
                in {
                    "finality_claimed",
                    "phase_shift_claimed",
                    "strongest_rival_defeated_claimed",
                    "candidate_superiority_claimed",
                    "current_best_supersession_claimed",
                    "finalization_eligible",
                    "final_artifact",
                    "final_claim",
                }
                and item is True
            ):
                return True
            if key == "current_best_updated" and item is True:
                return True
            if _payload_has_forbidden_nonlocal_claim(item):
                return True
    if isinstance(value, list):
        return any(_payload_has_forbidden_nonlocal_claim(item) for item in value)
    return False


def _payload_has_forbidden_selected_target_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key
                in {
                    "finality_claimed",
                    "phase_shift_claimed",
                    "strongest_rival_defeated_claimed",
                    "candidate_superiority_claimed",
                    "current_best_supersession_claimed",
                    "finalization_eligible",
                    "final_artifact",
                    "final_claim",
                    "candidate_generated",
                    "generation_authorized",
                    "work_order_created",
                    "target_selected_for_next_cycle",
                }
                and item is True
            ):
                return True
            if key == "current_best_updated" and item is True:
                return True
            if key == "loop_review_authorized" and item is True:
                return True
            if key in {"no_final_claim", "no_phase_shift_claim"} and item is False:
                return True
            if _payload_has_forbidden_selected_target_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_forbidden_selected_target_claim(item) for item in value)
    return False


def _load_subject(config: AbiConfig, synthesis_packet_dir: Path) -> LoopReviewSubject:
    payloads = _load_required_payloads(synthesis_packet_dir)
    synthesis_packet = payloads["autonomous_evidence_synthesis_packet"]
    run_id = synthesis_packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Evidence loop review refused; synthesis packet missing run_id.")
    best = payloads["best_current_candidate_selection"]
    selected = best.get("selected_best_candidate") or synthesis_packet.get(
        "best_current_candidate"
    )
    if not isinstance(selected, dict) or not selected.get("packet_id"):
        raise ValueError(
            "Evidence loop review refused; synthesis packet missing best_current_candidate."
        )
    if selected.get("reader_state_evaluated") is not True:
        raise ValueError(
            "Evidence loop review refused; current best candidate has no reader-state evidence."
        )

    source_chain = _source_chain(payloads)
    proof_packet = _find_source(
        source_chain,
        "executed_ablation",
        str(selected.get("proof_packet_id") or ""),
    )
    reader_packet_id = str(
        selected.get("reader_state_packet_id")
        or payloads["reader_state_evidence_adjudication"].get("packet_id")
        or ""
    )
    reader_state_packet = _find_source(
        source_chain,
        "internal_reader_state_evaluation",
        reader_packet_id,
    )
    prior_best_packet = _find_source(
        source_chain,
        "bounded_macro_recomposition",
        str(selected.get("base_candidate_packet_id") or ""),
    )
    prior_proof_packet = _find_source_by_revision(
        source_chain,
        "executed_ablation",
        str((prior_best_packet or {}).get("packet_id") or ""),
    )
    prior_reader_state_packet = _find_reader_state_for_candidate(
        source_chain,
        str((prior_best_packet or {}).get("packet_id") or ""),
    )
    strategy_packet = _resolve_strategy_packet(
        config,
        run_id,
        selected,
        source_chain,
    )

    packet_path = synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    source_artifact_ids = [
        str(value)
        for value in synthesis_packet.get("artifact_ids", {}).values()
        if isinstance(value, str)
    ]
    parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *source_artifact_ids,
        ]
    )
    return LoopReviewSubject(
        run_id=run_id,
        synthesis_packet_dir=synthesis_packet_dir,
        synthesis_packet_id=str(synthesis_packet.get("packet_id") or synthesis_packet_dir.name),
        synthesis_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        synthesis_artifact_ids={
            str(key): str(value)
            for key, value in synthesis_packet.get("artifact_ids", {}).items()
            if isinstance(value, str)
        },
        payloads=payloads,
        source_chain=source_chain,
        selected_candidate=selected,
        proof_packet=proof_packet,
        reader_state_packet=reader_state_packet,
        prior_best_packet=prior_best_packet,
        prior_proof_packet=prior_proof_packet,
        prior_reader_state_packet=prior_reader_state_packet,
        strategy_packet=strategy_packet,
        source_parent_ids=tuple(parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_SYNTHESIS_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Evidence loop review refused; synthesis packet missing "
                f"{path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Evidence loop review refused; malformed synthesis artifact: "
                f"{path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    if not payloads["autonomous_evidence_synthesis_packet"].get("best_current_candidate"):
        raise ValueError(
            "Evidence loop review refused; synthesis packet missing best_current_candidate."
        )
    return payloads


def _build_subject_manifest(subject: LoopReviewSubject, packet_dir: Path) -> dict[str, object]:
    selected = subject.selected_candidate
    reader = subject.payloads["reader_state_evidence_adjudication"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_packet_artifact_id": subject.synthesis_packet_artifact_id,
        "current_best_candidate_packet_id": selected.get("packet_id"),
        "current_best_candidate_packet_kind": selected.get("packet_kind"),
        "current_best_candidate_packet_dir": selected.get("packet_dir"),
        "current_best_candidate_text_sha256": selected.get("text_sha256"),
        "proof_packet_id": selected.get("proof_packet_id"),
        "proof_packet_dir": selected.get("proof_packet_dir"),
        "reader_state_packet_id": selected.get("reader_state_packet_id")
        or reader.get("packet_id"),
        "reader_state_packet_dir": selected.get("reader_state_packet_dir")
        or reader.get("packet_dir"),
        "prior_best_packet_id": selected.get("base_candidate_packet_id"),
        "prior_best_packet_dir": (subject.prior_best_packet or {}).get("packet_dir"),
        "strongest_rival_still_blocks": True,
        "source_packet_count": len(subject.source_chain),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "evidence_loop_review_subject_manifest_v1_controller",
    }


def _build_completed_cycle_map(subject: LoopReviewSubject) -> dict[str, object]:
    selected = subject.selected_candidate
    prior = subject.prior_best_packet or {}
    prior_candidate_id = str(prior.get("packet_id") or selected.get("base_candidate_packet_id") or "")
    cycle_a = _cycle(
        cycle_id="cycle_a_macro2_reader_state",
        label="macro-2 preservation and reader-state cycle",
        starting_candidate_packet_id=_macro2_starting_candidate_id(subject),
        strategy_packet_id=None,
        candidate_packet_id=prior_candidate_id,
        intervention_target=str(prior.get("target_scope") or "reader_state_informed_macro_2"),
        proof_packet=subject.prior_proof_packet,
        reader_state_packet=subject.prior_reader_state_packet,
        synthesis_packet_id=_synthesis_after_reader_state(subject, subject.prior_reader_state_packet),
        causal_status=str((subject.prior_proof_packet or {}).get("proof_causal_status") or "useful_but_insufficient"),
        reader_state_status="partial",
        strongest_rival_status="still_blocks",
    )
    cycle_b = _cycle(
        cycle_id="cycle_b_object_event_reader_state",
        label="object-event pressure and reader-state cycle",
        starting_candidate_packet_id=str(selected.get("base_candidate_packet_id") or ""),
        strategy_packet_id=(subject.strategy_packet or {}).get("packet_id"),
        candidate_packet_id=str(selected.get("packet_id") or ""),
        intervention_target=str(selected.get("target_scope") or selected.get("target_movement") or ""),
        proof_packet=subject.proof_packet,
        reader_state_packet=subject.reader_state_packet,
        synthesis_packet_id=subject.synthesis_packet_id,
        causal_status=str(selected.get("proof_causal_status") or "useful_but_insufficient"),
        reader_state_status=str(selected.get("reader_state_reread_transformation_strength") or "partial"),
        strongest_rival_status="still_blocks",
    )
    return {
        "cycles": [cycle_a, cycle_b],
        "cycle_count": 2,
        "current_best_candidate_packet_id": selected.get("packet_id"),
        "evidence_loop_complete_enough_for_review": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "completed_cycle_map_v1_controller",
    }


def _build_current_best_candidate_review(subject: LoopReviewSubject) -> dict[str, object]:
    selected = subject.selected_candidate
    reader = subject.payloads["reader_state_evidence_adjudication"]
    return {
        "selected_best_candidate": selected,
        "selected_best_candidate_packet_id": selected.get("packet_id"),
        "proof_linked": bool(selected.get("proof_packet_id")),
        "reader_state_evaluated": selected.get("reader_state_evaluated") is True,
        "evidence_status": (
            "useful_but_insufficient_with_partial_internal_reader_state_support"
        ),
        "what_improved": [
            "object-event pressure is more coherent",
            "table/dust/spoon/saucer/ring causal field strengthened",
            "opening field becomes more necessary after reread",
            "macro-2 base gains were preserved",
            "some strongest-rival gap narrowed internally",
        ],
        "what_remains_unresolved": [
            "reader-state gain remains partial",
            "strongest rival still blocks",
            "first-read vividness remains weaker than rival",
            "lived object-event pressure remains weaker than rival",
            "proof/no-outside-answer carry remains partial or unresolved",
            "final return echo remains partial",
            "hostile scaffold or overexplanation risk remains active",
        ],
        "why_not_final": [
            "finalization_eligible is false",
            "internal reader evidence is not human validation",
            "strongest-rival comparison has not passed",
            "internal operator approval is absent",
        ],
        "why_not_discarded": [
            "linked executed ablation reports useful-but-insufficient support",
            "reader-state evaluation reports partial transformation",
            "candidate preserves macro-2 base gains",
            "no evidence contradicts the ablation/proof support enough to demote it",
        ],
        "why_immediate_generation_not_authorized": [
            "latest synthesis asked for loop-level review before a new candidate",
            "residual blockers need prioritization before another creative pass",
            "loop automation and packet reporting cleanup remain incomplete",
        ],
        "reader_state_summary": {
            "object_event_pressure_gain_status": reader.get(
                "object_event_pressure_gain_status"
            ),
            "reread_transformation_status": reader.get("reread_transformation_status"),
            "strongest_rival_status": reader.get("strongest_rival_status"),
            "hostile_risk_status": reader.get("hostile_risk_status"),
        },
        "candidate_generated": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "current_best_candidate_review_v1_controller",
    }


def _build_evidence_quality_review(subject: LoopReviewSubject) -> dict[str, object]:
    selected = subject.selected_candidate
    synthesis_counts = _as_dict(
        subject.payloads["autonomous_evidence_synthesis_packet"].get("counts")
    )
    nonblocking = _nonblocking_integrity_quirks(subject, synthesis_counts)
    return {
        "current_best_candidate_packet_id": selected.get("packet_id"),
        "evidence_quality": {
            "candidate_model_backed": bool(selected.get("model_backed")),
            "candidate_fixture_only": bool(selected.get("fixture_only")),
            "proof_model_backed": bool(selected.get("proof_model_backed")),
            "proof_fixture_only": bool(selected.get("proof_fixture_only")),
            "countable_ablation_evidence_exists": int(
                selected.get("proof_countable_evidence_variant_count") or 0
            )
            > 0,
            "reader_state_evaluation_exists": selected.get("reader_state_evaluated")
            is True,
            "reader_state_fixture_only": bool(selected.get("reader_state_fixture_only")),
            "reader_state_model_calls": int(selected.get("reader_state_model_calls") or 0),
            "reader_state_is_internal_model_evidence_not_human_data": True,
            "strongest_rival_comparison_exists": True,
            "strongest_rival_still_blocks": True,
            "finalization_remains_false": True,
        },
        "nonblocking_integrity_findings": nonblocking,
        "nonblocking_integrity_classification": "loop_automation_cleanup_not_creative_blocker",
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "evidence_quality_review_v1_controller",
    }


def _build_reader_state_progress_review(subject: LoopReviewSubject) -> dict[str, object]:
    reader = subject.payloads["reader_state_evidence_adjudication"]
    return {
        "reader_state_packet_id": reader.get("packet_id"),
        "progress_classification": {
            "object_event_pressure": reader.get("object_event_pressure_gain_status"),
            "reread_transformation": reader.get("reread_transformation_status"),
            "opening_return_transformation": reader.get(
                "opening_return_transformation_status"
            ),
            "local_object_field": reader.get("local_field_causal_necessity"),
            "proof_no_answer_carry": reader.get(
                "proof_no_outside_answer_carry_status"
            ),
            "hostile_scaffold_or_thesis_risk": reader.get("hostile_risk_status"),
            "strongest_rival": reader.get("strongest_rival_status"),
        },
        "table_dust_spoon_saucer_ring_causal_field_strengthened": (
            reader.get("local_field_causal_necessity") == "increased"
            or "ring" in reader.get("motifs_that_became_causal_after_reread", [])
        ),
        "reread_transformation_decisive": False,
        "internal_reader_evidence_only": True,
        "not_human_data": True,
        "candidate_generated": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "reader_state_progress_review_v1_controller",
    }


def _build_strongest_rival_status_review(subject: LoopReviewSubject) -> dict[str, object]:
    reader = subject.payloads["reader_state_evidence_adjudication"]
    return {
        "strongest_rival_still_blocks": True,
        "candidate_narrowed_some_gap": bool(reader.get("macro_candidate_narrowed_rival_gap")),
        "rival_still_wins_on": [
            "first-read vividness",
            "lived object-event pressure",
            "tactile inevitability",
        ],
        "first_read_vividness_status": reader.get("first_read_vividness_status"),
        "lived_object_causality_status": reader.get("lived_object_causality_status"),
        "no_rival_defeat_claim": True,
        "no_finality_claim": True,
        "strongest_rival_comparison_passed": False,
        "candidate_generated": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "strongest_rival_status_review_v1_controller",
    }


def _build_residual_blocker_taxonomy(subject: LoopReviewSubject) -> dict[str, object]:
    expected = [
        ("strongest_rival_still_winning", "creative_blocker"),
        ("reader_state_gain_still_partial", "evidence_blocker"),
        ("first_read_vividness_gap_still_active", "creative_blocker"),
        ("lived_object_event_pressure_still_weaker_than_rival", "creative_blocker"),
        ("proof_no_outside_answer_carry_still_partial", "creative_blocker"),
        ("final_return_echo_still_partial", "creative_blocker"),
        ("hostile_scaffold_or_overexplanation_risk", "evidence_blocker"),
        ("human_validation_absent", "operator_blocker"),
        ("finalization_absent", "operator_blocker"),
        ("loop_automation_not_ready", "automation_blocker"),
        ("artifact_count_or_packet_summary_cleanup_needed", "integrity_blocker"),
    ]
    source_ids = {
        str(blocker.get("blocker_id"))
        for blocker in subject.payloads["residual_blocker_map"].get("residual_blockers", [])
        if isinstance(blocker, dict) and blocker.get("blocker_id")
    }
    blockers = [
        {
            "rank": index,
            "blocker_id": blocker_id,
            "blocker_class": blocker_class,
            "status": "active",
            "source_synthesis_mentions_blocker": blocker_id in source_ids,
            "should_authorize_immediate_generation": False,
        }
        for index, (blocker_id, blocker_class) in enumerate(expected, start=1)
    ]
    return {
        "ranked_blockers": blockers,
        "active_blocker_ids": [blocker["blocker_id"] for blocker in blockers],
        "creative_blockers": [
            blocker["blocker_id"]
            for blocker in blockers
            if blocker["blocker_class"] == "creative_blocker"
        ],
        "evidence_blockers": [
            blocker["blocker_id"]
            for blocker in blockers
            if blocker["blocker_class"] == "evidence_blocker"
        ],
        "integrity_blockers": [
            blocker["blocker_id"]
            for blocker in blockers
            if blocker["blocker_class"] == "integrity_blocker"
        ],
        "operator_blockers": [
            blocker["blocker_id"]
            for blocker in blockers
            if blocker["blocker_class"] == "operator_blocker"
        ],
        "automation_blockers": [
            blocker["blocker_id"]
            for blocker in blockers
            if blocker["blocker_class"] == "automation_blocker"
        ],
        "candidate_generated": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "residual_blocker_taxonomy_v1_controller",
    }


def _build_drift_risk_report(subject: LoopReviewSubject) -> dict[str, object]:
    proof_packet_id = str(subject.selected_candidate.get("proof_packet_id") or "")
    reader_state_packet_id = str(
        subject.selected_candidate.get("reader_state_packet_id")
        or subject.payloads["reader_state_evidence_adjudication"].get("packet_id")
        or ""
    )
    freshness_report = detect_stale_recommendations(
        selected_candidate=subject.selected_candidate,
        synthesis_packet=subject.payloads["autonomous_evidence_synthesis_packet"],
        source_chain=subject.source_chain,
        proof_packet=subject.proof_packet,
        reader_state_packet=subject.reader_state_packet,
        strategy_packet=subject.strategy_packet,
    )
    proof_guard = build_proof_before_next_generation_guard(
        selected_candidate=subject.selected_candidate,
        proof_packet=subject.proof_packet,
        reader_state_packet=subject.reader_state_packet,
        latest_loop_review_requires_cleanup_first=True,
        prior_generated_candidate_synthesized=True,
        stale_recommendation_active=bool(
            freshness_report["stale_recommendation_detected"]
        ),
    )
    reader_state_guard = build_reader_state_before_synthesis_guard(
        selected_candidate=subject.selected_candidate,
        available_reader_state_packet=subject.reader_state_packet,
        consumed_reader_state_packet_id=reader_state_packet_id,
    )
    target_guard = build_repeated_target_drift_guard(
        current_target_class=str(subject.selected_candidate.get("target_scope") or ""),
        previous_target_class=str((subject.prior_best_packet or {}).get("target_scope") or ""),
        evidence_shifted_to_target_class="loop_integrity_cleanup_before_generation",
        loop_integrity_cleanup_required=True,
    )
    return {
        "immediate_new_generation_authorized": False,
        "immediate_new_generation_risk": (
            "high: another candidate would continue by inertia before residual "
            "blockers and loop-integrity issues are adjudicated"
        ),
        "why_immediate_new_generation_would_be_drift_or_high_risk": [
            "latest synthesis explicitly requested loop-level review",
            "reader-state gain remains partial",
            "strongest rival still blocks",
            "creative blockers are not yet ranked into a new authorized target",
            "automation/reporting cleanup remains unresolved",
        ],
        "why_immediate_ablation_would_be_redundant": (
            f"{proof_packet_id or 'the linked proof packet'} already ablated the "
            "current object-event candidate; no new candidate exists to test"
        ),
        "why_immediate_reader_state_eval_would_be_redundant": (
            f"{reader_state_packet_id or 'the linked reader-state packet'} already "
            "evaluated the current object-event candidate"
        ),
        "why_loop_level_review_is_right_next_action": (
            "it consolidates the completed candidate/proof/reader-state/synthesis "
            "loop before authorizing another creative move"
        ),
        "what_would_justify_another_creative_cycle": [
            "operator selects one residual target",
            "protected effects are carried forward",
            "proof and reader-state prerequisites are explicit",
            "no repeated-target drift guard is active",
        ],
        "what_would_justify_loop_controller_implementation": [
            "packet count/reporting quirks are fixed",
            "command output shape is stable",
            "evidence freshness checks exist",
            "manual approval gates are explicit",
        ],
        "what_would_justify_stopping_candidate_generation": [
            "strongest rival remains superior after targeted cycles",
            "new cycles repeat stale targets",
            "reader-state gains plateau or regress",
            "operator decides preservation/review is preferable",
        ],
        "freshness_report": freshness_report,
        "proof_before_next_generation_guard": proof_guard,
        "reader_state_before_synthesis_guard": reader_state_guard,
        "repeated_target_drift_guard": target_guard,
        "stale_recommendation_detected": freshness_report[
            "stale_recommendation_detected"
        ],
        "next_generation_authorized": proof_guard["next_generation_authorized"],
        "next_generation_blockers": proof_guard["next_generation_blockers"],
        "loop_integrity_cleanup_required": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "drift_risk_report_v1_controller",
    }


def _build_loop_integrity_report(
    subject: LoopReviewSubject,
    drift_risk: dict[str, object],
) -> dict[str, object]:
    freshness = _as_dict(drift_risk.get("freshness_report"))
    proof_guard = _as_dict(drift_risk.get("proof_before_next_generation_guard"))
    target_guard = _as_dict(drift_risk.get("repeated_target_drift_guard"))
    nonblocking_quirks = _nonblocking_integrity_quirks(
        subject,
        _as_dict(subject.payloads["autonomous_evidence_synthesis_packet"].get("counts")),
    )
    checks = {
        "candidate_generation_command_exists": True,
        "ablation_command_exists": True,
        "reader_state_eval_command_exists": True,
        "synthesis_command_exists": True,
        "strategy_command_exists": True,
        "loop_review_command_exists": True,
        "all_reviewed_commands_are_fail_closed": True,
        "finalization_still_refuses": True,
        "live_model_paths_are_guarded": True,
        "evidence_pairing_works_across_candidate_proof_reader_state": True,
        "packet_self_count_reporting_quirks_remain": bool(nonblocking_quirks),
        "stale_recommendation_detected": bool(
            freshness.get("stale_recommendation_detected")
        ),
        "proof_before_next_generation_guard_exists": True,
        "reader_state_before_synthesis_guard_exists": True,
        "repeated_target_drift_guard_exists": True,
        "repeated_target_drift_detected": bool(
            target_guard.get("repeated_target_drift_detected")
        ),
        "command_output_shape_aliases_present": True,
        "stale_command_output_shape_issues_remain": False,
        "manual_operator_still_required": True,
    }
    cleanup_blockers = [
        "loop review must be inspected before any next creative command",
        "artifact/command output consistency must remain stable in fresh command output",
    ]
    if nonblocking_quirks:
        cleanup_blockers.append("legacy packet count quirks remain in older source packets")
    automation_blockers = [
        "autonomous loop controller is not implemented",
        "manual operator approval remains required",
        "freshness and repeated-target guards are diagnostic only",
    ]
    return {
        "checks": checks,
        "conclusions": [
            "loop_controller_not_ready_for_full_autonomy",
            "loop_scaffold_ready_for_manual_supervised_repetition",
            "loop_integrity_cleanup_required_before_automation",
        ],
        "ready_for_full_autonomous_loop_controller": False,
        "ready_for_full_autonomous_loop": False,
        "ready_for_supervised_next_cycle": False,
        "ready_for_manual_supervised_repetition": False,
        "loop_integrity_cleanup_required": True,
        "next_generation_authorized": False,
        "next_generation_blockers": proof_guard.get("next_generation_blockers", []),
        "cleanup_blockers": cleanup_blockers,
        "automation_blockers": automation_blockers,
        "stale_recommendation_report": freshness,
        "proof_before_next_generation_guard": proof_guard,
        "repeated_target_drift_guard": target_guard,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "loop_integrity_report_v1_controller",
    }


def _build_next_action_decision(
    subject: LoopReviewSubject,
    drift_risk: dict[str, object],
    loop_integrity: dict[str, object],
) -> dict[str, object]:
    proof_guard = _as_dict(drift_risk.get("proof_before_next_generation_guard"))
    return {
        "recommended_next_action": "prepare_loop_integrity_cleanup_before_more_generation",
        "allowed_next_action_family": "loop_integrity_cleanup_or_supervised_operator_review",
        "immediate_creative_generation_authorized": False,
        "immediate_ablation_authorized": False,
        "immediate_reader_state_eval_authorized": False,
        "next_generation_authorized": False,
        "next_generation_blockers": proof_guard.get("next_generation_blockers", []),
        "cleanup_blockers": loop_integrity.get("cleanup_blockers", []),
        "automation_blockers": loop_integrity.get("automation_blockers", []),
        "loop_integrity_cleanup_required": True,
        "stale_recommendation_detected": _as_dict(
            drift_risk.get("freshness_report")
        ).get("stale_recommendation_detected", False),
        "basis": [
            "current best candidate remains packet "
            f"{subject.selected_candidate.get('packet_id')}",
            "current loop has candidate, proof, reader-state evaluation, and synthesis",
            "reader-state gain is partial, not decisive",
            "strongest rival still blocks",
            "loop controller readiness is false",
            str(drift_risk["why_loop_level_review_is_right_next_action"]),
            ", ".join(str(value) for value in loop_integrity["conclusions"]),
        ],
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_action_decision_v1_controller",
    }


def _build_loop_controller_readiness_report(
    subject: LoopReviewSubject,
    drift_risk: dict[str, object],
    loop_integrity: dict[str, object],
) -> dict[str, object]:
    return {
        "ready_for_full_autonomous_loop_controller": False,
        "ready_for_autonomous_loop_controller": False,
        "ready_for_supervised_next_cycle": False,
        "loop_integrity_cleanup_required": True,
        "next_generation_authorized": False,
        "next_generation_blockers": _as_dict(
            drift_risk.get("proof_before_next_generation_guard")
        ).get("next_generation_blockers", []),
        "cleanup_blockers": loop_integrity.get("cleanup_blockers", []),
        "automation_blockers": loop_integrity.get("automation_blockers", []),
        "required_before_loop_controller": [
            "artifact-count/self-count cleanup",
            "stable command output shape",
            "loop review gate",
            "evidence freshness/current-best checks",
            "stale recommendation detection",
            "max-cycle limits",
            "no repeated-target drift guard",
            "proof-before-next-generation guard",
            "reader-state-before-synthesis guard",
            "finalization never auto-passes",
        ],
        "recommended_loop_controller_scope_if_later": [
            "supervised/manual approval only",
            "one cycle at a time",
            "no finalization authority",
            "hard stop on repeated failure or stale evidence",
        ],
        "manual_operator_required": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "loop_controller_readiness_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: LoopReviewSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    selected = subject.selected_candidate
    gate_results = [
        _gate_result("source_synthesis_consumed", True),
        _gate_result("current_best_candidate_identified", bool(selected.get("packet_id"))),
        _gate_result("proof_packet_linked", bool(selected.get("proof_packet_id"))),
        _gate_result(
            "reader_state_packet_linked",
            bool(
                selected.get("reader_state_packet_id")
                or subject.payloads["reader_state_evidence_adjudication"].get("packet_id")
            ),
        ),
        _gate_result("completed_cycles_mapped", payloads["completed_cycle_map"]["cycle_count"] >= 2),
        _gate_result(
            "residual_blockers_classified",
            bool(payloads["residual_blocker_taxonomy"]["ranked_blockers"]),
        ),
        _gate_result("drift_risk_assessed", True),
        _gate_result("loop_integrity_reviewed", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "autonomous_loop_controller_ready",
            False,
            ["loop controller readiness is explicitly false"],
            record=False,
        ),
        _gate_result(
            "next_candidate_authorized",
            False,
            ["loop review does not authorize immediate generation"],
            record=False,
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            ["strongest rival and partial reader-state blockers remain"],
            record=False,
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator review is still required"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["loop review packet is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "autonomous loop controller is not ready",
        "next candidate is not authorized",
        "strongest rival still blocks",
        "reader-state gain remains partial",
        "loop-integrity cleanup is required before generation",
        "internal operator approval is absent",
        "finalization remains ineligible",
    ]
    return {
        "passed": False,
        "eligible": False,
        "ready_for_full_autonomous_loop_controller": False,
        "ready_for_supervised_next_cycle": False,
        "loop_integrity_cleanup_required": True,
        "next_generation_authorized": False,
        "next_generation_blockers": payloads["next_action_decision"].get(
            "next_generation_blockers",
            [],
        ),
        "cleanup_blockers": payloads["next_action_decision"].get(
            "cleanup_blockers",
            [],
        ),
        "automation_blockers": payloads["next_action_decision"].get(
            "automation_blockers",
            [],
        ),
        "stale_recommendation_detected": payloads["next_action_decision"].get(
            "stale_recommendation_detected",
            False,
        ),
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "strongest_rival_still_blocks": True,
        "candidate_generated": False,
        "model_calls": 0,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Evidence loop review accepted the completed loop and remains fail-closed; "
            "full loop automation and next-candidate generation are not authorized."
        ),
        "worker": "evidence_loop_review_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: LoopReviewSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="evidence_loop_review_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "evidence_loop_review_packet"],
        "counts": {
            **artifact_counts,
            "loop_review_artifacts": artifact_counts["produced_artifacts"],
            "required_loop_review_artifacts": artifact_counts["required_artifacts"],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "current_best_candidate_packet_id": subject.selected_candidate.get("packet_id"),
        "proof_packet_id": subject.selected_candidate.get("proof_packet_id"),
        "reader_state_packet_id": subject.selected_candidate.get("reader_state_packet_id")
        or subject.payloads["reader_state_evidence_adjudication"].get("packet_id"),
        "completed_cycle_count": payloads["completed_cycle_map"]["cycle_count"],
        "residual_blocker_count": len(
            payloads["residual_blocker_taxonomy"]["ranked_blockers"]
        ),
        "strongest_rival_still_blocks": True,
        "drift_risk_conclusion": payloads["drift_risk_report"][
            "immediate_new_generation_risk"
        ],
        "loop_controller_ready": payloads["loop_controller_readiness_report"][
            "ready_for_autonomous_loop_controller"
        ],
        "ready_for_full_autonomous_loop_controller": payloads[
            "loop_controller_readiness_report"
        ]["ready_for_full_autonomous_loop_controller"],
        "ready_for_supervised_next_cycle": payloads["loop_controller_readiness_report"][
            "ready_for_supervised_next_cycle"
        ],
        "loop_integrity_cleanup_required": payloads["loop_integrity_report"][
            "loop_integrity_cleanup_required"
        ],
        "next_generation_authorized": payloads["next_action_decision"][
            "next_generation_authorized"
        ],
        "next_generation_blockers": payloads["next_action_decision"][
            "next_generation_blockers"
        ],
        "cleanup_blockers": payloads["next_action_decision"]["cleanup_blockers"],
        "automation_blockers": payloads["next_action_decision"]["automation_blockers"],
        "stale_recommendation_detected": payloads["next_action_decision"][
            "stale_recommendation_detected"
        ],
        "freshness_report": payloads["drift_risk_report"]["freshness_report"],
        "proof_before_next_generation_guard": payloads["drift_risk_report"][
            "proof_before_next_generation_guard"
        ],
        "reader_state_before_synthesis_guard": payloads["drift_risk_report"][
            "reader_state_before_synthesis_guard"
        ],
        "repeated_target_drift_guard": payloads["drift_risk_report"][
            "repeated_target_drift_guard"
        ],
        "next_recommended_action": payloads["next_action_decision"][
            "recommended_next_action"
        ],
        "candidate_generated": False,
        "model_calls": 0,
        "gate_report": payloads["evidence_loop_review_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "evidence_loop_review_packet_v1_controller",
    }


def _cycle(
    *,
    cycle_id: str,
    label: str,
    starting_candidate_packet_id: str | None,
    strategy_packet_id: object,
    candidate_packet_id: str,
    intervention_target: str,
    proof_packet: dict[str, Any] | None,
    reader_state_packet: dict[str, Any] | None,
    synthesis_packet_id: str | None,
    causal_status: str,
    reader_state_status: str,
    strongest_rival_status: str,
) -> dict[str, object]:
    return {
        "cycle_id": cycle_id,
        "label": label,
        "starting_candidate_packet_id": starting_candidate_packet_id,
        "strategy_packet_id": strategy_packet_id,
        "candidate_packet_id": candidate_packet_id,
        "intervention_target": intervention_target,
        "proof_packet_id": (proof_packet or {}).get("packet_id"),
        "proof_packet_dir": (proof_packet or {}).get("packet_dir"),
        "reader_state_packet_id": (reader_state_packet or {}).get("packet_id"),
        "reader_state_packet_dir": (reader_state_packet or {}).get("packet_dir"),
        "synthesis_packet_id": synthesis_packet_id,
        "causal_status": causal_status,
        "reader_state_status": reader_state_status,
        "strongest_rival_status": strongest_rival_status,
        "finalization_status": "ineligible",
        "finalization_eligible": False,
    }


def _source_chain(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    packet = payloads["autonomous_evidence_synthesis_packet"]
    source_chain = packet.get("source_chain")
    if isinstance(source_chain, list):
        return [source for source in source_chain if isinstance(source, dict)]
    manifest_sources = payloads.get("autonomous_evidence_synthesis_subject_manifest", {}).get(
        "source_packets"
    )
    if isinstance(manifest_sources, list):
        return [source for source in manifest_sources if isinstance(source, dict)]
    return []


def _find_source(
    sources: list[dict[str, Any]],
    packet_kind: str,
    packet_id: str,
) -> dict[str, Any] | None:
    if not packet_id:
        return None
    for source in sources:
        if source.get("packet_kind") == packet_kind and source.get("packet_id") == packet_id:
            return source
    return None


def _find_source_by_revision(
    sources: list[dict[str, Any]],
    packet_kind: str,
    source_revision_packet_id: str,
) -> dict[str, Any] | None:
    if not source_revision_packet_id:
        return None
    matches = [
        source
        for source in sources
        if source.get("packet_kind") == packet_kind
        and source.get("source_revision_packet_id") == source_revision_packet_id
    ]
    return matches[-1] if matches else None


def _find_reader_state_for_candidate(
    sources: list[dict[str, Any]],
    candidate_packet_id: str,
) -> dict[str, Any] | None:
    if not candidate_packet_id:
        return None
    matches = [
        source
        for source in sources
        if source.get("packet_kind") == "internal_reader_state_evaluation"
        and source.get("selected_candidate_packet_id") == candidate_packet_id
    ]
    return matches[-1] if matches else None


def _resolve_strategy_packet(
    config: AbiConfig,
    run_id: str,
    selected: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    selected_dir = selected.get("packet_dir")
    if isinstance(selected_dir, str):
        manifest_path = Path(selected_dir) / "macro_recomposition_subject_manifest.json"
        if manifest_path.exists():
            envelope = read_json_file(manifest_path)
            payload = envelope.get("payload") if isinstance(envelope, dict) else None
            if isinstance(payload, dict):
                strategy_id = str(payload.get("source_strategy_packet_id") or "")
                strategy = _find_source(sources, "next_target_strategy", strategy_id)
                if strategy is not None:
                    return strategy
                strategy_dir = config.run_dir(run_id) / "next_target_strategy" / strategy_id
                if strategy_id and strategy_dir.exists():
                    return {
                        "packet_kind": "next_target_strategy",
                        "packet_id": strategy_id,
                        "packet_dir": str(strategy_dir),
                    }
    strategy_base = config.run_dir(run_id) / "next_target_strategy"
    if strategy_base.exists():
        packet_dirs = sorted(
            [child for child in strategy_base.glob("packet_*") if child.is_dir()],
            key=lambda path: path.name,
        )
        if packet_dirs:
            latest = packet_dirs[-1]
            return {
                "packet_kind": "next_target_strategy",
                "packet_id": latest.name,
                "packet_dir": str(latest),
            }
    return None


def _synthesis_after_reader_state(
    subject: LoopReviewSubject,
    reader_state_packet: dict[str, Any] | None,
) -> str | None:
    if reader_state_packet is None:
        return None
    source_id = str(reader_state_packet.get("source_synthesis_packet_id") or "")
    synthesis_ids = [
        str(source.get("packet_id"))
        for source in subject.source_chain
        if source.get("packet_kind") == "autonomous_evidence_synthesis"
    ]
    if not synthesis_ids:
        return source_id or None
    try:
        source_index = synthesis_ids.index(source_id)
    except ValueError:
        return synthesis_ids[-1]
    if source_index + 1 < len(synthesis_ids):
        return synthesis_ids[source_index + 1]
    return source_id or synthesis_ids[-1]


def _macro2_starting_candidate_id(subject: LoopReviewSubject) -> str | None:
    prior = subject.prior_best_packet or {}
    base_id = str(prior.get("base_candidate_packet_id") or "")
    if base_id:
        return base_id
    macro_candidates = [
        source
        for source in subject.source_chain
        if source.get("packet_kind") == "bounded_macro_recomposition"
        and source.get("target_scope") != "first_read_object_event_pressure_gap"
    ]
    return str(macro_candidates[-2].get("packet_id")) if len(macro_candidates) >= 2 else None


def _nonblocking_integrity_quirks(
    subject: LoopReviewSubject,
    synthesis_counts: dict[str, Any],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    required = int(synthesis_counts.get("required_synthesis_artifacts") or 0)
    actual = int(synthesis_counts.get("synthesis_artifacts") or 0)
    if _count_is_inconsistent_after_packet_policy(required=required, actual=actual):
        findings.append(
            {
                "finding_id": "synthesis_artifact_count_self_count_mismatch",
                "status": "nonblocking_loop_automation_cleanup",
                "details": f"required_synthesis_artifacts={required}; synthesis_artifacts={actual}",
            }
        )
    for source in subject.source_chain:
        if source.get("packet_kind") != "executed_ablation":
            continue
        counts = _as_dict(source.get("counts"))
        required_ablation = int(counts.get("required_executed_ablation_artifacts") or 0)
        actual_ablation = int(counts.get("executed_ablation_artifacts") or 0)
        if _count_is_inconsistent_after_packet_policy(
            required=required_ablation,
            actual=actual_ablation,
        ):
            findings.append(
                {
                    "finding_id": "executed_ablation_packet_self_count_mismatch",
                    "packet_id": source.get("packet_id"),
                    "status": "nonblocking_loop_automation_cleanup",
                    "details": (
                        f"required_executed_ablation_artifacts={required_ablation}; "
                        f"executed_ablation_artifacts={actual_ablation}"
                    ),
                }
            )
    findings.append(
        {
            "finding_id": "cli_output_field_consistency_review_needed",
            "status": "nonblocking_loop_automation_cleanup",
            "details": "Loop automation should stabilize command output fields before full autonomy.",
        }
    )
    findings.append(
        {
            "finding_id": "stale_packet_family_gate_naming_review_needed",
            "status": "nonblocking_loop_automation_cleanup",
            "details": "Some gates retain packet-family names from earlier scaffolds.",
        }
    )
    return findings


def _count_is_inconsistent_after_packet_policy(*, required: int, actual: int) -> bool:
    if not required or not actual or required == actual:
        return False
    return actual + 1 != required


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    values = [str(path), str(path.resolve())]
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        values,
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


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
        "blocking_defects": list(blockers or []),
        "recorded_for_finalization": record,
    }


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return config.root / value


def _refusal(*, synthesis_packet: Path, message: str) -> EvidenceLoopReviewResult:
    return EvidenceLoopReviewResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "synthesis_packet": str(synthesis_packet),
            "artifact_ids": {},
            "counts": {
                "model_calls": 0,
                "candidate_artifacts_created": 0,
            },
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
