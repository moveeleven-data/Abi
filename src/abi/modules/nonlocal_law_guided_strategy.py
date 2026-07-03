"""Nonlocal law-guided strategy from live local-law rival diagnostic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_GUIDED_STRATEGY_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
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


NONLOCAL_LAW_GUIDED_STRATEGY_LINEAGE_ID = (
    "nonlocal_law_guided_strategy_from_rival_diagnostic_v1"
)
NONLOCAL_LAW_GUIDED_STRATEGY_CREATED_BY = (
    "nonlocal_law_guided_strategy_v1_controller"
)
NONLOCAL_LAW_GUIDED_STRATEGY_KIND = (
    "nonlocal_law_guided_strategy_from_rival_diagnostic"
)
SELECTED_NONLOCAL_STRATEGY_CLASS = "consequence_first_nonlocal_recomposition_strategy"
NEXT_RECOMMENDED_ACTION = "review_nonlocal_law_guided_strategy_before_work_order_planning"
FUTURE_WORK_ORDER_ACTION = "implement_nonlocal_law_guided_work_order_planning"
SOURCE_RECOMMENDED_STRATEGY_CLASS = (
    "nonlocal_law_guided_strategy_from_rival_diagnostic"
)
REQUIRED_COMPARISON_ROW_CLASSES = (
    "first_read_pressure_timing",
    "explanation_timing",
    "object_event_sequence",
    "proof_no_answer_residue",
    "reread_transformation",
    "strongest_rival_advantage",
)
PRESERVED_PACKET_0063_STRENGTHS = (
    "table/dust/spoon/saucer/ring field",
    "object-motion causal gains",
    "tactile inevitability gains",
    "no outside answer pressure",
    "current proof packet_0034 evidence chain",
    "current reader-state packet_0013 evidence chain",
)
RIVAL_SEQUENCE_FORBIDDEN = (
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

NONLOCAL_LAW_GUIDED_STRATEGY_ARTIFACT_TYPES = (
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
    "nonlocal_law_guided_strategy_packet",
)

REQUIRED_DIAGNOSTIC_ARTIFACTS = (
    "model_backed_local_law_diagnostic_packet",
    "source_direct_rival_materialization_intake_summary",
    "law_application_comparison_matrix",
    "first_read_pressure_diagnostic_report",
    "rival_advantage_under_law_report",
    "packet_0063_law_gap_report",
    "non_imitation_constraint_report",
    "next_strategy_readiness_report",
    "project_health_scope_guard_report",
    "local_law_rival_diagnostic_gate_report",
)


@dataclass(frozen=True)
class NonlocalLawGuidedStrategyResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class NonlocalLawGuidedStrategySubject:
    run_id: str
    diagnostic_packet_dir: Path
    diagnostic_packet_id: str
    diagnostic_packet_artifact_id: str | None
    diagnostic_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]


def run_nonlocal_law_guided_strategy(
    config: AbiConfig,
    *,
    diagnostic_packet: Path | str,
    operator_reviewed: bool,
) -> NonlocalLawGuidedStrategyResult:
    initialize_database(config)
    diagnostic_packet_dir = _resolve_path(config, diagnostic_packet)
    if not operator_reviewed:
        return _refusal(
            diagnostic_packet=diagnostic_packet_dir,
            message=(
                "Nonlocal law-guided strategy refused; --operator-reviewed is "
                "required."
            ),
        )
    if not diagnostic_packet_dir.exists() or not diagnostic_packet_dir.is_dir():
        return _refusal(
            diagnostic_packet=diagnostic_packet_dir,
            message=(
                "Nonlocal law-guided strategy refused; diagnostic packet "
                f"directory not found: {diagnostic_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, diagnostic_packet_dir)
    except ValueError as error:
        return _refusal(diagnostic_packet=diagnostic_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                diagnostic_packet=diagnostic_packet_dir,
                message=(
                    "Nonlocal law-guided strategy refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_GUIDED_STRATEGY_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_guided_strategy"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_GUIDED_STRATEGY_LINEAGE_ID,
            created_by=NONLOCAL_LAW_GUIDED_STRATEGY_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_live_diagnostic_intake_summary"] = (
            _build_source_live_diagnostic_intake_summary(subject, packet_dir)
        )
        artifacts["source_live_diagnostic_intake_summary"] = writer.write_artifact(
            "source_live_diagnostic_intake_summary",
            payloads["source_live_diagnostic_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["law_transfer_summary"] = _build_law_transfer_summary(subject)
        artifacts["law_transfer_summary"] = writer.write_artifact(
            "law_transfer_summary",
            payloads["law_transfer_summary"],
            parent_ids=[artifacts["source_live_diagnostic_intake_summary"].id],
        )

        payloads["packet_0063_nonlocal_gap_map"] = _build_packet_0063_gap_map(subject)
        artifacts["packet_0063_nonlocal_gap_map"] = writer.write_artifact(
            "packet_0063_nonlocal_gap_map",
            payloads["packet_0063_nonlocal_gap_map"],
            parent_ids=[artifacts["law_transfer_summary"].id],
        )

        payloads["rival_advantage_not_to_copy_report"] = (
            _build_rival_advantage_not_to_copy_report(subject)
        )
        artifacts["rival_advantage_not_to_copy_report"] = writer.write_artifact(
            "rival_advantage_not_to_copy_report",
            payloads["rival_advantage_not_to_copy_report"],
            parent_ids=[artifacts["law_transfer_summary"].id],
        )

        payloads["nonlocal_strategy_option_map"] = _build_strategy_option_map(subject)
        artifacts["nonlocal_strategy_option_map"] = writer.write_artifact(
            "nonlocal_strategy_option_map",
            payloads["nonlocal_strategy_option_map"],
            parent_ids=[
                artifacts["packet_0063_nonlocal_gap_map"].id,
                artifacts["rival_advantage_not_to_copy_report"].id,
            ],
        )

        payloads["selected_nonlocal_strategy_contract"] = (
            _build_selected_strategy_contract(subject)
        )
        artifacts["selected_nonlocal_strategy_contract"] = writer.write_artifact(
            "selected_nonlocal_strategy_contract",
            payloads["selected_nonlocal_strategy_contract"],
            parent_ids=[artifacts["nonlocal_strategy_option_map"].id],
        )

        payloads["future_candidate_design_constraints"] = (
            _build_future_candidate_design_constraints(subject)
        )
        artifacts["future_candidate_design_constraints"] = writer.write_artifact(
            "future_candidate_design_constraints",
            payloads["future_candidate_design_constraints"],
            parent_ids=[artifacts["selected_nonlocal_strategy_contract"].id],
        )

        payloads["forbidden_imitation_and_regression_report"] = (
            _build_forbidden_imitation_and_regression_report(subject)
        )
        artifacts["forbidden_imitation_and_regression_report"] = writer.write_artifact(
            "forbidden_imitation_and_regression_report",
            payloads["forbidden_imitation_and_regression_report"],
            parent_ids=[
                artifacts["rival_advantage_not_to_copy_report"].id,
                artifacts["future_candidate_design_constraints"].id,
            ],
        )

        payloads["generation_lock_report"] = _build_generation_lock_report(subject)
        artifacts["generation_lock_report"] = writer.write_artifact(
            "generation_lock_report",
            payloads["generation_lock_report"],
            parent_ids=[artifacts["selected_nonlocal_strategy_contract"].id],
        )

        payloads["next_work_order_readiness_report"] = (
            _build_next_work_order_readiness_report(subject)
        )
        artifacts["next_work_order_readiness_report"] = writer.write_artifact(
            "next_work_order_readiness_report",
            payloads["next_work_order_readiness_report"],
            parent_ids=[
                artifacts["future_candidate_design_constraints"].id,
                artifacts["generation_lock_report"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[artifacts["next_work_order_readiness_report"].id],
        )

        payloads["nonlocal_law_guided_strategy_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["nonlocal_law_guided_strategy_gate_report"] = writer.write_artifact(
            "nonlocal_law_guided_strategy_gate_report",
            payloads["nonlocal_law_guided_strategy_gate_report"],
            parent_ids=[
                artifacts["project_health_scope_guard_report"].id,
                artifacts["forbidden_imitation_and_regression_report"].id,
            ],
        )

        payloads["nonlocal_law_guided_strategy_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["nonlocal_law_guided_strategy_packet"] = writer.write_artifact(
            "nonlocal_law_guided_strategy_packet",
            payloads["nonlocal_law_guided_strategy_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "nonlocal_law_guided_strategy_packet"
            ],
        )

        gate_report = payloads["nonlocal_law_guided_strategy_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_guided_strategy_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=NONLOCAL_LAW_GUIDED_STRATEGY_LINEAGE_ID,
        )

    return NonlocalLawGuidedStrategyResult(
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
    diagnostic_packet_dir: Path,
) -> NonlocalLawGuidedStrategySubject:
    payloads = _load_required_payloads(diagnostic_packet_dir)
    _validate_diagnostic_payloads(payloads)
    packet = payloads["model_backed_local_law_diagnostic_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Nonlocal law-guided strategy refused; diagnostic packet missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or diagnostic_packet_dir.name)
    packet_path = diagnostic_packet_dir / "model_backed_local_law_diagnostic_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    return NonlocalLawGuidedStrategySubject(
        run_id=run_id,
        diagnostic_packet_dir=diagnostic_packet_dir,
        diagnostic_packet_id=packet_id,
        diagnostic_packet_artifact_id=packet_artifact.id
        if packet_artifact
        else None,
        diagnostic_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_DIAGNOSTIC_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Nonlocal law-guided strategy refused; diagnostic packet missing "
                f"{path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Nonlocal law-guided strategy refused; malformed diagnostic artifact: "
            f"{path.name}."
        )
    return envelope["payload"]


def _validate_diagnostic_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["model_backed_local_law_diagnostic_packet"]
    matrix = payloads["law_application_comparison_matrix"]
    gap = payloads["packet_0063_law_gap_report"]
    constraints = payloads["non_imitation_constraint_report"]

    if packet.get("accepted") is not True:
        raise ValueError(
            "Nonlocal law-guided strategy refused; diagnostic packet is not accepted."
        )
    _require_bool(packet, "live_model_diagnostic", True)
    _require_bool(packet, "model_backed", True)
    if _int_or_zero(packet.get("model_calls")) != 1:
        raise ValueError(
            "Nonlocal law-guided strategy refused; diagnostic model_calls must equal 1."
        )
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(
        packet,
        "current_best_candidate_packet_id",
        EXPECTED_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "proof_packet_id", EXPECTED_PROOF_PACKET_ID)
    _require_equal(packet, "reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID)
    _require_equal(packet, "stronger_under_law", "rival")
    _require_bool(packet, "ready_for_nonlocal_strategy", True)
    _require_bool(packet, "ready_for_generation", False)
    _require_equal(
        packet,
        "recommended_next_strategy_class",
        SOURCE_RECOMMENDED_STRATEGY_CLASS,
    )
    if _int_or_zero(packet.get("comparison_row_count")) < len(
        REQUIRED_COMPARISON_ROW_CLASSES
    ):
        raise ValueError(
            "Nonlocal law-guided strategy refused; diagnostic comparison rows are "
            "incomplete."
        )
    row_classes = {
        str(row.get("row_class"))
        for row in _list_of_dicts(matrix.get("comparison_rows"))
    }
    missing_rows = sorted(set(REQUIRED_COMPARISON_ROW_CLASSES) - row_classes)
    if missing_rows:
        raise ValueError(
            "Nonlocal law-guided strategy refused; diagnostic missing comparison "
            f"row classes: {missing_rows}."
        )
    if not _list_of_dicts(gap.get("gap_claims")):
        raise ValueError(
            "Nonlocal law-guided strategy refused; packet_0063 gap claims are missing."
        )
    if not _string_list(gap.get("future_candidate_must_learn")):
        raise ValueError(
            "Nonlocal law-guided strategy refused; future_candidate_must_learn is "
            "missing."
        )
    if constraints.get("non_imitation_constraints_passed") is not True:
        raise ValueError(
            "Nonlocal law-guided strategy refused; non-imitation constraints are "
            "missing or failed."
        )
    if not _string_list(
        constraints.get("forbidden_imitation_modes")
    ) and not _string_list(constraints.get("constraints")):
        raise ValueError(
            "Nonlocal law-guided strategy refused; non-imitation constraints are "
            "missing."
        )
    if _any_true(
        payloads,
        (
            "generation_authorized",
            "next_generation_authorized",
            "candidate_generated",
            "residual_target_selected",
            "work_order_created",
            "ablation_authorized",
            "reader_state_eval_authorized",
        ),
    ):
        raise ValueError(
            "Nonlocal law-guided strategy refused; source diagnostic already opens "
            "a generation, target, work-order, ablation, or reader-state path."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Nonlocal law-guided strategy refused; finality or phase-shift claim "
            "appears in the diagnostic packet."
        )


def _build_source_live_diagnostic_intake_summary(
    subject: NonlocalLawGuidedStrategySubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["model_backed_local_law_diagnostic_packet"]
    matrix = subject.payloads["law_application_comparison_matrix"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_diagnostic_packet_id": subject.diagnostic_packet_id,
        "source_diagnostic_packet_dir": str(subject.diagnostic_packet_dir),
        "source_diagnostic_packet_artifact_id": subject.diagnostic_packet_artifact_id,
        "source_direct_rival_materialization_packet_id": packet.get(
            "source_direct_rival_materialization_packet_id"
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "model_backed": packet.get("model_backed"),
        "live_model_diagnostic": packet.get("live_model_diagnostic"),
        "source_model_calls": packet.get("model_calls"),
        "comparison_row_count": len(matrix.get("comparison_rows", [])),
        "comparison_row_classes": [
            row["row_class"] for row in _list_of_dicts(matrix.get("comparison_rows"))
        ],
        "stronger_under_law": packet.get("stronger_under_law"),
        "packet_0063_law_score": packet.get("packet_0063_law_score"),
        "rival_law_score": packet.get("rival_law_score"),
        "diagnostic_ready_for_nonlocal_strategy": packet.get(
            "ready_for_nonlocal_strategy"
        ),
        "diagnostic_ready_for_generation": packet.get("ready_for_generation"),
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_live_diagnostic_intake_summary_v1_controller",
    }


def _build_law_transfer_summary(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    packet = subject.payloads["model_backed_local_law_diagnostic_packet"]
    gap = subject.payloads["packet_0063_law_gap_report"]
    rival = subject.payloads["rival_advantage_under_law_report"]
    return {
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "law_transfer_principle": (
            "Object-event consequence must accumulate before explicit "
            "explanation, thesis, crisis, law, or named pressure."
        ),
        "source_gap_summary": packet.get("packet_0063_gap_summary"),
        "source_rival_advantage_summary": packet.get("rival_advantage_summary"),
        "transferable_lesson": (
            "Transfer sequencing and causal pressure only; do not transfer rival "
            "objects, scenes, diction, structure, or cadence."
        ),
        "packet_0063_gap_class": gap.get("gap_class"),
        "rival_advantage_class": rival.get("rival_advantage_class"),
        "explanation_policy": (
            "Explanation is allowed only after object pressure has been earned or "
            "embedded in consequence."
        ),
        "nonlocal_not_local_patch": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "law_transfer_summary_v1_controller",
    }


def _build_packet_0063_gap_map(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    gap = subject.payloads["packet_0063_law_gap_report"]
    return {
        "current_best_candidate_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "proof_packet_id": EXPECTED_PROOF_PACKET_ID,
        "reader_state_packet_id": EXPECTED_READER_STATE_PACKET_ID,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "gap_class": gap.get("gap_class"),
        "gap_summary": gap.get("summary"),
        "gap_claims": list(gap.get("gap_claims", [])),
        "future_candidate_must_learn": list(gap.get("future_candidate_must_learn", [])),
        "nonlocal_scope": [
            "opening pressure distribution",
            "middle object-event sequencing",
            "explanation timing",
            "return/reread preparation",
        ],
        "packet_0063_should_not_be_locally_patched_again": True,
        "current_best_not_demoted": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "packet_0063_nonlocal_gap_map_v1_controller",
    }


def _build_rival_advantage_not_to_copy_report(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    rival = subject.payloads["rival_advantage_under_law_report"]
    return {
        "source_direct_rival_materialization_packet_id": (
            subject.payloads["model_backed_local_law_diagnostic_packet"].get(
                "source_direct_rival_materialization_packet_id"
            )
        ),
        "rival_text_sha256": rival.get("rival_text_sha256"),
        "rival_advantage_summary": rival.get("summary"),
        "rival_advantage_class": rival.get("rival_advantage_class"),
        "advantage_to_learn": (
            "causal staging through mundane consequence before explicit thesis"
        ),
        "forbidden_rival_sequence": list(RIVAL_SEQUENCE_FORBIDDEN),
        "no_rival_diction": True,
        "no_rival_scene_transplant": True,
        "no_rival_structure_transplant": True,
        "no_rival_cadence_copy": True,
        "strongest_rival_defeated": False,
        "strongest_rival_defeat_claim": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "rival_advantage_not_to_copy_report_v1_controller",
    }


def _build_strategy_option_map(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    del subject
    options = [
        {
            "rank": 1,
            "strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
            "selected": True,
            "purpose": (
                "re-stage packet_0063 so object-event consequence accumulates "
                "before explanatory naming"
            ),
        },
        {
            "rank": 2,
            "strategy_class": "explanation_delay_and_embedding_strategy",
            "selected": False,
            "purpose": (
                "delay explicit conceptual claims until object pressure has matured"
            ),
        },
        {
            "rank": 3,
            "strategy_class": "object_event_sequence_expansion_without_rival_imitation",
            "selected": False,
            "purpose": (
                "make packet_0063's own objects undergo consequence without "
                "importing rival scenes"
            ),
        },
        {
            "rank": 4,
            "strategy_class": "reread_return_preparation_strategy",
            "selected": False,
            "purpose": (
                "ensure first-read object pressure prepares later return/reread "
                "transformation"
            ),
        },
        {
            "rank": 5,
            "strategy_class": "no_generation_until_work_order_strategy",
            "selected": False,
            "purpose": "keep generation locked until a bounded nonlocal work order exists",
        },
    ]
    return {
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "ranked_options": options,
        "generation_allowed": False,
        "candidate_generated": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "nonlocal_strategy_option_map_v1_controller",
    }


def _build_selected_strategy_contract(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    packet = subject.payloads["model_backed_local_law_diagnostic_packet"]
    return {
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "selection_basis": [
            f"stronger_under_law={packet.get('stronger_under_law')}",
            f"packet_0063_law_score={packet.get('packet_0063_law_score')}",
            f"rival_law_score={packet.get('rival_law_score')}",
            "live diagnostic requires nonlocal strategy review before work-order planning",
        ],
        "nonlocal_strategy": True,
        "not_one_region_patch": True,
        "not_residual_target_selection": True,
        "not_work_order": True,
        "not_generation": True,
        "affected_future_regions": [
            "opening pressure distribution",
            "middle object-event sequencing",
            "explanation timing",
            "return/reread preparation",
        ],
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "selected_nonlocal_strategy_contract_v1_controller",
    }


def _build_future_candidate_design_constraints(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    gap = subject.payloads["packet_0063_law_gap_report"]
    required = [
        "consequence before explanation",
        "object-event sequence before thesis",
        "explanation earned by object pressure",
        "no generic vividness",
        "no local residual patching",
        "no imitation of rival sequence",
        "preserve packet_0063 evidence-supported object/tactile gains",
        "preserve strongest-rival pressure as active blocker until ablation/reader-state/synthesis say otherwise",
    ]
    forbidden = [
        "copying rival objects/scenes/actions",
        "simply adding more incidents",
        "making the text grimmer generically",
        "deleting all explanation",
        "turning the law into a thesis statement",
        "claiming finality or strongest-rival defeat",
    ]
    return {
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "required_constraints": required,
        "forbidden_constraints": forbidden,
        "future_candidate_must_learn": list(gap.get("future_candidate_must_learn", [])),
        "preserve_packet_0063_strengths": list(PRESERVED_PACKET_0063_STRENGTHS),
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "future_candidate_design_constraints_v1_controller",
    }


def _build_forbidden_imitation_and_regression_report(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    constraints = subject.payloads["non_imitation_constraint_report"]
    return {
        "non_imitation_constraints_passed": True,
        "source_forbidden_imitation_modes": (
            _string_list(constraints.get("forbidden_imitation_modes"))
            or _string_list(constraints.get("constraints"))
        ),
        "forbidden_rival_objects_or_sequence": list(RIVAL_SEQUENCE_FORBIDDEN),
        "forbidden_regressions": [
            "local patching instead of nonlocal pressure redistribution",
            "generic vividness substituted for causal consequence",
            "all explanation deleted rather than delayed or earned",
            "rival scene imported",
            "packet_0063 object/tactile gains weakened",
            "strongest-rival pressure marked resolved without proof",
        ],
        "diagnose_causal_advantage_only": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "forbidden_imitation_and_regression_report_v1_controller",
    }


def _build_generation_lock_report(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    del subject
    return {
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "generation_lock_reason": (
            "strategy packet is non-generative; generation requires future "
            "nonlocal work order and separate authorization"
        ),
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "nonlocal_law_guided_generation_lock_report_v1_controller",
    }


def _build_next_work_order_readiness_report(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    del subject
    return {
        "ready_for_nonlocal_work_order_planning": True,
        "ready_for_generation": False,
        "generation_requires_future_work_order": True,
        "generation_requires_separate_authorization": True,
        "recommended_next_action": FUTURE_WORK_ORDER_ACTION,
        "next_recommended_action": FUTURE_WORK_ORDER_ACTION,
        "work_order_created": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "next_work_order_readiness_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: NonlocalLawGuidedStrategySubject,
) -> dict[str, object]:
    packet = subject.payloads["model_backed_local_law_diagnostic_packet"]
    checks = [
        _check("source_diagnostic_accepted", packet.get("accepted") is True),
        _check("source_is_live_model_backed", packet.get("model_backed") is True),
        _check("source_model_call_count_one", packet.get("model_calls") == 1),
        _check("current_best_is_packet_0063", packet.get("current_best_candidate_packet_id") == EXPECTED_CURRENT_BEST_PACKET_ID),
        _check("proof_is_packet_0034", packet.get("proof_packet_id") == EXPECTED_PROOF_PACKET_ID),
        _check("reader_state_is_packet_0013", packet.get("reader_state_packet_id") == EXPECTED_READER_STATE_PACKET_ID),
        _check("nonlocal_strategy_only", True),
        _check("no_generation_path_introduced", True),
        _check("no_target_or_work_order_introduced", True),
        _check("finalization_remains_false", True),
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "nonlocal_law_guided_project_health_scope_guard_v1_controller",
    }


def _build_gate_report(
    *,
    subject: NonlocalLawGuidedStrategySubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    health = payloads["project_health_scope_guard_report"]
    gate_results = [
        _gate_result("source_live_diagnostic_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("required_comparison_rows_present", True),
        _gate_result("packet_0063_gap_claims_present", True),
        _gate_result("future_candidate_learning_present", True),
        _gate_result("non_imitation_constraints_preserved", True),
        _gate_result("selected_strategy_is_nonlocal", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_model_calls", True),
        _gate_result("project_health_scope_guard_passed", health["passed"] is True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "finalization_eligible",
            False,
            ["nonlocal strategy packet is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    return {
        "passed": False,
        "eligible": False,
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "source_diagnostic_packet_id": subject.diagnostic_packet_id,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
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
            "nonlocal work order has not been created",
            "generation remains unauthorized",
            "candidate has not been generated",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        "summary_verdict": (
            "Nonlocal law-guided strategy recorded strategy evidence only; "
            "generation remains locked."
        ),
        "worker": "nonlocal_law_guided_strategy_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawGuidedStrategySubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    source = subject.payloads["model_backed_local_law_diagnostic_packet"]
    readiness = payloads["next_work_order_readiness_report"]
    health = payloads["project_health_scope_guard_report"]
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_GUIDED_STRATEGY_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_guided_strategy_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_diagnostic_packet_id": subject.diagnostic_packet_id,
        "source_diagnostic_packet_dir": str(subject.diagnostic_packet_dir),
        "source_direct_rival_materialization_packet_id": source.get(
            "source_direct_rival_materialization_packet_id"
        ),
        "current_best_candidate_packet_id": source.get("current_best_candidate_packet_id"),
        "proof_packet_id": source.get("proof_packet_id"),
        "reader_state_packet_id": source.get("reader_state_packet_id"),
        "law_id": source.get("law_id"),
        "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
        "selected_strategy_class": SELECTED_NONLOCAL_STRATEGY_CLASS,
        "stronger_under_law": source.get("stronger_under_law"),
        "packet_0063_law_score": source.get("packet_0063_law_score"),
        "rival_law_score": source.get("rival_law_score"),
        "law_transfer_summary": payloads["law_transfer_summary"],
        "future_candidate_constraints": payloads["future_candidate_design_constraints"],
        "forbidden_imitation_constraints": payloads[
            "forbidden_imitation_and_regression_report"
        ],
        "ready_for_nonlocal_work_order_planning": readiness[
            "ready_for_nonlocal_work_order_planning"
        ],
        "ready_for_generation": readiness["ready_for_generation"],
        "generation_requires_future_work_order": readiness[
            "generation_requires_future_work_order"
        ],
        "generation_requires_separate_authorization": readiness[
            "generation_requires_separate_authorization"
        ],
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "future_work_order_recommended_next_action": readiness[
            "recommended_next_action"
        ],
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 0,
            "residual_target_selection_artifacts_created": 0,
        },
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_guided_strategy_packet",
        ],
        "project_health_scope_guard_passed": health["project_health_scope_guard_passed"],
        "source_chain_coherent": health["source_chain_coherent"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_report": payloads["nonlocal_law_guided_strategy_gate_report"],
        "worker": "nonlocal_law_guided_strategy_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_guided_strategy_packet"]
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
    diagnostic_packet: Path,
    message: str,
) -> NonlocalLawGuidedStrategyResult:
    return NonlocalLawGuidedStrategyResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "diagnostic_packet": str(diagnostic_packet),
            "strategy_kind": NONLOCAL_LAW_GUIDED_STRATEGY_KIND,
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


def _require_equal(
    payload: dict[str, Any],
    field_name: str,
    expected: object,
) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(
            "Nonlocal law-guided strategy refused; diagnostic "
            f"{field_name} must be {expected}."
        )


def _require_bool(
    payload: dict[str, Any],
    field_name: str,
    expected: bool,
) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(
            "Nonlocal law-guided strategy refused; diagnostic "
            f"{field_name} must be {str(expected).lower()}."
        )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


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
