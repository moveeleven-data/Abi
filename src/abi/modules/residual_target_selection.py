"""Controller-owned narrow residual target selection packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_RESIDUAL_TARGET_SELECTION_ACTIVE_PHASE,
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
from abi.modules.residual_targets import (
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    REPEATED_BROAD_TARGET_ID,
    ResidualTargetSpec,
    TACTILE_INEVITABILITY_TARGET_ID,
    get_residual_target_spec,
)


RESIDUAL_TARGET_SELECTION_LINEAGE_ID = "residual_target_selection_v1"
RESIDUAL_TARGET_SELECTION_CREATED_BY = "residual_target_selection_v1_controller"

RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES = (
    "residual_target_selection_subject_manifest",
    "strategy_packet_intake_summary",
    "available_residual_options_report",
    "operator_residual_target_choice",
    "selected_residual_target_contract",
    "protected_effects_and_forbidden_changes",
    "next_work_order_scope",
    "residual_target_selection_gate_report",
    "residual_target_selection_packet",
)

REQUIRED_STRATEGY_ARTIFACTS = (
    "next_target_strategy_subject_manifest",
    "source_evidence_summary",
    "current_best_candidate_summary",
    "reader_state_blocker_summary",
    "strongest_rival_pressure_delta",
    "protected_effects_and_forbidden_changes",
    "object_event_pressure_target_map",
    "residual_target_option_map",
    "candidate_region_pressure_map",
    "next_intervention_strategy",
    "ablation_and_reader_eval_plan",
    "next_target_strategy_gate_report",
    "next_target_strategy_packet",
)

NEXT_ALLOWED_ACTION = "prepare_object_motion_causality_specificity_work_order"
CHECKPOINT_STALE_BLOCKED_TARGET_IDS = (
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
)


@dataclass(frozen=True)
class ResidualTargetSelectionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class ResidualTargetSelectionSubject:
    run_id: str
    strategy_packet_dir: Path
    strategy_packet_id: str
    strategy_packet_artifact_id: str | None
    strategy_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    selected_target_id: str
    selected_option: dict[str, Any]
    target_spec: ResidualTargetSpec
    source_parent_ids: tuple[str, ...]


def run_residual_target_selection(
    config: AbiConfig,
    *,
    strategy_packet: Path | str,
    target: str,
    operator_reviewed: bool,
) -> ResidualTargetSelectionResult:
    initialize_database(config)
    strategy_packet_dir = _resolve_path(config, strategy_packet)
    if not operator_reviewed:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            target=target,
            message=(
                "Residual target selection refused; --operator-reviewed is "
                "required."
            ),
        )
    if not strategy_packet_dir.exists() or not strategy_packet_dir.is_dir():
        return _refusal(
            strategy_packet=strategy_packet_dir,
            target=target,
            message=(
                "Residual target selection refused; strategy packet directory "
                f"not found: {strategy_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, strategy_packet_dir, target)
    except ValueError as error:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            target=target,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                strategy_packet=strategy_packet_dir,
                target=target,
                message=(
                    "Residual target selection refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_RESIDUAL_TARGET_SELECTION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "residual_target_selection"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=RESIDUAL_TARGET_SELECTION_LINEAGE_ID,
            created_by=RESIDUAL_TARGET_SELECTION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["residual_target_selection_subject_manifest"] = (
            _build_subject_manifest(subject, packet_dir)
        )
        artifacts["residual_target_selection_subject_manifest"] = writer.write_artifact(
            "residual_target_selection_subject_manifest",
            payloads["residual_target_selection_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["strategy_packet_intake_summary"] = _build_strategy_intake_summary(
            subject
        )
        artifacts["strategy_packet_intake_summary"] = writer.write_artifact(
            "strategy_packet_intake_summary",
            payloads["strategy_packet_intake_summary"],
            parent_ids=[
                artifacts["residual_target_selection_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["available_residual_options_report"] = (
            _build_available_residual_options_report(subject)
        )
        artifacts["available_residual_options_report"] = writer.write_artifact(
            "available_residual_options_report",
            payloads["available_residual_options_report"],
            parent_ids=[artifacts["strategy_packet_intake_summary"].id],
        )

        payloads["operator_residual_target_choice"] = (
            _build_operator_residual_target_choice(subject)
        )
        artifacts["operator_residual_target_choice"] = writer.write_artifact(
            "operator_residual_target_choice",
            payloads["operator_residual_target_choice"],
            parent_ids=[artifacts["available_residual_options_report"].id],
        )

        payloads["selected_residual_target_contract"] = (
            _build_selected_residual_target_contract(subject)
        )
        artifacts["selected_residual_target_contract"] = writer.write_artifact(
            "selected_residual_target_contract",
            payloads["selected_residual_target_contract"],
            parent_ids=[artifacts["operator_residual_target_choice"].id],
        )

        payloads["protected_effects_and_forbidden_changes"] = (
            _build_protected_effects_and_forbidden_changes(subject)
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["selected_residual_target_contract"].id,
                artifacts["strategy_packet_intake_summary"].id,
            ],
        )

        payloads["next_work_order_scope"] = _build_next_work_order_scope(subject)
        artifacts["next_work_order_scope"] = writer.write_artifact(
            "next_work_order_scope",
            payloads["next_work_order_scope"],
            parent_ids=[
                artifacts["selected_residual_target_contract"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["residual_target_selection_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["residual_target_selection_gate_report"] = writer.write_artifact(
            "residual_target_selection_gate_report",
            payloads["residual_target_selection_gate_report"],
            parent_ids=[
                artifacts["strategy_packet_intake_summary"].id,
                artifacts["operator_residual_target_choice"].id,
                artifacts["next_work_order_scope"].id,
            ],
        )

        payloads["residual_target_selection_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["residual_target_selection_packet"] = writer.write_artifact(
            "residual_target_selection_packet",
            payloads["residual_target_selection_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "residual_target_selection_packet"
            ],
        )

        gate_report = payloads["residual_target_selection_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="residual_target_selection_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=RESIDUAL_TARGET_SELECTION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return ResidualTargetSelectionResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    strategy_packet_dir: Path,
    target: str,
) -> ResidualTargetSelectionSubject:
    payloads = _load_required_payloads(strategy_packet_dir)
    packet = payloads["next_target_strategy_packet"]
    run_id = packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Residual target selection refused; strategy packet missing run_id.")
    _validate_current_best_consistency(payloads)
    strategy_packet_id = str(packet.get("packet_id") or strategy_packet_dir.name)
    if _strategy_marked_stale_by_latest_cleanup(config, run_id, strategy_packet_id):
        raise ValueError(
            "Residual target selection refused; strategy packet is marked stale "
            "by the latest loop-integrity cleanup checkpoint."
        )
    checkpoint_stale_status = _checkpoint_stale_target_for_selection(
        config,
        strategy_packet_dir,
        payloads,
        run_id=run_id,
        target=target,
    )
    if checkpoint_stale_status:
        raise ValueError(
            "Residual target selection refused; strategy packet predates the "
            "latest architecture/evidence-risk checkpoint for this target: "
            f"{target}."
        )
    residual_map = payloads["residual_target_option_map"]
    options = residual_map.get("specific_residual_options")
    if not isinstance(options, list):
        raise ValueError(
            "Residual target selection refused; strategy packet has no residual options."
        )
    failed_status = _failed_target_status_for_selection(
        config,
        strategy_packet_dir,
        payloads,
        run_id=run_id,
        target=target,
    )
    if failed_status:
        raise ValueError(
            "Residual target selection refused; "
            f"{target} is paused/exhausted by failed-target adjudication "
            "or the strategy packet is stale relative to that adjudication."
        )
    selected_option = _find_option(options, target)
    if selected_option is None:
        raise ValueError(
            "Residual target selection refused; selected target is not an "
            f"available residual option: {target}"
        )
    target_spec = get_residual_target_spec(target)
    if target_spec is None:
        raise ValueError(
            "Residual target selection refused; selected target is unsupported "
            f"by the residual target registry: {target}"
        )
    if selected_option.get("status") != "available_for_operator_selection":
        raise ValueError(
            "Residual target selection refused; selected target is not "
            f"available for operator selection: {target}"
        )

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
    return ResidualTargetSelectionSubject(
        run_id=run_id,
        strategy_packet_dir=strategy_packet_dir,
        strategy_packet_id=strategy_packet_id,
        strategy_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        strategy_artifact_ids=strategy_artifact_ids,
        payloads=payloads,
        selected_target_id=target,
        selected_option=selected_option,
        target_spec=target_spec,
        source_parent_ids=tuple(parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_STRATEGY_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Residual target selection refused; strategy packet missing "
                f"{path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Residual target selection refused; malformed strategy artifact: "
                f"{path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _strategy_marked_stale_by_latest_cleanup(
    config: AbiConfig,
    run_id: str,
    strategy_packet_id: str,
) -> bool:
    base_dir = config.run_dir(run_id) / "loop_integrity_cleanup"
    if not base_dir.exists():
        return False
    cleanup_dirs = sorted(
        [child for child in base_dir.glob("packet_*") if child.is_dir()],
        key=lambda path: path.name,
    )
    for cleanup_dir in reversed(cleanup_dirs):
        registry_path = cleanup_dir / "stale_recommendation_registry.json"
        if not registry_path.exists():
            continue
        envelope = read_json_file(registry_path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        stale_entries = payload.get("stale_recommendations")
        if not isinstance(stale_entries, list):
            continue
        for entry in stale_entries:
            if not isinstance(entry, dict):
                continue
            if (
                entry.get("reference_type") == "older_next_target_strategy"
                and entry.get("reference_packet_id") == strategy_packet_id
                and entry.get("reuse_allowed_for_new_generation") is False
            ):
                return True
        return False
    return False


def _checkpoint_stale_target_for_selection(
    config: AbiConfig,
    strategy_packet_dir: Path,
    payloads: dict[str, dict[str, Any]],
    *,
    run_id: str,
    target: str,
) -> dict[str, Any]:
    del strategy_packet_dir
    if target not in CHECKPOINT_STALE_BLOCKED_TARGET_IDS:
        return {}
    latest_checkpoint = _latest_architecture_checkpoint(config, run_id)
    if latest_checkpoint is None:
        return {}
    latest_payload = _read_checkpoint_packet(latest_checkpoint)
    latest_checkpoint_id = _first_string(
        latest_payload.get("packet_id"),
        latest_checkpoint.name,
    )
    packet = payloads["next_target_strategy_packet"]
    manifest = payloads["next_target_strategy_subject_manifest"]
    residual_map = payloads["residual_target_option_map"]
    strategy_checkpoint_id = _first_string(
        packet.get("architecture_checkpoint_packet_id"),
        manifest.get("architecture_checkpoint_packet_id"),
        residual_map.get("architecture_checkpoint_packet_id"),
    )
    if strategy_checkpoint_id and strategy_checkpoint_id == latest_checkpoint_id:
        return {}
    return {
        "target_id": target,
        "latest_architecture_checkpoint_packet_id": latest_checkpoint_id,
        "latest_architecture_checkpoint_packet_dir": str(latest_checkpoint),
        "strategy_checkpoint_packet_id": strategy_checkpoint_id,
        "strategy_packet_predates_architecture_checkpoint": True,
    }


def _latest_architecture_checkpoint(config: AbiConfig, run_id: str) -> Path | None:
    base_dir = config.run_dir(run_id) / "architecture_evidence_risk_checkpoint"
    if not base_dir.exists():
        return None
    packet_dirs = sorted(
        [child for child in base_dir.glob("packet_*") if child.is_dir()],
        key=lambda path: path.name,
    )
    for packet_dir in reversed(packet_dirs):
        if (packet_dir / "architecture_evidence_risk_checkpoint_packet.json").exists():
            return packet_dir
    return None


def _read_checkpoint_packet(packet_dir: Path) -> dict[str, Any]:
    path = packet_dir / "architecture_evidence_risk_checkpoint_packet.json"
    if not path.exists():
        return {}
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    return payload if isinstance(payload, dict) else {}


def _failed_target_status_for_selection(
    config: AbiConfig,
    strategy_packet_dir: Path,
    payloads: dict[str, dict[str, Any]],
    *,
    run_id: str,
    target: str,
) -> dict[str, Any]:
    if target != HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return {}
    residual_map = payloads["residual_target_option_map"]
    status_map = residual_map.get("failed_target_status_map")
    if isinstance(status_map, dict):
        status = _as_dict(status_map.get(target))
        if _is_failed_target_unavailable(status):
            return status

    synthesis_dir = _source_synthesis_dir_for_strategy(
        config,
        strategy_packet_dir,
        payloads,
        run_id=run_id,
    )
    if synthesis_dir is None:
        return {}
    return _hostile_failed_status_from_synthesis_dir(synthesis_dir)


def _source_synthesis_dir_for_strategy(
    config: AbiConfig,
    strategy_packet_dir: Path,
    payloads: dict[str, dict[str, Any]],
    *,
    run_id: str,
) -> Path | None:
    packet = payloads["next_target_strategy_packet"]
    manifest = payloads["next_target_strategy_subject_manifest"]
    source_dir = _first_string(
        packet.get("source_synthesis_packet_dir"),
        manifest.get("source_synthesis_packet_dir"),
    )
    if source_dir:
        return _resolve_path(config, source_dir)
    source_id = _first_string(
        packet.get("source_synthesis_packet_id"),
        manifest.get("source_synthesis_packet_id"),
    )
    if source_id:
        return config.run_dir(run_id) / "autonomous_evidence_synthesis" / source_id
    return strategy_packet_dir.parent.parent / "autonomous_evidence_synthesis"


def _hostile_failed_status_from_synthesis_dir(synthesis_dir: Path) -> dict[str, Any]:
    for artifact_type in (
        "failed_or_rejected_repairs",
        "residual_blocker_map",
        "strategic_decision_report",
        "autonomous_evidence_synthesis_packet",
    ):
        path = synthesis_dir / f"{artifact_type}.json"
        if not path.exists():
            continue
        envelope = read_json_file(path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        status = _extract_hostile_failed_status(payload)
        if _is_failed_target_unavailable(status):
            return status
    return {}


def _extract_hostile_failed_status(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(payload.get("hostile_scaffold_failed_generation_path"))
    target_id = _first_string(
        summary.get("target_id"),
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
        if summary.get("attempted") is True
        else "",
    )
    status = _first_string(
        summary.get("target_status"),
        payload.get("hostile_scaffold_visibility_target_status"),
    )
    if target_id != HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID and not status:
        return {}
    return {
        "target_id": HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        "target_status": status,
        "failed_attempt_count": summary.get(
            "failed_attempt_count",
            payload.get("hostile_scaffold_failed_attempt_count"),
        ),
        "failed_packet_ids": summary.get("attempt_packet_ids", []),
        "stop_test_triggered": bool(
            summary.get("stop_test_triggered")
            or payload.get("hostile_scaffold_stop_test_triggered")
        ),
        "no_accepted_hostile_scaffold_candidate_exists": summary.get(
            "no_accepted_hostile_scaffold_candidate_exists"
        ),
        "next_allowed_status": summary.get("next_allowed_status"),
        "generation_retry_recommended": summary.get("generation_retry_recommended"),
    }


def _is_failed_target_unavailable(status: dict[str, Any]) -> bool:
    if not status:
        return False
    target_status = str(status.get("target_status") or "")
    unavailable_markers = (
        "paused",
        "exhausted",
        "failed_stop_test",
        "unavailable_due_to_failed_generation_path",
    )
    failed_packet_ids = status.get("failed_packet_ids")
    has_failed_packets = isinstance(failed_packet_ids, list) and bool(failed_packet_ids)
    has_failed_attempts = _int_or_zero(status.get("failed_attempt_count")) > 0
    marker_present = any(marker in target_status for marker in unavailable_markers)
    if (
        not has_failed_packets
        and not has_failed_attempts
        and status.get("stop_test_triggered") is not True
        and not marker_present
    ):
        return False
    return (
        marker_present
        or status.get("stop_test_triggered") is True
        or status.get("no_accepted_hostile_scaffold_candidate_exists") is True
    )


def _build_subject_manifest(
    subject: ResidualTargetSelectionSubject,
    packet_dir: Path,
) -> dict[str, object]:
    strategy_packet = subject.payloads["next_target_strategy_packet"]
    stale_report = _stale_current_best_reference_report(subject)
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "source_strategy_packet_artifact_id": subject.strategy_packet_artifact_id,
        "current_best_candidate_packet_id": strategy_packet.get(
            "current_best_candidate_packet_id"
        ),
        "proof_packet_id": strategy_packet.get("proof_packet_id"),
        "reader_state_packet_id": strategy_packet.get("reader_state_packet_id"),
        "source_synthesis_packet_id": strategy_packet.get("source_synthesis_packet_id"),
        "loop_review_packet_id": strategy_packet.get("loop_review_packet_id"),
        "authorization_packet_id": strategy_packet.get("authorization_packet_id"),
        "selected_residual_target_id": subject.selected_target_id,
        **stale_report,
        "broad_blocker_class": _broad_blocker_class(subject),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "residual_target_selection_subject_manifest_v1_controller",
    }


def _build_strategy_intake_summary(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    stale_report = _stale_current_best_reference_report(subject)
    return {
        "strategy_packet_consumed": True,
        "strategy_packet_id": subject.strategy_packet_id,
        "strategy_packet_dir": str(subject.strategy_packet_dir),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "loop_review_packet_id": packet.get("loop_review_packet_id"),
        "authorization_packet_id": packet.get("authorization_packet_id"),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "repeated_target_id": packet.get("repeated_target_id")
        or residual_map.get("repeated_target_id"),
        "primary_next_target": packet.get("primary_next_target"),
        "primary_next_subtarget": packet.get("primary_next_subtarget"),
        **stale_report,
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "next_generation_authorized": packet.get("next_generation_authorized") is True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "strategy_packet_intake_summary_v1_controller",
    }


def _build_available_residual_options_report(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    residual_map = subject.payloads["residual_target_option_map"]
    options = residual_map.get("specific_residual_options", [])
    return {
        "residual_options_loaded": True,
        "broad_blocker_class": _broad_blocker_class(subject),
        "option_count": len(options) if isinstance(options, list) else 0,
        "available_option_ids": [
            str(option.get("option_id"))
            for option in options
            if isinstance(option, dict)
            and option.get("status") == "available_for_operator_selection"
        ],
        "selected_residual_target_id": subject.selected_target_id,
        "selected_target_valid": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "available_residual_options_report_v1_controller",
    }


def _build_operator_residual_target_choice(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    return {
        "operator_reviewed": True,
        "selected_residual_target_id": subject.selected_target_id,
        "operator_selection_reason": _operator_selection_reason(subject),
        "broad_blocker_class": _broad_blocker_class(subject),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "selected_target_is_narrower_than_repeated_broad_target": (
            _selected_target_is_narrower_than_repeated_broad_target(subject)
        ),
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "not_final_operator_approval": True,
        "not_human_validation": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "operator_residual_target_choice_v1_controller",
    }


def _build_selected_residual_target_contract(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    current_best_id = subject.payloads["next_target_strategy_packet"].get(
        "current_best_candidate_packet_id"
    )
    stale_report = _stale_current_best_reference_report(subject)
    return {
        "selected_residual_target_id": subject.selected_target_id,
        **stale_report,
        "target_definition": subject.target_spec.target_definition,
        "operational_definition": [
            item.replace("current-best", str(current_best_id))
            for item in subject.target_spec.operational_definition
        ],
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "work_order_adapter": subject.target_spec.work_order_adapter,
        "required_evidence_inputs": list(subject.target_spec.required_evidence_inputs),
        "forbidden_under_this_target": list(
            subject.target_spec.forbidden_under_this_target
        ),
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "selected_residual_target_contract_v1_controller",
    }


def _build_protected_effects_and_forbidden_changes(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    stale_report = _stale_current_best_reference_report(subject)
    return {
        "protected_effects": [
            f"{packet.get('current_best_candidate_packet_id')} as current best candidate",
            f"executed ablation support from {packet.get('proof_packet_id')}",
            f"reader-state support from {packet.get('reader_state_packet_id')}",
            *subject.target_spec.protected_effects,
        ],
        "forbidden_changes": list(subject.target_spec.forbidden_changes),
        **stale_report,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_next_work_order_scope(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    stale_report = _stale_current_best_reference_report(subject)
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "next_allowed_action": subject.target_spec.canonical_next_action,
        "work_order_review_action": subject.target_spec.review_action,
        "work_order_adapter": subject.target_spec.work_order_adapter,
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "requires_separate_generation_authorization": True,
        "future_generation_requires_separate_authorization": (
            subject.target_spec.generation_requires_separate_authorization
        ),
        **stale_report,
        "next_strategy_or_work_order_authorized": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_work_order_scope_v1_controller",
    }


def _build_gate_report(
    *,
    subject: ResidualTargetSelectionSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("strategy_packet_consumed", True),
        _gate_result("residual_options_loaded", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("selected_target_valid", True),
        _gate_result(
            "selected_target_narrower_than_repeated_broad_target",
            _selected_target_is_narrower_than_repeated_broad_target(subject),
        ),
        _gate_result(
            "protected_effects_recorded",
            bool(payloads["protected_effects_and_forbidden_changes"]["protected_effects"]),
        ),
        _gate_result("current_best_reference_normalized", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "candidate_generation_authorized",
            False,
            ["selection packet authorizes only a future work-order/strategy step"],
            record=False,
        ),
        _gate_result(
            "live_model_call_authorized",
            False,
            ["selection packet does not authorize live model calls"],
            record=False,
        ),
        _gate_result(
            "ablation_authorized",
            False,
            ["selection packet does not authorize ablation"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_authorized",
            False,
            ["selection packet does not authorize reader-state evaluation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["residual target selection is not finalization evidence"],
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
            ["operator target selection is not human validation"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "candidate generation remains unauthorized",
        "live model calls remain unauthorized",
        "ablation remains unauthorized",
        "reader-state evaluation remains unauthorized",
        "strongest rival remains blocking",
        "human validation is absent",
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
        "no_final_claim": True,
        "selected_residual_target_id": subject.selected_target_id,
        "next_allowed_action": subject.target_spec.canonical_next_action,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Residual target selection accepted the operator-reviewed narrow "
            "target but remains fail-closed; it authorizes only a future work "
            "order, not generation."
        ),
        "worker": "residual_target_selection_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ResidualTargetSelectionSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    stale_report = _stale_current_best_reference_report(subject)
    counts = packet_artifact_count_summary(
        required_artifact_types=RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="residual_target_selection_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "residual_target_selection_packet"],
        "counts": {
            **counts,
            "residual_target_selection_artifacts": counts["produced_artifacts"],
            "required_residual_target_selection_artifacts": counts[
                "required_artifacts"
            ],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "source_strategy_packet_id": subject.strategy_packet_id,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "selected_residual_target_id": subject.selected_target_id,
        **stale_report,
        "broad_blocker_class": _broad_blocker_class(subject),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "selected_target_is_narrower_than_repeated_broad_target": (
            _selected_target_is_narrower_than_repeated_broad_target(subject)
        ),
        "next_allowed_action": subject.target_spec.canonical_next_action,
        "next_recommended_action": subject.target_spec.canonical_next_action,
        "work_order_adapter": subject.target_spec.work_order_adapter,
        "candidate_generated": False,
        "model_calls": 0,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "requires_separate_generation_authorization": True,
        "next_strategy_or_work_order_authorized": True,
        "gate_report": payloads["residual_target_selection_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "residual_target_selection_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: ResidualTargetSelectionSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["residual_target_selection_packet"]
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
        "current_best_candidate_packet_id": packet["current_best_candidate_packet_id"],
        "proof_packet_id": packet["proof_packet_id"],
        "reader_state_packet_id": packet["reader_state_packet_id"],
        "selected_residual_target_id": subject.selected_target_id,
        "stale_strategy_current_best_reference_detected": packet[
            "stale_strategy_current_best_reference_detected"
        ],
        "stale_reference_packet_id": packet["stale_reference_packet_id"],
        "authoritative_current_best_packet_id": packet[
            "authoritative_current_best_packet_id"
        ],
        "broad_blocker_class": packet["broad_blocker_class"],
        "next_allowed_action": subject.target_spec.canonical_next_action,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": subject.target_spec.canonical_next_action,
        "model_calls": 0,
    }


def _operator_selection_reason(subject: ResidualTargetSelectionSubject) -> str:
    if subject.selected_target_id == OBJECT_MOTION_CAUSALITY_TARGET_ID:
        return (
            "object motion causality specificity is narrower than the repeated "
            "broad first-read object-event pressure target, evidence-aligned "
            "with the rival gap, and less likely to drift into generic vividness, "
            "rival mimicry, proof/no-answer compression, or final-return overwork."
        )
    if subject.selected_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return (
            "hostile scaffold visibility is a narrower residual target than the "
            "repeated broad first-read object-event pressure target; it asks for "
            "less visible thesis/explanatory pressure while preserving embodied "
            "causal field, proof/no-answer carry, and opening-return gains."
        )
    return (
        "tactile inevitability is a narrower residual target than the repeated "
        "broad first-read object-event pressure target; it asks for material "
        "force/contact necessity rather than another object-motion pass."
    )


def _find_option(options: list[object], target: str) -> dict[str, Any] | None:
    for option in options:
        if isinstance(option, dict) and option.get("option_id") == target:
            return option
    return None


def _broad_blocker_class(subject: ResidualTargetSelectionSubject) -> str:
    residual_map = subject.payloads["residual_target_option_map"]
    return str(residual_map.get("broad_blocker_class") or REPEATED_BROAD_TARGET_ID)


def _repeated_broad_target_detected(subject: ResidualTargetSelectionSubject) -> bool:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    return bool(
        packet.get("repeated_target_detected") is True
        or residual_map.get("repeated_target_detected") is True
    )


def _same_broad_target_allowed(subject: ResidualTargetSelectionSubject) -> bool:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    return bool(
        packet.get("same_broad_target_allowed") is True
        or residual_map.get("same_broad_target_allowed") is True
    )


def _selected_target_is_narrower_than_repeated_broad_target(
    subject: ResidualTargetSelectionSubject,
) -> bool:
    return (
        _repeated_broad_target_detected(subject)
        and subject.selected_target_id != _broad_blocker_class(subject)
        and _same_broad_target_allowed(subject) is False
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
    artifact_ids = packet_payload.get("artifact_ids")
    if not isinstance(artifact_ids, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in artifact_ids.items()
        if isinstance(value, str)
    }


def _validate_current_best_consistency(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["next_target_strategy_packet"]
    current_best = packet.get("current_best_candidate_packet_id")
    if not isinstance(current_best, str) or not current_best:
        raise ValueError(
            "Residual target selection refused; strategy packet missing current "
            "best candidate packet ID."
        )
    checks = (
        (
            "next_target_strategy_subject_manifest.current_best_candidate_packet_id",
            payloads["next_target_strategy_subject_manifest"].get(
                "current_best_candidate_packet_id"
            ),
        ),
        (
            "source_evidence_summary.current_best_candidate_packet_id",
            payloads["source_evidence_summary"].get("current_best_candidate_packet_id"),
        ),
        (
            "current_best_candidate_summary.current_best_candidate_packet_id",
            payloads["current_best_candidate_summary"].get(
                "current_best_candidate_packet_id"
            ),
        ),
    )
    for field_name, value in checks:
        if isinstance(value, str) and value and value != current_best:
            raise ValueError(
                "Residual target selection refused; strategy current best is "
                f"inconsistent: {field_name}={value}, authoritative={current_best}."
            )
    current_best_object = packet.get("current_best_candidate")
    if isinstance(current_best_object, dict):
        object_id = current_best_object.get("packet_id")
        if isinstance(object_id, str) and object_id and object_id != current_best:
            raise ValueError(
                "Residual target selection refused; strategy current best object "
                f"does not match top-level current best: {object_id} != {current_best}."
            )


def _stale_current_best_reference_report(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    current_best = str(packet.get("current_best_candidate_packet_id") or "")
    allowed = _allowed_packet_references(subject)
    stale_locations: list[dict[str, object]] = []
    for artifact_type, payload in subject.payloads.items():
        _collect_stale_packet_refs(
            payload,
            path=artifact_type,
            allowed_packet_ids=allowed,
            stale_locations=stale_locations,
        )
    stale_ids = sorted(
        {
            str(location["packet_id"])
            for location in stale_locations
            if isinstance(location.get("packet_id"), str)
        }
    )
    return {
        "stale_strategy_current_best_reference_detected": bool(stale_ids),
        "stale_reference_packet_id": stale_ids[0] if len(stale_ids) == 1 else None,
        "stale_reference_packet_ids": stale_ids,
        "authoritative_current_best_packet_id": current_best,
        "stale_reference_locations": stale_locations[:12],
    }


def _allowed_packet_references(subject: ResidualTargetSelectionSubject) -> set[str]:
    packet = subject.payloads["next_target_strategy_packet"]
    values = [
        subject.strategy_packet_id,
        packet.get("packet_id"),
        packet.get("current_best_candidate_packet_id"),
        packet.get("proof_packet_id"),
        packet.get("reader_state_packet_id"),
        packet.get("source_synthesis_packet_id"),
        packet.get("authorization_packet_id"),
        packet.get("source_authorization_packet_id"),
        packet.get("architecture_checkpoint_packet_id"),
        packet.get("source_loop_cleanup_packet_id"),
        packet.get("loop_review_packet_id"),
        packet.get("source_loop_review_packet_id"),
    ]
    current_best = packet.get("current_best_candidate")
    if isinstance(current_best, dict):
        values.append(current_best.get("packet_id"))
    return {str(value) for value in values if isinstance(value, str) and value}


def _collect_stale_packet_refs(
    value: object,
    *,
    path: str,
    allowed_packet_ids: set[str],
    stale_locations: list[dict[str, object]],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _historical_reference_field(child_path):
                continue
            _collect_stale_packet_refs(
                child,
                path=child_path,
                allowed_packet_ids=allowed_packet_ids,
                stale_locations=stale_locations,
            )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _collect_stale_packet_refs(
                child,
                path=f"{path}[{index}]",
                allowed_packet_ids=allowed_packet_ids,
                stale_locations=stale_locations,
            )
        return
    if not isinstance(value, str):
        return
    for packet_id in re.findall(r"\bpacket_\d+\b", value):
        if packet_id in allowed_packet_ids:
            continue
        stale_locations.append(
            {
                "packet_id": packet_id,
                "path": path,
                "snippet": _snippet(value),
            }
        )


def _historical_reference_field(path: str) -> bool:
    lowered = path.lower()
    return any(
        token in lowered
        for token in (
            "superseded",
            "prior_best",
            "base_candidate_packet_id",
            "source_selection_packet_id",
        )
    )


def _snippet(value: str, limit: int = 160) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path), str(path.resolve())),
    ).fetchone()
    if row is None:
        return None
    return row_to_artifact(row)


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return (config.root / value).resolve()


def _refusal(
    *,
    strategy_packet: Path,
    target: str,
    message: str,
) -> ResidualTargetSelectionResult:
    return ResidualTargetSelectionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "strategy_packet": str(strategy_packet),
            "selected_residual_target_id": target,
            "candidate_generated": False,
            "candidate_generation_authorized": False,
            "next_strategy_or_work_order_authorized": False,
            "counts": {"model_calls": 0, "candidate_artifacts_created": 0},
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
