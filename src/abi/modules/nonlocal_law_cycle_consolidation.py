"""Deterministic nonlocal law cycle-consolidation packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_CYCLE_CONSOLIDATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.evidence_loop_review import (
    NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_ARTIFACT_TYPES,
)
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_CYCLE_CONSOLIDATION_LINEAGE_ID = (
    "nonlocal_law_cycle_consolidation_v1"
)
NONLOCAL_LAW_CYCLE_CONSOLIDATION_CREATED_BY = (
    "nonlocal_law_cycle_consolidation_v1_controller"
)
NONLOCAL_LAW_CYCLE_CONSOLIDATION_ARTIFACT_TYPES = (
    "nonlocal_law_cycle_consolidation_packet",
    "source_loop_review_intake_summary",
    "learned_local_law_cycle_lesson",
    "non_universalization_guard_report",
    "current_best_transition_memory",
    "active_risk_memory",
    "strongest_rival_pressure_memory",
    "abi_ear_signal_memory",
    "next_loop_constraint_memory",
    "next_target_selection_readiness_report",
    "cycle_consolidation_gate_report",
    "project_health_scope_guard_report",
)

EXPECTED_LOOP_REVIEW_PACKET_ID = "packet_0002"
EXPECTED_SOURCE_SYNTHESIS_PACKET_ID = "packet_0002"
EXPECTED_SOURCE_READER_STATE_PACKET_ID = "packet_0002"
EXPECTED_SOURCE_CANDIDATE_PACKET_ID = "packet_0002"
EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID = "packet_0063"
EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID = "packet_0002"
EXPECTED_UPDATE_METHOD = "loop_review_packet_only"
EXPECTED_STRONGEST_RIVAL_STATUS = "narrowed_but_blocking"
EXPECTED_ACTIVE_RISK_IDS = (
    "explanation_may_arrive_too_explicitly",
    "event_sequence_may_remain_static",
    "chemistry_register_risk",
    "conclusion_may_summarize_law",
)
TARGET_SEED_IDS = (
    "reduce_explanation_explicitness_after_initial_pressure",
    "convert_static_retrospective_trace_to_living_event_sequence",
    "repair_chemistry_register_intrusion",
    "enact_return_instead_of_summarizing_law",
)
TARGET_SEED_TO_RISK = {
    "reduce_explanation_explicitness_after_initial_pressure": (
        "explanation_may_arrive_too_explicitly"
    ),
    "convert_static_retrospective_trace_to_living_event_sequence": (
        "event_sequence_may_remain_static"
    ),
    "repair_chemistry_register_intrusion": "chemistry_register_risk",
    "enact_return_instead_of_summarizing_law": "conclusion_may_summarize_law",
}
RISK_HANDLING = {
    "explanation_may_arrive_too_explicitly": (
        "Use the next target-selection command to test explanation timing without "
        "authorizing a new candidate in this consolidation packet."
    ),
    "event_sequence_may_remain_static": (
        "Preserve object-event pressure but check whether traces become living "
        "consequences rather than retrospective inventory."
    ),
    "chemistry_register_risk": (
        "Repair conceptual-register intrusion without weakening the object and "
        "tactile field that packet_0002 improved."
    ),
    "conclusion_may_summarize_law": (
        "Make return occur through object relation instead of a stated rule."
    ),
}
LEARNED_CYCLE_LESSON_ID = (
    "consequence_before_explanation_improves_first_read_pressure_in_this_work"
)
TRANSFERABLE_PRINCIPLE_STATUS = "provisional_context_bound"
LESSON_SCOPE = "work_local"
NEXT_RECOMMENDED_ACTION = "review_cycle_consolidation_before_next_target_selection"
NEXT_TARGET_SELECTION_ACTION = "select_next_target_from_consolidated_cycle_memory"
FORBIDDEN_UNIVERSALIZATIONS = (
    "always delay explanation",
    "always begin with objects",
    "always use table/spoon/ring fields",
    "always solve by adding object-event sequence",
    "always treat explanation as failure",
    "always imitate rival causal staging",
)


@dataclass(frozen=True)
class NonlocalLawCycleConsolidationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawCycleConsolidationSubject:
    run_id: str
    loop_review_packet_dir: Path
    loop_review_packet_id: str
    loop_review_packet_artifact_id: str | None
    loop_review_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    active_risks: tuple[dict[str, Any], ...]
    next_target_options: tuple[dict[str, Any], ...]


def run_nonlocal_law_cycle_consolidation(
    config: AbiConfig,
    *,
    loop_review_packet: Path | str,
    operator_reviewed: bool,
) -> NonlocalLawCycleConsolidationResult:
    initialize_database(config)
    loop_review_packet_dir = _resolve_path(config, loop_review_packet)
    if not operator_reviewed:
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Nonlocal law cycle consolidation refused; --operator-reviewed "
                "is required."
            ),
        )
    if not loop_review_packet_dir.exists() or not loop_review_packet_dir.is_dir():
        return _refusal(
            loop_review_packet=loop_review_packet_dir,
            message=(
                "Nonlocal law cycle consolidation refused; loop-review packet "
                f"directory not found: {loop_review_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, loop_review_packet_dir)
        _validate_subject_for_consolidation(config, subject)
    except ValueError as error:
        return _refusal(loop_review_packet=loop_review_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                loop_review_packet=loop_review_packet_dir,
                message=(
                    "Nonlocal law cycle consolidation refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_CYCLE_CONSOLIDATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_cycle_consolidation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CYCLE_CONSOLIDATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CYCLE_CONSOLIDATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_loop_review_intake_summary"] = (
            _build_source_loop_review_intake_summary(subject, packet_dir)
        )
        artifacts["source_loop_review_intake_summary"] = writer.write_artifact(
            "source_loop_review_intake_summary",
            payloads["source_loop_review_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["learned_local_law_cycle_lesson"] = (
            _build_learned_local_law_cycle_lesson(subject)
        )
        artifacts["learned_local_law_cycle_lesson"] = writer.write_artifact(
            "learned_local_law_cycle_lesson",
            payloads["learned_local_law_cycle_lesson"],
            parent_ids=[artifacts["source_loop_review_intake_summary"].id],
        )

        payloads["non_universalization_guard_report"] = (
            _build_non_universalization_guard_report(subject)
        )
        artifacts["non_universalization_guard_report"] = writer.write_artifact(
            "non_universalization_guard_report",
            payloads["non_universalization_guard_report"],
            parent_ids=[artifacts["learned_local_law_cycle_lesson"].id],
        )

        payloads["current_best_transition_memory"] = (
            _build_current_best_transition_memory(subject)
        )
        artifacts["current_best_transition_memory"] = writer.write_artifact(
            "current_best_transition_memory",
            payloads["current_best_transition_memory"],
            parent_ids=[
                artifacts["source_loop_review_intake_summary"].id,
                artifacts["learned_local_law_cycle_lesson"].id,
            ],
        )

        payloads["active_risk_memory"] = _build_active_risk_memory(subject)
        artifacts["active_risk_memory"] = writer.write_artifact(
            "active_risk_memory",
            payloads["active_risk_memory"],
            parent_ids=[
                artifacts["source_loop_review_intake_summary"].id,
                artifacts["current_best_transition_memory"].id,
            ],
        )

        payloads["strongest_rival_pressure_memory"] = (
            _build_strongest_rival_pressure_memory(subject)
        )
        artifacts["strongest_rival_pressure_memory"] = writer.write_artifact(
            "strongest_rival_pressure_memory",
            payloads["strongest_rival_pressure_memory"],
            parent_ids=[
                artifacts["current_best_transition_memory"].id,
                artifacts["active_risk_memory"].id,
            ],
        )

        payloads["abi_ear_signal_memory"] = _build_abi_ear_signal_memory(subject)
        artifacts["abi_ear_signal_memory"] = writer.write_artifact(
            "abi_ear_signal_memory",
            payloads["abi_ear_signal_memory"],
            parent_ids=[
                artifacts["learned_local_law_cycle_lesson"].id,
                artifacts["strongest_rival_pressure_memory"].id,
            ],
        )

        payloads["next_loop_constraint_memory"] = (
            _build_next_loop_constraint_memory(subject)
        )
        artifacts["next_loop_constraint_memory"] = writer.write_artifact(
            "next_loop_constraint_memory",
            payloads["next_loop_constraint_memory"],
            parent_ids=[
                artifacts["active_risk_memory"].id,
                artifacts["abi_ear_signal_memory"].id,
            ],
        )

        payloads["next_target_selection_readiness_report"] = (
            _build_next_target_selection_readiness_report(subject)
        )
        artifacts["next_target_selection_readiness_report"] = writer.write_artifact(
            "next_target_selection_readiness_report",
            payloads["next_target_selection_readiness_report"],
            parent_ids=[
                artifacts["next_loop_constraint_memory"].id,
                artifacts["non_universalization_guard_report"].id,
            ],
        )

        payloads["cycle_consolidation_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["cycle_consolidation_gate_report"] = writer.write_artifact(
            "cycle_consolidation_gate_report",
            payloads["cycle_consolidation_gate_report"],
            parent_ids=[
                artifacts["source_loop_review_intake_summary"].id,
                artifacts["learned_local_law_cycle_lesson"].id,
                artifacts["non_universalization_guard_report"].id,
                artifacts["active_risk_memory"].id,
                artifacts["next_target_selection_readiness_report"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["cycle_consolidation_gate_report"].id,
                artifacts["strongest_rival_pressure_memory"].id,
            ],
        )

        payloads["nonlocal_law_cycle_consolidation_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["nonlocal_law_cycle_consolidation_packet"] = writer.write_artifact(
            "nonlocal_law_cycle_consolidation_packet",
            payloads["nonlocal_law_cycle_consolidation_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "nonlocal_law_cycle_consolidation_packet"
            ],
        )

        gate_report = payloads["cycle_consolidation_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="cycle_consolidation_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_CYCLE_CONSOLIDATION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    return NonlocalLawCycleConsolidationResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    loop_review_packet_dir: Path,
) -> NonlocalLawCycleConsolidationSubject:
    payloads = _load_required_payloads(loop_review_packet_dir)
    loop_packet = payloads["nonlocal_law_candidate_loop_review_packet"]
    run_id = _required_text(loop_packet.get("run_id"), "loop-review missing run_id")

    with connect(config.db_path) as connection:
        loop_artifact = _artifact_for_path(
            connection,
            loop_review_packet_dir / "nonlocal_law_candidate_loop_review_packet.json",
        )

    artifact_ids = _string_dict(loop_packet.get("artifact_ids"))
    source_parent_ids = _unique(
        [
            loop_artifact.id if loop_artifact else None,
            *artifact_ids.values(),
        ]
    )
    active_risks = _active_risks(payloads)
    next_options = _next_target_options(payloads)
    return NonlocalLawCycleConsolidationSubject(
        run_id=run_id,
        loop_review_packet_dir=loop_review_packet_dir,
        loop_review_packet_id=str(loop_packet.get("packet_id") or loop_review_packet_dir.name),
        loop_review_packet_artifact_id=loop_artifact.id if loop_artifact else None,
        loop_review_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        active_risks=tuple(active_risks),
        next_target_options=tuple(next_options),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in NONLOCAL_LAW_CANDIDATE_LOOP_REVIEW_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Nonlocal law cycle consolidation refused; loop-review packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Nonlocal law cycle consolidation refused; malformed loop-review "
                f"artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_subject_for_consolidation(
    config: AbiConfig,
    subject: NonlocalLawCycleConsolidationSubject,
) -> None:
    packet = _loop_packet(subject)
    _validate_no_forbidden_claims(subject.payloads)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop-review packet is not accepted."
        )
    if subject.loop_review_packet_id != EXPECTED_LOOP_REVIEW_PACKET_ID:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; stale or unsupported "
            f"loop-review packet {subject.loop_review_packet_id}."
        )
    if _has_newer_matching_loop_review(config, subject):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop-review packet is stale "
            "or superseded by a newer current-valid loop-review packet."
        )
    if (
        packet.get("superseded_loop_review_packet_id") is not None
        and packet.get("superseded_loop_review_packet_id") == subject.loop_review_packet_id
    ):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop-review packet supersedes itself."
        )
    if packet.get("source_synthesis_packet_id") != EXPECTED_SOURCE_SYNTHESIS_PACKET_ID:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; source synthesis packet must be "
            f"{EXPECTED_SOURCE_SYNTHESIS_PACKET_ID}."
        )
    if (
        packet.get("source_reader_state_packet_id")
        != EXPECTED_SOURCE_READER_STATE_PACKET_ID
    ):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; source reader-state packet must "
            f"be {EXPECTED_SOURCE_READER_STATE_PACKET_ID}."
        )
    if packet.get("source_candidate_packet_id") != EXPECTED_SOURCE_CANDIDATE_PACKET_ID:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; source candidate packet must be "
            f"{EXPECTED_SOURCE_CANDIDATE_PACKET_ID}."
        )
    if (
        packet.get("prior_current_best_candidate_packet_id")
        != EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID
    ):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; prior current best candidate "
            f"must be {EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID}."
        )
    if (
        packet.get("current_best_for_next_loop_packet_id")
        != EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
    ):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; current_best_for_next_loop "
            f"must be {EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID}."
        )
    if packet.get("current_best_update_method") != EXPECTED_UPDATE_METHOD:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; current_best_update_method "
            f"must be {EXPECTED_UPDATE_METHOD}."
        )
    if packet.get("current_best_decision_packet_is_source_of_truth") is not True:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; current-best decision packet "
            "must be source of truth."
        )
    if packet.get("current_best_state_mutation_performed") is not False:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop review must not mutate "
            "global current-best state."
        )
    if packet.get("strongest_rival_remains_blocking") is not True:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; strongest rival must remain "
            "blocking."
        )
    if packet.get("strongest_rival_status") != EXPECTED_STRONGEST_RIVAL_STATUS:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; strongest rival status must "
            f"be {EXPECTED_STRONGEST_RIVAL_STATUS}."
        )
    if packet.get("generation_authorized") is not False:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop review authorized generation."
        )
    if packet.get("candidate_generated") is not False:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop review generated a candidate."
        )
    if packet.get("work_order_created") is True:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop review created a work order."
        )
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; loop review made model calls."
        )
    if len(subject.active_risks) < len(EXPECTED_ACTIVE_RISK_IDS):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; active risks missing or fewer "
            "than four."
        )
    risk_ids = {str(risk.get("risk_id") or "") for risk in subject.active_risks}
    missing = [risk_id for risk_id in EXPECTED_ACTIVE_RISK_IDS if risk_id not in risk_ids]
    if missing:
        raise ValueError(
            "Nonlocal law cycle consolidation refused; active risks missing: "
            + ", ".join(missing)
        )
    if _accepted_consolidation_exists(config, subject):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; corrected current-valid "
            "consolidation already exists for this loop-review packet."
        )


def _build_source_loop_review_intake_summary(
    subject: NonlocalLawCycleConsolidationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _loop_packet(subject)
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_loop_review_packet_dir": str(subject.loop_review_packet_dir),
        "source_loop_review_packet_artifact_id": subject.loop_review_packet_artifact_id,
        "source_loop_review_artifact_ids": dict(subject.loop_review_artifact_ids),
        "loop_review_accepted": True,
        "loop_review_decision": packet.get("decision"),
        "current_best_update_method": packet.get("current_best_update_method"),
        "current_best_decision_packet_is_source_of_truth": True,
        "current_best_state_mutation_performed": False,
        "cycle_consolidation_required_before_next_repair": True,
        "target_selection_requires_cycle_consolidation": True,
        "operator_reviewed": True,
        "consolidation_executed": True,
        "target_selected": False,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "source_loop_review_intake_summary_v1_controller",
    }


def _build_learned_local_law_cycle_lesson(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "learned_cycle_lesson_id": LEARNED_CYCLE_LESSON_ID,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "lesson_statement": (
            "In this work, packet_0002 improved first-read pressure when "
            "object-event consequence was staged before explicit explanation."
        ),
        "evidence_basis": [
            "live model-backed rival diagnostic found packet_0063 explained before pressure matured",
            "packet_0002 accepted under law-guided generation",
            "ablation identified coherent law-bearing choices",
            "live model-backed reader-state evaluation found first-read pressure improved",
            "synthesis classified law effect supported_but_incomplete",
            "loop review promoted packet_0002 as working current best",
        ],
        "lesson_limitations": [
            "strongest rival remains blocking",
            "active risks remain",
            "reader-state support is supportive_mixed, not conclusive",
            "candidate_law_effect is supported_but_incomplete",
            "no finalization",
            "no strongest-rival defeat",
            "this lesson is work-local, not universal",
        ],
        "transferable_principle": (
            "consequence may need to precede explanation when a work's "
            "reader-state pressure is being stabilized too early by conceptual naming."
        ),
        "transfer_warning": (
            "Do not universalize into always delay explanation or always use objects "
            "before ideas."
        ),
        "lesson_scope": LESSON_SCOPE,
        "transferable_principle_status": TRANSFERABLE_PRINCIPLE_STATUS,
        "memory_not_final_proof": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "learned_local_law_cycle_lesson_v1_controller",
    }


def _build_non_universalization_guard_report(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "universalized_rule_created": False,
        "forbidden_universalizations": list(FORBIDDEN_UNIVERSALIZATIONS),
        "correct_generalization_level": (
            "This cycle provides a context-bound diagnostic lens, not a universal "
            "craft rule."
        ),
        "apply_only_when": [
            "current work shows early conceptual stabilization before pressure matures",
            "reader-state evidence suggests pressure improves when consequence precedes naming",
            "non-imitation constraints can be preserved",
            "local field supports the transfer",
        ],
        "do_not_apply_when": [
            "explanation itself is the pressure engine",
            "abstraction is the work's local field",
            "object detail becomes generic vividness",
            "delay weakens clarity without increasing pressure",
            "the result imitates a rival",
        ],
        "lesson_scope": LESSON_SCOPE,
        "transferable_principle_status": TRANSFERABLE_PRINCIPLE_STATUS,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "non_universalization_guard_report_v1_controller",
    }


def _build_current_best_transition_memory(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    packet = _loop_packet(subject)
    return {
        **_source_fields(subject),
        "prior_current_best_candidate_packet_id": EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
        "current_best_for_next_loop_packet_id": (
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ),
        "transition_status": "packet_owned_working_current_best_for_next_loop",
        "transition_source_of_truth": subject.loop_review_packet_id,
        "current_best_update_method": EXPECTED_UPDATE_METHOD,
        "global_current_best_state_mutated": False,
        "prior_current_best_preserved_as_history": True,
        "prior_preservation_summary": packet.get("prior_preservation_summary"),
        "promotion_summary": packet.get("evidence_summary"),
        "evidence_strength": packet.get("evidence_strength")
        or "loop_review_promotable_not_final",
        "not_finalization_evidence": True,
        "strongest_rival_remains_blocking": True,
        "worker": "current_best_transition_memory_v1_controller",
    }


def _build_active_risk_memory(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    source = {str(risk.get("risk_id") or ""): risk for risk in subject.active_risks}
    risks: list[dict[str, object]] = []
    for seed_id in TARGET_SEED_IDS:
        risk_id = TARGET_SEED_TO_RISK[seed_id]
        source_risk = source.get(risk_id, {})
        risks.append(
            {
                "risk_id": risk_id,
                "risk": source_risk.get("risk") or risk_id,
                "source_loop_review_packet_id": subject.loop_review_packet_id,
                "source_reader_state_probe": source_risk.get("reader_state_probe"),
                "blocks_finalization": True,
                "target_seed": seed_id,
                "recommended_next_handling": RISK_HANDLING[risk_id],
                "not_selected_yet": True,
            }
        )
    return {
        **_source_fields(subject),
        "active_risk_count": len(risks),
        "active_risks": risks,
        "target_seeds": list(TARGET_SEED_IDS),
        "all_risks_block_finalization": True,
        "target_selected": False,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "active_risk_memory_v1_controller",
    }


def _build_strongest_rival_pressure_memory(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "strongest_rival_status": EXPECTED_STRONGEST_RIVAL_STATUS,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_comparison_passed": False,
        "pressure_memory": (
            "The nonlocal law-guided candidate narrowed rival pressure, but the "
            "rival remains a blocker for finalization and future strategy."
        ),
        "what_transferred": [
            "causal timing",
            "pressure before naming",
            "object-event consequence before explicit explanation",
        ],
        "what_must_not_transfer": [
            "rival object inventory",
            "rival scene",
            "rival diction",
            "rival cadence",
            "rival plot",
        ],
        "blocks_finalization": True,
        "next_cycle_pressure_policy": (
            "Carry strongest-rival pressure forward as a blocker; do not claim "
            "defeat or use consolidation as comparison evidence."
        ),
        "worker": "strongest_rival_pressure_memory_v1_controller",
    }


def _build_abi_ear_signal_memory(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "pressure_timing_signal": (
            "first-read pressure improved when the opening made the reader "
            "register consequence before instruction."
        ),
        "register_risk_signal": (
            '"Chemistry gives thought a place to search" may import a conceptual '
            "register that calls attention to framing rather than object-event enactment."
        ),
        "return_signal": (
            "reread return improved when the ending sent the reader back through "
            "table/dust/spoon/saucer consequences."
        ),
        "static_trace_warning": (
            "object traces can still remain too retrospective if they do not "
            "become living consequences."
        ),
        "explanation_signal": (
            "explanation improved when earned, but sections that state the law "
            "directly keep explicitness risk active."
        ),
        "non_imitation_signal": (
            "rival advantage should transfer as causal timing only, not object "
            "inventory, scene, diction, cadence, or plot."
        ),
        "memory_not_final_proof": True,
        "abi_ear_solved_claimed": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "abi_ear_signal_memory_v1_controller",
    }


def _build_next_loop_constraint_memory(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "constraints": [
            "do not universalize the local law",
            "do not select a target inside consolidation",
            "do not create a work order inside consolidation",
            "do not authorize generation inside consolidation",
            "preserve packet_0002 as current best for next loop by packet decision only",
            "carry packet_0063 as prior current-best history",
            "carry strongest-rival pressure as blocking",
            "carry all four active risks",
        ],
        "allowed_next_target_seed_ids": list(TARGET_SEED_IDS),
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "target_selection_requires_separate_command": True,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "next_loop_constraint_memory_v1_controller",
    }


def _build_next_target_selection_readiness_report(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
        "target_selection_requires_separate_command": True,
        "work_order_authorized": False,
        "generation_authorized": False,
        "recommended_next_action": NEXT_TARGET_SELECTION_ACTION,
        "allowed_target_seed_ids": list(TARGET_SEED_IDS),
        "target_seed_count": len(TARGET_SEED_IDS),
        "target_selection_must_use_consolidated_memory": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "next_target_selection_readiness_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: NonlocalLawCycleConsolidationSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_loop_review_accepted", True),
        _gate_result("source_loop_review_current_valid", True),
        _gate_result("learned_cycle_lesson_recorded", True),
        _gate_result("lesson_scope_work_local", True),
        _gate_result("non_universalization_guard_recorded", True),
        _gate_result("abi_ear_signal_memory_recorded", True),
        _gate_result("all_active_risks_carried_forward", True),
        _gate_result("next_target_seeds_exposed", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_target_selection", True),
        _gate_result("no_work_order", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival remains narrowed but blocking"],
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["cycle consolidation is memory, not finalization evidence"],
        ),
    ]
    failed = [str(gate["gate_name"]) for gate in gate_results if not gate["passed"]]
    blockers = [
        "strongest rival remains blocking",
        "active risks remain",
        "next target has not been selected",
        "work order has not been created",
        "generation is not authorized",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "consolidation_executed": True,
        "learned_cycle_lesson_id": LEARNED_CYCLE_LESSON_ID,
        "lesson_scope": payloads["learned_local_law_cycle_lesson"]["lesson_scope"],
        "universalized_rule_created": False,
        "ready_for_next_target_selection": True,
        "target_selection_authorized": False,
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
        "worker": "cycle_consolidation_gate_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: NonlocalLawCycleConsolidationSubject,
) -> dict[str, object]:
    checks = [
        _check("no_openai_calls", True),
        _check("no_generation_performed", True),
        _check("no_target_selected", True),
        _check("no_work_order_created", True),
        _check("no_authorization_created", True),
        _check("no_ablation_performed", True),
        _check("no_reader_state_evaluation_performed", True),
        _check("no_synthesis_performed", True),
        _check("no_global_current_best_mutation", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
        _check("no_strongest_rival_defeat_claim", True),
        _check("local_law_not_universalized", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "consolidation_only": True,
        "target_selected": False,
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
    subject: NonlocalLawCycleConsolidationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CYCLE_CONSOLIDATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_cycle_consolidation_packet",
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
        "artifact_types": [*artifacts, "nonlocal_law_cycle_consolidation_packet"],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "consolidation_executed": True,
        "learned_cycle_lesson_id": LEARNED_CYCLE_LESSON_ID,
        "lesson_scope": LESSON_SCOPE,
        "transferable_principle_status": TRANSFERABLE_PRINCIPLE_STATUS,
        "universalized_rule_created": False,
        "active_risk_count": len(payloads["active_risk_memory"]["active_risks"]),
        "active_risks_remain": True,
        "next_target_seeds": list(TARGET_SEED_IDS),
        "ready_for_next_target_selection": True,
        "target_selected": False,
        "target_selection_authorized": False,
        "work_order_created": False,
        "work_order_authorized": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["cycle_consolidation_gate_report"],
        "worker": "nonlocal_law_cycle_consolidation_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: NonlocalLawCycleConsolidationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_cycle_consolidation_packet"]
    return {
        **packet,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
    }


def _source_fields(subject: NonlocalLawCycleConsolidationSubject) -> dict[str, object]:
    packet = _loop_packet(subject)
    return {
        "source_loop_review_packet_id": subject.loop_review_packet_id,
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
        "law_id": packet.get("law_id") or DISCOVERED_LOCAL_LAW_ID,
    }


def _loop_packet(subject: NonlocalLawCycleConsolidationSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_candidate_loop_review_packet"]


def _active_risks(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    risk_payload = payloads["active_risk_carry_forward_report"]
    risks = risk_payload.get("active_risks")
    if not isinstance(risks, list):
        return []
    return [risk for risk in risks if isinstance(risk, dict)]


def _next_target_options(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    seed = payloads["next_cycle_target_seed_report"]
    options = seed.get("next_cycle_target_options")
    if isinstance(options, list):
        return [option for option in options if isinstance(option, dict)]
    packet_options = payloads["nonlocal_law_candidate_loop_review_packet"].get(
        "next_cycle_target_options"
    )
    if isinstance(packet_options, list):
        return [option for option in packet_options if isinstance(option, dict)]
    return []


def _has_newer_matching_loop_review(
    config: AbiConfig,
    subject: NonlocalLawCycleConsolidationSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_candidate_loop_review"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= subject.loop_review_packet_id:
            continue
        path = packet_dir / "nonlocal_law_candidate_loop_review_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_synthesis_packet_id")
            == _loop_packet(subject).get("source_synthesis_packet_id")
            and payload.get("current_best_decision_packet_is_source_of_truth") is True
            and payload.get("current_best_for_next_loop_packet_id")
            == EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ):
            return True
    return False


def _accepted_consolidation_exists(
    config: AbiConfig,
    subject: NonlocalLawCycleConsolidationSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_cycle_consolidation"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
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
            == subject.loop_review_packet_id
            and payload.get("consolidation_executed") is True
            and payload.get("universalized_rule_created") is False
            and payload.get("target_selected") is False
            and payload.get("work_order_created") is False
            and payload.get("generation_authorized") is False
            and payload.get("candidate_generated") is False
            and int(payload.get("model_calls") or 0) == 0
        ):
            return True
    return False


def _validate_no_forbidden_claims(payloads: dict[str, dict[str, Any]]) -> None:
    if _payload_has_forbidden_claim(payloads):
        raise ValueError(
            "Nonlocal law cycle consolidation refused; finality, phase-shift, "
            "rival-defeat, generation, target-selection, or work-order claim appears."
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
                "target_selected",
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
    raise ValueError(f"Nonlocal law cycle consolidation refused; {message}.")


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
    loop_review_packet: Path,
    message: str,
) -> NonlocalLawCycleConsolidationResult:
    return NonlocalLawCycleConsolidationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "message": message,
            "loop_review_packet": str(loop_review_packet),
            "consolidation_executed": False,
            "target_selected": False,
            "work_order_created": False,
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
