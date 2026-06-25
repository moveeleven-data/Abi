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
from abi.modules.loop_integrity_cleanup import LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES
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

REQUIRED_LOOP_CLEANUP_ARTIFACTS = LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES

KNOWN_RESIDUAL_RUN_ID = "run_8fa54199f23f3d8e"
KNOWN_LOOP_CLEANUP_PACKET_ID = "packet_0002"
KNOWN_CURRENT_BEST_PACKET_ID = "packet_0061"
KNOWN_PROOF_PACKET_ID = "packet_0023"
KNOWN_READER_STATE_PACKET_ID = "packet_0011"
KNOWN_SOURCE_SYNTHESIS_PACKET_ID = "packet_0026"
KNOWN_LOOP_REVIEW_PACKET_ID = "packet_0006"


@dataclass(frozen=True)
class SupervisedCycleAuthorizationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SupervisedCycleAuthorizationSubject:
    run_id: str
    source_kind: str
    loop_review_packet_dir: Path
    loop_review_packet_id: str
    loop_review_packet_artifact_id: str | None
    loop_review_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    loop_cleanup_packet_dir: Path | None
    loop_cleanup_packet_id: str | None
    loop_cleanup_packet_artifact_id: str | None
    loop_cleanup_artifact_ids: dict[str, str]
    loop_cleanup_payloads: dict[str, dict[str, Any]]
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
    loop_review_packet: Path | str | None = None,
    loop_cleanup_packet: Path | str | None = None,
    operator_reviewed: bool,
    decision: str | None,
) -> SupervisedCycleAuthorizationResult:
    initialize_database(config)
    if (loop_review_packet is None) == (loop_cleanup_packet is None):
        return _refusal(
            loop_review_packet=_resolve_path(config, loop_review_packet)
            if loop_review_packet is not None
            else None,
            loop_cleanup_packet=_resolve_path(config, loop_cleanup_packet)
            if loop_cleanup_packet is not None
            else None,
            message=(
                "Supervised cycle authorization refused; pass exactly one of "
                "--loop-review-packet or --loop-cleanup-packet."
            ),
        )

    source_packet_dir = _resolve_path(
        config,
        loop_cleanup_packet if loop_cleanup_packet is not None else loop_review_packet,
    )
    if not operator_reviewed:
        return _refusal(
            loop_review_packet=_resolve_path(config, loop_review_packet)
            if loop_review_packet is not None
            else None,
            loop_cleanup_packet=_resolve_path(config, loop_cleanup_packet)
            if loop_cleanup_packet is not None
            else None,
            message=(
                "Supervised cycle authorization refused; --operator-reviewed is "
                "required."
            ),
        )
    if decision not in SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS:
        return _refusal(
            loop_review_packet=_resolve_path(config, loop_review_packet)
            if loop_review_packet is not None
            else None,
            loop_cleanup_packet=_resolve_path(config, loop_cleanup_packet)
            if loop_cleanup_packet is not None
            else None,
            message=(
                "Supervised cycle authorization refused; --decision must be one "
                f"of: {', '.join(SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS)}."
            ),
        )
    if loop_cleanup_packet is not None and decision != "authorize_next_strategy_only":
        return _refusal(
            loop_cleanup_packet=source_packet_dir,
            message=(
                "Supervised cycle authorization refused; cleanup-aware "
                "authorization only supports --decision authorize_next_strategy_only."
            ),
        )
    if not source_packet_dir.exists() or not source_packet_dir.is_dir():
        packet_label = "loop-cleanup" if loop_cleanup_packet is not None else "loop-review"
        return _refusal(
            loop_review_packet=source_packet_dir if loop_review_packet is not None else None,
            loop_cleanup_packet=source_packet_dir if loop_cleanup_packet is not None else None,
            message=(
                f"Supervised cycle authorization refused; {packet_label} packet "
                f"directory not found: {source_packet_dir}"
            ),
        )

    try:
        if loop_cleanup_packet is not None:
            subject = _load_cleanup_subject(config, source_packet_dir)
        else:
            subject = _load_loop_review_subject(config, source_packet_dir)
    except ValueError as error:
        return _refusal(
            loop_review_packet=source_packet_dir if loop_review_packet is not None else None,
            loop_cleanup_packet=source_packet_dir if loop_cleanup_packet is not None else None,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                loop_review_packet=subject.loop_review_packet_dir
                if loop_review_packet is not None
                else None,
                loop_cleanup_packet=subject.loop_cleanup_packet_dir,
                message=(
                    "Supervised cycle authorization refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )
        if subject.loop_cleanup_packet_id is not None:
            duplicate = _accepted_authorization_for_cleanup(connection, subject)
            if duplicate is not None:
                return _refusal(
                    loop_cleanup_packet=subject.loop_cleanup_packet_dir,
                    message=(
                        "Supervised cycle authorization refused; cleanup packet "
                        "already has an accepted strategy authorization linked to it: "
                        f"{duplicate.id}"
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


def _load_loop_review_subject(
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
        source_kind="loop_review",
        loop_review_packet_dir=loop_review_packet_dir,
        loop_review_packet_id=str(loop_packet.get("packet_id") or loop_review_packet_dir.name),
        loop_review_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        loop_review_artifact_ids=loop_artifact_ids,
        payloads=payloads,
        loop_cleanup_packet_dir=None,
        loop_cleanup_packet_id=None,
        loop_cleanup_packet_artifact_id=None,
        loop_cleanup_artifact_ids={},
        loop_cleanup_payloads={},
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


def _load_cleanup_subject(
    config: AbiConfig,
    loop_cleanup_packet_dir: Path,
) -> SupervisedCycleAuthorizationSubject:
    cleanup_payloads = _load_cleanup_payloads(loop_cleanup_packet_dir)
    cleanup_packet = cleanup_payloads["loop_integrity_cleanup_packet"]
    checkpoint = cleanup_payloads["active_evidence_state_checkpoint"]
    readiness = cleanup_payloads["supervised_strategy_readiness_report"]
    run_id = cleanup_packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Supervised cycle authorization refused; cleanup packet missing run_id.")

    _validate_cleanup_readiness(cleanup_payloads)

    current_best_packet_id = _required_text(
        cleanup_packet.get("current_best_candidate_packet_id")
        or checkpoint.get("current_best_candidate_packet_id"),
        "cleanup packet missing current best candidate packet ID",
    )
    proof_packet_id = _required_text(
        cleanup_packet.get("proof_packet_id") or checkpoint.get("proof_packet_id"),
        "cleanup packet missing proof packet ID",
    )
    reader_state_packet_id = _required_text(
        cleanup_packet.get("reader_state_packet_id")
        or checkpoint.get("reader_state_packet_id"),
        "cleanup packet missing reader-state packet ID",
    )
    source_synthesis_packet_id = _required_text(
        cleanup_packet.get("source_synthesis_packet_id")
        or checkpoint.get("synthesis_packet_id"),
        "cleanup packet missing source synthesis packet ID",
    )
    loop_review_packet_id = _required_text(
        cleanup_packet.get("source_loop_review_packet_id")
        or checkpoint.get("loop_review_packet_id"),
        "cleanup packet missing source loop-review packet ID",
    )
    cleanup_packet_id = str(cleanup_packet.get("packet_id") or loop_cleanup_packet_dir.name)

    if run_id == KNOWN_RESIDUAL_RUN_ID:
        expected = {
            "cleanup packet": (cleanup_packet_id, KNOWN_LOOP_CLEANUP_PACKET_ID),
            "current best candidate": (
                current_best_packet_id,
                KNOWN_CURRENT_BEST_PACKET_ID,
            ),
            "proof packet": (proof_packet_id, KNOWN_PROOF_PACKET_ID),
            "reader-state packet": (reader_state_packet_id, KNOWN_READER_STATE_PACKET_ID),
            "source synthesis packet": (
                source_synthesis_packet_id,
                KNOWN_SOURCE_SYNTHESIS_PACKET_ID,
            ),
            "source loop-review packet": (
                loop_review_packet_id,
                KNOWN_LOOP_REVIEW_PACKET_ID,
            ),
        }
        mismatches = [
            f"{label} is {actual}, expected {expected_value}"
            for label, (actual, expected_value) in expected.items()
            if actual != expected_value
        ]
        if mismatches:
            raise ValueError(
                "Supervised cycle authorization refused; cleanup checkpoint "
                f"does not match the authoritative residual state: {'; '.join(mismatches)}."
            )

    current_best_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="bounded_macro_recomposition",
        packet_id=current_best_packet_id,
        preferred=checkpoint.get("current_best_candidate_packet_dir"),
    )
    _require_packet_file(
        current_best_packet_dir,
        "macro_recomposition_packet.json",
        "current best candidate cannot be resolved",
    )
    proof_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="executed_ablation",
        packet_id=proof_packet_id,
        preferred=checkpoint.get("proof_packet_dir"),
    )
    _require_packet_file(
        proof_packet_dir,
        "executed_ablation_packet.json",
        "proof packet cannot be resolved",
    )
    reader_state_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="internal_reader_state_evaluation",
        packet_id=reader_state_packet_id,
        preferred=checkpoint.get("reader_state_packet_dir"),
    )
    _require_packet_file(
        reader_state_packet_dir,
        "internal_reader_state_eval_packet.json",
        "reader-state packet cannot be resolved",
    )
    source_synthesis_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="autonomous_evidence_synthesis",
        packet_id=source_synthesis_packet_id,
        preferred=(
            cleanup_packet.get("source_synthesis_packet_dir")
            or checkpoint.get("synthesis_packet_dir")
        ),
    )
    _require_packet_file(
        source_synthesis_packet_dir,
        "autonomous_evidence_synthesis_packet.json",
        "source synthesis cannot be resolved",
    )
    loop_review_packet_dir = _resolve_packet_dir(
        config=config,
        run_id=run_id,
        family="evidence_loop_review",
        packet_id=loop_review_packet_id,
        preferred=(
            cleanup_packet.get("source_loop_review_packet_dir")
            or checkpoint.get("loop_review_packet_dir")
        ),
    )
    loop_payloads = _load_required_payloads(loop_review_packet_dir)
    loop_packet = loop_payloads["evidence_loop_review_packet"]
    loop_manifest = loop_payloads["evidence_loop_review_subject_manifest"]
    if str(loop_packet.get("packet_id") or loop_review_packet_dir.name) != loop_review_packet_id:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup source loop-review "
            "packet does not match loaded loop-review packet."
        )
    _validate_cleanup_chain_matches_loop_review(
        cleanup_current_best=current_best_packet_id,
        cleanup_proof=proof_packet_id,
        cleanup_reader=reader_state_packet_id,
        cleanup_synthesis=source_synthesis_packet_id,
        loop_packet=loop_packet,
        loop_manifest=loop_manifest,
    )
    later_cleanup = _later_cleanup_for_same_chain(
        config,
        run_id=run_id,
        cleanup_packet_id=cleanup_packet_id,
        loop_review_packet_id=loop_review_packet_id,
        current_best_packet_id=current_best_packet_id,
    )
    if later_cleanup is not None:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup packet is stale. "
            f"Use the later cleanup checkpoint: {later_cleanup}."
        )

    cleanup_path = loop_cleanup_packet_dir / "loop_integrity_cleanup_packet.json"
    loop_path = loop_review_packet_dir / "evidence_loop_review_packet.json"
    with connect(config.db_path) as connection:
        cleanup_artifact = _artifact_for_path(connection, cleanup_path)
        loop_artifact = _artifact_for_path(connection, loop_path)
    cleanup_artifact_ids = _artifact_ids_from_packet(cleanup_packet)
    loop_artifact_ids = _artifact_ids_from_packet(loop_packet)
    parent_ids = _unique(
        [
            cleanup_artifact.id if cleanup_artifact else None,
            loop_artifact.id if loop_artifact else None,
            *cleanup_artifact_ids.values(),
            *loop_artifact_ids.values(),
        ]
    )
    return SupervisedCycleAuthorizationSubject(
        run_id=run_id,
        source_kind="loop_cleanup",
        loop_review_packet_dir=loop_review_packet_dir,
        loop_review_packet_id=loop_review_packet_id,
        loop_review_packet_artifact_id=loop_artifact.id if loop_artifact else None,
        loop_review_artifact_ids=loop_artifact_ids,
        payloads=loop_payloads,
        loop_cleanup_packet_dir=loop_cleanup_packet_dir,
        loop_cleanup_packet_id=cleanup_packet_id,
        loop_cleanup_packet_artifact_id=cleanup_artifact.id if cleanup_artifact else None,
        loop_cleanup_artifact_ids=cleanup_artifact_ids,
        loop_cleanup_payloads=cleanup_payloads,
        current_best_candidate_packet_id=current_best_packet_id,
        current_best_candidate_packet_dir=str(current_best_packet_dir),
        proof_packet_id=proof_packet_id,
        proof_packet_dir=str(proof_packet_dir),
        reader_state_packet_id=reader_state_packet_id,
        reader_state_packet_dir=str(reader_state_packet_dir),
        source_synthesis_packet_id=source_synthesis_packet_id,
        source_synthesis_packet_dir=str(source_synthesis_packet_dir),
        completed_cycles=int(
            loop_packet.get("completed_cycle_count")
            or loop_packet.get("completed_cycles")
            or 0
        ),
        strongest_rival_still_blocks=bool(
            cleanup_packet.get("strongest_rival_still_blocks")
            or checkpoint.get("strongest_rival_still_blocks")
            or readiness.get("strongest_rival_still_blocks")
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


def _load_cleanup_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_LOOP_CLEANUP_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Supervised cycle authorization refused; loop-cleanup packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Supervised cycle authorization refused; malformed loop-cleanup "
                f"artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_cleanup_readiness(payloads: dict[str, dict[str, Any]]) -> None:
    cleanup_packet = payloads["loop_integrity_cleanup_packet"]
    readiness = payloads["supervised_strategy_readiness_report"]
    generation_lock = payloads["generation_lock_report"]
    checkpoint = payloads["active_evidence_state_checkpoint"]
    safety = payloads["next_command_safety_policy"]
    if cleanup_packet.get("loop_integrity_cleanup_completed") is not True:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup checkpoint is not completed."
        )
    if cleanup_packet.get("ready_for_supervised_strategy_authorization") is not True:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup checkpoint is not "
            "ready for supervised strategy authorization."
        )
    if readiness.get("ready_for_supervised_strategy_authorization") is not True:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup readiness report "
            "does not authorize supervised strategy."
        )
    if (
        cleanup_packet.get("ready_for_supervised_candidate_generation") is True
        or readiness.get("ready_for_supervised_candidate_generation") is True
    ):
        raise ValueError(
            "Supervised cycle authorization refused; cleanup checkpoint claims "
            "candidate generation readiness."
        )
    if (
        cleanup_packet.get("next_generation_authorized") is True
        or generation_lock.get("next_generation_authorized") is True
        or safety.get("next_generation_authorized") is True
    ):
        raise ValueError(
            "Supervised cycle authorization refused; cleanup checkpoint authorizes "
            "generation directly."
        )
    if generation_lock.get("generation_locked_until_supervised_strategy") is not True:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup generation lock is absent."
        )
    _validate_no_final_or_phase_claim(payloads)
    for artifact_type, payload in (
        ("active_evidence_state_checkpoint", checkpoint),
        ("loop_integrity_cleanup_packet", cleanup_packet),
    ):
        if payload.get("current_best_candidate_finalization_eligible") is True:
            raise ValueError(
                "Supervised cycle authorization refused; cleanup claims finality "
                f"in {artifact_type}."
            )


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
            "Supervised cycle authorization refused; source contains finality or "
            f"phase-shift claim fields: {', '.join(offenders)}."
        )


