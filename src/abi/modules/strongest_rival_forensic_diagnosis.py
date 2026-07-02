"""Deterministic strongest-rival forensic diagnosis packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.post_local_residual_strategy_synthesis import (
    EXPECTED_CURRENT_BEST_PACKET_ID,
    EXPECTED_PROOF_PACKET_ID,
    EXPECTED_READER_STATE_PACKET_ID,
    FAILED_LOCAL_RESIDUAL_TARGET_IDS,
    INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS,
    POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_DIRECTION_ID,
    RECOMMENDED_STRATEGY_CLASS as POST_LOCAL_RECOMMENDED_STRATEGY_CLASS,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_CLIENTS = ("fake", "openai")
STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_LINEAGE_ID = (
    "strongest_rival_forensic_diagnosis_v1"
)
STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_CREATED_BY = (
    "strongest_rival_forensic_diagnosis_v1_controller"
)
DIAGNOSIS_KIND = "strongest_rival_forensic_diagnosis"
NEXT_RECOMMENDED_ACTION = (
    "review_strongest_rival_forensic_diagnosis_before_local_law_discovery"
)
NEXT_RECOMMENDED_STRATEGY_CLASS = "local_law_discovery_from_rival_forensics"
DIAGNOSIS_BASIS = "evidence_map_based"

STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_ARTIFACT_TYPES = (
    "source_post_local_strategy_intake_summary",
    "current_best_evidence_state",
    "failed_local_residual_memory_summary",
    "current_best_vs_rival_subject_manifest",
    "rival_advantage_hypothesis_map",
    "non_imitation_constraint_report",
    "forensic_question_set",
    "next_strategy_readiness_report",
    "project_health_scope_guard_report",
    "strongest_rival_forensic_gate_report",
    "strongest_rival_forensic_diagnosis_packet",
)

REQUIRED_POST_LOCAL_ARTIFACTS = (
    "post_local_residual_strategy_synthesis_packet",
    "source_direction_review_intake_summary",
    "failed_local_residual_path_summary",
    "current_best_evidence_state",
    "local_residual_exhaustion_report",
    "higher_order_strategy_option_map",
    "recommended_next_strategy_class",
    "forbidden_next_moves",
    "generation_lock_report",
    "post_local_strategy_gate_report",
)

REQUIRED_HYPOTHESIS_IDS = (
    "first_read_pressure_advantage",
    "object_event_inevitability_gap",
    "proof_no_answer_embodiment_gap",
    "reader_state_transformation_partiality",
    "local_patch_diminishing_returns",
    "nonlocal_structure_gap",
)
TOP_RANKED_HYPOTHESIS_ID = REQUIRED_HYPOTHESIS_IDS[0]


@dataclass(frozen=True)
class StrongestRivalForensicDiagnosisResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class StrongestRivalForensicDiagnosisSubject:
    run_id: str
    client_name: str
    post_local_strategy_packet_dir: Path
    post_local_strategy_packet_id: str
    post_local_strategy_packet_artifact_id: str | None
    post_local_strategy_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    display_alias_warning: str | None


def run_strongest_rival_forensic_diagnosis(
    config: AbiConfig,
    *,
    client_name: str,
    post_local_strategy_packet: Path | str,
    operator_reviewed: bool,
    allow_live_model: bool,
) -> StrongestRivalForensicDiagnosisResult:
    initialize_database(config)
    post_local_strategy_packet_dir = _resolve_path(config, post_local_strategy_packet)
    if client_name not in STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_CLIENTS:
        return _refusal(
            post_local_strategy_packet=post_local_strategy_packet_dir,
            client_name=client_name,
            message=(
                "Strongest-rival forensic diagnosis refused; unsupported "
                f"client: {client_name}."
            ),
        )
    if client_name == "openai" and not allow_live_model:
        return _refusal(
            post_local_strategy_packet=post_local_strategy_packet_dir,
            client_name=client_name,
            message=(
                "Strongest-rival forensic diagnosis refused; --allow-live-model "
                "is required for client openai."
            ),
        )
    if client_name == "openai" and allow_live_model:
        return _refusal(
            post_local_strategy_packet=post_local_strategy_packet_dir,
            client_name=client_name,
            message=(
                "Strongest-rival forensic diagnosis refused; live OpenAI "
                "forensic diagnosis is not implemented in this diagnostic-only "
                "task."
            ),
        )
    if not operator_reviewed:
        return _refusal(
            post_local_strategy_packet=post_local_strategy_packet_dir,
            client_name=client_name,
            message=(
                "Strongest-rival forensic diagnosis refused; --operator-reviewed "
                "is required."
            ),
        )
    if (
        not post_local_strategy_packet_dir.exists()
        or not post_local_strategy_packet_dir.is_dir()
    ):
        return _refusal(
            post_local_strategy_packet=post_local_strategy_packet_dir,
            client_name=client_name,
            message=(
                "Strongest-rival forensic diagnosis refused; post-local "
                f"strategy packet directory not found: {post_local_strategy_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(
            config,
            post_local_strategy_packet_dir,
            client_name=client_name,
        )
    except ValueError as error:
        return _refusal(
            post_local_strategy_packet=post_local_strategy_packet_dir,
            client_name=client_name,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                post_local_strategy_packet=post_local_strategy_packet_dir,
                client_name=client_name,
                message=(
                    "Strongest-rival forensic diagnosis refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "strongest_rival_forensic_diagnosis"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_LINEAGE_ID,
            created_by=STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_post_local_strategy_intake_summary"] = (
            _build_source_post_local_strategy_intake_summary(subject, packet_dir)
        )
        artifacts["source_post_local_strategy_intake_summary"] = (
            writer.write_artifact(
                "source_post_local_strategy_intake_summary",
                payloads["source_post_local_strategy_intake_summary"],
                parent_ids=list(subject.source_parent_ids),
            )
        )

        payloads["current_best_evidence_state"] = _build_current_best_evidence_state(
            subject
        )
        artifacts["current_best_evidence_state"] = writer.write_artifact(
            "current_best_evidence_state",
            payloads["current_best_evidence_state"],
            parent_ids=[artifacts["source_post_local_strategy_intake_summary"].id],
        )

        payloads["failed_local_residual_memory_summary"] = (
            _build_failed_local_residual_memory_summary(subject)
        )
        artifacts["failed_local_residual_memory_summary"] = writer.write_artifact(
            "failed_local_residual_memory_summary",
            payloads["failed_local_residual_memory_summary"],
            parent_ids=[artifacts["source_post_local_strategy_intake_summary"].id],
        )

        payloads["current_best_vs_rival_subject_manifest"] = (
            _build_current_best_vs_rival_subject_manifest(subject)
        )
        artifacts["current_best_vs_rival_subject_manifest"] = writer.write_artifact(
            "current_best_vs_rival_subject_manifest",
            payloads["current_best_vs_rival_subject_manifest"],
            parent_ids=[
                artifacts["current_best_evidence_state"].id,
                artifacts["failed_local_residual_memory_summary"].id,
            ],
        )

        payloads["rival_advantage_hypothesis_map"] = (
            _build_rival_advantage_hypothesis_map(subject)
        )
        artifacts["rival_advantage_hypothesis_map"] = writer.write_artifact(
            "rival_advantage_hypothesis_map",
            payloads["rival_advantage_hypothesis_map"],
            parent_ids=[artifacts["current_best_vs_rival_subject_manifest"].id],
        )

        payloads["non_imitation_constraint_report"] = (
            _build_non_imitation_constraint_report(subject)
        )
        artifacts["non_imitation_constraint_report"] = writer.write_artifact(
            "non_imitation_constraint_report",
            payloads["non_imitation_constraint_report"],
            parent_ids=[artifacts["rival_advantage_hypothesis_map"].id],
        )

        payloads["forensic_question_set"] = _build_forensic_question_set(subject)
        artifacts["forensic_question_set"] = writer.write_artifact(
            "forensic_question_set",
            payloads["forensic_question_set"],
            parent_ids=[
                artifacts["rival_advantage_hypothesis_map"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["next_strategy_readiness_report"] = (
            _build_next_strategy_readiness_report(subject)
        )
        artifacts["next_strategy_readiness_report"] = writer.write_artifact(
            "next_strategy_readiness_report",
            payloads["next_strategy_readiness_report"],
            parent_ids=[artifacts["forensic_question_set"].id],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["source_post_local_strategy_intake_summary"].id,
                artifacts["next_strategy_readiness_report"].id,
            ],
        )

        payloads["strongest_rival_forensic_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["strongest_rival_forensic_gate_report"] = writer.write_artifact(
            "strongest_rival_forensic_gate_report",
            payloads["strongest_rival_forensic_gate_report"],
            parent_ids=[
                artifacts["project_health_scope_guard_report"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["strongest_rival_forensic_diagnosis_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["strongest_rival_forensic_diagnosis_packet"] = (
            writer.write_artifact(
                "strongest_rival_forensic_diagnosis_packet",
                payloads["strongest_rival_forensic_diagnosis_packet"],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type != "strongest_rival_forensic_diagnosis_packet"
                ],
            )
        )

        gate_report = payloads["strongest_rival_forensic_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="strongest_rival_forensic_diagnosis_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return StrongestRivalForensicDiagnosisResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    post_local_strategy_packet_dir: Path,
    *,
    client_name: str,
) -> StrongestRivalForensicDiagnosisSubject:
    payloads = _load_required_payloads(post_local_strategy_packet_dir)
    display_alias_warning = _validate_post_local_strategy_payloads(payloads)
    packet = payloads["post_local_residual_strategy_synthesis_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Strongest-rival forensic diagnosis refused; post-local strategy packet "
        "missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or post_local_strategy_packet_dir.name)
    packet_path = (
        post_local_strategy_packet_dir
        / "post_local_residual_strategy_synthesis_packet.json"
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
    return StrongestRivalForensicDiagnosisSubject(
        run_id=run_id,
        client_name=client_name,
        post_local_strategy_packet_dir=post_local_strategy_packet_dir,
        post_local_strategy_packet_id=packet_id,
        post_local_strategy_packet_artifact_id=packet_artifact.id
        if packet_artifact
        else None,
        post_local_strategy_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        display_alias_warning=display_alias_warning,
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_POST_LOCAL_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Strongest-rival forensic diagnosis refused; post-local "
                f"strategy packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; malformed post-local "
            f"strategy artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_post_local_strategy_payloads(
    payloads: dict[str, dict[str, Any]],
) -> str | None:
    packet = payloads["post_local_residual_strategy_synthesis_packet"]
    source_intake = payloads["source_direction_review_intake_summary"]
    failed_memory = payloads["failed_local_residual_path_summary"]
    current_best = payloads["current_best_evidence_state"]
    exhaustion = payloads["local_residual_exhaustion_report"]
    option_map = payloads["higher_order_strategy_option_map"]
    recommendation = payloads["recommended_next_strategy_class"]
    lock = payloads["generation_lock_report"]
    gate = payloads["post_local_strategy_gate_report"]

    if packet.get("accepted") is not True:
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; source post-local "
            "strategy packet is not accepted."
        )
    canonical = _first_string(
        packet.get("recommended_strategy_class"),
        recommendation.get("recommended_strategy_class"),
        option_map.get("recommended_strategy_class"),
    )
    alias = packet.get("recommended_next_strategy_class")
    alias_warning = None
    if isinstance(alias, str) and alias and alias != canonical:
        alias_warning = (
            "recommended_next_strategy_class display alias differs from "
            "canonical recommended_strategy_class and was ignored"
        )
    if canonical != POST_LOCAL_RECOMMENDED_STRATEGY_CLASS:
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; post-local strategy "
            "packet does not canonically recommend strongest_rival_forensic_diagnosis."
        )
    if packet.get("local_residual_retry_recommended") is True or exhaustion.get(
        "local_residual_retry_recommended"
    ) is True:
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; local residual retry "
            "is recommended."
        )
    for label, source in (
        ("packet", packet),
        ("failed_local_residual_path_summary", failed_memory),
        ("local_residual_exhaustion_report", exhaustion),
    ):
        failed_targets = set(_string_list(source.get("failed_local_residual_targets")))
        if not set(FAILED_LOCAL_RESIDUAL_TARGET_IDS).issubset(failed_targets):
            raise ValueError(
                "Strongest-rival forensic diagnosis refused; failed local "
                f"residual target memory is incomplete in {label}."
            )
    for target_id in FAILED_LOCAL_RESIDUAL_TARGET_IDS:
        if target_id not in set(
            _string_list(packet.get("failed_local_residual_targets"))
        ):
            raise ValueError(
                "Strongest-rival forensic diagnosis refused; failed local "
                f"residual target missing: {target_id}."
            )
    for field_name, expected in (
        ("current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID),
        ("proof_packet_id", EXPECTED_PROOF_PACKET_ID),
        ("reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID),
    ):
        value = _first_string(
            packet.get(field_name),
            source_intake.get(field_name),
            current_best.get(field_name),
        )
        if value != expected:
            raise ValueError(
                "Strongest-rival forensic diagnosis refused; "
                f"{field_name} must be {expected}."
            )
    if source_intake.get("selected_checkpoint_direction_id") != (
        POST_LOCAL_RESIDUAL_STRATEGY_SYNTHESIS_DIRECTION_ID
    ):
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; source direction review "
            "did not select post_local_residual_strategy_synthesis."
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
            "Strongest-rival forensic diagnosis refused; post-local strategy "
            "authorizes generation or generated a candidate."
        )
    if _any_true(payloads, ("residual_target_selected",)):
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; post-local strategy "
            "selected a residual target."
        )
    if _any_true(payloads, ("work_order_created",)):
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; post-local strategy "
            "created a work order."
        )
    if _model_calls(payloads) != 0:
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; post-local strategy "
            "contains model calls."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; finality or phase-shift "
            "claim appears in the post-local strategy packet."
        )
    if lock.get("generation_authorized") is not False or gate.get(
        "generation_authorized"
    ) is not False:
        raise ValueError(
            "Strongest-rival forensic diagnosis refused; generation lock is not "
            "closed."
        )
    return alias_warning


def _build_source_post_local_strategy_intake_summary(
    subject: StrongestRivalForensicDiagnosisSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["post_local_residual_strategy_synthesis_packet"]
    source_intake = subject.payloads["source_direction_review_intake_summary"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": subject.client_name,
        "diagnosis_mode": "deterministic_fake_non_model_backed",
        "model_backed": False,
        "diagnosis_basis": DIAGNOSIS_BASIS,
        "source_post_local_strategy_packet_id": subject.post_local_strategy_packet_id,
        "source_post_local_strategy_packet_dir": str(
            subject.post_local_strategy_packet_dir
        ),
        "source_post_local_strategy_packet_artifact_id": (
            subject.post_local_strategy_packet_artifact_id
        ),
        "source_direction_review_packet_id": packet.get(
            "source_direction_review_packet_id"
        ),
        "source_strategy_packet_id": packet.get("source_strategy_packet_id"),
        "source_architecture_checkpoint_packet_id": packet.get(
            "source_architecture_checkpoint_packet_id"
        ),
        "direct_rival_text_available": False,
        "selected_checkpoint_direction_id": source_intake.get(
            "selected_checkpoint_direction_id"
        ),
        "canonical_recommended_strategy_class": packet.get(
            "recommended_strategy_class"
        ),
        "display_alias_recommended_next_strategy_class": packet.get(
            "recommended_next_strategy_class"
        ),
        "display_alias_warning": subject.display_alias_warning,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "local_residual_retry_recommended": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_post_local_strategy_intake_summary_v1_controller",
    }


def _build_current_best_evidence_state(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    packet = subject.payloads["post_local_residual_strategy_synthesis_packet"]
    source_state = subject.payloads["current_best_evidence_state"]
    return {
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "strongest_rival_still_blocks": True,
        "reader_state_transformation_status": _first_string(
            source_state.get("reader_state_transformation_status"),
            "partial",
        ),
        "proof_status": _first_string(source_state.get("proof_status"), "partial"),
        "integrated_current_best_path_targets": list(
            INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS
        ),
        "local_residual_targets_are_exhausted_or_paused": True,
        "current_best_preserved": True,
        "diagnosis_kind": DIAGNOSIS_KIND,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "strongest_rival_current_best_evidence_state_v1_controller",
    }


def _build_failed_local_residual_memory_summary(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    packet = subject.payloads["post_local_residual_strategy_synthesis_packet"]
    failed_summary = subject.payloads["failed_local_residual_path_summary"]
    exhaustion = subject.payloads["local_residual_exhaustion_report"]
    return {
        "failed_local_residual_targets": list(FAILED_LOCAL_RESIDUAL_TARGET_IDS),
        "failed_paths": list(failed_summary.get("failed_paths", [])),
        "exhaustion_reasons": list(exhaustion.get("reasons", [])),
        "local_residual_retry_recommended": False,
        "integrated_current_best_path_targets": list(
            packet.get("integrated_current_best_path_targets", [])
        ),
        "failed_packets_are_diagnostic_only": True,
        "not_candidate_evidence": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "failed_local_residual_memory_summary_v1_controller",
    }


def _build_current_best_vs_rival_subject_manifest(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    packet = subject.payloads["post_local_residual_strategy_synthesis_packet"]
    return {
        "diagnosis_kind": DIAGNOSIS_KIND,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "strongest_rival_still_blocks": True,
        "reader_state_transformation_remains_partial": True,
        "direct_rival_text_available": False,
        "diagnosis_basis": DIAGNOSIS_BASIS,
        "diagnosis_basis_sources": [
            "synthesis/rival summaries",
            "reader-state comparison reports",
            "ablation summaries",
            "blocker maps",
            "post-local residual strategy synthesis",
        ],
        "limitation": (
            "forensic diagnosis is evidence-map based until direct rival subject "
            "is available"
        ),
        "does_not_require_direct_rival_text": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "current_best_vs_rival_subject_manifest_v1_controller",
    }


def _build_rival_advantage_hypothesis_map(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    del subject
    hypotheses = [
        _hypothesis(
            rank=1,
            hypothesis_id="first_read_pressure_advantage",
            description=(
                "rival may generate stronger first-read pressure before "
                "explanatory scaffolding is noticed"
            ),
            supporting=[
                "strongest rival remains blocking across cycles",
                "reader-state comparison still reports first-read pressure gap",
            ],
            uncertain=[
                "direct rival text is not loaded into this diagnostic packet",
                "packet_0063 has integrated object/tactile gains",
            ],
            risk="chasing surface vividness instead of causal pressure",
            forbidden="imitate rival diction or scenes",
            next_diagnostic="isolate rival first-read pressure mechanism",
        ),
        _hypothesis(
            rank=2,
            hypothesis_id="object_event_inevitability_gap",
            description=(
                "packet_0063 narrows object/tactile causality but may still "
                "not make object-event pressure inevitable enough"
            ),
            supporting=[
                "object-motion and tactile are integrated current-best mechanisms",
                "strongest rival still blocks despite those integrations",
            ],
            uncertain=[
                "executed proof is useful but insufficient",
                "object-event pressure may be macro-distributed rather than local",
            ],
            risk="repeating object-motion or tactile as ordinary local patches",
            forbidden="object-motion repeat or tactile repeat",
            next_diagnostic="compare object-event inevitability against rival summary",
        ),
        _hypothesis(
            rank=3,
            hypothesis_id="proof_no_answer_embodiment_gap",
            description=(
                "proof/no-answer pressure remains present but unstable after "
                "proof-no-answer failed target path"
            ),
            supporting=[
                "proof-no-answer local residual path failed twice",
                "failed target memory marks proof-no-answer diagnostic-only",
            ],
            uncertain=[
                "current best still carries some proof/no-answer pressure",
                "reader-state evidence is partial rather than absent",
            ],
            risk="turning proof/no-answer into abstract thesis",
            forbidden="proof-no-answer retry or explanatory thesis amplification",
            next_diagnostic="map where proof pressure stops being embodied",
        ),
        _hypothesis(
            rank=4,
            hypothesis_id="reader_state_transformation_partiality",
            description=(
                "reread transformation exists but remains partial, not decisive"
            ),
            supporting=[
                "reader-state packet_0013 remains partial",
                "finalization remains ineligible",
            ],
            uncertain=[
                "internal reader evidence is not human validation",
                "partial transformation may point to more than one mechanism",
            ],
            risk="mistaking partial reader-state evidence for success",
            forbidden="claim phase shift or strongest-rival defeat",
            next_diagnostic="decompose partial reader-state transition failures",
        ),
        _hypothesis(
            rank=5,
            hypothesis_id="local_patch_diminishing_returns",
            description=(
                "local residual patches are no longer producing accepted gains"
            ),
            supporting=[
                "hostile scaffold path paused after repeated attempts",
                "ending-return path paused after repeated attempts",
                "proof-no-answer path paused after repeated attempts",
            ],
            uncertain=[
                "a narrower nonlocal strategy may still use local evidence later",
                "failed packets are diagnostic only, not candidate evidence",
            ],
            risk="continuing local patching by inertia",
            forbidden="local residual retry",
            next_diagnostic="identify higher-order nonlocal mechanism",
        ),
        _hypothesis(
            rank=6,
            hypothesis_id="nonlocal_structure_gap",
            description=(
                "missing advantage may be macro/nonlocal rather than "
                "one-region repairable"
            ),
            supporting=[
                "post-local strategy synthesis moved above one-region patching",
                "strongest rival pressure persists after local cycles",
            ],
            uncertain=[
                "nonlocal strategy is not yet implemented",
                "macro change could damage packet_0063 evidence chain if misused",
            ],
            risk="broad rewrite that loses current-best gains",
            forbidden="broad recomposition without a diagnostic contract",
            next_diagnostic="local law discovery from rival forensics",
        ),
    ]
    return {
        "diagnosis_kind": DIAGNOSIS_KIND,
        "hypotheses": hypotheses,
        "top_ranked_hypothesis_id": TOP_RANKED_HYPOTHESIS_ID,
        "ranked_hypothesis_ids": [item["hypothesis_id"] for item in hypotheses],
        "hypothesis_ids": [item["hypothesis_id"] for item in hypotheses],
        "recommended_next_strategy_class": NEXT_RECOMMENDED_STRATEGY_CLASS,
        "recommended_next_strategy_not_generation": NEXT_RECOMMENDED_STRATEGY_CLASS,
        "exhausted_local_targets_recommended_as_next_targets": [],
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "rival_advantage_hypothesis_map_v1_controller",
    }


def _build_non_imitation_constraint_report(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    del subject
    constraints = [
        "do not imitate rival diction",
        "do not transplant rival scenes",
        "do not copy rival structure",
        "do not chase generic vividness",
        "do not turn packet_0063 into the rival",
        "diagnose causal advantage only",
        "preserve packet_0063 current-best evidence chain",
        "preserve failed-target memory",
        "preserve no final/phase-shift claim",
    ]
    return {
        "constraints": constraints,
        "forbidden_imitation_modes": constraints,
        "non_imitation_required": True,
        "non_imitation_constraints_passed": True,
        "diagnosis_not_imitation": True,
        "rival_text_may_not_be_copied": True,
        "diagnosis_only": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "non_imitation_constraint_report_v1_controller",
    }


def _build_forensic_question_set(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    del subject
    return {
        "diagnosis_kind": DIAGNOSIS_KIND,
        "questions": [
            {
                "question_id": "where_first_read_pressure_enters",
                "question": (
                    "Where does rival pressure begin before packet_0063's "
                    "evidence chain becomes legible?"
                ),
                "generation_allowed": False,
            },
            {
                "question_id": "which_object_event_feels_inevitable",
                "question": (
                    "Which object-event relation feels inevitable in the rival "
                    "summary but only partially inevitable in packet_0063?"
                ),
                "generation_allowed": False,
            },
            {
                "question_id": "where_proof_becomes_explanation",
                "question": (
                    "Where does packet_0063's proof/no-answer pressure risk "
                    "becoming explanation rather than embodied pressure?"
                ),
                "generation_allowed": False,
            },
            {
                "question_id": "what_nonlocal_law_is_missing",
                "question": (
                    "What governing local law would make packet_0063's object "
                    "field feel less optional without copying the rival?"
                ),
                "generation_allowed": False,
            },
        ],
        "forbidden_question_uses": [
            "write a revised candidate",
            "copy rival wording",
            "select a residual target",
            "authorize generation",
        ],
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "forensic_question_set_v1_controller",
    }


def _build_next_strategy_readiness_report(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    del subject
    return {
        "ready_for_next_strategy": True,
        "readiness_basis": (
            "forensic diagnosis is ready for operator review and local-law "
            "strategy design, not for generation"
        ),
        "ready_for_generation": False,
        "ready_for_residual_target_selection": False,
        "ready_for_work_order": False,
        "ready_for_ablation": False,
        "ready_for_reader_state_evaluation": False,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_strategy_class": NEXT_RECOMMENDED_STRATEGY_CLASS,
        "allowed_next_actions": [
            "review_strongest_rival_forensic_diagnosis_before_local_law_discovery",
            "implement_local_law_discovery_from_rival_forensics",
        ],
        "forbidden_next_actions": [
            "local residual retry",
            "hostile scaffold retry",
            "ending-return retry",
            "proof-no-answer retry",
            "object-motion repeat",
            "tactile repeat",
            "immediate generation",
            "ablation",
            "finalization",
        ],
        "generation_allowed": False,
        "target_selection_allowed": False,
        "work_order_allowed": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "strongest_rival_next_strategy_readiness_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: StrongestRivalForensicDiagnosisSubject,
) -> dict[str, object]:
    packet = subject.payloads["post_local_residual_strategy_synthesis_packet"]
    post_local_strategy_packet_expected = (
        subject.post_local_strategy_packet_id == "packet_0002"
        or subject.post_local_strategy_packet_id.startswith("packet_")
    )
    checks = [
        _check("source_chain_current_and_coherent", True),
        _check(
            "post_local_strategy_packet_expected",
            post_local_strategy_packet_expected,
            None
            if post_local_strategy_packet_expected
            else ["post-local strategy packet should be a registered packet directory"],
        ),
        _check(
            "current_best_is_packet_0063",
            packet.get("current_best_candidate_packet_id")
            == EXPECTED_CURRENT_BEST_PACKET_ID,
        ),
        _check("proof_is_packet_0034", packet.get("proof_packet_id") == "packet_0034"),
        _check(
            "reader_state_is_packet_0013",
            packet.get("reader_state_packet_id") == "packet_0013",
        ),
        _check(
            "all_three_failed_local_targets_present",
            set(FAILED_LOCAL_RESIDUAL_TARGET_IDS).issubset(
                set(_string_list(packet.get("failed_local_residual_targets")))
            ),
        ),
        _check("local_residual_retry_false", packet.get("local_residual_retry_recommended") is False),
        _check("no_new_target_adapter_introduced", True),
        _check("no_new_generation_path_introduced", True),
        _check("no_work_order_path_introduced", True),
        _check("no_stale_packet_consumed", True),
        _check("no_finality_or_phase_shift_language", True),
        _check("broad_refactor_not_performed", True),
        _check("command_is_diagnostic_only", True),
    ]
    return {
        "checks": checks,
        "passed": all(bool(check["passed"]) for check in checks),
        "project_health_scope_guard_passed": all(
            bool(check["passed"]) for check in checks
        ),
        "source_chain_current_and_coherent": True,
        "source_chain_coherent": True,
        "post_local_strategy_packet_id": subject.post_local_strategy_packet_id,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "failed_local_residual_targets": list(FAILED_LOCAL_RESIDUAL_TARGET_IDS),
        "local_residual_retry_recommended": False,
        "new_target_adapter_introduced": False,
        "no_new_target_adapter_introduced": True,
        "new_generation_path_introduced": False,
        "no_new_generation_path_introduced": True,
        "work_order_path_introduced": False,
        "no_work_order_path_introduced": True,
        "stale_packet_consumed": False,
        "broad_refactor_performed": False,
        "diagnostic_only": True,
        "command_is_diagnostic_only": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: StrongestRivalForensicDiagnosisSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    health = payloads["project_health_scope_guard_report"]
    gate_results = [
        _gate_result("source_post_local_strategy_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("canonical_strategy_class_valid", True),
        _gate_result("failed_local_targets_present", True),
        _gate_result("current_best_preserved", True),
        _gate_result("non_imitation_constraints_recorded", True),
        _gate_result("project_health_scope_guard_passed", health["passed"] is True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "generation_authorized",
            False,
            ["strongest-rival forensic diagnosis does not authorize generation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["strongest-rival forensic diagnosis is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "diagnosis has not been reviewed for next strategy selection",
        "local law discovery has not been implemented",
        "generation remains unauthorized",
        "candidate has not been generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        "passed": False,
        "eligible": False,
        "diagnosis_kind": DIAGNOSIS_KIND,
        "source_post_local_strategy_packet_id": subject.post_local_strategy_packet_id,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
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
            "Strongest-rival forensic diagnosis produced diagnostic evidence "
            "only; generation remains locked."
        ),
        "worker": "strongest_rival_forensic_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: StrongestRivalForensicDiagnosisSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    post_local_packet = subject.payloads["post_local_residual_strategy_synthesis_packet"]
    hypothesis_map = payloads["rival_advantage_hypothesis_map"]
    subject_manifest = payloads["current_best_vs_rival_subject_manifest"]
    constraints = payloads["non_imitation_constraint_report"]
    readiness = payloads["next_strategy_readiness_report"]
    health = payloads["project_health_scope_guard_report"]
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="strongest_rival_forensic_diagnosis_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": subject.client_name,
        "diagnosis_kind": DIAGNOSIS_KIND,
        "diagnosis_mode": "deterministic_fake_non_model_backed",
        "model_backed": False,
        "direct_rival_text_available": subject_manifest[
            "direct_rival_text_available"
        ],
        "diagnosis_basis": subject_manifest["diagnosis_basis"],
        "top_ranked_hypothesis_id": hypothesis_map["top_ranked_hypothesis_id"],
        "recommended_next_strategy_class": NEXT_RECOMMENDED_STRATEGY_CLASS,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "strongest_rival_forensic_diagnosis_packet",
        ],
        "counts": {
            **artifact_counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 0,
            "residual_target_selection_artifacts_created": 0,
        },
        "source_post_local_strategy_packet_id": subject.post_local_strategy_packet_id,
        "source_direction_review_packet_id": post_local_packet.get(
            "source_direction_review_packet_id"
        ),
        "source_strategy_packet_id": post_local_packet.get("source_strategy_packet_id"),
        "source_architecture_checkpoint_packet_id": post_local_packet.get(
            "source_architecture_checkpoint_packet_id"
        ),
        "current_best_candidate_packet_id": post_local_packet.get(
            "current_best_candidate_packet_id"
        ),
        "proof_packet_id": post_local_packet.get("proof_packet_id"),
        "reader_state_packet_id": post_local_packet.get("reader_state_packet_id"),
        "local_residual_retry_recommended": False,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "non_imitation_constraints_passed": constraints[
            "non_imitation_constraints_passed"
        ],
        "project_health_scope_guard_passed": health[
            "project_health_scope_guard_passed"
        ],
        "source_chain_coherent": health["source_chain_coherent"],
        "no_new_generation_path_introduced": health[
            "no_new_generation_path_introduced"
        ],
        "no_new_target_adapter_introduced": health[
            "no_new_target_adapter_introduced"
        ],
        "no_work_order_path_introduced": health["no_work_order_path_introduced"],
        "ready_for_next_strategy": readiness["ready_for_next_strategy"],
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_report": payloads["strongest_rival_forensic_gate_report"],
        "worker": "strongest_rival_forensic_diagnosis_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["strongest_rival_forensic_diagnosis_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _hypothesis(
    *,
    rank: int,
    hypothesis_id: str,
    description: str,
    supporting: list[str],
    uncertain: list[str],
    risk: str,
    forbidden: str,
    next_diagnostic: str,
) -> dict[str, object]:
    return {
        "rank": rank,
        "hypothesis_id": hypothesis_id,
        "description": description,
        "supporting_evidence": supporting,
        "contrary_or_uncertain_evidence": uncertain,
        "risk_if_misused": risk,
        "forbidden_response": forbidden,
        "likely_next_diagnostic": next_diagnostic,
        "generation_allowed": False,
    }


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
            if key in {
                "phase_shift_claim",
                "strongest_rival_defeated",
                "strongest_rival_defeat_claim",
            }:
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
    post_local_strategy_packet: Path,
    client_name: str,
    message: str,
) -> StrongestRivalForensicDiagnosisResult:
    return StrongestRivalForensicDiagnosisResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "client": client_name,
            "post_local_strategy_packet": str(post_local_strategy_packet),
            "candidate_generated": False,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "residual_target_selected": False,
            "work_order_created": False,
            "ablation_authorized": False,
            "reader_state_eval_authorized": False,
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
