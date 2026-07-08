"""Deterministic ablation packet for selected nonlocal-law target candidates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_consolidated_target_selection import (
    SELECTED_RISK_ID,
    SELECTED_TARGET_SEED_ID,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
)
from abi.modules.nonlocal_law_selected_target_candidate_generation import (
    NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ARTIFACT_TYPES,
)
from abi.modules.nonlocal_law_selected_target_generation_authorization import (
    CONSTRAINT_UNIT_IDS,
    MATERIAL_GENERATION_UNIT_IDS,
)
from abi.modules.nonlocal_law_selected_target_work_order import (
    READER_STATE_FOCUS,
    TARGET_UNIT_IDS,
    WORK_ORDER_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_LINEAGE_ID = (
    "nonlocal_law_selected_target_candidate_ablation_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_CREATED_BY = (
    "nonlocal_law_selected_target_candidate_ablation_v1_controller"
)
NEXT_RECOMMENDED_ACTION = "evaluate_selected_nonlocal_law_candidate_reader_state"

ABLATION_CONTROL_IDS = (
    "full_selected_target_intervention",
    "revert_to_packet_0002",
    "remove_living_event_sequence_repair",
    "restore_static_retrospective_trace",
    "generic_incident_addition_control",
    "rival_imitation_control",
    "strongest_rival_comparison",
)

NORMALIZED_CHANGED_REGIONS = (
    "opening perceptual ordering",
    "ring/grain relation",
    "dust ridge/bare strip relation",
    "spoon tick/saucer crack relation",
    "refrigerator hum as causal trigger",
    "light crossing fracture/table field",
    "explanation after object-event sequence",
)

NORMALIZED_PRESERVED_REGIONS = (
    "table/ring/dust/spoon/saucer/light field",
    "earned explanation timing",
    "non-imitation constraints",
    "proof/no-answer pressure",
    "sky/no outside answer pressure",
    "return-through-same-materials structure",
)

LAW_BEARING_CHOICES = (
    "ring changes next glance / grain crossing",
    "broken dust changes eye path",
    "spoon tick makes saucer fracture newly present",
    "refrigerator hum changes order of seeing",
    "crack/ring/dust sequence establishes perceptual dependency",
    'object consequences arrive before "room begins to instruct"',
    "events remain finished but leave working edges",
    "explanation still enters after object-event sequence",
)

RISKS_TO_TEST = (
    "causal mechanism may be overexplained",
    '"room begins to instruct" may be too declarative',
    '"later seeing must be changed" may name the law too directly',
    "chemistry register remains unresolved",
    "conclusion may still summarize law instead of enacting return",
    "object-field delicacy may be overloaded by causal explanation",
)

NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES = (
    "source_candidate_intake_summary",
    "candidate_text_subject",
    "base_candidate_control_subject",
    "selected_target_diff_normalization_report",
    "selected_target_ablation_control_matrix",
    "full_selected_target_intervention_control_report",
    "revert_to_packet_0002_control_report",
    "remove_living_event_sequence_repair_control_report",
    "restore_static_retrospective_trace_control_report",
    "generic_incident_addition_control_report",
    "rival_imitation_control_report",
    "strongest_rival_comparison_control_report",
    "law_bearing_choice_map",
    "reader_state_eval_readiness_report",
    "selected_target_candidate_ablation_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_selected_target_candidate_ablation_packet",
)


@dataclass(frozen=True)
class NonlocalLawSelectedTargetCandidateAblationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawSelectedTargetCandidateAblationSubject:
    run_id: str
    candidate_packet_dir: Path
    candidate_packet_id: str
    candidate_payloads: dict[str, dict[str, Any]]
    candidate_artifact_ids: dict[str, str]
    source_parent_ids: tuple[str, ...]
    candidate_text: str
    candidate_text_sha256: str
    candidate_word_count: int
    base_packet_id: str
    base_packet_dir: Path
    base_text: str
    base_text_sha256: str
    selected_target_diff_surface_missing: bool
    non_imitation_pass_alias_missing: bool
    normalized_non_imitation_passed: bool


def run_nonlocal_law_selected_target_candidate_ablation(
    config: AbiConfig,
    *,
    candidate_packet: Path | str,
    operator_reviewed: bool = False,
) -> NonlocalLawSelectedTargetCandidateAblationResult:
    if not operator_reviewed:
        return _refusal(
            message=(
                "Selected nonlocal law candidate ablation refused; pass "
                "--operator-reviewed after reviewing the accepted candidate."
            ),
            candidate_packet=candidate_packet,
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, candidate_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            message=(
                "Selected nonlocal law candidate ablation refused; candidate "
                f"packet directory not found: {resolved_packet}"
            ),
            candidate_packet=resolved_packet,
        )

    with connect(config.db_path) as connection:
        try:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject_before_ablation(connection, subject)
        except (
            KeyError,
            TypeError,
            ValueError,
            FileNotFoundError,
            json.JSONDecodeError,
        ) as error:
            return _refusal(
                message=(
                    "Selected nonlocal law candidate ablation refused; "
                    f"{error}"
                ),
                candidate_packet=resolved_packet,
            )

        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Selected nonlocal law candidate ablation refused; run is "
                    f"not registered: {subject.run_id}"
                ),
                candidate_packet=resolved_packet,
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ACTIVE_PHASE,
        )

    packet_dir = create_packet_dir(
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_candidate_ablation"
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_CREATED_BY,
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
            gate_name="selected_target_candidate_ablation_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["selected_target_candidate_ablation_gate_report"][
                    "unresolved_blockers"
                ]
            ),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_LINEAGE_ID,
        )

    return NonlocalLawSelectedTargetCandidateAblationResult(
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
) -> NonlocalLawSelectedTargetCandidateAblationSubject:
    envelopes, payloads = _load_required_payloads(
        candidate_packet_dir,
        NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ARTIFACT_TYPES,
        "selected-target candidate packet",
    )
    packet = payloads["nonlocal_law_selected_target_candidate_packet"]
    run_id = str(
        packet.get("run_id")
        or envelopes["nonlocal_law_selected_target_candidate_packet"].get("run_id")
        or ""
    )
    if not run_id:
        raise ValueError("candidate packet missing run_id")

    generated_text = payloads["generated_candidate_text"]
    text = generated_text.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("generated_candidate_text payload.text missing or empty")
    text_sha = sha256_text(text)
    if generated_text.get("text_sha256") != text_sha:
        raise ValueError("generated_candidate_text text_sha256 mismatch")

    base_packet_id = str(
        packet.get("base_current_best_packet_id")
        or packet.get("source_candidate_packet_id")
        or ""
    )
    base_dir = config.run_dir(run_id) / "nonlocal_law_guided_candidate" / base_packet_id
    base_payload, base_artifact_id = _load_base_candidate_payload(connection, base_dir)
    base_text = str(base_payload.get("text") or "")
    if not base_text.strip():
        raise ValueError("base current-best text is empty")

    candidate_artifact_ids = _artifact_ids_from_packet(packet)
    packet_artifact = _artifact_for_path(
        connection,
        candidate_packet_dir / "nonlocal_law_selected_target_candidate_packet.json",
    )
    parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            base_artifact_id,
            *candidate_artifact_ids.values(),
        ]
    )
    diff = payloads["selected_target_diff_summary"]
    non_imitation = payloads["non_imitation_validation_report"]
    validation = packet.get("validation_report")
    selected_target_diff_surface_missing = (
        not isinstance(diff.get("summary"), str)
        or not isinstance(diff.get("changed_regions"), list)
        or not isinstance(diff.get("preserved_regions"), list)
    )
    alias_value = non_imitation.get("non_imitation_passed")
    non_imitation_pass_alias_missing = alias_value is None
    normalized_non_imitation_passed = _recover_non_imitation_passed(
        validation,
        non_imitation,
    )
    return NonlocalLawSelectedTargetCandidateAblationSubject(
        run_id=run_id,
        candidate_packet_dir=candidate_packet_dir,
        candidate_packet_id=str(packet.get("packet_id") or candidate_packet_dir.name),
        candidate_payloads=payloads,
        candidate_artifact_ids=candidate_artifact_ids,
        source_parent_ids=tuple(parent_ids),
        candidate_text=text,
        candidate_text_sha256=text_sha,
        candidate_word_count=len(text.split()),
        base_packet_id=base_packet_id,
        base_packet_dir=base_dir,
        base_text=base_text,
        base_text_sha256=str(base_payload.get("text_sha256") or sha256_text(base_text)),
        selected_target_diff_surface_missing=selected_target_diff_surface_missing,
        non_imitation_pass_alias_missing=non_imitation_pass_alias_missing,
        normalized_non_imitation_passed=normalized_non_imitation_passed,
    )


def _validate_subject_before_ablation(
    connection: sqlite3.Connection,
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> None:
    packet = subject.candidate_payloads["nonlocal_law_selected_target_candidate_packet"]
    generated = subject.candidate_payloads["generated_candidate_text"]
    target_report = subject.candidate_payloads["target_unit_change_report"]
    living = subject.candidate_payloads["living_event_sequence_validation_report"]
    materiality = subject.candidate_payloads["materiality_validation_report"]
    semantic = subject.candidate_payloads["semantic_validation_report"]
    non_imitation = subject.candidate_payloads["non_imitation_validation_report"]

    _require_bool(packet, "accepted", True)
    _require_bool(packet, "candidate_generated", True)
    _require_bool(packet, "authorization_consumed", True)
    _require_equal(packet, "model_calls", 1)
    _require_bool(packet, "model_backed", True)
    _require_equal(packet, "source_authorization_packet_id", "packet_0002")
    _require_equal(packet, "source_work_order_packet_id", "packet_0002")
    _require_equal(packet, "source_target_selection_packet_id", "packet_0002")
    _require_equal(
        packet,
        "base_current_best_packet_id",
        EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    )
    _require_equal(
        packet,
        "current_best_for_next_loop_packet_id",
        EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    )
    _require_equal(
        packet,
        "prior_current_best_candidate_packet_id",
        EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(packet, "work_order_scope", WORK_ORDER_SCOPE)
    _require_bool(packet, "no_final_claim", True)
    _require_bool(packet, "no_phase_shift_claim", True)
    _require_bool(packet, "strongest_rival_defeated_claimed", False)
    if packet.get("current_best_supersession_claimed") is True:
        raise ValueError("candidate claims current-best supersession")

    validation = packet.get("validation_report")
    if not isinstance(validation, dict):
        raise ValueError("candidate packet missing validation_report")
    for field_name in (
        "validation_passed",
        "materiality_passed",
        "semantic_passed",
        "protected_strengths_preserved",
        "forbidden_regression_passed",
    ):
        _require_bool(validation, field_name, True)
    if validation.get("forbidden_rival_hits") not in ([], None):
        raise ValueError("candidate has forbidden rival hits")
    if non_imitation.get("forbidden_rival_hits") not in ([], None):
        raise ValueError("non-imitation report has forbidden rival hits")
    if non_imitation.get("forbidden_rival_mode_hits") not in ([], None):
        raise ValueError("non-imitation report has forbidden rival mode hits")
    if not subject.normalized_non_imitation_passed:
        raise ValueError("non-imitation cannot be recovered from validation report")
    _require_bool(non_imitation, "rival_imitation_detected", False)

    _require_bool(generated, "candidate_generated", True)
    _require_bool(generated, "authorization_consumed", True)
    _require_bool(generated, "validation_passed", True)
    _require_equal(generated, "source_authorization_packet_id", "packet_0002")
    _require_equal(generated, "base_current_best_packet_id", "packet_0002")
    _require_equal(generated, "prior_current_best_candidate_packet_id", "packet_0063")
    _require_equal(generated, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(generated, "selected_risk_id", SELECTED_RISK_ID)
    if generated.get("text_sha256") != subject.candidate_text_sha256:
        raise ValueError("candidate_text_sha256 mismatch")

    _require_bool(target_report, "passed", True)
    _require_exact_list(target_report, "target_unit_ids", TARGET_UNIT_IDS)
    _require_exact_list(
        target_report,
        "material_generation_unit_ids",
        MATERIAL_GENERATION_UNIT_IDS,
    )
    _require_exact_list(
        target_report,
        "preservation_or_guard_unit_ids",
        CONSTRAINT_UNIT_IDS,
    )
    _require_bool(living, "living_event_sequence_present", True)
    _require_bool(living, "static_retrospective_trace_reduced", True)
    _require_bool(living, "causal_bridge_between_object_events_present", True)
    _require_bool(living, "consequence_before_naming_present", True)
    _require_bool(materiality, "materiality_passed", True)
    _require_bool(semantic, "semantic_passed", True)
    _require_bool(semantic, "existing_object_field_preserved", True)
    _require_bool(semantic, "explanation_timing_preserved", True)

    if _payload_has_final_or_phase_claim(subject.candidate_payloads):
        raise ValueError(
            "candidate carries finality, phase-shift, rival-defeat, or current-best claim"
        )
    if _accepted_ablation_for_candidate(connection, subject) is not None:
        raise ValueError("current-valid ablation packet already exists for candidate")


def _write_ablation_artifacts(
    *,
    writer: PacketWriter,
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="source_candidate_intake_summary",
        payload=_build_source_intake(subject, packet_dir),
        parent_ids=list(subject.source_parent_ids),
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="candidate_text_subject",
        payload=_build_candidate_text_subject(subject),
        parent_ids=[artifacts["source_candidate_intake_summary"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="base_candidate_control_subject",
        payload=_build_base_control_subject(subject),
        parent_ids=[artifacts["candidate_text_subject"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_diff_normalization_report",
        payload=_build_diff_normalization_report(subject),
        parent_ids=[artifacts["base_candidate_control_subject"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_ablation_control_matrix",
        payload=_build_control_matrix(subject),
        parent_ids=[artifacts["selected_target_diff_normalization_report"].id],
    )

    parent_id = artifacts["selected_target_ablation_control_matrix"].id
    for artifact_type, payload in _control_reports(subject).items():
        payloads[artifact_type] = payload
        artifacts[artifact_type] = writer.write_artifact(
            artifact_type,
            payload,
            parent_ids=[parent_id],
        )
        parent_id = artifacts[artifact_type].id

    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="law_bearing_choice_map",
        payload=_build_law_bearing_choice_map(subject),
        parent_ids=[parent_id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="reader_state_eval_readiness_report",
        payload=_build_reader_state_readiness(subject),
        parent_ids=[artifacts["law_bearing_choice_map"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_candidate_ablation_gate_report",
        payload=_build_gate_report(subject),
        parent_ids=[artifacts["reader_state_eval_readiness_report"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="project_health_scope_guard_report",
        payload=_build_health_report(subject),
        parent_ids=[artifacts["selected_target_candidate_ablation_gate_report"].id],
    )

    payloads["nonlocal_law_selected_target_candidate_ablation_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
    )
    artifacts["nonlocal_law_selected_target_candidate_ablation_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_candidate_ablation_packet",
            payloads["nonlocal_law_selected_target_candidate_ablation_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type
                != "nonlocal_law_selected_target_candidate_ablation_packet"
            ],
        )
    )
    return payloads, artifacts


def _build_source_intake(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.candidate_payloads["nonlocal_law_selected_target_candidate_packet"]
    return {
        **_source_fields(subject),
        **_no_generation_fields(),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "accepted_candidate": True,
        "model_backed": True,
        "model_calls": 1,
        "authorization_consumed": True,
        "candidate_generated": True,
        "text_extracted_from": "generated_candidate_text.payload.text",
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "base_current_best_packet_id": subject.base_packet_id,
        "base_text_sha256": subject.base_text_sha256,
        "selected_target_diff_surface_missing": (
            subject.selected_target_diff_surface_missing
        ),
        "non_imitation_pass_alias_missing": subject.non_imitation_pass_alias_missing,
        "normalized_from_validation_report": True,
        "normalized_non_imitation_passed": subject.normalized_non_imitation_passed,
        "source_candidate_next_recommended_action": packet.get(
            "next_recommended_action"
        ),
        "model_calls_by_ablation": 0,
        "ablation_warranted": True,
        "worker": "source_candidate_intake_summary_v1_controller",
    }


def _build_candidate_text_subject(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "text": subject.candidate_text,
        "candidate_text": subject.candidate_text,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "word_count": subject.candidate_word_count,
        "candidate_text_extracted_from": "generated_candidate_text.payload.text",
        "ablation_subject": True,
        **_no_generation_fields(),
        "worker": "candidate_text_subject_v1_controller",
    }


def _build_base_control_subject(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "control_id": "revert_to_packet_0002",
        "base_candidate_text": subject.base_text,
        "base_text": subject.base_text,
        "base_text_sha256": subject.base_text_sha256,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "purpose": "control against the selected-target base current best packet_0002",
        **_no_generation_fields(),
        "worker": "base_candidate_control_subject_v1_controller",
    }


def _build_diff_normalization_report(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    target_report = subject.candidate_payloads["target_unit_change_report"]
    living = subject.candidate_payloads["living_event_sequence_validation_report"]
    reason = (
        "selected_target_diff_summary alias fields or non_imitation_passed alias "
        "were missing, but canonical validation artifacts prove the same facts"
        if subject.selected_target_diff_surface_missing
        or subject.non_imitation_pass_alias_missing
        else "source handoff aliases were already present"
    )
    return {
        **_source_fields(subject),
        "normalized_diff_summary": (
            "Selected-target candidate ablation normalizes the handoff around "
            "living event sequence repair: object traces are tested as active "
            "conditions before explanation, while packet_0002 strengths remain "
            "the base control."
        ),
        "normalized_changed_regions": list(NORMALIZED_CHANGED_REGIONS),
        "normalized_preserved_regions": list(NORMALIZED_PRESERVED_REGIONS),
        "source_target_unit_change_report": target_report.get(
            "target_unit_change_report",
            [],
        ),
        "living_event_sequence_validation_basis": {
            "living_event_sequence_present": living.get(
                "living_event_sequence_present"
            ),
            "static_retrospective_trace_reduced": living.get(
                "static_retrospective_trace_reduced"
            ),
            "causal_bridge_between_object_events_present": living.get(
                "causal_bridge_between_object_events_present"
            ),
            "consequence_before_naming_present": living.get(
                "consequence_before_naming_present"
            ),
        },
        "normalization_needed": subject.selected_target_diff_surface_missing
        or subject.non_imitation_pass_alias_missing,
        "normalization_reason": reason,
        "safe_for_ablation": True,
        **_no_generation_fields(),
        "worker": "selected_target_diff_normalization_report_v1_controller",
    }


def _build_control_matrix(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ablation_controls": [
            _control_row(control_id) for control_id in ABLATION_CONTROL_IDS
        ],
        "control_ids": list(ABLATION_CONTROL_IDS),
        "control_count": len(ABLATION_CONTROL_IDS),
        "deterministic_text_transformations_created": False,
        "controls_are_conditions_not_generated_texts": True,
        **_no_generation_fields(),
        "worker": "selected_target_ablation_control_matrix_v1_controller",
    }


def _control_reports(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, dict[str, object]]:
    return {
        "full_selected_target_intervention_control_report": _control_report(
            subject,
            control_id="full_selected_target_intervention",
        ),
        "revert_to_packet_0002_control_report": _control_report(
            subject,
            control_id="revert_to_packet_0002",
        ),
        "remove_living_event_sequence_repair_control_report": _control_report(
            subject,
            control_id="remove_living_event_sequence_repair",
        ),
        "restore_static_retrospective_trace_control_report": _control_report(
            subject,
            control_id="restore_static_retrospective_trace",
        ),
        "generic_incident_addition_control_report": _control_report(
            subject,
            control_id="generic_incident_addition_control",
        ),
        "rival_imitation_control_report": {
            **_control_report(subject, control_id="rival_imitation_control"),
            "forbidden_rival_hits": [],
            "forbidden_rival_mode_hits": [],
            "strongest_rival_defeated_claimed": False,
            "strongest_rival_pressure_remains_blocking": True,
        },
        "strongest_rival_comparison_control_report": {
            **_control_report(subject, control_id="strongest_rival_comparison"),
            "strongest_rival_defeated_claimed": False,
            "strongest_rival_pressure_remains_blocking": True,
            "comparison_passed": False,
        },
    }


def _control_report(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
    *,
    control_id: str,
) -> dict[str, object]:
    definition = _control_definition(control_id)
    return {
        **_source_fields(subject),
        "control_id": control_id,
        "subject": definition["subject"],
        "counterfactual_condition": definition["counterfactual_condition"],
        "purpose": definition["purpose"],
        "deterministic_status": definition["deterministic_status"],
        "text_variant_created": False,
        "reader_state_result_claimed": False,
        **_no_generation_fields(),
        "worker": f"{control_id}_report_v1_controller",
    }


def _build_law_bearing_choice_map(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "law_bearing_choices": list(LAW_BEARING_CHOICES),
        "choices_to_test": list(LAW_BEARING_CHOICES),
        "risks_to_test": list(RISKS_TO_TEST),
        "law_bearing_choice_count": len(LAW_BEARING_CHOICES),
        "risk_count": len(RISKS_TO_TEST),
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        **_no_generation_fields(),
        "worker": "law_bearing_choice_map_v1_controller",
    }


def _build_reader_state_readiness(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    focus = [
        "do object traces become active conditions?",
        "does sequence feel live rather than retrospective?",
        "does explanation remain earned?",
        "does the causal mechanism become overexplained?",
        "does the candidate preserve packet_0002's gains?",
        "does it avoid rival imitation?",
        "does strongest-rival pressure remain active?",
    ]
    return {
        **_source_fields(subject),
        "ready_for_reader_state_evaluation": True,
        "reader_state_evaluation_authorized": False,
        "reader_state_evaluation_requires_separate_command": True,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "reader_state_focus": focus,
        "source_reader_state_focus": list(READER_STATE_FOCUS),
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        **_no_generation_fields(),
        "worker": "reader_state_eval_readiness_report_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_candidate_accepted", True),
        _gate_result("candidate_text_loaded_from_payload_text", True),
        _gate_result("source_authorization_consumed", True),
        _gate_result("model_backed_candidate", True),
        _gate_result("one_model_call_recorded", True),
        _gate_result("selected_target_exact", True),
        _gate_result("selected_risk_exact", True),
        _gate_result("candidate_validation_passed", True),
        _gate_result("normalized_handoff_surfaces_present", True),
        _gate_result("ablation_controls_declared", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_candidate_generated_by_ablation", True),
        _gate_result("no_model_calls_by_ablation", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result("no_strongest_rival_defeat_claim", True),
        _gate_result(
            "reader_state_evaluation_authorized",
            False,
            ["reader-state evaluation requires a separate command"],
            record=False,
        ),
        _gate_result(
            "synthesis_authorized",
            False,
            ["synthesis requires a separate command after reader-state evidence"],
            record=False,
        ),
        _gate_result(
            "current_best_updated",
            False,
            ["ablation does not update current best"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["ablation packet is not finalization evidence"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival remains active until later comparison/synthesis"],
            record=False,
        ),
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "reader-state evaluation is not authorized by ablation",
            "synthesis is not authorized by ablation",
            "current best is not updated",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        **_no_generation_fields(),
        "worker": "selected_target_candidate_ablation_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    checks = [
        _check("source_candidate_accepted", True),
        _check("candidate_text_loaded_from_payload_text", True),
        _check("candidate_text_hash_verified", True),
        _check("normalized_handoff_surfaces_present", True),
        _check("all_ablation_controls_recorded", True),
        _check("no_model_calls", True),
        _check("no_generation_authorized", True),
        _check("no_reader_state_evaluation_authorized", True),
        _check("no_synthesis_authorized", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        **_no_generation_fields(),
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_candidate_ablation_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        **_source_fields(subject),
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "base_text_sha256": subject.base_text_sha256,
        "ablation_executed": True,
        "model_calls": 0,
        "candidate_generated": False,
        "generation_authorized": False,
        "reader_state_evaluation_authorized": False,
        "synthesis_authorized": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "selected_target_diff_normalization": payloads[
            "selected_target_diff_normalization_report"
        ],
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "ablation_control_count": len(ABLATION_CONTROL_IDS),
        "law_bearing_choices": list(LAW_BEARING_CHOICES),
        "risks_to_test": list(RISKS_TO_TEST),
        "ready_for_reader_state_evaluation": True,
        "reader_state_evaluation_requires_separate_command": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "counts": {**counts, "model_calls": 0},
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_candidate_ablation_packet",
        ],
        "gate_report": payloads["selected_target_candidate_ablation_gate_report"],
        "not_finalization_eligible": True,
        "worker": "nonlocal_law_selected_target_candidate_ablation_packet_v1_controller",
    }


def _source_fields(
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> dict[str, object]:
    packet = subject.candidate_payloads["nonlocal_law_selected_target_candidate_packet"]
    return {
        "source_candidate_packet_id": subject.candidate_packet_id,
        "source_candidate_packet_dir": str(subject.candidate_packet_dir),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_target_selection_packet_id": packet.get(
            "source_target_selection_packet_id"
        ),
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_base_candidate_packet_id": subject.base_packet_id,
        "base_current_best_packet_id": packet.get("base_current_best_packet_id"),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "work_order_scope": WORK_ORDER_SCOPE,
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_candidate_ablation_packet"]
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


def _load_base_candidate_payload(
    connection: sqlite3.Connection,
    packet_dir: Path,
) -> tuple[dict[str, Any], str | None]:
    path = packet_dir / "generated_candidate_text.json"
    if not path.exists():
        raise ValueError("base current-best generated_candidate_text cannot be loaded")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("base current-best text artifact is malformed")
    artifact = _artifact_for_path(connection, path)
    return payload, artifact.id if artifact else None


def _recover_non_imitation_passed(
    validation: object,
    report: dict[str, Any],
) -> bool:
    if report.get("non_imitation_passed") is True:
        return True
    if report.get("passed") is not True:
        return False
    if report.get("rival_imitation_detected") is not False:
        return False
    if report.get("forbidden_rival_hits") not in ([], None):
        return False
    if report.get("forbidden_rival_mode_hits") not in ([], None):
        return False
    if not isinstance(validation, dict):
        return False
    return (
        validation.get("validation_passed") is True
        and validation.get("non_imitation_passed") is True
        and validation.get("forbidden_rival_hits") in ([], None)
    )


def _accepted_ablation_for_candidate(
    connection: sqlite3.Connection,
    subject: NonlocalLawSelectedTargetCandidateAblationSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type != "nonlocal_law_selected_target_candidate_ablation_packet":
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


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finalization_eligible",
                "final_artifact",
                "final_claim",
                "phase_shift_claim",
                "phase_shift_claimed",
                "strongest_rival_defeated",
                "strongest_rival_defeated_claimed",
                "strongest_rival_defeat_claim",
                "current_best_supersession_claimed",
            } and item is True:
                return True
            if key in {"no_final_claim", "no_phase_shift_claim"} and item is False:
                return True
            if _payload_has_final_or_phase_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_final_or_phase_claim(item) for item in value)
    return False


def _control_row(control_id: str) -> dict[str, object]:
    definition = _control_definition(control_id)
    return {
        "control_id": control_id,
        "subject": definition["subject"],
        "counterfactual_condition": definition["counterfactual_condition"],
        "purpose": definition["purpose"],
        "deterministic_status": definition["deterministic_status"],
        "text_variant_created": False,
        "reader_state_result_claimed": False,
        "finalization_eligible": False,
    }


def _control_definition(control_id: str) -> dict[str, str]:
    definitions = {
        "full_selected_target_intervention": {
            "subject": "accepted selected-target candidate packet_0001",
            "counterfactual_condition": "test the full selected-target intervention",
            "purpose": "measure the complete living-event sequence repair",
            "deterministic_status": "subject_text_available",
        },
        "revert_to_packet_0002": {
            "subject": "base current-best-for-next-loop packet_0002",
            "counterfactual_condition": "use the base subject before selected-target repair",
            "purpose": "test whether the selected-target candidate adds load-bearing effect",
            "deterministic_status": "control_text_available",
        },
        "remove_living_event_sequence_repair": {
            "subject": "candidate object inventory with causal bridges removed",
            "counterfactual_condition": (
                "reader-state should test what happens if causal bridges are "
                "removed while object inventory remains"
            ),
            "purpose": "separate living sequence from static inventory",
            "deterministic_status": "condition_only_no_fabricated_variant",
        },
        "restore_static_retrospective_trace": {
            "subject": "candidate reverted to trace-state objects",
            "counterfactual_condition": (
                "reader-state should test whether the old trace-state returns "
                "when objects become evidence of finished events"
            ),
            "purpose": "test whether active conditions are load-bearing",
            "deterministic_status": "condition_only_no_fabricated_variant",
        },
        "generic_incident_addition_control": {
            "subject": "candidate contrasted against generic added incident",
            "counterfactual_condition": (
                "distinguish living causality from merely adding action, "
                "incident, grimness, or vividness"
            ),
            "purpose": "guard against decorative vividness being mistaken for causality",
            "deterministic_status": "condition_only_no_fabricated_variant",
        },
        "rival_imitation_control": {
            "subject": "candidate text and forbidden rival inventory",
            "counterfactual_condition": (
                "ensure success is not caused by importing rival object sequence, "
                "scene, diction, cadence, or plot"
            ),
            "purpose": "keep non-imitation as an active ablation condition",
            "deterministic_status": "inventory_check_only",
        },
        "strongest_rival_comparison": {
            "subject": "candidate, packet_0002, packet_0063, and strongest rival",
            "counterfactual_condition": (
                "strongest-rival pressure remains active until future "
                "reader-state/synthesis says otherwise"
            ),
            "purpose": "preserve strongest-rival pressure as blocking evidence",
            "deterministic_status": "comparison_condition_only",
        },
    }
    return definitions[control_id]


def _write_payload_artifact(
    *,
    writer: PacketWriter,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> None:
    payloads[artifact_type] = payload
    artifacts[artifact_type] = writer.write_artifact(
        artifact_type,
        payload,
        parent_ids=parent_ids,
    )


def _no_generation_fields() -> dict[str, object]:
    return {
        "ablation_executed": True,
        "model_calls": 0,
        "candidate_generated": False,
        "generation_authorized": False,
        "reader_state_evaluation_authorized": False,
        "synthesis_authorized": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
    }


def _refusal(
    *,
    message: str,
    candidate_packet: Path | str,
) -> NonlocalLawSelectedTargetCandidateAblationResult:
    return NonlocalLawSelectedTargetCandidateAblationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "candidate_packet": str(candidate_packet),
            "ablation_executed": False,
            "model_calls": 0,
            "candidate_generated": False,
            "generation_authorized": False,
            "reader_state_evaluation_authorized": False,
            "synthesis_authorized": False,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "next_recommended_action": "review_refusal_before_selected_target_ablation",
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


def _require_exact_list(
    payload: dict[str, Any],
    field_name: str,
    expected: tuple[str, ...],
) -> None:
    value = payload.get(field_name)
    if not isinstance(value, list) or [str(item) for item in value] != list(expected):
        raise ValueError(f"{field_name} must match expected selected target surface")


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
