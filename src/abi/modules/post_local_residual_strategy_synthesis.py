"""Deterministic post-local residual strategy synthesis packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.residual_targets import (
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    PROOF_NO_ANSWER_RESIDUE_TARGET_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_LINEAGE_ID = (
    "post_local_residual_strategy_synthesis_v1"
)
POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_CREATED_BY = (
    "post_local_residual_strategy_synthesis_v1_controller"
)

POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_DIRECTION_ID = (
    "post_local_residual_strategy_synthesis"
)
RECOMMENDED_STRATEGY_CLASS = "strongest_rival_forensic_diagnosis"
RECOMMENDED_NEXT_ACTION = (
    "review_post_local_strategy_synthesis_before_strongest_rival_forensic_diagnosis"
)

EXPECTED_CURRENT_BEST_PACKET_ID = "packet_0063"
EXPECTED_PROOF_PACKET_ID = "packet_0034"
EXPECTED_READER_STATE_PACKET_ID = "packet_0013"

FAILED_LOCAL_RESIDUAL_TARGET_IDS = (
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    PROOF_NO_ANSWER_RESIDUE_TARGET_ID,
)
INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS = (
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
)

POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_ARTIFACT_TYPES = (
    "source_direction_review_intake_summary",
    "failed_local_residual_path_summary",
    "current_best_evidence_state",
    "local_residual_exhaustion_report",
    "higher_order_strategy_option_map",
    "recommended_next_strategy_class",
    "forbidden_next_moves",
    "generation_lock_report",
    "post_local_strategy_gate_report",
    "post_local_residual_strategy_synthesis_packet",
)

REQUIRED_DIRECTION_REVIEW_ARTIFACTS = (
    "checkpoint_strategy_direction_review_packet",
    "selected_checkpoint_direction_contract",
    "source_strategy_intake_summary",
    "source_checkpoint_intake_summary",
    "generation_lock_report",
    "checkpoint_strategy_direction_gate_report",
)

LEGACY_DIRECTION_RATIONALE_ARTIFACT = "proof_no_answer_residue_rationale"


@dataclass(frozen=True)
class PostLocalResidualStrategySynthesisResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class PostLocalResidualStrategySynthesisSubject:
    run_id: str
    direction_review_packet_dir: Path
    direction_review_packet_id: str
    direction_review_packet_artifact_id: str | None
    direction_review_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    legacy_direction_rationale_artifact_seen: bool


def run_post_local_residual_strategy_synthesis(
    config: AbiConfig,
    *,
    direction_review_packet: Path | str,
    operator_reviewed: bool,
) -> PostLocalResidualStrategySynthesisResult:
    initialize_database(config)
    direction_review_packet_dir = _resolve_path(config, direction_review_packet)
    if not operator_reviewed:
        return _refusal(
            direction_review_packet=direction_review_packet_dir,
            message=(
                "Post-local residual strategy synthesis refused; "
                "--operator-reviewed is required."
            ),
        )
    if (
        not direction_review_packet_dir.exists()
        or not direction_review_packet_dir.is_dir()
    ):
        return _refusal(
            direction_review_packet=direction_review_packet_dir,
            message=(
                "Post-local residual strategy synthesis refused; direction "
                f"review packet directory not found: {direction_review_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, direction_review_packet_dir)
    except ValueError as error:
        return _refusal(
            direction_review_packet=direction_review_packet_dir,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                direction_review_packet=direction_review_packet_dir,
                message=(
                    "Post-local residual strategy synthesis refused; run is "
                    f"not registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "post_local_residual_strategy_synthesis"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_LINEAGE_ID,
            created_by=POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_direction_review_intake_summary"] = (
            _build_source_direction_review_intake_summary(subject, packet_dir)
        )
        artifacts["source_direction_review_intake_summary"] = writer.write_artifact(
            "source_direction_review_intake_summary",
            payloads["source_direction_review_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["failed_local_residual_path_summary"] = (
            _build_failed_local_residual_path_summary(subject)
        )
        artifacts["failed_local_residual_path_summary"] = writer.write_artifact(
            "failed_local_residual_path_summary",
            payloads["failed_local_residual_path_summary"],
            parent_ids=[artifacts["source_direction_review_intake_summary"].id],
        )

        payloads["current_best_evidence_state"] = _build_current_best_evidence_state(
            subject
        )
        artifacts["current_best_evidence_state"] = writer.write_artifact(
            "current_best_evidence_state",
            payloads["current_best_evidence_state"],
            parent_ids=[artifacts["source_direction_review_intake_summary"].id],
        )

        payloads["local_residual_exhaustion_report"] = (
            _build_local_residual_exhaustion_report(subject)
        )
        artifacts["local_residual_exhaustion_report"] = writer.write_artifact(
            "local_residual_exhaustion_report",
            payloads["local_residual_exhaustion_report"],
            parent_ids=[
                artifacts["failed_local_residual_path_summary"].id,
                artifacts["current_best_evidence_state"].id,
            ],
        )

        payloads["higher_order_strategy_option_map"] = (
            _build_higher_order_strategy_option_map(subject)
        )
        artifacts["higher_order_strategy_option_map"] = writer.write_artifact(
            "higher_order_strategy_option_map",
            payloads["higher_order_strategy_option_map"],
            parent_ids=[artifacts["local_residual_exhaustion_report"].id],
        )

        payloads["recommended_next_strategy_class"] = (
            _build_recommended_next_strategy_class(subject)
        )
        artifacts["recommended_next_strategy_class"] = writer.write_artifact(
            "recommended_next_strategy_class",
            payloads["recommended_next_strategy_class"],
            parent_ids=[artifacts["higher_order_strategy_option_map"].id],
        )

        payloads["forbidden_next_moves"] = _build_forbidden_next_moves(subject)
        artifacts["forbidden_next_moves"] = writer.write_artifact(
            "forbidden_next_moves",
            payloads["forbidden_next_moves"],
            parent_ids=[artifacts["recommended_next_strategy_class"].id],
        )

        payloads["generation_lock_report"] = _build_generation_lock_report(subject)
        artifacts["generation_lock_report"] = writer.write_artifact(
            "generation_lock_report",
            payloads["generation_lock_report"],
            parent_ids=[
                artifacts["recommended_next_strategy_class"].id,
                artifacts["forbidden_next_moves"].id,
            ],
        )

        payloads["post_local_strategy_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["post_local_strategy_gate_report"] = writer.write_artifact(
            "post_local_strategy_gate_report",
            payloads["post_local_strategy_gate_report"],
            parent_ids=[
                artifacts["source_direction_review_intake_summary"].id,
                artifacts["local_residual_exhaustion_report"].id,
                artifacts["generation_lock_report"].id,
            ],
        )

        payloads["post_local_residual_strategy_synthesis_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["post_local_residual_strategy_synthesis_packet"] = (
            writer.write_artifact(
                "post_local_residual_strategy_synthesis_packet",
                payloads["post_local_residual_strategy_synthesis_packet"],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type
                    != "post_local_residual_strategy_synthesis_packet"
                ],
            )
        )

        gate_report = payloads["post_local_strategy_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="post_local_strategy_synthesis_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return PostLocalResidualStrategySynthesisResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    direction_review_packet_dir: Path,
) -> PostLocalResidualStrategySynthesisSubject:
    payloads = _load_required_payloads(direction_review_packet_dir)
    _validate_direction_review_payloads(payloads)
    packet = payloads["checkpoint_strategy_direction_review_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Post-local residual strategy synthesis refused; direction review "
        "packet missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or direction_review_packet_dir.name)
    packet_path = (
        direction_review_packet_dir / "checkpoint_strategy_direction_review_packet.json"
    )
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    return PostLocalResidualStrategySynthesisSubject(
        run_id=run_id,
        direction_review_packet_dir=direction_review_packet_dir,
        direction_review_packet_id=packet_id,
        direction_review_packet_artifact_id=packet_artifact.id
        if packet_artifact
        else None,
        direction_review_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        legacy_direction_rationale_artifact_seen=(
            LEGACY_DIRECTION_RATIONALE_ARTIFACT in payloads
        ),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_DIRECTION_REVIEW_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Post-local residual strategy synthesis refused; direction "
                f"review packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    legacy_path = packet_dir / f"{LEGACY_DIRECTION_RATIONALE_ARTIFACT}.json"
    if legacy_path.exists():
        payloads[LEGACY_DIRECTION_RATIONALE_ARTIFACT] = _read_envelope_payload(
            legacy_path
        )
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Post-local residual strategy synthesis refused; malformed "
            f"direction review artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_direction_review_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["checkpoint_strategy_direction_review_packet"]
    contract = payloads["selected_checkpoint_direction_contract"]
    source_strategy = payloads["source_strategy_intake_summary"]
    source_checkpoint = payloads["source_checkpoint_intake_summary"]
    generation_lock = payloads["generation_lock_report"]
    gate_report = payloads["checkpoint_strategy_direction_gate_report"]

    selected = _required_string(
        packet.get("selected_checkpoint_direction_id"),
        "Post-local residual strategy synthesis refused; direction review "
        "packet missing selected_checkpoint_direction_id.",
    )
    for payload_name, payload in (
        ("selected_checkpoint_direction_contract", contract),
        ("source_strategy_intake_summary", source_strategy),
        ("generation_lock_report", generation_lock),
        ("checkpoint_strategy_direction_gate_report", gate_report),
    ):
        if payload.get("selected_checkpoint_direction_id") != selected:
            raise ValueError(
                "Post-local residual strategy synthesis refused; selected "
                f"direction mismatch in {payload_name}."
            )
    if selected != POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_DIRECTION_ID:
        raise ValueError(
            "Post-local residual strategy synthesis refused; direction review "
            "did not select post_local_residual_strategy_synthesis."
        )
    if contract.get("direction_id") != POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_DIRECTION_ID:
        raise ValueError(
            "Post-local residual strategy synthesis refused; selected direction "
            "contract does not identify the post-local direction."
        )
    if source_strategy.get("strategy_packet_checkpoint_aware") is not True:
        raise ValueError(
            "Post-local residual strategy synthesis refused; source strategy "
            "did not consume an architecture checkpoint."
        )
    if not source_strategy.get("source_architecture_checkpoint_packet_id"):
        raise ValueError(
            "Post-local residual strategy synthesis refused; source strategy "
            "missing architecture checkpoint reference."
        )
    if source_checkpoint.get("checkpoint_reviewed") is not True:
        raise ValueError(
            "Post-local residual strategy synthesis refused; source checkpoint "
            "was not reviewed."
        )
    if (
        source_checkpoint.get("generation_locked_by_checkpoint") is not True
        or source_checkpoint.get("checkpoint_permits_generation") is True
    ):
        raise ValueError(
            "Post-local residual strategy synthesis refused; source checkpoint "
            "has generation authorized or is not generation-locked."
        )
    failed_targets = set(
        _string_list(source_checkpoint.get("failed_local_residual_generation_targets"))
    )
    if not set(FAILED_LOCAL_RESIDUAL_TARGET_IDS).issubset(failed_targets):
        raise ValueError(
            "Post-local residual strategy synthesis refused; source checkpoint "
            "does not include all three failed local residual targets."
        )
    for field_name, expected in (
        ("current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID),
        ("proof_packet_id", EXPECTED_PROOF_PACKET_ID),
        ("reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID),
    ):
        value = _first_string(packet.get(field_name), source_strategy.get(field_name))
        if value != expected:
            raise ValueError(
                "Post-local residual strategy synthesis refused; "
                f"{field_name} must be {expected}."
            )
    if _any_true(
        payloads,
        (
            "generation_authorized",
            "next_generation_authorized",
            "candidate_generated",
        ),
    ):
        raise ValueError(
            "Post-local residual strategy synthesis refused; direction review "
            "or source strategy authorizes generation or generated a candidate."
        )
    if _any_true(payloads, ("residual_target_selected",)):
        raise ValueError(
            "Post-local residual strategy synthesis refused; direction review "
            "selected a residual target."
        )
    if _any_true(payloads, ("work_order_created",)):
        raise ValueError(
            "Post-local residual strategy synthesis refused; direction review "
            "created a work order."
        )
    if _model_calls(payloads) != 0:
        raise ValueError(
            "Post-local residual strategy synthesis refused; direction review "
            "contains model calls."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Post-local residual strategy synthesis refused; finality or "
            "phase-shift claim appears in the direction review packet."
        )


def _build_source_direction_review_intake_summary(
    subject: PostLocalResidualStrategySynthesisSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["checkpoint_strategy_direction_review_packet"]
    contract = subject.payloads["selected_checkpoint_direction_contract"]
    source_strategy = subject.payloads["source_strategy_intake_summary"]
    source_checkpoint = subject.payloads["source_checkpoint_intake_summary"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_direction_review_packet_id": subject.direction_review_packet_id,
        "source_direction_review_packet_dir": str(subject.direction_review_packet_dir),
        "source_direction_review_packet_artifact_id": (
            subject.direction_review_packet_artifact_id
        ),
        "source_strategy_packet_id": packet.get("source_strategy_packet_id"),
        "source_strategy_packet_dir": source_strategy.get("source_strategy_packet_dir"),
        "source_architecture_checkpoint_packet_id": packet.get(
            "source_architecture_checkpoint_packet_id"
        ),
        "source_architecture_checkpoint_packet_dir": source_checkpoint.get(
            "source_architecture_checkpoint_packet_dir"
        ),
        "selected_checkpoint_direction_id": packet.get(
            "selected_checkpoint_direction_id"
        ),
        "direction_contract_id": contract.get("direction_id"),
        "legacy_direction_rationale_artifact_name_seen": (
            LEGACY_DIRECTION_RATIONALE_ARTIFACT
            if subject.legacy_direction_rationale_artifact_seen
            else None
        ),
        "legacy_direction_rationale_artifact_ignored_for_direction_resolution": (
            subject.legacy_direction_rationale_artifact_seen
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_direction_review_intake_summary_v1_controller",
    }


def _build_failed_local_residual_path_summary(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    source_checkpoint = subject.payloads["source_checkpoint_intake_summary"]
    failed_targets = _ordered_failed_targets(source_checkpoint)
    return {
        "failed_local_residual_targets": failed_targets,
        "failed_target_count": len(failed_targets),
        "failed_paths": [
            {
                "target_id": HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
                "status": "paused_or_exhausted_pending_strategy_review",
                "summary": (
                    "hostile scaffold failed after repeated materiality and "
                    "semantic attempts"
                ),
                "generation_retry_recommended": False,
                "diagnostic_only": True,
            },
            {
                "target_id": ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
                "status": "paused_or_exhausted_pending_strategy_review",
                "summary": (
                    "ending-return failed after repeated reset, global-relation, "
                    "and object-pressure attempts"
                ),
                "generation_retry_recommended": False,
                "diagnostic_only": True,
            },
            {
                "target_id": PROOF_NO_ANSWER_RESIDUE_TARGET_ID,
                "status": "paused_or_exhausted_pending_strategy_review",
                "summary": (
                    "proof-no-answer failed after repeated object-carry and "
                    "answer-absence attempts"
                ),
                "generation_retry_recommended": False,
                "diagnostic_only": True,
            },
        ],
        "local_residual_retry_recommended": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "failed_local_residual_path_summary_v1_controller",
    }


def _build_current_best_evidence_state(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    packet = subject.payloads["checkpoint_strategy_direction_review_packet"]
    return {
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "integrated_current_best_path_targets": list(
            INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS
        ),
        "strongest_rival_still_blocks": True,
        "reader_state_transformation_status": "partial",
        "proof_status": "useful_but_insufficient",
        "current_best_preserved": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "current_best_evidence_state_v1_controller",
    }


def _build_local_residual_exhaustion_report(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    return {
        "local_residual_patching_exhausted_or_currently_nonproductive": True,
        "local_residual_retry_recommended": False,
        "reasons": [
            "hostile scaffold failed after repeated materiality/semantic attempts",
            (
                "ending-return failed after repeated reset/global-relation/"
                "object-pressure attempts"
            ),
            (
                "proof-no-answer failed after repeated object-carry/"
                "answer-absence attempts"
            ),
            (
                "object-motion and tactile are already integrated current-best "
                "path mechanisms, not ordinary repeat options"
            ),
            "strongest rival still blocks",
            "reader-state transformation is partial",
            "finalization remains ineligible",
        ],
        "failed_local_residual_targets": _ordered_failed_targets(
            subject.payloads["source_checkpoint_intake_summary"]
        ),
        "integrated_current_best_path_targets": list(
            INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS
        ),
        "strongest_rival_still_blocks": True,
        "reader_state_transformation_status": "partial",
        "finalization_eligible": False,
        "candidate_generated": False,
        "model_calls": 0,
        "no_phase_shift_claim": True,
        "worker": "local_residual_exhaustion_report_v1_controller",
    }


def _build_higher_order_strategy_option_map(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    del subject
    options = [
        {
            "rank": 1,
            "strategy_class": "strongest_rival_forensic_diagnosis",
            "recommended": True,
            "purpose": (
                "identify why the rival still beats packet_0063 without "
                "imitating it"
            ),
            "generation_authorized": False,
            "likely_next_step": "model-backed or deterministic forensic comparison packet",
            "preserve": [
                "packet_0063",
                "failed-target memory",
                "strongest-rival pressure without imitation",
            ],
        },
        {
            "rank": 2,
            "strategy_class": "local_law_discovery_strengthening",
            "recommended": False,
            "purpose": (
                "infer the governing local law that packet_0063 is failing to "
                "make inevitable"
            ),
            "generation_authorized": False,
            "likely_next_step": "internal reader/local-law diagnostic packet",
            "preserve": ["packet_0063", "object/tactile gains"],
        },
        {
            "rank": 3,
            "strategy_class": "nonlocal_macro_recomposition_strategy",
            "recommended": False,
            "purpose": (
                "move above one-region patching and redesign a broader "
                "transformation path"
            ),
            "generation_authorized": False,
            "likely_next_step": "nonlocal macro work-order planning",
            "preserve": ["packet_0063 evidence basis", "failed local memory"],
        },
        {
            "rank": 4,
            "strategy_class": "reader_state_failure_decomposition",
            "recommended": False,
            "purpose": (
                "decompose partial reader-state transformation into precise "
                "subfailures"
            ),
            "generation_authorized": False,
            "likely_next_step": "targeted internal reader-state diagnostic",
            "preserve": ["reader-state packet_0013", "current best packet_0063"],
        },
        {
            "rank": 5,
            "strategy_class": "pause_local_generation_for_autonomous_loop_controller",
            "recommended": False,
            "purpose": "recognize controller limits before another creative attempt",
            "generation_authorized": False,
            "likely_next_step": "operator/controller review only",
            "preserve": ["all current evidence", "fail-closed controller limits"],
        },
    ]
    return {
        "strategy_options": options,
        "recommended_strategy_class": RECOMMENDED_STRATEGY_CLASS,
        "recommended_next_targets": [],
        "exhausted_local_targets_recommended_as_next_targets": [],
        "failed_local_residual_targets": list(FAILED_LOCAL_RESIDUAL_TARGET_IDS),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "higher_order_strategy_option_map_v1_controller",
    }


def _build_recommended_next_strategy_class(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    del subject
    return {
        "recommended_strategy_class": RECOMMENDED_STRATEGY_CLASS,
        "recommended_next_action": RECOMMENDED_NEXT_ACTION,
        "rationale": (
            "The strongest rival has remained the high-severity blocker across "
            "multiple cycles. Local residual patching has failed, so Abi needs "
            "to identify what the rival is doing that packet_0063 is not doing "
            "without copying the rival."
        ),
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "recommended_next_strategy_class_v1_controller",
    }


def _build_forbidden_next_moves(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    del subject
    return {
        "forbidden_next_moves": [
            "run OpenAI",
            "generate candidate",
            "authorize generation",
            "select residual target",
            "create work order",
            "run ablation",
            "run reader-state evaluation",
            "run evidence synthesis",
            "finalize",
            "retry exhausted local residual targets",
            "repeat object-motion or tactile as ordinary local targets",
            "claim improvement",
            "claim strongest-rival defeat",
            "claim finality",
            "claim phase shift",
        ],
        "exhausted_local_residual_targets": list(FAILED_LOCAL_RESIDUAL_TARGET_IDS),
        "integrated_current_best_path_targets": list(
            INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS
        ),
        "candidate_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "forbidden_next_moves_v1_controller",
    }


def _build_generation_lock_report(
    subject: PostLocalResidualStrategySynthesisSubject,
) -> dict[str, object]:
    packet = subject.payloads["checkpoint_strategy_direction_review_packet"]
    return {
        "source_direction_review_packet_id": subject.direction_review_packet_id,
        "selected_checkpoint_direction_id": packet.get(
            "selected_checkpoint_direction_id"
        ),
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_evaluation_authorized": False,
        "live_model_call_authorized": False,
        "model_calls": 0,
        "local_residual_retry_recommended": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "post_local_strategy_generation_lock_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: PostLocalResidualStrategySynthesisSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    lock = payloads["generation_lock_report"]
    gate_results = [
        _gate_result("direction_review_packet_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("post_local_direction_selected", True),
        _gate_result("source_strategy_checkpoint_aware", True),
        _gate_result("failed_local_targets_present", True),
        _gate_result("current_best_preserved", True),
        _gate_result("generation_locked", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "generation_authorized",
            False,
            ["post-local strategy synthesis does not authorize generation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["post-local strategy synthesis is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "strongest rival remains blocking",
        "reader-state transformation remains partial",
        "higher-order strategy has not been implemented",
        "generation remains unauthorized",
        "candidate has not been generated",
        "finalization remains refused",
    ]
    return {
        "passed": False,
        "eligible": False,
        "source_direction_review_packet_id": subject.direction_review_packet_id,
        "recommended_strategy_class": RECOMMENDED_STRATEGY_CLASS,
        "generation_authorized": lock["generation_authorized"],
        "next_generation_authorized": lock["next_generation_authorized"],
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Post-local residual strategy synthesis selected a higher-order "
            "strategy class only; generation remains locked."
        ),
        "worker": "post_local_strategy_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: PostLocalResidualStrategySynthesisSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    direction_packet = subject.payloads["checkpoint_strategy_direction_review_packet"]
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="post_local_residual_strategy_synthesis_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "post_local_residual_strategy_synthesis_packet",
        ],
        "counts": {
            **artifact_counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 0,
            "residual_target_selection_artifacts_created": 0,
        },
        "source_direction_review_packet_id": subject.direction_review_packet_id,
        "source_strategy_packet_id": direction_packet.get("source_strategy_packet_id"),
        "source_architecture_checkpoint_packet_id": direction_packet.get(
            "source_architecture_checkpoint_packet_id"
        ),
        "current_best_candidate_packet_id": direction_packet.get(
            "current_best_candidate_packet_id"
        ),
        "proof_packet_id": direction_packet.get("proof_packet_id"),
        "reader_state_packet_id": direction_packet.get("reader_state_packet_id"),
        "selected_checkpoint_direction_id": direction_packet.get(
            "selected_checkpoint_direction_id"
        ),
        "failed_local_residual_targets": list(FAILED_LOCAL_RESIDUAL_TARGET_IDS),
        "integrated_current_best_path_targets": list(
            INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS
        ),
        "local_residual_retry_recommended": False,
        "recommended_strategy_class": RECOMMENDED_STRATEGY_CLASS,
        "recommended_next_action": RECOMMENDED_NEXT_ACTION,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_report": payloads["post_local_strategy_gate_report"],
        "worker": "post_local_residual_strategy_synthesis_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["post_local_residual_strategy_synthesis_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _ordered_failed_targets(source_checkpoint: dict[str, Any]) -> list[str]:
    found = set(
        _string_list(source_checkpoint.get("failed_local_residual_generation_targets"))
    )
    return [target_id for target_id in FAILED_LOCAL_RESIDUAL_TARGET_IDS if target_id in found]


def _any_true(
    payloads: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> bool:
    for payload in payloads.values():
        for field_name in field_names:
            if payload.get(field_name) is True:
                return True
        counts = _as_dict(payload.get("counts"))
        if (
            "candidate_generated" in field_names
            and _int_or_zero(counts.get("candidate_artifacts_created"))
        ):
            return True
        if (
            "work_order_created" in field_names
            and _int_or_zero(counts.get("work_order_artifacts_created"))
        ):
            return True
        if (
            "residual_target_selected" in field_names
            and _int_or_zero(counts.get("residual_target_selection_artifacts_created"))
        ):
            return True
    return False


def _model_calls(payloads: dict[str, dict[str, Any]]) -> int:
    total = 0
    for payload in payloads.values():
        total += _int_or_zero(payload.get("model_calls"))
        total += _int_or_zero(_as_dict(payload.get("counts")).get("model_calls"))
    return total


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    for payload in payloads.values():
        if _payload_has_final_or_phase_claim(payload):
            return True
    return False


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"finalization_eligible", "final_artifact", "final_claim"}:
                if item is True:
                    return True
            if key in {"phase_shift_claim", "strongest_rival_defeated"}:
                if item is True:
                    return True
            if key in {"no_final_claim", "no_phase_shift_claim"}:
                if item is False:
                    return True
            if _payload_has_final_or_phase_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_final_or_phase_claim(item) for item in value)
    return False


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
    direction_review_packet: Path,
    message: str,
) -> PostLocalResidualStrategySynthesisResult:
    return PostLocalResidualStrategySynthesisResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "direction_review_packet": str(direction_review_packet),
            "candidate_generated": False,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "residual_target_selected": False,
            "work_order_created": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
        },
    )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, tuple):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []


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


def _unique(values: object) -> list[str]:
    result = []
    for value in values:
        if not value:
            continue
        text = str(value)
        if text not in result:
            result.append(text)
    return result
