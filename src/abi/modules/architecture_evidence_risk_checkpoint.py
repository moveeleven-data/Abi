"""Deterministic architecture/evidence-risk checkpoint packet."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.residual_targets import (
    get_residual_target_adapter,
    get_residual_target_spec,
    supported_residual_target_ids,
    target_generation_readiness_failures,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)
from abi.target_artifacts import (
    GENERIC_TARGET_DIAGNOSTIC_ARTIFACT,
    GENERIC_TARGET_UNIT_MAP_ARTIFACT,
    LEGACY_TARGET_DIAGNOSTIC_ARTIFACT,
    LEGACY_TARGET_UNIT_MAP_ARTIFACT,
)


ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_LINEAGE_ID = (
    "architecture_evidence_risk_checkpoint_v1"
)
ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_CREATED_BY = (
    "architecture_evidence_risk_checkpoint_v1_controller"
)

ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_ARTIFACT_TYPES = (
    "active_evidence_chain_summary",
    "failed_target_memory_report",
    "target_adapter_inventory",
    "legacy_artifact_name_audit",
    "hardcoded_packet_id_audit",
    "generation_lock_and_authorization_audit",
    "unresolved_creative_blocker_summary",
    "next_strategy_readiness_report",
    "architecture_risk_gate_report",
    "architecture_evidence_risk_checkpoint_packet",
)

HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID = "hostile_scaffold_visibility"
ENDING_EXPLAINS_RETURN_RISK_TARGET_ID = "ending_explains_return_risk"
OBJECT_MOTION_CAUSALITY_TARGET_ID = "object_motion_causality_specificity"
PAUSED_STATUS = "paused_or_exhausted_pending_strategy_review"
NEXT_RECOMMENDED_ACTION = (
    "review_architecture_evidence_risk_checkpoint_before_next_target_strategy"
)
PACKET_ID_PATTERN = re.compile(r"\bpacket_\d{4}\b")


@dataclass(frozen=True)
class ArchitectureEvidenceRiskCheckpointResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class ArchitectureEvidenceRiskSubject:
    run_id: str
    authorization_packet_dir: Path
    authorization_payloads: dict[str, dict[str, Any]]
    authorization_packet: dict[str, Any]
    authorization_packet_artifact_id: str | None
    loop_cleanup_packet_dir: Path | None
    loop_cleanup_payloads: dict[str, dict[str, Any]]
    loop_cleanup_packet_artifact_id: str | None
    loop_review_packet_dir: Path
    loop_review_payloads: dict[str, dict[str, Any]]
    loop_review_packet_artifact_id: str | None
    synthesis_packet_dir: Path
    synthesis_payloads: dict[str, dict[str, Any]]
    synthesis_packet_artifact_id: str | None
    source_parent_ids: tuple[str, ...]


def run_architecture_evidence_risk_checkpoint(
    config: AbiConfig,
    *,
    authorization_packet: Path | str,
    operator_reviewed: bool,
) -> ArchitectureEvidenceRiskCheckpointResult:
    initialize_database(config)
    authorization_packet_dir = _resolve_path(config, authorization_packet)
    if not operator_reviewed:
        return _refusal(
            authorization_packet=authorization_packet_dir,
            message=(
                "Architecture/evidence-risk checkpoint refused; "
                "--operator-reviewed is required."
            ),
        )
    if not authorization_packet_dir.exists() or not authorization_packet_dir.is_dir():
        return _refusal(
            authorization_packet=authorization_packet_dir,
            message=(
                "Architecture/evidence-risk checkpoint refused; authorization "
                f"packet directory not found: {authorization_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, authorization_packet_dir)
    except ValueError as error:
        return _refusal(
            authorization_packet=authorization_packet_dir,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                authorization_packet=authorization_packet_dir,
                message=(
                    "Architecture/evidence-risk checkpoint refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "architecture_evidence_risk_checkpoint"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_LINEAGE_ID,
            created_by=ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["active_evidence_chain_summary"] = _build_active_evidence_chain_summary(
            subject
        )
        artifacts["active_evidence_chain_summary"] = writer.write_artifact(
            "active_evidence_chain_summary",
            payloads["active_evidence_chain_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["failed_target_memory_report"] = _build_failed_target_memory_report(
            subject
        )
        artifacts["failed_target_memory_report"] = writer.write_artifact(
            "failed_target_memory_report",
            payloads["failed_target_memory_report"],
            parent_ids=[artifacts["active_evidence_chain_summary"].id],
        )

        payloads["target_adapter_inventory"] = _build_target_adapter_inventory(
            subject,
            payloads["failed_target_memory_report"],
        )
        artifacts["target_adapter_inventory"] = writer.write_artifact(
            "target_adapter_inventory",
            payloads["target_adapter_inventory"],
            parent_ids=[artifacts["failed_target_memory_report"].id],
        )

        payloads["legacy_artifact_name_audit"] = _build_legacy_artifact_name_audit(
            config,
            subject,
        )
        artifacts["legacy_artifact_name_audit"] = writer.write_artifact(
            "legacy_artifact_name_audit",
            payloads["legacy_artifact_name_audit"],
            parent_ids=[artifacts["target_adapter_inventory"].id],
        )

        payloads["hardcoded_packet_id_audit"] = _build_hardcoded_packet_id_audit(config)
        artifacts["hardcoded_packet_id_audit"] = writer.write_artifact(
            "hardcoded_packet_id_audit",
            payloads["hardcoded_packet_id_audit"],
            parent_ids=[artifacts["legacy_artifact_name_audit"].id],
        )

        payloads["generation_lock_and_authorization_audit"] = (
            _build_generation_lock_and_authorization_audit(subject)
        )
        artifacts["generation_lock_and_authorization_audit"] = writer.write_artifact(
            "generation_lock_and_authorization_audit",
            payloads["generation_lock_and_authorization_audit"],
            parent_ids=[
                artifacts["active_evidence_chain_summary"].id,
                artifacts["failed_target_memory_report"].id,
            ],
        )

        payloads["unresolved_creative_blocker_summary"] = (
            _build_unresolved_creative_blocker_summary(subject)
        )
        artifacts["unresolved_creative_blocker_summary"] = writer.write_artifact(
            "unresolved_creative_blocker_summary",
            payloads["unresolved_creative_blocker_summary"],
            parent_ids=[
                artifacts["active_evidence_chain_summary"].id,
                artifacts["failed_target_memory_report"].id,
            ],
        )

        payloads["next_strategy_readiness_report"] = (
            _build_next_strategy_readiness_report(
                subject,
                payloads["failed_target_memory_report"],
            )
        )
        artifacts["next_strategy_readiness_report"] = writer.write_artifact(
            "next_strategy_readiness_report",
            payloads["next_strategy_readiness_report"],
            parent_ids=[
                artifacts["generation_lock_and_authorization_audit"].id,
                artifacts["unresolved_creative_blocker_summary"].id,
                artifacts["target_adapter_inventory"].id,
            ],
        )

        payloads["architecture_risk_gate_report"] = _build_gate_report(payloads)
        artifacts["architecture_risk_gate_report"] = writer.write_artifact(
            "architecture_risk_gate_report",
            payloads["architecture_risk_gate_report"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "architecture_risk_gate_report"
            ],
        )

        payloads["architecture_evidence_risk_checkpoint_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["architecture_evidence_risk_checkpoint_packet"] = (
            writer.write_artifact(
                "architecture_evidence_risk_checkpoint_packet",
                payloads["architecture_evidence_risk_checkpoint_packet"],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type != "architecture_evidence_risk_checkpoint_packet"
                ],
            )
        )

        gate_report = payloads["architecture_risk_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="architecture_risk_checkpoint_completed",
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    return ArchitectureEvidenceRiskCheckpointResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    authorization_packet_dir: Path,
) -> ArchitectureEvidenceRiskSubject:
    authorization_payloads = _load_packet_payloads(
        authorization_packet_dir,
        (
            "supervised_cycle_authorization_subject_manifest",
            "supervised_cycle_authorization_packet",
        ),
        "supervised cycle authorization",
    )
    authorization_packet = authorization_payloads["supervised_cycle_authorization_packet"]
    authorization_manifest = authorization_payloads[
        "supervised_cycle_authorization_subject_manifest"
    ]
    run_id = _first_string(authorization_packet.get("run_id"))
    if not run_id:
        raise ValueError(
            "Architecture/evidence-risk checkpoint refused; authorization packet "
            "missing run_id."
        )
    if authorization_packet.get("next_strategy_authorized") is not True:
        raise ValueError(
            "Architecture/evidence-risk checkpoint refused; authorization packet "
            "does not authorize next strategy review."
        )
    if authorization_packet.get("next_generation_authorized") is True:
        raise ValueError(
            "Architecture/evidence-risk checkpoint refused; authorization packet "
            "authorizes generation, which is out of scope."
        )

    cleanup_dir = _optional_packet_dir(
        config,
        run_id,
        "loop_integrity_cleanup",
        authorization_packet,
        authorization_manifest,
        path_keys=("source_loop_cleanup_packet_dir", "loop_cleanup_packet_dir"),
        id_keys=("source_loop_cleanup_packet_id", "loop_cleanup_packet_id"),
    )
    cleanup_payloads: dict[str, dict[str, Any]] = {}
    if cleanup_dir is not None and cleanup_dir.exists():
        cleanup_payloads = _load_packet_payloads(
            cleanup_dir,
            (
                "active_evidence_state_checkpoint",
                "generation_lock_report",
                "loop_integrity_cleanup_packet",
            ),
            "loop-integrity cleanup",
        )

    cleanup_packet = cleanup_payloads.get("loop_integrity_cleanup_packet", {})
    active_checkpoint = cleanup_payloads.get("active_evidence_state_checkpoint", {})
    loop_review_dir = _optional_packet_dir(
        config,
        run_id,
        "evidence_loop_review",
        active_checkpoint,
        cleanup_packet,
        authorization_packet,
        authorization_manifest,
        path_keys=("source_loop_review_packet_dir", "loop_review_packet_dir"),
        id_keys=("source_loop_review_packet_id", "loop_review_packet_id"),
    )
    if loop_review_dir is None or not loop_review_dir.exists():
        raise ValueError(
            "Architecture/evidence-risk checkpoint refused; linked loop-review "
            f"packet directory not found: {loop_review_dir}"
        )
    loop_review_payloads = _load_packet_payloads(
        loop_review_dir,
        (
            "evidence_loop_review_subject_manifest",
            "evidence_loop_review_packet",
            "current_best_candidate_review",
            "reader_state_progress_review",
            "strongest_rival_status_review",
            "residual_blocker_taxonomy",
            "next_action_decision",
        ),
        "evidence loop review",
    )

    synthesis_dir = _optional_packet_dir(
        config,
        run_id,
        "autonomous_evidence_synthesis",
        active_checkpoint,
        cleanup_packet,
        loop_review_payloads.get("evidence_loop_review_subject_manifest", {}),
        loop_review_payloads.get("evidence_loop_review_packet", {}),
        authorization_packet,
        authorization_manifest,
        path_keys=("source_synthesis_packet_dir", "synthesis_packet_dir"),
        id_keys=("source_synthesis_packet_id", "synthesis_packet_id"),
    )
    if synthesis_dir is None or not synthesis_dir.exists():
        raise ValueError(
            "Architecture/evidence-risk checkpoint refused; linked synthesis packet "
            f"directory not found: {synthesis_dir}"
        )
    synthesis_payloads = _load_packet_payloads(
        synthesis_dir,
        (
            "autonomous_evidence_synthesis_packet",
            "best_current_candidate_selection",
            "candidate_evidence_graph",
            "failed_or_rejected_repairs",
            "reader_state_evidence_adjudication",
            "residual_blocker_map",
            "rival_pressure_summary",
            "strategic_decision_report",
            "synthesis_gate_report",
        ),
        "autonomous evidence synthesis",
    )

    with connect(config.db_path) as connection:
        authorization_artifact = _artifact_for_path(
            connection,
            authorization_packet_dir / "supervised_cycle_authorization_packet.json",
        )
        cleanup_artifact = (
            _artifact_for_path(
                connection,
                cleanup_dir / "loop_integrity_cleanup_packet.json",
            )
            if cleanup_dir is not None and cleanup_dir.exists()
            else None
        )
        loop_review_artifact = _artifact_for_path(
            connection,
            loop_review_dir / "evidence_loop_review_packet.json",
        )
        synthesis_artifact = _artifact_for_path(
            connection,
            synthesis_dir / "autonomous_evidence_synthesis_packet.json",
        )

    parent_ids = _unique(
        [
            authorization_artifact.id if authorization_artifact else None,
            cleanup_artifact.id if cleanup_artifact else None,
            loop_review_artifact.id if loop_review_artifact else None,
            synthesis_artifact.id if synthesis_artifact else None,
            *_artifact_ids_from_packet(authorization_packet).values(),
            *_artifact_ids_from_packet(cleanup_packet).values(),
            *_artifact_ids_from_packet(
                loop_review_payloads["evidence_loop_review_packet"]
            ).values(),
            *_artifact_ids_from_packet(
                synthesis_payloads["autonomous_evidence_synthesis_packet"]
            ).values(),
        ]
    )
    return ArchitectureEvidenceRiskSubject(
        run_id=run_id,
        authorization_packet_dir=authorization_packet_dir,
        authorization_payloads=authorization_payloads,
        authorization_packet=authorization_packet,
        authorization_packet_artifact_id=authorization_artifact.id
        if authorization_artifact
        else None,
        loop_cleanup_packet_dir=cleanup_dir if cleanup_dir and cleanup_dir.exists() else None,
        loop_cleanup_payloads=cleanup_payloads,
        loop_cleanup_packet_artifact_id=cleanup_artifact.id if cleanup_artifact else None,
        loop_review_packet_dir=loop_review_dir,
        loop_review_payloads=loop_review_payloads,
        loop_review_packet_artifact_id=loop_review_artifact.id
        if loop_review_artifact
        else None,
        synthesis_packet_dir=synthesis_dir,
        synthesis_payloads=synthesis_payloads,
        synthesis_packet_artifact_id=synthesis_artifact.id if synthesis_artifact else None,
        source_parent_ids=tuple(parent_ids),
    )


def _build_active_evidence_chain_summary(
    subject: ArchitectureEvidenceRiskSubject,
) -> dict[str, object]:
    synthesis_packet = subject.synthesis_payloads["autonomous_evidence_synthesis_packet"]
    best = subject.synthesis_payloads["best_current_candidate_selection"][
        "selected_best_candidate"
    ]
    return {
        "run_id": subject.run_id,
        "current_best_candidate_packet_id": best.get("packet_id"),
        "current_best_candidate_packet_dir": best.get("packet_dir"),
        "current_best_candidate_kind": best.get("packet_kind"),
        "proof_packet_id": best.get("proof_packet_id"),
        "proof_packet_dir": best.get("proof_packet_dir"),
        "reader_state_packet_id": best.get("reader_state_packet_id"),
        "reader_state_packet_dir": best.get("reader_state_packet_dir"),
        "source_synthesis_packet_id": synthesis_packet.get("packet_id"),
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_loop_review_packet_id": _loop_review_packet(subject).get("packet_id"),
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_cleanup_packet_id": _cleanup_packet(subject).get("packet_id"),
        "source_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "source_authorization_packet_id": subject.authorization_packet.get("packet_id"),
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
        "next_strategy_authorized": bool(
            subject.authorization_packet.get("next_strategy_authorized")
        ),
        "next_generation_authorized": bool(
            subject.authorization_packet.get("next_generation_authorized")
        ),
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_still_blocks": bool(
            best.get("strongest_rival_still_blocks")
            or _rival_pressure(subject).get("strongest_rival_still_blocks")
        ),
        "worker": "active_evidence_chain_summary_v1_controller",
    }


def _build_failed_target_memory_report(
    subject: ArchitectureEvidenceRiskSubject,
) -> dict[str, object]:
    status_map = _failed_target_status_map(subject.synthesis_payloads)
    failed_targets = {}
    for target_id in (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    ):
        status = status_map.get(target_id, {})
        failed_targets[target_id] = {
            "target_id": target_id,
            "target_status": status.get("target_status") or PAUSED_STATUS,
            "paused_or_exhausted": (
                status.get("target_status") == PAUSED_STATUS
                or bool(status.get("stop_test_triggered"))
            ),
            "generation_retry_recommended": False,
            "failed_packet_ids": list(status.get("failed_packet_ids", []))
            if isinstance(status.get("failed_packet_ids"), list)
            else [],
            "failure_classes": list(status.get("failure_classes", []))
            if isinstance(status.get("failure_classes"), list)
            else [],
            "source_authorization_packet_id": status.get(
                "source_authorization_packet_id"
            ),
            "source_work_order_packet_id": status.get("source_work_order_packet_id"),
            "authorization_still_technically_unconsumed": True,
            "should_not_reuse_authorization_without_strategy_review": True,
            "candidate_generation_authorized": False,
            "ablation_authorized_on_failed_packets": False,
            "reader_state_evaluation_authorized_on_failed_packets": False,
            "failed_packets_are_not_candidate_evidence": True,
        }
    authorization_reuse_warnings = [
        {
            "target_id": target_id,
            "source_authorization_packet_id": target["source_authorization_packet_id"],
            "technically_unconsumed": target[
                "authorization_still_technically_unconsumed"
            ],
            "reuse_without_strategy_review_allowed": False,
        }
        for target_id, target in failed_targets.items()
        if target.get("source_authorization_packet_id")
    ]
    return {
        "failed_targets": failed_targets,
        "failed_target_count": len(
            [target for target in failed_targets.values() if target["failed_packet_ids"]]
        ),
        "paused_or_exhausted_target_ids": [
            target_id
            for target_id, target in failed_targets.items()
            if target["paused_or_exhausted"]
        ],
        "authorization_reuse_warnings": authorization_reuse_warnings,
        "hostile_scaffold_retry_recommended": False,
        "ending_return_retry_recommended": False,
        "do_not_recommend_hostile_scaffold_generation": True,
        "do_not_recommend_ending_return_generation": True,
        "not_candidate_evidence": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "failed_target_memory_report_v1_controller",
    }


def _build_target_adapter_inventory(
    subject: ArchitectureEvidenceRiskSubject,
    failed_memory: dict[str, object],
) -> dict[str, object]:
    failed_targets = failed_memory["failed_targets"]
    inventory = []
    for target_id in supported_residual_target_ids():
        spec = get_residual_target_spec(target_id)
        adapter = get_residual_target_adapter(target_id)
        readiness_failures = []
        if adapter is not None:
            readiness_failures = target_generation_readiness_failures(target_id)
        failed_status = failed_targets.get(target_id, {})
        paused = bool(failed_status.get("paused_or_exhausted"))
        inventory.append(
            {
                "target_id": target_id,
                "adapter_id": adapter.adapter_id if adapter else spec.work_order_adapter if spec else None,
                "planning_support": spec is not None,
                "generation_support": adapter is not None and not readiness_failures,
                "generation_readiness_failures": readiness_failures,
                "materiality_policy_id": adapter.materiality_policy.policy_id
                if adapter
                else None,
                "semantic_validator_id": adapter.semantic_validator_id
                if adapter
                else None,
                "failed_or_paused_in_current_run": paused,
                "target_status": failed_status.get("target_status")
                if failed_status
                else "not_paused_by_checkpoint",
                "available_for_immediate_selection": (
                    spec is not None and not paused
                ),
                "available_for_generation": False,
                "known_technical_debt_or_compatibility_notes": _target_notes(target_id),
            }
        )
    return {
        "targets": inventory,
        "target_count": len(inventory),
        "required_targets_present": all(
            target_id in {row["target_id"] for row in inventory}
            for target_id in (
                OBJECT_MOTION_CAUSALITY_TARGET_ID,
                "tactile_inevitability_gap",
                HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
                ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
            )
        ),
        "next_generation_authorized": False,
        "no_target_selected": True,
        "worker": "target_adapter_inventory_v1_controller",
    }


def _build_legacy_artifact_name_audit(
    config: AbiConfig,
    subject: ArchitectureEvidenceRiskSubject,
) -> dict[str, object]:
    findings = []
    run_dir = config.run_dir(subject.run_id)
    legacy_to_generic = {
        f"{LEGACY_TARGET_UNIT_MAP_ARTIFACT}.json": (
            f"{GENERIC_TARGET_UNIT_MAP_ARTIFACT}.json"
        ),
        f"{LEGACY_TARGET_DIAGNOSTIC_ARTIFACT}.json": (
            f"{GENERIC_TARGET_DIAGNOSTIC_ARTIFACT}.json"
        ),
    }
    for file_name, generic_file_name in legacy_to_generic.items():
        for path in sorted(run_dir.glob(f"**/{file_name}")):
            payload = _read_optional_payload(path)
            target_id = _first_string(
                payload.get("selected_residual_target_id"),
                payload.get("target_scope"),
                payload.get("target_movement"),
            )
            if target_id == OBJECT_MOTION_CAUSALITY_TARGET_ID:
                continue
            if not target_id:
                continue
            generic_path = path.with_name(generic_file_name)
            generic_payload = _read_optional_payload(generic_path)
            generic_present = bool(generic_payload)
            blocking = (
                payload.get("blocking_legacy_semantic_dependency") is True
                or generic_payload.get("blocking_legacy_semantic_dependency") is True
            )
            classification = (
                "blocking_legacy_semantic_dependency"
                if blocking
                else "generic_alias_present_legacy_retained_for_compatibility"
                if generic_present
                else "legacy_only_no_generic_alias"
            )
            consumer_state = (
                "blocking_legacy_semantic_dependency"
                if blocking
                else "consumer_prefers_generic"
                if generic_present
                else "legacy_fallback_required"
            )
            severity = "blocking" if blocking else "note" if generic_present else "warning"
            findings.append(
                {
                    "path": str(path),
                    "file_name": file_name,
                    "generic_alias_path": str(generic_path) if generic_present else None,
                    "generic_alias_file_name": generic_file_name,
                    "payload_target_id": target_id,
                    "payload_target_adapter_id": payload.get("target_adapter_id"),
                    "classification": classification,
                    "consumer_state": consumer_state,
                    "severity": severity,
                    "compatibility_reason": _first_string(
                        generic_payload.get("source_legacy_artifact_name"),
                        payload.get("artifact_name_compatibility_reason"),
                        payload.get("legacy_artifact_name"),
                        "legacy object-motion artifact filename retained for compatibility",
                    ),
                    "downstream_risk": (
                        "legacy fallback only; operator or future automation may "
                        "misread target-specific artifacts as object-motion only"
                        if not generic_present
                        else "generic alias is available; legacy file retained for historical compatibility"
                    ),
                    "recommendation": (
                        "consumers should prefer generic target_unit_map/target_diagnostic aliases"
                        if generic_present
                        else "write generic target_unit_map/target_diagnostic aliases in new packets"
                    ),
                    "blocking": blocking,
                }
            )
    warning_count = len([finding for finding in findings if finding["severity"] == "warning"])
    note_count = len([finding for finding in findings if finding["severity"] == "note"])
    blocking_count = len([finding for finding in findings if finding["blocking"]])
    return {
        "findings": findings,
        "finding_count": len(findings),
        "warning_count": warning_count,
        "note_count": note_count,
        "generic_alias_present_count": len(
            [
                finding
                for finding in findings
                if finding["classification"]
                == "generic_alias_present_legacy_retained_for_compatibility"
            ]
        ),
        "legacy_only_count": len(
            [
                finding
                for finding in findings
                if finding["classification"] == "legacy_only_no_generic_alias"
            ]
        ),
        "consumer_prefers_generic_count": len(
            [
                finding
                for finding in findings
                if finding["consumer_state"] == "consumer_prefers_generic"
            ]
        ),
        "blocking_count": blocking_count,
        "passed": blocking_count == 0,
        "recommendation": (
            "Track as compatibility debt; do not block this checkpoint unless "
            "a downstream command relies on the legacy name semantically."
        ),
        "worker": "legacy_artifact_name_audit_v1_controller",
    }


def _build_hardcoded_packet_id_audit(config: AbiConfig) -> dict[str, object]:
    production_findings = _scan_packet_ids(config.root / "src" / "abi", production=True)
    test_findings = _scan_packet_ids(config.root / "tests", production=False)
    unacceptable = [
        finding
        for finding in production_findings
        if finding["classification"] == "unacceptable_hardcode"
    ]
    suspicious = [
        finding
        for finding in production_findings
        if finding["classification"] == "suspicious_run_specific_logic"
    ]
    return {
        "production_findings": production_findings,
        "production_finding_count": len(production_findings),
        "test_fixture_findings": test_findings,
        "test_fixture_finding_count": len(test_findings),
        "suspicious_production_finding_count": len(suspicious),
        "unacceptable_hardcode_count": len(unacceptable),
        "passed": not unacceptable,
        "tests_classified_separately": True,
        "default_behavior": (
            "warnings only unless a production packet ID is classified as "
            "unacceptable_hardcode"
        ),
        "worker": "hardcoded_packet_id_audit_v1_controller",
    }


def _build_generation_lock_and_authorization_audit(
    subject: ArchitectureEvidenceRiskSubject,
) -> dict[str, object]:
    cleanup = _cleanup_packet(subject)
    return {
        "source_authorization_packet_id": subject.authorization_packet.get("packet_id"),
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
        "authorization_decision": subject.authorization_packet.get("decision"),
        "next_strategy_authorized": bool(
            subject.authorization_packet.get("next_strategy_authorized")
        ),
        "next_generation_authorized": bool(
            subject.authorization_packet.get("next_generation_authorized")
        ),
        "generation_authorized": False,
        "candidate_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "cleanup_completed": bool(cleanup.get("loop_integrity_cleanup_completed"))
        if cleanup
        else None,
        "authorization_consumed_for_generation": False,
        "generation_requires_separate_authorization": True,
        "lock_status": "generation_locked_strategy_only",
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "generation_lock_and_authorization_audit_v1_controller",
    }


def _build_unresolved_creative_blocker_summary(
    subject: ArchitectureEvidenceRiskSubject,
) -> dict[str, object]:
    best = subject.synthesis_payloads["best_current_candidate_selection"][
        "selected_best_candidate"
    ]
    reader_state = subject.synthesis_payloads["reader_state_evidence_adjudication"]
    failed_status = _failed_target_status_map(subject.synthesis_payloads)
    blockers = [
        {
            "blocker_id": "strongest_rival_still_blocks",
            "severity": "high",
            "status": "active",
        },
        {
            "blocker_id": "reader_state_transformation_partial",
            "severity": "high",
            "status": reader_state.get("reread_transformation_strength") or "partial",
        },
        {
            "blocker_id": "proof_no_answer_carry_partial_or_unresolved",
            "severity": "high",
            "status": "active",
        },
        {
            "blocker_id": "hostile_reader_or_scaffold_risk_unresolved",
            "severity": "high",
            "status": "active",
        },
        {
            "blocker_id": "human_operator_validation_absent",
            "severity": "high",
            "status": "absent",
        },
        {
            "blocker_id": "finalization_ineligible",
            "severity": "high",
            "status": "fail_closed",
        },
        {
            "blocker_id": "hostile_scaffold_generation_path_failed",
            "severity": "high",
            "status": failed_status.get(
                HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID, {}
            ).get("target_status", PAUSED_STATUS),
        },
        {
            "blocker_id": "ending_return_generation_path_failed",
            "severity": "high",
            "status": failed_status.get(
                ENDING_EXPLAINS_RETURN_RISK_TARGET_ID, {}
            ).get("target_status", PAUSED_STATUS),
        },
    ]
    return {
        "current_best_candidate_packet_id": best.get("packet_id"),
        "current_best_is_final": False,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "failed_local_residual_generation_targets": [
            HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
            ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
        ],
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "unresolved_creative_blocker_summary_v1_controller",
    }


def _build_next_strategy_readiness_report(
    subject: ArchitectureEvidenceRiskSubject,
    failed_memory: dict[str, object],
) -> dict[str, object]:
    del failed_memory
    return {
        "ready_for_next_target_strategy_review": bool(
            subject.authorization_packet.get("next_strategy_authorized")
        ),
        "generation_authorized": False,
        "candidate_generated": False,
        "selected_target_id": None,
        "target_selected": False,
        "recommendations": [
            "do_not_generate",
            "do_not_retry_hostile_scaffold",
            "do_not_retry_ending_return",
            "do_not_finalize",
            "review_architecture_evidence_risk_checkpoint_before_next_target_strategy",
            "after_review_strategy_planning_may_proceed_strategy_only",
        ],
        "plausible_remaining_strategic_directions": [
            "proof_no_answer_residue",
            "local_busyness_decorative_detail_risk",
            "rival_level_first_read_vividness",
            "pause local residual generation",
            "architecture consolidation before more target work",
        ],
        "automatic_selection_performed": False,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_strategy_readiness_report_v1_controller",
    }


def _build_gate_report(payloads: dict[str, dict[str, object]]) -> dict[str, object]:
    chain = payloads["active_evidence_chain_summary"]
    failed_memory = payloads["failed_target_memory_report"]
    inventory = payloads["target_adapter_inventory"]
    legacy = payloads["legacy_artifact_name_audit"]
    hardcoded = payloads["hardcoded_packet_id_audit"]
    generation_lock = payloads["generation_lock_and_authorization_audit"]
    readiness = payloads["next_strategy_readiness_report"]
    gate_results = [
        _gate_result("active_evidence_chain_recorded", bool(chain)),
        _gate_result("current_best_candidate_linked", bool(chain.get("current_best_candidate_packet_id"))),
        _gate_result("proof_packet_linked", bool(chain.get("proof_packet_id"))),
        _gate_result("reader_state_packet_linked", bool(chain.get("reader_state_packet_id"))),
        _gate_result(
            "failed_target_memory_visible",
            bool(failed_memory.get("paused_or_exhausted_target_ids")),
        ),
        _gate_result("target_adapter_inventory_created", bool(inventory.get("target_count"))),
        _gate_result("legacy_artifact_name_audit_completed", bool(legacy.get("passed"))),
        _gate_result("hardcoded_packet_id_audit_no_unacceptable_hardcode", bool(hardcoded.get("passed"))),
        _gate_result("generation_locked", generation_lock.get("generation_authorized") is False),
        _gate_result("next_strategy_review_only", readiness.get("target_selected") is False),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
    ]
    blocking_defects = [
        str(gate["gate_name"]) for gate in gate_results if not gate["passed"]
    ]
    return {
        "passed": not blocking_defects,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "gate_results": gate_results,
        "failed_gates": blocking_defects,
        "blocking_defects": blocking_defects,
        "legacy_artifact_name_warnings": legacy.get("warning_count", 0),
        "suspicious_hardcoded_packet_id_warnings": hardcoded.get(
            "suspicious_production_finding_count",
            0,
        ),
        "unacceptable_hardcoded_packet_ids": hardcoded.get(
            "unacceptable_hardcode_count",
            0,
        ),
        "no_phase_shift_claim": True,
        "worker": "architecture_risk_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ArchitectureEvidenceRiskSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    chain = payloads["active_evidence_chain_summary"]
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=ARCHITECTURE_EVIDENCE_RISK_CHECKPOINT_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="architecture_evidence_risk_checkpoint_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            **artifact_counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "current_best_candidate_packet_id": chain.get("current_best_candidate_packet_id"),
        "proof_packet_id": chain.get("proof_packet_id"),
        "reader_state_packet_id": chain.get("reader_state_packet_id"),
        "source_synthesis_packet_id": chain.get("source_synthesis_packet_id"),
        "source_loop_review_packet_id": chain.get("source_loop_review_packet_id"),
        "source_cleanup_packet_id": chain.get("source_cleanup_packet_id"),
        "source_authorization_packet_id": chain.get("source_authorization_packet_id"),
        "next_strategy_authorized": chain.get("next_strategy_authorized"),
        "next_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "failed_target_memory_report": payloads["failed_target_memory_report"],
        "target_adapter_inventory": payloads["target_adapter_inventory"],
        "legacy_artifact_name_audit": payloads["legacy_artifact_name_audit"],
        "hardcoded_packet_id_audit": payloads["hardcoded_packet_id_audit"],
        "unresolved_creative_blocker_summary": payloads[
            "unresolved_creative_blocker_summary"
        ],
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "architecture_evidence_risk_checkpoint_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: ArchitectureEvidenceRiskSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["architecture_evidence_risk_checkpoint_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
    }


def _failed_target_status_map(
    synthesis_payloads: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    for payload_name in (
        "autonomous_evidence_synthesis_packet",
        "residual_blocker_map",
        "strategic_decision_report",
        "failed_or_rejected_repairs",
    ):
        status_map = synthesis_payloads.get(payload_name, {}).get(
            "failed_target_status_map"
        )
        if isinstance(status_map, dict) and status_map:
            return {
                str(target_id): dict(status)
                for target_id, status in status_map.items()
                if isinstance(status, dict)
            }
    failed_repairs = synthesis_payloads.get("failed_or_rejected_repairs", {})
    statuses = {}
    for target_id, key in (
        (
            HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
            "hostile_scaffold_failed_generation_path",
        ),
        (ENDING_EXPLAINS_RETURN_RISK_TARGET_ID, "ending_return_failed_generation_path"),
    ):
        summary = failed_repairs.get(key)
        if isinstance(summary, dict) and summary.get("attempted"):
            statuses[target_id] = {
                "target_id": target_id,
                "target_status": summary.get("target_status"),
                "failed_packet_ids": summary.get("attempt_packet_ids", []),
                "failure_classes": summary.get("failure_classes", []),
                "source_authorization_packet_id": summary.get(
                    "source_authorization_packet_id"
                ),
                "source_work_order_packet_id": summary.get(
                    "source_work_order_packet_id"
                ),
                "stop_test_triggered": summary.get("stop_test_triggered"),
            }
    return statuses


def _scan_packet_ids(root: Path, *, production: bool) -> list[dict[str, object]]:
    if not root.exists():
        return []
    findings = []
    for path in sorted(root.rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(lines, start=1):
            matches = sorted(set(PACKET_ID_PATTERN.findall(line)))
            if not matches:
                continue
            context = "\n".join(lines[max(0, index - 4) : min(len(lines), index + 3)])
            findings.append(
                {
                    "path": str(path.relative_to(root.parent if production else root.parent)),
                    "line": index,
                    "packet_ids": matches,
                    "classification": _classify_packet_id_reference(
                        path,
                        line,
                        context,
                        production=production,
                    ),
                    "source_kind": "production" if production else "test_fixture",
                    "line_excerpt": line.strip()[:240],
                }
            )
    return findings


def _classify_packet_id_reference(
    path: Path,
    line: str,
    context: str,
    *,
    production: bool,
) -> str:
    if not production:
        return "test_fixture_usage"
    lowered = f"{path.as_posix()} {line} {context}".lower()
    if (
        "known_packet_chain" in lowered
        or "stale" in lowered
        or "historical" in lowered
        or "compat" in lowered
        or "discovery" in lowered
    ):
        return "allowed_history_discovery"
    if "fixture" in lowered:
        return "allowed_fixture_loader"
    return "suspicious_run_specific_logic"


def _target_notes(target_id: str) -> list[str]:
    notes = []
    if target_id in {
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    }:
        notes.append("current run marks this target paused/exhausted when failed memory is present")
    if target_id != OBJECT_MOTION_CAUSALITY_TARGET_ID:
        notes.append(
            "some work-order artifacts may still use legacy object_motion_* filenames for compatibility"
        )
    return notes


def _gate_result(
    gate_name: str,
    passed: bool,
    blocking_defects: list[str] | None = None,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": blocking_defects or ([] if passed else [f"{gate_name} failed"]),
    }


def _load_packet_payloads(
    packet_dir: Path,
    artifact_types: tuple[str, ...],
    label: str,
) -> dict[str, dict[str, Any]]:
    payloads = {}
    for artifact_type in artifact_types:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                f"Architecture/evidence-risk checkpoint refused; {label} packet "
                f"missing {path.name}."
            )
        payload = _read_optional_payload(path)
        if not payload:
            raise ValueError(
                f"Architecture/evidence-risk checkpoint refused; {label} packet "
                f"{path.name} has no object payload."
            )
        payloads[artifact_type] = payload
    return payloads


def _read_optional_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    return payload if isinstance(payload, dict) else {}


def _optional_packet_dir(
    config: AbiConfig,
    run_id: str,
    family: str,
    *payloads: dict[str, Any],
    path_keys: tuple[str, ...],
    id_keys: tuple[str, ...],
) -> Path | None:
    for payload in payloads:
        for key in path_keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return _resolve_path(config, value)
    for payload in payloads:
        for key in id_keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return config.run_dir(run_id) / family / value
    return None


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
    return row_to_artifact(row) if row is not None else None


def _artifact_ids_from_packet(packet: dict[str, Any]) -> dict[str, str]:
    artifact_ids = packet.get("artifact_ids")
    if not isinstance(artifact_ids, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in artifact_ids.items()
        if isinstance(value, str) and value
    }


def _cleanup_packet(subject: ArchitectureEvidenceRiskSubject) -> dict[str, Any]:
    return subject.loop_cleanup_payloads.get("loop_integrity_cleanup_packet", {})


def _loop_review_packet(subject: ArchitectureEvidenceRiskSubject) -> dict[str, Any]:
    return subject.loop_review_payloads["evidence_loop_review_packet"]


def _rival_pressure(subject: ArchitectureEvidenceRiskSubject) -> dict[str, Any]:
    return subject.synthesis_payloads.get("rival_pressure_summary", {})


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return (config.root / value).resolve()


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _unique(values: object) -> list[str]:
    result = []
    for value in values:
        if not value:
            continue
        text = str(value)
        if text not in result:
            result.append(text)
    return result


def _refusal(
    *,
    authorization_packet: Path,
    message: str,
) -> ArchitectureEvidenceRiskCheckpointResult:
    return ArchitectureEvidenceRiskCheckpointResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "authorization_packet": str(authorization_packet),
            "message": message,
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
