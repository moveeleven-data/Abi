"""Operator-reviewed checkpoint strategy direction packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_CHECKPOINT_STRATEGY_DIRECTION_REVIEW_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.residual_targets import (
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


CHECKPOINT_STRATEGY_DIRECTION_REVIEW_LINEAGE_ID = (
    "checkpoint_strategy_direction_review_v1"
)
CHECKPOINT_STRATEGY_DIRECTION_REVIEW_CREATED_BY = (
    "checkpoint_strategy_direction_review_v1_controller"
)

PROOF_NO_ANSWER_RESIDUE_DIRECTION_ID = "proof_no_answer_residue"
RIVAL_LEVEL_FIRST_READ_VIVIDNESS_DIRECTION_ID = "rival_level_first_read_vividness"

CHECKPOINT_STRATEGY_DIRECTION_REVIEW_ARTIFACT_TYPES = (
    "source_strategy_intake_summary",
    "source_checkpoint_intake_summary",
    "selected_checkpoint_direction_contract",
    "rejected_or_deferred_direction_options",
    "proof_no_answer_residue_rationale",
    "generation_lock_report",
    "next_step_readiness_report",
    "checkpoint_strategy_direction_gate_report",
    "checkpoint_strategy_direction_review_packet",
)

REQUIRED_STRATEGY_ARTIFACTS = (
    "next_target_strategy_subject_manifest",
    "residual_target_option_map",
    "next_intervention_strategy",
    "next_target_strategy_gate_report",
    "next_target_strategy_packet",
)

BLOCKED_FAILED_TARGET_DIRECTION_IDS = (
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
)
BLOCKED_HISTORY_TARGET_DIRECTION_IDS = (
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
)


@dataclass(frozen=True)
class CheckpointStrategyDirectionReviewResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class CheckpointStrategyDirectionReviewSubject:
    run_id: str
    strategy_packet_dir: Path
    strategy_packet_id: str
    strategy_packet_artifact_id: str | None
    strategy_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    selected_direction_id: str
    selected_direction_option: dict[str, Any] | None
    source_parent_ids: tuple[str, ...]


def run_checkpoint_strategy_direction_review(
    config: AbiConfig,
    *,
    strategy_packet: Path | str,
    direction: str,
    operator_reviewed: bool,
) -> CheckpointStrategyDirectionReviewResult:
    initialize_database(config)
    strategy_packet_dir = _resolve_path(config, strategy_packet)
    if not operator_reviewed:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            direction=direction,
            message=(
                "Checkpoint strategy direction review refused; "
                "--operator-reviewed is required."
            ),
        )
    if not strategy_packet_dir.exists() or not strategy_packet_dir.is_dir():
        return _refusal(
            strategy_packet=strategy_packet_dir,
            direction=direction,
            message=(
                "Checkpoint strategy direction review refused; strategy packet "
                f"directory not found: {strategy_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, strategy_packet_dir, direction)
    except ValueError as error:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            direction=direction,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                strategy_packet=strategy_packet_dir,
                direction=direction,
                message=(
                    "Checkpoint strategy direction review refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_CHECKPOINT_STRATEGY_DIRECTION_REVIEW_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "checkpoint_strategy_direction_review"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=CHECKPOINT_STRATEGY_DIRECTION_REVIEW_LINEAGE_ID,
            created_by=CHECKPOINT_STRATEGY_DIRECTION_REVIEW_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_strategy_intake_summary"] = (
            _build_source_strategy_intake_summary(subject, packet_dir)
        )
        artifacts["source_strategy_intake_summary"] = writer.write_artifact(
            "source_strategy_intake_summary",
            payloads["source_strategy_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["source_checkpoint_intake_summary"] = (
            _build_source_checkpoint_intake_summary(subject)
        )
        artifacts["source_checkpoint_intake_summary"] = writer.write_artifact(
            "source_checkpoint_intake_summary",
            payloads["source_checkpoint_intake_summary"],
            parent_ids=[
                artifacts["source_strategy_intake_summary"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["selected_checkpoint_direction_contract"] = (
            _build_selected_checkpoint_direction_contract(subject)
        )
        artifacts["selected_checkpoint_direction_contract"] = writer.write_artifact(
            "selected_checkpoint_direction_contract",
            payloads["selected_checkpoint_direction_contract"],
            parent_ids=[artifacts["source_checkpoint_intake_summary"].id],
        )

        payloads["rejected_or_deferred_direction_options"] = (
            _build_rejected_or_deferred_direction_options(subject)
        )
        artifacts["rejected_or_deferred_direction_options"] = writer.write_artifact(
            "rejected_or_deferred_direction_options",
            payloads["rejected_or_deferred_direction_options"],
            parent_ids=[artifacts["source_checkpoint_intake_summary"].id],
        )

        payloads["proof_no_answer_residue_rationale"] = (
            _build_proof_no_answer_residue_rationale(subject)
        )
        artifacts["proof_no_answer_residue_rationale"] = writer.write_artifact(
            "proof_no_answer_residue_rationale",
            payloads["proof_no_answer_residue_rationale"],
            parent_ids=[artifacts["selected_checkpoint_direction_contract"].id],
        )

        payloads["generation_lock_report"] = _build_generation_lock_report(subject)
        artifacts["generation_lock_report"] = writer.write_artifact(
            "generation_lock_report",
            payloads["generation_lock_report"],
            parent_ids=[artifacts["selected_checkpoint_direction_contract"].id],
        )

        payloads["next_step_readiness_report"] = _build_next_step_readiness_report(
            subject
        )
        artifacts["next_step_readiness_report"] = writer.write_artifact(
            "next_step_readiness_report",
            payloads["next_step_readiness_report"],
            parent_ids=[
                artifacts["selected_checkpoint_direction_contract"].id,
                artifacts["generation_lock_report"].id,
            ],
        )

        payloads["checkpoint_strategy_direction_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["checkpoint_strategy_direction_gate_report"] = writer.write_artifact(
            "checkpoint_strategy_direction_gate_report",
            payloads["checkpoint_strategy_direction_gate_report"],
            parent_ids=[
                artifacts["source_strategy_intake_summary"].id,
                artifacts["selected_checkpoint_direction_contract"].id,
                artifacts["generation_lock_report"].id,
            ],
        )

        payloads["checkpoint_strategy_direction_review_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["checkpoint_strategy_direction_review_packet"] = writer.write_artifact(
            "checkpoint_strategy_direction_review_packet",
            payloads["checkpoint_strategy_direction_review_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "checkpoint_strategy_direction_review_packet"
            ],
        )

        gate_report = payloads["checkpoint_strategy_direction_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="checkpoint_strategy_direction_review_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=CHECKPOINT_STRATEGY_DIRECTION_REVIEW_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return CheckpointStrategyDirectionReviewResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    strategy_packet_dir: Path,
    direction: str,
) -> CheckpointStrategyDirectionReviewSubject:
    payloads = _load_required_payloads(strategy_packet_dir)
    packet = payloads["next_target_strategy_packet"]
    residual_map = payloads["residual_target_option_map"]
    run_id = _required_string(
        packet.get("run_id"),
        "Checkpoint strategy direction review refused; strategy packet missing run_id.",
    )
    _validate_strategy_packet(payloads, direction=direction)
    strategy_packet_id = str(packet.get("packet_id") or strategy_packet_dir.name)
    packet_path = strategy_packet_dir / "next_target_strategy_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    strategy_artifact_ids = _artifact_ids_from_packet(packet)
    parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *strategy_artifact_ids.values(),
        ]
    )
    return CheckpointStrategyDirectionReviewSubject(
        run_id=run_id,
        strategy_packet_dir=strategy_packet_dir,
        strategy_packet_id=strategy_packet_id,
        strategy_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        strategy_artifact_ids=strategy_artifact_ids,
        payloads=payloads,
        selected_direction_id=direction,
        selected_direction_option=_find_option(
            residual_map.get("specific_residual_options", []),
            direction,
        ),
        source_parent_ids=tuple(parent_ids),
    )


def _validate_strategy_packet(
    payloads: dict[str, dict[str, Any]],
    *,
    direction: str,
) -> None:
    packet = payloads["next_target_strategy_packet"]
    residual_map = payloads["residual_target_option_map"]
    gate_report = payloads["next_target_strategy_gate_report"]
    intake = _as_dict(packet.get("architecture_checkpoint_intake"))
    if packet.get("architecture_checkpoint_reviewed") is not True:
        raise ValueError(
            "Checkpoint strategy direction review refused; strategy packet did "
            "not consume an architecture/evidence-risk checkpoint."
        )
    if packet.get("primary_next_target") != "checkpoint_review_required":
        raise ValueError(
            "Checkpoint strategy direction review refused; primary_next_target "
            "must be checkpoint_review_required."
        )
    if (
        packet.get("next_generation_authorized") is True
        or residual_map.get("next_generation_authorized") is True
        or gate_report.get("generation_locked_by_checkpoint") is not True
    ):
        raise ValueError(
            "Checkpoint strategy direction review refused; strategy packet "
            "authorizes generation or is not checkpoint-locked."
        )
    if packet.get("candidate_generated") is True or _int_or_zero(
        _as_dict(packet.get("counts")).get("candidate_artifacts_created")
    ):
        raise ValueError(
            "Checkpoint strategy direction review refused; strategy packet "
            "already generated a candidate."
        )
    if packet.get("finalization_eligible") is True or packet.get(
        "no_phase_shift_claim"
    ) is not True:
        raise ValueError(
            "Checkpoint strategy direction review refused; strategy packet has "
            "a finality or phase-shift claim."
        )
    if intake.get("target_adapter_contract_audit_passed") is not True or _int_or_zero(
        intake.get("target_adapter_contract_blocker_count")
    ):
        raise ValueError(
            "Checkpoint strategy direction review refused; checkpoint adapter "
            "contract audit is not passing."
        )
    if _int_or_zero(intake.get("hardcoded_packet_id_unacceptable_count")):
        raise ValueError(
            "Checkpoint strategy direction review refused; checkpoint hardcode "
            "blockers are nonzero."
        )
    plausible = _plausible_direction_ids(residual_map)
    if direction not in plausible and _find_option(
        residual_map.get("specific_residual_options", []),
        direction,
    ) is None:
        raise ValueError(
            "Checkpoint strategy direction review refused; selected direction "
            f"is not a checkpoint plausible direction: {direction}"
        )
    if direction in BLOCKED_FAILED_TARGET_DIRECTION_IDS:
        raise ValueError(
            "Checkpoint strategy direction review refused; selected direction "
            f"is paused/exhausted and cannot be reviewed for immediate pursuit: {direction}"
        )
    if direction in _failed_target_ids(payloads):
        raise ValueError(
            "Checkpoint strategy direction review refused; selected direction "
            f"is paused/exhausted by failed-target memory: {direction}"
        )
    option = _find_option(residual_map.get("specific_residual_options", []), direction)
    if option is not None and _option_is_paused_or_exhausted(option):
        raise ValueError(
            "Checkpoint strategy direction review refused; selected direction "
            f"is paused/exhausted: {direction}"
        )
    if direction in BLOCKED_HISTORY_TARGET_DIRECTION_IDS:
        raise ValueError(
            "Checkpoint strategy direction review refused; selected direction "
            "is a history/current-best-path target requiring explicit future "
            f"override: {direction}"
        )
    if direction == RIVAL_LEVEL_FIRST_READ_VIVIDNESS_DIRECTION_ID:
        raise ValueError(
            "Checkpoint strategy direction review refused; rival-level "
            "first-read vividness requires a narrower mechanism first."
        )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_STRATEGY_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Checkpoint strategy direction review refused; strategy packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Checkpoint strategy direction review refused; malformed "
                f"strategy artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _build_source_strategy_intake_summary(
    subject: CheckpointStrategyDirectionReviewSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "source_strategy_packet_artifact_id": subject.strategy_packet_artifact_id,
        "strategy_packet_checkpoint_aware": True,
        "primary_next_target": packet.get("primary_next_target"),
        "primary_next_subtarget": packet.get("primary_next_subtarget"),
        "checkpoint_plausible_direction_ids": _plausible_direction_ids(residual_map),
        "available_residual_target_ids": packet.get("available_residual_target_ids", []),
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "source_architecture_checkpoint_packet_id": packet.get(
            "architecture_checkpoint_packet_id"
        ),
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "source_strategy_intake_summary_v1_controller",
    }


def _build_source_checkpoint_intake_summary(
    subject: CheckpointStrategyDirectionReviewSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    intake = _as_dict(packet.get("architecture_checkpoint_intake"))
    return {
        "source_architecture_checkpoint_packet_id": packet.get(
            "architecture_checkpoint_packet_id"
        ),
        "source_architecture_checkpoint_packet_dir": packet.get(
            "architecture_checkpoint_packet_dir"
        ),
        "checkpoint_reviewed": intake.get("architecture_checkpoint_reviewed") is True,
        "generation_locked_by_checkpoint": intake.get(
            "generation_locked_by_checkpoint"
        )
        is True,
        "target_adapter_contract_audit_passed": intake.get(
            "target_adapter_contract_audit_passed"
        )
        is True,
        "target_adapter_contract_blocker_count": intake.get(
            "target_adapter_contract_blocker_count",
            0,
        ),
        "target_adapter_contract_warning_count": intake.get(
            "target_adapter_contract_warning_count",
            0,
        ),
        "hardcoded_packet_id_unacceptable_count": intake.get(
            "hardcoded_packet_id_unacceptable_count",
            0,
        ),
        "failed_local_residual_generation_targets": intake.get(
            "failed_local_residual_generation_targets",
            [],
        ),
        "unresolved_creative_blocker_count": intake.get(
            "unresolved_creative_blocker_count",
            0,
        ),
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "source_checkpoint_intake_summary_v1_controller",
    }


def _build_selected_checkpoint_direction_contract(
    subject: CheckpointStrategyDirectionReviewSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    direction_id = subject.selected_direction_id
    return {
        "direction_id": direction_id,
        "selected_checkpoint_direction_id": direction_id,
        "direction_kind": "checkpoint_plausible_direction",
        "selected_direction_status": "operator_reviewed_checkpoint_direction",
        "strategic_reason": _direction_reason(direction_id),
        "intended_next_development_step": _next_development_step(direction_id),
        "next_recommended_action": _next_recommended_action(direction_id),
        "not_residual_target_selection": True,
        "not_work_order": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "does_not_claim_improvement": True,
        "does_not_change_current_best": True,
        "operator_reviewed_direction_choice_only": True,
        "forbidden_immediate_actions": [
            "generation",
            "ablation",
            "reader-state evaluation",
            "finalization",
            "hostile scaffold retry",
            "ending return retry",
            "object motion repeat",
            "tactile repeat",
            "rival imitation",
            "generic vividness",
        ],
        "protected_effects": [
            f"{packet.get('current_best_candidate_packet_id')} current best",
            f"proof packet {packet.get('proof_packet_id')} support",
            f"reader-state packet {packet.get('reader_state_packet_id')} support",
            "object/tactile gains already integrated",
            "failed hostile scaffold memory",
            "failed ending-return memory",
            "strongest-rival pressure remains unresolved",
            "finalization remains refused",
        ],
        "residual_target_selected": False,
        "work_order_created": False,
        "next_generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "selected_checkpoint_direction_contract_v1_controller",
    }


def _build_rejected_or_deferred_direction_options(
    subject: CheckpointStrategyDirectionReviewSubject,
) -> dict[str, object]:
    residual_map = subject.payloads["residual_target_option_map"]
    options = residual_map.get("specific_residual_options", [])
    rows = []
    for direction_id in _all_direction_ids(residual_map):
        if direction_id == subject.selected_direction_id:
            status = "selected_for_operator_review"
            reason = "operator selected this checkpoint direction"
        else:
            status, reason = _deferred_status_for_direction(direction_id, options)
        rows.append(
            {
                "direction_id": direction_id,
                "status": status,
                "reason": reason,
                "candidate_generation_authorized": False,
            }
        )
    return {
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "direction_options": rows,
        "residual_target_selected": False,
        "work_order_created": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "rejected_or_deferred_direction_options_v1_controller",
    }


def _build_proof_no_answer_residue_rationale(
    subject: CheckpointStrategyDirectionReviewSubject,
) -> dict[str, object]:
    selected = subject.selected_direction_id == PROOF_NO_ANSWER_RESIDUE_DIRECTION_ID
    return {
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "proof_no_answer_residue_selected": selected,
        "strategic_reason": (
            "proof/no-answer pressure remains partial_or_unresolved"
            if selected
            else _direction_reason(subject.selected_direction_id)
        ),
        "why_not_failed_local_targets": (
            "hostile scaffold and ending-return generation paths are paused/"
            "exhausted and remain diagnostic-only."
        ),
        "why_not_rival_level_vividness": (
            "rival-level vividness is too broad before a narrower mechanism is "
            "defined."
        ),
        "next_development_step": _next_development_step(subject.selected_direction_id),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "proof_no_answer_residue_rationale_v1_controller",
    }


def _build_generation_lock_report(
    subject: CheckpointStrategyDirectionReviewSubject,
) -> dict[str, object]:
    return {
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_evaluation_authorized": False,
        "live_model_call_authorized": False,
        "model_calls": 0,
        "generation_requires_future_first_class_target_planning": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "checkpoint_strategy_generation_lock_report_v1_controller",
    }


def _build_next_step_readiness_report(
    subject: CheckpointStrategyDirectionReviewSubject,
) -> dict[str, object]:
    return {
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "ready_for_generation": False,
        "ready_for_residual_target_selection": False,
        "ready_for_work_order": False,
        "ready_for_next_target_planning": True,
        "next_recommended_action": _next_recommended_action(
            subject.selected_direction_id
        ),
        "requires_future_registry_support": subject.selected_direction_id
        == PROOF_NO_ANSWER_RESIDUE_DIRECTION_ID,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "checkpoint_strategy_next_step_readiness_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: CheckpointStrategyDirectionReviewSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    lock = payloads["generation_lock_report"]
    gate_results = [
        _gate_result("strategy_packet_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("checkpoint_direction_valid", True),
        _gate_result("checkpoint_adapter_contract_audit_passing", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "generation_authorized",
            False,
            ["direction review does not authorize generation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["checkpoint direction review is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "residual target has not been selected",
        "work order has not been created",
        "generation remains unauthorized",
        "candidate has not been generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        "passed": False,
        "eligible": False,
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "selected_direction_status": "operator_reviewed_checkpoint_direction",
        "generation_authorized": lock["generation_authorized"],
        "next_generation_authorized": lock["next_generation_authorized"],
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Operator reviewed the checkpoint-aware strategy and selected a "
            "strategic direction only; generation remains locked."
        ),
        "worker": "checkpoint_strategy_direction_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: CheckpointStrategyDirectionReviewSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=CHECKPOINT_STRATEGY_DIRECTION_REVIEW_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="checkpoint_strategy_direction_review_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "checkpoint_strategy_direction_review_packet"],
        "counts": {
            **artifact_counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 0,
            "residual_target_selection_artifacts_created": 0,
        },
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_architecture_checkpoint_packet_id": packet.get(
            "architecture_checkpoint_packet_id"
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "selected_checkpoint_direction_id": subject.selected_direction_id,
        "selected_direction_status": "operator_reviewed_checkpoint_direction",
        "not_residual_target_selection": True,
        "not_work_order": True,
        "does_not_authorize_generation": True,
        "does_not_claim_improvement": True,
        "does_not_change_current_best": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "next_recommended_action": _next_recommended_action(
            subject.selected_direction_id
        ),
        "gate_report": payloads["checkpoint_strategy_direction_gate_report"],
        "worker": "checkpoint_strategy_direction_review_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: CheckpointStrategyDirectionReviewSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["checkpoint_strategy_direction_review_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _direction_reason(direction_id: str) -> str:
    if direction_id == PROOF_NO_ANSWER_RESIDUE_DIRECTION_ID:
        return "proof/no-answer pressure remains partial_or_unresolved"
    return f"{direction_id} remains a checkpoint-plausible direction"


def _next_development_step(direction_id: str) -> str:
    if direction_id == PROOF_NO_ANSWER_RESIDUE_DIRECTION_ID:
        return "implement first-class residual target planning for proof_no_answer_residue"
    return f"review {direction_id} before target registry support"


def _next_recommended_action(direction_id: str) -> str:
    if direction_id == PROOF_NO_ANSWER_RESIDUE_DIRECTION_ID:
        return "implement_proof_no_answer_residue_target_planning"
    return f"review_{direction_id}_direction_before_target_registry_support"


def _deferred_status_for_direction(
    direction_id: str,
    options: object,
) -> tuple[str, str]:
    option = _find_option(options, direction_id)
    if direction_id in BLOCKED_FAILED_TARGET_DIRECTION_IDS or (
        option is not None and _option_is_paused_or_exhausted(option)
    ):
        return (
            "rejected_paused_or_exhausted",
            "failed local generation path remains diagnostic-only",
        )
    if direction_id in BLOCKED_HISTORY_TARGET_DIRECTION_IDS:
        return (
            "deferred_history_current_best_path",
            "history/current-best path target requires explicit future override",
        )
    if direction_id == RIVAL_LEVEL_FIRST_READ_VIVIDNESS_DIRECTION_ID:
        return (
            "deferred_requires_narrower_mechanism",
            "rival-level vividness is too broad before narrower mechanism planning",
        )
    return ("deferred_not_selected", "operator selected a different direction")


def _all_direction_ids(residual_map: dict[str, Any]) -> list[str]:
    ids = [*_plausible_direction_ids(residual_map)]
    options = residual_map.get("specific_residual_options")
    if isinstance(options, list):
        ids.extend(
            str(option.get("option_id"))
            for option in options
            if isinstance(option, dict) and option.get("option_id")
        )
    return _unique(ids)


def _plausible_direction_ids(residual_map: dict[str, Any]) -> list[str]:
    value = residual_map.get("checkpoint_plausible_direction_ids")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _failed_target_ids(payloads: dict[str, dict[str, Any]]) -> set[str]:
    packet = payloads["next_target_strategy_packet"]
    residual_map = payloads["residual_target_option_map"]
    intake = _as_dict(packet.get("architecture_checkpoint_intake"))
    failed_ids = set()
    for source in (
        intake.get("failed_local_residual_generation_targets"),
        residual_map.get("failed_target_status_map"),
        packet.get("failed_target_status_map"),
    ):
        if isinstance(source, list):
            failed_ids.update(str(item) for item in source if item)
        elif isinstance(source, dict):
            failed_ids.update(str(key) for key in source)
    return failed_ids


def _find_option(options: object, option_id: str) -> dict[str, Any] | None:
    if not isinstance(options, list):
        return None
    for option in options:
        if isinstance(option, dict) and option.get("option_id") == option_id:
            return option
    return None


def _option_is_paused_or_exhausted(option: dict[str, Any]) -> bool:
    status = str(option.get("status") or "")
    return (
        "paused" in status
        or "exhausted" in status
        or option.get("stop_test_triggered") is True
        or option.get("generation_retry_recommended") is False
        and option.get("failed_packet_ids")
    )


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


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config.root / candidate


def _refusal(
    *,
    strategy_packet: Path,
    direction: str,
    message: str,
) -> CheckpointStrategyDirectionReviewResult:
    return CheckpointStrategyDirectionReviewResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "strategy_packet": str(strategy_packet),
            "selected_checkpoint_direction_id": direction,
            "candidate_generated": False,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "residual_target_selected": False,
            "work_order_created": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return 0


def _unique(values: list[str | None]) -> list[str]:
    seen = set()
    unique_values = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
