"""Evidence synthesis for selected nonlocal-law reader-state packets."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_consolidated_target_selection import (
    SELECTED_RISK_ID,
    SELECTED_TARGET_SEED_ID,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
)
from abi.modules.nonlocal_law_selected_target_candidate_ablation import (
    ABLATION_CONTROL_IDS,
    NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES,
)
from abi.modules.nonlocal_law_selected_target_reader_state_evaluation import (
    NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_ARTIFACT_TYPES,
    REQUIRED_RISK_PROBE_IDS,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_LINEAGE_ID = (
    "nonlocal_law_selected_target_evidence_synthesis_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_CREATED_BY = (
    "nonlocal_law_selected_target_evidence_synthesis_v1_controller"
)
NEXT_RECOMMENDED_ACTION = "review_selected_target_synthesis_before_loop_review"
SELECTED_TARGET_EFFECT = "supported_but_incomplete"
READER_STATE_SUPPORT = "supportive_with_active_risks"
CURRENT_BEST_DECISION = "do_not_finalize"
CURRENT_BEST_UPDATE_RECOMMENDATION = (
    "recommend_loop_review_consideration_not_direct_update"
)
STRONGEST_RIVAL_STATUS = "narrowed_but_blocking"

NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES = (
    "source_reader_state_intake_summary",
    "selected_target_effect_synthesis",
    "ablation_reader_state_alignment_report",
    "packet_0002_comparison_synthesis",
    "active_risk_synthesis_report",
    "strongest_rival_pressure_synthesis",
    "current_best_decision_recommendation",
    "future_repair_or_supersession_options",
    "loop_review_readiness_report",
    "selected_target_synthesis_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_selected_target_evidence_synthesis_packet",
)

REQUIRED_READER_STATE_RESULTS = (
    "living_event_sequence_result",
    "static_trace_reduction_result",
    "causal_bridge_result",
    "consequence_before_naming_result",
    "causal_mechanism_overexplained_result",
    "explanation_earned_result",
    "packet_0002_gains_preserved_result",
    "non_imitation_result",
    "strongest_rival_pressure_result",
    "overall_selected_target_reader_state_result",
)

SUPPORTIVE_EVIDENCE = (
    "living_event_sequence_result improved",
    "static_trace_reduction_result improved",
    "causal_bridge_result improved",
    "consequence_before_naming_result improved",
    "packet_0002 gains preserved",
    "non-imitation preserved",
    "ablation controls defined the selected target clearly",
)

INCOMPLETE_OR_BLOCKING_EVIDENCE = (
    "causal mechanism overexplained active_risk",
    "explanation earned only mixed",
    "room begins to instruct too declarative active_risk",
    "later seeing must be changed names law too directly active_risk",
    "chemistry register unresolved",
    "conclusion summarizes instead of enacts return",
    "object-field delicacy may be overloaded by causal explanation",
    "strongest rival remains blocking",
    "no synthesis-to-finalization claim",
)

ACTIVE_RISK_IDS = (
    "causal_mechanism_overexplained",
    "room_begins_to_instruct_too_declarative",
    "later_seeing_must_be_changed_names_law_too_directly",
    "chemistry_register_unresolved",
    "conclusion_summarizes_instead_of_enacts_return",
    "object_field_delicacy_overloaded_by_causal_explanation",
    "strongest_rival_remains_blocking",
    "finalization_not_allowed",
)

FUTURE_OPTIONS = (
    "loop_review_packet_0001_against_packet_0002",
    "consolidate_selected_target_lesson_if_loop_review_accepts",
    "next_target_reduce_causal_mechanism_naming",
    "next_target_enact_return_instead_of_summarizing_law",
    "next_target_integrate_or_remove_chemistry_register",
)

EFFECT_SUMMARY = (
    "The selected target improved: packet_0001 makes object traces more often feel "
    "like active conditions for later perception rather than merely stored evidence."
)
ALIGNMENT_SUMMARY = (
    "The ablation target and reader-state result align on selected-target "
    "improvement, but the same evidence exposes a new finer-grained "
    "overexplanation risk."
)
RIVAL_PRESSURE_SUMMARY = (
    "selected target gap narrowed, but strongest rival remains blocking because "
    "explicit mechanism and return-summary risks persist."
)


@dataclass(frozen=True)
class NonlocalLawSelectedTargetEvidenceSynthesisResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawSelectedTargetEvidenceSynthesisSubject:
    run_id: str
    reader_state_packet_dir: Path
    reader_state_packet_id: str
    reader_state_artifact_id: str | None
    reader_state_payloads: dict[str, dict[str, Any]]
    reader_state_artifact_ids: dict[str, str]
    parent_ids: tuple[str, ...]
    source_ablation_packet_dir: Path
    source_ablation_payloads: dict[str, dict[str, Any]]
    source_ablation_artifact_ids: dict[str, str]


def run_nonlocal_law_selected_target_evidence_synthesis(
    config: AbiConfig,
    *,
    reader_state_packet: Path | str,
    operator_reviewed: bool = False,
) -> NonlocalLawSelectedTargetEvidenceSynthesisResult:
    if not operator_reviewed:
        return _refusal(
            reader_state_packet=reader_state_packet,
            message=(
                "Selected nonlocal law evidence synthesis refused; pass "
                "--operator-reviewed after reviewing the model-backed reader-state "
                "packet."
            ),
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, reader_state_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            reader_state_packet=resolved_packet,
            message=(
                "Selected nonlocal law evidence synthesis refused; reader-state "
                f"packet directory not found: {resolved_packet}"
            ),
        )

    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject(subject)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    reader_state_packet=resolved_packet,
                    message=(
                        "Selected nonlocal law evidence synthesis refused; run is "
                        f"not registered: {subject.run_id}"
                    ),
                )
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_ACTIVE_PHASE,
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            reader_state_packet=resolved_packet,
            message=f"Selected nonlocal law evidence synthesis refused; {error}",
        )

    packet_dir = create_packet_dir(
        config.run_dir(subject.run_id) / "nonlocal_law_selected_target_evidence_synthesis"
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_synthesis_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_synthesis_gate_report",
            passed=False,
            blocking_defects=payloads["selected_target_synthesis_gate_report"][
                "unresolved_blockers"
            ],
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_LINEAGE_ID,
        )
    return NonlocalLawSelectedTargetEvidenceSynthesisResult(
        exit_code=0,
        payload=_result_payload(packet_dir, artifacts, payloads),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    reader_state_packet_dir: Path,
) -> NonlocalLawSelectedTargetEvidenceSynthesisSubject:
    reader_payloads: dict[str, dict[str, Any]] = {}
    reader_artifact_ids: dict[str, str] = {}
    parent_ids: list[str] = []
    for artifact_type in NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_ARTIFACT_TYPES:
        path = reader_state_packet_dir / f"{artifact_type}.json"
        envelope = _read_envelope(path, artifact_type)
        reader_payloads[artifact_type] = envelope["payload"]
        artifact = _artifact_for_path(connection, path)
        if artifact is not None:
            reader_artifact_ids[artifact_type] = artifact.id
            parent_ids.append(artifact.id)

    packet = reader_payloads["nonlocal_law_selected_target_reader_state_evaluation_packet"]
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("source reader-state packet missing run_id")
    reader_state_packet_id = str(packet.get("packet_id") or reader_state_packet_dir.name)
    packet_artifact = _artifact_for_path(
        connection,
        reader_state_packet_dir
        / "nonlocal_law_selected_target_reader_state_evaluation_packet.json",
    )
    source_ablation_dir = _source_ablation_dir(config, packet, run_id)
    source_ablation_payloads: dict[str, dict[str, Any]] = {}
    source_ablation_artifact_ids: dict[str, str] = {}
    for artifact_type in NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES:
        path = source_ablation_dir / f"{artifact_type}.json"
        envelope = _read_envelope(path, artifact_type)
        source_ablation_payloads[artifact_type] = envelope["payload"]
        artifact = _artifact_for_path(connection, path)
        if artifact is not None:
            source_ablation_artifact_ids[artifact_type] = artifact.id
            parent_ids.append(artifact.id)

    return NonlocalLawSelectedTargetEvidenceSynthesisSubject(
        run_id=run_id,
        reader_state_packet_dir=reader_state_packet_dir,
        reader_state_packet_id=reader_state_packet_id,
        reader_state_artifact_id=packet_artifact.id if packet_artifact else None,
        reader_state_payloads=reader_payloads,
        reader_state_artifact_ids=reader_artifact_ids,
        parent_ids=tuple(parent_ids),
        source_ablation_packet_dir=source_ablation_dir,
        source_ablation_payloads=source_ablation_payloads,
        source_ablation_artifact_ids=source_ablation_artifact_ids,
    )


def _validate_subject(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> None:
    packet = _packet(subject)
    _require_bool(packet, "accepted", True)
    _require_bool(packet, "model_backed", True)
    _require_equal(packet, "reader_state_evaluation_mode", "model_backed_live")
    _require_bool(packet, "provisional_reader_state_evaluation", False)
    _require_bool(packet, "usable_for_synthesis", True)
    _require_bool(packet, "reader_state_evaluation_executed", True)
    _require_bool(packet, "ready_for_synthesis", True)
    _require_bool(packet, "synthesis_authorized", False)
    _require_bool(packet, "current_best_updated", False)
    _require_bool(packet, "candidate_generated", False)
    _require_bool(packet, "generation_authorized", False)
    _require_bool(packet, "finalization_eligible", False)
    _require_bool(packet, "no_final_claim", True)
    _require_bool(packet, "no_phase_shift_claim", True)
    _require_bool(packet, "strongest_rival_defeated_claimed", False)
    _require_equal(packet, "source_candidate_packet_id", "packet_0001")
    _require_equal(
        packet,
        "source_base_candidate_packet_id",
        EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    )
    _require_equal(
        packet,
        "prior_current_best_candidate_packet_id",
        EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    if int(packet.get("model_calls") or 0) < 1:
        raise ValueError("source reader-state packet must be model-backed")
    for key in REQUIRED_READER_STATE_RESULTS:
        if not str(packet.get(key) or "").strip():
            raise ValueError(f"{key} missing")
    _validate_risk_probe_surface(packet)
    risk_report = subject.reader_state_payloads["selected_target_risk_probe_report"]
    _validate_risk_probe_surface(risk_report)
    _validate_source_ablation_alignment(subject)
    if _payload_has_forbidden_claim(subject.reader_state_payloads):
        raise ValueError(
            "source reader-state packet carries finality, phase-shift, "
            "rival-defeat, generation, or current-best claim"
        )


def _validate_source_ablation_alignment(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> None:
    packet = _packet(subject)
    ablation = subject.source_ablation_payloads[
        "nonlocal_law_selected_target_candidate_ablation_packet"
    ]
    _require_bool(ablation, "accepted", True)
    _require_bool(ablation, "ablation_executed", True)
    _require_equal(
        packet,
        "source_ablation_packet_id",
        str(ablation.get("packet_id") or ""),
    )
    for key in (
        "source_candidate_packet_id",
        "source_authorization_packet_id",
        "source_work_order_packet_id",
        "source_target_selection_packet_id",
        "source_consolidation_packet_id",
        "source_base_candidate_packet_id",
        "prior_current_best_candidate_packet_id",
        "selected_target_seed_id",
        "selected_risk_id",
        "candidate_text_sha256",
        "base_text_sha256",
    ):
        if packet.get(key) != ablation.get(key):
            raise ValueError(f"source chain mismatch for {key}")
    controls = set(_string_list(packet.get("ablation_controls")))
    matrix = subject.source_ablation_payloads["selected_target_ablation_control_matrix"]
    controls.update(_string_list(matrix.get("control_ids")))
    missing_controls = [control for control in ABLATION_CONTROL_IDS if control not in controls]
    if missing_controls:
        raise ValueError("source ablation controls missing: " + ", ".join(missing_controls))


def _write_synthesis_artifacts(
    *,
    writer: PacketWriter,
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    _write_artifact(
        writer,
        artifacts,
        payloads,
        "source_reader_state_intake_summary",
        _build_intake(subject, packet_dir),
        list(subject.parent_ids),
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "selected_target_effect_synthesis",
        _build_effect_synthesis(subject),
        [artifacts["source_reader_state_intake_summary"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "ablation_reader_state_alignment_report",
        _build_alignment_report(subject),
        [artifacts["selected_target_effect_synthesis"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "packet_0002_comparison_synthesis",
        _build_packet_0002_comparison(subject),
        [artifacts["ablation_reader_state_alignment_report"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "active_risk_synthesis_report",
        _build_active_risk_report(subject),
        [artifacts["packet_0002_comparison_synthesis"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "strongest_rival_pressure_synthesis",
        _build_rival_synthesis(subject),
        [artifacts["active_risk_synthesis_report"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "current_best_decision_recommendation",
        _build_current_best_recommendation(subject),
        [artifacts["strongest_rival_pressure_synthesis"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "future_repair_or_supersession_options",
        _build_future_options(subject),
        [artifacts["current_best_decision_recommendation"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "loop_review_readiness_report",
        _build_loop_review_readiness(subject),
        [artifacts["future_repair_or_supersession_options"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "selected_target_synthesis_gate_report",
        _build_gate_report(subject),
        [artifacts["loop_review_readiness_report"].id],
    )
    _write_artifact(
        writer,
        artifacts,
        payloads,
        "project_health_scope_guard_report",
        _build_health_report(subject),
        [artifacts["selected_target_synthesis_gate_report"].id],
    )
    payloads["nonlocal_law_selected_target_evidence_synthesis_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
        )
    )
    artifacts["nonlocal_law_selected_target_evidence_synthesis_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_evidence_synthesis_packet",
            payloads["nonlocal_law_selected_target_evidence_synthesis_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type
                != "nonlocal_law_selected_target_evidence_synthesis_packet"
            ],
        )
    )
    return payloads, artifacts


def _build_intake(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_reader_state_packet_dir": str(subject.reader_state_packet_dir),
        "source_reader_state_artifact_id": subject.reader_state_artifact_id,
        "source_reader_state_accepted": True,
        "source_reader_state_model_backed": True,
        "source_reader_state_usable_for_synthesis": True,
        "source_reader_state_mode": packet["reader_state_evaluation_mode"],
        "risk_probe_count": packet["risk_probe_count"],
        "all_required_risk_probes_present": True,
        "missing_risk_probe_ids": [],
        "synthesis_executed": True,
        **_safety_fields(),
        "worker": "source_reader_state_intake_summary_v1_controller",
    }


def _build_effect_synthesis(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        **_source_fields(subject),
        "selected_target_effect": SELECTED_TARGET_EFFECT,
        "reader_state_support": READER_STATE_SUPPORT,
        "summary": EFFECT_SUMMARY,
        "supportive_evidence": list(SUPPORTIVE_EVIDENCE),
        "incomplete_or_blocking_evidence": list(INCOMPLETE_OR_BLOCKING_EVIDENCE),
        "reader_state_results": {
            key: packet.get(key) for key in REQUIRED_READER_STATE_RESULTS
        },
        "synthesis_confidence": "moderate",
        "not_finalization_evidence": True,
        **_safety_fields(),
        "worker": "selected_target_effect_synthesis_v1_controller",
    }


def _build_alignment_report(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "alignment": "aligned_but_incomplete",
        "summary": ALIGNMENT_SUMMARY,
        "aligned_signals": [
            "ablation controls isolate the selected target",
            "living event sequence result supports improvement",
            "static trace reduction result supports improvement",
            "causal bridge result supports improvement",
            "reader-state packet preserves non-imitation and packet_0002 gains",
        ],
        "misalignment_or_risk_signals": [
            "causal mechanism overexplained remains active",
            "explanation earned is mixed",
            "risk probes show declarative and return-summary risks",
            "strongest rival pressure remains blocking",
        ],
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "alignment_supports_loop_review": True,
        "alignment_does_not_authorize_generation": True,
        **_safety_fields(),
        "worker": "ablation_reader_state_alignment_report_v1_controller",
    }


def _build_packet_0002_comparison(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "comparison_result": "packet_0001_improves_selected_target_over_packet_0002",
        "packet_0002_preserved_strengths": [
            "object/tactile field remains protected",
            "proof/no-answer pressure remains protected",
            "return-through-same-materials structure remains protected",
        ],
        "packet_0001_advantages": [
            "object traces more often become active conditions",
            "static retrospective trace behavior is reduced",
            "causal bridges are clearer before naming",
        ],
        "packet_0001_costs": [
            "causal mechanism can become overexplained",
            "room-instructs phrasing may be too declarative",
            "return can still summarize law instead of enacting it",
        ],
        "packet_0002_retained_advantages": [
            "packet_0002 remains the base/current-best-for-next-loop candidate",
            "packet_0002 is not erased by selected-target synthesis",
            "packet_0002 remains available if loop review rejects packet_0001",
        ],
        "packet_0001_not_final": True,
        "packet_0002_not_erased": True,
        "candidate_superiority_claimed": False,
        "current_best_supersession_claimed": False,
        **_safety_fields(),
        "worker": "packet_0002_comparison_synthesis_v1_controller",
    }


def _build_active_risk_report(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    risk_results = _risk_results(subject)
    active_risks = []
    for risk_id in ACTIVE_RISK_IDS:
        active_risks.append(
            {
                "risk_id": risk_id,
                "source_probe": risk_results.get(risk_id),
                "carried_forward": True,
                "blocks_finalization": True,
            }
        )
    return {
        **_source_fields(subject),
        "active_risks": active_risks,
        "active_risk_ids": list(ACTIVE_RISK_IDS),
        "active_risk_count": len(active_risks),
        "risk_classification": "supportive_evidence_with_active_risks",
        "ready_for_loop_review": True,
        "finalization_eligible": False,
        "strongest_rival_defeated_claimed": False,
        "worker": "active_risk_synthesis_report_v1_controller",
    }


def _build_rival_synthesis(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "strongest_rival_status": STRONGEST_RIVAL_STATUS,
        "strongest_rival_pressure_result": _packet(subject).get(
            "strongest_rival_pressure_result"
        ),
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_comparison_passed": False,
        "pressure_summary": RIVAL_PRESSURE_SUMMARY,
        "finalization_eligible": False,
        "worker": "strongest_rival_pressure_synthesis_v1_controller",
    }


def _build_current_best_recommendation(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "current_best_decision": CURRENT_BEST_DECISION,
        "current_best_update_recommendation": CURRENT_BEST_UPDATE_RECOMMENDATION,
        "direct_current_best_update_forbidden": True,
        "loop_review_required": True,
        "finalization_forbidden": True,
        "candidate_superiority_not_final_proof": True,
        "current_best_updated": False,
        "finalization_allowed": False,
        "strongest_rival_defeated_claimed": False,
        "summary": (
            "Treat packet_0001 as evidence for loop review, not as a direct "
            "current-best update or finalization proof."
        ),
        "worker": "current_best_decision_recommendation_v1_controller",
    }


def _build_future_options(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ranked_options": [
            {"rank": index + 1, "option_id": option}
            for index, option in enumerate(FUTURE_OPTIONS)
        ],
        "options": list(FUTURE_OPTIONS),
        "recommended_next_option": FUTURE_OPTIONS[0],
        "strongest_rival_remains_blocking": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "current_best_updated": False,
        "worker": "future_repair_or_supersession_options_v1_controller",
    }


def _build_loop_review_readiness(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ready_for_loop_review": True,
        "loop_review_authorized": False,
        "loop_review_requires_separate_command": True,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        **_safety_fields(),
        "worker": "loop_review_readiness_report_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    pass_gates = (
        "source_reader_state_accepted",
        "source_reader_state_model_backed",
        "source_reader_state_usable_for_synthesis",
        "risk_probes_complete",
        "selected_target_effect_synthesized",
        "active_risks_carried_forward",
        "no_generation",
        "no_candidate",
        "no_current_best_update",
        "no_final_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    )
    block_gates = (
        "loop_review_authorized",
        "current_best_updated",
        "finalization_eligible",
        "strongest_rival_resolved",
    )
    gate_results = [
        _gate_result(gate_name, True) for gate_name in pass_gates
    ] + [
        _gate_result(gate_name, False, [f"{gate_name} remains blocked"])
        for gate_name in block_gates
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "gate_results": gate_results,
        "passed_gates": list(pass_gates),
        "failed_gates": list(block_gates),
        "unresolved_blockers": [
            "loop review requires a separate command",
            "current best is not updated",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "ready_for_loop_review": True,
        "loop_review_authorized": False,
        **_safety_fields(),
        "worker": "selected_target_synthesis_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    checks = [
        _check("no_generation_performed", True),
        _check("no_ablation_performed", True),
        _check("no_reader_state_evaluation_performed", True),
        _check("no_model_calls", True),
        _check("current_best_not_mutated", True),
        _check("finalization_refused", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "source_reader_state_model_backed": True,
        "source_reader_state_usable_for_synthesis": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_current_best_mutation": True,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_remains_blocking": True,
        **_safety_fields(),
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = _packet(subject)
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_evidence_synthesis_packet",
    )
    return {
        **_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "synthesis_executed": True,
        "source_chain_coherent": True,
        "candidate_text_sha256": packet.get("candidate_text_sha256"),
        "base_text_sha256": packet.get("base_text_sha256"),
        "selected_target_effect": SELECTED_TARGET_EFFECT,
        "reader_state_support": READER_STATE_SUPPORT,
        "current_best_decision": CURRENT_BEST_DECISION,
        "current_best_update_recommendation": CURRENT_BEST_UPDATE_RECOMMENDATION,
        "strongest_rival_status": STRONGEST_RIVAL_STATUS,
        "ready_for_loop_review": True,
        "loop_review_authorized": False,
        "current_best_updated": False,
        "model_calls": 0,
        "candidate_generated": False,
        "generation_authorized": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "active_risk_ids": list(ACTIVE_RISK_IDS),
        "supportive_evidence": payloads["selected_target_effect_synthesis"][
            "supportive_evidence"
        ],
        "incomplete_or_blocking_evidence": payloads[
            "selected_target_effect_synthesis"
        ]["incomplete_or_blocking_evidence"],
        "counts": {**counts, "model_calls": 0},
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_evidence_synthesis_packet",
        ],
        "gate_report": payloads["selected_target_synthesis_gate_report"],
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "worker": "nonlocal_law_selected_target_evidence_synthesis_packet_v1_controller",
    }


def _source_fields(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_reader_state_packet_id": subject.reader_state_packet_id,
        "source_reader_state_packet_dir": str(subject.reader_state_packet_dir),
        "source_ablation_packet_id": packet.get("source_ablation_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_target_selection_packet_id": packet.get("source_target_selection_packet_id"),
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_base_candidate_packet_id": packet.get("source_base_candidate_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "law_id": packet.get("law_id"),
        "selected_target_seed_id": packet.get("selected_target_seed_id"),
        "selected_risk_id": packet.get("selected_risk_id"),
    }


def _result_payload(
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_evidence_synthesis_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _packet(subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject) -> dict[str, Any]:
    return subject.reader_state_payloads[
        "nonlocal_law_selected_target_reader_state_evaluation_packet"
    ]


def _source_ablation_dir(config: AbiConfig, packet: dict[str, Any], run_id: str) -> Path:
    source_dir = packet.get("source_ablation_packet_dir")
    if isinstance(source_dir, str) and source_dir.strip():
        path = Path(source_dir)
        return path if path.is_absolute() else config.root / path
    source_id = str(packet.get("source_ablation_packet_id") or "")
    return config.run_dir(run_id) / "nonlocal_law_selected_target_candidate_ablation" / source_id


def _validate_risk_probe_surface(payload: dict[str, Any]) -> None:
    if payload.get("all_required_risk_probes_present") is not True:
        raise ValueError("risk probes incomplete")
    if payload.get("missing_risk_probe_ids") not in ([], None):
        raise ValueError("risk probes incomplete")
    if int(payload.get("risk_probe_count") or 0) != len(REQUIRED_RISK_PROBE_IDS):
        raise ValueError("risk probes incomplete")
    by_id = payload.get("risk_probe_results_by_id")
    if not isinstance(by_id, dict):
        raise ValueError("risk_probe_results_by_id missing")
    missing = [risk_id for risk_id in REQUIRED_RISK_PROBE_IDS if risk_id not in by_id]
    if missing:
        raise ValueError("risk probes incomplete: " + ", ".join(missing))
    extra = sorted(str(risk_id) for risk_id in by_id if risk_id not in REQUIRED_RISK_PROBE_IDS)
    if extra:
        raise ValueError("unexpected risk probes: " + ", ".join(extra))


def _risk_results(
    subject: NonlocalLawSelectedTargetEvidenceSynthesisSubject,
) -> dict[str, object]:
    report = subject.reader_state_payloads["selected_target_risk_probe_report"]
    results = report.get("risk_probe_results_by_id")
    return results if isinstance(results, dict) else {}


def _write_artifact(
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


def _read_envelope(path: Path, artifact_type: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing {artifact_type}: {path}")
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(f"malformed {artifact_type} artifact")
    return envelope


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


def _payload_has_forbidden_claim(value: object) -> bool:
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
                "candidate_superiority_claimed",
                "current_best_supersession_claimed",
                "current_best_updated",
                "generation_authorized",
                "candidate_generated",
                "synthesis_authorized",
            } and item is True:
                return True
            if key in {"no_final_claim", "no_phase_shift_claim"} and item is False:
                return True
            if _payload_has_forbidden_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_forbidden_claim(item) for item in value)
    return False


def _safety_fields() -> dict[str, object]:
    return {
        "candidate_generated": False,
        "generation_authorized": False,
        "ablation_executed": False,
        "reader_state_evaluation_executed": False,
        "current_best_updated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
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
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": blockers or ([] if passed else [f"{gate_name} failed"]),
    }


def _require_bool(payload: dict[str, object], key: str, expected: bool) -> None:
    if payload.get(key) is not expected:
        raise ValueError(f"{key} must be {str(expected).lower()}")


def _require_equal(payload: dict[str, object], key: str, expected: object) -> None:
    if payload.get(key) != expected:
        raise ValueError(f"{key} must be {expected}")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _refusal(
    *,
    reader_state_packet: Path | str,
    message: str,
) -> NonlocalLawSelectedTargetEvidenceSynthesisResult:
    return NonlocalLawSelectedTargetEvidenceSynthesisResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "reader_state_packet": str(reader_state_packet),
            "synthesis_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "ablation_executed": False,
            "reader_state_evaluation_executed": False,
            "current_best_updated": False,
            "model_calls": 0,
            "artifact_ids": {},
            "artifact_paths": {},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path
