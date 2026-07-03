"""Controller-owned nonlocal law-guided work-order planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_GUIDED_WORK_ORDER_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_guided_strategy import (
    NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
    SELECTED_NONLOCAL_STRATEGY_CLASS,
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


NONLOCAL_LAW_GUIDED_WORK_ORDER_LINEAGE_ID = "nonlocal_law_guided_work_order_v1"
NONLOCAL_LAW_GUIDED_WORK_ORDER_CREATED_BY = (
    "nonlocal_law_guided_work_order_v1_controller"
)
NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND = "nonlocal_law_guided_work_order"
NONLOCAL_LAW_TARGET_SCOPE = "nonlocal_artifact_pressure_distribution"
NEXT_RECOMMENDED_ACTION = (
    "review_nonlocal_law_work_order_before_generation_authorization"
)
GENERATION_CONTRACT_VERSION = "1"
PROMPT_CONTRACT_ID = "autonomous.nonlocal_law_guided_generation.v1"
MATERIALITY_POLICY_ID = "nonlocal_law_guided_generation_materiality_v1"
SEMANTIC_VALIDATOR_ID = "nonlocal_law_guided_semantic_validator_v1"
FUTURE_SCHEMA_NAME = "NonlocalLawGuidedGenerationOutput@1"
SUPERSESSION_REASON_GENERATION_READINESS_METADATA_MISSING = (
    "nonlocal_law_work_order_generation_readiness_metadata_missing"
)
RECOMPOSITION_PRINCIPLE = (
    "Object-event consequence must accumulate before explicit explanation, thesis, "
    "crisis, law, or named pressure."
)
EXPLANATION_POLICY = (
    "Explanation is allowed, but only after object pressure has been earned or "
    "embedded in consequence."
)

NONLOCAL_TARGET_UNIT_IDS = (
    "object_event_consequence_before_explanation",
    "delay_or_embed_explanatory_naming",
    "packet_0063_objects_undergo_consequence",
    "middle_sequence_pressure_accumulation",
    "reread_return_prepared_by_first_read_pressure",
    "non_imitation_constraint_preservation",
)
NONLOCAL_SCOPE_REGIONS = (
    "opening pressure distribution",
    "early explanation timing",
    "middle object-event sequencing",
    "return/reread preparation",
    "proof/no-answer carry as protected pressure only",
)
CANONICAL_AFFECTED_REGIONS = (
    "opening_pressure_distribution",
    "early_explanation_timing",
    "middle_object_event_sequence",
    "return_reread_preparation",
)
CANONICAL_PROTECTED_REGIONS = (
    "proof_no_answer_carry_as_protected_pressure",
    "packet_0063_object_tactile_strengths",
    "non_imitation_constraints",
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
FORBIDDEN_NONLOCAL_REGRESSIONS = (
    "generic domestic grime as replacement for law",
    "copying ordinary consequence as phrase or thesis",
    "local patching instead of nonlocal pressure redistribution",
    "deleting explanation rather than earning it",
    "weakening packet_0063 object/tactile gains",
    "claiming strongest-rival defeat without ablation/reader-state/synthesis",
)
FORBIDDEN_RIVAL_MATERIAL = (
    *FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE,
    *FORBIDDEN_RIVAL_IMITATION_MODES,
    *FORBIDDEN_NONLOCAL_REGRESSIONS,
    'copying "ordinary consequence" as a phrase or thesis',
)
MATERIALITY_REQUIREMENTS = (
    "materially re-stage object-event consequence before explanation",
    "materially delay or embed explanatory naming",
    "materially make packet_0063's own objects undergo consequence",
    "materially accumulate middle-sequence pressure through object-events",
    "materially prepare reread return through first-read pressure",
    "preserve non-imitation constraints",
)
SEMANTIC_VALIDATION_REQUIREMENTS = (
    "consequence_before_explanation_passed",
    "explanation_earned_not_abolished",
    "packet_0063_object_field_preserved",
    "rival_imitation_absent",
    "nonlocal_pressure_redistribution_present",
    "generic_vividness_absent",
    "strongest_rival_not_claimed_defeated",
    "no_finality_or_phase_shift_claim",
)
GENERATION_AUTHORIZATION_ALLOWED_DECISIONS = (
    "authorize_one_bounded_nonlocal_law_guided_generation",
    "require_work_order_revision",
    "pause_generation",
)
ABLATION_CONTROLS = (
    "full_nonlocal_law_guided_intervention",
    "revert_to_packet_0063",
    "remove_consequence_first_sequence",
    "restore_early_explanation_timing",
    "rival_imitation_control",
    "generic_vividness_control",
    "strongest_rival_comparison",
)
READER_STATE_FOCUS = (
    "first-read pressure before explanation",
    "object-event consequence felt before naming",
    "explanation earned, not abolished",
    "reread return preparation",
    "no rival imitation detected",
    "strongest-rival pressure remains active until synthesis",
)
OPTIONAL_ALIAS_FIELDS = (
    ("law_transfer_summary", "summary"),
    ("packet_0063_nonlocal_gap_map", "summary"),
    ("packet_0063_nonlocal_gap_map", "nonlocal_gap_summary"),
    ("selected_nonlocal_strategy_contract", "strategy_contract_id"),
    ("selected_nonlocal_strategy_contract", "target_scope"),
    ("forbidden_imitation_and_regression_report", "rival_imitation_forbidden"),
)

NONLOCAL_LAW_GUIDED_WORK_ORDER_ARTIFACT_TYPES = (
    "source_strategy_intake_summary",
    "selected_nonlocal_intervention_scope",
    "law_guided_pressure_recomposition_map",
    "protected_current_best_strengths",
    "forbidden_rival_imitation_inventory",
    "nonlocal_target_unit_map",
    "future_generation_contract",
    "materiality_and_semantic_validation_plan",
    "ablation_and_reader_eval_plan",
    "generation_lock_report",
    "project_health_scope_guard_report",
    "nonlocal_law_work_order_gate_report",
    "nonlocal_law_guided_work_order_packet",
)

REQUIRED_STRATEGY_ARTIFACTS = (
    "nonlocal_law_guided_strategy_packet",
    "source_live_diagnostic_intake_summary",
    "law_transfer_summary",
    "packet_0063_nonlocal_gap_map",
    "rival_advantage_not_to_copy_report",
    "nonlocal_strategy_option_map",
    "selected_nonlocal_strategy_contract",
    "future_candidate_design_constraints",
    "forbidden_imitation_and_regression_report",
    "generation_lock_report",
    "next_work_order_readiness_report",
    "project_health_scope_guard_report",
    "nonlocal_law_guided_strategy_gate_report",
)


@dataclass(frozen=True)
class NonlocalLawGuidedWorkOrderResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawGuidedWorkOrderSubject:
    run_id: str
    strategy_packet_dir: Path
    strategy_packet_id: str
    strategy_packet_artifact_id: str | None
    strategy_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    missing_optional_aliases: tuple[str, ...]
    superseded_work_order_packet_id: str | None
    supersession_reason: str | None


@dataclass(frozen=True)
class WorkOrderSupersessionContext:
    corrected_current_valid_work_order_exists: bool
    superseded_work_order_packet_id: str | None = None
    supersession_reason: str | None = None
    stale_surface_failures: tuple[str, ...] = ()


def run_nonlocal_law_guided_work_order_planning(
    config: AbiConfig,
    *,
    strategy_packet: Path | str,
    operator_reviewed: bool,
) -> NonlocalLawGuidedWorkOrderResult:
    initialize_database(config)
    strategy_packet_dir = _resolve_path(config, strategy_packet)
    if not operator_reviewed:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            message=(
                "Nonlocal law-guided work-order planning refused; "
                "--operator-reviewed is required."
            ),
        )
    if not strategy_packet_dir.exists() or not strategy_packet_dir.is_dir():
        return _refusal(
            strategy_packet=strategy_packet_dir,
            message=(
                "Nonlocal law-guided work-order planning refused; strategy "
                f"packet directory not found: {strategy_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, strategy_packet_dir)
    except ValueError as error:
        return _refusal(strategy_packet=strategy_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                strategy_packet=strategy_packet_dir,
                message=(
                    "Nonlocal law-guided work-order planning refused; run is "
                    f"not registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_GUIDED_WORK_ORDER_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_guided_work_order"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_GUIDED_WORK_ORDER_LINEAGE_ID,
            created_by=NONLOCAL_LAW_GUIDED_WORK_ORDER_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_strategy_intake_summary"] = (
            _build_source_strategy_intake_summary(subject, packet_dir)
        )
        artifacts["source_strategy_intake_summary"] = writer.write_artifact(
            "source_strategy_intake_summary",
            payloads["source_strategy_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["selected_nonlocal_intervention_scope"] = (
            _build_selected_nonlocal_intervention_scope(subject)
        )
        artifacts["selected_nonlocal_intervention_scope"] = writer.write_artifact(
            "selected_nonlocal_intervention_scope",
            payloads["selected_nonlocal_intervention_scope"],
            parent_ids=[artifacts["source_strategy_intake_summary"].id],
        )

        payloads["law_guided_pressure_recomposition_map"] = (
            _build_law_guided_pressure_recomposition_map(subject)
        )
        artifacts["law_guided_pressure_recomposition_map"] = writer.write_artifact(
            "law_guided_pressure_recomposition_map",
            payloads["law_guided_pressure_recomposition_map"],
            parent_ids=[artifacts["selected_nonlocal_intervention_scope"].id],
        )

        payloads["protected_current_best_strengths"] = (
            _build_protected_current_best_strengths(subject)
        )
        artifacts["protected_current_best_strengths"] = writer.write_artifact(
            "protected_current_best_strengths",
            payloads["protected_current_best_strengths"],
            parent_ids=[artifacts["law_guided_pressure_recomposition_map"].id],
        )

        payloads["forbidden_rival_imitation_inventory"] = (
            _build_forbidden_rival_imitation_inventory(subject)
        )
        artifacts["forbidden_rival_imitation_inventory"] = writer.write_artifact(
            "forbidden_rival_imitation_inventory",
            payloads["forbidden_rival_imitation_inventory"],
            parent_ids=[artifacts["source_strategy_intake_summary"].id],
        )

        payloads["nonlocal_target_unit_map"] = _build_nonlocal_target_unit_map(
            subject
        )
        artifacts["nonlocal_target_unit_map"] = writer.write_artifact(
            "nonlocal_target_unit_map",
            payloads["nonlocal_target_unit_map"],
            parent_ids=[
                artifacts["law_guided_pressure_recomposition_map"].id,
                artifacts["forbidden_rival_imitation_inventory"].id,
            ],
        )

        payloads["future_generation_contract"] = _build_future_generation_contract(
            subject
        )
        artifacts["future_generation_contract"] = writer.write_artifact(
            "future_generation_contract",
            payloads["future_generation_contract"],
            parent_ids=[artifacts["nonlocal_target_unit_map"].id],
        )

        payloads["materiality_and_semantic_validation_plan"] = (
            _build_materiality_and_semantic_validation_plan(subject)
        )
        artifacts["materiality_and_semantic_validation_plan"] = writer.write_artifact(
            "materiality_and_semantic_validation_plan",
            payloads["materiality_and_semantic_validation_plan"],
            parent_ids=[
                artifacts["nonlocal_target_unit_map"].id,
                artifacts["future_generation_contract"].id,
            ],
        )

        payloads["ablation_and_reader_eval_plan"] = (
            _build_ablation_and_reader_eval_plan(subject)
        )
        artifacts["ablation_and_reader_eval_plan"] = writer.write_artifact(
            "ablation_and_reader_eval_plan",
            payloads["ablation_and_reader_eval_plan"],
            parent_ids=[artifacts["materiality_and_semantic_validation_plan"].id],
        )

        payloads["generation_lock_report"] = _build_generation_lock_report(subject)
        artifacts["generation_lock_report"] = writer.write_artifact(
            "generation_lock_report",
            payloads["generation_lock_report"],
            parent_ids=[artifacts["future_generation_contract"].id],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject, payloads)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["generation_lock_report"].id,
                artifacts["ablation_and_reader_eval_plan"].id,
            ],
        )

        payloads["nonlocal_law_work_order_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["nonlocal_law_work_order_gate_report"] = writer.write_artifact(
            "nonlocal_law_work_order_gate_report",
            payloads["nonlocal_law_work_order_gate_report"],
            parent_ids=[artifacts["project_health_scope_guard_report"].id],
        )

        payloads["nonlocal_law_guided_work_order_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["nonlocal_law_guided_work_order_packet"] = writer.write_artifact(
            "nonlocal_law_guided_work_order_packet",
            payloads["nonlocal_law_guided_work_order_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "nonlocal_law_guided_work_order_packet"
            ],
        )

        gate_report = payloads["nonlocal_law_work_order_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_work_order_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_GUIDED_WORK_ORDER_LINEAGE_ID,
        )

    return NonlocalLawGuidedWorkOrderResult(
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
    config: AbiConfig,
    strategy_packet_dir: Path,
) -> NonlocalLawGuidedWorkOrderSubject:
    payloads = _load_required_payloads(strategy_packet_dir)
    _validate_strategy_payloads(payloads)
    packet = payloads["nonlocal_law_guided_strategy_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Nonlocal law-guided work-order planning refused; strategy packet missing run_id.",
    )
    strategy_packet_id = str(packet.get("packet_id") or strategy_packet_dir.name)
    supersession_context = _work_order_supersession_context(
        config=config,
        run_id=run_id,
        source_strategy_packet_id=strategy_packet_id,
    )
    if supersession_context.corrected_current_valid_work_order_exists:
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; a current-valid "
            "work order already exists for this strategy packet."
        )

    packet_path = strategy_packet_dir / "nonlocal_law_guided_strategy_packet.json"
    with connect(config.db_path) as connection:
        strategy_artifact = _artifact_for_path(connection, packet_path)
    strategy_artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [
            strategy_artifact.id if strategy_artifact else None,
            *strategy_artifact_ids.values(),
        ]
    )
    return NonlocalLawGuidedWorkOrderSubject(
        run_id=run_id,
        strategy_packet_dir=strategy_packet_dir,
        strategy_packet_id=strategy_packet_id,
        strategy_packet_artifact_id=strategy_artifact.id
        if strategy_artifact
        else None,
        strategy_artifact_ids=strategy_artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        missing_optional_aliases=tuple(_missing_optional_aliases(payloads)),
        superseded_work_order_packet_id=(
            supersession_context.superseded_work_order_packet_id
        ),
        supersession_reason=supersession_context.supersession_reason,
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_STRATEGY_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Nonlocal law-guided work-order planning refused; strategy "
                f"packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; malformed "
            f"strategy artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_strategy_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["nonlocal_law_guided_strategy_packet"]
    option_map = payloads["nonlocal_strategy_option_map"]
    contract = payloads["selected_nonlocal_strategy_contract"]
    readiness = payloads["next_work_order_readiness_report"]
    future = payloads["future_candidate_design_constraints"]
    forbidden = payloads["forbidden_imitation_and_regression_report"]
    law_transfer = payloads["law_transfer_summary"]
    gap = payloads["packet_0063_nonlocal_gap_map"]

    if packet.get("accepted") is not True:
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; source strategy "
            "is not accepted."
        )
    _require_equal(packet, "strategy_kind", NONLOCAL_LAW_GUIDED_STRATEGY_KIND)
    _require_equal(packet, "selected_strategy_class", SELECTED_NONLOCAL_STRATEGY_CLASS)
    _require_equal(option_map, "selected_strategy_class", SELECTED_NONLOCAL_STRATEGY_CLASS)
    _require_equal(contract, "selected_strategy_class", SELECTED_NONLOCAL_STRATEGY_CLASS)
    if contract.get("nonlocal_strategy") is not True:
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; selected strategy "
            "contract is not nonlocal."
        )
    _require_bool(packet, "ready_for_nonlocal_work_order_planning", True)
    _require_bool(readiness, "ready_for_nonlocal_work_order_planning", True)
    _require_bool(packet, "ready_for_generation", False)
    _require_bool(readiness, "ready_for_generation", False)
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(
        packet,
        "current_best_candidate_packet_id",
        EXPECTED_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "proof_packet_id", EXPECTED_PROOF_PACKET_ID)
    _require_equal(packet, "reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID)
    if not _string_value(law_transfer.get("law_transfer_principle")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; law transfer "
            "principle is missing."
        )
    if not _string_value(law_transfer.get("source_gap_summary")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; source gap "
            "summary is missing."
        )
    if not _string_value(law_transfer.get("source_rival_advantage_summary")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; source rival "
            "advantage summary is missing."
        )
    if not _string_value(law_transfer.get("transferable_lesson")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; transferable "
            "lesson is missing."
        )
    if not _list_of_dicts(gap.get("gap_claims")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; packet_0063 "
            "gap claims are missing."
        )
    if not _string_list(gap.get("future_candidate_must_learn")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; future candidate "
            "learning constraints are missing."
        )
    if not _string_list(contract.get("affected_future_regions")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; affected future "
            "regions are missing."
        )
    if not _string_list(contract.get("selection_basis")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; selection basis "
            "is missing."
        )
    if not _string_list(future.get("required_constraints")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; future candidate "
            "constraints are missing."
        )
    if not _string_list(future.get("forbidden_constraints")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; future candidate "
            "forbidden constraints are missing."
        )
    if not _string_list(future.get("preserve_packet_0063_strengths")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; packet_0063 "
            "protected strengths are missing."
        )
    if forbidden.get("non_imitation_constraints_passed") is not True:
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; forbidden rival "
            "imitation constraints are missing or failed."
        )
    if not _string_list(forbidden.get("forbidden_rival_objects_or_sequence")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; forbidden rival "
            "material inventory is missing."
        )
    if not _string_list(forbidden.get("forbidden_regressions")):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; forbidden "
            "regressions are missing."
        )
    if _any_true(
        payloads,
        (
            "generation_authorized",
            "next_generation_authorized",
            "candidate_generated",
            "work_order_created",
            "ablation_authorized",
            "reader_state_eval_authorized",
        ),
    ):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; source strategy "
            "already opens generation, candidate, work-order, ablation, or "
            "reader-state evaluation."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; finality or "
            "phase-shift claim appears in the source strategy packet."
        )


def _build_source_strategy_intake_summary(
    subject: NonlocalLawGuidedWorkOrderSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["nonlocal_law_guided_strategy_packet"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "source_strategy_packet_artifact_id": subject.strategy_packet_artifact_id,
        "source_diagnostic_packet_id": packet.get("source_diagnostic_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "selected_strategy_class": packet.get("selected_strategy_class"),
        "strategy_optional_aliases_missing": bool(subject.missing_optional_aliases),
        "missing_optional_aliases": list(subject.missing_optional_aliases),
        "superseded_work_order_packet_id": subject.superseded_work_order_packet_id,
        "supersession_reason": subject.supersession_reason,
        "stale_work_order_superseded": (
            subject.superseded_work_order_packet_id is not None
        ),
        "consumed_existing_strategy_fields_successfully": True,
        "no_strategy_surface_fix_required_for_work_order_planning": True,
        "work_order_kind": NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_strategy_intake_summary_v1_controller",
    }


def _build_selected_nonlocal_intervention_scope(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    future = subject.payloads["future_candidate_design_constraints"]
    return {
        "work_order_kind": NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "intervention_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "nonlocal_but_bounded": True,
        "does_not_permit_free_rewrite": True,
        "free_rewrite_allowed": False,
        "one_region_patch_allowed": False,
        "generation_allowed": False,
        "affected_regions": list(CANONICAL_AFFECTED_REGIONS),
        "protected_regions": list(CANONICAL_PROTECTED_REGIONS),
        "scope_regions": list(NONLOCAL_SCOPE_REGIONS),
        "summary": (
            "The work order redistributes pressure across the artifact while "
            "remaining bounded by the selected nonlocal scope, protected "
            "packet_0063 strengths, and non-imitation constraints; it is not a "
            "free rewrite or one-region patch."
        ),
        "proof_no_answer_carry_policy": (
            "proof/no-answer pressure is protected pressure, not a new local "
            "patch target"
        ),
        "preserve_strengths": list(future["preserve_packet_0063_strengths"]),
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "selected_nonlocal_intervention_scope_v1_controller",
    }


def _build_law_guided_pressure_recomposition_map(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    law = subject.payloads["law_transfer_summary"]
    gap = subject.payloads["packet_0063_nonlocal_gap_map"]
    return {
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "law_transfer_principle": law["law_transfer_principle"],
        "recomposition_principle": RECOMPOSITION_PRINCIPLE,
        "source_gap_summary": law["source_gap_summary"],
        "source_rival_advantage_summary": law["source_rival_advantage_summary"],
        "transferable_lesson": law["transferable_lesson"],
        "gap_claims": list(gap["gap_claims"]),
        "future_candidate_must_learn": list(gap["future_candidate_must_learn"]),
        "pressure_recomposition_steps": [
            "stage object-event consequence before explanatory naming",
            "delay or embed explanation until object pressure earns it",
            "make packet_0063's own objects undergo consequence",
            "redistribute pressure across opening, middle sequence, and return",
            "prepare reread return through first-read object pressure",
        ],
        "explanation_policy": EXPLANATION_POLICY,
        "not_one_region_patch": True,
        "nonlocal_not_local_patch": True,
        "object_event_sequence_before_explanation": True,
        "explanation_abolition_forbidden": True,
        "generic_vividness_forbidden": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "law_guided_pressure_recomposition_map_v1_controller",
    }


def _build_protected_current_best_strengths(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    future = subject.payloads["future_candidate_design_constraints"]
    return {
        "current_best_candidate_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "proof_packet_id": EXPECTED_PROOF_PACKET_ID,
        "reader_state_packet_id": EXPECTED_READER_STATE_PACKET_ID,
        "protected_strengths": list(future["preserve_packet_0063_strengths"]),
        "must_preserve": [
            "table/dust/spoon/saucer/ring object field",
            "object-motion causal gains",
            "tactile inevitability gains",
            "no outside answer pressure",
            "proof packet_0034 evidence chain",
            "reader-state packet_0013 evidence chain",
        ],
        "forbidden_regressions": list(
            subject.payloads["forbidden_imitation_and_regression_report"][
                "forbidden_regressions"
            ]
        ),
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "protected_current_best_strengths_v1_controller",
    }


def _build_forbidden_rival_imitation_inventory(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    forbidden = subject.payloads["forbidden_imitation_and_regression_report"]
    return {
        "non_imitation_constraints_passed": True,
        "rival_imitation_forbidden": True,
        "source_forbidden_rival_objects_or_sequence": list(
            forbidden["forbidden_rival_objects_or_sequence"]
        ),
        "forbidden_rival_objects_or_sequence": list(
            FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE
        ),
        "forbidden_rival_imitation_modes": list(FORBIDDEN_RIVAL_IMITATION_MODES),
        "forbidden_regressions": list(FORBIDDEN_NONLOCAL_REGRESSIONS),
        "forbidden_rival_material": list(FORBIDDEN_RIVAL_MATERIAL),
        "forbidden_modes": [
            "rival diction",
            "rival scene transplant",
            "rival structure transplant",
            "rival cadence copy",
            "rival causal plot copy",
            "generic domestic grime substituted for the law",
            'copying "ordinary consequence" as a phrase or thesis',
        ],
        "generation_allowed": False,
        "strongest_rival_defeated": False,
        "strongest_rival_pressure_remains_blocking": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "forbidden_rival_imitation_inventory_v1_controller",
    }


def _build_nonlocal_target_unit_map(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    del subject
    units = [
        _target_unit(
            "object_event_consequence_before_explanation",
            "stage consequence before naming pressure",
            "future candidate must stage consequence before naming pressure",
        ),
        _target_unit(
            "delay_or_embed_explanatory_naming",
            "delay or embed explanatory naming",
            "explanation must be earned by object pressure, not removed entirely",
        ),
        _target_unit(
            "packet_0063_objects_undergo_consequence",
            "use packet_0063 object field under consequence",
            "use table/dust/spoon/saucer/ring, not rival objects",
        ),
        _target_unit(
            "middle_sequence_pressure_accumulation",
            "accumulate pressure through middle object-events",
            "pressure should accumulate through object-events across the middle",
        ),
        _target_unit(
            "reread_return_prepared_by_first_read_pressure",
            "prepare reread return through first-read pressure",
            "opening objects should become more necessary on reread",
        ),
        {
            "target_unit_id": "non_imitation_constraint_preservation",
            "unit_id": "non_imitation_constraint_preservation",
            "unit_role": "protected_negative_unit",
            "material_change_required": False,
            "protected_negative_unit": True,
            "target_effect": (
                "no rival scene/diction/structure/cadence/object sequence appears"
            ),
            "required_preservation": "rival imitation remains forbidden",
            "allowed_operations": [
                "diagnose causal sequencing only",
                "preserve packet_0063 object field",
            ],
            "forbidden_operations": list(FORBIDDEN_RIVAL_MATERIAL),
        },
    ]
    return {
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "target_units": units,
        "target_unit_ids": [unit["target_unit_id"] for unit in units],
        "required_unit_ids": list(NONLOCAL_TARGET_UNIT_IDS),
        "nonlocal_work_order": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "nonlocal_target_unit_map_v1_controller",
    }


def _target_unit(
    target_unit_id: str,
    target_effect: str,
    material_requirement: str,
) -> dict[str, object]:
    return {
        "target_unit_id": target_unit_id,
        "unit_id": target_unit_id,
        "unit_role": "material_change_unit",
        "material_change_required": True,
        "target_effect": target_effect,
        "material_requirement": material_requirement,
        "allowed_operations": [
            "redistribute pressure nonlocally",
            "stage object consequence before interpretation",
            "preserve packet_0063 evidence chain",
        ],
        "forbidden_operations": [
            "one-region patching",
            "free rewrite",
            "rival imitation",
            "generic vividness",
            "claiming strongest-rival defeat",
        ],
    }


def _build_future_generation_contract(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    del subject
    return {
        "generation_contract_version": GENERATION_CONTRACT_VERSION,
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "schema": FUTURE_SCHEMA_NAME,
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "ready_for_generation_authorization_review": True,
        "generation_authorization_decision_required": True,
        "generation_authorization_allowed_decisions": list(
            GENERATION_AUTHORIZATION_ALLOWED_DECISIONS
        ),
        "generation_attempt_budget": 0,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "future_generation_contract_v1_controller",
    }


def _build_materiality_and_semantic_validation_plan(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    del subject
    return {
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_validation_requirements": list(SEMANTIC_VALIDATION_REQUIREMENTS),
        "target_unit_ids_covered": list(NONLOCAL_TARGET_UNIT_IDS),
        "protected_unit_ids_covered": ["non_imitation_constraint_preservation"],
        "generation_allowed": False,
        "validation_required_before_candidate_evidence": True,
        "validation_requirements": [
            "stages object-event consequence before explanation",
            "delays or embeds explanation rather than deleting it",
            "uses packet_0063's own object field",
            "avoids rival imitation",
            "redistributes pressure nonlocally instead of patching one region",
            "preserves current-best object/tactile/proof/reader-state strengths",
            "avoids generic vividness or generic grimness",
            "does not claim strongest-rival defeat",
        ],
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "materiality_and_semantic_validation_plan_v1_controller",
    }


def _build_ablation_and_reader_eval_plan(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    del subject
    return {
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "strongest_rival_pressure_remains_active_until_synthesis": True,
        "ablation_executed": False,
        "reader_state_eval_executed": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "ablation_and_reader_eval_plan_v1_controller",
    }


def _build_generation_lock_report(
    subject: NonlocalLawGuidedWorkOrderSubject,
) -> dict[str, object]:
    del subject
    return {
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "future_generation_authorized": False,
        "ready_for_generation_authorization_review": True,
        "generation_authorization_still_required": True,
        "generation_authorization_decision_required": True,
        "generation_attempt_budget": 0,
        "work_order_created": True,
        "model_calls": 0,
        "generation_lock_reason": (
            "work-order planning records future generation contract metadata but "
            "does not authorize generation"
        ),
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "nonlocal_law_work_order_generation_lock_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: NonlocalLawGuidedWorkOrderSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = subject.payloads["nonlocal_law_guided_strategy_packet"]
    contract = payloads["future_generation_contract"]
    checks = [
        _check("source_strategy_accepted", packet.get("accepted") is True),
        _check("current_best_is_packet_0063", packet.get("current_best_candidate_packet_id") == EXPECTED_CURRENT_BEST_PACKET_ID),
        _check("proof_is_packet_0034", packet.get("proof_packet_id") == EXPECTED_PROOF_PACKET_ID),
        _check("reader_state_is_packet_0013", packet.get("reader_state_packet_id") == EXPECTED_READER_STATE_PACKET_ID),
        _check("work_order_created", True),
        _check("no_candidate_generated", True),
        _check("no_generation_authorized", True),
        _check("future_generation_authorized_false", contract["future_generation_authorized"] is False),
        _check("no_model_calls", True),
        _check("finalization_remains_false", True),
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "work_order_kind": NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "future_generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "nonlocal_law_work_order_project_health_scope_guard_v1_controller",
    }


def _build_gate_report(
    *,
    subject: NonlocalLawGuidedWorkOrderSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    health = payloads["project_health_scope_guard_report"]
    gate_results = [
        _gate_result("source_strategy_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("target_units_present", True),
        _gate_result("forbidden_rival_inventory_present", True),
        _gate_result("future_generation_contract_present", True),
        _gate_result("work_order_created", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("future_generation_not_authorized", True),
        _gate_result("no_model_calls", True),
        _gate_result("project_health_scope_guard_passed", health["passed"] is True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "finalization_eligible",
            False,
            ["nonlocal work order is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    return {
        "passed": False,
        "eligible": False,
        "source_strategy_packet_id": subject.strategy_packet_id,
        "work_order_kind": NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "future_generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "generation remains unauthorized",
            "candidate has not been generated",
            "ablation has not been executed",
            "reader-state evaluation has not been run",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        "summary_verdict": (
            "Nonlocal law-guided work order recorded future generation contract "
            "metadata only; generation remains locked."
        ),
        "worker": "nonlocal_law_work_order_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawGuidedWorkOrderSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    source = subject.payloads["nonlocal_law_guided_strategy_packet"]
    contract = payloads["future_generation_contract"]
    scope = payloads["selected_nonlocal_intervention_scope"]
    recomposition = payloads["law_guided_pressure_recomposition_map"]
    forbidden = payloads["forbidden_rival_imitation_inventory"]
    validation = payloads["materiality_and_semantic_validation_plan"]
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_GUIDED_WORK_ORDER_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_guided_work_order_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "superseded_work_order_packet_id": subject.superseded_work_order_packet_id,
        "supersession_reason": subject.supersession_reason,
        "stale_work_order_superseded": (
            subject.superseded_work_order_packet_id is not None
        ),
        "source_diagnostic_packet_id": source.get("source_diagnostic_packet_id"),
        "current_best_candidate_packet_id": source.get("current_best_candidate_packet_id"),
        "proof_packet_id": source.get("proof_packet_id"),
        "reader_state_packet_id": source.get("reader_state_packet_id"),
        "law_id": source.get("law_id"),
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "work_order_kind": NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "intervention_scope": scope["intervention_scope"],
        "affected_regions": list(scope["affected_regions"]),
        "protected_regions": list(scope["protected_regions"]),
        "recomposition_principle": recomposition["recomposition_principle"],
        "explanation_policy": recomposition["explanation_policy"],
        "nonlocal_not_local_patch": recomposition["nonlocal_not_local_patch"],
        "rival_imitation_forbidden": forbidden["rival_imitation_forbidden"],
        "forbidden_rival_objects_or_sequence": list(
            forbidden["forbidden_rival_objects_or_sequence"]
        ),
        "forbidden_rival_imitation_modes": list(
            forbidden["forbidden_rival_imitation_modes"]
        ),
        "forbidden_regressions": list(forbidden["forbidden_regressions"]),
        "materiality_requirements": list(validation["materiality_requirements"]),
        "semantic_validation_requirements": list(
            validation["semantic_validation_requirements"]
        ),
        "ready_for_generation_authorization_review": True,
        "generation_authorization_still_required": True,
        "target_unit_ids": list(NONLOCAL_TARGET_UNIT_IDS),
        "future_generation_contract": contract,
        "future_generation_authorized": False,
        "generation_attempt_budget": 0,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "work_order_created": True,
        "model_calls": 0,
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 1,
        },
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_guided_work_order_packet",
        ],
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_report": payloads["nonlocal_law_work_order_gate_report"],
        "worker": "nonlocal_law_guided_work_order_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_guided_work_order_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _work_order_supersession_context(
    *,
    config: AbiConfig,
    run_id: str,
    source_strategy_packet_id: str,
) -> WorkOrderSupersessionContext:
    root = config.run_dir(run_id) / "nonlocal_law_guided_work_order"
    if not root.exists():
        return WorkOrderSupersessionContext(
            corrected_current_valid_work_order_exists=False
        )
    for packet_dir in sorted(root.glob("packet_*"), reverse=True):
        packet_path = packet_dir / "nonlocal_law_guided_work_order_packet.json"
        if not packet_path.exists():
            continue
        try:
            payload = _read_envelope_payload(packet_path)
        except (OSError, ValueError, TypeError):
            continue
        if (
            payload.get("accepted") is True
            and payload.get("source_strategy_packet_id") == source_strategy_packet_id
            and payload.get("work_order_kind") == NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND
            and payload.get("work_order_created") is True
            and payload.get("candidate_generated") is False
            and payload.get("generation_authorized") is False
            and payload.get("future_generation_authorized") is False
            and payload.get("finalization_eligible") is False
            and payload.get("no_final_claim") is True
            and payload.get("no_phase_shift_claim") is True
        ):
            surface_failures = _generation_readiness_surface_failures(
                packet_dir=packet_dir,
                packet_payload=payload,
            )
            if surface_failures:
                return WorkOrderSupersessionContext(
                    corrected_current_valid_work_order_exists=False,
                    superseded_work_order_packet_id=str(payload.get("packet_id"))
                    or packet_dir.name,
                    supersession_reason=(
                        SUPERSESSION_REASON_GENERATION_READINESS_METADATA_MISSING
                    ),
                    stale_surface_failures=tuple(surface_failures),
                )
            return WorkOrderSupersessionContext(
                corrected_current_valid_work_order_exists=True,
                superseded_work_order_packet_id=str(payload.get("packet_id"))
                or packet_dir.name,
            )
    return WorkOrderSupersessionContext(corrected_current_valid_work_order_exists=False)


def _generation_readiness_surface_failures(
    *,
    packet_dir: Path,
    packet_payload: dict[str, Any],
) -> list[str]:
    failures: list[str] = []

    def require_string(payload: dict[str, Any], field_name: str, label: str) -> None:
        if not _string_value(payload.get(field_name)):
            failures.append(f"{label}.{field_name}")

    def require_string_list(payload: dict[str, Any], field_name: str, label: str) -> None:
        if not _string_list(payload.get(field_name)):
            failures.append(f"{label}.{field_name}")

    def require_bool(
        payload: dict[str, Any],
        field_name: str,
        expected: bool,
        label: str,
    ) -> None:
        if payload.get(field_name) is not expected:
            failures.append(f"{label}.{field_name}")

    require_string(packet_payload, "intervention_scope", "packet")
    require_string_list(packet_payload, "affected_regions", "packet")
    require_string_list(packet_payload, "protected_regions", "packet")
    require_string(packet_payload, "recomposition_principle", "packet")
    require_string(packet_payload, "explanation_policy", "packet")
    require_bool(packet_payload, "nonlocal_not_local_patch", True, "packet")
    require_bool(packet_payload, "rival_imitation_forbidden", True, "packet")
    require_string_list(packet_payload, "forbidden_rival_objects_or_sequence", "packet")
    require_string_list(packet_payload, "forbidden_rival_imitation_modes", "packet")
    require_string_list(packet_payload, "forbidden_regressions", "packet")
    require_string_list(packet_payload, "materiality_requirements", "packet")
    require_string_list(packet_payload, "semantic_validation_requirements", "packet")
    require_bool(
        packet_payload,
        "ready_for_generation_authorization_review",
        True,
        "packet",
    )
    require_bool(
        packet_payload,
        "generation_authorization_still_required",
        True,
        "packet",
    )
    require_bool(packet_payload, "future_generation_authorized", False, "packet")

    artifact_requirements = (
        (
            "selected_nonlocal_intervention_scope",
            (
                ("string", "intervention_scope", None),
                ("list", "affected_regions", None),
                ("list", "protected_regions", None),
                ("string", "summary", None),
                ("bool", "nonlocal_but_bounded", True),
                ("bool", "free_rewrite_allowed", False),
                ("bool", "one_region_patch_allowed", False),
                ("bool", "generation_allowed", False),
            ),
        ),
        (
            "law_guided_pressure_recomposition_map",
            (
                ("string", "recomposition_principle", None),
                ("string", "explanation_policy", None),
                ("bool", "nonlocal_not_local_patch", True),
                ("bool", "generation_allowed", False),
            ),
        ),
        (
            "forbidden_rival_imitation_inventory",
            (
                ("list", "forbidden_rival_objects_or_sequence", None),
                ("list", "forbidden_rival_imitation_modes", None),
                ("list", "forbidden_regressions", None),
                ("bool", "rival_imitation_forbidden", True),
                ("bool", "generation_allowed", False),
            ),
        ),
        (
            "materiality_and_semantic_validation_plan",
            (
                ("list", "materiality_requirements", None),
                ("list", "semantic_validation_requirements", None),
                ("bool", "generation_allowed", False),
                ("bool", "validation_required_before_candidate_evidence", True),
            ),
        ),
        (
            "future_generation_contract",
            (
                ("bool", "ready_for_generation_authorization_review", True),
                ("bool", "generation_authorization_decision_required", True),
                ("list", "generation_authorization_allowed_decisions", None),
                ("bool", "future_generation_authorized", False),
            ),
        ),
    )
    for artifact_type, requirements in artifact_requirements:
        payload = _read_work_order_payload(packet_dir, artifact_type)
        if not payload:
            failures.append(f"{artifact_type}.payload")
            continue
        for requirement_type, field_name, expected in requirements:
            if requirement_type == "string":
                require_string(payload, field_name, artifact_type)
            elif requirement_type == "list":
                require_string_list(payload, field_name, artifact_type)
            elif requirement_type == "bool" and isinstance(expected, bool):
                require_bool(payload, field_name, expected, artifact_type)
    return failures


def _read_work_order_payload(
    packet_dir: Path,
    artifact_type: str,
) -> dict[str, Any]:
    try:
        return _read_envelope_payload(packet_dir / f"{artifact_type}.json")
    except (OSError, ValueError, TypeError):
        return {}


def _missing_optional_aliases(payloads: dict[str, dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for artifact_type, field_name in OPTIONAL_ALIAS_FIELDS:
        value = payloads[artifact_type].get(field_name)
        if value is None or value == "":
            missing.append(f"{artifact_type}.{field_name}")
    return missing


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
    return False


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
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _refusal(
    *,
    strategy_packet: Path,
    message: str,
) -> NonlocalLawGuidedWorkOrderResult:
    return NonlocalLawGuidedWorkOrderResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "strategy_packet": str(strategy_packet),
            "work_order_kind": NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
            "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
            "candidate_generated": False,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "future_generation_authorized": False,
            "work_order_created": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
        },
    )


def _require_equal(
    payload: dict[str, Any],
    field_name: str,
    expected: object,
) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; source strategy "
            f"{field_name} must be {expected}."
        )


def _require_bool(
    payload: dict[str, Any],
    field_name: str,
    expected: bool,
) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(
            "Nonlocal law-guided work-order planning refused; source strategy "
            f"{field_name} must be {str(expected).lower()}."
        )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def _string_value(value: object) -> str:
    return value if isinstance(value, str) and value else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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
