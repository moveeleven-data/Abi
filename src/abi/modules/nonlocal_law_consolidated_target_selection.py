"""Deterministic target selection from nonlocal law cycle consolidation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_ACTIVE_RISK_IDS,
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    EXPECTED_STRONGEST_RIVAL_STATUS,
    EXPECTED_UPDATE_METHOD,
    LESSON_SCOPE,
    NONLOCAL_LAW_CYCLE_CONSOLIDATION_ARTIFACT_TYPES,
    TARGET_SEED_IDS,
    TARGET_SEED_TO_RISK,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_LINEAGE_ID = (
    "nonlocal_law_consolidated_target_selection_v1"
)
NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_CREATED_BY = (
    "nonlocal_law_consolidated_target_selection_v1_controller"
)
NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_ARTIFACT_TYPES = (
    "nonlocal_law_consolidated_target_selection_packet",
    "source_consolidation_intake_summary",
    "selected_target_decision",
    "target_candidate_ranking_report",
    "selected_risk_evidence_report",
    "non_selected_risk_carry_forward_report",
    "current_best_context_report",
    "non_universalization_guard_carry_forward_report",
    "strongest_rival_blocker_carry_forward_report",
    "next_work_order_readiness_report",
    "target_selection_gate_report",
    "project_health_scope_guard_report",
)

EXPECTED_CONSOLIDATION_PACKET_ID = "packet_0002"
SELECTED_TARGET_SEED_ID = "convert_static_retrospective_trace_to_living_event_sequence"
SELECTED_RISK_ID = "event_sequence_may_remain_static"
SELECTED_TARGET_CLASS = "living_event_sequence_repair_target"
TARGET_SCOPE = "next_loop_nonlocal_causal_sequence_risk"
TARGET_STATEMENT = (
    "Convert packet_0002's static or retrospective object traces into living "
    "consequences that actively condition the reader before explanation."
)
NEXT_RECOMMENDED_ACTION = (
    "review_consolidated_target_selection_before_work_order_planning"
)
NEXT_WORK_ORDER_ACTION = "plan_work_order_for_selected_consolidated_target"
SELECTED_RISK_READER_STATE_PROBE = (
    "The spoon tremor and fracture-light improve event pressure, but much of "
    "the sequence remains retrospective: glass gone, broom gone, hand gone, "
    "fall stored."
)
SELECTED_RISK_HANDLING = (
    "Preserve object-event pressure but check whether traces become living "
    "consequences rather than retrospective inventory."
)
NON_SELECTED_RISK_IDS = (
    "explanation_may_arrive_too_explicitly",
    "chemistry_register_risk",
    "conclusion_may_summarize_law",
)


@dataclass(frozen=True)
class NonlocalLawConsolidatedTargetSelectionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawConsolidatedTargetSelectionSubject:
    run_id: str
    consolidation_packet_dir: Path
    consolidation_packet_id: str
    consolidation_packet_artifact_id: str | None
    consolidation_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    active_risks: tuple[dict[str, Any], ...]
    allowed_target_seed_ids: tuple[str, ...]


def run_nonlocal_law_consolidated_target_selection(
    config: AbiConfig,
    *,
    consolidation_packet: Path | str,
    operator_reviewed: bool,
) -> NonlocalLawConsolidatedTargetSelectionResult:
    initialize_database(config)
    consolidation_packet_dir = _resolve_path(config, consolidation_packet)
    if not operator_reviewed:
        return _refusal(
            consolidation_packet=consolidation_packet_dir,
            message=(
                "Nonlocal law consolidated target selection refused; "
                "--operator-reviewed is required."
            ),
        )
    if not consolidation_packet_dir.exists() or not consolidation_packet_dir.is_dir():
        return _refusal(
            consolidation_packet=consolidation_packet_dir,
            message=(
                "Nonlocal law consolidated target selection refused; "
                f"consolidation packet directory not found: {consolidation_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, consolidation_packet_dir)
        _validate_subject_for_target_selection(config, subject)
    except ValueError as error:
        return _refusal(consolidation_packet=consolidation_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                consolidation_packet=consolidation_packet_dir,
                message=(
                    "Nonlocal law consolidated target selection refused; run is "
                    f"not registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_consolidated_target_selection"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_consolidation_intake_summary"] = (
            _build_source_consolidation_intake_summary(subject, packet_dir)
        )
        artifacts["source_consolidation_intake_summary"] = writer.write_artifact(
            "source_consolidation_intake_summary",
            payloads["source_consolidation_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["selected_target_decision"] = _build_selected_target_decision(
            subject
        )
        artifacts["selected_target_decision"] = writer.write_artifact(
            "selected_target_decision",
            payloads["selected_target_decision"],
            parent_ids=[artifacts["source_consolidation_intake_summary"].id],
        )

        payloads["target_candidate_ranking_report"] = (
            _build_target_candidate_ranking_report(subject)
        )
        artifacts["target_candidate_ranking_report"] = writer.write_artifact(
            "target_candidate_ranking_report",
            payloads["target_candidate_ranking_report"],
            parent_ids=[
                artifacts["source_consolidation_intake_summary"].id,
                artifacts["selected_target_decision"].id,
            ],
        )

        payloads["selected_risk_evidence_report"] = (
            _build_selected_risk_evidence_report(subject)
        )
        artifacts["selected_risk_evidence_report"] = writer.write_artifact(
            "selected_risk_evidence_report",
            payloads["selected_risk_evidence_report"],
            parent_ids=[artifacts["selected_target_decision"].id],
        )

        payloads["non_selected_risk_carry_forward_report"] = (
            _build_non_selected_risk_carry_forward_report(subject)
        )
        artifacts["non_selected_risk_carry_forward_report"] = writer.write_artifact(
            "non_selected_risk_carry_forward_report",
            payloads["non_selected_risk_carry_forward_report"],
            parent_ids=[
                artifacts["selected_risk_evidence_report"].id,
                artifacts["target_candidate_ranking_report"].id,
            ],
        )

        payloads["current_best_context_report"] = _build_current_best_context_report(
            subject
        )
        artifacts["current_best_context_report"] = writer.write_artifact(
            "current_best_context_report",
            payloads["current_best_context_report"],
            parent_ids=[artifacts["selected_target_decision"].id],
        )

        payloads["non_universalization_guard_carry_forward_report"] = (
            _build_non_universalization_guard_carry_forward_report(subject)
        )
        artifacts["non_universalization_guard_carry_forward_report"] = (
            writer.write_artifact(
                "non_universalization_guard_carry_forward_report",
                payloads["non_universalization_guard_carry_forward_report"],
                parent_ids=[
                    artifacts["current_best_context_report"].id,
                    artifacts["selected_target_decision"].id,
                ],
            )
        )

        payloads["strongest_rival_blocker_carry_forward_report"] = (
            _build_strongest_rival_blocker_carry_forward_report(subject)
        )
        artifacts["strongest_rival_blocker_carry_forward_report"] = (
            writer.write_artifact(
                "strongest_rival_blocker_carry_forward_report",
                payloads["strongest_rival_blocker_carry_forward_report"],
                parent_ids=[
                    artifacts["selected_target_decision"].id,
                    artifacts["non_universalization_guard_carry_forward_report"].id,
                ],
            )
        )

        payloads["next_work_order_readiness_report"] = (
            _build_next_work_order_readiness_report(subject)
        )
        artifacts["next_work_order_readiness_report"] = writer.write_artifact(
            "next_work_order_readiness_report",
            payloads["next_work_order_readiness_report"],
            parent_ids=[
                artifacts["selected_target_decision"].id,
                artifacts["current_best_context_report"].id,
                artifacts["strongest_rival_blocker_carry_forward_report"].id,
            ],
        )

        payloads["target_selection_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["target_selection_gate_report"] = writer.write_artifact(
            "target_selection_gate_report",
            payloads["target_selection_gate_report"],
            parent_ids=[
                artifacts["selected_target_decision"].id,
                artifacts["selected_risk_evidence_report"].id,
                artifacts["non_selected_risk_carry_forward_report"].id,
                artifacts["next_work_order_readiness_report"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["target_selection_gate_report"].id,
                artifacts["strongest_rival_blocker_carry_forward_report"].id,
            ],
        )

        payloads["nonlocal_law_consolidated_target_selection_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["nonlocal_law_consolidated_target_selection_packet"] = (
            writer.write_artifact(
                "nonlocal_law_consolidated_target_selection_packet",
                payloads["nonlocal_law_consolidated_target_selection_packet"],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type
                    != "nonlocal_law_consolidated_target_selection_packet"
                ],
            )
        )

        gate_report = payloads["target_selection_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_consolidated_target_selection_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    return NonlocalLawConsolidatedTargetSelectionResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    consolidation_packet_dir: Path,
) -> NonlocalLawConsolidatedTargetSelectionSubject:
    payloads = _load_required_payloads(consolidation_packet_dir)
    packet = payloads["nonlocal_law_cycle_consolidation_packet"]
    run_id = _required_text(packet.get("run_id"), "consolidation packet missing run_id")
    packet_id = str(packet.get("packet_id") or consolidation_packet_dir.name)

    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(
            connection,
            consolidation_packet_dir / "nonlocal_law_cycle_consolidation_packet.json",
        )
    artifact_ids = _string_dict(packet.get("artifact_ids"))
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    active_risks = _active_risks(payloads)
    allowed_seed_ids = _allowed_target_seed_ids(payloads)
    return NonlocalLawConsolidatedTargetSelectionSubject(
        run_id=run_id,
        consolidation_packet_dir=consolidation_packet_dir,
        consolidation_packet_id=packet_id,
        consolidation_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        consolidation_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        active_risks=tuple(active_risks),
        allowed_target_seed_ids=tuple(allowed_seed_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in NONLOCAL_LAW_CYCLE_CONSOLIDATION_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Nonlocal law consolidated target selection refused; "
                f"consolidation packet missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Nonlocal law consolidated target selection refused; malformed "
                f"consolidation artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_subject_for_target_selection(
    config: AbiConfig,
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> None:
    packet = _packet(subject)
    _validate_no_forbidden_source_claims(subject.payloads)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; consolidation "
            "packet is not accepted."
        )
    if subject.consolidation_packet_id != EXPECTED_CONSOLIDATION_PACKET_ID:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; stale or "
            f"unsupported consolidation packet {subject.consolidation_packet_id}."
        )
    if _has_newer_current_valid_consolidation(config, subject):
        raise ValueError(
            "Nonlocal law consolidated target selection refused; consolidation "
            "packet is stale or superseded by a newer corrected consolidation packet."
        )
    if packet.get("consolidation_executed") is not True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; consolidation "
            "was not executed."
        )
    if (
        packet.get("current_best_for_next_loop_packet_id")
        != EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
    ):
        raise ValueError(
            "Nonlocal law consolidated target selection refused; "
            "current_best_for_next_loop_packet_id must be packet_0002."
        )
    if (
        packet.get("prior_current_best_candidate_packet_id")
        != EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
    ):
        raise ValueError(
            "Nonlocal law consolidated target selection refused; "
            "prior_current_best_candidate_packet_id must be packet_0063."
        )
    if packet.get("law_id") != DISCOVERED_LOCAL_LAW_ID:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; law_id must be "
            f"{DISCOVERED_LOCAL_LAW_ID}."
        )
    if packet.get("lesson_scope") != LESSON_SCOPE:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; lesson_scope "
            f"must be {LESSON_SCOPE}."
        )
    if packet.get("universalized_rule_created") is not False:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; "
            "universalized_rule_created must be false."
        )
    if packet.get("target_selection_must_use_consolidated_risk_memory") is not True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; target selection "
            "must use consolidated risk memory."
        )
    if packet.get("ready_for_next_target_selection") is not True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; source is not "
            "ready for next target selection."
        )
    if packet.get("target_selection_authorized") is True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; source unexpectedly "
            "authorized target selection."
        )
    if packet.get("work_order_authorized") is True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; source authorized "
            "a work order."
        )
    if packet.get("generation_authorized") is True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; source authorized "
            "generation."
        )
    if len(subject.active_risks) < len(EXPECTED_ACTIVE_RISK_IDS):
        raise ValueError(
            "Nonlocal law consolidated target selection refused; active risks "
            "missing or fewer than four."
        )
    risk_ids = {str(risk.get("risk_id") or "") for risk in subject.active_risks}
    missing_risks = [
        risk_id for risk_id in EXPECTED_ACTIVE_RISK_IDS if risk_id not in risk_ids
    ]
    if missing_risks:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; active risks "
            "missing: " + ", ".join(missing_risks)
        )
    missing_seeds = [
        seed_id
        for seed_id in TARGET_SEED_IDS
        if seed_id not in subject.allowed_target_seed_ids
    ]
    if missing_seeds:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; allowed target "
            "seeds missing: " + ", ".join(missing_seeds)
        )
    rival = subject.payloads["strongest_rival_pressure_memory"]
    if rival.get("strongest_rival_remains_blocking") is not True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; strongest rival "
            "must remain blocking."
        )
    if rival.get("strongest_rival_status") != EXPECTED_STRONGEST_RIVAL_STATUS:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; strongest rival "
            f"status must be {EXPECTED_STRONGEST_RIVAL_STATUS}."
        )
    if packet.get("strongest_rival_defeated_claimed") is True:
        raise ValueError(
            "Nonlocal law consolidated target selection refused; strongest-rival "
            "defeat claim appears."
        )
    if _accepted_target_selection_exists(config, subject):
        raise ValueError(
            "Nonlocal law consolidated target selection refused; corrected "
            "current-valid target selection already exists for this consolidation packet."
        )


def _build_source_consolidation_intake_summary(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_consolidation_packet_dir": str(subject.consolidation_packet_dir),
        "source_consolidation_packet_artifact_id": (
            subject.consolidation_packet_artifact_id
        ),
        "source_consolidation_artifact_ids": dict(subject.consolidation_artifact_ids),
        "source_consolidation_accepted": True,
        "source_consolidation_current_valid": True,
        "source_consolidation_ready_for_target_selection": True,
        "operator_reviewed": True,
        "target_selection_executed": True,
        "target_selected": True,
        "selected_target_count": 1,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "source_consolidation_intake_summary_v1_controller",
    }


def _build_selected_target_decision(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "target_scope": TARGET_SCOPE,
        "target_statement": TARGET_STATEMENT,
        "selection_basis": [
            "It is the deepest structural risk because it concerns causal sequence, not local wording.",
            "It protects the completed lesson: consequence before explanation helped.",
            "It prevents the next loop from becoming generic vividness or sentence polish.",
            "It attacks the remaining weakness that objects may still function as retrospective traces rather than live consequences.",
            "It can be tested later without copying rival scene, object inventory, diction, cadence, or plot.",
            "It preserves packet_0002's current-best-for-next-loop status while preparing a bounded work order.",
        ],
        "why_selected_before_other_risks": [
            "reduce_explanation_explicitness_after_initial_pressure risks sentence-level polish before the event-sequence issue is addressed",
            "repair_chemistry_register_intrusion is a sharp register risk but narrower than the causal-field problem",
            "enact_return_instead_of_summarizing_law should follow clarification of living-event sequence",
        ],
        "target_selection_authorized_by_consolidation": False,
        "target_selection_executed_by_this_packet": True,
        "work_order_required_before_generation": True,
        "generation_requires_future_authorization": True,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "selected_target_decision_v1_controller",
    }


def _build_target_candidate_ranking_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    rankings = [
        {
            "rank": 1,
            "target_seed_id": SELECTED_TARGET_SEED_ID,
            "risk_id": SELECTED_RISK_ID,
            "selected": True,
            "selection_reason": (
                "deepest structural risk; repairs causal sequence before local "
                "wording or return polish"
            ),
        },
        {
            "rank": 2,
            "target_seed_id": "reduce_explanation_explicitness_after_initial_pressure",
            "risk_id": "explanation_may_arrive_too_explicitly",
            "selected": False,
            "not_selected_reason": (
                "important, but selecting it first risks sentence polish before "
                "event-sequence causality is clarified"
            ),
        },
        {
            "rank": 3,
            "target_seed_id": "enact_return_instead_of_summarizing_law",
            "risk_id": "conclusion_may_summarize_law",
            "selected": False,
            "not_selected_reason": (
                "return repair should follow a clearer living sequence to return through"
            ),
        },
        {
            "rank": 4,
            "target_seed_id": "repair_chemistry_register_intrusion",
            "risk_id": "chemistry_register_risk",
            "selected": False,
            "not_selected_reason": (
                "register risk is real but narrower than the causal-field problem"
            ),
        },
    ]
    return {
        **_source_fields(subject),
        "ranked_target_candidates": rankings,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_count": 1,
        "allowed_target_seed_ids": list(subject.allowed_target_seed_ids),
        "unselected_target_seed_ids": [
            item["target_seed_id"] for item in rankings if not item["selected"]
        ],
        "target_selected": True,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "target_candidate_ranking_report_v1_controller",
    }


def _build_selected_risk_evidence_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    risk = _risk_by_id(subject, SELECTED_RISK_ID)
    return {
        **_source_fields(subject),
        "risk_id": SELECTED_RISK_ID,
        "risk": risk.get("risk")
        or "event sequence may remain too static or retrospective",
        "source_reader_state_probe": SELECTED_RISK_READER_STATE_PROBE,
        "target_seed": SELECTED_TARGET_SEED_ID,
        "blocks_finalization": True,
        "not_selected_yet_from_source": bool(risk.get("not_selected_yet", True)),
        "selected_now": True,
        "recommended_next_handling": SELECTED_RISK_HANDLING,
        "evidence_status": "selected_for_next_loop_work_order_planning",
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "selected_risk_evidence_report_v1_controller",
    }


def _build_non_selected_risk_carry_forward_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    risks = []
    for risk_id in NON_SELECTED_RISK_IDS:
        risk = _risk_by_id(subject, risk_id)
        risks.append(
            {
                "risk_id": risk_id,
                "risk": risk.get("risk") or risk_id,
                "target_seed": risk.get("target_seed") or _target_seed_for_risk(risk_id),
                "carried_forward": True,
                "selected_now": False,
                "blocks_finalization": True,
                "not_resolved": True,
                "recommended_next_handling": risk.get("recommended_next_handling"),
            }
        )
    return {
        **_source_fields(subject),
        "non_selected_risks": risks,
        "non_selected_risk_count": len(risks),
        "selected_risk_id": SELECTED_RISK_ID,
        "all_non_selected_risks_carried_forward": True,
        "target_selected": True,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "non_selected_risk_carry_forward_report_v1_controller",
    }


def _build_current_best_context_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "current_best_for_next_loop_packet_id": (
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ),
        "prior_current_best_candidate_packet_id": EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
        "current_best_update_method": EXPECTED_UPDATE_METHOD,
        "global_state_mutation_performed": False,
        "packet_0002_is_working_basis_not_final_artifact": True,
        "packet_0063_preserved_as_history": True,
        "current_best_decision_packet_is_source_of_truth": True,
        "target_selected": True,
        "work_order_created": False,
        "generation_authorized": False,
        "finalization_eligible": False,
        "worker": "current_best_context_report_v1_controller",
    }


def _build_non_universalization_guard_carry_forward_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "universalized_rule_created": False,
        "lesson_scope": LESSON_SCOPE,
        "selected_target_does_not_universalize_law": True,
        "selected_target_does_not_mean_always_add_events": True,
        "selected_target_does_not_mean_imitate_rival_causal_sequence": True,
        "selected_target_does_not_mean_object_detail_is_always_better_than_explanation": True,
        "guardrails": [
            "selected target does not universalize first_read_pressure_precedes_explanation_law",
            "selected target does not mean always add events",
            "selected target does not mean imitate rival causal sequence",
            "selected target does not mean object detail is always better than explanation",
        ],
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "non_universalization_guard_carry_forward_report_v1_controller",
    }


def _build_strongest_rival_blocker_carry_forward_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "strongest_rival_status": EXPECTED_STRONGEST_RIVAL_STATUS,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "selected_target_must_not_copy": [
            "rival objects",
            "rival scenes",
            "rival diction",
            "rival cadence",
            "rival plot",
            "rival domestic sequence",
        ],
        "strongest_rival_pressure_remains_active_until": (
            "future ablation, reader-state evaluation, and synthesis say otherwise"
        ),
        "strongest_rival_comparison_passed": False,
        "blocks_finalization": True,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "strongest_rival_blocker_carry_forward_report_v1_controller",
    }


def _build_next_work_order_readiness_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ready_for_work_order_planning": True,
        "work_order_authorized": False,
        "work_order_requires_separate_command": True,
        "generation_authorized": False,
        "generation_requires_future_work_order": True,
        "generation_requires_separate_authorization": True,
        "recommended_next_action": NEXT_WORK_ORDER_ACTION,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "target_selected": True,
        "work_order_created": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "next_work_order_readiness_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_consolidation_accepted", True),
        _gate_result("source_consolidation_current_valid", True),
        _gate_result("source_consolidation_ready_for_target_selection", True),
        _gate_result("selected_exactly_one_target", True),
        _gate_result("selected_target_from_allowed_seed", True),
        _gate_result("current_best_for_next_loop_preserved", True),
        _gate_result("non_universalization_guard_preserved", True),
        _gate_result("strongest_rival_blocking_preserved", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result("work_order_created", False, ["work order not created yet"]),
        _gate_result("generation_authorized", False, ["generation is not authorized"]),
        _gate_result("finalization_eligible", False, ["target selection is not final evidence"]),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival remains narrowed but blocking"],
        ),
    ]
    failed = [str(gate["gate_name"]) for gate in gate_results if not gate["passed"]]
    blockers = [
        "work order has not been created",
        "generation is not authorized",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "target_selection_executed": True,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_count": 1,
        "target_selected": True,
        "work_order_created": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "gate_results": gate_results,
        "failed_gates": failed,
        "unresolved_blockers": blockers,
        "worker": "target_selection_gate_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    checks = [
        _check("no_openai_calls", True),
        _check("no_text_generation", True),
        _check("no_work_order_created", True),
        _check("no_generation_authorization", True),
        _check("no_ablation_performed", True),
        _check("no_reader_state_evaluation_performed", True),
        _check("no_synthesis_performed", True),
        _check("no_finalization", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
        _check("no_strongest_rival_defeat_claim", True),
        _check("selected_exactly_one_target", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "target_selection_only": True,
        "selected_target_count": 1,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_consolidated_target_selection_packet",
    )
    return {
        **_source_fields(subject),
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_consolidated_target_selection_packet",
        ],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "selected_target_count": 1,
        },
        "target_selection_executed": True,
        "target_selected": True,
        "selected_target_count": 1,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "target_scope": TARGET_SCOPE,
        "work_order_created": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "ready_for_work_order_planning": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["target_selection_gate_report"],
        "worker": "nonlocal_law_consolidated_target_selection_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_consolidated_target_selection_packet"]
    return {
        **packet,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
    }


def _source_fields(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_consolidation_packet_id": subject.consolidation_packet_id,
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_ablation_packet_id": packet.get("source_ablation_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "proof_packet_id": packet.get("proof_packet_id"),
        "prior_reader_state_packet_id": packet.get("prior_reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "learned_cycle_lesson_id": packet.get("learned_cycle_lesson_id"),
        "lesson_scope": packet.get("lesson_scope"),
        "transferable_principle_status": packet.get("transferable_principle_status"),
        "universalized_rule_created": packet.get("universalized_rule_created"),
    }


def _packet(subject: NonlocalLawConsolidatedTargetSelectionSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_cycle_consolidation_packet"]


def _active_risks(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    risk_payload = payloads["active_risk_memory"]
    risks = risk_payload.get("active_risks")
    if not isinstance(risks, list):
        return []
    return [risk for risk in risks if isinstance(risk, dict)]


def _allowed_target_seed_ids(payloads: dict[str, dict[str, Any]]) -> list[str]:
    readiness = payloads["next_target_selection_readiness_report"]
    seeds = readiness.get("allowed_target_seed_ids")
    if isinstance(seeds, list):
        return [seed for seed in seeds if isinstance(seed, str)]
    packet_seeds = payloads["nonlocal_law_cycle_consolidation_packet"].get(
        "next_target_seeds"
    )
    if isinstance(packet_seeds, list):
        return [seed for seed in packet_seeds if isinstance(seed, str)]
    return []


def _risk_by_id(
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
    risk_id: str,
) -> dict[str, Any]:
    for risk in subject.active_risks:
        if risk.get("risk_id") == risk_id:
            return risk
    return {}


def _target_seed_for_risk(risk_id: str) -> str | None:
    for seed_id, mapped_risk_id in TARGET_SEED_TO_RISK.items():
        if mapped_risk_id == risk_id:
            return seed_id
    return None


def _has_newer_current_valid_consolidation(
    config: AbiConfig,
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_cycle_consolidation"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= subject.consolidation_packet_id:
            continue
        path = packet_dir / "nonlocal_law_cycle_consolidation_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_loop_review_packet_id")
            == _packet(subject).get("source_loop_review_packet_id")
            and payload.get("current_best_for_next_loop_packet_id")
            == EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
            and payload.get("target_selection_must_use_consolidated_risk_memory")
            is True
            and payload.get("ready_for_next_target_selection") is True
        ):
            return True
    return False


def _accepted_target_selection_exists(
    config: AbiConfig,
    subject: NonlocalLawConsolidatedTargetSelectionSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_consolidated_target_selection"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        path = packet_dir / "nonlocal_law_consolidated_target_selection_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_consolidation_packet_id")
            == subject.consolidation_packet_id
            and payload.get("target_selection_executed") is True
            and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
            and payload.get("selected_risk_id") == SELECTED_RISK_ID
            and payload.get("selected_target_count") == 1
            and payload.get("work_order_created") is False
            and payload.get("generation_authorized") is False
            and payload.get("candidate_generated") is False
            and int(payload.get("model_calls") or 0) == 0
        ):
            return True
    return False


def _validate_no_forbidden_source_claims(payloads: dict[str, dict[str, Any]]) -> None:
    if _payload_has_forbidden_claim(payloads):
        raise ValueError(
            "Nonlocal law consolidated target selection refused; finality, "
            "phase-shift, rival-defeat, work-order, generation, or candidate claim appears."
        )


def _payload_has_forbidden_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finality_claimed",
                "phase_shift_claimed",
                "strongest_rival_defeated_claimed",
                "candidate_superiority_claimed",
                "final_artifact",
                "final_claim",
            } and item is True:
                return True
            if key in {
                "generation_authorized",
                "candidate_generated",
                "work_order_created",
            } and item is True:
                return True
            if key == "finalization_eligible" and item is True:
                return True
            if _payload_has_forbidden_claim(item):
                return True
    if isinstance(value, list):
        return any(_payload_has_forbidden_claim(item) for item in value)
    return False


def _read_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(f"Malformed packet artifact: {path.name}")
    return envelope["payload"]


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
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
    return row_to_artifact(row) if row is not None else None


def _gate_result(
    gate_name: str,
    passed: bool,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": list(blockers or []),
    }


def _check(check_name: str, passed: bool) -> dict[str, object]:
    return {"check_name": check_name, "passed": passed}


def _required_text(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Nonlocal law consolidated target selection refused; {message}.")


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(item, str) and item
    }


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config.root / candidate


def _refusal(
    *,
    consolidation_packet: Path,
    message: str,
) -> NonlocalLawConsolidatedTargetSelectionResult:
    return NonlocalLawConsolidatedTargetSelectionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "message": message,
            "consolidation_packet": str(consolidation_packet),
            "target_selection_executed": False,
            "target_selected": False,
            "selected_target_count": 0,
            "work_order_created": False,
            "work_order_authorized": False,
            "generation_authorized": False,
            "candidate_generated": False,
            "model_calls": 0,
            "counts": {"model_calls": 0},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )
