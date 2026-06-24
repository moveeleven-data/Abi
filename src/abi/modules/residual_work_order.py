"""Controller-owned object-motion causality work-order planning."""

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


RESIDUAL_WORK_ORDER_LINEAGE_ID = "residual_work_order_v1"
RESIDUAL_WORK_ORDER_CREATED_BY = "residual_work_order_v1_controller"

OBJECT_MOTION_CAUSALITY_TARGET_ID = "object_motion_causality_specificity"
REPEATED_BROAD_TARGET_ID = "first_read_object_event_pressure_gap"
SELECTED_REGION_ID = "middle_recurrence_ordinary_trace_logic"
NEXT_RECOMMENDED_ACTION = (
    "review_object_motion_causality_work_order_before_generation_authorization"
)

RESIDUAL_WORK_ORDER_ARTIFACT_TYPES = (
    "residual_work_order_subject_manifest",
    "residual_target_selection_intake",
    "current_candidate_region_inventory",
    "object_motion_causality_diagnostic",
    "selected_intervention_region",
    "object_motion_target_unit_map",
    "protected_effects_and_forbidden_changes",
    "future_generation_contract",
    "ablation_and_reader_eval_plan",
    "residual_work_order_gate_report",
    "residual_work_order_packet",
)

REQUIRED_SELECTION_ARTIFACTS = (
    "residual_target_selection_packet",
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
    candidate: CandidateText
    source_parent_ids: tuple[str, ...]


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

        payloads["protected_effects_and_forbidden_changes"] = (
            _build_protected_effects_and_forbidden_changes(subject)
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["residual_target_selection_intake"].id,
                artifacts["object_motion_target_unit_map"].id,
            ],
        )

        payloads["future_generation_contract"] = _build_future_generation_contract(
            subject,
            payloads["selected_intervention_region"],
            payloads["object_motion_target_unit_map"],
        )
        artifacts["future_generation_contract"] = writer.write_artifact(
            "future_generation_contract",
            payloads["future_generation_contract"],
            parent_ids=[
                artifacts["selected_intervention_region"].id,
                artifacts["object_motion_target_unit_map"].id,
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
            ],
        )

        payloads["residual_work_order_gate_report"] = _build_gate_report(
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
    _validate_selection_payloads(payloads)
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
    return ResidualWorkOrderSubject(
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
        candidate=candidate,
        source_parent_ids=tuple(parent_ids),
    )


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


def _validate_selection_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    selection_packet = payloads["residual_target_selection_packet"]
    scope = payloads["next_work_order_scope"]
    contract = payloads["selected_residual_target_contract"]
    gate = payloads["residual_target_selection_gate_report"]
    selected_target = selection_packet.get("selected_residual_target_id")
    if selected_target != OBJECT_MOTION_CAUSALITY_TARGET_ID:
        raise ValueError(
            "Residual work-order planning refused; selected residual target is "
            f"not {OBJECT_MOTION_CAUSALITY_TARGET_ID}: {selected_target}"
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
    if contract.get("selected_residual_target_id") != OBJECT_MOTION_CAUSALITY_TARGET_ID:
        raise ValueError(
            "Residual work-order planning refused; selected target contract does "
            "not match the selection packet."
        )
    if _has_final_or_phase_shift_claim(selection_packet) or _has_final_or_phase_shift_claim(gate):
        raise ValueError(
            "Residual work-order planning refused; selection packet carries a "
            "finality or phase-shift claim."
        )


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
        "selected_residual_target_id": selection.get("selected_residual_target_id"),
        "selected_region_id": SELECTED_REGION_ID,
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
        "selected_residual_target_id": selection.get("selected_residual_target_id"),
        "current_best_candidate_packet_id": subject.candidate.packet_id,
        "proof_packet_id": selection.get("proof_packet_id"),
        "reader_state_packet_id": selection.get("reader_state_packet_id"),
        "broad_blocker_class": selection.get("broad_blocker_class"),
        "next_allowed_action": scope.get("next_allowed_action"),
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
                "contains cup/ring/dust/spoon/saucer motion and consequence; "
                "best fit for object-motion causality specificity"
            ),
        ),
        _region(
            region_id="proof_no_outside_answer_region",
            paragraphs=paragraphs,
            start=8,
            end=9,
            function="keeps proof/no-outside-answer pressure inside the room",
            protected_effects=[
                "proof/no-answer gains",
                "no external answer enters",
            ],
            modification_risk="high: may slide back into proof compression",
            eligible=False,
            reason="protect from renewed proof/no-answer compression by inertia",
        ),
        _region(
            region_id="final_return_opening_transformation_region",
            paragraphs=paragraphs,
            start=10,
            end=10,
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
        "selected_region_candidate": SELECTED_REGION_ID,
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
        "reason": reason,
    }


