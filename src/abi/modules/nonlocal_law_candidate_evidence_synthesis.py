"""Evidence synthesis for model-backed nonlocal law candidate reader-state packets."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_candidate_ablation import (
    ABLATION_CONTROL_IDS,
    CANDIDATE_REVIEW_RISKS,
)
from abi.modules.nonlocal_law_guided_work_order import NONLOCAL_LAW_TARGET_SCOPE
from abi.modules.post_local_residual_strategy_synthesis import (
    EXPECTED_CURRENT_BEST_PACKET_ID,
    EXPECTED_PROOF_PACKET_ID,
    EXPECTED_READER_STATE_PACKET_ID,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_LINEAGE_ID = (
    "nonlocal_law_candidate_evidence_synthesis_v1"
)
NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_CREATED_BY = (
    "nonlocal_law_candidate_evidence_synthesis_v1_controller"
)
NEXT_RECOMMENDED_ACTION = (
    "review_nonlocal_law_candidate_synthesis_before_current_best_decision"
)
CURRENT_BEST_RECOMMENDATION = (
    "recommend_promote_to_new_current_best_pending_loop_review"
)
CURRENT_BEST_DECISION = "do_not_finalize"
CANDIDATE_LAW_EFFECT = "supported_but_incomplete"
READER_STATE_SUPPORT = "supportive_mixed"
EXPECTED_READER_STATE_MODE = "model_backed_live"

NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES = (
    "source_reader_state_intake_summary",
    "evidence_chain_integrity_report",
    "candidate_law_effect_synthesis",
    "packet_0063_comparison_synthesis",
    "ablation_reader_state_alignment_report",
    "active_risk_synthesis_report",
    "strongest_rival_pressure_synthesis",
    "current_best_decision_recommendation",
    "future_repair_or_supersession_options",
    "synthesis_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_candidate_evidence_synthesis_packet",
)

REQUIRED_READER_STATE_ARTIFACT_TYPES = (
    "nonlocal_law_candidate_reader_state_evaluation_packet",
    "source_ablation_intake_summary",
    "ablation_control_reader_state_matrix",
    "candidate_review_risk_probe_report",
    "candidate_vs_packet_0063_reader_state_comparison",
    "strongest_rival_pressure_status_report",
    "synthesis_readiness_report",
)

REQUIRED_READER_STATE_RESULTS = (
    "first_read_pressure_result",
    "object_event_consequence_result",
    "explanation_timing_result",
    "reread_return_result",
    "non_imitation_result",
    "strongest_rival_pressure_result",
    "overall_reader_state_result",
)

ACTIVE_RISK_IDS = tuple(str(risk["risk_id"]) for risk in CANDIDATE_REVIEW_RISKS)


@dataclass(frozen=True)
class NonlocalLawCandidateEvidenceSynthesisResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawCandidateEvidenceSynthesisSubject:
    run_id: str
    reader_state_packet_dir: Path
    reader_state_packet_id: str
    reader_state_artifact_id: str | None
    reader_state_payloads: dict[str, dict[str, Any]]
    reader_state_artifact_ids: dict[str, str]
    parent_ids: tuple[str, ...]
    source_ablation_payloads: dict[str, dict[str, Any]]


def run_nonlocal_law_candidate_evidence_synthesis(
    config: AbiConfig,
    *,
    reader_state_packet: Path | str,
    operator_reviewed: bool = False,
) -> NonlocalLawCandidateEvidenceSynthesisResult:
    if not operator_reviewed:
        return _refusal(
            reader_state_packet=reader_state_packet,
            message=(
                "Nonlocal law candidate evidence synthesis refused; pass "
                "--operator-reviewed after reviewing the model-backed reader-state packet."
            ),
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, reader_state_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            reader_state_packet=resolved_packet,
            message=(
                "Nonlocal law candidate evidence synthesis refused; "
                f"reader-state packet directory not found: {resolved_packet}"
            ),
        )

    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject(subject)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    reader_state_packet=resolved_packet,
                    message=(
                        "Nonlocal law candidate evidence synthesis refused; "
                        f"run is not registered: {subject.run_id}"
                    ),
                )
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_ACTIVE_PHASE,
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            reader_state_packet=resolved_packet,
            message=f"Nonlocal law candidate evidence synthesis refused; {error}",
        )

    packet_dir = create_packet_dir(
        config.run_dir(subject.run_id) / "nonlocal_law_candidate_evidence_synthesis"
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_synthesis_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_candidate_evidence_synthesis_gate_report",
            passed=False,
            blocking_defects=payloads["synthesis_gate_report"]["unresolved_blockers"],
            lineage_id=NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_LINEAGE_ID,
        )
        return NonlocalLawCandidateEvidenceSynthesisResult(
            exit_code=0,
            payload=_result_payload(packet_dir, artifacts, payloads),
            artifacts=tuple(artifacts.values()),
            gate_record=gate_record,
        )


def _load_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    reader_state_packet_dir: Path,
) -> NonlocalLawCandidateEvidenceSynthesisSubject:
    envelopes: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    artifact_ids: dict[str, str] = {}
    parent_ids: list[str] = []
    for artifact_type in REQUIRED_READER_STATE_ARTIFACT_TYPES:
        path = reader_state_packet_dir / f"{artifact_type}.json"
        envelope = _read_envelope(path, artifact_type)
        envelopes[artifact_type] = envelope
        payloads[artifact_type] = envelope["payload"]
        artifact = _artifact_for_path(connection, path)
        if artifact is not None:
            artifact_ids[artifact_type] = artifact.id
            parent_ids.append(artifact.id)

    packet = payloads["nonlocal_law_candidate_reader_state_evaluation_packet"]
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("source reader-state packet missing run_id")
    packet_id = str(packet.get("packet_id") or reader_state_packet_dir.name)
    packet_artifact = _artifact_for_path(
        connection,
        reader_state_packet_dir
        / "nonlocal_law_candidate_reader_state_evaluation_packet.json",
    )
    source_ablation_dir = _source_ablation_dir(config, packet, run_id)
    source_ablation_payloads = _load_source_ablation_payloads(source_ablation_dir)
    return NonlocalLawCandidateEvidenceSynthesisSubject(
        run_id=run_id,
        reader_state_packet_dir=reader_state_packet_dir,
        reader_state_packet_id=packet_id,
        reader_state_artifact_id=packet_artifact.id if packet_artifact else None,
        reader_state_payloads=payloads,
        reader_state_artifact_ids=artifact_ids,
        parent_ids=tuple(parent_ids),
        source_ablation_payloads=source_ablation_payloads,
    )


def _validate_subject(subject: NonlocalLawCandidateEvidenceSynthesisSubject) -> None:
    packet = _packet(subject)
    _require_bool(packet, "accepted", True)
    _require_bool(packet, "model_backed", True)
    _require_equal(packet, "reader_state_evaluation_mode", EXPECTED_READER_STATE_MODE)
    _require_bool(packet, "provisional_reader_state_evaluation", False)
    _require_bool(packet, "usable_for_synthesis", True)
    _require_bool(packet, "reader_state_evaluation_executed", True)
    _require_bool(packet, "ready_for_synthesis", True)
    _require_bool(packet, "synthesis_authorized", False)
    _require_bool(packet, "current_best_updated", False)
    _require_bool(packet, "no_final_claim", True)
    _require_bool(packet, "no_phase_shift_claim", True)
    _require_bool(packet, "strongest_rival_defeated_claimed", False)
    _require_equal(packet, "base_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID)
    _require_equal(
        packet,
        "current_best_candidate_packet_id",
        EXPECTED_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "proof_packet_id", EXPECTED_PROOF_PACKET_ID)
    _require_equal(packet, "prior_reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID)
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(packet, "target_scope", NONLOCAL_LAW_TARGET_SCOPE)
    if not str(packet.get("candidate_text_sha256") or "").strip():
        raise ValueError("candidate_text_sha256 missing")
    for key in REQUIRED_READER_STATE_RESULTS:
        if not str(packet.get(key) or "").strip():
            raise ValueError(f"{key} missing")
    controls = _control_ids(subject)
    missing_controls = [control for control in ABLATION_CONTROL_IDS if control not in controls]
    if missing_controls:
        raise ValueError("ablation controls missing: " + ", ".join(missing_controls))
    _validate_source_ablation_alignment(subject)
    if _payload_has_forbidden_claim(subject.reader_state_payloads):
        raise ValueError(
            "source reader-state packet carries finality, phase-shift, "
            "superiority, current-best supersession, or rival-defeat claim"
        )


def _validate_source_ablation_alignment(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> None:
    packet = _packet(subject)
    ablation = subject.source_ablation_payloads["nonlocal_law_candidate_ablation_packet"]
    _require_bool(ablation, "accepted", True)
    _require_bool(ablation, "ablation_executed", True)
    _require_equal(
        packet,
        "source_ablation_packet_id",
        str(ablation.get("packet_id") or ""),
    )
    for key in (
        "source_candidate_packet_id",
        "source_authorization_packet_id",
        "source_work_order_packet_id",
        "source_strategy_packet_id",
        "source_diagnostic_packet_id",
        "base_candidate_packet_id",
        "current_best_candidate_packet_id",
        "proof_packet_id",
        "reader_state_packet_id",
        "law_id",
        "candidate_text_sha256",
    ):
        ablation_key = (
            "reader_state_packet_id"
            if key == "prior_reader_state_packet_id"
            else key
        )
        if key == "current_best_candidate_packet_id":
            continue
        packet_value = packet.get(
            "prior_reader_state_packet_id" if key == "reader_state_packet_id" else key
        )
        if packet_value != ablation.get(ablation_key):
            raise ValueError(f"source chain mismatch for {key}")


def _write_synthesis_artifacts(
    *,
    writer: PacketWriter,
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_reader_state_intake_summary"] = _build_intake(subject, packet_dir)
    artifacts["source_reader_state_intake_summary"] = writer.write_artifact(
        "source_reader_state_intake_summary",
        payloads["source_reader_state_intake_summary"],
        parent_ids=list(subject.parent_ids),
    )

    payloads["evidence_chain_integrity_report"] = _build_integrity_report(subject)
    artifacts["evidence_chain_integrity_report"] = writer.write_artifact(
        "evidence_chain_integrity_report",
        payloads["evidence_chain_integrity_report"],
        parent_ids=[artifacts["source_reader_state_intake_summary"].id],
    )

    payloads["candidate_law_effect_synthesis"] = _build_law_effect(subject)
    artifacts["candidate_law_effect_synthesis"] = writer.write_artifact(
        "candidate_law_effect_synthesis",
        payloads["candidate_law_effect_synthesis"],
        parent_ids=[artifacts["evidence_chain_integrity_report"].id],
    )

    payloads["packet_0063_comparison_synthesis"] = _build_packet_0063_comparison(subject)
    artifacts["packet_0063_comparison_synthesis"] = writer.write_artifact(
        "packet_0063_comparison_synthesis",
        payloads["packet_0063_comparison_synthesis"],
        parent_ids=[artifacts["candidate_law_effect_synthesis"].id],
    )

    payloads["ablation_reader_state_alignment_report"] = _build_alignment_report(subject)
    artifacts["ablation_reader_state_alignment_report"] = writer.write_artifact(
        "ablation_reader_state_alignment_report",
        payloads["ablation_reader_state_alignment_report"],
        parent_ids=[artifacts["packet_0063_comparison_synthesis"].id],
    )

    payloads["active_risk_synthesis_report"] = _build_risk_synthesis(subject)
    artifacts["active_risk_synthesis_report"] = writer.write_artifact(
        "active_risk_synthesis_report",
        payloads["active_risk_synthesis_report"],
        parent_ids=[artifacts["ablation_reader_state_alignment_report"].id],
    )

    payloads["strongest_rival_pressure_synthesis"] = _build_rival_synthesis(subject)
    artifacts["strongest_rival_pressure_synthesis"] = writer.write_artifact(
        "strongest_rival_pressure_synthesis",
        payloads["strongest_rival_pressure_synthesis"],
        parent_ids=[artifacts["active_risk_synthesis_report"].id],
    )

    payloads["current_best_decision_recommendation"] = (
        _build_current_best_recommendation(subject)
    )
    artifacts["current_best_decision_recommendation"] = writer.write_artifact(
        "current_best_decision_recommendation",
        payloads["current_best_decision_recommendation"],
        parent_ids=[artifacts["strongest_rival_pressure_synthesis"].id],
    )

    payloads["future_repair_or_supersession_options"] = _build_future_options(subject)
    artifacts["future_repair_or_supersession_options"] = writer.write_artifact(
        "future_repair_or_supersession_options",
        payloads["future_repair_or_supersession_options"],
        parent_ids=[artifacts["current_best_decision_recommendation"].id],
    )

    payloads["synthesis_gate_report"] = _build_gate_report(subject)
    artifacts["synthesis_gate_report"] = writer.write_artifact(
        "synthesis_gate_report",
        payloads["synthesis_gate_report"],
        parent_ids=[artifacts["future_repair_or_supersession_options"].id],
    )

    payloads["project_health_scope_guard_report"] = _build_health_report(subject)
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[artifacts["synthesis_gate_report"].id],
    )

    payloads["nonlocal_law_candidate_evidence_synthesis_packet"] = _build_packet_summary(
        subject=subject,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    artifacts["nonlocal_law_candidate_evidence_synthesis_packet"] = writer.write_artifact(
        "nonlocal_law_candidate_evidence_synthesis_packet",
        payloads["nonlocal_law_candidate_evidence_synthesis_packet"],
        parent_ids=[
            artifact.id
            for artifact_type, artifact in artifacts.items()
            if artifact_type != "nonlocal_law_candidate_evidence_synthesis_packet"
        ],
    )
    return payloads, artifacts


def _build_intake(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_reader_state_packet_dir": str(subject.reader_state_packet_dir),
        "source_reader_state_artifact_id": subject.reader_state_artifact_id,
        "source_reader_state_model_backed": packet["model_backed"],
        "source_reader_state_mode": packet["reader_state_evaluation_mode"],
        "source_reader_state_usable_for_synthesis": packet["usable_for_synthesis"],
        "candidate_text_sha256": packet["candidate_text_sha256"],
        "candidate_word_count": packet.get("candidate_word_count"),
        "synthesis_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "ablation_executed": False,
        "reader_state_evaluation_executed": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_reader_state_intake_summary_v1_controller",
    }


def _build_integrity_report(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    checks = [
        _check("source_reader_state_accepted", True),
        _check("source_reader_state_model_backed", True),
        _check("source_reader_state_usable_for_synthesis", True),
        _check("source_ablation_chain_loaded", True),
        _check("candidate_hash_matches_ablation", True),
        _check("proof_packet_preserved", True),
        _check("prior_reader_state_packet_preserved", True),
        _check("law_id_preserved", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "evidence_chain_coherent": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "evidence_chain_integrity_report_v1_controller",
    }


def _build_law_effect(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        **_source_fields(subject),
        "candidate_law_effect": CANDIDATE_LAW_EFFECT,
        "reader_state_support": READER_STATE_SUPPORT,
        "supportive_evidence": [
            "first-read pressure improved",
            "object-event consequence improved",
            "explanation timing improved",
            "reread return improved",
            "non-imitation passed",
            "model-backed reader-state evaluation accepted",
            "ablation identified coherent law-bearing choices",
        ],
        "first_read_pressure_result": packet["first_read_pressure_result"],
        "object_event_consequence_result": packet["object_event_consequence_result"],
        "explanation_timing_result": packet["explanation_timing_result"],
        "reread_return_result": packet["reread_return_result"],
        "non_imitation_result": packet["non_imitation_result"],
        "current_best_updated": False,
        "finalization_eligible": False,
        "worker": "candidate_law_effect_synthesis_v1_controller",
    }


def _build_packet_0063_comparison(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    comparison = subject.reader_state_payloads[
        "candidate_vs_packet_0063_reader_state_comparison"
    ]
    packet = _packet(subject)
    return {
        **_source_fields(subject),
        "packet_0063_preserved_as_current_best": True,
        "candidate_improves_law_specific_reader_path": True,
        "packet_0063_strengths_preserved": True,
        "comparison_summary": comparison.get(
            "comparison_summary",
            packet.get("reader_state_summary", {}).get("summary", ""),
        ),
        "reader_state_results": {
            key: packet[key]
            for key in (
                "first_read_pressure_result",
                "object_event_consequence_result",
                "explanation_timing_result",
                "reread_return_result",
            )
        },
        "candidate_superiority_claimed": False,
        "current_best_supersession_claimed": False,
        "current_best_updated": False,
        "worker": "packet_0063_comparison_synthesis_v1_controller",
    }


def _build_alignment_report(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    control_matrix = subject.reader_state_payloads["ablation_control_reader_state_matrix"]
    return {
        **_source_fields(subject),
        "ablation_control_count": len(ABLATION_CONTROL_IDS),
        "ablation_controls": [
            row
            for row in _object_list(control_matrix, "ablation_controls")
            if row.get("control_id") in set(ABLATION_CONTROL_IDS)
        ],
        "law_bearing_choice_count": packet.get("law_bearing_choice_count"),
        "alignment_result": "reader_state_supports_ablation_hypothesis_but_not_final_proof",
        "model_calls": 0,
        "ablation_executed": False,
        "reader_state_evaluation_executed": False,
        "worker": "ablation_reader_state_alignment_report_v1_controller",
    }


def _build_risk_synthesis(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    risk_report = subject.reader_state_payloads["candidate_review_risk_probe_report"]
    risk_results = {
        str(row.get("risk_id")): row for row in _object_list(risk_report, "risk_probe_results")
    }
    active_risks = []
    for risk in CANDIDATE_REVIEW_RISKS:
        risk_id = str(risk["risk_id"])
        active_risks.append(
            {
                **risk,
                "reader_state_probe": risk_results.get(risk_id, {}),
                "blocks_finalization": True,
            }
        )
    return {
        **_source_fields(subject),
        "active_risks": active_risks,
        "active_risk_count": len(active_risks),
        "risk_classification": "active_risks_block_finalization_not_synthesis_review",
        "strongest_rival_defeated_claimed": False,
        "finalization_eligible": False,
        "worker": "active_risk_synthesis_report_v1_controller",
    }


def _build_rival_synthesis(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    rival_report = subject.reader_state_payloads["strongest_rival_pressure_status_report"]
    return {
        **_source_fields(subject),
        "strongest_rival_status": packet["strongest_rival_pressure_result"],
        "strongest_rival_pressure_result": packet["strongest_rival_pressure_result"],
        "strongest_rival_remains_blocking": True,
        "strongest_rival_pressure_narrowed": (
            packet["strongest_rival_pressure_result"] == "narrowed_but_blocking"
        ),
        "pressure_summary": rival_report.get("pressure_summary"),
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_comparison_passed": False,
        "finalization_eligible": False,
        "worker": "strongest_rival_pressure_synthesis_v1_controller",
    }


def _build_current_best_recommendation(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "current_best_decision": CURRENT_BEST_DECISION,
        "current_best_update_recommendation": CURRENT_BEST_RECOMMENDATION,
        "recommendation_rationale": (
            "Model-backed reader-state evidence supports packet_0002 as a stronger "
            "law-specific candidate than packet_0063, but active risks and strongest-rival "
            "pressure still require a separate loop-review/current-best decision."
        ),
        "allowed_decision_values": [
            "recommend_promote_to_new_current_best_pending_loop_review",
            "hold_as_promising_candidate_pending_targeted_risk_repair",
            "reject_candidate_retain_packet_0063",
            "inconclusive_requires_additional_reader_state",
        ],
        "current_best_updated": False,
        "candidate_superiority_claimed": False,
        "current_best_supersession_claimed": False,
        "finalization_eligible": False,
        "worker": "current_best_decision_recommendation_v1_controller",
    }


def _build_future_options(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "if_promoting": [
            "use a separate current-best decision or loop-review command",
            "keep strongest-rival pressure blocking",
            "carry active risks into the next loop",
        ],
        "if_repairing": [
            "target explanation explicitness without free generation",
            "target static or retrospective event sequence",
            "target chemistry register risk",
            "target conclusion summary pressure",
        ],
        "next_evidence_step": NEXT_RECOMMENDED_ACTION,
        "generation_authorized": False,
        "candidate_generated": False,
        "current_best_updated": False,
        "worker": "future_repair_or_supersession_options_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_reader_state_accepted", True),
        _gate_result("source_reader_state_model_backed", True),
        _gate_result("source_reader_state_usable_for_synthesis", True),
        _gate_result("candidate_evidence_chain_coherent", True),
        _gate_result("reader_state_results_present", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_current_best_update", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "current_best_updated",
            False,
            ["current best remains packet_0063 until separate decision"],
        ),
        _gate_result(
            "strongest_rival_pressure_resolved",
            False,
            ["strongest rival pressure is narrowed but still blocking"],
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["evidence synthesis is not finalization evidence"],
        ),
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "unresolved_blockers": [
            "current best has not been updated",
            "strongest rival remains blocking",
            "active risks remain",
            "finalization remains refused",
        ],
        "synthesis_executed": True,
        "model_calls": 0,
        "candidate_generated": False,
        "generation_authorized": False,
        "current_best_updated": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "synthesis_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    checks = [
        _check("no_generation_performed", True),
        _check("no_ablation_performed", True),
        _check("no_reader_state_evaluation_performed", True),
        _check("no_model_calls", True),
        _check("current_best_not_mutated", True),
        _check("finalization_refused", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "model_calls": 0,
        "candidate_generated": False,
        "generation_authorized": False,
        "ablation_executed": False,
        "reader_state_evaluation_executed": False,
        "synthesis_executed": True,
        "current_best_updated": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = _packet(subject)
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CANDIDATE_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_candidate_evidence_synthesis_packet",
    )
    return {
        **_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "synthesis_executed": True,
        "candidate_text_sha256": packet["candidate_text_sha256"],
        "candidate_word_count": packet.get("candidate_word_count"),
        "candidate_law_effect": CANDIDATE_LAW_EFFECT,
        "reader_state_support": READER_STATE_SUPPORT,
        "strongest_rival_status": packet["strongest_rival_pressure_result"],
        "current_best_decision": CURRENT_BEST_DECISION,
        "current_best_update_recommendation": CURRENT_BEST_RECOMMENDATION,
        "ready_for_current_best_decision_review": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "ablation_executed": False,
        "reader_state_evaluation_executed": False,
        "model_calls": 0,
        "counts": {**counts, "model_calls": 0},
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_candidate_evidence_synthesis_packet",
        ],
        "gate_report": payloads["synthesis_gate_report"],
        "current_best_updated": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "worker": "nonlocal_law_candidate_evidence_synthesis_packet_v1_controller",
    }


def _result_payload(
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_candidate_evidence_synthesis_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _source_fields(
    subject: NonlocalLawCandidateEvidenceSynthesisSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_reader_state_packet_id": subject.reader_state_packet_id,
        "source_ablation_packet_id": packet.get("source_ablation_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_strategy_packet_id": packet.get("source_strategy_packet_id"),
        "source_diagnostic_packet_id": packet.get("source_diagnostic_packet_id"),
        "base_candidate_packet_id": packet.get("base_candidate_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "current_best_candidate_packet_id"
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "prior_reader_state_packet_id": packet.get("prior_reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "target_scope": packet.get("target_scope"),
    }


def _packet(subject: NonlocalLawCandidateEvidenceSynthesisSubject) -> dict[str, Any]:
    return subject.reader_state_payloads[
        "nonlocal_law_candidate_reader_state_evaluation_packet"
    ]


def _source_ablation_dir(config: AbiConfig, packet: dict[str, Any], run_id: str) -> Path:
    source_dir = packet.get("source_ablation_packet_dir")
    if isinstance(source_dir, str) and source_dir.strip():
        path = Path(source_dir)
        return path if path.is_absolute() else config.root / path
    source_id = str(packet.get("source_ablation_packet_id") or "")
    return config.run_dir(run_id) / "nonlocal_law_candidate_ablation" / source_id


def _load_source_ablation_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in (
        "nonlocal_law_candidate_ablation_packet",
        "ablation_control_matrix",
        "law_bearing_choice_map",
    ):
        payloads[artifact_type] = _read_envelope(
            packet_dir / f"{artifact_type}.json",
            artifact_type,
        )["payload"]
    return payloads


def _read_envelope(path: Path, artifact_type: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing {artifact_type}: {path}")
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(f"malformed {artifact_type} artifact")
    return envelope


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


def _control_ids(subject: NonlocalLawCandidateEvidenceSynthesisSubject) -> set[str]:
    packet = _packet(subject)
    controls = set()
    if isinstance(packet.get("ablation_controls"), list):
        controls.update(str(control) for control in packet["ablation_controls"])
    matrix = subject.reader_state_payloads["ablation_control_reader_state_matrix"]
    for row in _object_list(matrix, "ablation_controls"):
        if isinstance(row.get("control_id"), str):
            controls.add(str(row["control_id"]))
    source_matrix = subject.source_ablation_payloads["ablation_control_matrix"]
    for row in _object_list(source_matrix, "ablation_controls"):
        if isinstance(row.get("control_id"), str):
            controls.add(str(row["control_id"]))
    return controls


def _object_list(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def _payload_has_forbidden_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finality_claimed",
                "phase_shift_claimed",
                "strongest_rival_defeated_claimed",
                "candidate_superiority_claimed",
                "current_best_supersession_claimed",
                "current_best_updated",
                "finalization_eligible",
                "final_artifact",
                "final_claim",
            } and item is True:
                return True
            if _payload_has_forbidden_claim(item):
                return True
    if isinstance(value, list):
        return any(_payload_has_forbidden_claim(item) for item in value)
    return False


def _require_bool(payload: dict[str, object], key: str, expected: bool) -> None:
    if payload.get(key) is not expected:
        raise ValueError(f"{key} must be {str(expected).lower()}")


def _require_equal(payload: dict[str, object], key: str, expected: object) -> None:
    if payload.get(key) != expected:
        raise ValueError(f"{key} must be {expected}")


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
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": blockers or ([] if passed else [f"{gate_name} failed"]),
    }


def _refusal(
    *,
    reader_state_packet: Path | str,
    message: str,
) -> NonlocalLawCandidateEvidenceSynthesisResult:
    return NonlocalLawCandidateEvidenceSynthesisResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "reader_state_packet": str(reader_state_packet),
            "synthesis_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "ablation_executed": False,
            "reader_state_evaluation_executed": False,
            "current_best_updated": False,
            "model_calls": 0,
            "artifact_ids": {},
            "artifact_paths": {},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path
