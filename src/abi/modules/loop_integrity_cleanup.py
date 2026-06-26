"""Deterministic loop-integrity cleanup checkpoint packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_LOOP_INTEGRITY_CLEANUP_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.evidence_loop_review import EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


LOOP_INTEGRITY_CLEANUP_LINEAGE_ID = "loop_integrity_cleanup_v1"
LOOP_INTEGRITY_CLEANUP_CREATED_BY = "loop_integrity_cleanup_v1_controller"

LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES = (
    "loop_integrity_cleanup_subject_manifest",
    "loop_review_intake_summary",
    "active_evidence_state_checkpoint",
    "stale_recommendation_registry",
    "prior_cycle_supersession_map",
    "next_command_safety_policy",
    "generation_lock_report",
    "supervised_strategy_readiness_report",
    "loop_integrity_cleanup_gate_report",
    "loop_integrity_cleanup_packet",
)

REQUIRED_LOOP_REVIEW_ARTIFACTS = EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES


@dataclass(frozen=True)
class LoopIntegrityCleanupResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class LoopIntegrityCleanupSubject:
    run_id: str
    loop_review_packet_dir: Path
    loop_review_packet_id: str
    loop_review_packet_artifact_id: str | None
    loop_review_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_synthesis_packet_dir: Path
    source_synthesis_payload: dict[str, Any]
    source_synthesis_artifact_id: str | None
    current_best_candidate: dict[str, Any]
    current_best_candidate_packet_id: str
    current_best_candidate_kind: str
    current_best_candidate_packet_dir: Path
    proof_packet_id: str
    proof_packet_dir: Path
    proof_payload: dict[str, Any]
    reader_state_packet_id: str
    reader_state_packet_dir: Path
    reader_state_payload: dict[str, Any]
    source_synthesis_packet_id: str
    selected_residual_target_id: str | None
    target_adapter_id: str | None
    target_scope: str | None
    reader_state_transformation_strength: str
    strongest_rival_still_blocks: bool
    prior_best_packet_id: str
    residual_authorization_packet_id: str | None
    residual_work_order_packet_id: str | None
    source_parent_ids: tuple[str, ...]


def run_loop_integrity_cleanup(
    config: AbiConfig,
    *,
    loop_review_packet: Path | str,
    operator_reviewed: bool,
) -> LoopIntegrityCleanupResult:
    initialize_database(config)
    loop_review_packet_dir = _resolve_path(config, loop_review_packet)
    if not operator_reviewed:
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Loop-integrity cleanup refused; --operator-reviewed is required."
            ),
        )
    if not loop_review_packet_dir.exists() or not loop_review_packet_dir.is_dir():
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Loop-integrity cleanup refused; loop-review packet directory "
                f"not found: {loop_review_packet_dir}"
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
                    "Loop-integrity cleanup refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_LOOP_INTEGRITY_CLEANUP_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "loop_integrity_cleanup"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=LOOP_INTEGRITY_CLEANUP_LINEAGE_ID,
            created_by=LOOP_INTEGRITY_CLEANUP_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["loop_integrity_cleanup_subject_manifest"] = (
            _build_subject_manifest(subject, packet_dir)
        )
        artifacts["loop_integrity_cleanup_subject_manifest"] = writer.write_artifact(
            "loop_integrity_cleanup_subject_manifest",
            payloads["loop_integrity_cleanup_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["loop_review_intake_summary"] = _build_loop_review_intake_summary(
            subject
        )
        artifacts["loop_review_intake_summary"] = writer.write_artifact(
            "loop_review_intake_summary",
            payloads["loop_review_intake_summary"],
            parent_ids=[
                artifacts["loop_integrity_cleanup_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["active_evidence_state_checkpoint"] = (
            _build_active_evidence_state_checkpoint(subject)
        )
        artifacts["active_evidence_state_checkpoint"] = writer.write_artifact(
            "active_evidence_state_checkpoint",
            payloads["active_evidence_state_checkpoint"],
            parent_ids=[artifacts["loop_review_intake_summary"].id],
        )

        payloads["stale_recommendation_registry"] = (
            _build_stale_recommendation_registry(config, subject)
        )
        artifacts["stale_recommendation_registry"] = writer.write_artifact(
            "stale_recommendation_registry",
            payloads["stale_recommendation_registry"],
            parent_ids=[artifacts["active_evidence_state_checkpoint"].id],
        )

        payloads["prior_cycle_supersession_map"] = _build_prior_cycle_supersession_map(
            subject
        )
        artifacts["prior_cycle_supersession_map"] = writer.write_artifact(
            "prior_cycle_supersession_map",
            payloads["prior_cycle_supersession_map"],
            parent_ids=[
                artifacts["active_evidence_state_checkpoint"].id,
                artifacts["stale_recommendation_registry"].id,
            ],
        )

        payloads["next_command_safety_policy"] = _build_next_command_safety_policy(
            subject
        )
        artifacts["next_command_safety_policy"] = writer.write_artifact(
            "next_command_safety_policy",
            payloads["next_command_safety_policy"],
            parent_ids=[
                artifacts["active_evidence_state_checkpoint"].id,
                artifacts["prior_cycle_supersession_map"].id,
            ],
        )

        payloads["generation_lock_report"] = _build_generation_lock_report(subject)
        artifacts["generation_lock_report"] = writer.write_artifact(
            "generation_lock_report",
            payloads["generation_lock_report"],
            parent_ids=[
                artifacts["stale_recommendation_registry"].id,
                artifacts["next_command_safety_policy"].id,
            ],
        )

        payloads["supervised_strategy_readiness_report"] = (
            _build_supervised_strategy_readiness_report(
                subject,
                packet_dir=packet_dir,
            )
        )
        artifacts["supervised_strategy_readiness_report"] = writer.write_artifact(
            "supervised_strategy_readiness_report",
            payloads["supervised_strategy_readiness_report"],
            parent_ids=[
                artifacts["generation_lock_report"].id,
                artifacts["next_command_safety_policy"].id,
            ],
        )

        payloads["loop_integrity_cleanup_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["loop_integrity_cleanup_gate_report"] = writer.write_artifact(
            "loop_integrity_cleanup_gate_report",
            payloads["loop_integrity_cleanup_gate_report"],
            parent_ids=[
                artifacts["active_evidence_state_checkpoint"].id,
                artifacts["stale_recommendation_registry"].id,
                artifacts["prior_cycle_supersession_map"].id,
                artifacts["next_command_safety_policy"].id,
                artifacts["generation_lock_report"].id,
                artifacts["supervised_strategy_readiness_report"].id,
            ],
        )

        payloads["loop_integrity_cleanup_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["loop_integrity_cleanup_packet"] = writer.write_artifact(
            "loop_integrity_cleanup_packet",
            payloads["loop_integrity_cleanup_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "loop_integrity_cleanup_packet"
            ],
        )

        gate_report = payloads["loop_integrity_cleanup_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="loop_integrity_cleanup_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=LOOP_INTEGRITY_CLEANUP_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    return LoopIntegrityCleanupResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    loop_review_packet_dir: Path,
) -> LoopIntegrityCleanupSubject:
    payloads = _load_required_payloads(loop_review_packet_dir)
    loop_packet = payloads["evidence_loop_review_packet"]
    manifest = payloads["evidence_loop_review_subject_manifest"]
    run_id = _required_text(loop_packet.get("run_id"), "loop-review missing run_id")

    _validate_no_final_or_phase_claim(payloads)
    _validate_loop_review_does_not_authorize_generation(payloads)

    source_synthesis_packet_id = _required_text(
        loop_packet.get("source_synthesis_packet_id")
        or manifest.get("source_synthesis_packet_id"),
        "loop-review missing source synthesis packet ID",
    )
    source_synthesis_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="autonomous_evidence_synthesis",
        packet_id=source_synthesis_packet_id,
        preferred=manifest.get("source_synthesis_packet_dir"),
    )
    source_synthesis_payload = _require_packet_file(
        source_synthesis_packet_dir,
        "autonomous_evidence_synthesis_packet.json",
        "source synthesis cannot be resolved",
    )
    _validate_payload_no_final_or_phase_claim(source_synthesis_payload, "source synthesis")
    current_best = _as_dict(source_synthesis_payload.get("best_current_candidate"))
    if not current_best:
        best_selection = _optional_packet_payload(
            source_synthesis_packet_dir,
            "best_current_candidate_selection.json",
        )
        current_best = _as_dict(best_selection.get("selected_best_candidate"))
    if not current_best:
        raise ValueError(
            "Loop-integrity cleanup refused; source synthesis does not expose "
            "best_current_candidate."
        )

    current_best_packet_id = _required_text(
        loop_packet.get("current_best_candidate_packet_id")
        or manifest.get("current_best_candidate_packet_id"),
        "loop-review missing current best candidate packet ID",
    )
    _validate_packet_id_match(
        label="current best candidate",
        expected=_required_text(
            current_best.get("packet_id"),
            "source synthesis current best is missing packet_id",
        ),
        actual=current_best_packet_id,
    )
    current_best_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="bounded_macro_recomposition",
        packet_id=current_best_packet_id,
        preferred=manifest.get("current_best_candidate_packet_dir"),
    )
    _require_packet_file(
        current_best_packet_dir,
        "macro_recomposition_packet.json",
        "current best candidate cannot be resolved",
    )

    proof_packet_id = _required_text(
        loop_packet.get("proof_packet_id") or manifest.get("proof_packet_id"),
        "loop-review missing proof packet ID",
    )
    _validate_packet_id_match(
        label="proof packet",
        expected=_required_text(
            current_best.get("proof_packet_id"),
            "source synthesis current best is missing proof_packet_id",
        ),
        actual=proof_packet_id,
    )
    proof_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="executed_ablation",
        packet_id=proof_packet_id,
        preferred=manifest.get("proof_packet_dir"),
    )
    proof_payload = _require_packet_file(
        proof_packet_dir,
        "executed_ablation_packet.json",
        "proof packet cannot be resolved",
    )

    reader_state_packet_id = _required_text(
        loop_packet.get("reader_state_packet_id") or manifest.get("reader_state_packet_id"),
        "loop-review missing reader-state packet ID",
    )
    _validate_packet_id_match(
        label="reader-state packet",
        expected=_required_text(
            current_best.get("reader_state_packet_id"),
            "source synthesis current best is missing reader_state_packet_id",
        ),
        actual=reader_state_packet_id,
    )
    reader_state_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="internal_reader_state_evaluation",
        packet_id=reader_state_packet_id,
        preferred=manifest.get("reader_state_packet_dir"),
    )
    reader_state_payload = _require_packet_file(
        reader_state_packet_dir,
        "internal_reader_state_eval_packet.json",
        "reader-state packet cannot be resolved",
    )

    selected_residual_target_id = _optional_text(
        current_best.get("selected_residual_target_id")
        or current_best.get("target_movement")
        or current_best.get("target_scope")
    )
    target_adapter_id = _optional_text(current_best.get("target_adapter_id"))
    target_scope = _optional_text(current_best.get("target_scope"))
    _validate_completed_cycle_alignment(
        payloads=payloads,
        source_synthesis_packet_id=source_synthesis_packet_id,
        current_best_packet_id=current_best_packet_id,
        proof_packet_id=proof_packet_id,
        reader_state_packet_id=reader_state_packet_id,
    )
    _validate_current_cycle_packets(
        current_best=current_best,
        proof_payload=proof_payload,
        proof_packet_dir=proof_packet_dir,
        reader_state_payload=reader_state_payload,
        reader_state_packet_dir=reader_state_packet_dir,
        current_best_packet_id=current_best_packet_id,
        proof_packet_id=proof_packet_id,
        reader_state_packet_id=reader_state_packet_id,
        selected_residual_target_id=selected_residual_target_id,
        target_adapter_id=target_adapter_id,
    )

    packet_path = loop_review_packet_dir / "evidence_loop_review_packet.json"
    synthesis_path = source_synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json"
    with connect(config.db_path) as connection:
        loop_packet_artifact = _artifact_for_path(connection, packet_path)
        synthesis_artifact = _artifact_for_path(connection, synthesis_path)

    loop_artifact_ids = _string_dict(loop_packet.get("artifact_ids", {}))
    source_parent_ids = _unique(
        [
            loop_packet_artifact.id if loop_packet_artifact else None,
            synthesis_artifact.id if synthesis_artifact else None,
            *loop_artifact_ids.values(),
        ]
    )
    return LoopIntegrityCleanupSubject(
        run_id=run_id,
        loop_review_packet_dir=loop_review_packet_dir,
        loop_review_packet_id=str(loop_packet.get("packet_id") or loop_review_packet_dir.name),
        loop_review_packet_artifact_id=(
            loop_packet_artifact.id if loop_packet_artifact else None
        ),
        loop_review_artifact_ids=loop_artifact_ids,
        payloads=payloads,
        source_synthesis_packet_dir=source_synthesis_packet_dir,
        source_synthesis_payload=source_synthesis_payload,
        source_synthesis_artifact_id=synthesis_artifact.id if synthesis_artifact else None,
        current_best_candidate=current_best,
        current_best_candidate_packet_id=current_best_packet_id,
        current_best_candidate_kind=str(
            manifest.get("current_best_candidate_packet_kind")
            or current_best.get("packet_kind")
            or "bounded_macro_recomposition"
        ),
        current_best_candidate_packet_dir=current_best_packet_dir,
        proof_packet_id=proof_packet_id,
        proof_packet_dir=proof_packet_dir,
        proof_payload=proof_payload,
        reader_state_packet_id=reader_state_packet_id,
        reader_state_packet_dir=reader_state_packet_dir,
        reader_state_payload=reader_state_payload,
        source_synthesis_packet_id=source_synthesis_packet_id,
        selected_residual_target_id=selected_residual_target_id,
        target_adapter_id=target_adapter_id,
        target_scope=target_scope,
        reader_state_transformation_strength=str(
            current_best.get("reader_state_reread_transformation_strength")
            or "partial"
        ),
        strongest_rival_still_blocks=bool(
            loop_packet.get("strongest_rival_still_blocks")
            or manifest.get("strongest_rival_still_blocks")
            or current_best.get("strongest_rival_still_blocks")
        ),
        prior_best_packet_id=str(current_best.get("base_candidate_packet_id") or ""),
        residual_authorization_packet_id=_optional_text(
            current_best.get("source_authorization_packet_id")
        ),
        residual_work_order_packet_id=_find_residual_work_order_id(
            config.run_dir(run_id),
            current_best,
        ),
        source_parent_ids=tuple(source_parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_LOOP_REVIEW_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Loop-integrity cleanup refused; loop-review packet missing "
                f"{path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Loop-integrity cleanup refused; malformed loop-review artifact: "
                f"{path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _build_subject_manifest(
    subject: LoopIntegrityCleanupSubject,
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
        "source_synthesis_packet_dir": str(subject.source_synthesis_packet_dir),
        "source_synthesis_packet_artifact_id": subject.source_synthesis_artifact_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "current_best_candidate_kind": subject.current_best_candidate_kind,
        "current_best_candidate_packet_dir": str(subject.current_best_candidate_packet_dir),
        "proof_packet_id": subject.proof_packet_id,
        "proof_packet_dir": str(subject.proof_packet_dir),
        "reader_state_packet_id": subject.reader_state_packet_id,
        "reader_state_packet_dir": str(subject.reader_state_packet_dir),
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_adapter_id": subject.target_adapter_id,
        "target_scope": subject.target_scope,
        "operator_reviewed": True,
        "candidate_generated": False,
        "model_calls": 0,
        "next_generation_authorized": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "loop_integrity_cleanup_subject_manifest_v1_controller",
    }


def _build_loop_review_intake_summary(
    subject: LoopIntegrityCleanupSubject,
) -> dict[str, object]:
    packet = subject.payloads["evidence_loop_review_packet"]
    return {
        "loop_review_packet_consumed": True,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_adapter_id": subject.target_adapter_id,
        "target_scope": subject.target_scope,
        "loop_integrity_cleanup_required": (
            packet.get("loop_integrity_cleanup_required") is True
        ),
        "stale_recommendation_detected": (
            packet.get("stale_recommendation_detected") is True
        ),
        "next_generation_authorized": False,
        "ready_for_full_autonomous_loop_controller": False,
        "ready_for_supervised_next_cycle": False,
        "operator_reviewed": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "loop_review_intake_summary_v1_controller",
    }


def _build_active_evidence_state_checkpoint(
    subject: LoopIntegrityCleanupSubject,
) -> dict[str, object]:
    return {
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "current_best_candidate_kind": subject.current_best_candidate_kind,
        "current_best_candidate_packet_dir": str(subject.current_best_candidate_packet_dir),
        "proof_packet_id": subject.proof_packet_id,
        "proof_packet_dir": str(subject.proof_packet_dir),
        "reader_state_packet_id": subject.reader_state_packet_id,
        "reader_state_packet_dir": str(subject.reader_state_packet_dir),
        "synthesis_packet_id": subject.source_synthesis_packet_id,
        "synthesis_packet_dir": str(subject.source_synthesis_packet_dir),
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_adapter_id": subject.target_adapter_id,
        "target_scope": subject.target_scope,
        "current_best_candidate_finalization_eligible": False,
        "reader_state_transformation_strength": subject.reader_state_transformation_strength,
        "strongest_rival_still_blocks": subject.strongest_rival_still_blocks,
        "preferred_source_for_future_supervised_strategy_authorization": True,
        "candidate_generated": False,
        "model_calls": 0,
        "next_generation_authorized": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "active_evidence_state_checkpoint_v1_controller",
    }


def _build_stale_recommendation_registry(
    config: AbiConfig,
    subject: LoopIntegrityCleanupSubject,
) -> dict[str, object]:
    source_chain = _source_chain(subject.source_synthesis_payload)
    entries: list[dict[str, object]] = []
    if subject.prior_best_packet_id:
        entries.append(
            {
                "registry_id": "prior_object_event_candidate_superseded",
                "reference_packet_id": subject.prior_best_packet_id,
                "reference_type": "prior_best_candidate",
                "status": "superseded",
                "superseded_by_packet_id": subject.current_best_candidate_packet_id,
                "superseded_by_synthesis_packet_id": subject.source_synthesis_packet_id,
                "reuse_allowed_for_new_generation": False,
            }
        )
        prior_node = _candidate_graph_node(subject, subject.prior_best_packet_id)
        prior_proof_packet_id = _optional_text(prior_node.get("proof_packet_id"))
        if prior_proof_packet_id and prior_proof_packet_id != subject.proof_packet_id:
            entries.append(
                {
                    "registry_id": f"prior_proof_{prior_proof_packet_id}_historical",
                    "reference_packet_id": prior_proof_packet_id,
                    "reference_type": "prior_best_proof",
                    "status": "historical_proof_superseded_by_active_cycle",
                    "prior_best_candidate_packet_id": subject.prior_best_packet_id,
                    "superseded_by_proof_packet_id": subject.proof_packet_id,
                    "superseded_by_candidate_packet_id": (
                        subject.current_best_candidate_packet_id
                    ),
                    "reuse_allowed_for_new_generation": False,
                }
            )
        prior_reader_state_packet_id = _optional_text(
            prior_node.get("reader_state_packet_id")
        )
        if (
            prior_reader_state_packet_id
            and prior_reader_state_packet_id != subject.reader_state_packet_id
        ):
            entries.append(
                {
                    "registry_id": (
                        f"prior_reader_state_{prior_reader_state_packet_id}_historical"
                    ),
                    "reference_packet_id": prior_reader_state_packet_id,
                    "reference_type": "prior_best_reader_state",
                    "status": "historical_reader_state_superseded_by_active_cycle",
                    "prior_best_candidate_packet_id": subject.prior_best_packet_id,
                    "superseded_by_reader_state_packet_id": (
                        subject.reader_state_packet_id
                    ),
                    "superseded_by_candidate_packet_id": (
                        subject.current_best_candidate_packet_id
                    ),
                    "reuse_allowed_for_new_generation": False,
                }
            )
    for entry in _completed_cycle_stale_entries(subject):
        entries.append(entry)
    for proof_entry in _rejected_proof_attempt_entries(subject):
        entries.append(proof_entry)
    for reader_state_entry in _fixture_reader_state_stale_entries(config, subject):
        entries.append(reader_state_entry)
    synthesis_sources = [
        source
        for source in source_chain
        if source.get("packet_kind") == "autonomous_evidence_synthesis"
    ]
    for source in synthesis_sources:
        packet_id = str(source.get("packet_id") or "")
        if not packet_id or packet_id == subject.source_synthesis_packet_id:
            continue
        payload = _optional_packet_payload(
            source.get("packet_dir"),
            "autonomous_evidence_synthesis_packet.json",
        )
        next_action = str(payload.get("next_recommended_action") or "")
        entry_status = "superseded_by_active_checkpoint"
        if "reader_state" in next_action and subject.current_best_candidate_packet_id in next_action:
            entry_status = "stale_reader_state_recommendation_superseded"
        entries.append(
            {
                "registry_id": f"synthesis_{packet_id}_superseded",
                "reference_packet_id": packet_id,
                "reference_type": "older_autonomous_evidence_synthesis",
                "status": entry_status,
                "older_next_recommended_action": next_action or None,
                "superseded_by_packet_id": subject.source_synthesis_packet_id,
                "active_current_best_candidate_packet_id": (
                    subject.current_best_candidate_packet_id
                ),
                "reuse_allowed_for_new_generation": False,
            }
        )

    for strategy_dir in _packet_dirs(config.run_dir(subject.run_id) / "next_target_strategy"):
        packet_payload = _optional_packet_payload(
            strategy_dir,
            "next_target_strategy_packet.json",
        )
        entries.append(
            {
                "registry_id": f"next_target_strategy_{strategy_dir.name}_stale",
                "reference_packet_id": str(packet_payload.get("packet_id") or strategy_dir.name),
                "reference_type": "older_next_target_strategy",
                "status": "stale_after_current_best_supersession",
                "tied_to_prior_candidate_packet_id": subject.prior_best_packet_id or None,
                "superseded_by_packet_id": subject.current_best_candidate_packet_id,
                "reuse_allowed_for_new_generation": False,
            }
        )

    if subject.residual_authorization_packet_id:
        entries.append(
            {
                "registry_id": "residual_generation_authorization_consumed",
                "reference_packet_id": subject.residual_authorization_packet_id,
                "reference_type": "residual_generation_authorization",
                "status": "consumed_by_generated_candidate",
                "generated_candidate_packet_id": subject.current_best_candidate_packet_id,
                "reuse_allowed_for_new_generation": False,
            }
        )
    if subject.residual_work_order_packet_id:
        entries.append(
            {
                "registry_id": "residual_work_order_already_realized",
                "reference_packet_id": subject.residual_work_order_packet_id,
                "reference_type": "residual_work_order",
                "status": "already_produced_current_best_candidate",
                "generated_candidate_packet_id": subject.current_best_candidate_packet_id,
                "reuse_allowed_for_new_generation": False,
            }
        )

    return {
        "active_checkpoint_synthesis_packet_id": subject.source_synthesis_packet_id,
        "active_current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "stale_recommendations": entries,
        "stale_recommendation_count": len(entries),
        "older_packet_0059_object_event_path_superseded": (
            subject.prior_best_packet_id == "packet_0059"
            or bool(subject.prior_best_packet_id)
        ),
        "older_reader_state_eval_recommendations_superseded": True,
        "consumed_generation_authorization_not_reusable": bool(
            subject.residual_authorization_packet_id
        ),
        "residual_work_order_not_reusable": bool(subject.residual_work_order_packet_id),
        "candidate_generated": False,
        "model_calls": 0,
        "next_generation_authorized": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "stale_recommendation_registry_v1_controller",
    }


def _build_prior_cycle_supersession_map(
    subject: LoopIntegrityCleanupSubject,
) -> dict[str, object]:
    chain = _source_chain(subject.source_synthesis_payload)
    macro2 = _latest_candidate_for_scope(chain, "reader_state_informed_macro_2")
    object_event = _latest_candidate_for_scope(chain, "first_read_object_event_pressure_gap")
    residual = _latest_candidate_for_scope(chain, "object_motion_causality_specificity")
    cycles = [
        {
            "cycle_id": "macro_2_cycle",
            "led_to_candidate_packet_id": (macro2 or {}).get("packet_id"),
            "superseded_by_packet_id": (object_event or {}).get("packet_id")
            or subject.current_best_candidate_packet_id,
            "status": "superseded_but_preserved_as_prior_gain",
        },
        {
            "cycle_id": "object_event_cycle",
            "led_to_candidate_packet_id": (object_event or {}).get("packet_id")
            or subject.prior_best_packet_id,
            "superseded_by_packet_id": subject.current_best_candidate_packet_id,
            "status": "superseded_by_residual_object_motion_cycle",
        },
        {
            "cycle_id": "residual_object_motion_cycle",
            "led_to_candidate_packet_id": (residual or {}).get("packet_id")
            or subject.current_best_candidate_packet_id,
            "proof_packet_id": subject.proof_packet_id,
            "reader_state_packet_id": subject.reader_state_packet_id,
            "selected_residual_target_id": subject.selected_residual_target_id,
            "target_adapter_id": subject.target_adapter_id,
            "target_scope": subject.target_scope,
            "status": "current_best_non_final",
        },
    ]
    return {
        "cycles": cycles,
        "macro_2_cycle_led_to_packet_id": (macro2 or {}).get("packet_id"),
        "object_event_cycle_led_to_packet_id": (object_event or {}).get("packet_id")
        or subject.prior_best_packet_id,
        "residual_object_motion_cycle_led_to_packet_id": (
            (residual or {}).get("packet_id") or subject.current_best_candidate_packet_id
        ),
        "active_target_cycle_led_to_packet_id": subject.current_best_candidate_packet_id,
        "active_target_cycle_proof_packet_id": subject.proof_packet_id,
        "active_target_cycle_reader_state_packet_id": subject.reader_state_packet_id,
        "active_target_cycle_target_id": subject.selected_residual_target_id,
        "active_target_cycle_adapter_id": subject.target_adapter_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "superseded_prior_best_packet_id": subject.prior_best_packet_id,
        "current_best_supersedes_prior_best": bool(subject.prior_best_packet_id),
        "strongest_rival_defeated": False,
        "strongest_rival_still_blocks": subject.strongest_rival_still_blocks,
        "current_best_is_final": False,
        "candidate_generated": False,
        "model_calls": 0,
        "next_generation_authorized": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "prior_cycle_supersession_map_v1_controller",
    }


def _build_next_command_safety_policy(
    subject: LoopIntegrityCleanupSubject,
) -> dict[str, object]:
    return {
        "allowed_next_command_category": "supervised_strategy_authorization_after_cleanup",
        "disallowed_next_commands": [
            "generate candidate",
            "ablate",
            "reader-state-eval",
            "synthesize",
            "finalize",
            "authorize generation",
        ],
        "required_before_generation": [
            "supervised next-cycle authorization",
            "authorization-aware strategy planning from cleanup checkpoint or latest loop review",
            "narrow target selection if strategy requires it",
            "work order",
            "separate generation authorization",
        ],
        "recommended_next_command_after_cleanup": (
            ".\\.venv\\Scripts\\abi.exe autonomous authorize-next-cycle "
            f"--loop-cleanup-packet {subject.run_id}/loop_integrity_cleanup/<packet> "
            "--operator-reviewed --decision authorize_next_strategy_only"
        ),
        "loop_cleanup_packet_input_for_authorization_not_yet_wired": True,
        "candidate_generated": False,
        "model_calls": 0,
        "next_generation_authorized": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_command_safety_policy_v1_controller",
    }


def _build_generation_lock_report(
    subject: LoopIntegrityCleanupSubject,
) -> dict[str, object]:
    return {
        "next_generation_authorized": False,
        "previous_generation_authorization_consumed": bool(
            subject.residual_authorization_packet_id
        ),
        "consumed_generation_authorization_packet_id": (
            subject.residual_authorization_packet_id
        ),
        "current_best_candidate_has_complete_current_cycle_evidence": True,
        "generation_locked_until_supervised_strategy": True,
        "no_model_calls": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "generation_lock_report_v1_controller",
    }


def _build_supervised_strategy_readiness_report(
    subject: LoopIntegrityCleanupSubject,
    *,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        "ready_for_supervised_strategy_authorization": True,
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "next_allowed_operator_decision": "authorize_next_strategy_only",
        "recommended_next_command_after_cleanup": (
            ".\\.venv\\Scripts\\abi.exe autonomous authorize-next-cycle "
            f"--loop-cleanup-packet {packet_dir} --operator-reviewed "
            "--decision authorize_next_strategy_only"
        ),
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "strongest_rival_still_blocks": subject.strongest_rival_still_blocks,
        "strategy_only": True,
        "candidate_generation_requires_later_authorization": True,
        "candidate_generated": False,
        "model_calls": 0,
        "next_generation_authorized": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "supervised_strategy_readiness_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: LoopIntegrityCleanupSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gates = [
        _gate_result("loop_review_packet_consumed", True),
        _gate_result("source_synthesis_resolved", bool(subject.source_synthesis_packet_id)),
        _gate_result(
            "current_best_candidate_resolved",
            bool(subject.current_best_candidate_packet_id),
        ),
        _gate_result("proof_packet_linked", bool(subject.proof_packet_id)),
        _gate_result("reader_state_packet_linked", bool(subject.reader_state_packet_id)),
        _gate_result("active_evidence_state_checkpoint_created", True),
        _gate_result("stale_recommendation_registry_created", True),
        _gate_result("prior_cycle_supersession_map_created", True),
        _gate_result("next_command_safety_policy_created", True),
        _gate_result("generation_lock_recorded", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "next_generation_authorized",
            False,
            ["loop-integrity cleanup does not authorize generation"],
            record=False,
        ),
        _gate_result(
            "ready_for_full_autonomous_loop_controller",
            False,
            ["full autonomous loop controller remains unavailable"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["cleanup checkpoint is not finalization evidence"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_defeated",
            False,
            ["strongest rival remains blocking"],
            record=False,
        ),
        _gate_result(
            "human_validation_present",
            False,
            ["no human validation is present"],
            record=False,
        ),
    ]
    failed = [
        str(gate["gate_name"])
        for gate in gates
        if not bool(gate["passed"])
    ]
    blockers = [
        "next generation remains unauthorized",
        "full autonomous loop controller remains unavailable",
        "finalization remains ineligible",
        "strongest rival still blocks",
        "human validation is absent",
    ]
    return {
        "passed": False,
        "eligible": False,
        "loop_integrity_cleanup_completed": True,
        "ready_for_supervised_strategy_authorization": payloads[
            "supervised_strategy_readiness_report"
        ]["ready_for_supervised_strategy_authorization"],
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated": False,
        "strongest_rival_still_blocks": subject.strongest_rival_still_blocks,
        "human_validation_present": False,
        "gate_results": gates,
        "failed_gates": failed,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Loop-integrity cleanup checkpoint created; supervised strategy "
            "authorization may be considered, but generation, full autonomy, and "
            "finalization remain fail-closed."
        ),
        "worker": "loop_integrity_cleanup_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: LoopIntegrityCleanupSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="loop_integrity_cleanup_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "loop_integrity_cleanup_packet"],
        "counts": {
            **counts,
            "loop_integrity_cleanup_artifacts": counts["produced_artifacts"],
            "required_loop_integrity_cleanup_artifacts": counts["required_artifacts"],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.source_synthesis_packet_dir),
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "current_best_candidate_kind": subject.current_best_candidate_kind,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_adapter_id": subject.target_adapter_id,
        "target_scope": subject.target_scope,
        "loop_integrity_cleanup_completed": True,
        "next_generation_authorized": False,
        "ready_for_supervised_strategy_authorization": True,
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "candidate_generated": False,
        "model_calls": 0,
        "generation_lock_report": payloads["generation_lock_report"],
        "stale_recommendation_registry": payloads["stale_recommendation_registry"],
        "active_evidence_state_checkpoint": payloads[
            "active_evidence_state_checkpoint"
        ],
        "gate_report": payloads["loop_integrity_cleanup_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "next_recommended_action": "authorize_next_strategy_only_from_loop_cleanup",
        "worker": "loop_integrity_cleanup_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: LoopIntegrityCleanupSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["loop_integrity_cleanup_packet"]
    return {
        "accepted": True,
        "refused": False,
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
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_adapter_id": subject.target_adapter_id,
        "target_scope": subject.target_scope,
        "loop_integrity_cleanup_completed": True,
        "next_generation_authorized": False,
        "ready_for_supervised_strategy_authorization": True,
        "ready_for_supervised_candidate_generation": False,
        "ready_for_full_autonomous_loop_controller": False,
        "candidate_generated": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": "authorize_next_strategy_only_from_loop_cleanup",
        "gate_report": payloads["loop_integrity_cleanup_gate_report"],
    }


def _validate_no_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> None:
    offenders = []
    for artifact_type, payload in payloads.items():
        if (
            payload.get("finalization_eligible") is True
            or payload.get("phase_shift_claim") is True
            or payload.get("no_phase_shift_claim") is False
            or payload.get("candidate_final") is True
        ):
            offenders.append(artifact_type)
    if offenders:
        raise ValueError(
            "Loop-integrity cleanup refused; loop review contains finality or "
            f"phase-shift claim fields: {', '.join(offenders)}."
        )


def _validate_loop_review_does_not_authorize_generation(
    payloads: dict[str, dict[str, Any]]
) -> None:
    offenders = []
    for artifact_type, payload in payloads.items():
        if (
            payload.get("next_generation_authorized") is True
            or payload.get("immediate_creative_generation_authorized") is True
        ):
            offenders.append(artifact_type)
    if offenders:
        raise ValueError(
            "Loop-integrity cleanup refused; loop review authorizes generation "
            f"directly: {', '.join(offenders)}."
        )


def _validate_payload_no_final_or_phase_claim(payload: dict[str, Any], label: str) -> None:
    if (
        payload.get("finalization_eligible") is True
        or payload.get("candidate_final") is True
        or payload.get("phase_shift_claim") is True
        or payload.get("no_phase_shift_claim") is False
    ):
        raise ValueError(
            "Loop-integrity cleanup refused; "
            f"{label} contains finality or phase-shift claim fields."
        )


def _validate_packet_id_match(*, label: str, expected: str, actual: str) -> None:
    if expected != actual:
        raise ValueError(
            "Loop-integrity cleanup refused; "
            f"{label} mismatch: loop review has {actual}, source synthesis has "
            f"{expected}."
        )


def _validate_completed_cycle_alignment(
    *,
    payloads: dict[str, dict[str, Any]],
    source_synthesis_packet_id: str,
    current_best_packet_id: str,
    proof_packet_id: str,
    reader_state_packet_id: str,
) -> None:
    completed_cycle_map = payloads.get("completed_cycle_map", {})
    cycles = completed_cycle_map.get("cycles")
    if not isinstance(cycles, list):
        return
    matching_cycles = [
        cycle
        for cycle in cycles
        if isinstance(cycle, dict)
        and cycle.get("candidate_packet_id") == current_best_packet_id
    ]
    if not matching_cycles:
        raise ValueError(
            "Loop-integrity cleanup refused; completed cycle map does not include "
            f"current best candidate {current_best_packet_id}."
        )
    cycle = matching_cycles[-1]
    mismatches = []
    expected_pairs = {
        "source synthesis packet": (
            str(cycle.get("synthesis_packet_id") or ""),
            source_synthesis_packet_id,
        ),
        "proof packet": (str(cycle.get("proof_packet_id") or ""), proof_packet_id),
        "reader-state packet": (
            str(cycle.get("reader_state_packet_id") or ""),
            reader_state_packet_id,
        ),
    }
    for label, (cycle_value, actual) in expected_pairs.items():
        if cycle_value and cycle_value != actual:
            mismatches.append(f"{label} is {actual}, cycle map has {cycle_value}")
    if mismatches:
        raise ValueError(
            "Loop-integrity cleanup refused; completed cycle map mismatch: "
            + "; ".join(mismatches)
            + "."
        )


def _validate_current_cycle_packets(
    *,
    current_best: dict[str, Any],
    proof_payload: dict[str, Any],
    proof_packet_dir: Path,
    reader_state_payload: dict[str, Any],
    reader_state_packet_dir: Path,
    current_best_packet_id: str,
    proof_packet_id: str,
    reader_state_packet_id: str,
    selected_residual_target_id: str | None,
    target_adapter_id: str | None,
) -> None:
    _validate_payload_no_final_or_phase_claim(proof_payload, "proof packet")
    _validate_payload_no_final_or_phase_claim(reader_state_payload, "reader-state packet")
    if _packet_fixture_only(proof_packet_dir, "executed_ablation_packet.json"):
        raise ValueError(
            "Loop-integrity cleanup refused; proof packet is fixture-only and "
            "cannot anchor cleanup."
        )
    if _packet_fixture_only(
        reader_state_packet_dir,
        "internal_reader_state_eval_packet.json",
    ):
        raise ValueError(
            "Loop-integrity cleanup refused; reader-state packet is fixture-only "
            "and cannot anchor cleanup."
        )
    _validate_packet_id_match(
        label="proof source revision",
        expected=current_best_packet_id,
        actual=_required_text(
            proof_payload.get("source_revision_packet_id"),
            "proof packet missing source_revision_packet_id",
        ),
    )
    if proof_payload.get("source_revision_packet_kind") not in (
        None,
        "",
        current_best.get("packet_kind"),
        "bounded_macro_recomposition",
    ):
        raise ValueError(
            "Loop-integrity cleanup refused; proof packet source kind does not "
            "match current best candidate."
        )
    selected_reader_candidate = _required_text(
        reader_state_payload.get("selected_candidate_packet_id")
        or reader_state_payload.get("evaluated_candidate_packet_id"),
        "reader-state packet missing selected candidate packet ID",
    )
    _validate_packet_id_match(
        label="reader-state selected candidate",
        expected=current_best_packet_id,
        actual=selected_reader_candidate,
    )
    _validate_packet_id_match(
        label="reader-state proof packet",
        expected=proof_packet_id,
        actual=_required_text(
            reader_state_payload.get("proof_packet_id"),
            "reader-state packet missing proof_packet_id",
        ),
    )
    if reader_state_payload.get("packet_id") not in (None, "", reader_state_packet_id):
        _validate_packet_id_match(
            label="reader-state packet self ID",
            expected=reader_state_packet_id,
            actual=str(reader_state_payload.get("packet_id")),
        )
    requires_target_aware_proof = (
        current_best.get("proof_target_aware_ablation") is True
        or target_adapter_id == "tactile_inevitability"
    )
    if requires_target_aware_proof:
        if proof_payload.get("target_aware_ablation") is not True:
            raise ValueError(
                "Loop-integrity cleanup refused; target-aware current best requires "
                "target-aware proof, but proof is generic."
            )
        _validate_packet_id_match(
            label="target adapter",
            expected=target_adapter_id,
            actual=_required_text(
                proof_payload.get("target_adapter_id"),
                "proof packet missing target_adapter_id",
            ),
        )
        _validate_packet_id_match(
            label="selected residual target",
            expected=_required_text(
                selected_residual_target_id,
                "current best missing selected residual target",
            ),
            actual=_required_text(
                proof_payload.get("selected_residual_target_id"),
                "proof packet missing selected_residual_target_id",
            ),
        )
        if proof_payload.get("target_role_consistency_passed") is not True:
            raise ValueError(
                "Loop-integrity cleanup refused; target-aware proof failed target "
                "role consistency."
            )
        if proof_payload.get("comparison_internal_consistency") is not True:
            raise ValueError(
                "Loop-integrity cleanup refused; target-aware proof failed "
                "comparison internal consistency."
            )
    causal_status = proof_payload.get("selected_repair_causal_status")
    if causal_status not in ("useful_but_insufficient", "stronger_than_prior"):
        raise ValueError(
            "Loop-integrity cleanup refused; proof packet is not useful current "
            f"cycle evidence: {causal_status}."
        )


def _resolve_packet_dir(
    *,
    config: AbiConfig,
    run_id: str,
    family: str,
    packet_id: str,
    preferred: object,
) -> Path:
    candidates: list[Path] = []
    if isinstance(preferred, str) and preferred:
        candidates.append(_resolve_path(config, preferred))
    candidates.append(config.run_dir(run_id) / family / packet_id)
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[-1]


def _require_packet_file(
    packet_dir: Path,
    file_name: str,
    failure_label: str,
) -> dict[str, Any]:
    path = packet_dir / file_name
    if not path.exists():
        raise ValueError(f"Loop-integrity cleanup refused; {failure_label}: {packet_dir}.")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError(f"Loop-integrity cleanup refused; malformed packet: {path}.")
    return payload


def _optional_packet_payload(packet_dir: object, file_name: str) -> dict[str, Any]:
    if not isinstance(packet_dir, (str, Path)) or not str(packet_dir):
        return {}
    path = Path(packet_dir) / file_name
    if not path.exists():
        return {}
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    return payload if isinstance(payload, dict) else {}


def _packet_fixture_only(packet_dir: Path, file_name: str) -> bool:
    path = packet_dir / file_name
    if not path.exists():
        return False
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    return bool(
        isinstance(envelope, dict)
        and (
            envelope.get("fixture_only") is True
            or (isinstance(payload, dict) and payload.get("fixture_only") is True)
        )
    )


def _source_chain(source_synthesis_payload: dict[str, Any]) -> list[dict[str, Any]]:
    source_chain = source_synthesis_payload.get("source_chain")
    if not isinstance(source_chain, list):
        return []
    return [source for source in source_chain if isinstance(source, dict)]


def _latest_candidate_for_scope(
    source_chain: list[dict[str, Any]],
    scope: str,
) -> dict[str, Any] | None:
    candidates = [
        source
        for source in source_chain
        if source.get("packet_kind") == "bounded_macro_recomposition"
        and (
            source.get("target_scope") == scope
            or source.get("target_movement") == scope
            or source.get("selected_residual_target_id") == scope
        )
    ]
    return candidates[-1] if candidates else None


def _candidate_graph_node(
    subject: LoopIntegrityCleanupSubject,
    candidate_packet_id: str,
) -> dict[str, Any]:
    graph = _optional_packet_payload(
        subject.source_synthesis_packet_dir,
        "candidate_evidence_graph.json",
    )
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return {}
    for node in nodes:
        if isinstance(node, dict) and node.get("candidate_packet_id") == candidate_packet_id:
            return node
    return {}


def _completed_cycle_stale_entries(
    subject: LoopIntegrityCleanupSubject,
) -> list[dict[str, object]]:
    completed_cycle_map = subject.payloads.get("completed_cycle_map", {})
    cycles = completed_cycle_map.get("cycles")
    if not isinstance(cycles, list):
        return []
    entries: list[dict[str, object]] = []
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        candidate_packet_id = _optional_text(cycle.get("candidate_packet_id"))
        if not candidate_packet_id or candidate_packet_id == subject.current_best_candidate_packet_id:
            continue
        cycle_id = str(cycle.get("cycle_id") or candidate_packet_id)
        entries.append(
            {
                "registry_id": f"completed_cycle_{cycle_id}_historical",
                "reference_packet_id": candidate_packet_id,
                "reference_type": "historical_completed_cycle_candidate",
                "status": "historical_cycle_preserved_not_active",
                "proof_packet_id": _optional_text(cycle.get("proof_packet_id")),
                "reader_state_packet_id": _optional_text(
                    cycle.get("reader_state_packet_id")
                ),
                "synthesis_packet_id": _optional_text(cycle.get("synthesis_packet_id")),
                "superseded_by_candidate_packet_id": (
                    subject.current_best_candidate_packet_id
                ),
                "reuse_allowed_for_new_generation": False,
            }
        )
    return entries


def _rejected_proof_attempt_entries(
    subject: LoopIntegrityCleanupSubject,
) -> list[dict[str, object]]:
    rejected = subject.current_best_candidate.get("rejected_proof_candidates")
    if not isinstance(rejected, list):
        return []
    entries: list[dict[str, object]] = []
    for proof in rejected:
        if not isinstance(proof, dict):
            continue
        packet_id = _optional_text(proof.get("proof_packet_id"))
        if not packet_id or packet_id == subject.proof_packet_id:
            continue
        reasons = proof.get("rejection_reasons")
        entries.append(
            {
                "registry_id": f"proof_attempt_{packet_id}_non_authoritative",
                "reference_packet_id": packet_id,
                "reference_type": "non_authoritative_proof_attempt",
                "status": "rejected_for_active_target_or_quality",
                "rejection_reasons": reasons if isinstance(reasons, list) else [],
                "proof_fixture_only": proof.get("proof_fixture_only"),
                "proof_model_backed": proof.get("proof_model_backed"),
                "proof_target_aware_ablation": proof.get("proof_target_aware_ablation"),
                "proof_target_adapter_id": proof.get("proof_target_adapter_id"),
                "proof_selected_residual_target_id": proof.get(
                    "proof_selected_residual_target_id"
                ),
                "proof_target_role_consistency_passed": proof.get(
                    "proof_target_role_consistency_passed"
                ),
                "active_proof_packet_id": subject.proof_packet_id,
                "active_current_best_candidate_packet_id": (
                    subject.current_best_candidate_packet_id
                ),
                "reuse_allowed_for_new_generation": False,
            }
        )
    return entries


def _fixture_reader_state_stale_entries(
    config: AbiConfig,
    subject: LoopIntegrityCleanupSubject,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for packet_dir in _packet_dirs(
        config.run_dir(subject.run_id) / "internal_reader_state_evaluation"
    ):
        if packet_dir.name == subject.reader_state_packet_id:
            continue
        payload = _optional_packet_payload(
            packet_dir,
            "internal_reader_state_eval_packet.json",
        )
        selected = _optional_text(
            payload.get("selected_candidate_packet_id")
            or payload.get("evaluated_candidate_packet_id")
        )
        if selected != subject.current_best_candidate_packet_id:
            continue
        if not _packet_fixture_only(packet_dir, "internal_reader_state_eval_packet.json"):
            continue
        entries.append(
            {
                "registry_id": f"reader_state_{packet_dir.name}_fixture_not_selected",
                "reference_packet_id": packet_dir.name,
                "reference_type": "fixture_reader_state_attempt",
                "status": "fixture_only_reader_state_not_authoritative",
                "selected_candidate_packet_id": selected,
                "active_reader_state_packet_id": subject.reader_state_packet_id,
                "active_current_best_candidate_packet_id": (
                    subject.current_best_candidate_packet_id
                ),
                "reuse_allowed_for_new_generation": False,
            }
        )
    return entries


def _find_residual_work_order_id(run_dir: Path, current_best: dict[str, Any]) -> str | None:
    authorization_dir = current_best.get("source_authorization_packet_dir")
    if isinstance(authorization_dir, str) and authorization_dir:
        payload = _optional_packet_payload(
            Path(authorization_dir),
            "residual_generation_authorization_packet.json",
        )
        work_order_id = _optional_text(payload.get("source_work_order_packet_id"))
        if work_order_id:
            return work_order_id
        manifest = _optional_packet_payload(
            Path(authorization_dir),
            "residual_generation_authorization_subject_manifest.json",
        )
        work_order_id = _optional_text(manifest.get("source_work_order_packet_id"))
        if work_order_id:
            return work_order_id
    packet_dirs = _packet_dirs(run_dir / "residual_work_order")
    return packet_dirs[-1].name if packet_dirs else None


def _packet_dirs(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    return sorted(
        [child for child in base_dir.glob("packet_*") if child.is_dir()],
        key=lambda path: path.name,
    )


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


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(item, str)
    }


def _required_text(value: object, label: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"Loop-integrity cleanup refused; {label}.")
    return text


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


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
) -> LoopIntegrityCleanupResult:
    return LoopIntegrityCleanupResult(
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
            "source_loop_review_packet_id": None,
            "source_synthesis_packet_id": None,
            "current_best_candidate_packet_id": None,
            "proof_packet_id": None,
            "reader_state_packet_id": None,
            "loop_integrity_cleanup_completed": False,
            "next_generation_authorized": False,
            "ready_for_supervised_strategy_authorization": False,
            "ready_for_supervised_candidate_generation": False,
            "ready_for_full_autonomous_loop_controller": False,
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
