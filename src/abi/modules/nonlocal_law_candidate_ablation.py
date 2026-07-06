"""Deterministic ablation packet for accepted nonlocal law-guided candidates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_CANDIDATE_ABLATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_guided_candidate_generation import (
    NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES,
)
from abi.modules.nonlocal_law_guided_work_order import (
    FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE,
    NONLOCAL_LAW_TARGET_SCOPE,
    READER_STATE_FOCUS,
)
from abi.modules.post_local_residual_strategy_synthesis import (
    EXPECTED_CURRENT_BEST_PACKET_ID,
    EXPECTED_PROOF_PACKET_ID,
    EXPECTED_READER_STATE_PACKET_ID,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_CANDIDATE_ABLATION_LINEAGE_ID = "nonlocal_law_candidate_ablation_v1"
NONLOCAL_LAW_CANDIDATE_ABLATION_CREATED_BY = (
    "nonlocal_law_candidate_ablation_v1_controller"
)
NEXT_RECOMMENDED_ACTION = (
    "review_nonlocal_law_candidate_ablation_before_reader_state_evaluation"
)
READER_STATE_NEXT_ACTION = "implement_nonlocal_law_candidate_reader_state_evaluation"

ABLATION_CONTROL_IDS = (
    "full_nonlocal_law_guided_intervention",
    "revert_to_packet_0063",
    "remove_consequence_first_sequence",
    "restore_early_explanation_timing",
    "rival_imitation_control",
    "generic_vividness_control",
    "strongest_rival_comparison",
)

LAW_BEARING_SPANS = (
    {
        "span_id": "opening_ring_dust_spoon_saucer_light_sequence",
        "description": "opening ring/dust/spoon/saucer/light sequence",
        "ablation_controls": [
            "full_nonlocal_law_guided_intervention",
            "remove_consequence_first_sequence",
        ],
    },
    {
        "span_id": "glass_gone_ring_keeps_weight",
        "description": "glass gone / ring keeps weight",
        "ablation_controls": ["remove_consequence_first_sequence"],
    },
    {
        "span_id": "broom_gone_dust_keeps_near_miss",
        "description": "broom gone / dust keeps near-miss",
        "ablation_controls": ["remove_consequence_first_sequence"],
    },
    {
        "span_id": "hand_gone_spoon_keeps_angle",
        "description": "hand gone / spoon keeps angle",
        "ablation_controls": ["remove_consequence_first_sequence"],
    },
    {
        "span_id": "refrigerator_hum_spoon_tremor",
        "description": "refrigerator hum / spoon tremor",
        "ablation_controls": [
            "remove_consequence_first_sequence",
            "generic_vividness_control",
        ],
    },
    {
        "span_id": "saucer_fracture_changing_light",
        "description": "saucer fracture changing light",
        "ablation_controls": [
            "remove_consequence_first_sequence",
            "generic_vividness_control",
        ],
    },
    {
        "span_id": "delayed_room_begins_to_instruct",
        "description": 'delayed "Only after this does the room begin to instruct"',
        "ablation_controls": ["restore_early_explanation_timing"],
    },
    {
        "span_id": "later_return_through_same_table_dust_spoon_saucer",
        "description": "later return through same table/dust/spoon/saucer",
        "ablation_controls": [
            "full_nonlocal_law_guided_intervention",
            "strongest_rival_comparison",
        ],
    },
    {
        "span_id": "no_reset_no_outside_answer_pressure",
        "description": "no reset / no outside answer pressure",
        "ablation_controls": [
            "full_nonlocal_law_guided_intervention",
            "strongest_rival_comparison",
        ],
    },
)

CANDIDATE_REVIEW_RISKS = (
    {
        "risk_id": "explanation_may_arrive_too_explicitly",
        "risk": "explanation may still arrive too explicitly after initial pressure",
        "test_with": ["restore_early_explanation_timing"],
    },
    {
        "risk_id": "event_sequence_may_remain_static",
        "risk": "event sequence may remain too static or retrospective",
        "test_with": [
            "remove_consequence_first_sequence",
            "generic_vividness_control",
        ],
    },
    {
        "risk_id": "chemistry_register_risk",
        "risk": '"Chemistry gives thought a place to search" may be a register-risk span',
        "test_with": ["generic_vividness_control", "strongest_rival_comparison"],
    },
    {
        "risk_id": "conclusion_may_summarize_law",
        "risk": "conclusion may still summarize law instead of fully enacting return",
        "test_with": ["strongest_rival_comparison"],
    },
)

NONLOCAL_LAW_CANDIDATE_ABLATION_ARTIFACT_TYPES = (
    "source_candidate_intake_summary",
    "candidate_text_subject",
    "base_candidate_control_subject",
    "ablation_control_matrix",
    "full_intervention_control_report",
    "revert_to_packet_0063_control_report",
    "consequence_first_sequence_ablation_report",
    "early_explanation_timing_control_report",
    "rival_imitation_control_report",
    "generic_vividness_control_report",
    "strongest_rival_comparison_control_report",
    "law_bearing_choice_map",
    "reader_state_eval_readiness_report",
    "nonlocal_law_candidate_ablation_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_candidate_ablation_packet",
)


@dataclass(frozen=True)
class NonlocalLawCandidateAblationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawCandidateAblationSubject:
    run_id: str
    candidate_packet_dir: Path
    candidate_packet_id: str
    candidate_packet_artifact_id: str | None
    candidate_payloads: dict[str, dict[str, Any]]
    candidate_artifact_ids: dict[str, str]
    source_parent_ids: tuple[str, ...]
    candidate_text: str
    candidate_text_sha256: str
    candidate_word_count: int
    base_candidate_packet_dir: Path
    base_candidate_text: str
    base_candidate_text_sha256: str


def run_nonlocal_law_candidate_ablation(
    config: AbiConfig,
    *,
    candidate_packet: Path | str,
    operator_reviewed: bool = False,
) -> NonlocalLawCandidateAblationResult:
    if not operator_reviewed:
        return _refusal(
            message=(
                "Nonlocal law candidate ablation refused; pass --operator-reviewed "
                "after reviewing the accepted candidate."
            ),
            candidate_packet=candidate_packet,
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, candidate_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            message=(
                "Nonlocal law candidate ablation refused; candidate packet "
                f"directory not found: {resolved_packet}"
            ),
            candidate_packet=resolved_packet,
        )

    with connect(config.db_path) as connection:
        try:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject_before_ablation(connection, subject)
        except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
            return _refusal(
                message=f"Nonlocal law candidate ablation refused; {error}",
                candidate_packet=resolved_packet,
            )

        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Nonlocal law candidate ablation refused; run is not "
                    f"registered: {subject.run_id}"
                ),
                candidate_packet=resolved_packet,
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_CANDIDATE_ABLATION_ACTIVE_PHASE,
        )

    packet_dir = create_packet_dir(
        config.run_dir(subject.run_id) / "nonlocal_law_candidate_ablation"
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_ABLATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_ABLATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_ablation_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_candidate_ablation_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["nonlocal_law_candidate_ablation_gate_report"][
                    "unresolved_blockers"
                ]
            ),
            lineage_id=NONLOCAL_LAW_CANDIDATE_ABLATION_LINEAGE_ID,
        )

    return NonlocalLawCandidateAblationResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    candidate_packet_dir: Path,
) -> NonlocalLawCandidateAblationSubject:
    envelopes, payloads = _load_required_payloads(
        candidate_packet_dir,
        NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES,
        "nonlocal law-guided candidate packet",
    )
    packet = payloads["nonlocal_law_guided_candidate_packet"]
    run_id = str(
        packet.get("run_id")
        or envelopes["nonlocal_law_guided_candidate_packet"].get("run_id")
        or ""
    )
    if not run_id:
        raise ValueError("candidate packet missing run_id")

    candidate_packet_id = str(packet.get("packet_id") or candidate_packet_dir.name)
    generated_text = payloads["generated_candidate_text"]
    text = generated_text.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("generated_candidate_text payload.text missing or empty")
    text_sha = sha256_text(text)
    recorded_sha = generated_text.get("text_sha256")
    if recorded_sha is not None and recorded_sha != text_sha:
        raise ValueError("generated_candidate_text text_sha256 mismatch")

    base_id = str(packet.get("base_candidate_packet_id") or "")
    base_dir = config.run_dir(run_id) / "bounded_macro_recomposition" / base_id
    base_payload, _base_artifact_id = _load_base_candidate_payload(base_dir)
    base_text = str(base_payload["text"])

    candidate_artifact_ids = {
        artifact_type: artifact.id
        for artifact_type in NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES
        if (artifact := _artifact_for_path(connection, candidate_packet_dir / f"{artifact_type}.json"))
        is not None
    }
    packet_artifact = _artifact_for_path(
        connection,
        candidate_packet_dir / "nonlocal_law_guided_candidate_packet.json",
    )
    parent_ids = _unique(
        [
            *candidate_artifact_ids.values(),
            *[
                str(value)
                for value in dict(packet.get("artifact_ids") or {}).values()
                if value
            ],
        ]
    )
    return NonlocalLawCandidateAblationSubject(
        run_id=run_id,
        candidate_packet_dir=candidate_packet_dir,
        candidate_packet_id=candidate_packet_id,
        candidate_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        candidate_payloads=payloads,
        candidate_artifact_ids=candidate_artifact_ids,
        source_parent_ids=tuple(parent_ids),
        candidate_text=text,
        candidate_text_sha256=text_sha,
        candidate_word_count=len(text.split()),
        base_candidate_packet_dir=base_dir,
        base_candidate_text=base_text,
        base_candidate_text_sha256=sha256_text(base_text),
    )


def _validate_subject_before_ablation(
    connection: sqlite3.Connection,
    subject: NonlocalLawCandidateAblationSubject,
) -> None:
    packet = subject.candidate_payloads["nonlocal_law_guided_candidate_packet"]
    text = subject.candidate_payloads["generated_candidate_text"]
    _require_bool(packet, "accepted", True)
    _require_bool(packet, "candidate_generated", True)
    _require_bool(packet, "candidate_artifact_created", True)
    _require_bool(packet, "authorization_consumed", True)
    _require_equal(packet, "model_calls", 1)
    _require_equal(packet, "base_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID)
    _require_equal(
        packet,
        "current_best_candidate_packet_id",
        EXPECTED_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "proof_packet_id", EXPECTED_PROOF_PACKET_ID)
    _require_equal(packet, "reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID)
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(packet, "target_scope", NONLOCAL_LAW_TARGET_SCOPE)
    _require_bool(packet, "no_final_claim", True)
    _require_bool(packet, "no_phase_shift_claim", True)
    _require_bool(packet, "strongest_rival_defeated_claimed", False)

    validation = packet.get("validation_report")
    if not isinstance(validation, dict):
        raise ValueError("candidate packet missing validation_report")
    for field_name in (
        "validation_passed",
        "materiality_passed",
        "semantic_passed",
        "non_imitation_passed",
        "protected_strengths_preserved",
        "forbidden_regression_passed",
    ):
        _require_bool(validation, field_name, True)
    if validation.get("forbidden_rival_hits") not in ([], None):
        raise ValueError("candidate has forbidden rival hits")

    _require_bool(text, "candidate_generated", True)
    _require_bool(text, "authorization_consumed", True)
    _require_bool(text, "validation_passed", True)
    _require_bool(text, "no_final_claim", True)
    _require_bool(text, "no_phase_shift_claim", True)
    _require_bool(text, "strongest_rival_defeated_claimed", False)

    if _payload_has_final_or_phase_claim(packet) or _payload_has_final_or_phase_claim(text):
        raise ValueError("candidate carries finality, phase-shift, or rival-defeat claim")
    if _accepted_ablation_for_candidate(connection, subject) is not None:
        raise ValueError("current-valid ablation packet already exists for candidate")


def _write_ablation_artifacts(
    *,
    writer: PacketWriter,
    subject: NonlocalLawCandidateAblationSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_candidate_intake_summary"] = _build_source_intake(
        subject,
        packet_dir,
    )
    artifacts["source_candidate_intake_summary"] = writer.write_artifact(
        "source_candidate_intake_summary",
        payloads["source_candidate_intake_summary"],
        parent_ids=list(subject.source_parent_ids),
    )

    payloads["candidate_text_subject"] = _build_candidate_text_subject(subject)
    artifacts["candidate_text_subject"] = writer.write_artifact(
        "candidate_text_subject",
        payloads["candidate_text_subject"],
        parent_ids=[artifacts["source_candidate_intake_summary"].id],
    )

    payloads["base_candidate_control_subject"] = _build_base_control_subject(subject)
    artifacts["base_candidate_control_subject"] = writer.write_artifact(
        "base_candidate_control_subject",
        payloads["base_candidate_control_subject"],
        parent_ids=[artifacts["candidate_text_subject"].id],
    )

    payloads["ablation_control_matrix"] = _build_control_matrix(subject)
    artifacts["ablation_control_matrix"] = writer.write_artifact(
        "ablation_control_matrix",
        payloads["ablation_control_matrix"],
        parent_ids=[
            artifacts["candidate_text_subject"].id,
            artifacts["base_candidate_control_subject"].id,
        ],
    )

    control_artifacts = {
        "full_intervention_control_report": _build_full_intervention_report(subject),
        "revert_to_packet_0063_control_report": _build_revert_report(subject),
        "consequence_first_sequence_ablation_report": _build_consequence_report(subject),
        "early_explanation_timing_control_report": _build_timing_report(subject),
        "rival_imitation_control_report": _build_rival_imitation_report(subject),
        "generic_vividness_control_report": _build_generic_vividness_report(subject),
        "strongest_rival_comparison_control_report": _build_strongest_rival_report(subject),
    }
    parent_id = artifacts["ablation_control_matrix"].id
    for artifact_type, payload in control_artifacts.items():
        payloads[artifact_type] = payload
        artifacts[artifact_type] = writer.write_artifact(
            artifact_type,
            payload,
            parent_ids=[parent_id],
        )
        parent_id = artifacts[artifact_type].id

    payloads["law_bearing_choice_map"] = _build_law_bearing_choice_map(subject)
    artifacts["law_bearing_choice_map"] = writer.write_artifact(
        "law_bearing_choice_map",
        payloads["law_bearing_choice_map"],
        parent_ids=[
            artifacts["full_intervention_control_report"].id,
            artifacts["consequence_first_sequence_ablation_report"].id,
            artifacts["early_explanation_timing_control_report"].id,
        ],
    )

    payloads["reader_state_eval_readiness_report"] = _build_reader_state_readiness(
        subject
    )
    artifacts["reader_state_eval_readiness_report"] = writer.write_artifact(
        "reader_state_eval_readiness_report",
        payloads["reader_state_eval_readiness_report"],
        parent_ids=[artifacts["law_bearing_choice_map"].id],
    )

    payloads["nonlocal_law_candidate_ablation_gate_report"] = _build_gate_report(
        subject
    )
    artifacts["nonlocal_law_candidate_ablation_gate_report"] = writer.write_artifact(
        "nonlocal_law_candidate_ablation_gate_report",
        payloads["nonlocal_law_candidate_ablation_gate_report"],
        parent_ids=[artifacts["reader_state_eval_readiness_report"].id],
    )

    payloads["project_health_scope_guard_report"] = _build_health_report(subject)
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[artifacts["nonlocal_law_candidate_ablation_gate_report"].id],
    )

    payloads["nonlocal_law_candidate_ablation_packet"] = _build_packet_summary(
        subject=subject,
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    artifacts["nonlocal_law_candidate_ablation_packet"] = writer.write_artifact(
        "nonlocal_law_candidate_ablation_packet",
        payloads["nonlocal_law_candidate_ablation_packet"],
        parent_ids=[
            artifact.id
            for artifact_type, artifact in artifacts.items()
            if artifact_type != "nonlocal_law_candidate_ablation_packet"
        ],
    )
    return payloads, artifacts


def _build_source_intake(
    subject: NonlocalLawCandidateAblationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.candidate_payloads["nonlocal_law_guided_candidate_packet"]
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_candidate_packet_dir": str(subject.candidate_packet_dir),
        "candidate_text_extracted_from": "generated_candidate_text.payload.text",
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "candidate_reviewed_for_ablation": True,
        "ablation_warranted": True,
        "candidate_validation_passed": True,
        "source_candidate_next_recommended_action": packet.get("next_recommended_action"),
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "reader_state_eval_authorized": False,
        "synthesis_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_candidate_intake_summary_v1_controller",
    }


def _build_candidate_text_subject(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "candidate_text": subject.candidate_text,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "candidate_text_extracted_from": "generated_candidate_text.payload.text",
        "ablation_subject": True,
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "candidate_text_subject_v1_controller",
    }


def _build_base_control_subject(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "control_id": "revert_to_packet_0063",
        "base_candidate_text": subject.base_candidate_text,
        "base_candidate_text_sha256": subject.base_candidate_text_sha256,
        "base_candidate_packet_dir": str(subject.base_candidate_packet_dir),
        "purpose": "compare against the prior current best packet_0063",
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "base_candidate_control_subject_v1_controller",
    }


def _build_control_matrix(subject: NonlocalLawCandidateAblationSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ablation_controls": [_control_row(control_id) for control_id in ABLATION_CONTROL_IDS],
        "control_count": len(ABLATION_CONTROL_IDS),
        "deterministic_text_transformations_created": False,
        "unsafe_transformations_recorded_as_conditions": True,
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "ablation_control_matrix_v1_controller",
    }


def _build_full_intervention_report(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return _control_report(
        subject,
        control_id="full_nonlocal_law_guided_intervention",
        subject_description="accepted candidate text",
        purpose="test the complete law-guided intervention",
        deterministic_status="subject_text_available",
        expected_reader_state_contrast=(
            "candidate should increase first-read pressure before explanation if "
            "the full intervention is load-bearing"
        ),
    )


def _build_revert_report(subject: NonlocalLawCandidateAblationSubject) -> dict[str, object]:
    return _control_report(
        subject,
        control_id="revert_to_packet_0063",
        subject_description="base/current-best packet_0063 text",
        purpose="compare against the prior current best",
        deterministic_status="control_text_available",
        expected_reader_state_contrast=(
            "packet_0063 should show whether the nonlocal intervention added "
            "load-bearing pressure beyond the prior current best"
        ),
    )


def _build_consequence_report(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return _control_report(
        subject,
        control_id="remove_consequence_first_sequence",
        subject_description="candidate law-bearing opening/middle consequence-first changes",
        purpose="test whether consequence-first sequencing is load-bearing",
        deterministic_status="condition_only_no_fabricated_variant",
        law_bearing_spans=[
            row for row in LAW_BEARING_SPANS if "remove_consequence_first_sequence" in row["ablation_controls"]
        ],
        expected_reader_state_contrast=(
            "reader-state evaluation should compare the candidate against a "
            "condition where object consequences no longer lead explanation"
        ),
    )


def _build_timing_report(subject: NonlocalLawCandidateAblationSubject) -> dict[str, object]:
    return _control_report(
        subject,
        control_id="restore_early_explanation_timing",
        subject_description="candidate explanation delay/embedding changes",
        purpose="test whether delaying explanation matters",
        deterministic_status="condition_only_no_fabricated_variant",
        law_bearing_spans=[
            row for row in LAW_BEARING_SPANS if "restore_early_explanation_timing" in row["ablation_controls"]
        ],
        expected_reader_state_contrast=(
            "reader-state evaluation should test whether earlier naming weakens "
            "first-read pressure"
        ),
    )


def _build_rival_imitation_report(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_control_report(
            subject,
            control_id="rival_imitation_control",
            subject_description="candidate text and forbidden rival inventory",
            purpose="confirm the candidate's effect is non-imitative",
            deterministic_status="inventory_check_only",
            expected_reader_state_contrast=(
                "candidate must be tested without granting strongest-rival defeat"
            ),
        ),
        "forbidden_rival_objects_or_sequence": list(FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE),
        "forbidden_rival_hits": list(
            subject.candidate_payloads["nonlocal_law_guided_candidate_packet"][
                "validation_report"
            ].get("forbidden_rival_hits", [])
        ),
        "non_imitation_passed": True,
        "strongest_rival_remains_blocking": True,
    }


def _build_generic_vividness_report(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_control_report(
            subject,
            control_id="generic_vividness_control",
            subject_description="candidate text",
            purpose="test whether added physical detail is causal consequence or generic vividness",
            deterministic_status="condition_only_no_fabricated_variant",
            expected_reader_state_contrast=(
                "reader-state evaluation should test whether physical detail "
                "acts causally or merely decorates the field"
            ),
        ),
        "candidate_review_risks": list(CANDIDATE_REVIEW_RISKS),
    }


def _build_strongest_rival_report(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_control_report(
            subject,
            control_id="strongest_rival_comparison",
            subject_description="candidate, packet_0063, and materialized strongest rival subject",
            purpose="keep strongest rival active as comparison; do not claim defeat",
            deterministic_status="comparison_condition_only",
            expected_reader_state_contrast=(
                "later evaluation must compare whether the candidate earns a "
                "reader-state path under strongest-rival pressure"
            ),
        ),
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_pressure_remains_blocking": True,
        "comparison_passed": False,
    }


def _build_law_bearing_choice_map(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "law_bearing_spans": list(LAW_BEARING_SPANS),
        "law_bearing_choices": list(LAW_BEARING_SPANS),
        "candidate_review_risks": list(CANDIDATE_REVIEW_RISKS),
        "law_bearing_choice_count": len(LAW_BEARING_SPANS),
        "risk_count": len(CANDIDATE_REVIEW_RISKS),
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "law_bearing_choice_map_v1_controller",
    }


def _build_reader_state_readiness(
    subject: NonlocalLawCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ready_for_reader_state_evaluation": True,
        "reader_state_evaluation_authorized": False,
        "reader_state_eval_authorized": False,
        "reader_state_evaluation_requires_separate_authorization_or_command": True,
        "recommended_next_action": READER_STATE_NEXT_ACTION,
        "reader_state_focus": [
            *list(READER_STATE_FOCUS),
            "compare candidate against packet_0063 and ablation controls",
        ],
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "synthesis_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "reader_state_eval_readiness_report_v1_controller",
    }


def _build_gate_report(subject: NonlocalLawCandidateAblationSubject) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_candidate_accepted", True),
        _gate_result("candidate_text_loaded_from_payload_text", True),
        _gate_result("all_ablation_controls_recorded", True),
        _gate_result("law_bearing_choice_map_recorded", True),
        _gate_result("ready_for_reader_state_evaluation", True),
        _gate_result(
            "reader_state_evaluation_authorized",
            False,
            ["reader-state evaluation requires separate command"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_pressure_resolved",
            False,
            ["strongest rival remains active until later comparison/synthesis"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["ablation packet is not finalization evidence"],
            record=False,
        ),
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "reader_state_eval_authorized": False,
        "synthesis_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "reader-state evaluation has not been run",
            "synthesis has not been run",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        "worker": "nonlocal_law_candidate_ablation_gate_report_v1_controller",
    }


def _build_health_report(subject: NonlocalLawCandidateAblationSubject) -> dict[str, object]:
    checks = [
        _check("source_candidate_accepted", True),
        _check("candidate_text_loaded_from_payload_text", True),
        _check("candidate_text_hash_verified", True),
        _check("all_ablation_controls_recorded", True),
        _check("no_model_calls", True),
        _check("no_generation_authorized", True),
        _check("no_reader_state_eval_authorized", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "reader_state_eval_authorized": False,
        "synthesis_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawCandidateAblationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CANDIDATE_ABLATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_candidate_ablation_packet",
    )
    return {
        **_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "reader_state_eval_authorized": False,
        "reader_state_eval_authorized_by_this_packet": False,
        "synthesis_authorized": False,
        "model_calls": 0,
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "ablation_control_count": len(ABLATION_CONTROL_IDS),
        "law_bearing_choice_map": payloads["law_bearing_choice_map"],
        "candidate_review_risks": list(CANDIDATE_REVIEW_RISKS),
        "ready_for_reader_state_evaluation": True,
        "reader_state_evaluation_authorized": False,
        "reader_state_evaluation_requires_separate_authorization_or_command": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "counts": {**counts, "model_calls": 0},
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_candidate_ablation_packet",
        ],
        "gate_report": payloads["nonlocal_law_candidate_ablation_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "nonlocal_law_candidate_ablation_packet_v1_controller",
    }


def _control_row(control_id: str) -> dict[str, object]:
    control = _control_definition(control_id)
    return {
        "control_id": control_id,
        "subject": control["subject"],
        "purpose": control["purpose"],
        "deterministic_status": control["deterministic_status"],
        "reader_state_result_claimed": False,
        "finalization_eligible": False,
    }


def _control_definition(control_id: str) -> dict[str, str]:
    definitions = {
        "full_nonlocal_law_guided_intervention": {
            "subject": "accepted candidate text",
            "purpose": "test the complete law-guided intervention",
            "deterministic_status": "subject_text_available",
        },
        "revert_to_packet_0063": {
            "subject": "base/current-best packet_0063 text",
            "purpose": "compare against the prior current best",
            "deterministic_status": "control_text_available",
        },
        "remove_consequence_first_sequence": {
            "subject": "candidate law-bearing opening/middle consequence-first changes",
            "purpose": "test whether consequence-first sequencing is load-bearing",
            "deterministic_status": "condition_only_no_fabricated_variant",
        },
        "restore_early_explanation_timing": {
            "subject": "candidate explanation delay/embedding changes",
            "purpose": "test whether delaying explanation matters",
            "deterministic_status": "condition_only_no_fabricated_variant",
        },
        "rival_imitation_control": {
            "subject": "candidate text and forbidden rival inventory",
            "purpose": "confirm the candidate's advantage is non-imitative",
            "deterministic_status": "inventory_check_only",
        },
        "generic_vividness_control": {
            "subject": "candidate text",
            "purpose": "test whether added physical detail is causal consequence or generic vividness",
            "deterministic_status": "condition_only_no_fabricated_variant",
        },
        "strongest_rival_comparison": {
            "subject": "candidate, packet_0063, materialized rival subject",
            "purpose": "keep strongest rival active as comparison; do not claim defeat",
            "deterministic_status": "comparison_condition_only",
        },
    }
    return definitions[control_id]


def _control_report(
    subject: NonlocalLawCandidateAblationSubject,
    *,
    control_id: str,
    subject_description: str,
    purpose: str,
    deterministic_status: str,
    expected_reader_state_contrast: str,
    law_bearing_spans: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "control_id": control_id,
        "subject": subject_description,
        "purpose": purpose,
        "deterministic_status": deterministic_status,
        "law_bearing_spans": list(law_bearing_spans or []),
        "expected_reader_state_contrast": expected_reader_state_contrast,
        "deterministic_text_variant_created": deterministic_status.endswith("available"),
        "reader_state_result_claimed": False,
        "ablation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": f"{control_id}_report_v1_controller",
    }


def _source_fields(subject: NonlocalLawCandidateAblationSubject) -> dict[str, object]:
    packet = subject.candidate_payloads["nonlocal_law_guided_candidate_packet"]
    return {
        "source_candidate_packet_id": subject.candidate_packet_id,
        "source_candidate_packet_dir": str(subject.candidate_packet_dir),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_strategy_packet_id": packet.get("source_strategy_packet_id"),
        "source_diagnostic_packet_id": packet.get("source_diagnostic_packet_id"),
        "base_candidate_packet_id": packet.get("base_candidate_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "selected_strategy_class": packet.get("selected_strategy_class"),
        "target_scope": packet.get("target_scope"),
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_candidate_ablation_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _load_required_payloads(
    packet_dir: Path,
    artifact_types: tuple[str, ...],
    label: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    envelopes: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in artifact_types:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(f"{label} missing {path.name}")
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(f"malformed {label} artifact: {path.name}")
        envelopes[artifact_type] = envelope
        payloads[artifact_type] = envelope["payload"]
    return envelopes, payloads


def _load_base_candidate_payload(packet_dir: Path) -> tuple[dict[str, Any], str | None]:
    path = packet_dir / "macro_recomposed_candidate_text.json"
    if not path.exists():
        raise ValueError("base candidate macro_recomposed_candidate_text cannot be loaded")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("base candidate text artifact is malformed")
    return payload, None


def _accepted_ablation_for_candidate(
    connection: sqlite3.Connection,
    subject: NonlocalLawCandidateAblationSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type != "nonlocal_law_candidate_ablation_packet":
            continue
        payload = _artifact_payload(artifact)
        if payload.get("source_candidate_packet_id") != subject.candidate_packet_id:
            continue
        if payload.get("accepted") is True and payload.get("ablation_executed") is True:
            return artifact
    return None


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        return {}
    return envelope["payload"]


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
    if row is None:
        return None
    return ArtifactRecord(
        id=row["id"],
        run_id=row["run_id"],
        lineage_id=row["lineage_id"],
        type=row["type"],
        path=row["path"],
        hash=row["hash"],
        created_at=row["created_at"],
        parent_ids=json.loads(row["parent_ids_json"]),
    )


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"finalization_eligible", "final_artifact", "final_claim"}:
                if item is True:
                    return True
            if key in {
                "phase_shift_claim",
                "phase_shift_claimed",
                "strongest_rival_defeated",
                "strongest_rival_defeated_claimed",
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


def _refusal(
    *,
    message: str,
    candidate_packet: Path | str,
) -> NonlocalLawCandidateAblationResult:
    return NonlocalLawCandidateAblationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "candidate_packet": str(candidate_packet),
            "ablation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "reader_state_eval_authorized": False,
            "synthesis_authorized": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "next_recommended_action": "review_refusal_before_ablation",
        },
    )


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(f"{field_name} must be {str(expected).lower()}")


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


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
