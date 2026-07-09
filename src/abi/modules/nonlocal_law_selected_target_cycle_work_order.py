"""Work-order planning for the selected-target cycle mechanism-visibility repair."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_WORK_ORDER_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.nonlocal_law_selected_target_cycle_target_selection import (
    CORE_REPAIR_PRINCIPLE,
    NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_ARTIFACT_TYPES,
    SELECTED_RISK_CLUSTER,
    SELECTED_RISK_ID,
    SELECTED_TARGET_CLASS,
    SELECTED_TARGET_SEED_ID,
    TARGET_STATEMENT,
    WORK_ORDER_PLANNING_PRINCIPLE,
    WORK_ORDER_TARGET_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


LINEAGE_ID = "nonlocal_law_selected_target_cycle_work_order_v1"
CREATED_BY = "nonlocal_law_selected_target_cycle_work_order_v1_controller"
SOURCE_FAMILY = "nonlocal_law_selected_target_cycle_target_selection_packet"
WORK_ORDER_KIND = "selected_target_cycle_work_order"
WORK_ORDER_SCOPE = "mechanism_visibility_repair"
NEXT_RECOMMENDED_ACTION = (
    "review_selected_target_cycle_work_order_before_generation_authorization"
)
PROMPT_CONTRACT_ID = "autonomous.selected_target_cycle_mechanism_visibility_generation.v1"
MATERIALITY_POLICY_ID = "selected_target_cycle_mechanism_visibility_materiality_v1"
SEMANTIC_VALIDATOR_ID = (
    "selected_target_cycle_mechanism_visibility_semantic_validator_v1"
)
FUTURE_SCHEMA = "SelectedTargetCycleMechanismVisibilityGenerationOutput@1"

NONLOCAL_LAW_SELECTED_TARGET_CYCLE_WORK_ORDER_ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_cycle_work_order_packet",
    "source_cycle_target_selection_intake_summary",
    "selected_mechanism_visibility_work_order_scope",
    "mechanism_naming_reduction_repair_map",
    "preserved_living_event_sequence_gain_report",
    "explicit_mechanism_phrase_inventory",
    "allowed_transformation_map",
    "forbidden_overcorrection_report",
    "non_selected_risk_constraint_report",
    "selected_target_cycle_unit_map",
    "future_generation_contract",
    "materiality_and_semantic_validation_plan",
    "ablation_and_reader_eval_plan",
    "selected_target_cycle_work_order_gate_report",
    "project_health_scope_guard_report",
)

RANKED_TARGET_IDS = (
    "reduce_causal_mechanism_naming",
    "enact_return_instead_of_summarizing_law",
    "protect_object_field_delicacy",
    "integrate_or_remove_chemistry_register",
)
NON_SELECTED_RISK_CONSTRAINTS = (
    {
        "risk_id": "conclusion_summarizes_instead_of_enacts_return",
        "role": (
            "avoid making ending more summarizing while reducing mechanism naming"
        ),
    },
    {
        "risk_id": "chemistry_register_unresolved",
        "role": "do not introduce new register intrusions",
    },
    {
        "risk_id": "object_field_delicacy_overloaded_by_causal_explanation",
        "role": "guard constraint; repair must preserve object delicacy",
    },
    {
        "risk_id": "strongest_rival_remains_blocking",
        "role": "no rival defeat claim; no imitation",
    },
    {
        "risk_id": "finalization_not_allowed",
        "role": "finalization remains locked",
    },
)
BAD_REPAIR_MODES = (
    "delete explanation",
    "make prose vague",
    "reduce object activity",
    "remove causal bridges",
    "flatten logic",
    "make the passage merely atmospheric",
    "solve by cutting all explicit claims",
    "solve by adding new incidents or objects",
)
CORRECT_REPAIR_MODES = (
    "preserve object-event causality",
    "reduce direct mechanism naming after the reader has already felt the object relation",
    "transfer causal meaning into object relation",
    "transfer causal meaning into syntax",
    "transfer causal meaning into timing",
    "transfer causal meaning into perceptual sequence",
    "leave explanation earned rather than abolished",
    "preserve packet_0001's living-event sequence gain",
)
REPAIR_STEPS = (
    "identify explicit causal-mechanism language that names what the object sequence should already make felt",
    "preserve the object relation or event that carries the causal force",
    "replace explicit mechanism naming with object relation, syntax, timing, or perceptual sequencing where possible",
    "keep explanation only where it remains earned after object pressure",
    "preserve the living-event sequence, non-imitation constraints, no-answer pressure, and strongest-rival blocker",
)
DO_NOT_SOLVE_BY = (
    "deleting explanation wholesale",
    "reducing object activity",
    "making prose vague",
    "adding new object inventory",
    "adding grimness or generic vividness",
    "solving return/chemistry/register as the primary target",
    "claiming packet_0001 is final",
    "claiming strongest rival defeated",
)
GAINS_TO_PRESERVE = (
    "ring/grain relation changes later seeing",
    "dust/bare strip relation changes eye path",
    "spoon tick makes saucer fracture newly present",
    "refrigerator hum changes order of seeing",
    "consequence arrives before naming",
    "object traces become active conditions rather than static evidence",
)
PRESERVATION_FAILURE_MODES = (
    "reverting to packet_0002 static traces",
    "deleting causal bridges",
    "making object field atmospheric rather than active",
    "making explanation too thin or unearned",
)
PHRASE_INVENTORY = (
    {
        "phrase": "changes the next glance",
        "phrase_class": "declared perception change",
        "risk": "names the perceptual effect before object pressure earns it",
        "possible_repair_mode": "convert to changed perceptual order",
    },
    {
        "phrase": "changes the order of seeing",
        "phrase_class": "direct causal statement",
        "risk": "states mechanism instead of letting sequence force it",
        "possible_repair_mode": "convert to syntactic dependency or timing",
    },
    {
        "phrase": "where later seeing must be changed by that receiving",
        "phrase_class": "explicit law naming",
        "risk": "turns reader effect into explanatory thesis",
        "possible_repair_mode": "enact through object relation",
    },
    {
        "phrase": "condition through which the next perception has to pass",
        "phrase_class": "mechanism word",
        "risk": "abstracts the causal bridge into terminology",
        "possible_repair_mode": "materialize as object relation",
    },
    {
        "phrase": "Only after this does the room begin to instruct",
        "phrase_class": "explanatory transition",
        "risk": "makes the room's instruction too declarative",
        "possible_repair_mode": "make transition earned by pressure",
    },
    {
        "phrase": "The room teaches slowly",
        "phrase_class": "declared instruction",
        "risk": "names interpretive function directly",
        "possible_repair_mode": "replace with object-event pressure",
    },
    {
        "phrase": "one condition to the next",
        "phrase_class": "repeated condition phrasing",
        "risk": "repeats mechanism vocabulary",
        "possible_repair_mode": "convert to sequence or timing",
    },
    {
        "phrase": "later seeing",
        "phrase_class": "repeated perception phrasing",
        "risk": "over-names the reader-state operation",
        "possible_repair_mode": "convert to changed order of notice",
    },
    {
        "phrase": "perception has to pass",
        "phrase_class": "explicit mechanism phrasing",
        "risk": "turns pressure into abstract law",
        "possible_repair_mode": "materialize as object threshold",
    },
)
ALLOWED_TRANSFORMATIONS = (
    {
        "from": "explicit law naming",
        "to": "enacted object relation",
    },
    {
        "from": "direct causal statement",
        "to": "syntactic dependency",
    },
    {
        "from": "declared perception change",
        "to": "changed perceptual order",
    },
    {
        "from": "explanatory transition",
        "to": "earned pressure transition",
    },
    {
        "from": "mechanism word",
        "to": "material relation",
    },
    {
        "from": "repeated condition/perception phrasing",
        "to": "object sequence or timing",
    },
)
FORBIDDEN_TRANSFORMATIONS = (
    "explanation deletion",
    "causal weakening",
    "object deletion",
    "new object inventory",
    "generic lyricism",
    "vague atmosphere",
    "rival imitation",
    "finality or rival-defeat claim",
)
TARGET_UNITS = (
    {
        "unit_id": "preserve_living_event_sequence_gain",
        "material_change_required": False,
        "preservation_unit": True,
    },
    {
        "unit_id": "reduce_direct_mechanism_naming",
        "material_change_required": True,
        "selected_target_unit": True,
    },
    {
        "unit_id": "convert_declarative_instruction_to_object_pressure",
        "material_change_required": True,
        "selected_target_unit": True,
    },
    {
        "unit_id": "convert_law_naming_to_perceptual_sequence",
        "material_change_required": True,
        "selected_target_unit": True,
    },
    {
        "unit_id": "preserve_earned_explanation_not_abolished",
        "material_change_required": False,
        "preservation_or_guard_unit": True,
    },
    {
        "unit_id": "protect_object_activity_and_delicacy",
        "material_change_required": False,
        "preservation_or_guard_unit": True,
    },
    {
        "unit_id": "preserve_non_selected_risks_as_constraints",
        "material_change_required": False,
        "preservation_or_guard_unit": True,
    },
    {
        "unit_id": "preserve_strongest_rival_blocker_and_non_imitation",
        "material_change_required": False,
        "preservation_or_guard_unit": True,
    },
)
TARGET_UNIT_IDS = tuple(str(unit["unit_id"]) for unit in TARGET_UNITS)
MATERIALITY_REQUIREMENTS = (
    "explicit mechanism naming reduced materially",
    "living-event sequence preserved",
    "object activity preserved",
    "explanation not abolished",
    "no new object inventory",
    "no vague generic smoothing",
)
SEMANTIC_REQUIREMENTS = (
    "mechanism naming reduction present",
    "causality still felt through object field",
    "explanation earned not deleted",
    "packet_0001 gains preserved",
    "non-selected risks not worsened",
    "rival imitation absent",
    "strongest rival not claimed defeated",
    "no finality or phase-shift claim",
)
ABLATION_CONTROLS = (
    "full_mechanism_visibility_repair",
    "revert_to_packet_0001",
    "remove_mechanism_naming_reduction",
    "delete_explanation_control",
    "vague_atmosphere_control",
    "object_activity_reduction_control",
    "strongest_rival_comparison",
)
READER_STATE_FOCUS = (
    "does causality remain felt after mechanism language is reduced?",
    "does object relation carry perceptual change?",
    "does the passage become vague or less active?",
    "is explanation still earned?",
    "are packet_0001 living-event gains preserved?",
    "does object-field delicacy improve?",
    "does return-summary risk remain carried forward?",
    "does strongest-rival pressure remain active?",
)


@dataclass(frozen=True)
class SelectedTargetCycleWorkOrderResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SelectedTargetCycleWorkOrderSubject:
    run_id: str
    target_selection_packet_dir: Path
    target_selection_packet_id: str
    target_selection_packet_artifact_id: str | None
    target_selection_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]


def run_selected_target_cycle_work_order_planning(
    config: AbiConfig,
    *,
    target_selection_packet: Path | str,
    operator_reviewed: bool,
) -> SelectedTargetCycleWorkOrderResult:
    initialize_database(config)
    packet_dir = _resolve_path(config, target_selection_packet)
    if not operator_reviewed:
        return _refusal(
            target_selection_packet=packet_dir,
            message=(
                "Nonlocal law selected-target cycle work-order planning refused; "
                "--operator-reviewed is required."
            ),
        )
    if not packet_dir.exists() or not packet_dir.is_dir():
        return _refusal(
            target_selection_packet=packet_dir,
            message=(
                "Nonlocal law selected-target cycle work-order planning refused; "
                f"target-selection packet directory not found: {packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, packet_dir)
        _validate_subject(config, subject)
    except ValueError as error:
        return _refusal(target_selection_packet=packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                target_selection_packet=packet_dir,
                message=(
                    "Nonlocal law selected-target cycle work-order planning refused; "
                    f"run is not registered: {subject.run_id}"
                ),
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CYCLE_WORK_ORDER_ACTIVE_PHASE,
        )
        output_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_work_order"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=LINEAGE_ID,
            created_by=CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads, artifacts = _write_artifacts(
            writer=writer,
            subject=subject,
            packet_dir=output_dir,
        )
        gate_report = payloads["selected_target_cycle_work_order_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_selected_target_cycle_work_order_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=LINEAGE_ID,
        )

    return SelectedTargetCycleWorkOrderResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=output_dir,
            payloads=payloads,
            artifacts=artifacts,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    packet_dir: Path,
) -> SelectedTargetCycleWorkOrderSubject:
    payloads = _load_required_payloads(packet_dir)
    packet = payloads["nonlocal_law_selected_target_cycle_target_selection_packet"]
    run_id = _required_string(packet.get("run_id"), "target-selection packet missing run_id")
    packet_id = str(packet.get("packet_id") or packet_dir.name)
    packet_path = packet_dir / "nonlocal_law_selected_target_cycle_target_selection_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    artifact_ids = _string_dict(packet.get("artifact_ids"))
    source_parent_ids = _unique(
        [packet_artifact.id if packet_artifact else None, *artifact_ids.values()]
    )
    return SelectedTargetCycleWorkOrderSubject(
        run_id=run_id,
        target_selection_packet_dir=packet_dir,
        target_selection_packet_id=packet_id,
        target_selection_packet_artifact_id=(
            packet_artifact.id if packet_artifact else None
        ),
        target_selection_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in NONLOCAL_LAW_SELECTED_TARGET_CYCLE_TARGET_SELECTION_ARTIFACT_TYPES:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Nonlocal law selected-target cycle work-order planning refused; "
                f"target-selection packet missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("payload"), dict
        ):
            raise ValueError(
                "Nonlocal law selected-target cycle work-order planning refused; "
                f"malformed target-selection artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_subject(
    config: AbiConfig,
    subject: SelectedTargetCycleWorkOrderSubject,
) -> None:
    packet = _packet(subject)
    _validate_no_forbidden_source_claims(subject.payloads)
    if packet.get("accepted") is not True:
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "target-selection packet is not accepted."
        )
    if _has_newer_current_valid_target_selection(config, subject):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "target-selection packet is stale or superseded."
        )
    if _current_valid_work_order_exists(config, subject):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "current-valid selected-target cycle work order already exists for "
            "this target-selection packet."
        )
    _require_bool(packet, "target_selection_executed", True)
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(packet, "selected_target_class", SELECTED_TARGET_CLASS)
    if packet.get("target_scope") not in {None, WORK_ORDER_TARGET_SCOPE}:
        _require_equal(packet, "target_scope", WORK_ORDER_TARGET_SCOPE)
    _require_equal(packet, "current_best_for_next_loop_packet_id", "packet_0001")
    _require_equal(packet, "prior_working_current_best_candidate_packet_id", "packet_0002")
    _require_equal(packet, "prior_historical_current_best_candidate_packet_id", "packet_0063")
    _require_bool(packet, "ready_for_work_order_planning", True)
    _require_bool(packet, "ready_for_selected_target_work_order_planning", True)
    _require_bool(packet, "work_order_authorized", False)
    _require_bool(packet, "work_order_requires_separate_command", True)
    _require_bool(packet, "work_order_planning_requires_operator_review", True)
    _require_bool(packet, "generation_authorized", False)
    _require_bool(packet, "candidate_generated", False)
    _require_bool(packet, "target_selected", True)
    _require_bool(packet, "selected_target_allowed", True)
    _require_bool(packet, "selected_target_ranked_first", True)
    if int(packet.get("model_calls") or 0) != 0:
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "source target-selection packet must have zero model calls."
        )
    if packet.get("ranked_target_ids") != list(RANKED_TARGET_IDS):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "ranked targets are incomplete."
        )
    if packet.get("ranked_target_count") != len(RANKED_TARGET_IDS):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "ranked_target_count must be 4."
        )

    decision = subject.payloads["selected_target_decision"]
    _require_equal(decision, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(decision, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(decision, "selected_target_class", SELECTED_TARGET_CLASS)
    _require_equal(decision, "target_scope", WORK_ORDER_TARGET_SCOPE)
    if not decision.get("work_order_planning_principle"):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "work_order_planning_principle missing."
        )
    if decision.get("selected_risk_cluster") != list(SELECTED_RISK_CLUSTER):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "selected risk cluster is incomplete."
        )

    guard = subject.payloads["non_universalization_guard_carry_forward_report"]
    for field_name in (
        "selected_target_does_not_mean_always_reduce_explanation",
        "selected_target_does_not_mean_delete_causality",
        "selected_target_does_not_mean_make_objects_less_active",
        "selected_target_does_not_mean_prior_candidate_failed",
    ):
        _require_bool(guard, field_name, True)

    carry = subject.payloads["non_selected_risk_carry_forward_report"]
    carried = carry.get("non_selected_risks")
    if not isinstance(carried, list) or len(carried) != len(NON_SELECTED_RISK_CONSTRAINTS):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "non-selected risk constraints are incomplete."
        )
    for expected in NON_SELECTED_RISK_CONSTRAINTS:
        matching = [
            risk
            for risk in carried
            if isinstance(risk, dict) and risk.get("risk_id") == expected["risk_id"]
        ]
        if not matching:
            raise ValueError(
                "Nonlocal law selected-target cycle work-order planning refused; "
                f"non-selected risk missing: {expected['risk_id']}."
            )
        if not matching[0].get("recommended_next_handling"):
            raise ValueError(
                "Nonlocal law selected-target cycle work-order planning refused; "
                f"non-selected risk handling missing: {expected['risk_id']}."
            )
        if not matching[0].get("work_order_constraint_role"):
            raise ValueError(
                "Nonlocal law selected-target cycle work-order planning refused; "
                f"non-selected risk constraint role missing: {expected['risk_id']}."
            )

    rival = subject.payloads["strongest_rival_blocker_carry_forward_report"]
    _require_bool(rival, "strongest_rival_remains_blocking", True)
    _require_bool(rival, "strongest_rival_defeated_claimed", False)
    gate = subject.payloads["selected_target_cycle_target_selection_gate_report"]
    _require_bool(gate, "strongest_rival_resolved", False)


def _write_artifacts(
    *,
    writer: PacketWriter,
    subject: SelectedTargetCycleWorkOrderSubject,
    packet_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    def write(
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

    write(
        "source_cycle_target_selection_intake_summary",
        _build_source_intake(subject, packet_dir),
        list(subject.source_parent_ids),
    )
    write(
        "selected_mechanism_visibility_work_order_scope",
        _build_scope(subject),
        [artifacts["source_cycle_target_selection_intake_summary"].id],
    )
    write(
        "mechanism_naming_reduction_repair_map",
        _build_repair_map(subject),
        [artifacts["selected_mechanism_visibility_work_order_scope"].id],
    )
    write(
        "preserved_living_event_sequence_gain_report",
        _build_preservation_report(subject),
        [artifacts["mechanism_naming_reduction_repair_map"].id],
    )
    write(
        "explicit_mechanism_phrase_inventory",
        _build_phrase_inventory(subject),
        [artifacts["mechanism_naming_reduction_repair_map"].id],
    )
    write(
        "allowed_transformation_map",
        _build_allowed_transformation_map(subject),
        [artifacts["explicit_mechanism_phrase_inventory"].id],
    )
    write(
        "forbidden_overcorrection_report",
        _build_forbidden_overcorrection_report(subject),
        [artifacts["allowed_transformation_map"].id],
    )
    write(
        "non_selected_risk_constraint_report",
        _build_non_selected_risk_constraint_report(subject),
        [
            artifacts["forbidden_overcorrection_report"].id,
            artifacts["source_cycle_target_selection_intake_summary"].id,
        ],
    )
    write(
        "selected_target_cycle_unit_map",
        _build_unit_map(subject),
        [
            artifacts["mechanism_naming_reduction_repair_map"].id,
            artifacts["non_selected_risk_constraint_report"].id,
        ],
    )
    write(
        "future_generation_contract",
        _build_future_generation_contract(subject),
        [artifacts["selected_target_cycle_unit_map"].id],
    )
    write(
        "materiality_and_semantic_validation_plan",
        _build_validation_plan(subject),
        [
            artifacts["future_generation_contract"].id,
            artifacts["selected_target_cycle_unit_map"].id,
        ],
    )
    write(
        "ablation_and_reader_eval_plan",
        _build_ablation_and_reader_eval_plan(subject),
        [artifacts["materiality_and_semantic_validation_plan"].id],
    )
    write(
        "selected_target_cycle_work_order_gate_report",
        _build_gate_report(subject),
        [
            artifacts["future_generation_contract"].id,
            artifacts["ablation_and_reader_eval_plan"].id,
        ],
    )
    write(
        "project_health_scope_guard_report",
        _build_health_report(subject),
        [artifacts["selected_target_cycle_work_order_gate_report"].id],
    )
    packet_payload = _build_packet_summary(
        subject=subject,
        packet_dir=packet_dir,
        payloads=payloads,
        artifacts=artifacts,
    )
    write(
        "nonlocal_law_selected_target_cycle_work_order_packet",
        packet_payload,
        [
            artifact.id
            for artifact_type, artifact in artifacts.items()
            if artifact_type != "nonlocal_law_selected_target_cycle_work_order_packet"
        ],
    )
    return payloads, artifacts


def _build_source_intake(
    subject: SelectedTargetCycleWorkOrderSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = _packet(subject)
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
        "source_family": SOURCE_FAMILY,
        "accepted_target_selection": True,
        "target_selection_current_valid": True,
        "superseded_target_selection_packet_id": (
            packet.get("superseded_target_selection_packet_id")
        ),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "target_scope": WORK_ORDER_SCOPE,
        "ranked_target_count": packet.get("ranked_target_count"),
        "selected_target_rank": packet.get("selected_target_rank"),
        "work_order_planning_principle_consumed": True,
        "non_universalization_guard_consumed": True,
        "non_selected_risk_constraints_consumed": True,
        "source_chain_coherent": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "source_cycle_target_selection_intake_summary_v1_controller",
    }


def _build_scope(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "work_order_kind": WORK_ORDER_KIND,
        "work_order_scope": WORK_ORDER_SCOPE,
        "target_statement": TARGET_STATEMENT,
        "core_repair_principle": CORE_REPAIR_PRINCIPLE,
        "work_order_planning_principle": WORK_ORDER_PLANNING_PRINCIPLE,
        "free_rewrite_allowed": False,
        "generation_allowed": False,
        "work_order_bounded": True,
        "work_order_authorizes_generation": False,
        "target_family_is_new_cycle_target": True,
        "prior_living_event_sequence_repair_must_be_preserved": True,
        "old_living_event_sequence_repair_path_forbidden": True,
        "not_a_static_trace_repair_work_order": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "selected_mechanism_visibility_work_order_scope_v1_controller",
    }


def _build_repair_map(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "repair_principle": CORE_REPAIR_PRINCIPLE,
        "mechanism_visibility_problem": (
            "The current best has learned a living-event sequence, but some "
            "passages still name the mechanism of changed perception too directly."
        ),
        "transformation_principle": WORK_ORDER_PLANNING_PRINCIPLE,
        "bad_repair": list(BAD_REPAIR_MODES),
        "correct_repair": list(CORRECT_REPAIR_MODES),
        "preserve_living_event_sequence_gain": True,
        "explanation_abolition_forbidden": True,
        "object_activity_reduction_forbidden": True,
        "vagueness_as_solution_forbidden": True,
        "generic_smoothing_forbidden": True,
        "repair_steps": list(REPAIR_STEPS),
        "do_not_solve_by": list(DO_NOT_SOLVE_BY),
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "mechanism_naming_reduction_repair_map_v1_controller",
    }


def _build_preservation_report(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_0001_living_event_sequence_gain_preserved_as_requirement": True,
        "packet_0001_current_best_for_next_loop": True,
        "packet_0002_preserved_as_prior_reference": True,
        "packet_0063_preserved_as_historical_reference": True,
        "gains_to_preserve": list(GAINS_TO_PRESERVE),
        "preservation_failure_modes": list(PRESERVATION_FAILURE_MODES),
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "preserved_living_event_sequence_gain_report_v1_controller",
    }


def _build_phrase_inventory(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "phrase_inventory": [dict(item) for item in PHRASE_INVENTORY],
        "phrase_classes": sorted({str(item["phrase_class"]) for item in PHRASE_INVENTORY}),
        "deletion_required": False,
        "transformation_or_earned_retention_required": True,
        "automatic_deletion_targets": False,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "explicit_mechanism_phrase_inventory_v1_controller",
    }


def _build_allowed_transformation_map(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "allowed_transformations": [dict(item) for item in ALLOWED_TRANSFORMATIONS],
        "forbidden_transformations": list(FORBIDDEN_TRANSFORMATIONS),
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "allowed_transformation_map_v1_controller",
    }


def _build_forbidden_overcorrection_report(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "delete_explanation_forbidden": True,
        "weaken_causality_forbidden": True,
        "reduce_object_activity_forbidden": True,
        "make_text_vague_forbidden": True,
        "generic_smoothing_forbidden": True,
        "new_object_inventory_forbidden": True,
        "return_target_expansion_forbidden": True,
        "chemistry_register_target_expansion_forbidden": True,
        "strongest_rival_defeat_claim_forbidden": True,
        "finality_claim_forbidden": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "forbidden_overcorrection_report_v1_controller",
    }


def _build_non_selected_risk_constraint_report(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "non_selected_risk_constraints": [
            dict(item) for item in NON_SELECTED_RISK_CONSTRAINTS
        ],
        "non_selected_risks_remain_unresolved": True,
        "strongest_rival_remains_blocking": True,
        "finalization_remains_locked": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "non_selected_risk_constraint_report_v1_controller",
    }


def _build_unit_map(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, object]:
    units = []
    for unit in TARGET_UNITS:
        row = {
            "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
            "selected_risk_id": SELECTED_RISK_ID,
            "work_order_scope": WORK_ORDER_SCOPE,
            "semantic_validation_required": True,
            **unit,
        }
        row.setdefault("selected_target_unit", False)
        row.setdefault("preservation_unit", False)
        row.setdefault("preservation_or_guard_unit", False)
        units.append(row)
    return {
        **_source_fields(subject),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "target_units": units,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "selected_target_cycle_unit_map_v1_controller",
    }


def _build_future_generation_contract(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "generation_contract_version": 1,
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "schema": FUTURE_SCHEMA,
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "generation_attempt_budget": 0,
        "ready_for_generation_authorization_review": True,
        "generation_authorization_requires_operator_review": True,
        "allowed_authorization_decisions": [
            "authorize_one_bounded_selected_target_cycle_generation",
            "refuse_generation",
        ],
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "future_generation_contract_v1_controller",
    }


def _build_validation_plan(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_requirements": list(SEMANTIC_REQUIREMENTS),
        "semantic_validation_requirements": list(SEMANTIC_REQUIREMENTS),
        "validation_required_before_candidate_evidence": True,
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "materiality_and_semantic_validation_plan_v1_controller",
    }


def _build_ablation_and_reader_eval_plan(
    subject: SelectedTargetCycleWorkOrderSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "work_order_created": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "worker": "ablation_and_reader_eval_plan_v1_controller",
    }


def _build_gate_report(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, object]:
    pass_gates = (
        "source_target_selection_accepted",
        "source_target_selection_current_valid",
        "selected_target_reduce_causal_mechanism_naming",
        "target_scope_mechanism_visibility_repair",
        "work_order_created",
        "old_living_event_sequence_repair_path_not_used",
        "packet_0001_working_current_best_preserved",
        "packet_0002_preserved_as_prior_reference",
        "packet_0063_preserved_as_historical_reference",
        "non_universalization_guard_preserved",
        "strongest_rival_remains_blocking",
        "no_generation_authorized",
        "no_candidate_generated",
        "no_model_calls",
        "no_final_claim",
        "no_phase_shift_claim",
        "no_strongest_rival_defeat_claim",
    )
    block_gates = (
        "generation_authorized",
        "candidate_generated",
        "finalization_eligible",
        "strongest_rival_resolved",
    )
    blockers = [
        "generation requires separate future authorization",
        "candidate is not generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "work_order_created": True,
        "old_living_event_sequence_repair_path_not_used": True,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "strongest_rival_remains_blocking": True,
        "strongest_rival_resolved": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "passed_gates": list(pass_gates),
        "failed_gates": list(block_gates),
        "gate_results": [
            *[_gate_result(name, True) for name in pass_gates],
            *[
                _gate_result(name, False, [f"{name} remains blocked"])
                for name in block_gates
            ],
        ],
        "unresolved_blockers": blockers,
        "worker": "selected_target_cycle_work_order_gate_report_v1_controller",
    }


def _build_health_report(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        "source_target_selection_accepted": True,
        "source_target_selection_current_valid": True,
        "selected_target_exact": True,
        "selected_risk_exact": True,
        "work_order_created": True,
        "old_living_event_sequence_repair_path_not_used": True,
        "no_generation_path_introduced": True,
        "no_model_call_introduced": True,
        "no_candidate_introduced": True,
        "no_finality_claim": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "no_strongest_rival_defeat_claim": True,
        "strongest_rival_defeated_claimed": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: SelectedTargetCycleWorkOrderSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_CYCLE_WORK_ORDER_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_cycle_work_order_packet",
    )
    contract = payloads["future_generation_contract"]
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
            "nonlocal_law_selected_target_cycle_work_order_packet",
        ],
        "counts": {**counts, "model_calls": 0, "candidate_artifacts_created": 0},
        "source_family": SOURCE_FAMILY,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "work_order_kind": WORK_ORDER_KIND,
        "work_order_scope": WORK_ORDER_SCOPE,
        "work_order_created": True,
        "old_living_event_sequence_repair_path_not_used": True,
        "future_generation_authorized": False,
        "future_generation_requires_separate_authorization": True,
        "generation_attempt_budget": contract["generation_attempt_budget"],
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_finality_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "no_strongest_rival_defeat_claim": True,
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "explicit_mechanism_phrase_count": len(PHRASE_INVENTORY),
        "forbidden_overcorrections": list(FORBIDDEN_TRANSFORMATIONS),
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["selected_target_cycle_work_order_gate_report"],
        "worker": "nonlocal_law_selected_target_cycle_work_order_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_cycle_work_order_packet"]
    return {
        **packet,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
    }


def _source_fields(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, object]:
    packet = _packet(subject)
    return {
        "source_target_selection_packet_id": subject.target_selection_packet_id,
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "prior_working_current_best_candidate_packet_id": packet.get(
            "prior_working_current_best_candidate_packet_id"
        ),
        "current_best_for_next_loop_packet_id": packet.get(
            "current_best_for_next_loop_packet_id"
        ),
        "prior_historical_current_best_candidate_packet_id": packet.get(
            "prior_historical_current_best_candidate_packet_id"
        ),
        "learned_cycle_lesson_id": packet.get("learned_cycle_lesson_id"),
        "lesson_scope": packet.get("lesson_scope"),
    }


def _packet(subject: SelectedTargetCycleWorkOrderSubject) -> dict[str, Any]:
    return subject.payloads["nonlocal_law_selected_target_cycle_target_selection_packet"]


def _has_newer_current_valid_target_selection(
    config: AbiConfig,
    subject: SelectedTargetCycleWorkOrderSubject,
) -> bool:
    root = (
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_cycle_target_selection"
    )
    if not root.exists():
        return False
    source_consolidation_id = _packet(subject).get("source_consolidation_packet_id")
    for packet_dir in sorted(root.glob("packet_*")):
        if packet_dir.name <= subject.target_selection_packet_id:
            continue
        path = packet_dir / "nonlocal_law_selected_target_cycle_target_selection_packet.json"
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
            and payload.get("target_scope") == WORK_ORDER_SCOPE
        ):
            return True
    return False


def _current_valid_work_order_exists(
    config: AbiConfig,
    subject: SelectedTargetCycleWorkOrderSubject,
) -> bool:
    root = config.run_dir(subject.run_id) / "nonlocal_law_selected_target_cycle_work_order"
    if not root.exists():
        return False
    for packet_dir in sorted(root.glob("packet_*")):
        path = packet_dir / "nonlocal_law_selected_target_cycle_work_order_packet.json"
        if not path.exists():
            continue
        try:
            payload = _read_payload(path)
        except ValueError:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_target_selection_packet_id")
            == subject.target_selection_packet_id
            and payload.get("work_order_scope") == WORK_ORDER_SCOPE
            and payload.get("work_order_kind") == WORK_ORDER_KIND
            and payload.get("work_order_created") is True
            and payload.get("generation_authorized") is False
            and payload.get("candidate_generated") is False
            and int(payload.get("model_calls") or 0) == 0
            and payload.get("finalization_eligible") is False
        ):
            return True
    return False


def _validate_no_forbidden_source_claims(payloads: dict[str, dict[str, Any]]) -> None:
    if _payload_has_forbidden_claim(payloads):
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            "finality, phase-shift, rival-defeat, generation, candidate, model-call, "
            "or source work-order claim appears."
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
                "work_order_authorized",
            } and item is True:
                return True
            if key == "model_calls" and isinstance(item, int) and item != 0:
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


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            f"{field_name} must be {expected}."
        )


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(
            "Nonlocal law selected-target cycle work-order planning refused; "
            f"{field_name} must be {str(expected).lower()}."
        )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(
        f"Nonlocal law selected-target cycle work-order planning refused; {message}."
    )


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
    result: list[str] = []
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config.root / candidate


def _refusal(
    *,
    target_selection_packet: Path,
    message: str,
) -> SelectedTargetCycleWorkOrderResult:
    return SelectedTargetCycleWorkOrderResult(
        exit_code=1,
        payload={
            "accepted": False,
            "message": message,
            "target_selection_packet": str(target_selection_packet),
            "work_order_kind": WORK_ORDER_KIND,
            "work_order_scope": WORK_ORDER_SCOPE,
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
