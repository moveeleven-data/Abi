"""Controller-owned work-order planning for a selected nonlocal law target."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_consolidated_target_selection import (
    EXPECTED_CONSOLIDATION_PACKET_ID,
    NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_ARTIFACT_TYPES,
    SELECTED_RISK_ID,
    SELECTED_TARGET_CLASS,
    SELECTED_TARGET_SEED_ID,
    TARGET_SCOPE,
    TARGET_STATEMENT,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    EXPECTED_STRONGEST_RIVAL_STATUS,
    LESSON_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_LINEAGE_ID = (
    "nonlocal_law_selected_target_work_order_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_CREATED_BY = (
    "nonlocal_law_selected_target_work_order_v1_controller"
)
NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND = (
    "selected_nonlocal_law_target_work_order"
)
WORK_ORDER_SCOPE = "living_event_sequence_repair"
NEXT_RECOMMENDED_ACTION = (
    "review_selected_target_work_order_before_generation_authorization"
)
SUPERSESSION_REASON_AUTHORIZATION_SURFACE_MISSING = (
    "nonlocal_law_selected_target_work_order_authorization_surface_missing"
)
CORE_REPAIR_PRINCIPLE = (
    "Object traces should not merely report finished events. They should become "
    "active conditions that alter what the reader expects, notices, and rereads "
    "before conceptual naming stabilizes them."
)
WORK_ORDER_SUMMARY = (
    "Plan a bounded living-event-sequence repair for the selected nonlocal law "
    "target without authorizing generation."
)
LIVING_EVENT_SEQUENCE_DEFINITION = (
    "A living event sequence is a sequence in which object traces become active "
    "conditions for later perception, not merely evidence that something finished "
    "before the text began."
)
GENERATION_CONTRACT_VERSION = 1
PROMPT_CONTRACT_ID = "autonomous.selected_nonlocal_law_target_generation.v1"
MATERIALITY_POLICY_ID = "selected_nonlocal_law_target_materiality_v1"
SEMANTIC_VALIDATOR_ID = "selected_nonlocal_law_target_semantic_validator_v1"
FUTURE_SCHEMA = "SelectedNonlocalLawTargetGenerationOutput@1"

DO_NOT_SOLVE_BY = (
    "simply adding more incidents",
    "adding generic action",
    "increasing grimness",
    "polishing sentences",
    "deleting explanation",
    "copying rival causal sequence",
    "copying rival objects/scenes/diction/cadence/plot",
    "weakening packet_0002's earned explanation timing",
    "weakening packet_0002's table/dust/spoon/saucer/ring field",
)
AUTHORIZATION_DO_NOT_SOLVE_BY = (
    *DO_NOT_SOLVE_BY,
    "weakening packet_0002's object field",
    "treating object inventory as living causality",
)
REPAIR_STEPS = (
    "identify static retrospective traces in packet_0002's current object field",
    "convert at least one trace into an active condition that changes later perception",
    "build causal dependency between selected object-events",
    "make consequence felt before conceptual naming",
    "preserve earned explanation timing",
    "preserve packet_0002's table/ring/dust/spoon/saucer/light field",
    "avoid rival object inventory, scene, diction, cadence, and causal plot",
)
PROTECTED_PACKET_0002_STRENGTHS = (
    "first-read pressure improved",
    "object-event consequence improved",
    "explanation timing improved",
    "reread return improved",
    "non-imitation passed",
    "table/ring/dust/spoon/saucer/light field",
    "no outside answer pressure",
    "proof packet_0034",
    "prior reader-state packet_0013",
    "source-chain through loop-review/consolidation/target-selection",
)
FORBIDDEN_RIVAL_INVENTORY = (
    "rival causal sequence",
    "rival objects",
    "rival scenes",
    "rival diction",
    "rival cadence",
    "rival plot",
    "rival domestic sequence",
    "cup-return sequence",
    "windowsill/bill/shoes/drag-mark/scar/sink/payment/shade inventory",
)
FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE = (
    "cup",
    "windowsill",
    "bill",
    "shoes",
    "drag-mark",
    "scar",
    "sink",
    "payment",
    "shade",
    "cup-return sequence",
)
FORBIDDEN_RIVAL_IMITATION_MODES = (
    "rival diction",
    "rival scene structure",
    "rival cadence",
    "rival causal plot",
    "rival domestic sequence",
    "rival object inventory",
)
FORBIDDEN_REGRESSIONS = (
    "free rewrite beyond selected target",
    "generic vividness replacing causality",
    "object inventory treated as living sequence",
    "premature explanation",
    "deleted explanation",
    "rival imitation",
)
TARGET_UNIT_IDS = (
    "static_trace_to_active_condition",
    "causal_bridge_between_object_events",
    "living_consequence_before_naming",
    "preserve_earned_explanation_timing",
    "preserve_packet_0002_object_field",
    "non_imitation_and_rival_guard",
    "carry_forward_unselected_risks",
)
MATERIALITY_VALIDATION_REQUIREMENTS = (
    "living_event_sequence_present",
    "static_retrospective_trace_reduced",
    "existing_object_field_preserved",
    "explanation_timing_preserved",
    "non_imitation_passed",
    "generic_vividness_absent",
    "rival_sequence_absent",
    "no_finality_or_phase_shift_claim",
)
MATERIALITY_REQUIREMENTS = (
    "materially convert static trace into active condition",
    "materially build causal bridge between object-events",
    "materially make consequence felt before naming",
    "preserve earned explanation timing",
    "preserve packet_0002 object field",
    "preserve non-imitation constraints",
    "carry forward unselected risks",
)
SEMANTIC_VALIDATION_REQUIREMENTS = MATERIALITY_VALIDATION_REQUIREMENTS
GENERATION_AUTHORIZATION_ALLOWED_DECISIONS = (
    "authorize_one_bounded_selected_target_generation",
    "refuse_generation_authorization",
)
ABLATION_CONTROLS = (
    "full_selected_target_intervention",
    "revert_to_packet_0002",
    "remove_living_event_sequence_repair",
    "restore_static_retrospective_trace",
    "generic_incident_addition_control",
    "rival_imitation_control",
    "strongest_rival_comparison",
)
READER_STATE_FOCUS = (
    "do object traces become active conditions?",
    "does sequence feel live rather than retrospective?",
    "does explanation remain earned?",
    "does the candidate preserve packet_0002's gains?",
    "does it avoid rival imitation?",
    "does strongest-rival pressure remain active?",
)

NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_work_order_packet",
    "source_target_selection_intake_summary",
    "selected_target_work_order_scope",
    "living_event_sequence_repair_map",
    "protected_current_best_packet_0002_strengths",
    "prior_current_best_packet_0063_preservation_report",
    "forbidden_rival_imitation_inventory",
    "selected_target_unit_map",
    "non_selected_risk_carry_forward_report",
    "future_generation_contract",
    "materiality_and_semantic_validation_plan",
    "ablation_and_reader_eval_plan",
    "selected_target_work_order_gate_report",
    "project_health_scope_guard_report",
)


@dataclass(frozen=True)
class NonlocalLawSelectedTargetWorkOrderResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawSelectedTargetWorkOrderSubject:
    run_id: str
    target_selection_packet_dir: Path
    target_selection_packet_id: str
    target_selection_packet_artifact_id: str | None
    target_selection_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    corrected_current_valid_work_order_exists: bool
    superseded_work_order_packet_id: str | None
    supersession_reason: str | None
    stale_surface_failures: tuple[str, ...]


@dataclass(frozen=True)
class WorkOrderSupersessionContext:
    corrected_current_valid_work_order_exists: bool
    superseded_work_order_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


def run_nonlocal_law_selected_target_work_order_planning(
    config: AbiConfig,
    *,
    target_selection_packet: Path | str,
    operator_reviewed: bool,
) -> NonlocalLawSelectedTargetWorkOrderResult:
    initialize_database(config)
    target_selection_packet_dir = _resolve_path(config, target_selection_packet)
    if not operator_reviewed:
        return _refusal(
            target_selection_packet=target_selection_packet_dir,
            message=(
                "Nonlocal law selected-target work-order planning refused; "
                "--operator-reviewed is required."
            ),
        )
    if (
        not target_selection_packet_dir.exists()
        or not target_selection_packet_dir.is_dir()
    ):
        return _refusal(
            target_selection_packet=target_selection_packet_dir,
            message=(
                "Nonlocal law selected-target work-order planning refused; "
                "target-selection packet directory not found: "
                f"{target_selection_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, target_selection_packet_dir)
        _validate_subject(config, subject)
    except ValueError as error:
        return _refusal(
            target_selection_packet=target_selection_packet_dir,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                target_selection_packet=target_selection_packet_dir,
                message=(
                    "Nonlocal law selected-target work-order planning refused; "
                    f"run is not registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_work_order"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_target_selection_intake_summary"] = (
            _build_source_target_selection_intake_summary(subject, packet_dir)
        )
        artifacts["source_target_selection_intake_summary"] = writer.write_artifact(
            "source_target_selection_intake_summary",
            payloads["source_target_selection_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["selected_target_work_order_scope"] = (
            _build_selected_target_work_order_scope(subject)
        )
        artifacts["selected_target_work_order_scope"] = writer.write_artifact(
            "selected_target_work_order_scope",
            payloads["selected_target_work_order_scope"],
            parent_ids=[artifacts["source_target_selection_intake_summary"].id],
        )

        payloads["living_event_sequence_repair_map"] = (
            _build_living_event_sequence_repair_map(subject)
        )
        artifacts["living_event_sequence_repair_map"] = writer.write_artifact(
            "living_event_sequence_repair_map",
            payloads["living_event_sequence_repair_map"],
            parent_ids=[artifacts["selected_target_work_order_scope"].id],
        )

        payloads["protected_current_best_packet_0002_strengths"] = (
            _build_protected_current_best_packet_0002_strengths(subject)
        )
        artifacts["protected_current_best_packet_0002_strengths"] = (
            writer.write_artifact(
                "protected_current_best_packet_0002_strengths",
                payloads["protected_current_best_packet_0002_strengths"],
                parent_ids=[artifacts["living_event_sequence_repair_map"].id],
            )
        )

        payloads["prior_current_best_packet_0063_preservation_report"] = (
            _build_prior_current_best_packet_0063_preservation_report(subject)
        )
        artifacts["prior_current_best_packet_0063_preservation_report"] = (
            writer.write_artifact(
                "prior_current_best_packet_0063_preservation_report",
                payloads["prior_current_best_packet_0063_preservation_report"],
                parent_ids=[artifacts["protected_current_best_packet_0002_strengths"].id],
            )
        )

        payloads["forbidden_rival_imitation_inventory"] = (
            _build_forbidden_rival_imitation_inventory(subject)
        )
        artifacts["forbidden_rival_imitation_inventory"] = writer.write_artifact(
            "forbidden_rival_imitation_inventory",
            payloads["forbidden_rival_imitation_inventory"],
            parent_ids=[artifacts["source_target_selection_intake_summary"].id],
        )

        payloads["selected_target_unit_map"] = _build_selected_target_unit_map(subject)
        artifacts["selected_target_unit_map"] = writer.write_artifact(
            "selected_target_unit_map",
            payloads["selected_target_unit_map"],
            parent_ids=[
                artifacts["living_event_sequence_repair_map"].id,
                artifacts["forbidden_rival_imitation_inventory"].id,
            ],
        )

        payloads["non_selected_risk_carry_forward_report"] = (
            _build_non_selected_risk_carry_forward_report(subject)
        )
        artifacts["non_selected_risk_carry_forward_report"] = writer.write_artifact(
            "non_selected_risk_carry_forward_report",
            payloads["non_selected_risk_carry_forward_report"],
            parent_ids=[artifacts["selected_target_unit_map"].id],
        )

        payloads["future_generation_contract"] = _build_future_generation_contract(
            subject
        )
        artifacts["future_generation_contract"] = writer.write_artifact(
            "future_generation_contract",
            payloads["future_generation_contract"],
            parent_ids=[artifacts["selected_target_unit_map"].id],
        )

        payloads["materiality_and_semantic_validation_plan"] = (
            _build_materiality_and_semantic_validation_plan(subject)
        )
        artifacts["materiality_and_semantic_validation_plan"] = (
            writer.write_artifact(
                "materiality_and_semantic_validation_plan",
                payloads["materiality_and_semantic_validation_plan"],
                parent_ids=[
                    artifacts["future_generation_contract"].id,
                    artifacts["selected_target_unit_map"].id,
                ],
            )
        )

        payloads["ablation_and_reader_eval_plan"] = (
            _build_ablation_and_reader_eval_plan(subject)
        )
        artifacts["ablation_and_reader_eval_plan"] = writer.write_artifact(
            "ablation_and_reader_eval_plan",
            payloads["ablation_and_reader_eval_plan"],
            parent_ids=[artifacts["materiality_and_semantic_validation_plan"].id],
        )

        payloads["selected_target_work_order_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["selected_target_work_order_gate_report"] = writer.write_artifact(
            "selected_target_work_order_gate_report",
            payloads["selected_target_work_order_gate_report"],
            parent_ids=[
                artifacts["future_generation_contract"].id,
                artifacts["ablation_and_reader_eval_plan"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[artifacts["selected_target_work_order_gate_report"].id],
        )

        payloads["nonlocal_law_selected_target_work_order_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
            )
        )
        artifacts["nonlocal_law_selected_target_work_order_packet"] = (
            writer.write_artifact(
                "nonlocal_law_selected_target_work_order_packet",
                payloads["nonlocal_law_selected_target_work_order_packet"],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type != "nonlocal_law_selected_target_work_order_packet"
                ],
            )
        )

        gate_report = payloads["selected_target_work_order_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_selected_target_work_order_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_LINEAGE_ID,
        )

    return NonlocalLawSelectedTargetWorkOrderResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    target_selection_packet_dir: Path,
) -> NonlocalLawSelectedTargetWorkOrderSubject:
    payloads = _load_required_payloads(target_selection_packet_dir)
    packet = payloads["nonlocal_law_consolidated_target_selection_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "target-selection packet missing run_id",
    )
    packet_id = str(packet.get("packet_id") or target_selection_packet_dir.name)
    supersession = _work_order_supersession_context(
        config=config,
        run_id=run_id,
        source_target_selection_packet_id=packet_id,
    )
    packet_path = (
        target_selection_packet_dir
        / "nonlocal_law_consolidated_target_selection_packet.json"
    )
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    artifact_ids = _string_dict(packet.get("artifact_ids"))
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    return NonlocalLawSelectedTargetWorkOrderSubject(
        run_id=run_id,
        target_selection_packet_dir=target_selection_packet_dir,
        target_selection_packet_id=packet_id,
        target_selection_packet_artifact_id=(
            packet_artifact.id if packet_artifact else None
        ),
        target_selection_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        corrected_current_valid_work_order_exists=(
            supersession.corrected_current_valid_work_order_exists
        ),
        superseded_work_order_packet_id=supersession.superseded_work_order_packet_id,
        supersession_reason=supersession.supersession_reason,
        stale_surface_failures=supersession.stale_surface_failures,
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in NONLOCAL_LAW_CONSOLIDATED_TARGET_SELECTION_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Nonlocal law selected-target work-order planning refused; "
                f"target-selection packet missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("payload"), dict
        ):
            raise ValueError(
                "Nonlocal law selected-target work-order planning refused; "
                f"malformed target-selection artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_subject(
    config: AbiConfig,
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> None:
    packet = _packet(subject)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; "
            "target-selection packet is not accepted."
        )
    if _has_newer_current_valid_target_selection(config, subject):
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; "
            "target-selection packet is stale or superseded."
        )
    _validate_no_forbidden_source_claims(subject.payloads)
    _require_bool(packet, "target_selection_executed", True)
    _require_equal(packet, "source_consolidation_packet_id", EXPECTED_CONSOLIDATION_PACKET_ID)
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(packet, "selected_target_class", SELECTED_TARGET_CLASS)
    _require_equal(packet, "target_scope", TARGET_SCOPE)
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
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(packet, "lesson_scope", LESSON_SCOPE)
    _require_bool(packet, "selected_target_does_not_universalize_law", True)
    _require_bool(packet, "source_chain_coherent", True)
    _require_bool(packet, "ready_for_selected_target_work_order_planning", True)
    _require_bool(packet, "work_order_created", False)
    _require_bool(packet, "work_order_authorized", False)
    _require_bool(packet, "generation_authorized", False)
    _require_bool(packet, "candidate_generated", False)
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; source "
            "target-selection packet must have zero model calls."
        )

    readiness = subject.payloads["next_work_order_readiness_report"]
    _require_bool(readiness, "ready_for_selected_target_work_order_planning", True)
    _require_equal(readiness, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(readiness, "selected_risk_id", SELECTED_RISK_ID)
    _require_bool(readiness, "work_order_authorized", False)
    _require_bool(readiness, "work_order_requires_separate_command", True)
    _require_bool(readiness, "generation_authorized", False)

    rival = subject.payloads["strongest_rival_blocker_carry_forward_report"]
    _require_equal(rival, "strongest_rival_status", EXPECTED_STRONGEST_RIVAL_STATUS)
    _require_bool(rival, "strongest_rival_remains_blocking", True)
    _require_bool(rival, "strongest_rival_defeated_claimed", False)

    if subject.corrected_current_valid_work_order_exists:
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; corrected "
            "current-valid work order already exists for this target-selection packet."
        )


def _build_source_target_selection_intake_summary(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_target_selection_packet_dir": str(subject.target_selection_packet_dir),
        "source_target_selection_packet_artifact_id": (
            subject.target_selection_packet_artifact_id
        ),
        "source_target_selection_artifact_ids": dict(
            subject.target_selection_artifact_ids
        ),
        "source_target_selection_accepted": True,
        "operator_reviewed": True,
        "work_order_kind": NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "source_target_selection_intake_summary_v1_controller",
    }


def _build_selected_target_work_order_scope(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "summary": WORK_ORDER_SUMMARY,
        "work_order_summary": WORK_ORDER_SUMMARY,
        "work_order_kind": NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
        "work_order_scope": WORK_ORDER_SCOPE,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "target_scope": TARGET_SCOPE,
        "target_statement": TARGET_STATEMENT,
        "core_repair_principle": CORE_REPAIR_PRINCIPLE,
        "do_not_solve_by": list(DO_NOT_SOLVE_BY),
        "free_rewrite_allowed": False,
        "generation_allowed": False,
        "work_order_bounded": True,
        "work_order_authorizes_generation": False,
        "generation_requires_separate_authorization": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "selected_target_work_order_scope_v1_controller",
    }


def _build_living_event_sequence_repair_map(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "work_order_scope": WORK_ORDER_SCOPE,
        "selected_risk_evidence": (
            "The spoon tremor and fracture-light improve event pressure, but much "
            "of the sequence remains retrospective: glass gone, broom gone, hand "
            "gone, fall stored."
        ),
        "core_repair_principle": CORE_REPAIR_PRINCIPLE,
        "living_event_sequence_definition": LIVING_EVENT_SEQUENCE_DEFINITION,
        "repair_steps": list(REPAIR_STEPS),
        "do_not_solve_by": list(AUTHORIZATION_DO_NOT_SOLVE_BY),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "repair_map": [
            {
                "from": "retrospective object trace",
                "to": "active condition shaping later perception",
            },
            {
                "from": "separate object evidence",
                "to": "causal bridge between object events",
            },
            {
                "from": "named law or pressure",
                "to": "felt consequence before conceptual naming stabilizes",
            },
        ],
        "bounded_to_existing_object_field": True,
        "causal_sequence_not_object_inventory": True,
        "object_events_must_condition_later_perception": True,
        "explanation_must_remain_earned": True,
        "rival_imitation_forbidden": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "living_event_sequence_repair_map_v1_controller",
    }


def _build_protected_current_best_packet_0002_strengths(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "current_best_for_next_loop_packet_id": (
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ),
        "protected_strengths": list(PROTECTED_PACKET_0002_STRENGTHS),
        "protected_object_field": [
            "table",
            "ring",
            "dust",
            "spoon",
            "saucer",
            "refrigerator hum",
            "light",
        ],
        "proof_packet_id": "packet_0034",
        "prior_reader_state_packet_id": "packet_0013",
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "protected_current_best_packet_0002_strengths_v1_controller",
    }


def _build_prior_current_best_packet_0063_preservation_report(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_0063_preserved_as_history": True,
        "prior_current_best_candidate_packet_id": EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
        "current_best_for_next_loop_packet_id": (
            EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
        ),
        "proof_packet_id": "packet_0034",
        "prior_reader_state_packet_id": "packet_0013",
        "preservation_summary": (
            "Packet_0063 remains prior-current-best history and a protected "
            "object/tactile reference; packet_0002 remains current best for the "
            "next loop."
        ),
        "packet_0063_remains_prior_current_best_history": True,
        "packet_0063_restored_as_current_best": False,
        "packet_0063_not_restored_as_current_best": True,
        "packet_0063_proof_and_reader_state_chain_preserved": True,
        "packet_0063_proof_and_reader_state_preserved": True,
        "packet_0063_object_tactile_gains_protected_reference": True,
        "packet_0063_object_tactile_gains_preserved_as_reference": True,
        "prior_packet_0063_preserved": True,
        "work_order_uses_packet_0002_as_current_best_for_next_loop": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "prior_current_best_packet_0063_preservation_report_v1_controller",
    }


def _build_forbidden_rival_imitation_inventory(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    source = subject.payloads["strongest_rival_blocker_carry_forward_report"]
    return {
        **_source_fields(subject),
        "strongest_rival_status": EXPECTED_STRONGEST_RIVAL_STATUS,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "forbidden_rival_inventory": list(FORBIDDEN_RIVAL_INVENTORY),
        "rival_imitation_forbidden": True,
        "forbidden_rival_objects_or_sequence": list(
            FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE
        ),
        "forbidden_rival_imitation_modes": list(FORBIDDEN_RIVAL_IMITATION_MODES),
        "forbidden_regressions": list(FORBIDDEN_REGRESSIONS),
        "selected_target_must_not_copy_rival_causal_sequence": True,
        "non_imitation_constraints_passed": True,
        "forbidden_rival_sequence": list(FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE),
        "forbidden_rival_modes": list(FORBIDDEN_RIVAL_IMITATION_MODES),
        "source_selected_target_must_not_copy": list(
            source.get("selected_target_must_not_copy")
            if isinstance(source.get("selected_target_must_not_copy"), list)
            else []
        ),
        "non_imitation_required": True,
        "strongest_rival_comparison_passed": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "forbidden_rival_imitation_inventory_v1_controller",
    }


def _build_selected_target_unit_map(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    units = [
        _target_unit(
            "static_trace_to_active_condition",
            "Convert at least one retrospective trace into an active condition that changes what later perception must pass through.",
            "Materially alter the trace's causal function, not just its wording.",
            "The trace must condition later perception before explanation stabilizes it.",
        ),
        _target_unit(
            "causal_bridge_between_object_events",
            "Build causal relation between existing object-events rather than listing them as separate evidence.",
            "Create an explicit object-event dependency across selected moments.",
            "Object-events must feel mutually conditioning, not merely adjacent.",
        ),
        _target_unit(
            "living_consequence_before_naming",
            "Let the reader feel consequence in motion before the text names the law or pressure.",
            "Move consequence into sequence before conceptual naming.",
            "The reader-state pressure should arrive before the abstract statement.",
        ),
        _target_unit(
            "preserve_earned_explanation_timing",
            "Explanation must remain delayed/earned, not abolished and not made earlier.",
            "Keep explanation present but earned by prior object-event pressure.",
            "The result must not solve by deleting or prematurely moving explanation.",
        ),
        _target_unit(
            "preserve_packet_0002_object_field",
            "Preserve packet_0002's table, ring, dust, spoon, saucer, refrigerator hum/light field unless a future command explicitly authorizes expansion.",
            "Use the existing object field as the repair substrate.",
            "The repair must not replace packet_0002's protected material field.",
        ),
        _target_unit(
            "non_imitation_and_rival_guard",
            "Preserve all non-imitation constraints and forbidden rival inventory.",
            "Avoid rival sequence, object inventory, diction, cadence, scene, and plot.",
            "No strongest-rival defeat may be claimed before later evidence.",
        ),
        _target_unit(
            "carry_forward_unselected_risks",
            "Keep explanation explicitness, chemistry register risk, and conclusion summary risk active but unselected.",
            "Do not treat unselected risks as solved by this work order.",
            "Future synthesis must still see these risks as carried forward.",
        ),
    ]
    return {
        **_source_fields(subject),
        "target_units": units,
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "selected_target_unit_map_v1_controller",
    }


def _target_unit(
    unit_id: str,
    target_requirement: str,
    material_change_required: str,
    semantic_validation_requirement: str,
) -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "target_requirement": target_requirement,
        "material_change_required": material_change_required,
        "semantic_validation_requirement": semantic_validation_requirement,
        "protected_strengths": list(PROTECTED_PACKET_0002_STRENGTHS),
        "forbidden_regressions": list(DO_NOT_SOLVE_BY),
        "evidence_basis": [
            "corrected target-selection packet_0002",
            "selected risk event_sequence_may_remain_static",
            "source reader-state evidence that some object traces remain retrospective",
        ],
    }


def _build_non_selected_risk_carry_forward_report(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    source = subject.payloads["non_selected_risk_carry_forward_report"]
    risks = source.get("non_selected_risks")
    if not isinstance(risks, list):
        risks = []
    return {
        **_source_fields(subject),
        "non_selected_risks": risks,
        "non_selected_risk_count": len(risks),
        "carried_forward_not_resolved": True,
        "selected_risk_id": SELECTED_RISK_ID,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "non_selected_risk_carry_forward_report_v1_controller",
    }


def _build_future_generation_contract(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "generation_contract_version": GENERATION_CONTRACT_VERSION,
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "schema": FUTURE_SCHEMA,
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "generation_attempt_budget": 0,
        "ready_for_generation_authorization_review": True,
        "ready_for_selected_target_generation_authorization": True,
        "generation_authorization_requires_operator_review": True,
        "generation_authorization_allowed_decisions": list(
            GENERATION_AUTHORIZATION_ALLOWED_DECISIONS
        ),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "generation_authorization_decision_required": True,
        "metadata_only": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "future_generation_contract_v1_controller",
    }


def _build_materiality_and_semantic_validation_plan(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "required_validation_checks": list(MATERIALITY_VALIDATION_REQUIREMENTS),
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_validation_requirements": list(SEMANTIC_VALIDATION_REQUIREMENTS),
        "validation_required_before_candidate_evidence": True,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "materiality_and_semantic_validation_plan_v1_controller",
    }


def _build_ablation_and_reader_eval_plan(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "strongest_rival_comparison_required": True,
        "post_generation_evidence_required": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "worker": "ablation_and_reader_eval_plan_v1_controller",
    }


def _build_gate_report(
    *,
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_target_selection_accepted", True),
        _gate_result("selected_target_exact", True),
        _gate_result("selected_risk_exact", True),
        _gate_result("current_best_for_next_loop_preserved", True),
        _gate_result("prior_current_best_preserved", True),
        _gate_result("work_order_created", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result("no_strongest_rival_defeat_claim", True),
        _gate_result(
            "generation_authorized",
            False,
            ["generation requires a separate future authorization command"],
        ),
        _gate_result(
            "candidate_generated",
            False,
            ["work-order planning does not create candidates"],
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["selected-target work order is not final evidence"],
        ),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival remains narrowed but blocking"],
        ),
    ]
    failed = [str(gate["gate_name"]) for gate in gate_results if not gate["passed"]]
    blockers = [
        "generation is not authorized",
        "candidate has not been generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "work_order_kind": NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
        "work_order_created": True,
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
        "worker": "selected_target_work_order_gate_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> dict[str, object]:
    checks = [
        _check("no_openai_calls", True),
        _check("no_text_generation", True),
        _check("work_order_created", True),
        _check("no_generation_authorization", True),
        _check("no_candidate_created", True),
        _check("no_ablation_performed", True),
        _check("no_reader_state_evaluation_performed", True),
        _check("no_synthesis_performed", True),
        _check("no_finalization", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
        _check("no_strongest_rival_defeat_claim", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "source_target_selection_accepted": True,
        "source_target_selection_current_valid": True,
        "selected_target_exact": True,
        "selected_risk_exact": True,
        "work_order_created": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_introduced": True,
        "no_finality_claim": True,
        "no_strongest_rival_defeat_claim": True,
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
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_work_order_packet",
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
            "nonlocal_law_selected_target_work_order_packet",
        ],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "target_unit_count": len(TARGET_UNIT_IDS),
        },
        "work_order_kind": NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
        "work_order_scope": WORK_ORDER_SCOPE,
        "work_order_created": True,
        "work_order_summary": payloads["selected_target_work_order_scope"][
            "work_order_summary"
        ],
        "free_rewrite_allowed": False,
        "generation_allowed": False,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "target_units": payloads["selected_target_unit_map"]["target_units"],
        "protected_packet_0002_strengths": list(PROTECTED_PACKET_0002_STRENGTHS),
        "prior_packet_0063_preserved": True,
        "repair_steps": payloads["living_event_sequence_repair_map"]["repair_steps"],
        "do_not_solve_by": payloads["living_event_sequence_repair_map"][
            "do_not_solve_by"
        ],
        "living_event_sequence_definition": payloads[
            "living_event_sequence_repair_map"
        ]["living_event_sequence_definition"],
        "forbidden_rival_sequence": payloads["forbidden_rival_imitation_inventory"][
            "forbidden_rival_sequence"
        ],
        "forbidden_rival_modes": payloads["forbidden_rival_imitation_inventory"][
            "forbidden_rival_modes"
        ],
        "rival_imitation_forbidden": True,
        "materiality_requirements": payloads[
            "materiality_and_semantic_validation_plan"
        ]["materiality_requirements"],
        "semantic_validation_requirements": payloads[
            "materiality_and_semantic_validation_plan"
        ]["semantic_validation_requirements"],
        "source_chain_coherent": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_introduced": True,
        "no_finality_claim": True,
        "ready_for_selected_target_generation_authorization": True,
        "generation_authorization_allowed_decisions": list(
            GENERATION_AUTHORIZATION_ALLOWED_DECISIONS
        ),
        "future_generation_contract": payloads["future_generation_contract"],
        "validation_plan": payloads["materiality_and_semantic_validation_plan"],
        "ablation_and_reader_eval_plan": payloads["ablation_and_reader_eval_plan"],
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["selected_target_work_order_gate_report"],
        "worker": "nonlocal_law_selected_target_work_order_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_work_order_packet"]
    return {
        **packet,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
    }


def _source_fields(subject: NonlocalLawSelectedTargetWorkOrderSubject) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_target_selection_packet_id": subject.target_selection_packet_id,
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
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
        "superseded_work_order_packet_id": subject.superseded_work_order_packet_id,
        "supersession_reason": subject.supersession_reason,
        "stale_work_order_surface_failures": list(subject.stale_surface_failures),
    }


def _packet(subject: NonlocalLawSelectedTargetWorkOrderSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_consolidated_target_selection_packet"]


def _has_newer_current_valid_target_selection(
    config: AbiConfig,
    subject: NonlocalLawSelectedTargetWorkOrderSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_consolidated_target_selection"
    if not root.exists():
        return False
    source_consolidation_id = _packet(subject).get("source_consolidation_packet_id")
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= subject.target_selection_packet_id:
            continue
        path = packet_dir / "nonlocal_law_consolidated_target_selection_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_consolidation_packet_id") == source_consolidation_id
            and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
            and payload.get("selected_risk_id") == SELECTED_RISK_ID
            and payload.get("ready_for_selected_target_work_order_planning") is True
            and payload.get("source_chain_coherent") is True
        ):
            return True
    return False


def _work_order_supersession_context(
    config: AbiConfig,
    *,
    run_id: str,
    source_target_selection_packet_id: str,
) -> WorkOrderSupersessionContext:
    root = config.run_dir(run_id) / "nonlocal_law_selected_target_work_order"
    if not root.exists():
        return WorkOrderSupersessionContext(False)
    stale_packet_id: str | None = None
    stale_failures: tuple[str, ...] = ()
    for packet_dir in sorted(root.glob("packet_*")):
        path = packet_dir / "nonlocal_law_selected_target_work_order_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_target_selection_packet_id")
            == source_target_selection_packet_id
            and payload.get("work_order_kind")
            == NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND
            and payload.get("selected_target_seed_id") == SELECTED_TARGET_SEED_ID
            and payload.get("selected_risk_id") == SELECTED_RISK_ID
            and payload.get("work_order_created") is True
            and payload.get("generation_authorized") is False
            and payload.get("candidate_generated") is False
            and int(payload.get("model_calls") or 0) == 0
        ):
            failures = _work_order_authorization_surface_failures(packet_dir, payload)
            if not failures:
                return WorkOrderSupersessionContext(
                    corrected_current_valid_work_order_exists=True
                )
            stale_packet_id = packet_dir.name
            stale_failures = tuple(failures)
    if stale_packet_id is None:
        return WorkOrderSupersessionContext(False)
    return WorkOrderSupersessionContext(
        corrected_current_valid_work_order_exists=False,
        superseded_work_order_packet_id=stale_packet_id,
        supersession_reason=SUPERSESSION_REASON_AUTHORIZATION_SURFACE_MISSING,
        stale_surface_failures=stale_failures,
    )


def _work_order_authorization_surface_failures(
    packet_dir: Path,
    packet_payload: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    _require_packet_surface(packet_payload, failures)
    _require_scope_surface(packet_dir, failures)
    _require_repair_surface(packet_dir, failures)
    _require_prior_packet_surface(packet_dir, failures)
    _require_forbidden_rival_surface(packet_dir, failures)
    _require_validation_surface(packet_dir, failures)
    _require_health_surface(packet_dir, failures)
    _require_future_contract_surface(packet_dir, failures)
    return failures


def _require_packet_surface(payload: dict[str, Any], failures: list[str]) -> None:
    _require_non_empty(payload, "work_order_summary", "packet", failures)
    _require_bool_surface(payload, "free_rewrite_allowed", False, "packet", failures)
    _require_bool_surface(payload, "generation_allowed", False, "packet", failures)
    _require_non_empty_list(payload, "repair_steps", "packet", failures)
    _require_non_empty_list(payload, "do_not_solve_by", "packet", failures)
    _require_non_empty(payload, "living_event_sequence_definition", "packet", failures)
    _require_bool_surface(payload, "prior_packet_0063_preserved", True, "packet", failures)
    _require_non_empty_list(payload, "forbidden_rival_sequence", "packet", failures)
    _require_non_empty_list(payload, "forbidden_rival_modes", "packet", failures)
    _require_bool_surface(payload, "rival_imitation_forbidden", True, "packet", failures)
    _require_non_empty_list(payload, "materiality_requirements", "packet", failures)
    _require_non_empty_list(
        payload,
        "semantic_validation_requirements",
        "packet",
        failures,
    )
    for field_name in (
        "source_chain_coherent",
        "no_generation_path_introduced",
        "no_model_call_introduced",
        "no_candidate_introduced",
        "no_finality_claim",
        "ready_for_selected_target_generation_authorization",
    ):
        _require_bool_surface(payload, field_name, True, "packet", failures)
    if payload.get("generation_authorization_allowed_decisions") != list(
        GENERATION_AUTHORIZATION_ALLOWED_DECISIONS
    ):
        failures.append("packet.generation_authorization_allowed_decisions")


def _require_scope_surface(packet_dir: Path, failures: list[str]) -> None:
    scope = _optional_payload(packet_dir / "selected_target_work_order_scope.json")
    _require_non_empty(scope, "summary", "scope", failures)
    _require_non_empty(scope, "work_order_summary", "scope", failures)
    _require_bool_surface(scope, "free_rewrite_allowed", False, "scope", failures)
    _require_bool_surface(scope, "generation_allowed", False, "scope", failures)
    _require_bool_surface(scope, "work_order_bounded", True, "scope", failures)
    _require_bool_surface(
        scope,
        "work_order_authorizes_generation",
        False,
        "scope",
        failures,
    )
    _require_bool_surface(
        scope,
        "generation_requires_separate_authorization",
        True,
        "scope",
        failures,
    )


def _require_repair_surface(packet_dir: Path, failures: list[str]) -> None:
    repair = _optional_payload(packet_dir / "living_event_sequence_repair_map.json")
    _require_non_empty(repair, "living_event_sequence_definition", "repair", failures)
    _require_non_empty_list(repair, "repair_steps", "repair", failures)
    _require_non_empty_list(repair, "do_not_solve_by", "repair", failures)
    for field_name in (
        "causal_sequence_not_object_inventory",
        "object_events_must_condition_later_perception",
        "explanation_must_remain_earned",
        "rival_imitation_forbidden",
    ):
        _require_bool_surface(repair, field_name, True, "repair", failures)


def _require_prior_packet_surface(packet_dir: Path, failures: list[str]) -> None:
    prior = _optional_payload(
        packet_dir / "prior_current_best_packet_0063_preservation_report.json"
    )
    for field_name in (
        "packet_0063_preserved_as_history",
        "packet_0063_not_restored_as_current_best",
        "packet_0063_proof_and_reader_state_preserved",
        "packet_0063_object_tactile_gains_preserved_as_reference",
        "prior_packet_0063_preserved",
    ):
        _require_bool_surface(prior, field_name, True, "prior", failures)
    _require_non_empty(prior, "preservation_summary", "prior", failures)


def _require_forbidden_rival_surface(packet_dir: Path, failures: list[str]) -> None:
    rival = _optional_payload(packet_dir / "forbidden_rival_imitation_inventory.json")
    _require_bool_surface(rival, "rival_imitation_forbidden", True, "rival", failures)
    _require_non_empty_list(
        rival,
        "forbidden_rival_objects_or_sequence",
        "rival",
        failures,
    )
    _require_non_empty_list(rival, "forbidden_rival_imitation_modes", "rival", failures)
    _require_non_empty_list(rival, "forbidden_regressions", "rival", failures)
    _require_bool_surface(
        rival,
        "selected_target_must_not_copy_rival_causal_sequence",
        True,
        "rival",
        failures,
    )
    _require_bool_surface(
        rival,
        "non_imitation_constraints_passed",
        True,
        "rival",
        failures,
    )


def _require_validation_surface(packet_dir: Path, failures: list[str]) -> None:
    validation = _optional_payload(
        packet_dir / "materiality_and_semantic_validation_plan.json"
    )
    _require_non_empty_list(
        validation,
        "materiality_requirements",
        "validation",
        failures,
    )
    _require_non_empty_list(
        validation,
        "semantic_validation_requirements",
        "validation",
        failures,
    )
    _require_bool_surface(
        validation,
        "validation_required_before_candidate_evidence",
        True,
        "validation",
        failures,
    )


def _require_health_surface(packet_dir: Path, failures: list[str]) -> None:
    health = _optional_payload(packet_dir / "project_health_scope_guard_report.json")
    for field_name in (
        "project_health_scope_guard_passed",
        "source_chain_coherent",
        "source_target_selection_accepted",
        "source_target_selection_current_valid",
        "selected_target_exact",
        "selected_risk_exact",
        "work_order_created",
        "no_generation_path_introduced",
        "no_model_call_introduced",
        "no_candidate_introduced",
        "no_finality_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    ):
        _require_bool_surface(health, field_name, True, "health", failures)


def _require_future_contract_surface(packet_dir: Path, failures: list[str]) -> None:
    contract = _optional_payload(packet_dir / "future_generation_contract.json")
    _require_bool_surface(
        contract,
        "ready_for_selected_target_generation_authorization",
        True,
        "future_generation_contract",
        failures,
    )
    _require_bool_surface(
        contract,
        "generation_authorization_requires_operator_review",
        True,
        "future_generation_contract",
        failures,
    )
    if contract.get("generation_authorization_allowed_decisions") != list(
        GENERATION_AUTHORIZATION_ALLOWED_DECISIONS
    ):
        failures.append(
            "future_generation_contract.generation_authorization_allowed_decisions"
        )
    if contract.get("selected_target_seed_id") != SELECTED_TARGET_SEED_ID:
        failures.append("future_generation_contract.selected_target_seed_id")
    if contract.get("selected_risk_id") != SELECTED_RISK_ID:
        failures.append("future_generation_contract.selected_risk_id")


def _optional_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return _read_payload(path)
    except ValueError:
        return {}


def _require_non_empty(
    payload: dict[str, Any],
    field_name: str,
    prefix: str,
    failures: list[str],
) -> None:
    if not payload.get(field_name):
        failures.append(f"{prefix}.{field_name}")


def _require_non_empty_list(
    payload: dict[str, Any],
    field_name: str,
    prefix: str,
    failures: list[str],
) -> None:
    value = payload.get(field_name)
    if not isinstance(value, list) or not value:
        failures.append(f"{prefix}.{field_name}")


def _require_bool_surface(
    payload: dict[str, Any],
    field_name: str,
    expected: bool,
    prefix: str,
    failures: list[str],
) -> None:
    if payload.get(field_name) is not expected:
        failures.append(f"{prefix}.{field_name}")


def _validate_no_forbidden_source_claims(payloads: dict[str, dict[str, Any]]) -> None:
    if _payload_has_forbidden_claim(payloads):
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; finality, "
            "phase-shift, rival-defeat, generation, candidate, or source work-order "
            "claim appears."
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


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; "
            f"{field_name} must be {expected}."
        )


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        expected_text = str(expected).lower()
        raise ValueError(
            "Nonlocal law selected-target work-order planning refused; "
            f"{field_name} must be {expected_text}."
        )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Nonlocal law selected-target work-order planning refused; {message}.")


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
    target_selection_packet: Path,
    message: str,
) -> NonlocalLawSelectedTargetWorkOrderResult:
    return NonlocalLawSelectedTargetWorkOrderResult(
        exit_code=1,
        payload={
            "accepted": False,
            "message": message,
            "target_selection_packet": str(target_selection_packet),
            "work_order_kind": NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
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
