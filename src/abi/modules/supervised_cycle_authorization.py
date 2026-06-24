"""Controller-owned supervised next-cycle authorization packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_SUPERVISED_CYCLE_AUTHORIZATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


SUPERVISED_CYCLE_AUTHORIZATION_LINEAGE_ID = "supervised_cycle_authorization_v1"
SUPERVISED_CYCLE_AUTHORIZATION_CREATED_BY = (
    "supervised_cycle_authorization_v1_controller"
)

SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS = (
    "authorize_next_strategy_only",
    "require_more_loop_cleanup",
    "pause_generation",
)

SUPERVISED_CYCLE_AUTHORIZATION_ARTIFACT_TYPES = (
    "supervised_cycle_authorization_subject_manifest",
    "loop_review_intake_summary",
    "operator_review_record",
    "cleanup_resolution_report",
    "supervised_next_cycle_readiness_report",
    "next_cycle_scope_constraints",
    "authorization_gate_report",
    "supervised_cycle_authorization_packet",
)

REQUIRED_LOOP_REVIEW_ARTIFACTS = (
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


@dataclass(frozen=True)
class SupervisedCycleAuthorizationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SupervisedCycleAuthorizationSubject:
    run_id: str
    loop_review_packet_dir: Path
    loop_review_packet_id: str
    loop_review_packet_artifact_id: str | None
    loop_review_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    current_best_candidate_packet_id: str
    current_best_candidate_packet_dir: str
    proof_packet_id: str
    proof_packet_dir: str
    reader_state_packet_id: str
    reader_state_packet_dir: str
    source_synthesis_packet_id: str
    source_synthesis_packet_dir: str
    completed_cycles: int
    strongest_rival_still_blocks: bool
    source_parent_ids: tuple[str, ...]


def run_supervised_cycle_authorization(
    config: AbiConfig,
    *,
    loop_review_packet: Path | str,
    operator_reviewed: bool,
    decision: str | None,
) -> SupervisedCycleAuthorizationResult:
    initialize_database(config)
    loop_review_packet_dir = _resolve_path(config, loop_review_packet)
    if not operator_reviewed:
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Supervised cycle authorization refused; --operator-reviewed is "
                "required."
            ),
        )
    if decision not in SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS:
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Supervised cycle authorization refused; --decision must be one "
                f"of: {', '.join(SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS)}."
            ),
        )
    if not loop_review_packet_dir.exists() or not loop_review_packet_dir.is_dir():
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Supervised cycle authorization refused; loop-review packet "
                f"directory not found: {loop_review_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, loop_review_packet_dir)
    except ValueError as error:
        return _refusal(loop_review_packet=loop_review_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                loop_review_packet=loop_review_packet_dir,
                message=(
                    "Supervised cycle authorization refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_SUPERVISED_CYCLE_AUTHORIZATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "supervised_cycle_authorization"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=SUPERVISED_CYCLE_AUTHORIZATION_LINEAGE_ID,
            created_by=SUPERVISED_CYCLE_AUTHORIZATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["supervised_cycle_authorization_subject_manifest"] = (
            _build_subject_manifest(subject, packet_dir)
        )
        artifacts["supervised_cycle_authorization_subject_manifest"] = (
            writer.write_artifact(
                "supervised_cycle_authorization_subject_manifest",
                payloads["supervised_cycle_authorization_subject_manifest"],
                parent_ids=list(subject.source_parent_ids),
            )
        )

        payloads["loop_review_intake_summary"] = _build_loop_review_intake_summary(
            subject
        )
        artifacts["loop_review_intake_summary"] = writer.write_artifact(
            "loop_review_intake_summary",
            payloads["loop_review_intake_summary"],
            parent_ids=[
                artifacts["supervised_cycle_authorization_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["operator_review_record"] = _build_operator_review_record(
            subject,
            decision=str(decision),
        )
        artifacts["operator_review_record"] = writer.write_artifact(
            "operator_review_record",
            payloads["operator_review_record"],
            parent_ids=[artifacts["loop_review_intake_summary"].id],
        )

        payloads["cleanup_resolution_report"] = _build_cleanup_resolution_report(subject)
        artifacts["cleanup_resolution_report"] = writer.write_artifact(
            "cleanup_resolution_report",
            payloads["cleanup_resolution_report"],
            parent_ids=[
                artifacts["loop_review_intake_summary"].id,
                artifacts["operator_review_record"].id,
            ],
        )

        payloads["supervised_next_cycle_readiness_report"] = (
            _build_supervised_next_cycle_readiness_report(
                subject=subject,
                decision=str(decision),
                cleanup_report=payloads["cleanup_resolution_report"],
            )
        )
        artifacts["supervised_next_cycle_readiness_report"] = writer.write_artifact(
            "supervised_next_cycle_readiness_report",
            payloads["supervised_next_cycle_readiness_report"],
            parent_ids=[
                artifacts["cleanup_resolution_report"].id,
                artifacts["operator_review_record"].id,
            ],
        )

        payloads["next_cycle_scope_constraints"] = _build_next_cycle_scope_constraints(
            subject=subject,
            readiness=payloads["supervised_next_cycle_readiness_report"],
        )
        artifacts["next_cycle_scope_constraints"] = writer.write_artifact(
            "next_cycle_scope_constraints",
            payloads["next_cycle_scope_constraints"],
            parent_ids=[artifacts["supervised_next_cycle_readiness_report"].id],
        )

        payloads["authorization_gate_report"] = _build_authorization_gate_report(
            subject=subject,
            decision=str(decision),
            payloads=payloads,
        )
        artifacts["authorization_gate_report"] = writer.write_artifact(
            "authorization_gate_report",
            payloads["authorization_gate_report"],
            parent_ids=[
                artifacts["cleanup_resolution_report"].id,
                artifacts["supervised_next_cycle_readiness_report"].id,
                artifacts["next_cycle_scope_constraints"].id,
            ],
        )

        payloads["supervised_cycle_authorization_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            decision=str(decision),
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["supervised_cycle_authorization_packet"] = writer.write_artifact(
            "supervised_cycle_authorization_packet",
            payloads["supervised_cycle_authorization_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "supervised_cycle_authorization_packet"
            ],
        )

        gate_report = payloads["authorization_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="supervised_cycle_authorization_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=SUPERVISED_CYCLE_AUTHORIZATION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        decision=str(decision),
        artifacts=artifacts,
        payloads=payloads,
    )
    return SupervisedCycleAuthorizationResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    loop_review_packet_dir: Path,
) -> SupervisedCycleAuthorizationSubject:
    payloads = _load_required_payloads(loop_review_packet_dir)
    loop_packet = payloads["evidence_loop_review_packet"]
    manifest = payloads["evidence_loop_review_subject_manifest"]
    run_id = loop_packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Supervised cycle authorization refused; loop-review missing run_id.")
    if loop_packet.get("accepted") is False:
        raise ValueError("Supervised cycle authorization refused; loop-review is not accepted.")

    packet_path = loop_review_packet_dir / "evidence_loop_review_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    loop_artifact_ids = {
        str(key): str(value)
        for key, value in loop_packet.get("artifact_ids", {}).items()
        if isinstance(value, str)
    }
    parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *loop_artifact_ids.values(),
        ]
    )
    return SupervisedCycleAuthorizationSubject(
        run_id=run_id,
        loop_review_packet_dir=loop_review_packet_dir,
        loop_review_packet_id=str(loop_packet.get("packet_id") or loop_review_packet_dir.name),
        loop_review_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        loop_review_artifact_ids=loop_artifact_ids,
        payloads=payloads,
        current_best_candidate_packet_id=str(
            loop_packet.get("current_best_candidate_packet_id")
            or manifest.get("current_best_candidate_packet_id")
            or ""
        ),
        current_best_candidate_packet_dir=str(
            manifest.get("current_best_candidate_packet_dir") or ""
        ),
        proof_packet_id=str(loop_packet.get("proof_packet_id") or manifest.get("proof_packet_id") or ""),
        proof_packet_dir=str(manifest.get("proof_packet_dir") or ""),
        reader_state_packet_id=str(
            loop_packet.get("reader_state_packet_id")
            or manifest.get("reader_state_packet_id")
            or ""
        ),
        reader_state_packet_dir=str(manifest.get("reader_state_packet_dir") or ""),
        source_synthesis_packet_id=str(
            loop_packet.get("source_synthesis_packet_id")
            or manifest.get("source_synthesis_packet_id")
            or ""
        ),
        source_synthesis_packet_dir=str(manifest.get("source_synthesis_packet_dir") or ""),
        completed_cycles=int(loop_packet.get("completed_cycle_count") or loop_packet.get("completed_cycles") or 0),
        strongest_rival_still_blocks=bool(
            loop_packet.get("strongest_rival_still_blocks")
            or manifest.get("strongest_rival_still_blocks")
        ),
        source_parent_ids=tuple(parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_LOOP_REVIEW_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Supervised cycle authorization refused; loop-review packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Supervised cycle authorization refused; malformed loop-review "
                f"artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _build_subject_manifest(
    subject: SupervisedCycleAuthorizationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "loop_review_packet_artifact_id": subject.loop_review_packet_artifact_id,
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "source_synthesis_packet_dir": subject.source_synthesis_packet_dir,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "current_best_candidate_packet_dir": subject.current_best_candidate_packet_dir,
        "proof_packet_id": subject.proof_packet_id,
        "proof_packet_dir": subject.proof_packet_dir,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "reader_state_packet_dir": subject.reader_state_packet_dir,
        "completed_cycles": subject.completed_cycles,
        "strongest_rival_still_blocks": subject.strongest_rival_still_blocks,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "supervised_cycle_authorization_subject_manifest_v1_controller",
    }


def _build_loop_review_intake_summary(
    subject: SupervisedCycleAuthorizationSubject,
) -> dict[str, object]:
    packet = subject.payloads["evidence_loop_review_packet"]
    counts = _as_dict(packet.get("counts"))
    return {
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "loop_review_accepted": packet.get("accepted", True) is not False,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "completed_cycles": subject.completed_cycles,
        "artifact_count_consistent": counts.get("artifact_count_consistent") is True,
        "produced_artifacts": counts.get("produced_artifacts"),
        "required_artifacts": counts.get("required_artifacts"),
        "stale_recommendation_detected": packet.get("stale_recommendation_detected") is True,
        "loop_integrity_cleanup_required": packet.get("loop_integrity_cleanup_required") is True,
        "ready_for_supervised_next_cycle": packet.get("ready_for_supervised_next_cycle") is True,
        "ready_for_full_autonomous_loop_controller": (
            packet.get("ready_for_full_autonomous_loop_controller") is True
        ),
        "next_generation_authorized": packet.get("next_generation_authorized") is True,
        "next_recommended_action": packet.get("next_recommended_action"),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "loop_review_intake_summary_v1_controller",
    }


def _build_operator_review_record(
    subject: SupervisedCycleAuthorizationSubject,
    *,
    decision: str,
) -> dict[str, object]:
    return {
        "operator_reviewed": True,
        "reviewed_loop_review_packet_id": subject.loop_review_packet_id,
        "reviewed_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "decision": decision,
        "not_final_operator_approval": True,
        "not_human_validation": True,
        "does_not_authorize_finalization": True,
        "does_not_authorize_candidate_generation": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "operator_review_record_v1_controller",
    }


def _build_cleanup_resolution_report(
    subject: SupervisedCycleAuthorizationSubject,
) -> dict[str, object]:
    packet = subject.payloads["evidence_loop_review_packet"]
    loop_integrity = subject.payloads["loop_integrity_report"]
    counts = _as_dict(packet.get("counts"))
    artifact_count_consistent = counts.get("artifact_count_consistent") is True
    stale_present = "stale_recommendation_detected" in packet
    stale_currently_false = packet.get("stale_recommendation_detected") is False
    output_shape_stable = bool(counts.get("model_calls") == 0 and packet.get("packet_id"))
    fresh_cleanup_passed = bool(
        artifact_count_consistent and stale_present and stale_currently_false and output_shape_stable
    )
    return {
        "artifact_count_consistency_resolved_for_fresh_loop_review_output": (
            artifact_count_consistent
        ),
        "command_output_shape_stable_for_inspected_command": output_shape_stable,
        "stale_recommendation_detection_present": stale_present,
        "stale_recommendation_detected": not stale_currently_false,
        "legacy_packet_count_quirks_nonblocking_for_supervised_cycle": True,
        "legacy_packet_count_quirks_scope": (
            "older source packets only; fresh loop-review output is count-consistent"
        ),
        "fresh_loop_integrity_cleanup_passed": fresh_cleanup_passed,
        "full_autonomous_loop_cleanup_complete": False,
        "supervised_strategy_step_cleanup_complete": fresh_cleanup_passed,
        "full_autonomous_loop_controller_remains_not_ready": True,
        "finalization_remains_ineligible": True,
        "source_loop_integrity_cleanup_blockers": list(
            loop_integrity.get("cleanup_blockers", [])
        ),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "cleanup_resolution_report_v1_controller",
    }


def _build_supervised_next_cycle_readiness_report(
    *,
    subject: SupervisedCycleAuthorizationSubject,
    decision: str,
    cleanup_report: dict[str, object],
) -> dict[str, object]:
    loop_packet = subject.payloads["evidence_loop_review_packet"]
    fresh_cleanup_passed = cleanup_report["fresh_loop_integrity_cleanup_passed"] is True
    coherent = (
        bool(subject.current_best_candidate_packet_id)
        and bool(subject.proof_packet_id)
        and bool(subject.reader_state_packet_id)
        and subject.completed_cycles >= 2
        and loop_packet.get("stale_recommendation_detected") is False
        and fresh_cleanup_passed
    )
    next_strategy_authorized = decision == "authorize_next_strategy_only" and coherent
    return {
        "ready_for_supervised_next_strategy": next_strategy_authorized,
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "next_strategy_authorized": next_strategy_authorized,
        "next_generation_authorized": False,
        "readiness_reasons": [
            f"current best candidate {subject.current_best_candidate_packet_id} exists",
            f"proof packet {subject.proof_packet_id} is linked",
            f"reader-state packet {subject.reader_state_packet_id} is linked",
            f"completed cycles mapped: {subject.completed_cycles}",
            "drift risk was assessed by loop review",
            "no stale recommendation is currently detected",
            "fresh artifact counts are consistent",
            "operator reviewed loop packet",
            "authorized next action is strategy/review, not generation",
        ],
        "readiness_blockers": [] if next_strategy_authorized else _readiness_blockers(
            subject=subject,
            decision=decision,
            cleanup_report=cleanup_report,
        ),
        "decision": decision,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "supervised_next_cycle_readiness_report_v1_controller",
    }


def _build_next_cycle_scope_constraints(
    *,
    subject: SupervisedCycleAuthorizationSubject,
    readiness: dict[str, object],
) -> dict[str, object]:
    return {
        "next_strategy_authorized": readiness["next_strategy_authorized"],
        "next_generation_authorized": False,
        "scope": [
            "produce a next residual target strategy packet only",
            "no candidate generation",
            "no OpenAI",
            "no ablation",
            "no reader-state evaluation",
            "no finalization",
            "no phase-shift claim",
            f"preserve {subject.current_best_candidate_packet_id} as current best candidate",
            "strongest rival remains blocking",
            "reader-state gain remains partial",
            "next strategy must be evidence-derived from loop-review residual blockers",
        ],
        "candidate_generation_requires_later_authorization_packet": True,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "strongest_rival_still_blocks": subject.strongest_rival_still_blocks,
        "reader_state_gain_remains_partial": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_cycle_scope_constraints_v1_controller",
    }


def _build_authorization_gate_report(
    *,
    subject: SupervisedCycleAuthorizationSubject,
    decision: str,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    readiness = payloads["supervised_next_cycle_readiness_report"]
    cleanup = payloads["cleanup_resolution_report"]
    next_strategy_authorized = readiness["next_strategy_authorized"] is True
    gate_results = [
        _gate_result("loop_review_packet_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("current_best_candidate_identified", bool(subject.current_best_candidate_packet_id)),
        _gate_result("proof_packet_linked", bool(subject.proof_packet_id)),
        _gate_result("reader_state_packet_linked", bool(subject.reader_state_packet_id)),
        _gate_result("completed_cycles_present", subject.completed_cycles >= 2),
        _gate_result(
            "cleanup_resolution_recorded",
            cleanup["fresh_loop_integrity_cleanup_passed"] is True,
        ),
        _gate_result("next_strategy_authorized", next_strategy_authorized),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "next_candidate_generation_authorized",
            False,
            ["candidate generation requires a later separate authorization packet"],
            record=False,
        ),
        _gate_result(
            "full_autonomous_loop_controller_ready",
            False,
            ["full autonomous loop controller remains out of scope"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["supervised cycle authorization is not finalization evidence"],
            record=False,
        ),
        _gate_result(
            "human_validation_present",
            False,
            ["operator review is not human validation"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_defeated",
            False,
            ["strongest rival remains blocking"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "next candidate generation is not authorized",
        "full autonomous loop controller remains not ready",
        "finalization remains ineligible",
        "human validation is absent",
        "strongest rival remains blocking",
    ]
    return {
        "accepted": next_strategy_authorized,
        "decision": decision,
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "operator_reviewed": True,
        "ready_for_supervised_next_strategy": next_strategy_authorized,
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "next_strategy_authorized": next_strategy_authorized,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "no_phase_shift_claim": True,
        "no_final_claim": True,
        "not_human_validated": True,
        "human_validation_present": False,
        "strongest_rival_defeated": False,
        "strongest_rival_still_blocks": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Supervised next strategy is authorized, but candidate generation, "
            "autonomous looping, and finalization remain fail-closed."
        )
        if next_strategy_authorized
        else (
            "Supervised cycle authorization was recorded, but next strategy is "
            "not authorized."
        ),
        "worker": "authorization_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: SupervisedCycleAuthorizationSubject,
    packet_dir: Path,
    decision: str,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    readiness = payloads["supervised_next_cycle_readiness_report"]
    counts = packet_artifact_count_summary(
        required_artifact_types=SUPERVISED_CYCLE_AUTHORIZATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="supervised_cycle_authorization_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "supervised_cycle_authorization_packet"],
        "counts": {
            **counts,
            "authorization_artifacts": counts["produced_artifacts"],
            "required_authorization_artifacts": counts["required_artifacts"],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "completed_cycles": subject.completed_cycles,
        "operator_reviewed": True,
        "decision": decision,
        "next_strategy_authorized": readiness["next_strategy_authorized"],
        "next_generation_authorized": False,
        "ready_for_supervised_next_strategy": readiness[
            "ready_for_supervised_next_strategy"
        ],
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "next_recommended_action": "prepare_next_residual_target_strategy_under_supervision",
        "gate_report": payloads["authorization_gate_report"],
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "supervised_cycle_authorization_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: SupervisedCycleAuthorizationSubject,
    packet_dir: Path,
    decision: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["supervised_cycle_authorization_packet"]
    return {
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
        "counts": packet["counts"],
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "operator_reviewed": True,
        "decision": decision,
        "next_strategy_authorized": packet["next_strategy_authorized"],
        "next_generation_authorized": False,
        "ready_for_supervised_next_strategy": packet[
            "ready_for_supervised_next_strategy"
        ],
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "candidate_generated": False,
        "model_calls": 0,
        "next_recommended_action": packet["next_recommended_action"],
        "gate_report": payloads["authorization_gate_report"],
    }


def _readiness_blockers(
    *,
    subject: SupervisedCycleAuthorizationSubject,
    decision: str,
    cleanup_report: dict[str, object],
) -> list[str]:
    blockers: list[str] = []
    if decision != "authorize_next_strategy_only":
        blockers.append(f"decision is {decision}")
    if not subject.current_best_candidate_packet_id:
        blockers.append("current best candidate is missing")
    if not subject.proof_packet_id:
        blockers.append("proof packet is missing")
    if not subject.reader_state_packet_id:
        blockers.append("reader-state packet is missing")
    if subject.completed_cycles < 2:
        blockers.append("completed cycles are fewer than two")
    if cleanup_report["fresh_loop_integrity_cleanup_passed"] is not True:
        blockers.append("fresh loop-integrity cleanup did not pass")
    return blockers


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


def _refusal(
    *,
    loop_review_packet: Path,
    message: str,
) -> SupervisedCycleAuthorizationResult:
    return SupervisedCycleAuthorizationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "loop_review_packet": str(loop_review_packet),
            "artifact_ids": {},
            "counts": {
                "model_calls": 0,
                "candidate_artifacts_created": 0,
            },
            "operator_reviewed": False,
            "next_strategy_authorized": False,
            "next_generation_authorized": False,
            "ready_for_supervised_next_strategy": False,
            "ready_for_supervised_candidate_generation": False,
            "ready_for_full_autonomous_loop_controller": False,
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
