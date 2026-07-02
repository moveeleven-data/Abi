"""Controller-owned residual work-order planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_RESIDUAL_WORK_ORDER_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)
from abi.target_artifacts import (
    GENERIC_TARGET_DIAGNOSTIC_ARTIFACT,
    GENERIC_TARGET_UNIT_MAP_ARTIFACT,
    LEGACY_TARGET_DIAGNOSTIC_ARTIFACT,
    LEGACY_TARGET_UNIT_MAP_ARTIFACT,
    read_target_unit_map,
)
from abi.modules.residual_targets import (
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    ENDING_RETURN_REGION_ID,
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    PROOF_NO_ANSWER_REGION_ID,
    PROOF_NO_ANSWER_RESIDUE_TARGET_ID,
    SELECTED_REGION_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
    ResidualTargetSpec,
    compile_tactile_target_units,
    extract_object_labels,
    get_residual_target_spec,
    payload_has_placeholder_generation_contract,
    semantic_preflight_failures_for_work_order,
    target_adapter_metadata,
)


RESIDUAL_WORK_ORDER_LINEAGE_ID = "residual_work_order_v1"
RESIDUAL_WORK_ORDER_CREATED_BY = "residual_work_order_v1_controller"

NEXT_RECOMMENDED_ACTION = (
    "review_object_motion_causality_work_order_before_generation_authorization"
)

RESIDUAL_WORK_ORDER_ARTIFACT_TYPES = (
    "residual_work_order_subject_manifest",
    "residual_target_selection_intake",
    "current_candidate_region_inventory",
    "object_motion_causality_diagnostic",
    "target_diagnostic",
    "selected_intervention_region",
    "object_motion_target_unit_map",
    "target_unit_map",
    "target_novelty_distinctness_report",
    "protected_effects_and_forbidden_changes",
    "future_generation_contract",
    "ablation_and_reader_eval_plan",
    "residual_work_order_gate_report",
    "residual_work_order_packet",
)

REQUIRED_SELECTION_ARTIFACTS = (
    "residual_target_selection_packet",
    "operator_residual_target_choice",
    "available_residual_options_report",
    "strategy_packet_intake_summary",
    "selected_residual_target_contract",
    "protected_effects_and_forbidden_changes",
    "next_work_order_scope",
    "residual_target_selection_gate_report",
)


@dataclass(frozen=True)
class ResidualWorkOrderResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class CandidateText:
    packet_id: str
    packet_dir: Path
    artifact_id: str | None
    text: str
    text_sha256: str
    word_count: int


@dataclass(frozen=True)
class ResidualWorkOrderSubject:
    run_id: str
    selection_packet_dir: Path
    selection_packet_id: str
    selection_packet_artifact_id: str | None
    selection_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    strategy_payloads: dict[str, dict[str, Any]]
    selected_target_id: str
    target_spec: ResidualTargetSpec
    selected_option: dict[str, Any]
    routing: dict[str, object]
    candidate: CandidateText
    source_parent_ids: tuple[str, ...]
    supersession: dict[str, object]


def run_residual_work_order_planning(
    config: AbiConfig,
    *,
    selection_packet: Path | str,
) -> ResidualWorkOrderResult:
    initialize_database(config)
    selection_packet_dir = _resolve_path(config, selection_packet)
    if not selection_packet_dir.exists() or not selection_packet_dir.is_dir():
        return _refusal(
            selection_packet=selection_packet_dir,
            message=(
                "Residual work-order planning refused; selection packet directory "
                f"not found: {selection_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, selection_packet_dir)
    except ValueError as error:
        return _refusal(selection_packet=selection_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                selection_packet=selection_packet_dir,
                message=(
                    "Residual work-order planning refused; run is not registered: "
                    f"{subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_RESIDUAL_WORK_ORDER_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "residual_work_order"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=RESIDUAL_WORK_ORDER_LINEAGE_ID,
            created_by=RESIDUAL_WORK_ORDER_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["residual_work_order_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir,
        )
        artifacts["residual_work_order_subject_manifest"] = writer.write_artifact(
            "residual_work_order_subject_manifest",
            payloads["residual_work_order_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["residual_target_selection_intake"] = _build_selection_intake(
            subject
        )
        artifacts["residual_target_selection_intake"] = writer.write_artifact(
            "residual_target_selection_intake",
            payloads["residual_target_selection_intake"],
            parent_ids=[
                artifacts["residual_work_order_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["current_candidate_region_inventory"] = _build_region_inventory(
            subject
        )
        artifacts["current_candidate_region_inventory"] = writer.write_artifact(
            "current_candidate_region_inventory",
            payloads["current_candidate_region_inventory"],
            parent_ids=[artifacts["residual_target_selection_intake"].id],
        )

        payloads["object_motion_causality_diagnostic"] = _build_diagnostic(
            subject,
            payloads["current_candidate_region_inventory"],
        )
        artifacts["object_motion_causality_diagnostic"] = writer.write_artifact(
            "object_motion_causality_diagnostic",
            payloads["object_motion_causality_diagnostic"],
            parent_ids=[artifacts["current_candidate_region_inventory"].id],
        )
        payloads["target_diagnostic"] = _build_generic_target_diagnostic(
            payloads["object_motion_causality_diagnostic"]
        )
        artifacts["target_diagnostic"] = writer.write_artifact(
            "target_diagnostic",
            payloads["target_diagnostic"],
            parent_ids=[artifacts["object_motion_causality_diagnostic"].id],
        )

        payloads["selected_intervention_region"] = _build_selected_region(
            subject,
            payloads["current_candidate_region_inventory"],
        )
        artifacts["selected_intervention_region"] = writer.write_artifact(
            "selected_intervention_region",
            payloads["selected_intervention_region"],
            parent_ids=[
                artifacts["current_candidate_region_inventory"].id,
                artifacts["object_motion_causality_diagnostic"].id,
                artifacts["target_diagnostic"].id,
            ],
        )

        payloads["object_motion_target_unit_map"] = _build_target_unit_map(
            subject,
            payloads["selected_intervention_region"],
        )
        artifacts["object_motion_target_unit_map"] = writer.write_artifact(
            "object_motion_target_unit_map",
            payloads["object_motion_target_unit_map"],
            parent_ids=[artifacts["selected_intervention_region"].id],
        )
        payloads["target_unit_map"] = _build_generic_target_unit_map(
            payloads["object_motion_target_unit_map"]
        )
        artifacts["target_unit_map"] = writer.write_artifact(
            "target_unit_map",
            payloads["target_unit_map"],
            parent_ids=[artifacts["object_motion_target_unit_map"].id],
        )

        payloads["target_novelty_distinctness_report"] = (
            _build_target_novelty_distinctness_report(
                subject,
                payloads["selected_intervention_region"],
                payloads["target_unit_map"],
            )
        )
        artifacts["target_novelty_distinctness_report"] = writer.write_artifact(
            "target_novelty_distinctness_report",
            payloads["target_novelty_distinctness_report"],
            parent_ids=[
                artifacts["selected_intervention_region"].id,
                artifacts["object_motion_target_unit_map"].id,
                artifacts["target_unit_map"].id,
            ],
        )

        payloads["protected_effects_and_forbidden_changes"] = (
            _build_protected_effects_and_forbidden_changes(subject)
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["residual_target_selection_intake"].id,
                artifacts["object_motion_target_unit_map"].id,
                artifacts["target_unit_map"].id,
                artifacts["target_novelty_distinctness_report"].id,
            ],
        )

        payloads["future_generation_contract"] = _build_future_generation_contract(
            subject,
            payloads["selected_intervention_region"],
            payloads["target_unit_map"],
        )
        artifacts["future_generation_contract"] = writer.write_artifact(
            "future_generation_contract",
            payloads["future_generation_contract"],
            parent_ids=[
                artifacts["selected_intervention_region"].id,
                artifacts["object_motion_target_unit_map"].id,
                artifacts["target_unit_map"].id,
                artifacts["target_novelty_distinctness_report"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["ablation_and_reader_eval_plan"] = _build_ablation_and_reader_eval_plan(
            subject
        )
        artifacts["ablation_and_reader_eval_plan"] = writer.write_artifact(
            "ablation_and_reader_eval_plan",
            payloads["ablation_and_reader_eval_plan"],
            parent_ids=[
                artifacts["future_generation_contract"].id,
                artifacts["object_motion_target_unit_map"].id,
                artifacts["target_unit_map"].id,
                artifacts["target_novelty_distinctness_report"].id,
            ],
        )

        payloads["residual_work_order_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["residual_work_order_gate_report"] = writer.write_artifact(
            "residual_work_order_gate_report",
            payloads["residual_work_order_gate_report"],
            parent_ids=[
                artifacts["residual_target_selection_intake"].id,
                artifacts["selected_intervention_region"].id,
                artifacts["future_generation_contract"].id,
                artifacts["ablation_and_reader_eval_plan"].id,
                artifacts["target_novelty_distinctness_report"].id,
            ],
        )

        payloads["residual_work_order_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["residual_work_order_packet"] = writer.write_artifact(
            "residual_work_order_packet",
            payloads["residual_work_order_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "residual_work_order_packet"
            ],
        )

        gate_report = payloads["residual_work_order_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="residual_work_order_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=RESIDUAL_WORK_ORDER_LINEAGE_ID,
        )

    return ResidualWorkOrderResult(
        exit_code=0,
        payload=_result_payload(
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(config: AbiConfig, selection_packet_dir: Path) -> ResidualWorkOrderSubject:
    payloads = _load_required_payloads(selection_packet_dir)
    selection_packet = payloads["residual_target_selection_packet"]
    run_id = selection_packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Residual work-order planning refused; selection packet missing run_id.")
    target_spec, routing = _validate_selection_payloads(config, payloads)
    strategy_payloads = _load_strategy_payloads(config, payloads)
    selected_option = _selected_strategy_option(
        strategy_payloads,
        str(selection_packet.get("selected_residual_target_id") or ""),
    )
    if selected_option is None:
        raise ValueError(
            "Residual work-order planning refused; selected target is absent "
            "from the source strategy residual options."
        )
    candidate = _load_candidate_text(config, run_id, payloads)

    packet_path = selection_packet_dir / "residual_target_selection_packet.json"
    with connect(config.db_path) as connection:
        selection_artifact = _artifact_for_path(connection, packet_path)
        candidate_artifact = _artifact_for_path(
            connection,
            candidate.packet_dir / "macro_recomposed_candidate_text.json",
        )
    selection_artifact_ids = _artifact_ids_from_packet(selection_packet)
    parent_ids = _unique(
        [
            selection_artifact.id if selection_artifact else None,
            candidate_artifact.id if candidate_artifact else None,
            *selection_artifact_ids.values(),
        ]
    )
    supersession = _work_order_supersession_context(
        config=config,
        run_id=run_id,
        source_selection_packet_id=str(
            selection_packet.get("packet_id") or selection_packet_dir.name
        ),
        target_id=target_spec.target_id,
    )
    if supersession.get("supersession_reason") == "prior current-valid work order already exists":
        raise ValueError(
            "Residual work-order planning refused; a current-valid work order "
            "already exists for this selection packet."
        )
    subject = ResidualWorkOrderSubject(
        run_id=run_id,
        selection_packet_dir=selection_packet_dir,
        selection_packet_id=str(
            selection_packet.get("packet_id") or selection_packet_dir.name
        ),
        selection_packet_artifact_id=selection_artifact.id
        if selection_artifact
        else None,
        selection_artifact_ids=selection_artifact_ids,
        payloads=payloads,
        strategy_payloads=strategy_payloads,
        selected_target_id=target_spec.target_id,
        target_spec=target_spec,
        selected_option=selected_option,
        routing=routing,
        candidate=candidate,
        source_parent_ids=tuple(parent_ids),
        supersession=supersession,
    )
    _prevalidate_target_adapter(subject)
    return subject


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_SELECTION_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Residual work-order planning refused; selection packet missing "
                f"{path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Residual work-order planning refused; malformed selection artifact: "
                f"{path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_selection_payloads(
    config: AbiConfig,
    payloads: dict[str, dict[str, Any]],
) -> tuple[ResidualTargetSpec, dict[str, object]]:
    selection_packet = payloads["residual_target_selection_packet"]
    scope = payloads["next_work_order_scope"]
    contract = payloads["selected_residual_target_contract"]
    gate = payloads["residual_target_selection_gate_report"]
    choice = payloads["operator_residual_target_choice"]
    selected_target = selection_packet.get("selected_residual_target_id")
    if not isinstance(selected_target, str) or not selected_target:
        raise ValueError(
            "Residual work-order planning refused; selected residual target is missing."
        )
    target_spec = get_residual_target_spec(selected_target)
    if target_spec is None:
        raise ValueError(
            "Residual work-order planning refused; unsupported selected "
            f"residual target: {selected_target}"
        )
    if selection_packet.get("candidate_generation_authorized") is True:
        raise ValueError(
            "Residual work-order planning refused; candidate generation is already "
            "authorized by the selection packet."
        )
    if scope.get("candidate_generation_authorized") is True:
        raise ValueError(
            "Residual work-order planning refused; next work-order scope "
            "authorizes candidate generation."
        )
    if selection_packet.get("next_strategy_or_work_order_authorized") is not True:
        raise ValueError(
            "Residual work-order planning refused; selection packet does not "
            "authorize a strategy/work-order step."
        )
    if scope.get("next_strategy_or_work_order_authorized") is not True:
        raise ValueError(
            "Residual work-order planning refused; next work-order scope does not "
            "authorize work-order planning."
        )
    if contract.get("selected_residual_target_id") != selected_target:
        raise ValueError(
            "Residual work-order planning refused; selected target contract does "
            "not match the selection packet."
        )
    if choice.get("selected_residual_target_id") != selected_target:
        raise ValueError(
            "Residual work-order planning refused; operator choice does not "
            "match the selection packet."
        )
    if _has_final_or_phase_shift_claim(selection_packet) or _has_final_or_phase_shift_claim(gate):
        raise ValueError(
            "Residual work-order planning refused; selection packet carries a "
            "finality or phase-shift claim."
        )
    routing = _selection_routing_report(config, payloads, target_spec)
    if (
        routing["stale_selection_routing_detected"] is True
        and routing["stale_selection_routing_safely_normalized"] is not True
    ):
        raise ValueError(
            "Residual work-order planning refused; stale selection routing "
            "could not be safely normalized."
        )
    return target_spec, routing


def _load_strategy_payloads(
    config: AbiConfig,
    payloads: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    intake = payloads["strategy_packet_intake_summary"]
    strategy_dir_value = intake.get("strategy_packet_dir")
    if not isinstance(strategy_dir_value, str) or not strategy_dir_value:
        raise ValueError(
            "Residual work-order planning refused; source strategy packet dir "
            "is missing."
        )
    strategy_dir = _resolve_path(config, strategy_dir_value)
    required = (
        "next_target_strategy_packet",
        "residual_target_option_map",
        "candidate_region_pressure_map",
    )
    result: dict[str, dict[str, Any]] = {}
    for artifact_type in required:
        path = strategy_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Residual work-order planning refused; source strategy packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            raise ValueError(
                "Residual work-order planning refused; malformed strategy "
                f"artifact: {path.name}."
            )
        result[artifact_type] = payload
    return result


def _selected_strategy_option(
    strategy_payloads: dict[str, dict[str, Any]],
    selected_target_id: str,
) -> dict[str, Any] | None:
    residual_map = strategy_payloads["residual_target_option_map"]
    options = residual_map.get("specific_residual_options")
    if not isinstance(options, list):
        return None
    for option in options:
        if isinstance(option, dict) and option.get("option_id") == selected_target_id:
            return option
    return None


def _selection_routing_report(
    config: AbiConfig,
    payloads: dict[str, dict[str, Any]],
    target_spec: ResidualTargetSpec,
) -> dict[str, object]:
    del config
    selection_packet = payloads["residual_target_selection_packet"]
    scope = payloads["next_work_order_scope"]
    choice = payloads["operator_residual_target_choice"]
    old_action = _first_string(
        selection_packet.get("next_allowed_action"),
        selection_packet.get("next_recommended_action"),
        scope.get("next_allowed_action"),
    )
    stale_detected = bool(old_action and old_action != target_spec.canonical_next_action)
    safely_normalized = (
        not stale_detected
        or (
            choice.get("selected_residual_target_id") == target_spec.target_id
            and selection_packet.get("selected_residual_target_id") == target_spec.target_id
            and scope.get("selected_residual_target_id") == target_spec.target_id
        )
    )
    return {
        "stale_selection_routing_detected": stale_detected,
        "stale_next_action_ignored": old_action if stale_detected else None,
        "canonical_next_action": target_spec.canonical_next_action,
        "routing_normalized_from_selected_target": stale_detected
        and safely_normalized,
        "stale_selection_routing_safely_normalized": safely_normalized,
        "stale_strategy_current_best_reference_detected": bool(
            selection_packet.get("stale_strategy_current_best_reference_detected")
        ),
        "stale_reference_packet_id": selection_packet.get("stale_reference_packet_id"),
        "stale_reference_packet_ids": selection_packet.get(
            "stale_reference_packet_ids",
            [],
        ),
        "authoritative_current_best_packet_id": selection_packet.get(
            "authoritative_current_best_packet_id"
        )
        or selection_packet.get("current_best_candidate_packet_id"),
    }


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _has_final_or_phase_shift_claim(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("finalization_eligible") is True
        or payload.get("phase_shift_claim") is True
        or payload.get("no_phase_shift_claim") is False
        or payload.get("no_final_claim") is False
    )


def _load_candidate_text(
    config: AbiConfig,
    run_id: str,
    payloads: dict[str, dict[str, Any]],
) -> CandidateText:
    selection_packet = payloads["residual_target_selection_packet"]
    current_best_id = selection_packet.get("current_best_candidate_packet_id")
    if not isinstance(current_best_id, str) or not current_best_id:
        raise ValueError(
            "Residual work-order planning refused; current best candidate is missing."
        )
    candidate_dir = _candidate_packet_dir(config, run_id, payloads, current_best_id)
    if candidate_dir is None or not candidate_dir.exists():
        raise ValueError(
            "Residual work-order planning refused; current best candidate packet "
            f"cannot be resolved: {current_best_id}"
        )
    text_path = candidate_dir / "macro_recomposed_candidate_text.json"
    if not text_path.exists():
        raise ValueError(
            "Residual work-order planning refused; packet text cannot be loaded "
            f"for {current_best_id}."
        )
    envelope = read_json_file(text_path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError(
            "Residual work-order planning refused; malformed candidate text "
            f"artifact for {current_best_id}."
        )
    text = str(payload["text"])
    text_sha256 = str(payload.get("text_sha256") or sha256_text(text))
    return CandidateText(
        packet_id=current_best_id,
        packet_dir=candidate_dir,
        artifact_id=None,
        text=text,
        text_sha256=text_sha256,
        word_count=int(payload.get("word_count") or len(text.split())),
    )


def _candidate_packet_dir(
    config: AbiConfig,
    run_id: str,
    payloads: dict[str, dict[str, Any]],
    current_best_id: str,
) -> Path | None:
    intake = payloads["strategy_packet_intake_summary"]
    strategy_dir_value = intake.get("strategy_packet_dir")
    if isinstance(strategy_dir_value, str) and strategy_dir_value:
        strategy_dir = _resolve_path(config, strategy_dir_value)
        strategy_packet_path = strategy_dir / "next_target_strategy_packet.json"
        if strategy_packet_path.exists():
            envelope = read_json_file(strategy_packet_path)
            payload = envelope.get("payload") if isinstance(envelope, dict) else None
            if isinstance(payload, dict):
                current_best = payload.get("current_best_candidate")
                if isinstance(current_best, dict):
                    packet_dir = current_best.get("packet_dir")
                    packet_id = current_best.get("packet_id")
                    if packet_id == current_best_id and isinstance(packet_dir, str):
                        return _resolve_path(config, packet_dir)
    fallback = config.run_dir(run_id) / "bounded_macro_recomposition" / current_best_id
    return fallback if fallback.exists() else None


def _work_order_supersession_context(
    *,
    config: AbiConfig,
    run_id: str,
    source_selection_packet_id: str,
    target_id: str,
) -> dict[str, object]:
    root = config.run_dir(run_id) / "residual_work_order"
    base = {
        "superseded_work_order_packet_id": None,
        "supersession_reason": None,
        "semantic_preflight_failures": [],
        "new_canonical_work_order_packet_id": None,
        "supersedes_semantically_stale_work_order": False,
    }
    if not root.exists():
        return base
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for packet_dir in sorted(root.glob("packet_*")):
        packet_path = packet_dir / "residual_work_order_packet.json"
        if not packet_path.exists():
            continue
        try:
            envelope = read_json_file(packet_path)
        except (OSError, ValueError):
            continue
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        if payload.get("source_selection_packet_id") != source_selection_packet_id:
            continue
        if payload.get("selected_residual_target_id") != target_id:
            continue
        candidates.append((str(payload.get("packet_id") or packet_dir.name), packet_dir, payload))
    if not candidates:
        return base
    for packet_id, packet_dir, _payload in reversed(candidates):
        try:
            payloads = {
                artifact_type: read_json_file(packet_dir / f"{artifact_type}.json")[
                    "payload"
                ]
                for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
                if (packet_dir / f"{artifact_type}.json").exists()
            }
        except (OSError, ValueError, KeyError, TypeError):
            continue
        handoff_failures = _generation_handoff_metadata_failures(
            payloads,
            target_id=target_id,
        )
        if handoff_failures:
            supersession_reason = "prior work order generation handoff metadata is stale"
            if target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
                supersession_reason = "ending_return_generation_handoff_metadata_missing"
            if target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
                supersession_reason = "proof_no_answer_generation_handoff_metadata_missing"
            return {
                **base,
                "superseded_work_order_packet_id": packet_id,
                "supersession_reason": supersession_reason,
                "semantic_preflight_failures": handoff_failures,
                "new_canonical_work_order_packet_id": "assigned_after_packet_creation",
                "supersedes_semantically_stale_work_order": True,
            }
        failures = semantic_preflight_failures_for_work_order(payloads)
        if failures:
            supersession_reason = (
                "out_of_region_target_units_in_single_region_work_order"
                if any(
                    "out_of_region_target_units_in_single_region_work_order" in failure
                    for failure in failures
                )
                else "prior work order failed current target-adapter semantic preflight"
            )
            return {
                **base,
                "superseded_work_order_packet_id": packet_id,
                "supersession_reason": supersession_reason,
                "semantic_preflight_failures": failures,
                "new_canonical_work_order_packet_id": "assigned_after_packet_creation",
                "supersedes_semantically_stale_work_order": True,
            }
        return {
            **base,
            "supersession_reason": "prior current-valid work order already exists",
            "semantic_preflight_failures": [],
        }
    return base


def _generation_handoff_metadata_failures(
    payloads: dict[str, dict[str, Any]],
    *,
    target_id: str,
) -> list[str]:
    if target_id not in {
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
        PROOF_NO_ANSWER_RESIDUE_TARGET_ID,
    }:
        return []
    failures: list[str] = []
    for artifact_type, payload in payloads.items():
        if payload_has_placeholder_generation_contract(payload):
            failures.append(f"{artifact_type} uses placeholder generation metadata")
    packet = payloads.get("residual_work_order_packet", {})
    contract = payloads.get("future_generation_contract", {})
    unit_map = payloads.get("target_unit_map") or payloads.get(
        "object_motion_target_unit_map", {}
    )
    plan = payloads.get("ablation_and_reader_eval_plan", {})
    for name, payload in (
        ("residual_work_order_packet", packet),
        ("future_generation_contract", contract),
        ("target_unit_map", unit_map),
    ):
        if payload.get("future_generation_authorized") is not False:
            failures.append(f"{name} missing future_generation_authorized false")
    if not isinstance(unit_map.get("target_unit_overlap_cluster_report"), dict):
        failures.append("target_unit_map missing overlap cluster report")
    if not isinstance(contract.get("target_unit_overlap_cluster_report"), dict):
        failures.append("future_generation_contract missing overlap cluster report")
    if target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        required_controls = {
            "full_proof_no_answer_residue_intervention",
            "revert_proof_no_answer_residue_to_current_best",
            "isolate_object_carry_without_outside_answer",
            "abstract_proof_language_control",
            "outside_answer_intrusion_control",
            "strongest_rival_comparison",
        }
        required_focus = {
            "proof/no-answer pressure embodied",
            "outside-answer absence preserved",
            "object field carries proof",
            "thesis visibility reduced",
            "first-read clarity without explanation",
            "reread carry preserved",
            "strongest-rival pressure",
        }
        target_label = "proof/no-answer"
    else:
        required_controls = {
            "full_ending_return_intervention",
            "revert_ending_return_intervention_to_current_best",
            "isolate_return_enactment_without_extra_explanation",
            "proof_no_answer_preservation_control",
            "object_field_return_preservation_control",
            "strongest_rival_comparison",
        }
        required_focus = {
            "final return enacts rather than explains",
            "opening-return transformation",
            "no-reset return pressure",
            "proof/no-answer carry preservation",
            "object-field return preservation",
            "reread transformation",
            "strongest-rival pressure",
        }
        target_label = "ending-return"
    controls = set(str(value) for value in contract.get("target_specific_ablation_controls", []))
    controls.update(str(value) for value in plan.get("future_ablation_controls", []))
    missing_controls = sorted(required_controls - controls)
    if missing_controls:
        failures.append(
            f"{target_label} ablation controls missing: "
            + ", ".join(missing_controls)
        )
    if target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        overlap_report = unit_map.get("target_unit_overlap_cluster_report")
        if (
            not isinstance(overlap_report, dict)
            or int(overlap_report.get("overlap_cluster_count") or 0) < 1
        ):
            failures.append("proof/no-answer overlap cluster report missing clusters")
        if contract.get("semantic_validator_id") != (
            "proof_no_answer_residue_semantic_validator_v1"
        ):
            failures.append("proof/no-answer semantic validator missing from contract")
        if unit_map.get("semantic_validator_id") != (
            "proof_no_answer_residue_semantic_validator_v1"
        ):
            failures.append("proof/no-answer semantic validator missing from target unit map")
        if contract.get("prompt_contract_id") != (
            "autonomous.residual_intervention_generation.v1.proof_no_answer_residue"
        ):
            failures.append("proof/no-answer prompt contract missing from contract")
        if contract.get("generation_schema_name") != "ResidualInterventionGenerationOutput":
            failures.append("proof/no-answer generation schema name missing from contract")
        if contract.get("generation_schema_version") != "1":
            failures.append("proof/no-answer generation schema version missing from contract")
        failures.extend(
            _proof_no_answer_evidence_handoff_metadata_failures(
                packet=packet,
                contract=contract,
                plan=plan,
                required_controls=required_controls,
                required_focus=required_focus,
            )
        )
    focus = set(str(value) for value in contract.get("target_specific_reader_state_focus", []))
    focus.update(str(value) for value in plan.get("future_reader_state_eval_focus", []))
    missing_focus = sorted(required_focus - focus)
    if missing_focus:
        failures.append(
            f"{target_label} reader-state focus missing: " + ", ".join(missing_focus)
        )
    return failures


def _proof_no_answer_evidence_handoff_metadata_failures(
    *,
    packet: dict[str, Any],
    contract: dict[str, Any],
    plan: dict[str, Any],
    required_controls: set[str],
    required_focus: set[str],
) -> list[str]:
    failures: list[str] = []
    failures.extend(
        _required_metadata_field_failures(
            packet,
            fields=("ablation_controls", "target_specific_ablation_controls"),
            required_values=required_controls,
            label="residual_work_order_packet proof/no-answer ablation controls",
        )
    )
    failures.extend(
        _required_metadata_field_failures(
            packet,
            fields=(
                "reader_state_focus",
                "reader_state_evaluation_focus",
                "target_specific_reader_state_focus",
            ),
            required_values=required_focus,
            label="residual_work_order_packet proof/no-answer reader-state focus",
        )
    )
    failures.extend(
        _required_metadata_field_failures(
            contract,
            fields=("ablation_controls", "target_specific_ablation_controls"),
            required_values=required_controls,
            label="future_generation_contract proof/no-answer ablation controls",
        )
    )
    failures.extend(
        _required_metadata_field_failures(
            contract,
            fields=(
                "reader_state_focus",
                "reader_state_evaluation_focus",
                "target_specific_reader_state_focus",
            ),
            required_values=required_focus,
            label="future_generation_contract proof/no-answer reader-state focus",
        )
    )
    failures.extend(
        _required_metadata_field_failures(
            plan,
            fields=(
                "ablation_controls",
                "target_specific_ablation_controls",
                "future_ablation_controls",
            ),
            required_values=required_controls,
            label="ablation_and_reader_eval_plan proof/no-answer ablation controls",
        )
    )
    failures.extend(
        _required_metadata_field_failures(
            plan,
            fields=(
                "reader_state_focus",
                "reader_state_evaluation_focus",
                "target_specific_reader_state_focus",
                "future_reader_state_eval_focus",
            ),
            required_values=required_focus,
            label="ablation_and_reader_eval_plan proof/no-answer reader-state focus",
        )
    )
    return failures


def _required_metadata_field_failures(
    payload: dict[str, Any],
    *,
    fields: tuple[str, ...],
    required_values: set[str],
    label: str,
) -> list[str]:
    failures: list[str] = []
    for field in fields:
        values = {
            str(value)
            for value in payload.get(field, [])
            if isinstance(value, str) and value
        }
        missing = sorted(required_values - values)
        if missing:
            failures.append(
                f"{label} field {field} missing: " + ", ".join(missing)
            )
    return failures


def _build_subject_manifest(
    subject: ResidualWorkOrderSubject,
    packet_dir: Path,
) -> dict[str, object]:
    selection = subject.payloads["residual_target_selection_packet"]
    intake = subject.payloads["strategy_packet_intake_summary"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_selection_packet_id": subject.selection_packet_id,
        "source_selection_packet_dir": str(subject.selection_packet_dir),
        "source_selection_packet_artifact_id": subject.selection_packet_artifact_id,
        "source_strategy_packet_id": selection.get("source_strategy_packet_id")
        or intake.get("strategy_packet_id"),
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "current_best_candidate_packet_dir": str(subject.candidate.packet_dir),
        "candidate_text_sha256": subject.candidate.text_sha256,
        "candidate_word_count": subject.candidate.word_count,
        "proof_packet_id": selection.get("proof_packet_id"),
        "reader_state_packet_id": selection.get("reader_state_packet_id"),
        "source_synthesis_packet_id": intake.get("source_synthesis_packet_id"),
        "loop_review_packet_id": intake.get("loop_review_packet_id"),
        "selected_residual_target_id": subject.selected_target_id,
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "work_order_adapter": subject.target_spec.work_order_adapter,
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": _selected_region_id(subject),
        **subject.supersession,
        "new_canonical_work_order_packet_id": (
            packet_dir.name
            if subject.supersession.get("supersedes_semantically_stale_work_order") is True
            else subject.supersession.get("new_canonical_work_order_packet_id")
        ),
        **subject.routing,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "residual_work_order_subject_manifest_v1_controller",
    }


def _build_selection_intake(subject: ResidualWorkOrderSubject) -> dict[str, object]:
    selection = subject.payloads["residual_target_selection_packet"]
    scope = subject.payloads["next_work_order_scope"]
    return {
        "selection_packet_consumed": True,
        "selection_packet_id": subject.selection_packet_id,
        "selection_packet_dir": str(subject.selection_packet_dir),
        "selected_residual_target_id": subject.selected_target_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "proof_packet_id": selection.get("proof_packet_id"),
        "reader_state_packet_id": selection.get("reader_state_packet_id"),
        "broad_blocker_class": selection.get("broad_blocker_class"),
        "next_allowed_action": scope.get("next_allowed_action"),
        "canonical_next_action": subject.target_spec.canonical_next_action,
        **subject.routing,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "next_strategy_or_work_order_authorized": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "residual_target_selection_intake_v1_controller",
    }


def _build_region_inventory(subject: ResidualWorkOrderSubject) -> dict[str, object]:
    paragraphs = _paragraphs(subject.candidate.text)
    final_return_start = 10 if len(paragraphs) > 10 else max(len(paragraphs) - 1, 0)
    regions = [
        _region(
            region_id="opening_table_dust_spoon_saucer_ring_field",
            paragraphs=paragraphs,
            start=0,
            end=2,
            function="establishes the record-bearing table/object field",
            protected_effects=[
                "opening table/dust/spoon/saucer/ring field",
                "ordinary record without overt explanation",
            ],
            modification_risk="high: opening carries the first record field",
            eligible=False,
            reason="protect unless later evidence selects a very narrow unit",
        ),
        _region(
            region_id=SELECTED_REGION_ID,
            paragraphs=paragraphs,
            start=3,
            end=4,
            function="turns ordinary recurrence into local cause and consequence",
            protected_effects=[
                "object relation pressure",
                "partial reread transformation",
                "reduced overexplanation",
            ],
            modification_risk=(
                "medium: strongest candidate region, but it could become busier "
                "local detail"
            ),
            eligible=True,
            reason=(
                "strategy evidence marks this as the plausible bounded region "
                "for first-read object-event pressure"
            ),
        ),
        _region(
            region_id=PROOF_NO_ANSWER_REGION_ID,
            paragraphs=paragraphs,
            start=8,
            end=9,
            function="keeps proof/no-outside-answer pressure inside the room",
            protected_effects=[
                "proof/no-answer gains",
                "no external answer enters",
            ],
            modification_risk="high: may slide back into proof compression",
            eligible=subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID,
            reason=(
                "operator-reviewed direction review selected proof/no-answer residue"
                if subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID
                else "protect from renewed proof/no-answer compression by inertia"
            ),
        ),
        _region(
            region_id="final_return_opening_transformation_region",
            paragraphs=paragraphs,
            start=final_return_start,
            end=final_return_start,
            function="returns to opening field with altered relation",
            protected_effects=[
                "final-return gains",
                "opening transformed by return",
            ],
            modification_risk="high: final return could become overworked or explanatory",
            eligible=False,
            reason="protect unless future evidence selects a narrow return unit",
        ),
    ]
    return {
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "candidate_text_sha256": subject.candidate.text_sha256,
        "regions": regions,
        "region_count": len(regions),
        "selected_region_candidate": _selected_region_id(subject),
        "selected_residual_target_id": subject.selected_target_id,
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "current_candidate_region_inventory_v1_controller",
    }


def _region(
    *,
    region_id: str,
    paragraphs: list[str],
    start: int,
    end: int,
    function: str,
    protected_effects: list[str],
    modification_risk: str,
    eligible: bool,
    reason: str,
) -> dict[str, object]:
    selected = paragraphs[start : end + 1]
    text = "\n\n".join(selected)
    return {
        "region_id": region_id,
        "paragraph_refs": [f"p{index + 1}" for index in range(start, end + 1)],
        "text_excerpt": _excerpt(text),
        "region_text_sha256": sha256_text(text),
        "function_in_current_candidate": function,
        "protected_effects": protected_effects,
        "modification_risk": modification_risk,
        "eligible_for_object_motion_causality_specificity_work": eligible,
        "eligible_for_tactile_inevitability_gap_work": eligible,
        "eligible_for_hostile_scaffold_visibility_work": eligible,
        "eligible_for_ending_explains_return_risk_work": (
            region_id == ENDING_RETURN_REGION_ID
        ),
        "eligible_for_proof_no_answer_residue_work": (
            region_id == PROOF_NO_ANSWER_REGION_ID and eligible
        ),
        "reason": reason,
    }


def _build_diagnostic(
    subject: ResidualWorkOrderSubject,
    inventory: dict[str, object],
) -> dict[str, object]:
    selected_region = _find_region(inventory, _selected_region_id(subject))
    if subject.selected_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        return {
            "selected_residual_target_id": subject.selected_target_id,
            "current_best_candidate_packet_id": subject.candidate.packet_id,
            "diagnostic_findings": [
                {
                    "category": "tactile_force_or_contact_relation",
                    "status": "candidate_region_contains_material relations",
                    "evidence": _tactile_evidence_sentences(
                        str(selected_region.get("text_excerpt") or "")
                    ),
                },
                {
                    "category": "distinct_from_object_motion_causality",
                    "status": "requires force/contact necessity rather than another motion pass",
                    "evidence": [
                        "object-motion causality has already been attempted",
                        "new work must preserve motion-to-consequence while adding physical non-optionality",
                    ],
                },
                {
                    "category": "generic_vividness_risk",
                    "status": "blocking_if_future_work_adds_sensory_adjectives_only",
                    "evidence": ["tactile inevitability is material force, not atmosphere"],
                },
                {
                    "category": "rival_mimicry_risk",
                    "status": "blocking_pressure_preserved",
                    "evidence": ["strongest rival remains pressure, not a template"],
                },
            ],
            "likely_strongest_candidate_region": SELECTED_REGION_ID,
            "selected_region_text_excerpt": selected_region.get("text_excerpt"),
            "opening_and_final_return_protection": (
                "opening and final return should remain protected unless a later "
                "authorization selects a narrower unit"
            ),
            "proof_no_answer_region_protection": (
                "proof/no-answer region should be protected from renewed proof compression"
            ),
            "summary": (
                "Middle recurrence / ordinary trace logic is the bounded candidate "
                "region for tactile inevitability because strategy evidence points "
                "there and the region already carries material traces."
            ),
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "worker": "tactile_inevitability_diagnostic_v1_controller",
        }
    if subject.selected_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return {
            "selected_residual_target_id": subject.selected_target_id,
            "diagnostic_kind": "hostile_scaffold_visibility_diagnostic",
            "legacy_artifact_name": "object_motion_causality_diagnostic",
            "artifact_name_compatibility_reason": (
                "residual work-order packet contract still expects this artifact "
                "filename; target_adapter_id and diagnostic_kind are authoritative"
            ),
            "current_best_candidate_packet_id": subject.candidate.packet_id,
            "diagnostic_findings": [
                {
                    "category": "overexplanation",
                    "status": "active_scaffold_visibility_risk",
                    "evidence": _selected_option_evidence(subject)
                    or ["reader-state synthesis still marks scaffold pressure active"],
                },
                {
                    "category": "thesis_replacing_artifact",
                    "status": "active_hostile_reader_risk",
                    "evidence": [
                        "future work must let field relations carry meaning before thesis language",
                    ],
                },
                {
                    "category": "cosmic_silence_as_slogan",
                    "status": "risk_to_reduce_without_deleting_no_answer_pressure",
                    "evidence": [
                        "proof/no-answer pressure remains partial and can become stated rather than embodied",
                    ],
                },
                {
                    "category": "proof_no_outside_answer_refinement",
                    "status": "partial_protected_gain",
                    "evidence": [
                        "proof/no-answer carry should remain inside objects, not be flattened into explanation",
                    ],
                },
                {
                    "category": "final_return_echo_reread_strength",
                    "status": "partial_protected_gain",
                    "evidence": [
                        "opening-return relation should be preserved without closing explanation",
                    ],
                },
                {
                    "category": "strongest_rival_first_read_vividness",
                    "status": "blocking_pressure_preserved",
                    "evidence": [
                        "strongest rival still wins first-read vividness/local embodiment",
                    ],
                },
                {
                    "category": "local_embodiment_vs_compression_balance",
                    "status": "target_must_preserve_embodiment",
                    "evidence": [
                        "reduce scaffold without compressing record/law/proof/answer into summary",
                    ],
                },
            ],
            "likely_strongest_candidate_region": SELECTED_REGION_ID,
            "selected_region_text_excerpt": selected_region.get("text_excerpt"),
            "opening_and_final_return_protection": (
                "opening field and final return are protected; only narrow scaffold "
                "visibility units may be prepared for later generation authorization"
            ),
            "proof_no_answer_region_protection": (
                "proof/no-answer pressure must be preserved as embodied pressure, "
                "not deleted or made more abstract"
            ),
            "summary": (
                "Hostile scaffold visibility targets visible explanatory pressure "
                "while preserving packet current-best object field, proof/no-answer, "
                "and reread gains."
            ),
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "worker": "hostile_scaffold_visibility_diagnostic_v1_controller",
        }
    if subject.selected_target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
        return {
            "selected_residual_target_id": subject.selected_target_id,
            "diagnostic_kind": "ending_explains_return_risk_diagnostic",
            "legacy_artifact_name": "object_motion_causality_diagnostic",
            "artifact_name_compatibility_reason": (
                "residual work-order packet contract still expects this artifact "
                "filename; target_adapter_id and diagnostic_kind are authoritative"
            ),
            "current_best_candidate_packet_id": subject.candidate.packet_id,
            "diagnostic_findings": [
                {
                    "category": "final_return_explains_rather_than_enacts",
                    "status": "active_return_risk",
                    "evidence": _selected_option_evidence(subject)
                    or ["final return remains improved but unproven"],
                },
                {
                    "category": "opening_return_relation",
                    "status": "must_transform_without_thesis",
                    "evidence": [
                        "future work must let the final return alter the opening relation through the field"
                    ],
                },
                {
                    "category": "proof_no_answer_carry",
                    "status": "protected_pressure_to_preserve",
                    "evidence": [
                        "proof/no-answer pressure must carry into return without becoming an answer"
                    ],
                },
                {
                    "category": "middle_recurrence_protection",
                    "status": "not_selected_by_inertia",
                    "evidence": [
                        "middle object-event/tactile gains are protected reference material"
                    ],
                },
                {
                    "category": "strongest_rival_pressure",
                    "status": "blocking_pressure_preserved",
                    "evidence": ["strongest rival remains pressure, not defeated evidence"],
                },
            ],
            "likely_strongest_candidate_region": ENDING_RETURN_REGION_ID,
            "selected_region_text_excerpt": selected_region.get("text_excerpt"),
            "middle_recurrence_protection": (
                "middle recurrence is protected reference material for this target; "
                "it is not selected again by inertia"
            ),
            "proof_no_answer_region_protection": (
                "proof/no-answer pressure is protected outside the selected ending region"
            ),
            "summary": (
                "Ending-return risk targets the final-return region so the ending "
                "can enact, rather than explain, the opening transformation."
            ),
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "worker": "ending_explains_return_risk_diagnostic_v1_controller",
        }
    if subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        return {
            "selected_residual_target_id": subject.selected_target_id,
            "diagnostic_kind": "proof_no_answer_residue_diagnostic",
            "legacy_artifact_name": "object_motion_causality_diagnostic",
            "artifact_name_compatibility_reason": (
                "residual work-order packet contract still expects this artifact "
                "filename; target_adapter_id and diagnostic_kind are authoritative"
            ),
            "current_best_candidate_packet_id": subject.candidate.packet_id,
            "diagnostic_findings": [
                {
                    "category": "proof_no_answer_residue",
                    "status": "active_checkpoint_direction",
                    "evidence": _selected_option_evidence(subject)
                    or ["direction review selected proof/no-answer residue"],
                },
                {
                    "category": "outside_answer_absence",
                    "status": "must_remain_pressure_not_explanation",
                    "evidence": [
                        "future work must not import an outside answer or elder-presence explanation"
                    ],
                },
                {
                    "category": "object_field_carries_proof",
                    "status": "must_preserve_object_tactile_gains",
                    "evidence": [
                        "table/dust/spoon/saucer/ring field remains protected context"
                    ],
                },
                {
                    "category": "strongest_rival_pressure",
                    "status": "blocking_pressure_preserved",
                    "evidence": ["strongest rival remains pressure, not defeated evidence"],
                },
            ],
            "likely_strongest_candidate_region": PROOF_NO_ANSWER_REGION_ID,
            "selected_region_text_excerpt": selected_region.get("text_excerpt"),
            "opening_middle_final_return_protection": (
                "opening, middle recurrence, and final-return material are "
                "protected reference units outside the proof/no-answer region"
            ),
            "summary": (
                "Proof/no-answer residue targets the proof/no-outside-answer "
                "region so future work can embody pressure without turning it "
                "into abstract thesis or explanation."
            ),
            "candidate_generated": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "worker": "proof_no_answer_residue_diagnostic_v1_controller",
        }
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "diagnostic_findings": [
            {
                "category": "object_motion_with_consequence",
                "status": "present_but_can_be_sharpened",
                "evidence": [
                    "A cup is placed and later lifted; ring and crumb change",
                    "spoon and saucer imply hand/drop/fall causality",
                ],
            },
            {
                "category": "object_state_without_motion",
                "status": "present",
                "evidence": [
                    "spoon lies on its side",
                    "saucer is cracked",
                    "ring holds memory of a glass",
                ],
            },
            {
                "category": "decorative_object_detail",
                "status": "risk_if_future_work_adds_busyness",
                "evidence": ["local object detail must change expectation, not decorate"],
            },
            {
                "category": "abstract_explanation_of_causality",
                "status": "risk_to_reduce",
                "evidence": [
                    "the candidate sometimes names the rule after showing it",
                    "future work should make consequence inferable before explanation",
                ],
            },
            {
                "category": "object_lists",
                "status": "risk_if_expanded",
                "evidence": ["table/dust/spoon/saucer/ring must remain causal, not listed"],
            },
            {
                "category": "rival_mimicry_risk",
                "status": "blocking_pressure_preserved",
                "evidence": ["future vividness must not copy rival identity or scene logic"],
            },
        ],
        "likely_strongest_candidate_region": SELECTED_REGION_ID,
        "selected_region_text_excerpt": selected_region.get("text_excerpt"),
        "opening_and_final_return_protection": (
            "opening and final return should remain protected unless a later "
            "authorization selects a narrower unit"
        ),
        "proof_no_answer_region_protection": (
            "proof/no-answer region should be protected from renewed proof compression"
        ),
        "summary": (
            "Middle recurrence / ordinary trace logic is the strongest candidate "
            "region, but future work must sharpen causality without adding busier "
            "local detail."
        ),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "object_motion_causality_diagnostic_v1_controller",
    }


def _build_generic_target_diagnostic(
    legacy_payload: dict[str, object],
) -> dict[str, object]:
    target_adapter_id = legacy_payload.get("target_adapter_id") or _target_adapter_id_for_target(
        legacy_payload
    )
    return {
        **legacy_payload,
        "artifact_type": GENERIC_TARGET_DIAGNOSTIC_ARTIFACT,
        "selected_residual_target_id": legacy_payload.get(
            "selected_residual_target_id"
        ),
        "target_adapter_id": target_adapter_id,
        "diagnostic_kind": legacy_payload.get("diagnostic_kind")
        or (
            f"{target_adapter_id}_diagnostic"
            if target_adapter_id
            else "object_motion_causality_diagnostic"
        ),
        "source_legacy_artifact_name": LEGACY_TARGET_DIAGNOSTIC_ARTIFACT,
        "legacy_alias_written": True,
        "consumer_should_prefer_generic_artifact": True,
        "no_phase_shift_claim": True,
        "finalization_eligible": False,
    }


def _build_generic_target_unit_map(
    legacy_payload: dict[str, object],
) -> dict[str, object]:
    target_adapter_id = legacy_payload.get("target_adapter_id") or _target_adapter_id_for_target(
        legacy_payload
    )
    generic: dict[str, object] = {
        **legacy_payload,
        "artifact_type": GENERIC_TARGET_UNIT_MAP_ARTIFACT,
        "selected_residual_target_id": legacy_payload.get(
            "selected_residual_target_id"
        ),
        "target_adapter_id": target_adapter_id,
        "unit_map_kind": legacy_payload.get("unit_map_kind")
        or target_adapter_id
        or "object_motion_causality",
        "source_legacy_artifact_name": LEGACY_TARGET_UNIT_MAP_ARTIFACT,
        "legacy_alias_written": True,
        "consumer_should_prefer_generic_artifact": True,
        "target_units": list(legacy_payload.get("target_units", []))
        if isinstance(legacy_payload.get("target_units"), list)
        else [],
        "protected_reference_units": list(
            legacy_payload.get("protected_reference_units", [])
        )
        if isinstance(legacy_payload.get("protected_reference_units"), list)
        else [],
        "no_phase_shift_claim": True,
        "finalization_eligible": False,
    }
    if "overlap_clusters" in legacy_payload:
        generic["overlap_clusters"] = legacy_payload["overlap_clusters"]
    return generic


def _target_adapter_id_for_target(payload: dict[str, object]) -> str | None:
    target_id = payload.get("selected_residual_target_id")
    if not isinstance(target_id, str) or not target_id:
        return None
    adapter_id = target_adapter_metadata(target_id).get("target_adapter_id")
    return adapter_id if isinstance(adapter_id, str) and adapter_id else None


def _build_selected_region(
    subject: ResidualWorkOrderSubject,
    inventory: dict[str, object],
) -> dict[str, object]:
    selected_region_id = _selected_region_id(subject)
    selected_region = _find_region(inventory, selected_region_id)
    selected_text = _region_text(subject.candidate.text, selected_region_id)
    if subject.selected_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        selection_reason = (
            "The strategy evidence marks this bounded middle recurrence region "
            "as plausible; it already contains material trace relations, and "
            "reopening it is less risky than reopening the opening, proof, or final return."
        )
    elif subject.selected_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        selection_reason = (
            "The strategy evidence marks visible scaffold/explanatory pressure as "
            "active. The middle recurrence region is the bounded planning anchor, "
            "with narrow proof and return units protected for later authorized work "
            "rather than broad rewrite."
        )
    elif subject.selected_target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
        selection_reason = (
            "The operator selected ending-return risk, so the bounded ending/final-return "
            "region is the editable planning scope. Opening, middle recurrence, and "
            "proof/no-answer material are protected references, not material target units."
        )
    elif subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        selection_reason = (
            "The operator-reviewed checkpoint direction selected proof/no-answer "
            "residue, so the proof/no-outside-answer region is the editable "
            "planning scope. Opening, middle recurrence, and final-return material "
            "are protected references, not material target units."
        )
    else:
        selection_reason = (
            "This region already contains object motion and implied consequence; "
            "it is the narrowest bounded place to sharpen causality before explanation."
        )
    return {
        "selected_region_id": selected_region_id,
        "selected_region_before_text": selected_text,
        "selected_region_sha256": sha256_text(selected_text),
        "selected_region_paragraph_refs": selected_region.get("paragraph_refs", []),
        "selection_reason": selection_reason,
        "selected_residual_target_id": subject.selected_target_id,
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "region_exists_in_current_best": bool(selected_text),
        "region_hash_matches_current_best": (
            selected_region.get("region_text_sha256") == sha256_text(selected_text)
        ),
        "strategy_evidence_points_to_region": _strategy_points_to_selected_region(subject),
        "distinct_from_prior_object_motion_operation": (
            subject.selected_target_id != OBJECT_MOTION_CAUSALITY_TARGET_ID
        ),
        "less_risky_than_reopening_protected_regions": True,
        "why_other_regions_were_not_selected": [
            {
                "region_id": "opening_table_dust_spoon_saucer_ring_field",
                "reason": (
                    "opening field carries protected setup and should not be disturbed"
                    if selected_region_id != "opening_table_dust_spoon_saucer_ring_field"
                    else "opening field is selected"
                ),
            },
            {
                "region_id": SELECTED_REGION_ID,
                "reason": (
                    "middle recurrence gains are protected references for ending-return work"
                    if selected_region_id != SELECTED_REGION_ID
                    else "middle recurrence is selected"
                ),
            },
            {
                "region_id": PROOF_NO_ANSWER_REGION_ID,
                "reason": (
                    "proof/no-answer region is selected through the direction review"
                    if selected_region_id == PROOF_NO_ANSWER_REGION_ID
                    else "proof/no-answer gains should not be compressed by inertia"
                ),
            },
            {
                "region_id": "final_return_opening_transformation_region",
                "reason": (
                    "final return is selected because ending-return risk is the chosen target"
                    if selected_region_id == ENDING_RETURN_REGION_ID
                    else "final return gains should not be overworked before evidence demands it"
                ),
            },
        ],
        "region_change_authorized_later": True,
        "region_change_authorized_now": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "selected_intervention_region_v1_controller",
    }


def _build_target_unit_map(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
) -> dict[str, object]:
    if subject.selected_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        return _build_tactile_target_unit_map(subject, selected_region)
    if subject.selected_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return _build_hostile_scaffold_target_unit_map(subject, selected_region)
    if subject.selected_target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
        return _build_ending_return_target_unit_map(subject, selected_region)
    if subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        return _build_proof_no_answer_target_unit_map(subject, selected_region)
    selected_text = str(selected_region["selected_region_before_text"])
    units = [
        _unit(
            "unit_001_cup_ring_crumb",
            _sentence_matching_any(selected_text, ("A cup is placed", "ring", "crumb")),
            objects=["cup", "ring", "crumb", "table grain"],
            current_motion_action_state="cup is placed and lifted; crumb is nudged",
            current_consequence="wet ring thins and crumb moves into the table grain",
            weakness="causal sequence is present but could be more visibly pressured",
            allowed_operation="sharpen_object_motion_to_consequence",
            target_effect="reader infers consequence from cup/ring/crumb motion before explanation",
        ),
        _unit(
            "unit_002_dust_hand_foot_air",
            _sentence_matching_any(selected_text, ("dust", "hand", "surface")),
            objects=["dust", "hand", "foot", "air", "surface"],
            current_motion_action_state="hand, foot, and air have touched the same surface",
            current_consequence="dust gathers as a record of crossings",
            weakness="motion is named generally; object relation can be sharpened",
            allowed_operation="convert_state_to_event_pressure",
            target_effect="dust reads as consequence of local movement, not static atmosphere",
        ),
        _unit(
            "unit_003_spoon_saucer_fall",
            _sentence_matching_any(selected_text, ("spoon", "saucer", "fall")),
            objects=["spoon", "saucer", "hand", "fall"],
            current_motion_action_state="hand lets go, spoon drops, saucer breaks",
            current_consequence="fall makes the break plain",
            weakness="strongest candidate for explicit motion-to-consequence tightening",
            allowed_operation="clarify_object_relation_without_adding_furniture",
            target_effect="reader sees the fall causing the break before abstraction arrives",
        ),
    ]
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "unit_map_kind": subject.target_spec.work_order_adapter,
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": selected_region["selected_region_id"],
        "target_units": units,
        "target_unit_count": len(units),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "object_motion_target_unit_map_v1_controller",
    }


def _unit(
    unit_id: str,
    before_text: str,
    *,
    objects: list[str],
    current_motion_action_state: str,
    current_consequence: str,
    weakness: str,
    allowed_operation: str,
    target_effect: str,
) -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "objects": objects,
        "current_motion_action_state": current_motion_action_state,
        "current_consequence": current_consequence,
        "weakness": weakness,
        "allowed_operation": allowed_operation,
        "forbidden_operation": [
            "add decorative detail",
            "add new object list",
            "add rival-like scene",
            "explain abstract causality",
            "alter final return",
            "compress proof/no-answer",
            "full rewrite",
        ],
        "target_effect": target_effect,
        "material_change_required": True,
        "preserve_requirements": [
            "preserve packet_0059 base structure",
            "preserve table/dust/spoon/saucer/ring field",
            "preserve partial reread transformation",
            "preserve proof/no-answer and final-return gains",
        ],
    }


def _build_hostile_scaffold_target_unit_map(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
) -> dict[str, object]:
    selected_text = str(selected_region["selected_region_before_text"])
    selected_region_id = str(selected_region["selected_region_id"])
    selected_paragraphs = _paragraphs(selected_text)
    units = [
        _hostile_scaffold_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="trace_before_naming_scaffold_reduction",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("trace before anyone names it", "already taken the trace"),
            ),
            weakness=(
                "trace-before-naming can still slide into explanation if future work "
                "names the thesis rather than trusting the material sequence"
            ),
            allowed_operation=(
                "reduce visible explanatory framing around the trace while preserving cup/ring/crumb pressure"
            ),
            target_effect=(
                "reader infers pressure from the object field before explanation names it"
            ),
        ),
        _hostile_scaffold_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="crossings_matter_without_thesis_pressure",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("world holds", "makes them matter", "crossings"),
            ),
            weakness=(
                "the sentence risks making the rule visible as a thesis instead of letting crossings carry it"
            ),
            allowed_operation=(
                "let crossings make matter through local pressure rather than thesis-signaling"
            ),
            target_effect=(
                "reader feels mattering from accumulated contact rather than an announced rule"
            ),
        ),
        _hostile_scaffold_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="ordinary_table_no_scaffold_signage",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=1,
                end=1,
                needles=("At first", "ordinary"),
            ),
            weakness=(
                "ordinary status can become a setup label instead of an enacted pressure"
            ),
            allowed_operation=(
                "keep the table ordinary while reducing visible cueing about what ordinary means"
            ),
            target_effect=(
                "ordinary presentation remains embodied instead of explanatory"
            ),
        ),
        _hostile_scaffold_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="ordinary_things_strict_without_abstraction",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=1,
                end=1,
                needles=("ordinary things are strict", "strict about what reaches them"),
            ),
            weakness=(
                "strictness can sound like conceptual declaration unless anchored in the following material marks"
            ),
            allowed_operation=(
                "reduce abstract strictness while preserving material consequence"
            ),
            target_effect="hostile scaffold visibility decreases without making the prose vague",
        ),
        _hostile_scaffold_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="small_kitchen_rule_plainness_reduction",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=1,
                end=1,
                needles=("kitchen is small", "one rule plain", "leaves a mark"),
            ),
            weakness=(
                "plain-rule language is the highest scaffold-risk unit in the selected region"
            ),
            allowed_operation=(
                "make the rule arrive through mark and pressure rather than announcement"
            ),
            target_effect=(
                "reader reads the rule from object consequence before it is named"
            ),
        ),
    ]
    protected_references = _hostile_scaffold_protected_reference_units(
        subject=subject,
        selected_region_text=selected_text,
    )
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "unit_map_kind": subject.target_spec.work_order_adapter,
        "legacy_artifact_name": "object_motion_target_unit_map",
        "artifact_name_compatibility_reason": (
            "residual work-order packet contract still expects this artifact "
            "filename; target_adapter_id and unit_map_kind are authoritative"
        ),
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": selected_region_id,
        "target_units": units,
        "target_unit_count": len(units),
        "material_target_units_all_inside_selected_region": True,
        "protected_reference_units": protected_references,
        "protected_reference_unit_count": len(protected_references),
        "future_evaluation_focus": [
            "proof/no-answer pressure remains protected outside selected region",
            "final-return/opening-return relation remains protected outside selected region",
            "opening table/dust/spoon/saucer/ring field remains protected unless separately selected",
            "reader-state evaluation should test scaffold reduction without loss of object pressure",
        ],
        "target_semantic_contract": list(subject.target_spec.operational_definition),
        "generation_materiality_policy": target_adapter_metadata(
            subject.selected_target_id
        )["materiality_policy_id"],
        "generation_semantic_validation_contract": [
            "reduce visible thesis/scaffold/explanatory pressure in selected region",
            "materially engage every hostile scaffold target unit",
            "preserve proof/no-answer carry and opening-return/reread gains",
            "preserve table/dust/spoon/saucer/ring causal field and tactile/object pressure",
            "reject vague summary, decorative vividness, rival imitation, finality claims, and phase-shift claims",
        ],
        "ablation_control_plan": list(
            subject.target_spec.target_specific_ablation_controls
        ),
        "reader_state_focus_plan": list(
            subject.target_spec.target_specific_reader_state_focus
        ),
        "stop_test_policy": target_adapter_metadata(subject.selected_target_id).get(
            "stop_test_policy"
        ),
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "hostile_scaffold_visibility_target_unit_map_v1_controller",
    }


def _hostile_scaffold_unit(
    *,
    subject: ResidualWorkOrderSubject,
    selected_region_id: str,
    selected_region_text: str,
    unit_id: str,
    text: str,
    weakness: str,
    allowed_operation: str,
    target_effect: str,
) -> dict[str, object]:
    before_text = text or _excerpt(subject.candidate.text)
    source_span = _source_span_for_selected_region_text(
        selected_region_id=selected_region_id,
        selected_region_text=selected_region_text,
        before_text=before_text,
    )
    object_labels = _hostile_scaffold_object_labels(before_text)
    return {
        "unit_id": unit_id,
        "target_unit_id": unit_id,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "objects": object_labels,
        "involved_object_labels": object_labels,
        "parent_region_id": selected_region_id,
        "source_region_id": selected_region_id,
        "source_span": source_span,
        "contained_in_selected_region": source_span["contained_in_selected_region"],
        "source_text_packet_id": subject.candidate.packet_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "current_motion_action_state": allowed_operation,
        "current_consequence": target_effect,
        "current_physical_relation": (
            "object marks, contact, crossing, pressure, and local consequence "
            "must carry meaning before explanation"
        ),
        "source_unit_role": "hostile_scaffold_visibility_reduction",
        "weakness": weakness,
        "allowed_operation": allowed_operation,
        "forbidden_operation": [
            "delete proof/no-answer structure",
            "make prose vaguer",
            "add decorative vividness",
            "imitate the rival",
            "weaken tactile/object pressure",
            "turn candidate into explanation",
            "broad rewrite",
        ],
        "protected_effects": [
            f"{subject.candidate.packet_id} as current best candidate",
            "proof/no-answer pressure",
            "opening-return relation",
            "tactile/object field gains",
            "table/dust/spoon/saucer/ring causal field",
            "strongest-rival pressure preservation",
        ],
        "target_effect": target_effect,
        "material_change_required": True,
        "semantic_contract": list(subject.target_spec.operational_definition),
        "future_generation_authorized": False,
    }


def _hostile_scaffold_object_labels(before_text: str) -> list[str]:
    preferred = [
        term
        for term in (
            "cup",
            "ring",
            "crumb",
            "grain",
            "world",
            "crossings",
            "table",
            "ordinary",
            "things",
            "kitchen",
            "mark",
            "rule",
        )
        if term in before_text.lower()
    ]
    labels = []
    for value in [*preferred, *extract_object_labels(before_text)]:
        if value and value not in labels:
            labels.append(value)
        if len(labels) >= 5:
            break
    return labels or ["table", "mark", "pressure"]


def _build_ending_return_target_unit_map(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
) -> dict[str, object]:
    selected_text = str(selected_region["selected_region_before_text"])
    selected_region_id = str(selected_region["selected_region_id"])
    selected_paragraphs = _paragraphs(selected_text)
    units = [
        _ending_return_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="final_return_enacts_not_explains",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("return", "same table", "explain", "means"),
            ),
            weakness=(
                "final return can become a thesis about what the return means "
                "instead of an enacted change in relation"
            ),
            allowed_operation=(
                "make the final return happen through object relation or reader encounter"
            ),
            target_effect="reader feels the return before explanatory closure arrives",
        ),
        _ending_return_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="opening_return_relation_without_thesis",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("opening", "first", "morning", "again"),
            ),
            weakness=(
                "opening-return relation can be named as structure rather than "
                "transformed by the returning field"
            ),
            allowed_operation=(
                "let the opening relation return altered without announcing the structure"
            ),
            target_effect="reader recognizes the opening as changed by return",
        ),
        _ending_return_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="no_reset_return_pressure",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("opening", "first", "morning", "again"),
            ),
            weakness=(
                "the ending can feel like reset or summary if return pressure "
                "does not remain locally active"
            ),
            allowed_operation=(
                "keep accumulated pressure active at return without adding explanation"
            ),
            target_effect="return carries prior pressure instead of resetting the artifact",
        ),
        _ending_return_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="same_object_field_returns_without_summary",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("table", "dust", "spoon", "saucer", "ring"),
            ),
            weakness=(
                "same-object return can collapse into summary unless object field "
                "keeps carrying the relation"
            ),
            allowed_operation=(
                "preserve table/dust/spoon/saucer/ring return as embodied relation"
            ),
            target_effect="same object field returns without explaining itself",
        ),
        _ending_return_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="proof_no_answer_carry_preserved",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=0,
                needles=("answer", "proof", "outside", "line", "carry"),
            ),
            weakness=(
                "proof/no-answer carry can turn into an answer at the ending "
                "instead of remaining pressure"
            ),
            allowed_operation=(
                "carry proof/no-answer pressure into return without resolving it"
            ),
            target_effect="proof/no-answer remains pressure, not final answer",
        ),
    ]
    protected_references = _ending_return_protected_reference_units(
        subject=subject,
        selected_region_text=selected_text,
    )
    overlap_report = _ending_return_overlap_cluster_report(
        units=units,
        selected_region_id=selected_region_id,
    )
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "unit_map_kind": subject.target_spec.work_order_adapter,
        "legacy_artifact_name": "object_motion_target_unit_map",
        "artifact_name_compatibility_reason": (
            "residual work-order packet contract still expects this artifact "
            "filename; target_adapter_id and unit_map_kind are authoritative"
        ),
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": selected_region_id,
        "target_units": units,
        "target_unit_count": len(units),
        "target_unit_overlap_cluster_report": overlap_report,
        "overlap_clusters": overlap_report["overlap_clusters"],
        "overlap_cluster_count": overlap_report["overlap_cluster_count"],
        "all_overlap_clusters_allowed": overlap_report["all_overlap_clusters_allowed"],
        "material_target_units_all_inside_selected_region": True,
        "protected_reference_units": protected_references,
        "protected_reference_unit_count": len(protected_references),
        "future_evaluation_focus": [
            "final return enacts rather than explains",
            "opening-return transformation remains readable",
            "proof/no-answer carry remains pressure",
            "object/tactile field returns without summary",
            "strongest-rival pressure remains blocking",
        ],
        "target_semantic_contract": list(subject.target_spec.operational_definition),
        "generation_materiality_policy": target_adapter_metadata(
            subject.selected_target_id
        )["materiality_policy_id"],
        "generation_semantic_validation_contract": [
            "generation requires a separate authorization packet",
            "selected ending region must carry return through object relation",
            "do not explain the return more explicitly",
            "do not let return reset the artifact",
            "validate overlapping unit semantics separately",
            "preserve opening, middle recurrence, proof/no-answer, and rival-pressure references",
        ],
        "ablation_control_plan": list(
            subject.target_spec.target_specific_ablation_controls
        ),
        "reader_state_focus_plan": list(
            subject.target_spec.target_specific_reader_state_focus
        ),
        "stop_test_policy": target_adapter_metadata(subject.selected_target_id).get(
            "stop_test_policy"
        ),
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "ending_explains_return_risk_target_unit_map_v1_controller",
    }


def _ending_return_unit(
    *,
    subject: ResidualWorkOrderSubject,
    selected_region_id: str,
    selected_region_text: str,
    unit_id: str,
    text: str,
    weakness: str,
    allowed_operation: str,
    target_effect: str,
) -> dict[str, object]:
    before_text = text or _excerpt(selected_region_text or subject.candidate.text)
    source_span = _source_span_for_selected_region_text(
        selected_region_id=selected_region_id,
        selected_region_text=selected_region_text,
        before_text=before_text,
    )
    object_labels = extract_object_labels(before_text) or ["table", "return", "opening"]
    return {
        "unit_id": unit_id,
        "target_unit_id": unit_id,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "objects": object_labels,
        "involved_object_labels": object_labels,
        "parent_region_id": selected_region_id,
        "source_region_id": selected_region_id,
        "source_span": source_span,
        "contained_in_selected_region": source_span["contained_in_selected_region"],
        "source_text_packet_id": subject.candidate.packet_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "current_motion_action_state": allowed_operation,
        "current_consequence": target_effect,
        "current_physical_relation": (
            "return must be carried by object relation, local pressure, or reader encounter"
        ),
        "source_unit_role": "ending_return_risk_reduction",
        "weakness": weakness,
        "allowed_operation": allowed_operation,
        "forbidden_operation": [
            "explain return more explicitly",
            "delete proof/no-answer pressure",
            "weaken object/tactile causal field",
            "imitate the rival",
            "return to hostile scaffold generation",
            "select middle recurrence by inertia",
            "broad rewrite",
        ],
        "protected_effects": [
            f"{subject.candidate.packet_id} as current best candidate",
            "opening-return relation",
            "proof/no-answer pressure",
            "object/tactile causal field",
            "table/dust/spoon/saucer/ring field",
            "strongest-rival pressure preservation",
        ],
        "target_effect": target_effect,
        "material_change_required": True,
        "semantic_contract": list(subject.target_spec.operational_definition),
        "future_generation_authorized": False,
    }


def _build_proof_no_answer_target_unit_map(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
) -> dict[str, object]:
    selected_text = str(selected_region["selected_region_before_text"])
    selected_region_id = str(selected_region["selected_region_id"])
    selected_paragraphs = _paragraphs(selected_text)
    shared_object_carry_sentence = _proof_no_answer_shared_object_carry_sentence(
        selected_paragraphs
    )
    units = [
        _proof_no_answer_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="no_outside_answer_embodied_in_room",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=1,
                needles=("No answer", "outside", "room", "enters"),
            ),
            weakness=(
                "no-outside-answer pressure can read as an abstract rule unless "
                "the room/object field carries it"
            ),
            allowed_operation=(
                "make the absence of outside answer register through local object pressure"
            ),
            target_effect="reader feels no outside answer from the room before explanation",
        ),
        _proof_no_answer_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="sky_silence_without_thesis",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=1,
                needles=("sky", "silence", "outside", "answer"),
            ),
            weakness=(
                "sky/silence language can become thesis-visible if it announces cosmic absence"
            ),
            allowed_operation=(
                "keep silence concrete and locally encountered rather than slogan-like"
            ),
            target_effect="outside absence remains pressure, not metaphysical signage",
        ),
        _proof_no_answer_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="line_bears_weight_without_abstraction",
            text=_sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=1,
                needles=("line", "carry", "bears", "weight"),
            ),
            weakness="line/carry language can become abstract proof compression",
            allowed_operation=(
                "make the line bear pressure through object relation rather than abstract proof"
            ),
            target_effect="reader tracks the proof as carried pressure",
        ),
        _proof_no_answer_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="proof_stays_in_object_carry",
            text=shared_object_carry_sentence
            or _sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=1,
                needles=("proof", "object", "carry", "table", "record"),
            ),
            weakness="proof can replace the artifact if it is named instead of carried",
            allowed_operation="keep proof inside object carry and visible consequence",
            target_effect="object field carries proof without explanatory takeover",
        ),
        _proof_no_answer_unit(
            subject=subject,
            selected_region_id=selected_region_id,
            selected_region_text=selected_text,
            unit_id="answer_absence_registered_by_objects",
            text=shared_object_carry_sentence
            or _sentence_for_hostile_unit(
                selected_paragraphs,
                start=0,
                end=1,
                needles=("answer", "objects", "table", "dust", "spoon", "saucer"),
            ),
            weakness=(
                "answer absence can become a claim unless objects register the absence locally"
            ),
            allowed_operation="let objects register absence without supplying an answer",
            target_effect="answer absence is readable through object pressure",
        ),
    ]
    protected_references = _proof_no_answer_protected_reference_units(
        subject=subject,
        selected_region_text=selected_text,
    )
    overlap_report = _proof_no_answer_overlap_cluster_report(
        units=units,
        selected_region_id=selected_region_id,
    )
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "unit_map_kind": subject.target_spec.work_order_adapter,
        "legacy_artifact_name": "object_motion_target_unit_map",
        "artifact_name_compatibility_reason": (
            "residual work-order packet contract still expects this artifact "
            "filename; target_adapter_id and unit_map_kind are authoritative"
        ),
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": selected_region_id,
        "target_units": units,
        "target_unit_count": len(units),
        "target_unit_overlap_cluster_report": overlap_report,
        "overlap_clusters": overlap_report["overlap_clusters"],
        "overlap_cluster_count": overlap_report["overlap_cluster_count"],
        "all_overlap_clusters_allowed": overlap_report["all_overlap_clusters_allowed"],
        "material_target_units_all_inside_selected_region": True,
        "protected_reference_units": protected_references,
        "protected_reference_unit_count": len(protected_references),
        "future_evaluation_focus": list(
            subject.target_spec.target_specific_reader_state_focus
        ),
        "target_semantic_contract": list(subject.target_spec.operational_definition),
        "generation_materiality_policy": target_adapter_metadata(
            subject.selected_target_id
        )["materiality_policy_id"],
        "generation_semantic_validation_contract": [
            "future generation requires a separate authorization packet",
            "selected proof/no-answer region must carry pressure through objects or reader encounter",
            "do not add outside-answer explanation, elder-presence explanation, or abstract thesis amplification",
            "sky/silence must not become thesis, doctrine, or cosmic signage",
            "proof must stay in line/object/mark/carry rather than abstract answer",
            "answer absence must register through objects or room pressure",
            "preserve opening, middle recurrence, final-return, object/tactile field, and rival-pressure references",
            "failed hostile-scaffold and ending-return paths must not be retried",
        ],
        "ablation_control_plan": list(
            subject.target_spec.target_specific_ablation_controls
        ),
        "reader_state_focus_plan": list(
            subject.target_spec.target_specific_reader_state_focus
        ),
        "stop_test_policy": target_adapter_metadata(subject.selected_target_id).get(
            "stop_test_policy"
        ),
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "proof_no_answer_residue_target_unit_map_v1_controller",
    }


def _proof_no_answer_unit(
    *,
    subject: ResidualWorkOrderSubject,
    selected_region_id: str,
    selected_region_text: str,
    unit_id: str,
    text: str,
    weakness: str,
    allowed_operation: str,
    target_effect: str,
) -> dict[str, object]:
    before_text = text or _excerpt(selected_region_text or subject.candidate.text)
    source_span = _source_span_for_selected_region_text(
        selected_region_id=selected_region_id,
        selected_region_text=selected_region_text,
        before_text=before_text,
    )
    object_labels = extract_object_labels(before_text) or [
        "room",
        "answer",
        "line",
        "proof",
    ]
    return {
        "unit_id": unit_id,
        "target_unit_id": unit_id,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "objects": object_labels,
        "involved_object_labels": object_labels,
        "parent_region_id": selected_region_id,
        "source_region_id": selected_region_id,
        "source_span": source_span,
        "contained_in_selected_region": source_span["contained_in_selected_region"],
        "source_text_packet_id": subject.candidate.packet_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "current_motion_action_state": allowed_operation,
        "current_consequence": target_effect,
        "current_physical_relation": (
            "proof/no-answer pressure must be carried by object relation, "
            "local pressure, or reader encounter"
        ),
        "source_unit_role": "proof_no_answer_residue_reduction",
        "weakness": weakness,
        "allowed_operation": allowed_operation,
        "forbidden_operation": [
            "add outside-answer explanation",
            "add elder-presence explanation",
            "amplify abstract thesis language",
            "delete object/tactile causal field",
            "retry hostile scaffold",
            "retry ending return",
            "repeat object-motion target",
            "repeat tactile target",
            "imitate the rival",
            "broad rewrite",
        ],
        "protected_effects": [
            f"{subject.candidate.packet_id} as current best candidate",
            "object/tactile causal field",
            "table/dust/spoon/saucer/ring field",
            "current final-return/opening-return structure",
            "failed hostile scaffold memory",
            "failed ending-return memory",
            "strongest-rival pressure preservation",
        ],
        "target_effect": target_effect,
        "material_change_required": True,
        "semantic_contract": list(subject.target_spec.operational_definition),
        "future_generation_authorized": False,
    }


def _proof_no_answer_shared_object_carry_sentence(
    selected_paragraphs: list[str],
) -> str:
    sentences = [
        sentence
        for paragraph in selected_paragraphs
        for sentence in _sentences(paragraph)
    ]
    for sentence in sentences:
        lower = sentence.lower()
        if "thing keeps its mark" in lower or "keeps its mark" in lower:
            return sentence
    for sentence in sentences:
        lower = sentence.lower()
        if (
            "legible" in lower
            and any(term in lower for term in ("mark", "line", "record"))
            and any(term in lower for term in ("carry", "keeps", "holds"))
        ):
            return sentence
    for sentence in sentences:
        lower = sentence.lower()
        if (
            any(term in lower for term in ("proof", "answer"))
            and any(term in lower for term in ("object", "thing", "table", "mark"))
            and any(term in lower for term in ("carry", "keeps", "holds"))
        ):
            return sentence
    return ""


def _proof_no_answer_overlap_cluster_report(
    *,
    units: list[dict[str, object]],
    selected_region_id: str,
) -> dict[str, object]:
    by_hash: dict[str, list[dict[str, object]]] = {}
    for unit in units:
        before_hash = str(unit.get("before_text_sha256") or "")
        if before_hash:
            by_hash.setdefault(before_hash, []).append(unit)
    clusters: list[dict[str, object]] = []
    for before_hash, group in by_hash.items():
        if len(group) < 2:
            continue
        first = group[0]
        source_span = first.get("source_span")
        source_span = source_span if isinstance(source_span, dict) else {}
        obligations = {
            str(unit.get("unit_id") or ""): {
                "allowed_operation": str(unit.get("allowed_operation") or ""),
                "target_effect": str(unit.get("target_effect") or ""),
                "semantic_contract": list(unit.get("semantic_contract", [])),
            }
            for unit in group
        }
        unit_ids = [str(unit.get("unit_id") or "") for unit in group]
        clusters.append(
            {
                "overlap_cluster_id": f"proof_no_answer_overlap_{before_hash[:12]}",
                "selected_region_id": selected_region_id,
                "source_region_id": selected_region_id,
                "source_span": dict(source_span),
                "before_text_sha256": before_hash,
                "shared_before_text": str(first.get("before_text") or ""),
                "overlapping_unit_ids": unit_ids,
                "semantic_obligations_by_unit": obligations,
                "overlap_allowed": True,
                "one_replacement_may_satisfy_multiple_units": True,
                "distinct_semantic_checks_required": True,
                "cluster_instruction": (
                    "One bounded replacement may satisfy these overlapping "
                    "proof/no-answer units only if object-carry and "
                    "answer-absence obligations are independently satisfied."
                ),
            }
        )
    return {
        "report_id": "proof_no_answer_overlap_cluster_report_v1",
        "selected_region_id": selected_region_id,
        "overlap_cluster_count": len(clusters),
        "overlap_clusters": clusters,
        "overlap_allowed": True,
        "all_overlap_clusters_allowed": all(
            cluster["overlap_allowed"] is True for cluster in clusters
        ),
        "one_replacement_may_satisfy_multiple_units": True,
        "distinct_semantic_checks_required": True,
        "worker": "proof_no_answer_overlap_cluster_report_v1_controller",
    }


def _ending_return_overlap_cluster_report(
    *,
    units: list[dict[str, object]],
    selected_region_id: str,
) -> dict[str, object]:
    by_hash: dict[str, list[dict[str, object]]] = {}
    for unit in units:
        before_hash = str(unit.get("before_text_sha256") or "")
        if before_hash:
            by_hash.setdefault(before_hash, []).append(unit)
    clusters: list[dict[str, object]] = []
    for before_hash, group in by_hash.items():
        if len(group) < 2:
            continue
        first = group[0]
        source_span = first.get("source_span")
        source_span = source_span if isinstance(source_span, dict) else {}
        obligations = {
            str(unit.get("unit_id") or ""): str(
                unit.get("target_effect")
                or unit.get("allowed_operation")
                or unit.get("weakness")
                or ""
            )
            for unit in group
        }
        unit_ids = [str(unit.get("unit_id") or "") for unit in group]
        clusters.append(
            {
                "overlap_cluster_id": f"ending_return_overlap_{before_hash[:12]}",
                "selected_region_id": selected_region_id,
                "source_region_id": selected_region_id,
                "source_span": dict(source_span),
                "before_text_sha256": before_hash,
                "shared_before_text": str(first.get("before_text") or ""),
                "overlapping_unit_ids": unit_ids,
                "semantic_obligations_by_unit": obligations,
                "overlap_allowed": True,
                "one_replacement_may_satisfy_multiple_units": True,
                "distinct_semantic_checks_required": True,
                "cluster_instruction": (
                    "One bounded replacement may satisfy these overlapping "
                    "ending-return units only if each listed semantic obligation "
                    "is independently satisfied."
                ),
            }
        )
    return {
        "report_id": "ending_return_overlap_cluster_report_v1",
        "selected_region_id": selected_region_id,
        "overlap_cluster_count": len(clusters),
        "overlap_clusters": clusters,
        "overlap_allowed": True,
        "all_overlap_clusters_allowed": all(
            cluster["overlap_allowed"] is True for cluster in clusters
        ),
        "one_replacement_may_satisfy_multiple_units": True,
        "distinct_semantic_checks_required": True,
        "source_a_b_c_artifacts_may_share_before_text": True,
        "worker": "ending_return_overlap_cluster_report_v1_controller",
    }


def _proof_no_answer_protected_reference_units(
    *,
    subject: ResidualWorkOrderSubject,
    selected_region_text: str,
) -> list[dict[str, object]]:
    paragraphs = _paragraphs(subject.candidate.text)
    references = [
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="opening_table_field_reference",
            source_region_id="opening_table_dust_spoon_saucer_ring_field",
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=0,
                end=2,
                needles=("table", "dust", "spoon", "saucer", "ring"),
            ),
            protection_reason=(
                "opening object field is protected reference material for proof/no-answer work"
            ),
            selected_region_text=selected_region_text,
        ),
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="middle_recurrence_object_tactile_reference",
            source_region_id=SELECTED_REGION_ID,
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=3,
                end=4,
                needles=("cup", "ring", "crumb", "spoon", "saucer"),
            ),
            protection_reason=(
                "middle recurrence object/tactile gains are protected; do not repeat object-motion or tactile work"
            ),
            selected_region_text=selected_region_text,
        ),
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="final_return_opening_relation_reference",
            source_region_id=ENDING_RETURN_REGION_ID,
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=10,
                end=10,
                needles=("return", "opening", "same table", "relation"),
            ),
            protection_reason=(
                "final-return/opening-return structure is protected outside the selected proof region"
            ),
            selected_region_text=selected_region_text,
        ),
    ]
    return [
        reference
        for reference in references
        if not reference["contained_in_selected_region"]
    ]


def _ending_return_protected_reference_units(
    *,
    subject: ResidualWorkOrderSubject,
    selected_region_text: str,
) -> list[dict[str, object]]:
    paragraphs = _paragraphs(subject.candidate.text)
    references = [
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="opening_table_field_reference",
            source_region_id="opening_table_dust_spoon_saucer_ring_field",
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=0,
                end=2,
                needles=("table", "dust", "spoon", "saucer", "ring"),
            ),
            protection_reason=(
                "opening object field is protected reference material for ending-return work"
            ),
            selected_region_text=selected_region_text,
        ),
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="middle_recurrence_object_field_reference",
            source_region_id=SELECTED_REGION_ID,
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=3,
                end=4,
                needles=("cup", "ring", "crumb", "spoon", "saucer"),
            ),
            protection_reason=(
                "middle recurrence object-event/tactile gains are protected; do not select them by inertia"
            ),
            selected_region_text=selected_region_text,
        ),
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="proof_no_answer_pressure_reference",
            source_region_id="proof_no_outside_answer_region",
            text=_sentence_matching_any(
                subject.candidate.text,
                ("No answer", "outside", "Proof", "line of carry"),
            ),
            protection_reason=(
                "proof/no-answer pressure is protected outside the selected ending region"
            ),
            selected_region_text=selected_region_text,
        ),
    ]
    return [
        reference
        for reference in references
        if not reference["contained_in_selected_region"]
    ]


def _hostile_scaffold_protected_reference_units(
    *,
    subject: ResidualWorkOrderSubject,
    selected_region_text: str,
) -> list[dict[str, object]]:
    paragraphs = _paragraphs(subject.candidate.text)
    references = [
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="proof_no_answer_embodiment_preservation",
            source_region_id="proof_no_outside_answer_region",
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=8,
                end=9,
                needles=("No answer", "outside", "Proof", "line of carry"),
            ),
            protection_reason=(
                "proof/no-answer pressure is outside the selected region and must be preserved, not edited"
            ),
            selected_region_text=selected_region_text,
        ),
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="final_return_echo_without_explanation",
            source_region_id="final_return_opening_transformation_region",
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=10,
                end=10,
                needles=("return", "opening", "same table", "relation"),
            ),
            protection_reason=(
                "final/opening return relation is outside the selected region and remains protected"
            ),
            selected_region_text=selected_region_text,
        ),
        _protected_reference_unit(
            subject=subject,
            reference_unit_id="preserve_table_dust_spoon_saucer_ring_causal_field",
            source_region_id="opening_table_dust_spoon_saucer_ring_field",
            text=_sentence_for_hostile_unit(
                paragraphs,
                start=0,
                end=2,
                needles=("table", "dust", "spoon", "saucer", "ring"),
            ),
            protection_reason=(
                "opening object field is outside the selected region and must not become a material target"
            ),
            selected_region_text=selected_region_text,
        ),
    ]
    return [
        reference
        for reference in references
        if not reference["contained_in_selected_region"]
    ]


def _protected_reference_unit(
    *,
    subject: ResidualWorkOrderSubject,
    reference_unit_id: str,
    source_region_id: str,
    text: str,
    protection_reason: str,
    selected_region_text: str,
) -> dict[str, object]:
    before_text = text or _excerpt(subject.candidate.text)
    return {
        "reference_unit_id": reference_unit_id,
        "unit_id": reference_unit_id,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "source_region_id": source_region_id,
        "parent_region_id": source_region_id,
        "source_text_packet_id": subject.candidate.packet_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "contained_in_selected_region": _normalize_for_containment(before_text)
        in _normalize_for_containment(selected_region_text),
        "material_change_required": False,
        "future_generation_authorized": False,
        "protection_reason": protection_reason,
    }


def _build_tactile_target_unit_map(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
) -> dict[str, object]:
    selected_text = str(selected_region["selected_region_before_text"])
    inherited_units = _inherited_target_units(subject)
    units = compile_tactile_target_units(
        inherited_units=inherited_units,
        selected_text=selected_text,
        parent_region_id=str(selected_region["selected_region_id"]),
    )
    return {
        "selected_residual_target_id": subject.selected_target_id,
        "unit_map_kind": subject.target_spec.work_order_adapter,
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": selected_region["selected_region_id"],
        "target_units": units,
        "target_unit_count": len(units),
        "inherited_units_count": len(inherited_units),
        "tactile_specific_units_count": len(units),
        "object_labels_source": (
            "candidate packet inherited target units and selected-region text"
            if inherited_units
            else "selected-region text"
        ),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "tactile_inevitability_target_unit_map_v1_controller",
    }


def _build_target_novelty_distinctness_report(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
    unit_map: dict[str, object],
) -> dict[str, object]:
    attempted = _attempted_target_ids(subject)
    units = [
        unit for unit in unit_map.get("target_units", []) if isinstance(unit, dict)
    ]
    selected_text = str(selected_region.get("selected_region_before_text") or "")
    region_repeated = (
        subject.selected_target_id == TACTILE_INEVITABILITY_TARGET_ID
        and OBJECT_MOTION_CAUSALITY_TARGET_ID in attempted
    )
    generic_vividness = _selection_reads_as_generic_vividness(subject)
    no_concrete_relation = not units
    merely_relabels = (
        subject.selected_target_id == TACTILE_INEVITABILITY_TARGET_ID
        and bool(units)
        and all(
            "object-motion" in str(unit.get("distinct_from_object_motion_basis", ""))
            for unit in units
        )
        and not any(
            _contains_tactile_signal(
                str(unit.get("before_text") or ""),
                [str(label) for label in unit.get("involved_object_labels", [])]
                if isinstance(unit.get("involved_object_labels"), list)
                else [],
            )
            for unit in units
        )
    )
    region_justified = (
        bool(selected_text)
        and selected_region.get("region_hash_matches_current_best") is True
        and selected_region.get("strategy_evidence_points_to_region") is True
        and selected_region.get("less_risky_than_reopening_protected_regions") is True
    )
    only_rival_justification = _only_strongest_rival_basis(subject)
    proceed = (
        bool(units)
        and not generic_vividness
        and not merely_relabels
        and region_justified
        and not only_rival_justification
    )
    refusal_reasons: list[str] = []
    if no_concrete_relation:
        refusal_reasons.append("no concrete tactile relation identified")
    if merely_relabels:
        refusal_reasons.append("all units merely relabel object-motion causality")
    if generic_vividness:
        refusal_reasons.append("proposed work order is generic vividness")
    if only_rival_justification:
        refusal_reasons.append("only justification is strongest-rival pressure")
    if not region_justified:
        refusal_reasons.append("bounded region is not justified by evidence")
    return {
        "selected_target_id": subject.selected_target_id,
        "attempted_target_ids": attempted,
        "distinct_from_attempted_targets": (
            subject.selected_target_id not in attempted
            and not merely_relabels
        ),
        "distinct_mechanism_basis": subject.target_spec.mechanism_description,
        "repeated_region_detected": region_repeated,
        "repeated_region_justified": region_justified,
        "inherited_units_count": int(unit_map.get("inherited_units_count") or 0),
        "tactile_specific_units_count": int(
            unit_map.get("tactile_specific_units_count")
            or (len(units) if subject.selected_target_id == TACTILE_INEVITABILITY_TARGET_ID else 0)
        ),
        "merely_relabels_object_motion": merely_relabels,
        "generic_vividness_only": generic_vividness,
        "diminishing_returns_risk": (
            "medium: repeated region after object-motion work"
            if region_repeated
            else "low"
        ),
        "proceed_with_work_order": proceed,
        "refusal_reason": "; ".join(refusal_reasons) if not proceed else None,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "target_novelty_distinctness_report_v1_controller",
    }


def _attempted_target_ids(subject: ResidualWorkOrderSubject) -> list[str]:
    residual_map = subject.strategy_payloads["residual_target_option_map"]
    attempted = residual_map.get("exhausted_or_attempted_target_ids")
    result: list[str] = []
    if isinstance(attempted, list):
        result.extend(str(target) for target in attempted if isinstance(target, str))
    repeated = residual_map.get("repeated_target_id")
    if isinstance(repeated, str) and repeated and repeated not in result:
        result.append(repeated)
    broad = residual_map.get("broad_blocker_class")
    if isinstance(broad, str) and broad and broad not in result:
        result.append(broad)
    return result


def _selection_reads_as_generic_vividness(subject: ResidualWorkOrderSubject) -> bool:
    if subject.selected_target_id != TACTILE_INEVITABILITY_TARGET_ID:
        return False
    text = " ".join(
        [
            str(subject.selected_option.get("description") or ""),
            " ".join(
                str(item)
                for item in subject.selected_option.get("source_evidence_basis", [])
                if isinstance(item, str)
            )
            if isinstance(subject.selected_option.get("source_evidence_basis"), list)
            else "",
            " ".join(
                str(item)
                for item in subject.payloads["selected_residual_target_contract"].get(
                    "operational_definition",
                    [],
                )
                if isinstance(item, str)
            )
            if isinstance(
                subject.payloads["selected_residual_target_contract"].get(
                    "operational_definition"
                ),
                list,
            )
            else "",
        ]
    ).lower()
    has_vividness = "vivid" in text or "sensory" in text
    has_tactile = any(
        term in text
        for term in (
            "tactile",
            "force",
            "contact",
            "material",
            "pressure",
            "resistance",
            "friction",
            "residue",
            "physical",
        )
    )
    return has_vividness and not has_tactile


def _only_strongest_rival_basis(subject: ResidualWorkOrderSubject) -> bool:
    descriptor = " ".join(
        [
            str(subject.selected_option.get("description") or ""),
            subject.target_spec.mechanism_description,
        ]
    ).lower()
    if any(
        term in descriptor
        for term in (
            "tactile",
            "material",
            "force",
            "contact",
            "object motion",
            "scaffold",
            "thesis",
            "proof",
            "return",
            "explanation",
            "no-answer",
        )
    ):
        return False
    basis = subject.selected_option.get("source_evidence_basis")
    if not isinstance(basis, list) or not basis:
        return False
    normalized = [str(item).lower() for item in basis if isinstance(item, str)]
    return bool(normalized) and all("rival" in item for item in normalized)


def _evidence_chain_resolved(subject: ResidualWorkOrderSubject) -> bool:
    selection = subject.payloads["residual_target_selection_packet"]
    intake = subject.payloads["strategy_packet_intake_summary"]
    return all(
        isinstance(value, str) and bool(value)
        for value in (
            selection.get("proof_packet_id"),
            selection.get("reader_state_packet_id"),
            intake.get("source_synthesis_packet_id"),
            intake.get("loop_review_packet_id"),
            selection.get("source_strategy_packet_id") or intake.get("strategy_packet_id"),
        )
    )


def _tactile_unit(
    *,
    index: int,
    source_target_unit_id: str | None,
    before_text: str,
    parent_region_id: str,
    object_labels: list[str],
) -> dict[str, object]:
    return {
        "target_unit_id": f"tactile_unit_{index:03d}",
        "unit_id": f"tactile_unit_{index:03d}",
        "source_target_unit_id": source_target_unit_id,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "parent_region_id": parent_region_id,
        "involved_object_labels": object_labels,
        "objects": object_labels,
        "current_physical_relation": _current_physical_relation(before_text),
        "tactile_inevitability_deficit": (
            "the relation can become more force/contact necessary without "
            "adding decorative sensory atmosphere"
        ),
        "allowed_operations": [
            "make contact, pressure, resistance, residue, displacement, or breakage materially causal",
            "preserve current object-motion consequence while adding physical necessity",
            "keep interpretation after material consequence",
        ],
        "forbidden_operations": [
            "decorative sensory detail",
            "new object inventory",
            "rival mimicry",
            "generic vividness amplification",
            "abstract inevitability language",
            "full rewrite",
            "reopening unrelated regions",
            "weakening current causal object relations",
        ],
        "forbidden_operation": [
            "add decorative detail",
            "add new object list",
            "add rival-like scene",
            "explain abstract inevitability",
            "full rewrite",
        ],
        "intended_first_read_effect": (
            "reader feels the material change as physically unavoidable before explanation"
        ),
        "target_effect": (
            "reader feels material consequence before interpretation explains it"
        ),
        "protected_effects": [
            "current-best partial reread transformation",
            "record-bearing object field",
            "proof/no-answer gains",
            "opening-return/final-return gains",
            "reduced overexplanation",
            "current macro structure",
        ],
        "required_material_change": (
            "increase physical force/contact necessity, not quantity of sensory description"
        ),
        "material_change_required": True,
        "distinct_from_object_motion_basis": (
            "object-motion asks moved-therefore-changed; tactile inevitability "
            "asks why the material relation could not have failed to leave the mark"
        ),
    }


def _inherited_target_units(subject: ResidualWorkOrderSubject) -> list[dict[str, Any]]:
    candidate_work_order = subject.candidate.packet_dir / "macro_recomposition_work_order.json"
    if candidate_work_order.exists():
        envelope = read_json_file(candidate_work_order)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if isinstance(payload, dict) and isinstance(payload.get("target_units"), list):
            return [unit for unit in payload["target_units"] if isinstance(unit, dict)]
    source_dir = _source_work_order_packet_dir(subject)
    if source_dir is not None:
        try:
            payload = read_target_unit_map(source_dir).payload
        except (FileNotFoundError, ValueError):
            payload = {}
        units = payload.get("target_units")
        if isinstance(units, list):
            return [unit for unit in units if isinstance(unit, dict)]
    return []


def _source_work_order_packet_dir(subject: ResidualWorkOrderSubject) -> Path | None:
    for file_name in ("macro_recomposition_packet.json", "macro_recomposition_subject_manifest.json"):
        path = subject.candidate.packet_dir / file_name
        if not path.exists():
            continue
        envelope = read_json_file(path)
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        packet_dir = payload.get("source_work_order_packet_dir")
        if isinstance(packet_dir, str) and packet_dir:
            resolved = Path(packet_dir)
            if not resolved.is_absolute():
                resolved = (subject.candidate.packet_dir / resolved).resolve()
            return resolved
    return None


def _object_labels_from_unit(unit: dict[str, Any]) -> list[str]:
    labels = unit.get("objects")
    if isinstance(labels, list):
        result = [str(label) for label in labels if isinstance(label, str) and label]
        if result:
            return result
    before_text = unit.get("before_text")
    return _extract_object_labels(str(before_text or ""))


def _extract_object_labels(text: str) -> list[str]:
    stop_words = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "into",
        "where",
        "when",
        "again",
        "before",
        "after",
        "already",
        "only",
        "ordinary",
        "strict",
        "visible",
        "change",
        "thing",
        "things",
        "another",
        "matter",
        "makes",
        "keeps",
        "seems",
        "first",
        "next",
        "same",
        "side",
        "plain",
        "small",
    }
    labels: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", text):
        lower = token.lower().strip("'")
        if lower in stop_words or lower.endswith("ly"):
            continue
        if lower not in labels:
            labels.append(lower)
        if len(labels) >= 8:
            break
    return labels


def _contains_tactile_signal(text: str, labels: list[str]) -> bool:
    lower = text.lower()
    tactile_terms = (
        "contact",
        "touch",
        "touched",
        "weight",
        "pressure",
        "pressed",
        "press",
        "resistance",
        "friction",
        "residue",
        "mark",
        "marks",
        "marked",
        "trace",
        "grain",
        "surface",
        "crack",
        "cracked",
        "break",
        "broke",
        "broken",
        "fall",
        "fell",
        "drop",
        "dropped",
        "released",
        "lifted",
        "set down",
        "narrow",
        "thinner",
        "wet",
        "dust",
        "shift",
        "nudged",
    )
    return any(term in lower for term in tactile_terms) and bool(labels)


def _prevalidate_target_adapter(subject: ResidualWorkOrderSubject) -> None:
    inventory = _build_region_inventory(subject)
    selected_region = _build_selected_region(subject, inventory)
    if subject.selected_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        unit_map = _build_hostile_scaffold_target_unit_map(subject, selected_region)
        failures = semantic_preflight_failures_for_work_order(
            {
                "residual_work_order_packet": {
                    "selected_residual_target_id": subject.selected_target_id,
                    **target_adapter_metadata(subject.selected_target_id),
                },
                "selected_intervention_region": selected_region,
                "object_motion_target_unit_map": unit_map,
            }
        )
        if failures:
            raise ValueError(
                "Residual work-order planning refused; hostile scaffold "
                "adapter failed selected-region invariant; semantic preflight "
                f"failed: {'; '.join(failures)}"
            )
        return
    if subject.selected_target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
        unit_map = _build_ending_return_target_unit_map(subject, selected_region)
        failures = semantic_preflight_failures_for_work_order(
            {
                "residual_work_order_packet": {
                    "selected_residual_target_id": subject.selected_target_id,
                    **target_adapter_metadata(subject.selected_target_id),
                },
                "selected_intervention_region": selected_region,
                "object_motion_target_unit_map": unit_map,
            }
        )
        if failures:
            raise ValueError(
                "Residual work-order planning refused; ending-return "
                "adapter failed selected-region invariant; semantic preflight "
                f"failed: {'; '.join(failures)}"
            )
        return
    if subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        unit_map = _build_proof_no_answer_target_unit_map(subject, selected_region)
        failures = semantic_preflight_failures_for_work_order(
            {
                "residual_work_order_packet": {
                    "selected_residual_target_id": subject.selected_target_id,
                    **target_adapter_metadata(subject.selected_target_id),
                },
                "selected_intervention_region": selected_region,
                "object_motion_target_unit_map": unit_map,
            }
        )
        if failures:
            raise ValueError(
                "Residual work-order planning refused; proof/no-answer "
                "adapter failed selected-region invariant; semantic preflight "
                f"failed: {'; '.join(failures)}"
            )
        return
    if subject.selected_target_id != TACTILE_INEVITABILITY_TARGET_ID:
        return
    unit_map = _build_tactile_target_unit_map(subject, selected_region)
    failures = semantic_preflight_failures_for_work_order(
        {
            "residual_work_order_packet": {
                "selected_residual_target_id": subject.selected_target_id,
                **target_adapter_metadata(subject.selected_target_id),
            },
            "object_motion_target_unit_map": unit_map,
        }
    )
    if failures:
        raise ValueError(
            "Residual work-order planning refused; tactile inevitability "
            "adapter failed stop-test; semantic preflight failed: "
            f"{'; '.join(failures)}; no concrete tactile relation identified"
        )
    novelty = _build_target_novelty_distinctness_report(
        subject,
        selected_region,
        unit_map,
    )
    if novelty["proceed_with_work_order"] is not True:
        reason = novelty.get("refusal_reason") or "target adapter refused"
        raise ValueError(
            "Residual work-order planning refused; tactile inevitability "
            f"adapter failed stop-test: {reason}"
        )


def _current_physical_relation(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("crack", "break", "fall", "released")):
        return "release, fall, or impact leaves a visible break"
    if any(term in lower for term in ("ring", "wet", "grain", "crumb", "narrow")):
        return "contact and residue alter the surface trace"
    if any(term in lower for term in ("dust", "surface", "touch", "crossed")):
        return "contact with the surface leaves residue as a record"
    return "material contact leaves a visible consequence"


def _sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?;])\s+", normalized) if sentence.strip()]


def _sentence_for_hostile_unit(
    paragraphs: list[str],
    *,
    start: int,
    end: int,
    needles: tuple[str, ...],
) -> str:
    if not paragraphs:
        return ""
    bounded_start = max(0, min(start, len(paragraphs) - 1))
    bounded_end = max(bounded_start, min(end, len(paragraphs) - 1))
    text = "\n\n".join(paragraphs[bounded_start : bounded_end + 1])
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if any(needle.lower() in lowered for needle in needles):
            return sentence
    sentences = _sentences(text)
    return sentences[0] if sentences else text.strip()


def _source_span_for_selected_region_text(
    *,
    selected_region_id: str,
    selected_region_text: str,
    before_text: str,
) -> dict[str, object]:
    start = selected_region_text.find(before_text)
    end = start + len(before_text) if start >= 0 else None
    return {
        "region_id": selected_region_id,
        "char_start": start if start >= 0 else None,
        "char_end": end,
        "before_text_sha256": sha256_text(before_text),
        "contained_in_selected_region": start >= 0,
    }


def _normalize_for_containment(value: str) -> str:
    return " ".join(value.split())


def _selected_option_evidence(subject: ResidualWorkOrderSubject) -> list[str]:
    basis = subject.selected_option.get("source_evidence_basis")
    if not isinstance(basis, list):
        return []
    return [str(item) for item in basis if isinstance(item, str) and item]


def _tactile_evidence_sentences(text: str) -> list[str]:
    sentences = _sentences(text)
    evidence = [
        sentence
        for sentence in sentences
        if _contains_tactile_signal(sentence, _extract_object_labels(sentence))
    ]
    return evidence[:4] or sentences[:2]


def _build_protected_effects_and_forbidden_changes(
    subject: ResidualWorkOrderSubject,
) -> dict[str, object]:
    selection = subject.payloads["residual_target_selection_packet"]
    return {
        "protected_effects": [
            f"{subject.candidate.packet_id} as current best candidate",
            f"executed ablation support from {selection.get('proof_packet_id')}",
            f"reader-state support from {selection.get('reader_state_packet_id')}",
            *subject.target_spec.protected_effects,
        ],
        "forbidden_changes": list(subject.target_spec.forbidden_changes),
        "selected_residual_target_id": subject.selected_target_id,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_future_generation_contract(
    subject: ResidualWorkOrderSubject,
    selected_region: dict[str, object],
    unit_map: dict[str, object],
) -> dict[str, object]:
    return {
        "future_generation_contract_created": True,
        "selected_residual_target_id": subject.selected_target_id,
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "work_order_adapter": subject.target_spec.work_order_adapter,
        **target_adapter_metadata(subject.selected_target_id),
        "base_candidate_packet_id": subject.candidate.packet_id,
        "selected_region_id": selected_region["selected_region_id"],
        "selected_region_sha256": selected_region["selected_region_sha256"],
        "target_unit_ids": [
            str(unit["unit_id"])
            for unit in unit_map["target_units"]
            if isinstance(unit, dict)
        ],
        "target_unit_hashes": {
            str(unit["unit_id"]): str(unit.get("before_text_sha256") or "")
            for unit in unit_map["target_units"]
            if isinstance(unit, dict)
        },
        "authoritative_target_units": list(unit_map["target_units"]),
        "target_unit_overlap_cluster_report": dict(
            unit_map.get("target_unit_overlap_cluster_report", {})
        ),
        "overlap_clusters": list(unit_map.get("overlap_clusters", [])),
        "overlap_cluster_count": int(unit_map.get("overlap_cluster_count") or 0),
        "protected_reference_units": list(unit_map.get("protected_reference_units", [])),
        "future_evaluation_focus": list(unit_map.get("future_evaluation_focus", [])),
        "mechanism_contract": list(subject.target_spec.operational_definition),
        "protected_effects": list(subject.target_spec.protected_effects),
        "forbidden_operations": list(subject.target_spec.forbidden_changes),
        "materiality_requirements": [
            "selected-region material change required",
            "target-unit mappings are necessary but insufficient",
            "preserve protected effects rather than sentence architecture",
            "reject generic vividness, full rewrite, and nonselected-region edits",
        ],
        "target_specific_ablation_controls": list(
            subject.target_spec.target_specific_ablation_controls
        ),
        "target_specific_reader_state_focus": list(
            subject.target_spec.target_specific_reader_state_focus
        ),
        "one_attempt_budget": 1,
        "future_generator_may_replace_only": [
            "selected region",
            "selected target units",
        ],
        "must_use_base_candidate_packet_id": subject.candidate.packet_id,
        "must_preserve": [
            "protected effects from this work order",
            "opening field unless separately selected",
            "final return unless separately selected",
            "proof/no-answer region unless separately selected",
            "controller-owned assembly and gates",
        ],
        "must_materially_improve": [
            subject.target_spec.mechanism_description,
            *subject.target_spec.target_specific_reader_state_focus[:2],
        ],
        "must_not": list(subject.target_spec.forbidden_changes),
        "controller_owns_assembly_and_gates": True,
        "future_generation_requires_separate_authorization": True,
        "future_generation_authorized": False,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "future_generation_contract_v1_controller",
    }


def _build_ablation_and_reader_eval_plan(subject: ResidualWorkOrderSubject) -> dict[str, object]:
    ablation_controls = list(subject.target_spec.target_specific_ablation_controls)
    reader_state_focus = list(subject.target_spec.target_specific_reader_state_focus)
    return {
        "if_future_candidate_is_generated": [
            f"execute ablation against {subject.candidate.packet_id}",
            *ablation_controls,
            "run strongest-rival comparison",
            "run reader-state evaluation focused on selected residual target",
            "verify preservation of partial reread transformation",
        ],
        "ablation_controls": list(ablation_controls),
        "target_specific_ablation_controls": list(ablation_controls),
        "future_ablation_controls": list(ablation_controls),
        "reader_state_focus": list(reader_state_focus),
        "reader_state_evaluation_focus": list(reader_state_focus),
        "target_specific_reader_state_focus": list(reader_state_focus),
        "future_reader_state_eval_focus": list(reader_state_focus),
        "selected_residual_target_id": subject.selected_target_id,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "ablation_and_reader_eval_plan_v1_controller",
    }


def _build_gate_report(
    *,
    subject: ResidualWorkOrderSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    unit_map = payloads.get("target_unit_map") or payloads["object_motion_target_unit_map"]
    selected_region = payloads["selected_intervention_region"]
    novelty = payloads["target_novelty_distinctness_report"]
    semantic_failures = semantic_preflight_failures_for_work_order(
        {
            "residual_work_order_packet": {
                "selected_residual_target_id": subject.selected_target_id,
                **target_adapter_metadata(subject.selected_target_id),
            },
            "selected_intervention_region": selected_region,
            "object_motion_target_unit_map": unit_map,
            "target_unit_map": unit_map,
        }
    )
    region_alignment_failures = [
        failure
        for failure in semantic_failures
        if "out_of_region_target_units_in_single_region_work_order" in failure
        or "single-region target alignment" in failure
        or "source_span" in failure
    ]
    gate_results = [
        _gate_result("selection_packet_consumed", True),
        _gate_result("selected_target_valid", True),
        _gate_result("selected_target_supported", True),
        _gate_result("operator_choice_matches_selected_target", True),
        _gate_result("stale_selection_routing_detected", True),
        _gate_result(
            "stale_selection_routing_safely_normalized",
            subject.routing["stale_selection_routing_safely_normalized"] is True,
        ),
        _gate_result("target_adapter_resolved", True),
        _gate_result("current_best_candidate_loaded", True),
        _gate_result("current_best_candidate_resolved", True),
        _gate_result("evidence_chain_resolved", _evidence_chain_resolved(subject)),
        _gate_result("candidate_region_inventory_created", True),
        _gate_result("selected_region_chosen", True),
        _gate_result(
            "bounded_region_selected",
            bool(selected_region.get("selected_region_before_text"))
            and selected_region.get("strategy_evidence_points_to_region") is True,
        ),
        _gate_result(
            "target_unit_map_created",
            unit_map["target_unit_count"] > 0,
        ),
        _gate_result(
            "target_units_created",
            unit_map["target_unit_count"] > 0,
        ),
        _gate_result(
            "target_units_inside_selected_region",
            not region_alignment_failures,
            region_alignment_failures,
        ),
        _gate_result(
            "target_mechanism_distinct",
            novelty["proceed_with_work_order"] is True,
            []
            if novelty["proceed_with_work_order"] is True
            else [
                str(
                    novelty.get("refusal_reason")
                    or "target mechanism distinctness failed"
                )
            ],
        ),
        _gate_result("future_generation_contract_created", True),
        _gate_result("ablation_and_reader_eval_plan_created", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "candidate_generation_authorized",
            False,
            ["work-order planning does not authorize generation"],
            record=False,
        ),
        _gate_result(
            "candidate_generated",
            False,
            ["work-order planning did not generate a candidate"],
            record=False,
        ),
        _gate_result(
            "live_model_call_authorized",
            False,
            ["work-order planning does not authorize live model calls"],
            record=False,
        ),
        _gate_result(
            "ablation_authorized",
            False,
            ["work-order planning does not authorize ablation"],
            record=False,
        ),
        _gate_result(
            "ablation_completed",
            False,
            ["work-order planning does not run ablation"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_authorized",
            False,
            ["work-order planning does not authorize reader-state evaluation"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_completed",
            False,
            ["work-order planning does not run reader-state evaluation"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["work-order packet is not finalization evidence"],
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
            ["work-order planning is not human validation"],
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
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "ablation_completed": False,
        "reader_state_eval_completed": False,
        "strongest_rival_defeated": False,
        "human_validation_present": False,
        "selected_residual_target_id": subject.selected_target_id,
        "stale_selection_routing_detected": subject.routing[
            "stale_selection_routing_detected"
        ],
        "stale_selection_routing_safely_normalized": subject.routing[
            "stale_selection_routing_safely_normalized"
        ],
        "canonical_next_action": subject.target_spec.canonical_next_action,
        "semantic_preflight_failures": semantic_failures,
        "target_units_inside_selected_region": not region_alignment_failures,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Residual work-order planning selected a bounded future region "
            "and target-unit map, but remains fail-closed and authorizes no "
            "generation."
        ),
        "worker": "residual_work_order_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ResidualWorkOrderSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=RESIDUAL_WORK_ORDER_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="residual_work_order_packet",
    )
    unit_map = payloads.get("target_unit_map") or payloads["object_motion_target_unit_map"]
    selected_region = payloads["selected_intervention_region"]
    novelty = payloads["target_novelty_distinctness_report"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "residual_work_order_packet"],
        "counts": {
            **counts,
            "residual_work_order_artifacts": counts["produced_artifacts"],
            "required_residual_work_order_artifacts": counts["required_artifacts"],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "source_selection_packet_id": subject.selection_packet_id,
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "candidate_text_sha256": subject.candidate.text_sha256,
        "proof_packet_id": subject.payloads["residual_target_selection_packet"].get(
            "proof_packet_id"
        ),
        "reader_state_packet_id": subject.payloads["residual_target_selection_packet"].get(
            "reader_state_packet_id"
        ),
        "selected_residual_target_id": subject.selected_target_id,
        "target_mechanism_description": subject.target_spec.mechanism_description,
        "work_order_adapter": subject.target_spec.work_order_adapter,
        **target_adapter_metadata(subject.selected_target_id),
        "selected_region_id": selected_region["selected_region_id"],
        "selected_region_sha256": selected_region["selected_region_sha256"],
        "target_unit_count": unit_map["target_unit_count"],
        "target_unit_ids": [
            str(unit["unit_id"])
            for unit in unit_map["target_units"]
            if isinstance(unit, dict)
        ],
        "target_unit_overlap_cluster_report": unit_map.get(
            "target_unit_overlap_cluster_report"
        ),
        "overlap_cluster_count": unit_map.get("overlap_cluster_count", 0),
        "target_novelty_distinctness_report": novelty,
        **subject.supersession,
        "new_canonical_work_order_packet_id": (
            packet_dir.name
            if subject.supersession.get("supersedes_semantically_stale_work_order") is True
            else subject.supersession.get("new_canonical_work_order_packet_id")
        ),
        **subject.routing,
        "candidate_generated": False,
        "model_calls": 0,
        "candidate_generation_authorized": False,
        "future_generation_authorized": False,
        "future_generation_contract_created": True,
        "next_allowed_action": subject.target_spec.review_action,
        "next_recommended_action": subject.target_spec.review_action,
        "live_model_call_authorized": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "requires_separate_generation_authorization": True,
        "gate_report": payloads["residual_work_order_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "residual_work_order_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: ResidualWorkOrderSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["residual_work_order_packet"]
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
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "selected_residual_target_id": subject.selected_target_id,
        "selected_region_id": packet["selected_region_id"],
        "selected_region_sha256": packet["selected_region_sha256"],
        "target_unit_count": packet["target_unit_count"],
        "target_novelty_distinctness_report": packet[
            "target_novelty_distinctness_report"
        ],
        "target_adapter_id": packet.get("target_adapter_id"),
        "target_adapter_version": packet.get("target_adapter_version"),
        "work_order_contract_version": packet.get("work_order_contract_version"),
        **target_adapter_metadata(subject.selected_target_id),
        "superseded_work_order_packet_id": packet.get("superseded_work_order_packet_id"),
        "supersession_reason": packet.get("supersession_reason"),
        "semantic_preflight_failures": packet.get("semantic_preflight_failures", []),
        "new_canonical_work_order_packet_id": packet.get("new_canonical_work_order_packet_id"),
        **subject.routing,
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "future_generation_authorized": False,
        "future_generation_contract_created": True,
        "next_allowed_action": subject.target_spec.review_action,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": subject.target_spec.review_action,
        "model_calls": 0,
    }


def _find_region(inventory: dict[str, object], region_id: str) -> dict[str, Any]:
    regions = inventory.get("regions")
    if isinstance(regions, list):
        for region in regions:
            if isinstance(region, dict) and region.get("region_id") == region_id:
                return region
    return {}


def _selected_region_id(subject: ResidualWorkOrderSubject) -> str:
    if subject.selected_target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
        return ENDING_RETURN_REGION_ID
    if subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
        return PROOF_NO_ANSWER_REGION_ID
    return SELECTED_REGION_ID


def _strategy_points_to_selected_region(subject: ResidualWorkOrderSubject) -> bool:
    pressure_map = subject.strategy_payloads.get("candidate_region_pressure_map", {})
    regions = pressure_map.get("regions")
    if not isinstance(regions, list):
        return False
    selected_region_id = _selected_region_id(subject)
    for region in regions:
        if not isinstance(region, dict):
            continue
        if region.get("region_id") != selected_region_id:
            continue
        if subject.selected_target_id == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID:
            return _selected_option_mentions(
                subject,
                ("return", "ending", "final", "opening"),
            )
        if subject.selected_target_id == PROOF_NO_ANSWER_RESIDUE_TARGET_ID:
            selection_packet = subject.payloads["residual_target_selection_packet"]
            return bool(
                selection_packet.get("selection_source_kind")
                == "checkpoint_strategy_direction_review"
                and selection_packet.get("source_direction_review_packet_id")
                and _selected_option_mentions(
                    subject,
                    ("proof", "answer", "outside", "checkpoint"),
                )
            )
        return bool(
            region.get("plausible_next_intervention_region") is True
            or region.get("recommendation") == "plausible_next_intervention_region"
        )
    return False


def _selected_option_mentions(
    subject: ResidualWorkOrderSubject,
    terms: tuple[str, ...],
) -> bool:
    values = [
        str(subject.selected_option.get("description") or ""),
        str(subject.target_spec.mechanism_description),
    ]
    basis = subject.selected_option.get("source_evidence_basis")
    if isinstance(basis, list):
        values.extend(str(value) for value in basis if isinstance(value, str))
    haystack = " ".join(values).lower()
    return any(term in haystack for term in terms)


def _region_text(text: str, region_id: str) -> str:
    paragraphs = _paragraphs(text)
    if region_id == SELECTED_REGION_ID:
        return "\n\n".join(paragraphs[3:5])
    if region_id == ENDING_RETURN_REGION_ID:
        final_return_start = 10 if len(paragraphs) > 10 else max(len(paragraphs) - 1, 0)
        return "\n\n".join(paragraphs[final_return_start : final_return_start + 1])
    if region_id == PROOF_NO_ANSWER_REGION_ID:
        return "\n\n".join(paragraphs[8:10])
    return ""


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def _sentence_matching_any(text: str, needles: tuple[str, ...]) -> str:
    normalized = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for needle in needles:
        for sentence in sentences:
            if needle.lower() in sentence.lower():
                return sentence.strip()
    return sentences[0].strip() if sentences else normalized


def _excerpt(text: str, limit: int = 360) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


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
    selection_packet: Path,
    message: str,
) -> ResidualWorkOrderResult:
    return ResidualWorkOrderResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "selection_packet": str(selection_packet),
            "candidate_generated": False,
            "candidate_generation_authorized": False,
            "future_generation_contract_created": False,
            "counts": {"model_calls": 0, "candidate_artifacts_created": 0},
            "model_calls": 0,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
        },
    )
