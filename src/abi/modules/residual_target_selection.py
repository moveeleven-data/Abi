"""Controller-owned narrow residual target selection packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_RESIDUAL_TARGET_SELECTION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


RESIDUAL_TARGET_SELECTION_LINEAGE_ID = "residual_target_selection_v1"
RESIDUAL_TARGET_SELECTION_CREATED_BY = "residual_target_selection_v1_controller"

RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES = (
    "residual_target_selection_subject_manifest",
    "strategy_packet_intake_summary",
    "available_residual_options_report",
    "operator_residual_target_choice",
    "selected_residual_target_contract",
    "protected_effects_and_forbidden_changes",
    "next_work_order_scope",
    "residual_target_selection_gate_report",
    "residual_target_selection_packet",
)

REQUIRED_STRATEGY_ARTIFACTS = (
    "next_target_strategy_subject_manifest",
    "source_evidence_summary",
    "current_best_candidate_summary",
    "reader_state_blocker_summary",
    "strongest_rival_pressure_delta",
    "protected_effects_and_forbidden_changes",
    "object_event_pressure_target_map",
    "residual_target_option_map",
    "candidate_region_pressure_map",
    "next_intervention_strategy",
    "ablation_and_reader_eval_plan",
    "next_target_strategy_gate_report",
    "next_target_strategy_packet",
)

OBJECT_MOTION_CAUSALITY_TARGET_ID = "object_motion_causality_specificity"
REPEATED_BROAD_TARGET_ID = "first_read_object_event_pressure_gap"
NEXT_ALLOWED_ACTION = "prepare_object_motion_causality_specificity_work_order"


@dataclass(frozen=True)
class ResidualTargetSelectionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class ResidualTargetSelectionSubject:
    run_id: str
    strategy_packet_dir: Path
    strategy_packet_id: str
    strategy_packet_artifact_id: str | None
    strategy_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    selected_target_id: str
    selected_option: dict[str, Any]
    source_parent_ids: tuple[str, ...]


def run_residual_target_selection(
    config: AbiConfig,
    *,
    strategy_packet: Path | str,
    target: str,
    operator_reviewed: bool,
) -> ResidualTargetSelectionResult:
    initialize_database(config)
    strategy_packet_dir = _resolve_path(config, strategy_packet)
    if not operator_reviewed:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            target=target,
            message=(
                "Residual target selection refused; --operator-reviewed is "
                "required."
            ),
        )
    if not strategy_packet_dir.exists() or not strategy_packet_dir.is_dir():
        return _refusal(
            strategy_packet=strategy_packet_dir,
            target=target,
            message=(
                "Residual target selection refused; strategy packet directory "
                f"not found: {strategy_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, strategy_packet_dir, target)
    except ValueError as error:
        return _refusal(
            strategy_packet=strategy_packet_dir,
            target=target,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                strategy_packet=strategy_packet_dir,
                target=target,
                message=(
                    "Residual target selection refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_RESIDUAL_TARGET_SELECTION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "residual_target_selection"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=RESIDUAL_TARGET_SELECTION_LINEAGE_ID,
            created_by=RESIDUAL_TARGET_SELECTION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["residual_target_selection_subject_manifest"] = (
            _build_subject_manifest(subject, packet_dir)
        )
        artifacts["residual_target_selection_subject_manifest"] = writer.write_artifact(
            "residual_target_selection_subject_manifest",
            payloads["residual_target_selection_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["strategy_packet_intake_summary"] = _build_strategy_intake_summary(
            subject
        )
        artifacts["strategy_packet_intake_summary"] = writer.write_artifact(
            "strategy_packet_intake_summary",
            payloads["strategy_packet_intake_summary"],
            parent_ids=[
                artifacts["residual_target_selection_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["available_residual_options_report"] = (
            _build_available_residual_options_report(subject)
        )
        artifacts["available_residual_options_report"] = writer.write_artifact(
            "available_residual_options_report",
            payloads["available_residual_options_report"],
            parent_ids=[artifacts["strategy_packet_intake_summary"].id],
        )

        payloads["operator_residual_target_choice"] = (
            _build_operator_residual_target_choice(subject)
        )
        artifacts["operator_residual_target_choice"] = writer.write_artifact(
            "operator_residual_target_choice",
            payloads["operator_residual_target_choice"],
            parent_ids=[artifacts["available_residual_options_report"].id],
        )

        payloads["selected_residual_target_contract"] = (
            _build_selected_residual_target_contract(subject)
        )
        artifacts["selected_residual_target_contract"] = writer.write_artifact(
            "selected_residual_target_contract",
            payloads["selected_residual_target_contract"],
            parent_ids=[artifacts["operator_residual_target_choice"].id],
        )

        payloads["protected_effects_and_forbidden_changes"] = (
            _build_protected_effects_and_forbidden_changes(subject)
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["selected_residual_target_contract"].id,
                artifacts["strategy_packet_intake_summary"].id,
            ],
        )

        payloads["next_work_order_scope"] = _build_next_work_order_scope(subject)
        artifacts["next_work_order_scope"] = writer.write_artifact(
            "next_work_order_scope",
            payloads["next_work_order_scope"],
            parent_ids=[
                artifacts["selected_residual_target_contract"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["residual_target_selection_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["residual_target_selection_gate_report"] = writer.write_artifact(
            "residual_target_selection_gate_report",
            payloads["residual_target_selection_gate_report"],
            parent_ids=[
                artifacts["strategy_packet_intake_summary"].id,
                artifacts["operator_residual_target_choice"].id,
                artifacts["next_work_order_scope"].id,
            ],
        )

        payloads["residual_target_selection_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["residual_target_selection_packet"] = writer.write_artifact(
            "residual_target_selection_packet",
            payloads["residual_target_selection_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "residual_target_selection_packet"
            ],
        )

        gate_report = payloads["residual_target_selection_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="residual_target_selection_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=RESIDUAL_TARGET_SELECTION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        subject=subject,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return ResidualTargetSelectionResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    strategy_packet_dir: Path,
    target: str,
) -> ResidualTargetSelectionSubject:
    payloads = _load_required_payloads(strategy_packet_dir)
    packet = payloads["next_target_strategy_packet"]
    run_id = packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Residual target selection refused; strategy packet missing run_id.")
    strategy_packet_id = str(packet.get("packet_id") or strategy_packet_dir.name)
    if _strategy_marked_stale_by_latest_cleanup(config, run_id, strategy_packet_id):
        raise ValueError(
            "Residual target selection refused; strategy packet is marked stale "
            "by the latest loop-integrity cleanup checkpoint."
        )
    residual_map = payloads["residual_target_option_map"]
    options = residual_map.get("specific_residual_options")
    if not isinstance(options, list):
        raise ValueError(
            "Residual target selection refused; strategy packet has no residual options."
        )
    selected_option = _find_option(options, target)
    if selected_option is None:
        raise ValueError(
            "Residual target selection refused; selected target is not an "
            f"available residual option: {target}"
        )
    if selected_option.get("status") != "available_for_operator_selection":
        raise ValueError(
            "Residual target selection refused; selected target is not "
            f"available for operator selection: {target}"
        )

    packet_path = strategy_packet_dir / "next_target_strategy_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    strategy_artifact_ids = _artifact_ids_from_packet(packet)
    parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *strategy_artifact_ids.values(),
        ]
    )
    return ResidualTargetSelectionSubject(
        run_id=run_id,
        strategy_packet_dir=strategy_packet_dir,
        strategy_packet_id=strategy_packet_id,
        strategy_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        strategy_artifact_ids=strategy_artifact_ids,
        payloads=payloads,
        selected_target_id=target,
        selected_option=selected_option,
        source_parent_ids=tuple(parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_STRATEGY_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Residual target selection refused; strategy packet missing "
                f"{path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Residual target selection refused; malformed strategy artifact: "
                f"{path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _strategy_marked_stale_by_latest_cleanup(
    config: AbiConfig,
    run_id: str,
    strategy_packet_id: str,
) -> bool:
    base_dir = config.run_dir(run_id) / "loop_integrity_cleanup"
    if not base_dir.exists():
        return False
    cleanup_dirs = sorted(
        [child for child in base_dir.glob("packet_*") if child.is_dir()],
        key=lambda path: path.name,
    )
    for cleanup_dir in reversed(cleanup_dirs):
        registry_path = cleanup_dir / "stale_recommendation_registry.json"
        if not registry_path.exists():
            continue
        envelope = read_json_file(registry_path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        stale_entries = payload.get("stale_recommendations")
        if not isinstance(stale_entries, list):
            continue
        for entry in stale_entries:
            if not isinstance(entry, dict):
                continue
            if (
                entry.get("reference_type") == "older_next_target_strategy"
                and entry.get("reference_packet_id") == strategy_packet_id
                and entry.get("reuse_allowed_for_new_generation") is False
            ):
                return True
        return False
    return False


def _build_subject_manifest(
    subject: ResidualTargetSelectionSubject,
    packet_dir: Path,
) -> dict[str, object]:
    strategy_packet = subject.payloads["next_target_strategy_packet"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "source_strategy_packet_artifact_id": subject.strategy_packet_artifact_id,
        "current_best_candidate_packet_id": strategy_packet.get(
            "current_best_candidate_packet_id"
        ),
        "proof_packet_id": strategy_packet.get("proof_packet_id"),
        "reader_state_packet_id": strategy_packet.get("reader_state_packet_id"),
        "source_synthesis_packet_id": strategy_packet.get("source_synthesis_packet_id"),
        "loop_review_packet_id": strategy_packet.get("loop_review_packet_id"),
        "authorization_packet_id": strategy_packet.get("authorization_packet_id"),
        "selected_residual_target_id": subject.selected_target_id,
        "broad_blocker_class": _broad_blocker_class(subject),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "residual_target_selection_subject_manifest_v1_controller",
    }


def _build_strategy_intake_summary(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    return {
        "strategy_packet_consumed": True,
        "strategy_packet_id": subject.strategy_packet_id,
        "strategy_packet_dir": str(subject.strategy_packet_dir),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "loop_review_packet_id": packet.get("loop_review_packet_id"),
        "authorization_packet_id": packet.get("authorization_packet_id"),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "repeated_target_id": packet.get("repeated_target_id")
        or residual_map.get("repeated_target_id"),
        "primary_next_target": packet.get("primary_next_target"),
        "primary_next_subtarget": packet.get("primary_next_subtarget"),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "next_generation_authorized": packet.get("next_generation_authorized") is True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "strategy_packet_intake_summary_v1_controller",
    }


def _build_available_residual_options_report(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    residual_map = subject.payloads["residual_target_option_map"]
    options = residual_map.get("specific_residual_options", [])
    return {
        "residual_options_loaded": True,
        "broad_blocker_class": _broad_blocker_class(subject),
        "option_count": len(options) if isinstance(options, list) else 0,
        "available_option_ids": [
            str(option.get("option_id"))
            for option in options
            if isinstance(option, dict)
            and option.get("status") == "available_for_operator_selection"
        ],
        "selected_residual_target_id": subject.selected_target_id,
        "selected_target_valid": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "available_residual_options_report_v1_controller",
    }


def _build_operator_residual_target_choice(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    return {
        "operator_reviewed": True,
        "selected_residual_target_id": subject.selected_target_id,
        "operator_selection_reason": (
            "object motion causality specificity is narrower than the repeated "
            "broad first-read object-event pressure target, evidence-aligned "
            "with the rival gap, and less likely to drift into generic vividness, "
            "rival mimicry, proof/no-answer compression, or final-return overwork."
        ),
        "broad_blocker_class": _broad_blocker_class(subject),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "selected_target_is_narrower_than_repeated_broad_target": (
            _selected_target_is_narrower_than_repeated_broad_target(subject)
        ),
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "not_final_operator_approval": True,
        "not_human_validation": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "operator_residual_target_choice_v1_controller",
    }


def _build_selected_residual_target_contract(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    current_best_id = subject.payloads["next_target_strategy_packet"].get(
        "current_best_candidate_packet_id"
    )
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "target_definition": {
            "object_movement_should_produce_visible_consequence_before_explanation": True,
            "object_relation_should_sharpen_causal_pressure": True,
            "tactile_or_object_detail_must_change_expectation_not_decorate": True,
            "reader_should_infer_pressure_locally": True,
            "must_preserve_current_best_macro_and_reader_state_gains": True,
        },
        "operational_definition": [
            "object movement should produce visible consequence before explanation",
            "object relation should sharpen causal pressure",
            "tactile/object detail must change expectation, not merely decorate",
            "the intervention should make the reader infer pressure locally",
            f"the intervention must preserve {current_best_id}'s macro and reader-state gains",
        ],
        "forbidden_under_this_target": [
            "generic vividness",
            "object lists",
            "decorative sensory detail",
            "rival mimicry",
            "proof/no-answer compression by inertia",
            "final-return overwork",
            "summary compression",
            "abstract explanation of causality",
            "direct candidate generation in this command",
        ],
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "selected_residual_target_contract_v1_controller",
    }


def _build_protected_effects_and_forbidden_changes(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    return {
        "protected_effects": [
            f"{packet.get('current_best_candidate_packet_id')} as current best candidate",
            f"executed ablation support from {packet.get('proof_packet_id')}",
            f"reader-state support from {packet.get('reader_state_packet_id')}",
            "partial reread transformation",
            "table/dust/spoon/saucer/ring causal field",
            "proof/no-answer gains",
            "final-return gains",
            "reduced overexplanation",
            "strongest-rival pressure preservation",
            "no finality claim",
        ],
        "forbidden_changes": [
            "generic vividness",
            "object lists",
            "decorative sensory detail",
            "rival mimicry",
            "proof/no-answer compression by inertia",
            "final-return overwork",
            "summary compression",
            "abstract explanation of causality",
            "direct candidate generation in this command",
            "finalization eligibility claim",
            "phase-shift claim",
        ],
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_next_work_order_scope(
    subject: ResidualTargetSelectionSubject,
) -> dict[str, object]:
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "next_allowed_action": NEXT_ALLOWED_ACTION,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "requires_separate_generation_authorization": True,
        "next_strategy_or_work_order_authorized": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "next_work_order_scope_v1_controller",
    }


def _build_gate_report(
    *,
    subject: ResidualTargetSelectionSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("strategy_packet_consumed", True),
        _gate_result("residual_options_loaded", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("selected_target_valid", True),
        _gate_result(
            "selected_target_narrower_than_repeated_broad_target",
            _selected_target_is_narrower_than_repeated_broad_target(subject),
        ),
        _gate_result(
            "protected_effects_recorded",
            bool(payloads["protected_effects_and_forbidden_changes"]["protected_effects"]),
        ),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "candidate_generation_authorized",
            False,
            ["selection packet authorizes only a future work-order/strategy step"],
            record=False,
        ),
        _gate_result(
            "live_model_call_authorized",
            False,
            ["selection packet does not authorize live model calls"],
            record=False,
        ),
        _gate_result(
            "ablation_authorized",
            False,
            ["selection packet does not authorize ablation"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_authorized",
            False,
            ["selection packet does not authorize reader-state evaluation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["residual target selection is not finalization evidence"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_defeated",
            False,
            ["strongest rival remains blocking"],
            record=False,
        ),
        _gate_result(
            "human_validation_present",
            False,
            ["operator target selection is not human validation"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "candidate generation remains unauthorized",
        "live model calls remain unauthorized",
        "ablation remains unauthorized",
        "reader-state evaluation remains unauthorized",
        "strongest rival remains blocking",
        "human validation is absent",
        "finalization remains ineligible",
    ]
    return {
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "no_final_claim": True,
        "selected_residual_target_id": subject.selected_target_id,
        "next_allowed_action": NEXT_ALLOWED_ACTION,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Residual target selection accepted the operator-reviewed narrow "
            "target but remains fail-closed; it authorizes only a future work "
            "order, not generation."
        ),
        "worker": "residual_target_selection_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ResidualTargetSelectionSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    packet = subject.payloads["next_target_strategy_packet"]
    counts = packet_artifact_count_summary(
        required_artifact_types=RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="residual_target_selection_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "residual_target_selection_packet"],
        "counts": {
            **counts,
            "residual_target_selection_artifacts": counts["produced_artifacts"],
            "required_residual_target_selection_artifacts": counts[
                "required_artifacts"
            ],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "source_strategy_packet_id": subject.strategy_packet_id,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "selected_residual_target_id": subject.selected_target_id,
        "broad_blocker_class": _broad_blocker_class(subject),
        "repeated_broad_target_detected": _repeated_broad_target_detected(subject),
        "same_broad_target_allowed": _same_broad_target_allowed(subject),
        "selected_target_is_narrower_than_repeated_broad_target": (
            _selected_target_is_narrower_than_repeated_broad_target(subject)
        ),
        "next_allowed_action": NEXT_ALLOWED_ACTION,
        "next_recommended_action": NEXT_ALLOWED_ACTION,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "requires_separate_generation_authorization": True,
        "next_strategy_or_work_order_authorized": True,
        "gate_report": payloads["residual_target_selection_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "residual_target_selection_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: ResidualTargetSelectionSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["residual_target_selection_packet"]
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
        "counts": packet["counts"],
        "current_best_candidate_packet_id": packet["current_best_candidate_packet_id"],
        "selected_residual_target_id": subject.selected_target_id,
        "broad_blocker_class": packet["broad_blocker_class"],
        "next_allowed_action": NEXT_ALLOWED_ACTION,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": NEXT_ALLOWED_ACTION,
        "model_calls": 0,
    }


def _find_option(options: list[object], target: str) -> dict[str, Any] | None:
    for option in options:
        if isinstance(option, dict) and option.get("option_id") == target:
            return option
    return None


def _broad_blocker_class(subject: ResidualTargetSelectionSubject) -> str:
    residual_map = subject.payloads["residual_target_option_map"]
    return str(residual_map.get("broad_blocker_class") or REPEATED_BROAD_TARGET_ID)


def _repeated_broad_target_detected(subject: ResidualTargetSelectionSubject) -> bool:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    return bool(
        packet.get("repeated_target_detected") is True
        or residual_map.get("repeated_target_detected") is True
    )


def _same_broad_target_allowed(subject: ResidualTargetSelectionSubject) -> bool:
    packet = subject.payloads["next_target_strategy_packet"]
    residual_map = subject.payloads["residual_target_option_map"]
    return bool(
        packet.get("same_broad_target_allowed") is True
        or residual_map.get("same_broad_target_allowed") is True
    )


def _selected_target_is_narrower_than_repeated_broad_target(
    subject: ResidualTargetSelectionSubject,
) -> bool:
    return (
        _repeated_broad_target_detected(subject)
        and subject.selected_target_id != _broad_blocker_class(subject)
        and _same_broad_target_allowed(subject) is False
    )


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


def _artifact_ids_from_packet(packet_payload: dict[str, Any]) -> dict[str, str]:
    artifact_ids = packet_payload.get("artifact_ids")
    if not isinstance(artifact_ids, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in artifact_ids.items()
        if isinstance(value, str)
    }


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path), str(path.resolve())),
    ).fetchone()
    if row is None:
        return None
    return row_to_artifact(row)


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return (config.root / value).resolve()


def _refusal(
    *,
    strategy_packet: Path,
    target: str,
    message: str,
) -> ResidualTargetSelectionResult:
    return ResidualTargetSelectionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "strategy_packet": str(strategy_packet),
            "selected_residual_target_id": target,
            "candidate_generated": False,
            "candidate_generation_authorized": False,
            "next_strategy_or_work_order_authorized": False,
            "counts": {"model_calls": 0, "candidate_artifacts_created": 0},
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
