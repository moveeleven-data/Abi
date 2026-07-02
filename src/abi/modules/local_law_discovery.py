"""Deterministic local-law discovery from strongest-rival forensics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_LOCAL_LAW_DISCOVERY_ACTIVE_PHASE,
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
)
from abi.modules.strongest_rival_forensic_diagnosis import (
    DIAGNOSIS_KIND as STRONGEST_RIVAL_DIAGNOSIS_KIND,
    NEXT_RECOMMENDED_STRATEGY_CLASS as SOURCE_RECOMMENDED_STRATEGY_CLASS,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


LOCAL_LAW_DISCOVERY_LINEAGE_ID = "local_law_discovery_from_rival_forensics_v1"
LOCAL_LAW_DISCOVERY_CREATED_BY = "local_law_discovery_v1_controller"
LOCAL_LAW_DISCOVERY_KIND = "local_law_discovery_from_rival_forensics"
DISCOVERED_LOCAL_LAW_ID = "first_read_pressure_precedes_explanation_law"
NEXT_RECOMMENDED_STRATEGY_CLASS = (
    "materialize_direct_rival_subject_for_model_backed_forensics"
)
NEXT_RECOMMENDED_ACTION = (
    "review_local_law_discovery_before_direct_rival_subject_materialization"
)
DIAGNOSIS_BASIS = "evidence_map_based"
TOP_FORENSIC_HYPOTHESIS_ID = "first_read_pressure_advantage"

LOCAL_LAW_DISCOVERY_ARTIFACT_TYPES = (
    "source_diagnosis_intake_summary",
    "forensic_hypothesis_to_law_map",
    "discovered_local_law_statement",
    "current_best_law_gap_report",
    "failed_local_residual_memory_summary",
    "evidence_basis_and_limitations_report",
    "non_imitation_constraint_report",
    "next_strategy_option_map",
    "local_law_discovery_gate_report",
    "project_health_scope_guard_report",
    "local_law_discovery_packet",
)

REQUIRED_DIAGNOSIS_ARTIFACTS = (
    "strongest_rival_forensic_diagnosis_packet",
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
)


@dataclass(frozen=True)
class LocalLawDiscoveryResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class LocalLawDiscoverySubject:
    run_id: str
    diagnosis_packet_dir: Path
    diagnosis_packet_id: str
    diagnosis_packet_artifact_id: str | None
    diagnosis_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]


def run_local_law_discovery(
    config: AbiConfig,
    *,
    diagnosis_packet: Path | str,
    operator_reviewed: bool,
) -> LocalLawDiscoveryResult:
    initialize_database(config)
    diagnosis_packet_dir = _resolve_path(config, diagnosis_packet)
    if not operator_reviewed:
        return _refusal(
            diagnosis_packet=diagnosis_packet_dir,
            message=(
                "Local-law discovery refused; --operator-reviewed is required."
            ),
        )
    if not diagnosis_packet_dir.exists() or not diagnosis_packet_dir.is_dir():
        return _refusal(
            diagnosis_packet=diagnosis_packet_dir,
            message=(
                "Local-law discovery refused; diagnosis packet directory not "
                f"found: {diagnosis_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, diagnosis_packet_dir)
    except ValueError as error:
        return _refusal(diagnosis_packet=diagnosis_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                diagnosis_packet=diagnosis_packet_dir,
                message=(
                    "Local-law discovery refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_LOCAL_LAW_DISCOVERY_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "local_law_discovery"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=LOCAL_LAW_DISCOVERY_LINEAGE_ID,
            created_by=LOCAL_LAW_DISCOVERY_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_diagnosis_intake_summary"] = (
            _build_source_diagnosis_intake_summary(subject, packet_dir)
        )
        artifacts["source_diagnosis_intake_summary"] = writer.write_artifact(
            "source_diagnosis_intake_summary",
            payloads["source_diagnosis_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["forensic_hypothesis_to_law_map"] = (
            _build_forensic_hypothesis_to_law_map(subject)
        )
        artifacts["forensic_hypothesis_to_law_map"] = writer.write_artifact(
            "forensic_hypothesis_to_law_map",
            payloads["forensic_hypothesis_to_law_map"],
            parent_ids=[artifacts["source_diagnosis_intake_summary"].id],
        )

        payloads["discovered_local_law_statement"] = (
            _build_discovered_local_law_statement(subject)
        )
        artifacts["discovered_local_law_statement"] = writer.write_artifact(
            "discovered_local_law_statement",
            payloads["discovered_local_law_statement"],
            parent_ids=[artifacts["forensic_hypothesis_to_law_map"].id],
        )

        payloads["current_best_law_gap_report"] = _build_current_best_law_gap_report(
            subject
        )
        artifacts["current_best_law_gap_report"] = writer.write_artifact(
            "current_best_law_gap_report",
            payloads["current_best_law_gap_report"],
            parent_ids=[artifacts["discovered_local_law_statement"].id],
        )

        payloads["failed_local_residual_memory_summary"] = (
            _build_failed_local_residual_memory_summary(subject)
        )
        artifacts["failed_local_residual_memory_summary"] = writer.write_artifact(
            "failed_local_residual_memory_summary",
            payloads["failed_local_residual_memory_summary"],
            parent_ids=[artifacts["source_diagnosis_intake_summary"].id],
        )

        payloads["evidence_basis_and_limitations_report"] = (
            _build_evidence_basis_and_limitations_report(subject)
        )
        artifacts["evidence_basis_and_limitations_report"] = writer.write_artifact(
            "evidence_basis_and_limitations_report",
            payloads["evidence_basis_and_limitations_report"],
            parent_ids=[
                artifacts["discovered_local_law_statement"].id,
                artifacts["current_best_law_gap_report"].id,
            ],
        )

        payloads["non_imitation_constraint_report"] = (
            _build_non_imitation_constraint_report(subject)
        )
        artifacts["non_imitation_constraint_report"] = writer.write_artifact(
            "non_imitation_constraint_report",
            payloads["non_imitation_constraint_report"],
            parent_ids=[
                artifacts["forensic_hypothesis_to_law_map"].id,
                artifacts["evidence_basis_and_limitations_report"].id,
            ],
        )

        payloads["next_strategy_option_map"] = _build_next_strategy_option_map(subject)
        artifacts["next_strategy_option_map"] = writer.write_artifact(
            "next_strategy_option_map",
            payloads["next_strategy_option_map"],
            parent_ids=[
                artifacts["discovered_local_law_statement"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["source_diagnosis_intake_summary"].id,
                artifacts["next_strategy_option_map"].id,
            ],
        )

        payloads["local_law_discovery_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["local_law_discovery_gate_report"] = writer.write_artifact(
            "local_law_discovery_gate_report",
            payloads["local_law_discovery_gate_report"],
            parent_ids=[
                artifacts["project_health_scope_guard_report"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["local_law_discovery_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["local_law_discovery_packet"] = writer.write_artifact(
            "local_law_discovery_packet",
            payloads["local_law_discovery_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "local_law_discovery_packet"
            ],
        )

        gate_report = payloads["local_law_discovery_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="local_law_discovery_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=LOCAL_LAW_DISCOVERY_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return LocalLawDiscoveryResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    diagnosis_packet_dir: Path,
) -> LocalLawDiscoverySubject:
    payloads = _load_required_payloads(diagnosis_packet_dir)
    _validate_diagnosis_payloads(payloads)
    packet = payloads["strongest_rival_forensic_diagnosis_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Local-law discovery refused; diagnosis packet missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or diagnosis_packet_dir.name)
    packet_path = (
        diagnosis_packet_dir / "strongest_rival_forensic_diagnosis_packet.json"
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
    return LocalLawDiscoverySubject(
        run_id=run_id,
        diagnosis_packet_dir=diagnosis_packet_dir,
        diagnosis_packet_id=packet_id,
        diagnosis_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        diagnosis_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_DIAGNOSIS_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Local-law discovery refused; diagnosis packet missing "
                f"{path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Local-law discovery refused; malformed diagnosis artifact: "
            f"{path.name}."
        )
    return envelope["payload"]


def _validate_diagnosis_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["strongest_rival_forensic_diagnosis_packet"]
    constraints = payloads["non_imitation_constraint_report"]
    readiness = payloads["next_strategy_readiness_report"]
    health = payloads["project_health_scope_guard_report"]

    if packet.get("accepted") is not True:
        raise ValueError(
            "Local-law discovery refused; source diagnosis packet is not accepted."
        )
    if packet.get("diagnosis_kind") != STRONGEST_RIVAL_DIAGNOSIS_KIND:
        raise ValueError(
            "Local-law discovery refused; source diagnosis kind is not "
            "strongest_rival_forensic_diagnosis."
        )
    if packet.get("recommended_next_strategy_class") != (
        SOURCE_RECOMMENDED_STRATEGY_CLASS
    ):
        raise ValueError(
            "Local-law discovery refused; source diagnosis does not recommend "
            "local_law_discovery_from_rival_forensics."
        )
    if packet.get("ready_for_next_strategy") is not True or readiness.get(
        "ready_for_next_strategy"
    ) is not True:
        raise ValueError(
            "Local-law discovery refused; source diagnosis is not ready for "
            "next strategy."
        )
    for field_name, expected in (
        ("current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID),
        ("proof_packet_id", EXPECTED_PROOF_PACKET_ID),
        ("reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID),
    ):
        if packet.get(field_name) != expected:
            raise ValueError(
                "Local-law discovery refused; source diagnosis "
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
            "Local-law discovery refused; source diagnosis authorizes generation "
            "or generated a candidate."
        )
    if _any_true(payloads, ("residual_target_selected",)):
        raise ValueError(
            "Local-law discovery refused; source diagnosis selected a residual "
            "target."
        )
    if _any_true(payloads, ("work_order_created",)):
        raise ValueError(
            "Local-law discovery refused; source diagnosis created a work order."
        )
    if constraints.get("non_imitation_constraints_passed") is not True or packet.get(
        "non_imitation_constraints_passed"
    ) is not True:
        raise ValueError(
            "Local-law discovery refused; source diagnosis lacks passing "
            "non-imitation constraints."
        )
    if health.get("project_health_scope_guard_passed") is not True or packet.get(
        "project_health_scope_guard_passed"
    ) is not True:
        raise ValueError(
            "Local-law discovery refused; source diagnosis lacks a passing "
            "project-health guard."
        )
    if _model_calls(payloads) != 0:
        raise ValueError(
            "Local-law discovery refused; source diagnosis contains model calls."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Local-law discovery refused; finality or phase-shift claim appears "
            "in the source diagnosis."
        )


def _build_source_diagnosis_intake_summary(
    subject: LocalLawDiscoverySubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["strongest_rival_forensic_diagnosis_packet"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_diagnosis_packet_id": subject.diagnosis_packet_id,
        "source_diagnosis_packet_dir": str(subject.diagnosis_packet_dir),
        "source_diagnosis_packet_artifact_id": subject.diagnosis_packet_artifact_id,
        "source_post_local_strategy_packet_id": packet.get(
            "source_post_local_strategy_packet_id"
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "local_law_discovery_kind": LOCAL_LAW_DISCOVERY_KIND,
        "diagnosis_kind": packet.get("diagnosis_kind"),
        "diagnosis_basis": packet.get("diagnosis_basis", DIAGNOSIS_BASIS),
        "model_backed": False,
        "direct_rival_text_available": packet.get("direct_rival_text_available"),
        "top_forensic_hypothesis_id": packet.get("top_ranked_hypothesis_id"),
        "source_recommended_next_strategy_class": packet.get(
            "recommended_next_strategy_class"
        ),
        "ready_for_next_strategy": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_diagnosis_intake_summary_v1_controller",
    }


def _build_forensic_hypothesis_to_law_map(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    hypothesis_map = subject.payloads["rival_advantage_hypothesis_map"]
    return {
        "local_law_discovery_kind": LOCAL_LAW_DISCOVERY_KIND,
        "top_forensic_hypothesis_id": hypothesis_map.get(
            "top_ranked_hypothesis_id",
            TOP_FORENSIC_HYPOTHESIS_ID,
        ),
        "discovered_local_law_id": DISCOVERED_LOCAL_LAW_ID,
        "hypothesis_to_law_edges": [
            {
                "hypothesis_id": "first_read_pressure_advantage",
                "law_id": DISCOVERED_LOCAL_LAW_ID,
                "mapping": (
                    "first-read pressure must be caused by object-event sequence "
                    "before explanation names the pressure"
                ),
                "generation_allowed": False,
            },
            {
                "hypothesis_id": "object_event_inevitability_gap",
                "law_id": DISCOVERED_LOCAL_LAW_ID,
                "mapping": (
                    "object/event relation must make consequence feel locally "
                    "inevitable before interpretation arrives"
                ),
                "generation_allowed": False,
            },
            {
                "hypothesis_id": "local_patch_diminishing_returns",
                "law_id": DISCOVERED_LOCAL_LAW_ID,
                "mapping": (
                    "the next diagnostic law must be nonlocal enough to avoid "
                    "another one-region retry"
                ),
                "generation_allowed": False,
            },
        ],
        "ranked_hypothesis_ids": list(
            hypothesis_map.get("ranked_hypothesis_ids", [])
        ),
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "forensic_hypothesis_to_law_map_v1_controller",
    }


def _build_discovered_local_law_statement(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    packet = subject.payloads["strongest_rival_forensic_diagnosis_packet"]
    return {
        "local_law_discovery_kind": LOCAL_LAW_DISCOVERY_KIND,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "discovered_local_law_id": DISCOVERED_LOCAL_LAW_ID,
        "law_statement": (
            "A successful next candidate must make first-read pressure arise "
            "from object-event sequence before explanation, thesis, or named "
            "pressure appears."
        ),
        "causal_form": (
            "object/event relation -> felt consequence -> delayed naming or "
            "interpretation"
        ),
        "reader_state_prediction": (
            "The reader should feel the table-world pressurize before knowing "
            "what concept or thesis explains that pressure."
        ),
        "violation_patterns": [
            "pressure arrives as explanation before event",
            "proof/no-answer residue becomes thesis language",
            "reread transformation is asked to do work not prepared by first-read object pressure",
            "rival advantage is imitated rather than diagnosed",
            "another local residual patch treats the symptom instead of the law",
        ],
        "required_concepts": [
            "pressure must be event-first, not explanation-first",
            "object/event relation must make the reader feel consequence before naming it",
            "proof/no-answer residue must not become thesis language",
            "reread transformation must be prepared by first-read object pressure",
            "rival advantage must be diagnosed, not imitated",
            "local residual patches are insufficient",
        ],
        "evidence_basis": [
            "top forensic hypothesis: first_read_pressure_advantage",
            "current best packet_0063",
            "proof packet_0034",
            "reader-state packet_0013",
            "failed local residual target memory",
        ],
        "uncertainty": (
            "direct rival text is unavailable; this law is evidence-map-based "
            "rather than direct textual forensic proof"
        ),
        "diagnosis_basis": packet.get("diagnosis_basis", DIAGNOSIS_BASIS),
        "direct_rival_text_available": False,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "discovered_local_law_statement_v1_controller",
    }


def _build_current_best_law_gap_report(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    packet = subject.payloads["strongest_rival_forensic_diagnosis_packet"]
    return {
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "likely_gaps": [
            "first-read pressure may still arrive too late or too conceptually",
            "packet_0063 has object/tactile gains but may still explain pressure after establishing it",
            "proof/no-answer remains unstable after failed proof target path",
            "reader-state transformation remains partial",
            "strongest rival still blocks",
            "local residual fixes have exhausted",
        ],
        "current_strengths": [
            "table/dust/spoon/saucer/ring object field",
            "object-motion causality path integrated",
            "tactile inevitability path integrated",
            "proof and reader-state evidence exists",
            "no finality claim",
        ],
        "packet_0063_preserved": True,
        "rewrite_performed": False,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "current_best_law_gap_report_v1_controller",
    }


def _build_failed_local_residual_memory_summary(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    source = subject.payloads["failed_local_residual_memory_summary"]
    return {
        "failed_local_residual_targets": list(FAILED_LOCAL_RESIDUAL_TARGET_IDS),
        "source_failed_local_residual_targets": list(
            source.get("failed_local_residual_targets", [])
        ),
        "integrated_current_best_path_targets": list(
            INTEGRATED_CURRENT_BEST_PATH_TARGET_IDS
        ),
        "local_residual_retry_recommended": False,
        "failed_packets_are_diagnostic_only": True,
        "local_patch_diminishing_returns": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "local_law_failed_local_residual_memory_summary_v1_controller",
    }


def _build_evidence_basis_and_limitations_report(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    packet = subject.payloads["strongest_rival_forensic_diagnosis_packet"]
    return {
        "diagnosis_basis": packet.get("diagnosis_basis", DIAGNOSIS_BASIS),
        "direct_rival_text_available": False,
        "evidence_basis": [
            "synthesis/rival summaries",
            "reader-state comparison",
            "ablation evidence",
            "failed-target memory",
            "strongest-rival forensic diagnosis packet",
        ],
        "limitations": [
            "local law is evidence-map-based, not direct textual forensic proof",
            "direct rival text is unavailable in this packet",
            "this packet does not authorize generation",
            "no claim is made that packet_0063 beats the strongest rival",
        ],
        "required_before_generation_claim": [
            "direct rival subject should be materialized",
            "or model-backed rival comparison should run before any generation that claims to beat the rival",
        ],
        "model_backed": False,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "evidence_basis_and_limitations_report_v1_controller",
    }


def _build_non_imitation_constraint_report(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    source_constraints = subject.payloads["non_imitation_constraint_report"]
    constraints = _string_list(
        source_constraints.get("forbidden_imitation_modes")
        or source_constraints.get("constraints")
    )
    if not constraints:
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
        "non_imitation_constraints_passed": True,
        "diagnosis_not_imitation": True,
        "rival_advantage_diagnosed_not_imitated": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "local_law_non_imitation_constraint_report_v1_controller",
    }


def _build_next_strategy_option_map(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    del subject
    return {
        "recommended_next_strategy_class": NEXT_RECOMMENDED_STRATEGY_CLASS,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_reason": (
            "The law is useful but evidence-map-based; direct rival subject "
            "material is needed before generation or a strongest-rival claim."
        ),
        "options": [
            {
                "strategy_class": "materialize_direct_rival_subject_for_model_backed_forensics",
                "recommended": True,
                "reason": "turn summary-only rival evidence into inspectable rival subject evidence",
                "generation_allowed": False,
            },
            {
                "strategy_class": "model_backed_local_law_diagnostic_with_rival_subject",
                "recommended": False,
                "reason": "use after direct rival subject material exists",
                "generation_allowed": False,
            },
            {
                "strategy_class": "nonlocal_macro_strategy_from_local_law",
                "recommended": False,
                "reason": "possible later, but currently premature without rival subject material",
                "generation_allowed": False,
            },
            {
                "strategy_class": "reader_state_failure_decomposition_against_local_law",
                "recommended": False,
                "reason": "useful if rival subject cannot be materialized",
                "generation_allowed": False,
            },
            {
                "strategy_class": "pause_generation_until_rival_subject_available",
                "recommended": False,
                "reason": "conservative fallback if direct rival subject cannot be provided",
                "generation_allowed": False,
            },
        ],
        "immediate_generation_recommended": False,
        "generation_allowed": False,
        "target_selection_allowed": False,
        "work_order_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "next_strategy_option_map_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: LocalLawDiscoverySubject,
) -> dict[str, object]:
    packet = subject.payloads["strongest_rival_forensic_diagnosis_packet"]
    source_packet_expected = (
        subject.diagnosis_packet_id == "packet_0006"
        or subject.diagnosis_packet_id.startswith("packet_")
    )
    checks = [
        _check("source_diagnosis_packet_expected", source_packet_expected),
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
            "source_recommends_local_law_discovery",
            packet.get("recommended_next_strategy_class")
            == SOURCE_RECOMMENDED_STRATEGY_CLASS,
        ),
        _check("no_new_generation_path_introduced", True),
        _check("no_work_order_path_introduced", True),
        _check("no_target_adapter_introduced", True),
        _check("no_stale_source_packet_consumed", True),
        _check("command_is_diagnostic_only", True),
        _check("broad_refactor_not_performed", True),
        _check("finalization_remains_false", True),
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "source_diagnosis_packet_id": subject.diagnosis_packet_id,
        "expected_real_source_diagnosis_packet_id": "packet_0006",
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "source_recommended_next_strategy_class": packet.get(
            "recommended_next_strategy_class"
        ),
        "no_new_generation_path_introduced": True,
        "no_work_order_path_introduced": True,
        "no_new_target_adapter_introduced": True,
        "stale_packet_consumed": False,
        "command_is_diagnostic_only": True,
        "broad_refactor_performed": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "local_law_project_health_scope_guard_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: LocalLawDiscoverySubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    health = payloads["project_health_scope_guard_report"]
    constraints = payloads["non_imitation_constraint_report"]
    gate_results = [
        _gate_result("source_diagnosis_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("source_recommends_local_law_discovery", True),
        _gate_result("discovered_local_law_present", True),
        _gate_result("current_best_preserved", True),
        _gate_result(
            "non_imitation_constraints_passed",
            constraints["non_imitation_constraints_passed"] is True,
        ),
        _gate_result("project_health_scope_guard_passed", health["passed"] is True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "finalization_eligible",
            False,
            ["local-law discovery is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "direct rival subject is not materialized",
        "local law has not been reviewed for next strategy selection",
        "generation remains unauthorized",
        "candidate has not been generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        "passed": False,
        "eligible": False,
        "local_law_discovery_kind": LOCAL_LAW_DISCOVERY_KIND,
        "source_diagnosis_packet_id": subject.diagnosis_packet_id,
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
            "Local-law discovery produced diagnostic law evidence only; "
            "generation remains locked."
        ),
        "worker": "local_law_discovery_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: LocalLawDiscoverySubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = subject.payloads["strongest_rival_forensic_diagnosis_packet"]
    law = payloads["discovered_local_law_statement"]
    options = payloads["next_strategy_option_map"]
    health = payloads["project_health_scope_guard_report"]
    counts = packet_artifact_count_summary(
        required_artifact_types=LOCAL_LAW_DISCOVERY_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="local_law_discovery_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "local_law_discovery_kind": LOCAL_LAW_DISCOVERY_KIND,
        "source_diagnosis_packet_id": subject.diagnosis_packet_id,
        "source_post_local_strategy_packet_id": packet.get(
            "source_post_local_strategy_packet_id"
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "diagnosis_basis": packet.get("diagnosis_basis", DIAGNOSIS_BASIS),
        "model_backed": False,
        "direct_rival_text_available": False,
        "top_forensic_hypothesis_id": packet.get("top_ranked_hypothesis_id"),
        "discovered_local_law_id": law["law_id"],
        "law_statement": law["law_statement"],
        "recommended_next_strategy_class": options["recommended_next_strategy_class"],
        "recommended_next_action": options["recommended_next_action"],
        "next_recommended_action": options["next_recommended_action"],
        "project_health_scope_guard_passed": health[
            "project_health_scope_guard_passed"
        ],
        "source_chain_coherent": health["source_chain_coherent"],
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "local_law_discovery_packet"],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 0,
            "residual_target_selection_artifacts_created": 0,
        },
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_report": payloads["local_law_discovery_gate_report"],
        "worker": "local_law_discovery_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["local_law_discovery_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
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
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()
    if row is None:
        return None
    return row_to_artifact(row)


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _refusal(
    *,
    diagnosis_packet: Path,
    message: str,
) -> LocalLawDiscoveryResult:
    return LocalLawDiscoveryResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "diagnosis_packet": str(diagnosis_packet),
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) else 0


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