def _build_diagnostic(
    subject: ResidualWorkOrderSubject,
    inventory: dict[str, object],
) -> dict[str, object]:
    selected_region = _find_region(inventory, SELECTED_REGION_ID)
    return {
        "selected_residual_target_id": OBJECT_MOTION_CAUSALITY_TARGET_ID,
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


def _build_selected_region(
    subject: ResidualWorkOrderSubject,
    inventory: dict[str, object],
) -> dict[str, object]:
    selected_region = _find_region(inventory, SELECTED_REGION_ID)
    selected_text = _region_text(subject.candidate.text, SELECTED_REGION_ID)
    return {
        "selected_region_id": SELECTED_REGION_ID,
        "selected_region_before_text": selected_text,
        "selected_region_sha256": sha256_text(selected_text),
        "selected_region_paragraph_refs": selected_region.get("paragraph_refs", []),
        "selection_reason": (
            "This region already contains object motion and implied consequence "
            "through cup, ring, crumb, dust, spoon, saucer, hand, and fall; it is "
            "the narrowest bounded place to sharpen causality before explanation."
        ),
        "why_other_regions_were_not_selected": [
            {
                "region_id": "opening_table_dust_spoon_saucer_ring_field",
                "reason": "opening field carries protected setup and should not be disturbed",
            },
            {
                "region_id": "proof_no_outside_answer_region",
                "reason": "proof/no-answer gains should not be compressed by inertia",
            },
            {
                "region_id": "final_return_opening_transformation_region",
                "reason": "final return gains should not be overworked before evidence demands it",
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


def _build_protected_effects_and_forbidden_changes(
    subject: ResidualWorkOrderSubject,
) -> dict[str, object]:
    selection = subject.payloads["residual_target_selection_packet"]
    return {
        "protected_effects": [
            f"{subject.candidate.packet_id} as current best candidate",
            f"executed ablation support from {selection.get('proof_packet_id')}",
            f"reader-state support from {selection.get('reader_state_packet_id')}",
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
            "candidate generation in this command",
            "finality claim",
            "phase-shift claim",
        ],
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
        "selected_residual_target_id": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "base_candidate_packet_id": subject.candidate.packet_id,
        "selected_region_id": selected_region["selected_region_id"],
        "selected_region_sha256": selected_region["selected_region_sha256"],
        "target_unit_ids": [
            str(unit["unit_id"])
            for unit in unit_map["target_units"]
            if isinstance(unit, dict)
        ],
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
            "object-motion causality specificity",
            "visible consequence before explanation",
            "local inference of pressure",
        ],
        "must_not": [
            "add decorative vividness",
            "mimic rival",
            "claim finality",
            "alter nonselected regions",
            "perform full rewrite",
        ],
        "controller_owns_assembly_and_gates": True,
        "future_generation_requires_separate_authorization": True,
        "candidate_generation_authorized": False,
        "live_model_call_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "future_generation_contract_v1_controller",
    }


def _build_ablation_and_reader_eval_plan(subject: ResidualWorkOrderSubject) -> dict[str, object]:
    return {
        "if_future_candidate_is_generated": [
            f"execute ablation against {subject.candidate.packet_id}",
            "revert object-motion causality intervention",
            "isolate object-motion relation",
            "include decorative-vividness control",
            "include object-list/no-causal-motion control",
            "run strongest-rival comparison",
            "run reader-state evaluation focused on first-read causal specificity",
            "verify preservation of partial reread transformation",
        ],
        "future_ablation_controls": [
            "revert_object_motion_causality_intervention",
            "isolate_object_motion_relation",
            "decorative_vividness_control",
            "object_list_no_causal_motion_control",
            "strongest_rival_comparison",
        ],
        "future_reader_state_eval_focus": [
            "first-read causal specificity",
            "object movement producing consequence before explanation",
            "reread preservation",
            "proof/no-answer carry",
            "final-return preservation",
            "hostile scaffold risk",
        ],
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
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    gate_results = [
        _gate_result("selection_packet_consumed", True),
        _gate_result("selected_target_valid", True),
        _gate_result("current_best_candidate_loaded", True),
        _gate_result("candidate_region_inventory_created", True),
        _gate_result("selected_region_chosen", True),
        _gate_result(
            "target_unit_map_created",
            payloads["object_motion_target_unit_map"]["target_unit_count"] > 0,
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
            "reader_state_eval_authorized",
            False,
            ["work-order planning does not authorize reader-state evaluation"],
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
        "strongest_rival_defeated": False,
        "human_validation_present": False,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Object-motion work-order planning selected a bounded future region "
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
    unit_map = payloads["object_motion_target_unit_map"]
    selected_region = payloads["selected_intervention_region"]
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
        "selected_residual_target_id": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": selected_region["selected_region_id"],
        "target_unit_count": unit_map["target_unit_count"],
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "future_generation_contract_created": True,
        "next_allowed_action": NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
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
        "selected_residual_target_id": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": packet["selected_region_id"],
        "target_unit_count": packet["target_unit_count"],
        "candidate_generated": False,
        "candidate_generation_authorized": False,
        "future_generation_contract_created": True,
        "next_allowed_action": NEXT_RECOMMENDED_ACTION,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "model_calls": 0,
    }


def _find_region(inventory: dict[str, object], region_id: str) -> dict[str, Any]:
    regions = inventory.get("regions")
    if isinstance(regions, list):
        for region in regions:
            if isinstance(region, dict) and region.get("region_id") == region_id:
                return region
    return {}


def _region_text(text: str, region_id: str) -> str:
    paragraphs = _paragraphs(text)
    if region_id == SELECTED_REGION_ID:
        return "\n\n".join(paragraphs[3:5])
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
