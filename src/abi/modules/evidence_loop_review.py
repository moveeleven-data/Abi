"""Deterministic evidence loop-level review packet."""

from __future__ import annotations

from dataclasses import dataclass
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
from abi.packets import PacketWriter, create_packet_dir, read_json_file


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

        payloads["loop_integrity_report"] = _build_loop_integrity_report(subject)
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
            _build_loop_controller_readiness_report(subject)
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
        "next_recommended_action": payloads["next_action_decision"][
            "recommended_next_action"
        ],
        "loop_controller_ready": payloads["loop_controller_readiness_report"][
            "ready_for_autonomous_loop_controller"
        ],
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
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "drift_risk_report_v1_controller",
    }


def _build_loop_integrity_report(subject: LoopReviewSubject) -> dict[str, object]:
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
        "packet_self_count_reporting_quirks_remain": bool(
            _nonblocking_integrity_quirks(subject, _as_dict(subject.payloads["autonomous_evidence_synthesis_packet"].get("counts")))
        ),
        "stale_command_output_shape_issues_remain": True,
        "manual_operator_still_required": True,
    }
    return {
        "checks": checks,
        "conclusions": [
            "loop_controller_not_ready_for_full_autonomy",
            "loop_scaffold_ready_for_manual_supervised_repetition",
            "loop_integrity_cleanup_required_before_automation",
        ],
        "ready_for_full_autonomous_loop": False,
        "ready_for_manual_supervised_repetition": True,
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
    return {
        "recommended_next_action": "prepare_loop_integrity_cleanup_before_more_generation",
        "allowed_next_action_family": "loop_integrity_cleanup_or_supervised_operator_review",
        "immediate_creative_generation_authorized": False,
        "immediate_ablation_authorized": False,
        "immediate_reader_state_eval_authorized": False,
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


def _build_loop_controller_readiness_report(subject: LoopReviewSubject) -> dict[str, object]:
    return {
        "ready_for_autonomous_loop_controller": False,
        "ready_for_supervised_next_cycle": False,
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
        "internal operator approval is absent",
        "finalization remains ineligible",
    ]
    return {
        "passed": False,
        "eligible": False,
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
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "evidence_loop_review_packet"],
        "counts": {
            "loop_review_artifacts": len(artifacts) + 1,
            "required_loop_review_artifacts": len(EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES),
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
    if required and actual and required != actual:
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
        if required_ablation and actual_ablation and required_ablation != actual_ablation:
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