def _validate_cleanup_chain_matches_loop_review(
    *,
    cleanup_current_best: str,
    cleanup_proof: str,
    cleanup_reader: str,
    cleanup_synthesis: str,
    loop_packet: dict[str, Any],
    loop_manifest: dict[str, Any],
) -> None:
    expected = {
        "current best candidate": (
            cleanup_current_best,
            _first_string(
                loop_packet.get("current_best_candidate_packet_id"),
                loop_manifest.get("current_best_candidate_packet_id"),
            ),
        ),
        "proof packet": (
            cleanup_proof,
            _first_string(loop_packet.get("proof_packet_id"), loop_manifest.get("proof_packet_id")),
        ),
        "reader-state packet": (
            cleanup_reader,
            _first_string(
                loop_packet.get("reader_state_packet_id"),
                loop_manifest.get("reader_state_packet_id"),
            ),
        ),
        "source synthesis packet": (
            cleanup_synthesis,
            _first_string(
                loop_packet.get("source_synthesis_packet_id"),
                loop_manifest.get("source_synthesis_packet_id"),
            ),
        ),
    }
    mismatches = [
        f"{label} is {actual}, loop review has {expected_value}"
        for label, (actual, expected_value) in expected.items()
        if expected_value and actual != expected_value
    ]
    if mismatches:
        raise ValueError(
            "Supervised cycle authorization refused; cleanup checkpoint does not "
            f"match source loop-review state: {'; '.join(mismatches)}."
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
        raise ValueError(f"Supervised cycle authorization refused; {failure_label}: {packet_dir}.")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError(f"Supervised cycle authorization refused; malformed packet: {path}.")
    return payload


def _later_cleanup_for_same_chain(
    config: AbiConfig,
    *,
    run_id: str,
    cleanup_packet_id: str,
    loop_review_packet_id: str,
    current_best_packet_id: str,
) -> Path | None:
    base_dir = config.run_dir(run_id) / "loop_integrity_cleanup"
    if not base_dir.exists():
        return None
    packet_dirs = sorted(
        [child for child in base_dir.glob("packet_*") if child.is_dir()],
        key=lambda path: path.name,
    )
    for packet_dir in reversed(packet_dirs):
        if packet_dir.name <= cleanup_packet_id:
            continue
        path = packet_dir / "loop_integrity_cleanup_packet.json"
        if not path.exists():
            continue
        envelope = read_json_file(path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("source_loop_review_packet_id") == loop_review_packet_id
            and payload.get("current_best_candidate_packet_id") == current_best_packet_id
        ):
            return packet_dir
    return None


def _build_subject_manifest(
    subject: SupervisedCycleAuthorizationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_kind": subject.source_kind,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "source_loop_cleanup_packet_artifact_id": subject.loop_cleanup_packet_artifact_id,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "loop_review_packet_artifact_id": subject.loop_review_packet_artifact_id,
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
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
        "source_kind": subject.source_kind,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "loop_review_accepted": packet.get("accepted", True) is not False,
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
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
        "source_kind": subject.source_kind,
        "reviewed_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "reviewed_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
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
    cleanup_packet = subject.loop_cleanup_payloads.get("loop_integrity_cleanup_packet", {})
    readiness = subject.loop_cleanup_payloads.get(
        "supervised_strategy_readiness_report",
        {},
    )
    generation_lock = subject.loop_cleanup_payloads.get("generation_lock_report", {})
    artifact_count_consistent = counts.get("artifact_count_consistent") is True
    stale_present = "stale_recommendation_detected" in packet
    stale_currently_false = packet.get("stale_recommendation_detected") is False
    output_shape_stable = bool(counts.get("model_calls") == 0 and packet.get("packet_id"))
    cleanup_checkpoint_consumed = subject.loop_cleanup_packet_id is not None
    explicit_cleanup_ready = (
        cleanup_checkpoint_consumed
        and cleanup_packet.get("loop_integrity_cleanup_completed") is True
        and cleanup_packet.get("ready_for_supervised_strategy_authorization") is True
        and cleanup_packet.get("ready_for_supervised_candidate_generation") is not True
        and cleanup_packet.get("next_generation_authorized") is not True
        and readiness.get("ready_for_supervised_strategy_authorization") is True
        and generation_lock.get("next_generation_authorized") is not True
    )
    fresh_cleanup_passed = bool(
        explicit_cleanup_ready
        if cleanup_checkpoint_consumed
        else artifact_count_consistent
        and stale_present
        and stale_currently_false
        and output_shape_stable
    )
    return {
        "source_kind": subject.source_kind,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "cleanup_checkpoint_consumed": cleanup_checkpoint_consumed,
        "explicit_cleanup_readiness_used": cleanup_checkpoint_consumed,
        "loop_integrity_cleanup_completed": cleanup_packet.get(
            "loop_integrity_cleanup_completed"
        )
        if cleanup_checkpoint_consumed
        else False,
        "cleanup_ready_for_supervised_strategy_authorization": readiness.get(
            "ready_for_supervised_strategy_authorization"
        )
        if cleanup_checkpoint_consumed
        else None,
        "cleanup_ready_for_supervised_candidate_generation": readiness.get(
            "ready_for_supervised_candidate_generation"
        )
        if cleanup_checkpoint_consumed
        else None,
        "cleanup_next_generation_authorized": generation_lock.get(
            "next_generation_authorized"
        )
        if cleanup_checkpoint_consumed
        else None,
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
        _gate_result(
            "loop_cleanup_packet_consumed",
            subject.loop_cleanup_packet_id is not None,
            []
            if subject.loop_cleanup_packet_id is not None
            else ["cleanup checkpoint was not supplied; legacy loop-review path used"],
            record=False,
        ),
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
        "source_kind": subject.source_kind,
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
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "source_synthesis_packet_dir": subject.source_synthesis_packet_dir,
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
        "next_recommended_action": (
            "plan_next_target_from_cleanup_authorization"
            if subject.loop_cleanup_packet_id is not None
            else "prepare_next_residual_target_strategy_under_supervision"
        ),
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
        "source_kind": subject.source_kind,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
        "counts": packet["counts"],
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "source_synthesis_packet_dir": subject.source_synthesis_packet_dir,
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


def _accepted_authorization_for_cleanup(
    connection: sqlite3.Connection,
    subject: SupervisedCycleAuthorizationSubject,
) -> ArtifactRecord | None:
    if subject.loop_cleanup_packet_id is None:
        return None
    rows = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE run_id = ?
          AND type = 'supervised_cycle_authorization_packet'
        ORDER BY created_at DESC
        """,
        (subject.run_id,),
    ).fetchall()
    for row in rows:
        artifact = row_to_artifact(row)
        path = Path(artifact.path)
        if not path.exists():
            continue
        envelope = read_json_file(path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("source_loop_cleanup_packet_id") == subject.loop_cleanup_packet_id
            and payload.get("next_strategy_authorized") is True
        ):
            return artifact
    return None


def _artifact_ids_from_packet(packet_payload: dict[str, Any]) -> dict[str, str]:
    artifact_ids = packet_payload.get("artifact_ids")
    if not isinstance(artifact_ids, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in artifact_ids.items()
        if isinstance(value, str)
    }


def _required_text(value: object, label: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Supervised cycle authorization refused; {label}.")


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


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
    loop_review_packet: Path | None = None,
    loop_cleanup_packet: Path | None = None,
    message: str,
) -> SupervisedCycleAuthorizationResult:
    return SupervisedCycleAuthorizationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "loop_review_packet": str(loop_review_packet) if loop_review_packet else None,
            "loop_cleanup_packet": str(loop_cleanup_packet)
            if loop_cleanup_packet
            else None,
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
