"""Evidence-grounded next-target strategy packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NEXT_TARGET_STRATEGY_ACTIVE_PHASE,
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


NEXT_TARGET_STRATEGY_LINEAGE_ID = "next_target_strategy_v1"
NEXT_TARGET_STRATEGY_CREATED_BY = "next_target_strategy_v1_controller"

NEXT_TARGET_STRATEGY_ARTIFACT_TYPES = (
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

REQUIRED_SYNTHESIS_FILES = (
    "autonomous_evidence_synthesis_packet",
    "best_current_candidate_selection",
    "reader_state_evidence_adjudication",
    "reader_state_tension_report",
    "residual_blocker_map",
    "rival_pressure_summary",
    "local_law_case_notes",
    "strategic_decision_report",
    "macro_recomposition_brief",
)

REQUIRED_LOOP_REVIEW_FILES = (
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

REQUIRED_AUTHORIZATION_FILES = (
    "supervised_cycle_authorization_subject_manifest",
    "loop_review_intake_summary",
    "operator_review_record",
    "cleanup_resolution_report",
    "supervised_next_cycle_readiness_report",
    "next_cycle_scope_constraints",
    "authorization_gate_report",
    "supervised_cycle_authorization_packet",
)

REQUIRED_LOOP_CLEANUP_FILES = LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES

REPEATED_BROAD_TARGET_ID = "first_read_object_event_pressure_gap"
ATTEMPTED_BROAD_TARGET_IDS = (
    "reader_state_informed_macro_2",
    REPEATED_BROAD_TARGET_ID,
    "object_motion_causality_specificity",
)
SAFE_RESIDUAL_CHOICE_TARGET_ID = "next_residual_target_requires_operator_choice"
SAFE_RESIDUAL_CHOICE_ACTION = "review_narrow_residual_target_options_before_generation"

RESIDUAL_TARGET_OPTIONS = (
    (
        "tactile_inevitability_gap",
        "Make the object field feel less optional on first encounter.",
    ),
    (
        "object_motion_causality_specificity",
        "Specify how object movement causes consequence before explanation.",
    ),
    (
        "rival_level_first_read_vividness",
        "Address the strongest rival's first-read vividness advantage.",
    ),
    (
        "hostile_scaffold_visibility",
        "Reduce thesis/scaffold visibility without thinning causal embodiment.",
    ),
    (
        "proof_no_answer_residue",
        "Keep no-outside-answer pressure embodied rather than abstract.",
    ),
    (
        "ending_explains_return_risk",
        "Prevent the ending from explaining the return instead of enacting it.",
    ),
    (
        "local_busyness_decorative_detail_risk",
        "Avoid adding lively details that do not carry causal pressure.",
    ),
)


@dataclass(frozen=True)
class NextTargetStrategyResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class StrategySubject:
    run_id: str
    input_mode: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_packet_artifact_id: str | None
    synthesis_artifact_ids: dict[str, str]
    authorization_packet_dir: Path | None
    authorization_packet_id: str | None
    authorization_packet_artifact_id: str | None
    authorization_artifact_ids: dict[str, str]
    authorization_payloads: dict[str, dict[str, Any]]
    loop_cleanup_packet_dir: Path | None
    loop_cleanup_packet_id: str | None
    loop_cleanup_packet_artifact_id: str | None
    loop_cleanup_artifact_ids: dict[str, str]
    loop_cleanup_payloads: dict[str, dict[str, Any]]
    loop_review_packet_dir: Path | None
    loop_review_packet_id: str | None
    loop_review_packet_artifact_id: str | None
    loop_review_artifact_ids: dict[str, str]
    loop_review_payloads: dict[str, dict[str, Any]]
    completed_cycles: int
    next_strategy_authorized: bool
    next_generation_authorized: bool
    repeated_target_report: dict[str, Any]
    exhausted_or_attempted_target_ids: tuple[str, ...]
    payloads: dict[str, dict[str, Any]]
    selected_candidate: dict[str, Any]
    reader_state: dict[str, Any]
    residual_blockers: dict[str, Any]
    rival_pressure: dict[str, Any]
    macro_brief: dict[str, Any]
    strategic_decision: dict[str, Any]
    source_parent_ids: tuple[str, ...]


def run_next_target_strategy(
    config: AbiConfig,
    *,
    synthesis_packet: Path | str | None = None,
    authorization_packet: Path | str | None = None,
) -> NextTargetStrategyResult:
    initialize_database(config)
    if (synthesis_packet is None) == (authorization_packet is None):
        return _refusal(
            message=(
                "Next-target strategy refused; pass exactly one of "
                "--synthesis-packet or --authorization-packet."
            ),
        )

    try:
        if authorization_packet is not None:
            authorization_packet_dir = _resolve_path(config, authorization_packet)
            if not authorization_packet_dir.exists() or not authorization_packet_dir.is_dir():
                return _refusal(
                    authorization_packet=authorization_packet_dir,
                    message=(
                        "Next-target strategy refused; authorization packet "
                        f"directory not found: {authorization_packet_dir}"
                    ),
                )
            subject = _load_authorized_subject(config, authorization_packet_dir)
        else:
            synthesis_packet_dir = _resolve_path(config, synthesis_packet or "")
            if not synthesis_packet_dir.exists() or not synthesis_packet_dir.is_dir():
                return _refusal(
                    synthesis_packet=synthesis_packet_dir,
                    message=(
                        "Next-target strategy refused; synthesis packet directory "
                        f"not found: {synthesis_packet_dir}"
                    ),
                )
            subject = _load_synthesis_subject(config, synthesis_packet_dir)
            stale_message = _synthesis_only_refusal_message(config, subject)
            if stale_message is not None:
                return _refusal(
                    synthesis_packet=synthesis_packet_dir,
                    message=stale_message,
                )
    except ValueError as error:
        return _refusal(
            synthesis_packet=_resolve_path(config, synthesis_packet)
            if synthesis_packet is not None
            else None,
            authorization_packet=_resolve_path(config, authorization_packet)
            if authorization_packet is not None
            else None,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                synthesis_packet=synthesis_packet_dir,
                message=(
                    "Next-target strategy refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NEXT_TARGET_STRATEGY_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "next_target_strategy")
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NEXT_TARGET_STRATEGY_LINEAGE_ID,
            created_by=NEXT_TARGET_STRATEGY_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["next_target_strategy_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir,
        )
        artifacts["next_target_strategy_subject_manifest"] = writer.write_artifact(
            "next_target_strategy_subject_manifest",
            payloads["next_target_strategy_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["source_evidence_summary"] = _build_source_evidence_summary(subject)
        artifacts["source_evidence_summary"] = writer.write_artifact(
            "source_evidence_summary",
            payloads["source_evidence_summary"],
            parent_ids=[
                artifacts["next_target_strategy_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["current_best_candidate_summary"] = _build_current_best_candidate_summary(
            subject
        )
        artifacts["current_best_candidate_summary"] = writer.write_artifact(
            "current_best_candidate_summary",
            payloads["current_best_candidate_summary"],
            parent_ids=[artifacts["source_evidence_summary"].id],
        )

        payloads["reader_state_blocker_summary"] = _build_reader_state_blocker_summary(
            subject
        )
        artifacts["reader_state_blocker_summary"] = writer.write_artifact(
            "reader_state_blocker_summary",
            payloads["reader_state_blocker_summary"],
            parent_ids=[artifacts["source_evidence_summary"].id],
        )

        payloads["strongest_rival_pressure_delta"] = _build_strongest_rival_pressure_delta(
            subject
        )
        artifacts["strongest_rival_pressure_delta"] = writer.write_artifact(
            "strongest_rival_pressure_delta",
            payloads["strongest_rival_pressure_delta"],
            parent_ids=[
                artifacts["source_evidence_summary"].id,
                artifacts["reader_state_blocker_summary"].id,
            ],
        )

        payloads["protected_effects_and_forbidden_changes"] = (
            _build_protected_effects_and_forbidden_changes(subject)
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[artifacts["current_best_candidate_summary"].id],
        )

        payloads["object_event_pressure_target_map"] = (
            _build_object_event_pressure_target_map(subject)
        )
        artifacts["object_event_pressure_target_map"] = writer.write_artifact(
            "object_event_pressure_target_map",
            payloads["object_event_pressure_target_map"],
            parent_ids=[
                artifacts["reader_state_blocker_summary"].id,
                artifacts["strongest_rival_pressure_delta"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["residual_target_option_map"] = _build_residual_target_option_map(
            subject
        )
        artifacts["residual_target_option_map"] = writer.write_artifact(
            "residual_target_option_map",
            payloads["residual_target_option_map"],
            parent_ids=[
                artifacts["object_event_pressure_target_map"].id,
                artifacts["reader_state_blocker_summary"].id,
                artifacts["strongest_rival_pressure_delta"].id,
            ],
        )

        payloads["candidate_region_pressure_map"] = _build_candidate_region_pressure_map(
            subject
        )
        artifacts["candidate_region_pressure_map"] = writer.write_artifact(
            "candidate_region_pressure_map",
            payloads["candidate_region_pressure_map"],
            parent_ids=[
                artifacts["residual_target_option_map"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["next_intervention_strategy"] = _build_next_intervention_strategy(
            subject,
            payloads["reader_state_blocker_summary"],
        )
        artifacts["next_intervention_strategy"] = writer.write_artifact(
            "next_intervention_strategy",
            payloads["next_intervention_strategy"],
            parent_ids=[
                artifacts["residual_target_option_map"].id,
                artifacts["candidate_region_pressure_map"].id,
            ],
        )

        payloads["ablation_and_reader_eval_plan"] = _build_ablation_and_reader_eval_plan(
            subject
        )
        artifacts["ablation_and_reader_eval_plan"] = writer.write_artifact(
            "ablation_and_reader_eval_plan",
            payloads["ablation_and_reader_eval_plan"],
            parent_ids=[
                artifacts["next_intervention_strategy"].id,
                artifacts["current_best_candidate_summary"].id,
            ],
        )

        payloads["next_target_strategy_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["next_target_strategy_gate_report"] = writer.write_artifact(
            "next_target_strategy_gate_report",
            payloads["next_target_strategy_gate_report"],
            parent_ids=[
                artifacts["source_evidence_summary"].id,
                artifacts["reader_state_blocker_summary"].id,
                artifacts["next_intervention_strategy"].id,
                artifacts["ablation_and_reader_eval_plan"].id,
            ],
        )

        payloads["next_target_strategy_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["next_target_strategy_packet"] = writer.write_artifact(
            "next_target_strategy_packet",
            payloads["next_target_strategy_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "next_target_strategy_packet"
            ],
        )

        gate_report = payloads["next_target_strategy_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="next_target_strategy_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NEXT_TARGET_STRATEGY_LINEAGE_ID,
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
        "counts": payloads["next_target_strategy_packet"]["counts"],
        "current_best_candidate": {
            "packet_id": subject.selected_candidate["packet_id"],
            "packet_kind": subject.selected_candidate.get("packet_kind"),
            "packet_dir": subject.selected_candidate.get("packet_dir"),
        },
        "current_best_candidate_packet_id": subject.selected_candidate["packet_id"],
        "proof_packet_id": subject.selected_candidate.get("proof_packet_id"),
        "reader_state_packet_id": subject.reader_state.get("packet_id"),
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "authorization_packet_id": subject.authorization_packet_id,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "completed_cycles": subject.completed_cycles,
        "next_strategy_authorized": subject.next_strategy_authorized,
        "next_generation_authorized": subject.next_generation_authorized,
        "next_recommended_action": payloads["next_intervention_strategy"][
            "recommended_action"
        ],
        "primary_next_target": payloads["residual_target_option_map"][
            "primary_next_target"
        ],
        "primary_next_subtarget": payloads["residual_target_option_map"][
            "primary_next_subtarget"
        ],
        "target_name": payloads["residual_target_option_map"]["primary_next_target"],
        "repeated_target_detected": subject.repeated_target_report[
            "repeated_target_detected"
        ],
        "repeated_target_id": subject.repeated_target_report["repeated_target_id"],
        "exhausted_or_attempted_target_ids": list(
            subject.exhausted_or_attempted_target_ids
        ),
        "residual_target_option_map": payloads["residual_target_option_map"],
        "same_broad_target_allowed": subject.repeated_target_report[
            "same_broad_target_allowed"
        ],
        "strongest_rival_still_blocks": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
    }
    return NextTargetStrategyResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_synthesis_subject(config: AbiConfig, synthesis_packet_dir: Path) -> StrategySubject:
    payloads = _load_required_payloads(synthesis_packet_dir)
    synthesis_packet = payloads["autonomous_evidence_synthesis_packet"]
    if not isinstance(synthesis_packet.get("run_id"), str):
        raise ValueError("Next-target strategy refused; synthesis packet missing run_id.")
    run_id = str(synthesis_packet["run_id"])
    best = payloads["best_current_candidate_selection"]
    selected = best.get("selected_best_candidate")
    if not isinstance(selected, dict):
        raise ValueError(
            "Next-target strategy refused; synthesis packet missing best_current_candidate."
        )
    if not selected.get("reader_state_evaluated"):
        raise ValueError(
            "Next-target strategy refused; selected candidate has no reader-state evaluation."
        )
    reader_state = payloads["reader_state_evidence_adjudication"]
    if not reader_state.get("reader_state_evidence_present"):
        raise ValueError(
            "Next-target strategy refused; reader-state evidence is not present."
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
    return StrategySubject(
        run_id=run_id,
        input_mode="synthesis",
        synthesis_packet_dir=synthesis_packet_dir,
        synthesis_packet_id=str(synthesis_packet.get("packet_id") or synthesis_packet_dir.name),
        synthesis_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        synthesis_artifact_ids={
            str(key): str(value)
            for key, value in synthesis_packet.get("artifact_ids", {}).items()
            if isinstance(value, str)
        },
        authorization_packet_dir=None,
        authorization_packet_id=None,
        authorization_packet_artifact_id=None,
        authorization_artifact_ids={},
        authorization_payloads={},
        loop_cleanup_packet_dir=None,
        loop_cleanup_packet_id=None,
        loop_cleanup_packet_artifact_id=None,
        loop_cleanup_artifact_ids={},
        loop_cleanup_payloads={},
        loop_review_packet_dir=None,
        loop_review_packet_id=None,
        loop_review_packet_artifact_id=None,
        loop_review_artifact_ids={},
        loop_review_payloads={},
        completed_cycles=0,
        next_strategy_authorized=False,
        next_generation_authorized=False,
        repeated_target_report=_build_repeated_target_report(
            selected_candidate=selected,
            loop_review_payloads={},
            authorization_packet_id=None,
            exhausted_or_attempted_target_ids=_attempted_target_ids(
                selected_candidate=selected,
                cleanup_payloads={},
                loop_review_payloads={},
            ),
        ),
        exhausted_or_attempted_target_ids=tuple(
            _attempted_target_ids(
                selected_candidate=selected,
                cleanup_payloads={},
                loop_review_payloads={},
            )
        ),
        payloads=payloads,
        selected_candidate=selected,
        reader_state=reader_state,
        residual_blockers=payloads["residual_blocker_map"],
        rival_pressure=payloads["rival_pressure_summary"],
        macro_brief=payloads["macro_recomposition_brief"],
        strategic_decision=payloads["strategic_decision_report"],
        source_parent_ids=tuple(parent_ids),
    )


def _load_authorized_subject(
    config: AbiConfig,
    authorization_packet_dir: Path,
) -> StrategySubject:
    authorization_payloads = _load_packet_payloads(
        authorization_packet_dir,
        REQUIRED_AUTHORIZATION_FILES,
        "authorization",
    )
    authorization_packet_payload = authorization_payloads[
        "supervised_cycle_authorization_packet"
    ]
    authorization_manifest = authorization_payloads[
        "supervised_cycle_authorization_subject_manifest"
    ]
    run_id = authorization_packet_payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Next-target strategy refused; authorization packet missing run_id.")
    if authorization_packet_payload.get("next_strategy_authorized") is not True:
        raise ValueError(
            "Next-target strategy refused; authorization packet does not authorize "
            "next strategy planning."
        )
    if authorization_packet_payload.get("next_generation_authorized") is True:
        raise ValueError(
            "Next-target strategy refused; authorization packet authorizes generation, "
            "which is out of scope for next-target planning."
        )

    loop_cleanup_dir: Path | None = None
    loop_cleanup_payloads: dict[str, dict[str, Any]] = {}
    loop_cleanup_artifact: ArtifactRecord | None = None
    loop_cleanup_artifact_ids: dict[str, str] = {}
    source_loop_cleanup_packet_id = _first_string(
        authorization_packet_payload.get("source_loop_cleanup_packet_id"),
        authorization_manifest.get("source_loop_cleanup_packet_id"),
    )
    if source_loop_cleanup_packet_id:
        loop_cleanup_dir = _payload_dir(
            config,
            authorization_packet_payload,
            authorization_manifest,
            "source_loop_cleanup_packet_dir",
        )
        if not loop_cleanup_dir.exists() or not loop_cleanup_dir.is_dir():
            raise ValueError(
                "Next-target strategy refused; linked loop-cleanup packet "
                f"directory not found: {loop_cleanup_dir}"
            )
        loop_cleanup_payloads = _load_packet_payloads(
            loop_cleanup_dir,
            REQUIRED_LOOP_CLEANUP_FILES,
            "loop-cleanup",
        )
        cleanup_packet = loop_cleanup_payloads["loop_integrity_cleanup_packet"]
        if (
            str(cleanup_packet.get("packet_id") or loop_cleanup_dir.name)
            != source_loop_cleanup_packet_id
        ):
            raise ValueError(
                "Next-target strategy refused; authorization cleanup packet ID "
                "does not match linked cleanup packet."
            )
        if cleanup_packet.get("loop_integrity_cleanup_completed") is not True:
            raise ValueError(
                "Next-target strategy refused; linked cleanup checkpoint is not completed."
            )
        if cleanup_packet.get("next_generation_authorized") is True:
            raise ValueError(
                "Next-target strategy refused; linked cleanup checkpoint authorizes generation."
            )
        loop_review_dir = _payload_dir(
            config,
            cleanup_packet,
            loop_cleanup_payloads["active_evidence_state_checkpoint"],
            "source_loop_review_packet_dir",
        )
    else:
        loop_review_dir = _payload_dir(
            config,
            authorization_packet_payload,
            authorization_manifest,
            "loop_review_packet_dir",
        )
    if not loop_review_dir.exists() or not loop_review_dir.is_dir():
        raise ValueError(
            "Next-target strategy refused; linked loop-review packet directory "
            f"not found: {loop_review_dir}"
        )
    loop_review_payloads = _load_packet_payloads(
        loop_review_dir,
        REQUIRED_LOOP_REVIEW_FILES,
        "loop-review",
    )
    loop_packet = loop_review_payloads["evidence_loop_review_packet"]
    loop_manifest = loop_review_payloads["evidence_loop_review_subject_manifest"]
    if loop_packet.get("accepted") is False:
        raise ValueError("Next-target strategy refused; linked loop-review refused.")

    if loop_cleanup_payloads:
        synthesis_dir = _payload_dir(
            config,
            loop_cleanup_payloads["loop_integrity_cleanup_packet"],
            loop_cleanup_payloads["active_evidence_state_checkpoint"],
            "source_synthesis_packet_dir",
        )
    else:
        synthesis_dir = _payload_dir(
            config,
            authorization_packet_payload,
            loop_manifest,
            "source_synthesis_packet_dir",
        )
    subject = _load_synthesis_subject(config, synthesis_dir)

    _validate_authorized_chain(
        subject=subject,
        authorization_packet=authorization_packet_payload,
        authorization_manifest=authorization_manifest,
        cleanup_payloads=loop_cleanup_payloads,
        loop_packet=loop_packet,
        loop_manifest=loop_manifest,
    )

    authorization_path = authorization_packet_dir / "supervised_cycle_authorization_packet.json"
    loop_path = loop_review_dir / "evidence_loop_review_packet.json"
    cleanup_path = (
        loop_cleanup_dir / "loop_integrity_cleanup_packet.json"
        if loop_cleanup_dir is not None
        else None
    )
    with connect(config.db_path) as connection:
        authorization_artifact = _artifact_for_path(connection, authorization_path)
        loop_artifact = _artifact_for_path(connection, loop_path)
        loop_cleanup_artifact = (
            _artifact_for_path(connection, cleanup_path)
            if cleanup_path is not None
            else None
        )

    authorization_artifact_ids = _artifact_ids_from_packet(authorization_packet_payload)
    loop_artifact_ids = _artifact_ids_from_packet(loop_packet)
    if loop_cleanup_payloads:
        loop_cleanup_artifact_ids = _artifact_ids_from_packet(
            loop_cleanup_payloads["loop_integrity_cleanup_packet"]
        )
    parent_ids = _unique(
        [
            authorization_artifact.id if authorization_artifact else None,
            loop_cleanup_artifact.id if loop_cleanup_artifact else None,
            loop_artifact.id if loop_artifact else None,
            *authorization_artifact_ids.values(),
            *loop_cleanup_artifact_ids.values(),
            *loop_artifact_ids.values(),
            *subject.source_parent_ids,
        ]
    )
    attempted_target_ids = _attempted_target_ids(
        selected_candidate=subject.selected_candidate,
        cleanup_payloads=loop_cleanup_payloads,
        loop_review_payloads=loop_review_payloads,
    )
    repeated_target_report = _build_repeated_target_report(
        selected_candidate=subject.selected_candidate,
        loop_review_payloads=loop_review_payloads,
        authorization_packet_id=str(
            authorization_packet_payload.get("packet_id") or authorization_packet_dir.name
        ),
        exhausted_or_attempted_target_ids=attempted_target_ids,
    )
    return StrategySubject(
        run_id=subject.run_id,
        input_mode="authorization",
        synthesis_packet_dir=subject.synthesis_packet_dir,
        synthesis_packet_id=subject.synthesis_packet_id,
        synthesis_packet_artifact_id=subject.synthesis_packet_artifact_id,
        synthesis_artifact_ids=subject.synthesis_artifact_ids,
        authorization_packet_dir=authorization_packet_dir,
        authorization_packet_id=str(
            authorization_packet_payload.get("packet_id") or authorization_packet_dir.name
        ),
        authorization_packet_artifact_id=authorization_artifact.id
        if authorization_artifact
        else None,
        authorization_artifact_ids=authorization_artifact_ids,
        authorization_payloads=authorization_payloads,
        loop_cleanup_packet_dir=loop_cleanup_dir,
        loop_cleanup_packet_id=source_loop_cleanup_packet_id or None,
        loop_cleanup_packet_artifact_id=loop_cleanup_artifact.id
        if loop_cleanup_artifact
        else None,
        loop_cleanup_artifact_ids=loop_cleanup_artifact_ids,
        loop_cleanup_payloads=loop_cleanup_payloads,
        loop_review_packet_dir=loop_review_dir,
        loop_review_packet_id=str(loop_packet.get("packet_id") or loop_review_dir.name),
        loop_review_packet_artifact_id=loop_artifact.id if loop_artifact else None,
        loop_review_artifact_ids=loop_artifact_ids,
        loop_review_payloads=loop_review_payloads,
        completed_cycles=int(
            authorization_packet_payload.get("completed_cycles")
            or loop_packet.get("completed_cycle_count")
            or loop_packet.get("completed_cycles")
            or 0
        ),
        next_strategy_authorized=True,
        next_generation_authorized=False,
        repeated_target_report=repeated_target_report,
        exhausted_or_attempted_target_ids=tuple(attempted_target_ids),
        payloads=subject.payloads,
        selected_candidate=subject.selected_candidate,
        reader_state=subject.reader_state,
        residual_blockers=subject.residual_blockers,
        rival_pressure=subject.rival_pressure,
        macro_brief=subject.macro_brief,
        strategic_decision=subject.strategic_decision,
        source_parent_ids=tuple(parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_SYNTHESIS_FILES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Next-target strategy refused; synthesis packet missing "
                f"{path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Next-target strategy refused; malformed synthesis artifact: "
                f"{path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    if not payloads["autonomous_evidence_synthesis_packet"].get("best_current_candidate"):
        raise ValueError(
            "Next-target strategy refused; synthesis packet missing best_current_candidate."
        )
    return payloads


def _load_packet_payloads(
    packet_dir: Path,
    artifact_types: tuple[str, ...],
    packet_label: str,
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in artifact_types:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Next-target strategy refused; "
                f"{packet_label} packet missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Next-target strategy refused; malformed "
                f"{packet_label} artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _payload_dir(
    config: AbiConfig,
    primary: dict[str, Any],
    fallback: dict[str, Any],
    key: str,
) -> Path:
    value = primary.get(key) or fallback.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Next-target strategy refused; linked {key} is missing.")
    return _resolve_path(config, value)


def _artifact_ids_from_packet(packet_payload: dict[str, Any]) -> dict[str, str]:
    artifact_ids = packet_payload.get("artifact_ids")
    if not isinstance(artifact_ids, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in artifact_ids.items()
        if isinstance(value, str)
    }


def _validate_authorized_chain(
    *,
    subject: StrategySubject,
    authorization_packet: dict[str, Any],
    authorization_manifest: dict[str, Any],
    cleanup_payloads: dict[str, dict[str, Any]],
    loop_packet: dict[str, Any],
    loop_manifest: dict[str, Any],
) -> None:
    cleanup_packet = cleanup_payloads.get("loop_integrity_cleanup_packet", {})
    cleanup_checkpoint = cleanup_payloads.get("active_evidence_state_checkpoint", {})
    expected_synthesis_id = _first_string(
        authorization_packet.get("source_synthesis_packet_id"),
        authorization_manifest.get("source_synthesis_packet_id"),
        cleanup_packet.get("source_synthesis_packet_id"),
        cleanup_checkpoint.get("synthesis_packet_id"),
        loop_packet.get("source_synthesis_packet_id"),
        loop_manifest.get("source_synthesis_packet_id"),
    )
    if expected_synthesis_id and expected_synthesis_id != subject.synthesis_packet_id:
        raise ValueError(
            "Next-target strategy refused; authorization source synthesis does "
            "not match the loaded synthesis packet."
        )

    expected_best = _first_string(
        authorization_packet.get("current_best_candidate_packet_id"),
        authorization_manifest.get("current_best_candidate_packet_id"),
        cleanup_packet.get("current_best_candidate_packet_id"),
        cleanup_checkpoint.get("current_best_candidate_packet_id"),
        loop_packet.get("current_best_candidate_packet_id"),
        loop_manifest.get("current_best_candidate_packet_id"),
    )
    if not expected_best:
        raise ValueError("Next-target strategy refused; current best candidate is missing.")
    if expected_best != str(subject.selected_candidate.get("packet_id") or ""):
        raise ValueError(
            "Next-target strategy refused; authorization current best does not "
            "match source synthesis."
        )

    expected_proof = _first_string(
        authorization_packet.get("proof_packet_id"),
        authorization_manifest.get("proof_packet_id"),
        cleanup_packet.get("proof_packet_id"),
        cleanup_checkpoint.get("proof_packet_id"),
        loop_packet.get("proof_packet_id"),
        loop_manifest.get("proof_packet_id"),
    )
    if not expected_proof:
        raise ValueError("Next-target strategy refused; proof packet is missing.")
    if expected_proof != str(subject.selected_candidate.get("proof_packet_id") or ""):
        raise ValueError(
            "Next-target strategy refused; authorization proof packet does not "
            "match source synthesis."
        )

    expected_reader = _first_string(
        authorization_packet.get("reader_state_packet_id"),
        authorization_manifest.get("reader_state_packet_id"),
        cleanup_packet.get("reader_state_packet_id"),
        cleanup_checkpoint.get("reader_state_packet_id"),
        loop_packet.get("reader_state_packet_id"),
        loop_manifest.get("reader_state_packet_id"),
    )
    reader_id = str(
        subject.selected_candidate.get("reader_state_packet_id")
        or subject.reader_state.get("packet_id")
        or ""
    )
    if not expected_reader:
        raise ValueError("Next-target strategy refused; reader-state packet is missing.")
    if expected_reader != reader_id:
        raise ValueError(
            "Next-target strategy refused; authorization reader-state packet does "
            "not match source synthesis."
        )


def _synthesis_only_refusal_message(
    config: AbiConfig,
    subject: StrategySubject,
) -> str | None:
    authorization_dir = _latest_packet_linking_synthesis(
        config,
        run_id=subject.run_id,
        family="supervised_cycle_authorization",
        packet_artifact_type="supervised_cycle_authorization_packet",
        source_synthesis_packet_id=subject.synthesis_packet_id,
    )
    if authorization_dir is not None:
        return (
            "Next-target strategy refused; this synthesis already has a later "
            "supervised authorization. Use --authorization-packet "
            f"{authorization_dir}."
        )
    loop_review_dir = _latest_packet_linking_synthesis(
        config,
        run_id=subject.run_id,
        family="evidence_loop_review",
        packet_artifact_type="evidence_loop_review_packet",
        source_synthesis_packet_id=subject.synthesis_packet_id,
    )
    if loop_review_dir is not None:
        return (
            "Next-target strategy refused; this synthesis already has a later "
            "loop-review packet. Use supervised authorization before planning "
            f"the next target: {loop_review_dir}."
        )
    return None


def _latest_packet_linking_synthesis(
    config: AbiConfig,
    *,
    run_id: str,
    family: str,
    packet_artifact_type: str,
    source_synthesis_packet_id: str,
) -> Path | None:
    base_dir = config.run_dir(run_id) / family
    if not base_dir.exists():
        return None
    packet_dirs = sorted(
        [child for child in base_dir.glob("packet_*") if child.is_dir()],
        key=lambda path: path.name,
    )
    for packet_dir in reversed(packet_dirs):
        path = packet_dir / f"{packet_artifact_type}.json"
        if not path.exists():
            continue
        envelope = read_json_file(path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        if payload.get("source_synthesis_packet_id") == source_synthesis_packet_id:
            return packet_dir
    return None


def _build_repeated_target_report(
    *,
    selected_candidate: dict[str, Any],
    loop_review_payloads: dict[str, dict[str, Any]],
    authorization_packet_id: str | None,
    exhausted_or_attempted_target_ids: list[str],
) -> dict[str, Any]:
    current_target = str(
        selected_candidate.get("target_scope")
        or selected_candidate.get("target_movement")
        or ""
    )
    loop_packet = loop_review_payloads.get("evidence_loop_review_packet", {})
    drift_guard = _as_dict(loop_packet.get("repeated_target_drift_guard"))
    detected = (
        current_target == REPEATED_BROAD_TARGET_ID
        or current_target in exhausted_or_attempted_target_ids
        or drift_guard.get("repeated_target_drift_detected") is True
    )
    return {
        "repeated_target_detected": detected,
        "repeated_target_id": current_target if detected and current_target else None,
        "repeated_broad_target_id": REPEATED_BROAD_TARGET_ID if detected else None,
        "current_target_id": current_target or None,
        "exhausted_or_attempted_target_ids": list(exhausted_or_attempted_target_ids),
        "prior_target_strategy_packet_id": _prior_strategy_packet_id(selected_candidate),
        "prior_candidate_packet_id": selected_candidate.get("packet_id"),
        "prior_ablation_packet_id": selected_candidate.get("proof_packet_id"),
        "prior_reader_state_packet_id": selected_candidate.get("reader_state_packet_id"),
        "source_loop_review_packet_id": loop_packet.get("packet_id"),
        "source_authorization_packet_id": authorization_packet_id,
        "same_broad_target_allowed": False if detected else True,
        "same_broad_target_justification": "",
        "narrower_subtarget_required": bool(detected),
        "repeated_broad_target_authorized": False,
        "guard_checked": bool(loop_review_payloads) or detected,
    }


def _attempted_target_ids(
    *,
    selected_candidate: dict[str, Any],
    cleanup_payloads: dict[str, dict[str, Any]],
    loop_review_payloads: dict[str, dict[str, Any]],
) -> list[str]:
    attempted: list[str] = [*ATTEMPTED_BROAD_TARGET_IDS] if cleanup_payloads else []
    current_target = _first_string(
        selected_candidate.get("target_scope"),
        selected_candidate.get("target_movement"),
        selected_candidate.get("selected_residual_target_id"),
    )
    if cleanup_payloads and current_target:
        attempted.append(current_target)
    prior_cycle = cleanup_payloads.get("prior_cycle_supersession_map", {})
    cycles = prior_cycle.get("cycles")
    if isinstance(cycles, list):
        for cycle in cycles:
            if not isinstance(cycle, dict):
                continue
            cycle_id = str(cycle.get("cycle_id") or "")
            if "macro" in cycle_id:
                attempted.append("reader_state_informed_macro_2")
            if "object_event" in cycle_id:
                attempted.append(REPEATED_BROAD_TARGET_ID)
            if "residual_object_motion" in cycle_id:
                attempted.append("object_motion_causality_specificity")
    loop_packet = loop_review_payloads.get("evidence_loop_review_packet", {})
    drift_guard = _as_dict(loop_packet.get("repeated_target_drift_guard"))
    repeated_target = _first_string(
        drift_guard.get("current_target_id"),
        drift_guard.get("repeated_target_id"),
    )
    if repeated_target:
        attempted.append(repeated_target)
    return _unique(attempted)


def _prior_strategy_packet_id(selected_candidate: dict[str, Any]) -> str | None:
    packet_dir = selected_candidate.get("packet_dir")
    if not isinstance(packet_dir, str) or not packet_dir:
        return None
    manifest_path = Path(packet_dir) / "macro_recomposition_subject_manifest.json"
    if not manifest_path.exists():
        return None
    envelope = read_json_file(manifest_path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        return None
    strategy_id = payload.get("source_strategy_packet_id")
    return str(strategy_id) if isinstance(strategy_id, str) and strategy_id else None


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _build_subject_manifest(subject: StrategySubject, packet_dir: Path) -> dict[str, object]:
    selected = subject.selected_candidate
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "input_mode": subject.input_mode,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_packet_artifact_id": subject.synthesis_packet_artifact_id,
        "authorization_packet_id": subject.authorization_packet_id,
        "authorization_packet_dir": str(subject.authorization_packet_dir)
        if subject.authorization_packet_dir
        else None,
        "authorization_packet_artifact_id": subject.authorization_packet_artifact_id,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_cleanup_packet_dir": str(subject.loop_cleanup_packet_dir)
        if subject.loop_cleanup_packet_dir
        else None,
        "loop_cleanup_packet_artifact_id": subject.loop_cleanup_packet_artifact_id,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "loop_review_packet_dir": str(subject.loop_review_packet_dir)
        if subject.loop_review_packet_dir
        else None,
        "loop_review_packet_artifact_id": subject.loop_review_packet_artifact_id,
        "completed_cycles": subject.completed_cycles,
        "next_strategy_authorized": subject.next_strategy_authorized,
        "next_generation_authorized": subject.next_generation_authorized,
        "current_best_candidate_packet_id": selected.get("packet_id"),
        "current_best_candidate_packet_kind": selected.get("packet_kind"),
        "current_best_candidate_packet_dir": selected.get("packet_dir"),
        "selected_candidate_text_sha256": selected.get("text_sha256"),
        "proof_packet_id": selected.get("proof_packet_id"),
        "proof_packet_dir": selected.get("proof_packet_dir"),
        "reader_state_eval_packet_id": subject.reader_state.get("packet_id"),
        "reader_state_eval_packet_dir": subject.reader_state.get("packet_dir"),
        "prior_best_packet_id": selected.get("base_candidate_packet_id"),
        "repeated_target_report": subject.repeated_target_report,
        "exhausted_or_attempted_target_ids": list(
            subject.exhausted_or_attempted_target_ids
        ),
        "strongest_rival_still_blocks": True,
        "candidate_generated": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "next_target_strategy_subject_manifest_v1_controller",
    }


def _build_source_evidence_summary(subject: StrategySubject) -> dict[str, object]:
    selected = subject.selected_candidate
    reader = subject.reader_state
    candidate_id = str(selected.get("packet_id") or "selected candidate")
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "current_best_candidate_packet_id": selected.get("packet_id"),
        "proof_packet_id": selected.get("proof_packet_id"),
        "reader_state_packet_id": reader.get("packet_id"),
        "exhausted_or_attempted_target_ids": list(
            subject.exhausted_or_attempted_target_ids
        ),
        "evidence_findings": [
            f"{candidate_id} has executed-ablation support",
            f"{candidate_id} has reader-state support",
            "reader-state transformation is partial, not decisive",
            "strongest rival still blocks",
            "proof/no-answer and return improved but remain incomplete",
            "first-read object-event pressure remains weaker than strongest rival",
            "internal evidence is model-internal, not human data",
            f"{candidate_id} remains non-final",
        ],
        "ablation_support_status": selected.get("proof_causal_status"),
        "reader_state_strength": reader.get("reread_transformation_strength"),
        "post_reread_reader_state": reader.get("post_reread_reader_state"),
        "proof_no_outside_answer_carry_status": reader.get(
            "proof_no_outside_answer_carry_status"
        ),
        "final_return_echo_status": reader.get("final_return_echo_status"),
        "first_read_object_event_pressure_status": reader.get(
            "first_read_object_event_pressure_status"
        ),
        "strongest_rival_status": reader.get("strongest_rival_status"),
        "fixture_only": False,
        "not_human_data": True,
        "candidate_final": False,
        "no_phase_shift_claim": True,
        "worker": "source_evidence_summary_v1_controller",
    }


def _build_current_best_candidate_summary(subject: StrategySubject) -> dict[str, object]:
    selected = subject.selected_candidate
    candidate_id = str(selected.get("packet_id") or "selected candidate")
    prior_id = str(selected.get("base_candidate_packet_id") or "prior best")
    return {
        "current_best_candidate_packet_id": selected.get("packet_id"),
        "current_best_candidate_packet_kind": selected.get("packet_kind"),
        "current_best_candidate_packet_dir": selected.get("packet_dir"),
        "candidate_text_sha256": selected.get("text_sha256"),
        "superseded_prior_best_packet_id": selected.get("base_candidate_packet_id"),
        "why_current_best_superseded_prior_best": [
            f"{candidate_id} preserved {prior_id} as base rather than discarding it",
            f"{candidate_id} has linked executed-ablation proof",
            f"{candidate_id} has linked reader-state evidence",
            "reader-state evidence supports partial reread gain without finality",
        ],
        "what_current_best_improved": [
            "structural return",
            "partial reread transformation",
            "local object field causality after reread",
            "reduced overexplanation",
            "proof/no-answer scene binding",
        ],
        "what_current_best_must_preserve": [
            "table/dust/spoon/saucer/ring causal field",
            "reduced overexplanation",
            "partial opening-return gains",
            "proof/no-outside-answer gains",
            f"macro structure of {candidate_id}",
        ],
        "what_remains_unresolved": _ranked_blocker_ids(subject),
        "why_no_new_candidate_before_strategy_review": (
            "The residual target has shifted toward first-read object-event "
            "pressure and must be operationalized before generation."
        ),
        "candidate_generated": False,
        "candidate_final": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "current_best_candidate_summary_v1_controller",
    }


def _build_reader_state_blocker_summary(subject: StrategySubject) -> dict[str, object]:
    ranked_ids = [
        "first_read_object_event_pressure_gap",
        "strongest_rival_still_winning",
        "lived_object_causality_gap",
        "first_read_vividness_gap",
        "proof_no_outside_answer_carry_still_partial",
        "final_return_echo_still_partial",
        "thesis_visible_scaffold_risk",
        "local_embodiment_vs_conceptual_compression_balance",
    ]
    blockers = [
        {
            "rank": index,
            "blocker_id": blocker_id,
            "status": "active",
            "evidence_basis": _blocker_evidence_basis(blocker_id, subject),
            "should_drive_next_target": index <= 4,
        }
        for index, blocker_id in enumerate(ranked_ids, start=1)
    ]
    return {
        "ranked_blockers": blockers,
        "active_blocker_ids": ranked_ids,
        "top_blocker_id": "first_read_object_event_pressure_gap",
        "prior_proof_no_answer_handle_status": "improved_but_not_solved",
        "do_not_continue_proof_no_answer_compression_by_inertia": True,
        "next_target_should_follow_evidence_not_previous_momentum": True,
        "reader_state_tensions": subject.payloads["reader_state_tension_report"].get(
            "tensions",
            [],
        ),
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "reader_state_blocker_summary_v1_controller",
    }


def _build_strongest_rival_pressure_delta(subject: StrategySubject) -> dict[str, object]:
    candidate_id = str(subject.selected_candidate.get("packet_id") or "current best")
    return {
        "strongest_rival_still_blocks": True,
        "where_current_best_narrows_gap": [
            "partial reread transformation",
            "more coherent structural return",
            "more causal table/dust/spoon/saucer/ring field after reread",
            "less visible overexplanation than prior macro candidate",
        ],
        "where_rival_still_wins": [
            "first-read vividness",
            "lived object-event pressure",
            "sharper object-motion causality",
            "concrete consequence",
            "tactile inevitability",
            "less visible scaffold",
        ],
        "rival_strength_to_target_next": "first-read lived object-event pressure without copying rival identity",
        "rival_traits_not_to_copy_blindly": [
            "surface vividness without Abi's reread structure",
            "different symbolic field",
            "decorative narrative furniture",
            "rival voice or premise",
        ],
        "would_damage_abi_if": [
            f"{candidate_id} macro structure is weakened",
            "table/dust/spoon/saucer/ring field stops carrying proof",
            "vividness becomes decorative rather than causal",
            "proof/no-answer becomes abstract explanation again",
        ],
        "strongest_rival_comparison_passed": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "strongest_rival_pressure_delta_v1_controller",
    }


def _build_protected_effects_and_forbidden_changes(
    subject: StrategySubject,
) -> dict[str, object]:
    candidate_id = str(subject.selected_candidate.get("packet_id") or "current best")
    return {
        "protected_effects": [
            f"{candidate_id} partial reread transformation",
            "table/dust/spoon/saucer/ring causal field",
            "reduced overexplanation",
            "proof/no-outside-answer gains",
            "final-return / opening-return gains",
            "local field as record-bearing system",
            "strongest-rival pressure preservation",
            "no finality claim",
        ],
        "forbidden_changes": [
            "local patch treadmill",
            "more abstract proof language",
            "summary compression",
            "decorative vividness",
            "adding narrative furniture without causal function",
            "turning Abi candidate into the rival",
            f"weakening {candidate_id} macro structure",
            "weakening table/dust/spoon/saucer/ring causal field",
            "declaring rival defeated",
            "declaring phase shift",
            "writing a new candidate in this command",
        ],
        "candidate_generated": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_object_event_pressure_target_map(subject: StrategySubject) -> dict[str, object]:
    candidate_id = str(subject.selected_candidate.get("packet_id") or "current best")
    repeated = subject.repeated_target_report["repeated_target_detected"] is True
    target_name = (
        SAFE_RESIDUAL_CHOICE_TARGET_ID if repeated else REPEATED_BROAD_TARGET_ID
    )
    return {
        "target_name": target_name,
        "broad_target_class": REPEATED_BROAD_TARGET_ID,
        "repeated_target_detected": repeated,
        "same_broad_target_allowed": subject.repeated_target_report[
            "same_broad_target_allowed"
        ],
        "primary_next_subtarget": "operator_choice_required" if repeated else None,
        "purpose": (
            "Stop broad object-event targeting from repeating by inertia; require "
            "operator choice among narrower residual subtargets."
        )
        if repeated
        else (
            "Increase first-read embodied pressure without weakening reread "
            f"structure or {candidate_id}'s object-field gains."
        ),
        "what_counts_as_object_event_pressure": [
            "an object changes because another object or action pressures it",
            "the reader can infer consequence before explanation",
            "tactile detail alters causal expectation",
            "the local field feels inevitable on first encounter",
        ],
        "what_counts_as_fake_detail_only_vividness": [
            "extra sensory description with no causal function",
            "decorative furniture added to seem vivid",
            "object lists that do not change pressure",
            "visible explanation disguised as image",
        ],
        "likely_candidate_regions_to_inspect": [
            "opening table/dust/spoon/saucer/ring field",
            "middle recurrence / ordinary trace logic",
            "proof/no-outside-answer region",
            "final return / opening transformation region",
        ],
        "possible_intervention_types": [
            "bounded early/middle scene-pressure recomposition",
            "object-event pressure insertion",
            "sharpened object-motion causality",
            "embodied consequence strengthening",
            "first-read tactile pressure increase",
            "do-nothing/preserve if target cannot be made operational",
        ],
        "protected_local_objects": ["table", "dust", "spoon", "saucer", "ring"],
        "possible_causal_handles": [
            "object motion causes consequence before explanation",
            "ordinary trace becomes pressure-bearing evidence",
            "first-read tactile inevitability increases",
            "rival vividness gap is narrowed without copying rival",
        ],
        "risks_and_uncertainties": [
            "decorative vividness may weaken Abi's macro structure",
            "object-event pressure may become narrative furniture",
            "proof/no-answer may become abstract again",
            "first-read improvement may damage reread preservation",
        ],
        "generation_chosen": False,
        "worker": "object_event_pressure_target_map_v1_controller",
    }


def _build_residual_target_option_map(subject: StrategySubject) -> dict[str, object]:
    repeated = subject.repeated_target_report["repeated_target_detected"] is True
    attempted = set(subject.exhausted_or_attempted_target_ids)
    if repeated:
        primary_next_target = SAFE_RESIDUAL_CHOICE_TARGET_ID
        primary_next_subtarget = "operator_choice_required"
        next_recommended_action = SAFE_RESIDUAL_CHOICE_ACTION
        strategy_decision = "request_operator_choice_among_narrowed_residuals"
    else:
        primary_next_target = REPEATED_BROAD_TARGET_ID
        primary_next_subtarget = "object_event_pressure_operationalization"
        next_recommended_action = "request_operator_review_before_generation"
        strategy_decision = "prepare_bounded_object_event_pressure_recomposition"
    return {
        "primary_next_target": primary_next_target,
        "primary_next_subtarget": primary_next_subtarget,
        "broad_blocker_class": REPEATED_BROAD_TARGET_ID,
        "exhausted_or_attempted_target_ids": list(
            subject.exhausted_or_attempted_target_ids
        ),
        "specific_residual_options": [
            {
                "option_id": option_id,
                "description": description,
                "status": (
                    "attempted_handle_requires_narrower_subtarget"
                    if option_id in attempted
                    else "available_for_operator_selection"
                ),
                "source_evidence_basis": _residual_option_basis(option_id, subject),
                "broad_reuse_authorized": False if option_id in attempted else None,
                "operator_may_select_narrower_subtarget": option_id in attempted,
                "candidate_generation_authorized": False,
            }
            for option_id, description in RESIDUAL_TARGET_OPTIONS
        ],
        "repeated_target_detected": repeated,
        "repeated_target_id": subject.repeated_target_report["repeated_target_id"],
        "same_broad_target_allowed": subject.repeated_target_report[
            "same_broad_target_allowed"
        ],
        "same_broad_target_allowed_only_if_narrow_subtarget_selected": bool(repeated),
        "repeated_broad_target_authorized": False,
        "strategy_decision": strategy_decision,
        "next_recommended_action": next_recommended_action,
        "next_strategy_authorized": subject.next_strategy_authorized,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "residual_target_option_map_v1_controller",
    }


def _build_candidate_region_pressure_map(subject: StrategySubject) -> dict[str, object]:
    residual_target = (
        SAFE_RESIDUAL_CHOICE_TARGET_ID
        if subject.repeated_target_report["repeated_target_detected"] is True
        else REPEATED_BROAD_TARGET_ID
    )
    return {
        "regions": [
            _region(
                "opening_table_dust_spoon_saucer_ring_field",
                "establish record-bearing local field",
                "object field becomes more causal after reread",
                "first-read pressure may still not be vivid enough",
                True,
                "changing too much could damage the opening record field",
                "protect_and_inspect",
            ),
            _region(
                "middle_recurrence_ordinary_trace_logic",
                "turn ordinary traces into causal recurrence",
                "reduced overexplanation and stronger macro structure",
                "may need sharper object-event consequence",
                True,
                "summary compression could thin discovery",
                "plausible_next_intervention_region",
            ),
            _region(
                "proof_no_outside_answer_region",
                "carry no-outside-answer pressure through scene",
                "proof/no-answer became more scene-bound",
                "carry remains partial or partly thesis-visible",
                False,
                "do not repeat proof/no-answer compression by inertia",
                "protect_unless_evidence_selects_narrow_subtarget",
            ),
            _region(
                "final_return_opening_transformation_region",
                "return to opening field with altered record",
                "final-return/opening-return gain is partial",
                "reread strength remains improved but unproven",
                False,
                "assuming the final return must change may miss first-read gap",
                "protect_and_review",
            ),
        ],
        "do_not_assume_final_return_is_next_region": True,
        "primary_pressure_need": residual_target,
        "broad_blocker_class": REPEATED_BROAD_TARGET_ID,
        "operator_must_select_specific_residual_subtarget": (
            subject.repeated_target_report["repeated_target_detected"] is True
        ),
        "not_candidate_artifact": True,
        "no_phase_shift_claim": True,
        "worker": "candidate_region_pressure_map_v1_controller",
    }


def _build_next_intervention_strategy(
    subject: StrategySubject,
    blocker_summary: dict[str, object],
) -> dict[str, object]:
    candidate_id = str(subject.selected_candidate.get("packet_id") or "current best")
    repeated = subject.repeated_target_report["repeated_target_detected"] is True
    return {
        "recommended_action": SAFE_RESIDUAL_CHOICE_ACTION
        if repeated
        else "request_operator_review_before_generation",
        "secondary_recommendation": "choose_narrow_residual_subtarget_before_generation"
        if repeated
        else "prepare_bounded_object_event_pressure_recomposition",
        "strategy": [
            f"preserve {candidate_id} as current best candidate",
            "consume the supervised authorization packet before strategy planning"
            if subject.input_mode == "authorization"
            else "consume the source synthesis packet",
            "do not repeat the broad object-event target without a narrower residual subtarget"
            if repeated
            else "prepare a bounded object-event pressure strategy brief",
            "require operator review before generation",
            "if later authorized, target only the selected residual subtarget"
            if repeated
            else "if authorized, target first-read object-event pressure / lived object causality",
            "do not run another proof/no-answer macro cycle by inertia",
        ],
        "top_ranked_blocker": blocker_summary["top_blocker_id"],
        "next_creative_action_if_authorized": (
            "operator-selected residual subtarget strategy before any generation"
            if repeated
            else (
                "bounded object-event pressure recomposition focused on first-read "
                "lived object causality"
            )
        ),
        "primary_next_target": SAFE_RESIDUAL_CHOICE_TARGET_ID
        if repeated
        else REPEATED_BROAD_TARGET_ID,
        "primary_next_subtarget": "operator_choice_required"
        if repeated
        else "object_event_pressure_operationalization",
        "repeated_target_detected": repeated,
        "same_broad_target_allowed": subject.repeated_target_report[
            "same_broad_target_allowed"
        ],
        "generation_allowed_by_this_packet": False,
        "candidate_generated": False,
        "operator_review_required_before_generation": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "next_intervention_strategy_v1_controller",
    }


def _build_ablation_and_reader_eval_plan(subject: StrategySubject) -> dict[str, object]:
    candidate_id = str(subject.selected_candidate.get("packet_id") or "current best")
    repeated = subject.repeated_target_report["repeated_target_detected"] is True
    return {
        "if_future_candidate_is_generated": [
            f"execute ablation against {candidate_id}",
            "verify the operator-selected residual subtarget is actually addressed"
            if repeated
            else "verify first-read object-event pressure is actually addressed",
            "include a revert of the object-event pressure intervention",
            "isolate the object-event pressure intervention",
            "include an over-vividness / decorative-detail control",
            "run strongest-rival comparison",
            "run reader-state evaluation focused on first-read vividness and reread preservation",
            "preserve fail-closed gates",
        ],
        "required_future_controls": [
            "revert_object_event_pressure_intervention",
            "isolate_object_event_pressure_intervention",
            "over_vividness_decorative_detail_control",
            "strongest_rival_comparison",
        ],
        "reader_eval_focus": [
            "first-read vividness",
            "lived object-event pressure",
            "reread preservation",
            "proof/no-answer carry",
            "hostile scaffold risk",
        ],
        "requires_operator_selected_residual_subtarget": repeated,
        "primary_next_target": SAFE_RESIDUAL_CHOICE_TARGET_ID
        if repeated
        else REPEATED_BROAD_TARGET_ID,
        "primary_next_subtarget": "operator_choice_required"
        if repeated
        else "object_event_pressure_operationalization",
        "next_candidate_generated": False,
        "ablation_completed_for_next_candidate": False,
        "reader_state_eval_completed_for_next_candidate": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "ablation_and_reader_eval_plan_v1_controller",
    }


def _build_gate_report(
    *,
    subject: StrategySubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    selected = subject.selected_candidate
    reader = subject.reader_state
    repeated = subject.repeated_target_report["repeated_target_detected"] is True
    same_broad_allowed = subject.repeated_target_report["same_broad_target_allowed"] is True
    gate_results = [
        _gate_result(
            "authorization_packet_consumed",
            subject.input_mode == "authorization"
            and bool(subject.authorization_packet_id),
        ),
        _gate_result(
            "loop_review_packet_consumed",
            subject.input_mode == "authorization" and bool(subject.loop_review_packet_id),
        ),
        _gate_result(
            "loop_cleanup_packet_consumed",
            subject.loop_cleanup_packet_id is not None,
            ["cleanup-aware authorization was not the source"],
            record=False,
        ),
        _gate_result("source_synthesis_consumed", True),
        _gate_result("current_best_candidate_identified", bool(selected.get("packet_id"))),
        _gate_result("proof_packet_linked", bool(selected.get("proof_packet_id"))),
        _gate_result("reader_state_packet_linked", bool(reader.get("packet_id"))),
        _gate_result(
            "repeated_target_guard_checked",
            bool(subject.repeated_target_report["guard_checked"]),
        ),
        _gate_result(
            "residual_blockers_ranked",
            bool(payloads["reader_state_blocker_summary"].get("ranked_blockers")),
        ),
        _gate_result("strongest_rival_pressure_preserved", True),
        _gate_result("next_target_strategy_created", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "next_candidate_generated",
            False,
            ["strategy packet intentionally generated no candidate"],
            record=False,
        ),
        _gate_result(
            "next_candidate_generation_authorized",
            False,
            ["candidate generation requires a later separate authorization packet"],
            record=False,
        ),
        _gate_result(
            "repeated_broad_target_authorized",
            same_broad_allowed if repeated else False,
            [
                "same broad object-event target cannot be reused without a "
                "narrower operator-selected residual subtarget"
            ]
            if repeated
            else ["no repeated broad target authorization is needed"],
            record=False,
        ),
        _gate_result(
            "ablation_completed_for_next_candidate",
            False,
            ["no next candidate exists to ablate"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_completed_for_next_candidate",
            False,
            ["no next candidate exists to evaluate"],
            record=False,
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            ["first-read object-event pressure and strongest-rival blockers remain"],
            record=False,
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator review required before generation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["strategy packet is not a finalization packet"],
            record=False,
        ),
        _gate_result(
            "phase_shift_claim",
            False,
            ["phase-shift claim is intentionally absent"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "next candidate has not been generated",
        "next-candidate ablation has not been completed",
        "next-candidate reader-state evaluation has not been completed",
        "operator has not selected a narrow residual target"
        if repeated
        else "first-read object-event pressure remains unresolved",
        "strongest rival still blocks",
        "internal operator approval is absent",
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
        "operator_review_required_before_generation": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Next-target strategy consumed supervised authorization and blocks "
            "repeated broad targeting until the operator chooses a narrower "
            "residual subtarget."
        )
        if repeated
        else (
            "Next-target strategy operationalizes first-read object-event "
            "pressure but remains fail-closed and generates no candidate."
        ),
        "worker": "next_target_strategy_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: StrategySubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=NEXT_TARGET_STRATEGY_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="next_target_strategy_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "next_target_strategy_packet"],
        "counts": {
            **artifact_counts,
            "strategy_artifacts": artifact_counts["produced_artifacts"],
            "required_strategy_artifacts": artifact_counts["required_artifacts"],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "authorization_packet_id": subject.authorization_packet_id,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_loop_cleanup_packet_id": subject.loop_cleanup_packet_id,
        "cleanup_checkpoint_consumed": subject.loop_cleanup_packet_id is not None,
        "loop_review_packet_id": subject.loop_review_packet_id,
        "source_loop_review_packet_id": subject.loop_review_packet_id,
        "completed_cycles": subject.completed_cycles,
        "next_strategy_authorized": subject.next_strategy_authorized,
        "next_generation_authorized": subject.next_generation_authorized,
        "current_best_candidate": {
            "packet_id": subject.selected_candidate.get("packet_id"),
            "packet_kind": subject.selected_candidate.get("packet_kind"),
            "packet_dir": subject.selected_candidate.get("packet_dir"),
        },
        "current_best_candidate_packet_id": subject.selected_candidate.get("packet_id"),
        "proof_packet_id": subject.selected_candidate.get("proof_packet_id"),
        "reader_state_packet_id": subject.reader_state.get("packet_id"),
        "primary_next_target": payloads["residual_target_option_map"][
            "primary_next_target"
        ],
        "primary_next_subtarget": payloads["residual_target_option_map"][
            "primary_next_subtarget"
        ],
        "target_name": payloads["residual_target_option_map"]["primary_next_target"],
        "next_recommended_action": payloads["next_intervention_strategy"][
            "recommended_action"
        ],
        "repeated_target_detected": subject.repeated_target_report[
            "repeated_target_detected"
        ],
        "repeated_target_id": subject.repeated_target_report["repeated_target_id"],
        "exhausted_or_attempted_target_ids": list(
            subject.exhausted_or_attempted_target_ids
        ),
        "residual_target_option_map": payloads["residual_target_option_map"],
        "same_broad_target_allowed": subject.repeated_target_report[
            "same_broad_target_allowed"
        ],
        "operator_review_required_before_generation": True,
        "candidate_generated": False,
        "strongest_rival_still_blocks": True,
        "gate_report": payloads["next_target_strategy_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "next_target_strategy_packet_v1_controller",
    }


def _blocker_evidence_basis(blocker_id: str, subject: StrategySubject) -> list[str]:
    reader = subject.reader_state
    basis = {
        "first_read_object_event_pressure_gap": [
            str(reader.get("first_read_object_event_pressure_status")),
            "strongest rival still wins lived object-event pressure",
        ],
        "strongest_rival_still_winning": [
            str(reader.get("strongest_rival_status")),
            "strongest-rival comparison has not passed",
        ],
        "lived_object_causality_gap": [
            "local field gained reread causality but first-read embodiment still lags",
        ],
        "first_read_vividness_gap": ["rival still wins first-read vividness"],
        "proof_no_outside_answer_carry_still_partial": [
            str(reader.get("proof_no_outside_answer_carry_status")),
        ],
        "final_return_echo_still_partial": [
            str(reader.get("final_return_echo_status")),
        ],
        "thesis_visible_scaffold_risk": [
            str(reader.get("hostile_risk_status")),
            ", ".join(str(value) for value in reader.get("hostile_active_risks", [])),
        ],
        "local_embodiment_vs_conceptual_compression_balance": [
            "protect local embodiment while avoiding conceptual compression drift",
        ],
    }
    return basis.get(blocker_id, ["active residual blocker"])


def _residual_option_basis(option_id: str, subject: StrategySubject) -> list[str]:
    reader = subject.reader_state
    basis = {
        "tactile_inevitability_gap": [
            str(reader.get("first_read_vividness_status") or ""),
            "strongest rival still wins tactile inevitability",
        ],
        "object_motion_causality_specificity": [
            str(reader.get("lived_object_causality_status") or ""),
            "object-event pressure remains weaker than strongest rival",
        ],
        "rival_level_first_read_vividness": [
            str(reader.get("strongest_rival_status") or ""),
            "first-read vividness remains a rival pressure point",
        ],
        "hostile_scaffold_visibility": [
            str(reader.get("hostile_risk_status") or ""),
            ", ".join(str(value) for value in reader.get("hostile_active_risks", [])),
        ],
        "proof_no_answer_residue": [
            str(reader.get("proof_no_outside_answer_carry_status") or ""),
            "proof/no-answer pressure remains partial",
        ],
        "ending_explains_return_risk": [
            str(reader.get("final_return_echo_status") or ""),
            "final return still risks explaining rather than enacting return",
        ],
        "local_busyness_decorative_detail_risk": [
            "object-event vividness must not become decorative local busyness",
            "protected table/dust/spoon/saucer/ring field must remain causal",
        ],
    }
    return [
        value
        for value in basis.get(option_id, ["active residual target option"])
        if value
    ]


def _ranked_blocker_ids(subject: StrategySubject) -> list[str]:
    blockers = subject.residual_blockers.get("residual_blockers", [])
    if not isinstance(blockers, list):
        return []
    return [
        str(blocker.get("blocker_id"))
        for blocker in blockers
        if isinstance(blocker, dict) and blocker.get("blocker_id")
    ]


def _region(
    region_id: str,
    current_function: str,
    protected_effect: str,
    remaining_weakness: str,
    plausible_next_intervention_region: bool,
    risk_if_modified: str,
    recommendation: str,
) -> dict[str, object]:
    return {
        "region_id": region_id,
        "current_function": current_function,
        "protected_effect": protected_effect,
        "remaining_weakness": remaining_weakness,
        "plausible_next_intervention_region": plausible_next_intervention_region,
        "risk_if_modified": risk_if_modified,
        "recommendation": recommendation,
    }


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


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return (config.root / value).resolve()


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


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _refusal(
    *,
    synthesis_packet: Path | None = None,
    authorization_packet: Path | None = None,
    message: str,
) -> NextTargetStrategyResult:
    payload = {
        "accepted": False,
        "refused": True,
        "message": message,
        "synthesis_packet": str(synthesis_packet) if synthesis_packet else None,
        "authorization_packet": str(authorization_packet)
        if authorization_packet
        else None,
        "candidate_generated": False,
        "counts": {"model_calls": 0, "candidate_artifacts_created": 0},
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "model_calls": 0,
    }
    return NextTargetStrategyResult(exit_code=1, payload=payload)
