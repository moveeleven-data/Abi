"""Controller-owned residual generation authorization packet."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import json
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_RESIDUAL_GENERATION_AUTHORIZATION_ACTIVE_PHASE,
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
from abi.modules.residual_targets import (
    SELECTED_REGION_ID,
    payload_has_placeholder_generation_contract,
    require_residual_target_adapter,
    semantic_preflight_failures_for_work_order,
    target_adapter_metadata,
    target_generation_readiness_failures,
)


RESIDUAL_GENERATION_AUTHORIZATION_LINEAGE_ID = (
    "residual_generation_authorization_v1"
)
RESIDUAL_GENERATION_AUTHORIZATION_CREATED_BY = (
    "residual_generation_authorization_v1_controller"
)

AUTHORIZATION_DECISION_AUTHORIZE_ONE = "authorize_one_bounded_generation"
NEXT_RECOMMENDED_ACTION = "run_one_bounded_residual_intervention_generation"

RESIDUAL_GENERATION_AUTHORIZATION_DECISIONS = (
    AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    "require_work_order_revision",
    "pause_generation",
)

EXPECTED_TARGET_UNIT_IDS = (
    "unit_001_cup_ring_crumb",
    "unit_002_dust_hand_foot_air",
    "unit_003_spoon_saucer_fall",
)

REQUIRED_WORK_ORDER_ARTIFACTS = (
    "residual_work_order_packet",
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
)

RESIDUAL_GENERATION_AUTHORIZATION_ARTIFACT_TYPES = (
    "residual_generation_authorization_subject_manifest",
    "work_order_intake_summary",
    "operator_work_order_review_record",
    "generation_scope_authorization",
    "generation_attempt_budget",
    "target_unit_integration_policy",
    "protected_effects_and_forbidden_changes",
    "residual_generation_contract",
    "future_generator_contract_ref",
    "authorization_gate_report",
    "residual_generation_authorization_packet",
)


@dataclass(frozen=True)
class ResidualGenerationAuthorizationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class ResidualGenerationAuthorizationSubject:
    run_id: str
    work_order_packet_dir: Path
    work_order_packet_id: str
    work_order_packet_artifact_id: str | None
    work_order_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    current_best_candidate_packet_id: str
    current_best_candidate_packet_dir: Path
    candidate_text_sha256: str
    proof_packet_id: str
    reader_state_packet_id: str
    source_selection_packet_id: str
    selected_residual_target_id: str
    selected_region_id: str
    selected_region_sha256: str
    target_unit_ids: tuple[str, ...]
    target_unit_count: int
    source_parent_ids: tuple[str, ...]
    previous_placeholder_authorization_packet_id: str | None = None
    previous_placeholder_authorization_artifact_id: str | None = None
    previous_placeholder_authorization_path: str | None = None


def run_residual_generation_authorization(
    config: AbiConfig,
    *,
    work_order_packet: Path | str,
    operator_reviewed: bool,
    decision: str | None,
) -> ResidualGenerationAuthorizationResult:
    initialize_database(config)
    work_order_packet_dir = _resolve_path(config, work_order_packet)
    if not operator_reviewed:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Residual generation authorization refused; --operator-reviewed "
                "is required."
            ),
        )
    if decision not in RESIDUAL_GENERATION_AUTHORIZATION_DECISIONS:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Residual generation authorization refused; --decision must be "
                "one of: "
                f"{', '.join(RESIDUAL_GENERATION_AUTHORIZATION_DECISIONS)}."
            ),
        )
    if not work_order_packet_dir.exists() or not work_order_packet_dir.is_dir():
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=(
                "Residual generation authorization refused; work-order packet "
                f"directory not found: {work_order_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, work_order_packet_dir)
    except ValueError as error:
        return _refusal(
            work_order_packet=work_order_packet_dir,
            decision=decision,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                work_order_packet=work_order_packet_dir,
                decision=decision,
                message=(
                    "Residual generation authorization refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )
        placeholder_context = _placeholder_authorization_context(connection, subject)
        if placeholder_context:
            subject = replace(subject, **placeholder_context)
        linked = _linked_later_authorization_or_generation(connection, subject)
        if linked is not None:
            return _refusal(
                work_order_packet=work_order_packet_dir,
                decision=decision,
                message=(
                    "Residual generation authorization refused; work order already "
                    "has a later authorization or generated candidate linked to it: "
                    f"{linked.id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_RESIDUAL_GENERATION_AUTHORIZATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "residual_generation_authorization"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=RESIDUAL_GENERATION_AUTHORIZATION_LINEAGE_ID,
            created_by=RESIDUAL_GENERATION_AUTHORIZATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["residual_generation_authorization_subject_manifest"] = (
            _build_subject_manifest(subject, packet_dir)
        )
        artifacts["residual_generation_authorization_subject_manifest"] = (
            writer.write_artifact(
                "residual_generation_authorization_subject_manifest",
                payloads["residual_generation_authorization_subject_manifest"],
                parent_ids=list(subject.source_parent_ids),
            )
        )

        payloads["work_order_intake_summary"] = _build_work_order_intake_summary(
            subject
        )
        artifacts["work_order_intake_summary"] = writer.write_artifact(
            "work_order_intake_summary",
            payloads["work_order_intake_summary"],
            parent_ids=[
                artifacts["residual_generation_authorization_subject_manifest"].id,
                *subject.source_parent_ids,
            ],
        )

        payloads["operator_work_order_review_record"] = (
            _build_operator_work_order_review_record(
                subject,
                decision=str(decision),
            )
        )
        artifacts["operator_work_order_review_record"] = writer.write_artifact(
            "operator_work_order_review_record",
            payloads["operator_work_order_review_record"],
            parent_ids=[artifacts["work_order_intake_summary"].id],
        )

        payloads["generation_scope_authorization"] = (
            _build_generation_scope_authorization(
                subject=subject,
                decision=str(decision),
            )
        )
        artifacts["generation_scope_authorization"] = writer.write_artifact(
            "generation_scope_authorization",
            payloads["generation_scope_authorization"],
            parent_ids=[
                artifacts["work_order_intake_summary"].id,
                artifacts["operator_work_order_review_record"].id,
            ],
        )

        payloads["generation_attempt_budget"] = _build_generation_attempt_budget(
            subject=subject,
            decision=str(decision),
        )
        artifacts["generation_attempt_budget"] = writer.write_artifact(
            "generation_attempt_budget",
            payloads["generation_attempt_budget"],
            parent_ids=[artifacts["generation_scope_authorization"].id],
        )

        payloads["target_unit_integration_policy"] = (
            _build_target_unit_integration_policy(subject)
        )
        artifacts["target_unit_integration_policy"] = writer.write_artifact(
            "target_unit_integration_policy",
            payloads["target_unit_integration_policy"],
            parent_ids=[
                artifacts["generation_scope_authorization"].id,
                artifacts["generation_attempt_budget"].id,
            ],
        )

        payloads["protected_effects_and_forbidden_changes"] = (
            _build_protected_effects_and_forbidden_changes(subject)
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["target_unit_integration_policy"].id,
                artifacts["generation_scope_authorization"].id,
            ],
        )

        payloads["residual_generation_contract"] = _build_residual_generation_contract(
            subject=subject,
            decision=str(decision),
        )
        artifacts["residual_generation_contract"] = writer.write_artifact(
            "residual_generation_contract",
            payloads["residual_generation_contract"],
            parent_ids=[
                artifacts["generation_scope_authorization"].id,
                artifacts["target_unit_integration_policy"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["future_generator_contract_ref"] = (
            _build_future_generator_contract_ref(
                subject=subject,
                packet_dir=packet_dir,
                decision=str(decision),
            )
        )
        artifacts["future_generator_contract_ref"] = writer.write_artifact(
            "future_generator_contract_ref",
            payloads["future_generator_contract_ref"],
            parent_ids=[
                artifacts["generation_scope_authorization"].id,
                artifacts["generation_attempt_budget"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
                artifacts["residual_generation_contract"].id,
            ],
        )

        payloads["authorization_gate_report"] = _build_authorization_gate_report(
            subject=subject,
            decision=str(decision),
            payloads=payloads,
        )
        artifacts["authorization_gate_report"] = writer.write_artifact(
            "authorization_gate_report",
            payloads["authorization_gate_report"],
            parent_ids=[
                artifacts["operator_work_order_review_record"].id,
                artifacts["future_generator_contract_ref"].id,
                artifacts["residual_generation_contract"].id,
                artifacts["target_unit_integration_policy"].id,
            ],
        )

        payloads["residual_generation_authorization_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            decision=str(decision),
            payloads=payloads,
            artifacts=artifacts,
        )
        artifacts["residual_generation_authorization_packet"] = writer.write_artifact(
            "residual_generation_authorization_packet",
            payloads["residual_generation_authorization_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "residual_generation_authorization_packet"
            ],
        )

        gate_report = payloads["authorization_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="residual_generation_authorization_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=RESIDUAL_GENERATION_AUTHORIZATION_LINEAGE_ID,
        )

    return ResidualGenerationAuthorizationResult(
        exit_code=0,
        payload=_result_payload(
            subject=subject,
            packet_dir=packet_dir,
            decision=str(decision),
            artifacts=artifacts,
            payloads=payloads,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    work_order_packet_dir: Path,
) -> ResidualGenerationAuthorizationSubject:
    payloads = _load_required_payloads(work_order_packet_dir)
    packet = payloads["residual_work_order_packet"]
    manifest = payloads["residual_work_order_subject_manifest"]
    selected_region = payloads["selected_intervention_region"]
    unit_map = payloads["object_motion_target_unit_map"]
    run_id = packet.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError(
            "Residual generation authorization refused; work-order missing run_id."
        )
    _validate_work_order_payloads(payloads)

    current_best_packet_id = str(
        packet.get("current_best_candidate_packet_id")
        or manifest.get("current_best_candidate_packet_id")
        or ""
    )
    candidate_dir = _candidate_packet_dir(config, manifest, current_best_packet_id)
    candidate_text_sha256 = str(
        packet.get("candidate_text_sha256")
        or manifest.get("candidate_text_sha256")
        or ""
    )
    if not current_best_packet_id or candidate_dir is None:
        raise ValueError(
            "Residual generation authorization refused; current best candidate "
            "cannot be resolved."
        )
    if not candidate_text_sha256:
        raise ValueError(
            "Residual generation authorization refused; candidate text SHA is missing."
        )

    packet_path = work_order_packet_dir / "residual_work_order_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    work_order_artifact_ids = _artifact_ids_from_packet(packet)
    parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *work_order_artifact_ids.values(),
        ]
    )
    target_units = unit_map.get("target_units")
    target_unit_ids = tuple(
        str(unit.get("unit_id"))
        for unit in target_units
        if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
    )

    return ResidualGenerationAuthorizationSubject(
        run_id=run_id,
        work_order_packet_dir=work_order_packet_dir,
        work_order_packet_id=str(packet.get("packet_id") or work_order_packet_dir.name),
        work_order_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        work_order_artifact_ids=work_order_artifact_ids,
        payloads=payloads,
        current_best_candidate_packet_id=current_best_packet_id,
        current_best_candidate_packet_dir=candidate_dir,
        candidate_text_sha256=candidate_text_sha256,
        proof_packet_id=str(manifest.get("proof_packet_id") or ""),
        reader_state_packet_id=str(manifest.get("reader_state_packet_id") or ""),
        source_selection_packet_id=str(
            packet.get("source_selection_packet_id")
            or manifest.get("source_selection_packet_id")
            or ""
        ),
        selected_residual_target_id=str(packet["selected_residual_target_id"]),
        selected_region_id=str(selected_region["selected_region_id"]),
        selected_region_sha256=str(selected_region["selected_region_sha256"]),
        target_unit_ids=target_unit_ids,
        target_unit_count=int(unit_map.get("target_unit_count") or len(target_unit_ids)),
        source_parent_ids=tuple(parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_WORK_ORDER_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Residual generation authorization refused; work-order packet "
                f"missing {path.name}."
            )
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(
                "Residual generation authorization refused; malformed work-order "
                f"artifact: {path.name}."
            )
        payloads[artifact_type] = envelope["payload"]
    return payloads


def _validate_work_order_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["residual_work_order_packet"]
    selected_region = payloads["selected_intervention_region"]
    unit_map = payloads["object_motion_target_unit_map"]
    contract = payloads["future_generation_contract"]
    gate = payloads["residual_work_order_gate_report"]

    selected_target = packet.get("selected_residual_target_id")
    if not isinstance(selected_target, str) or not selected_target:
        raise ValueError(
            "Residual generation authorization refused; selected residual target "
            "is missing."
        )
    adapter = require_residual_target_adapter(selected_target)
    readiness_failures = target_generation_readiness_failures(selected_target)
    if readiness_failures:
        raise ValueError(
            "Residual generation authorization refused; selected target "
            "generation readiness failed: "
            + "; ".join(readiness_failures)
        )
    semantic_failures = semantic_preflight_failures_for_work_order(payloads)
    if semantic_failures:
        raise ValueError(
            "Residual generation authorization refused; work-order semantic "
            f"preflight failed: {'; '.join(semantic_failures)}"
        )
    selected_region_id = selected_region.get("selected_region_id")
    if selected_region_id != SELECTED_REGION_ID or packet.get("selected_region_id") != SELECTED_REGION_ID:
        raise ValueError(
            "Residual generation authorization refused; selected region is not "
            f"{SELECTED_REGION_ID}: {selected_region_id}"
        )
    target_units = unit_map.get("target_units")
    if not isinstance(target_units, list) or not target_units:
        raise ValueError(
            "Residual generation authorization refused; target unit map is missing."
        )
    if int(unit_map.get("target_unit_count") or 0) < 1:
        raise ValueError(
            "Residual generation authorization refused; target unit count is missing."
        )
    target_unit_ids = [
        str(unit.get("unit_id"))
        for unit in target_units
        if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
    ]
    if len(set(target_unit_ids)) != len(target_unit_ids):
        raise ValueError(
            "Residual generation authorization refused; target unit IDs are duplicated."
        )
    if contract.get("selected_residual_target_id") != selected_target:
        raise ValueError(
            "Residual generation authorization refused; future generation contract "
            "target does not match work-order packet."
        )
    if contract.get("target_adapter_id") and contract.get("target_adapter_id") != adapter.adapter_id:
        raise ValueError(
            "Residual generation authorization refused; target adapter metadata "
            "does not match selected target."
        )
    if contract.get("future_generation_contract_created") is not True:
        raise ValueError(
            "Residual generation authorization refused; future generation "
            "contract was not created."
        )
    if packet.get("future_generation_contract_created") is not True:
        raise ValueError(
            "Residual generation authorization refused; packet does not record "
            "a future generation contract."
        )
    if packet.get("candidate_generation_authorized") is True:
        raise ValueError(
            "Residual generation authorization refused; work order already "
            "authorizes candidate generation."
        )
    if contract.get("candidate_generation_authorized") is True:
        raise ValueError(
            "Residual generation authorization refused; future generation "
            "contract already authorizes candidate generation."
        )
    selected_region_sha = selected_region.get("selected_region_sha256")
    if not isinstance(selected_region_sha, str) or not selected_region_sha:
        raise ValueError(
            "Residual generation authorization refused; selected region SHA is missing."
        )
    if contract.get("selected_region_sha256") != selected_region_sha:
        raise ValueError(
            "Residual generation authorization refused; selected region SHA "
            "does not match future generation contract."
        )
    if _has_final_or_phase_shift_claim(packet) or _has_final_or_phase_shift_claim(gate):
        raise ValueError(
            "Residual generation authorization refused; work order carries a "
            "finality or phase-shift claim."
        )


def _build_subject_manifest(
    subject: ResidualGenerationAuthorizationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_work_order_packet_id": subject.work_order_packet_id,
        "source_work_order_packet_dir": str(subject.work_order_packet_dir),
        "source_work_order_packet_artifact_id": subject.work_order_packet_artifact_id,
        "source_selection_packet_id": subject.source_selection_packet_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "current_best_candidate_packet_dir": str(subject.current_best_candidate_packet_dir),
        "candidate_text_sha256": subject.candidate_text_sha256,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": list(subject.target_unit_ids),
        "target_unit_count": subject.target_unit_count,
        **_placeholder_supersession_metadata(subject),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "residual_generation_authorization_subject_manifest_v1_controller",
    }


def _build_work_order_intake_summary(
    subject: ResidualGenerationAuthorizationSubject,
) -> dict[str, object]:
    packet = subject.payloads["residual_work_order_packet"]
    return {
        "work_order_packet_consumed": True,
        "work_order_packet_id": subject.work_order_packet_id,
        "work_order_packet_dir": str(subject.work_order_packet_dir),
        "source_selection_packet_id": subject.source_selection_packet_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "selected_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": list(subject.target_unit_ids),
        "target_unit_count": subject.target_unit_count,
        "future_generation_contract_created": (
            packet.get("future_generation_contract_created") is True
        ),
        "candidate_generation_authorized_in_work_order": (
            packet.get("candidate_generation_authorized") is True
        ),
        **_placeholder_supersession_metadata(subject),
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "work_order_intake_summary_v1_controller",
    }


def _placeholder_supersession_metadata(
    subject: ResidualGenerationAuthorizationSubject,
) -> dict[str, object]:
    if not subject.previous_placeholder_authorization_packet_id:
        return {
            "previous_placeholder_authorization_packet_id": None,
            "previous_placeholder_authorization_not_generation_authoritative": False,
            "supersedes_placeholder_authorization_for_target": False,
            "supersession_reason": None,
        }
    return {
        "previous_placeholder_authorization_packet_id": (
            subject.previous_placeholder_authorization_packet_id
        ),
        "previous_placeholder_authorization_artifact_id": (
            subject.previous_placeholder_authorization_artifact_id
        ),
        "previous_placeholder_authorization_path": (
            subject.previous_placeholder_authorization_path
        ),
        "previous_placeholder_authorization_not_generation_authoritative": True,
        "supersedes_placeholder_authorization_for_target": True,
        "supersession_reason": (
            "hostile scaffold generation contract was placeholder-only"
        ),
    }


def _build_operator_work_order_review_record(
    subject: ResidualGenerationAuthorizationSubject,
    *,
    decision: str,
) -> dict[str, object]:
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    return {
        "operator_reviewed": True,
        "reviewed_work_order_packet_id": subject.work_order_packet_id,
        "reviewed_work_order_packet_dir": str(subject.work_order_packet_dir),
        "decision": decision,
        "generation_authorized": generation_authorized,
        "generation_attempt_budget": 1 if generation_authorized else 0,
        "not_final_operator_approval": True,
        "not_human_validation": True,
        "does_not_authorize_finalization": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "operator_work_order_review_record_v1_controller",
    }


def _build_generation_scope_authorization(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    decision: str,
) -> dict[str, object]:
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    return {
        "generation_authorized": generation_authorized,
        "authorization_consumed": False,
        "authorized_base_candidate_packet_id": subject.current_best_candidate_packet_id,
        "authorized_work_order_packet_id": subject.work_order_packet_id,
        "authorized_selected_region_id": subject.selected_region_id,
        "authorized_selected_region_sha256": subject.selected_region_sha256,
        "authorized_candidate_text_sha256": subject.candidate_text_sha256,
        "authorized_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "authorized_target_unit_ids": list(subject.target_unit_ids),
        **_placeholder_supersession_metadata(subject),
        "may_replace_only": [
            "selected region",
            "selected target units",
        ],
        "must_use_base_candidate_packet_id": subject.current_best_candidate_packet_id,
        "must_preserve": [
            "opening/object field outside the selected region",
            "final return / opening transformation region",
            "proof/no-answer region",
            f"{subject.current_best_candidate_packet_id} macro and reader-state gains",
            "strongest-rival pressure as blocking evidence",
        ],
        "must_materially_improve": list(adapter.mechanism_contract),
        "must_not": list(
            subject.payloads["protected_effects_and_forbidden_changes"].get(
                "forbidden_changes",
                [],
            )
        )
        + [
            "alter nonselected regions",
            "claim finality",
            "claim phase shift",
        ],
        "controller_owns_assembly_and_gates": True,
        "future_generated_candidate_must_be_ablated_before_improvement_claim": True,
        "future_generated_candidate_must_be_reader_state_evaluated_before_reader_state_claim": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "generation_scope_authorization_v1_controller",
    }


def _build_generation_attempt_budget(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    decision: str,
) -> dict[str, object]:
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    return {
        "generation_authorized": generation_authorized,
        "generation_attempt_budget": 1 if generation_authorized else 0,
        "remaining_generation_attempts": 1 if generation_authorized else 0,
        "authorization_consumed": False,
        "max_model_calls_for_future_generation": 1 if generation_authorized else 0,
        "live_model_call_authorized_for_generation": generation_authorized,
        "authorized_work_order_packet_id": subject.work_order_packet_id,
        "authorized_selected_region_id": subject.selected_region_id,
        "open_ended_generation_authorized": False,
        "repeated_generation_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "generation_attempt_budget_v1_controller",
    }


def _build_target_unit_integration_policy(
    subject: ResidualGenerationAuthorizationSubject,
) -> dict[str, object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    return {
        "selected_region_id": subject.selected_region_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "target_unit_ids": list(subject.target_unit_ids),
        "target_unit_count": subject.target_unit_count,
        "future_generator_must_produce_one_bounded_replacement": True,
        "replacement_scope": "selected_region_only",
        "unit_mapping_requirement": (
            "Future output must explain how each target unit is addressed inside "
            "one bounded selected-region replacement."
        ),
        "overlapping_units_must_be_reconciled": True,
        "overlap_notes": [
            "unit_002_dust_hand_foot_air and unit_003_spoon_saucer_fall may share sentence context",
            "target units may share sentence context",
            "shared sentence context must not be duplicated",
            "unit repairs must combine into one coherent region replacement",
        ],
        "prompt_instructions": list(adapter.prompt_instructions),
        "mechanism_contract": list(adapter.mechanism_contract),
        "materiality_policy": adapter.materiality_policy.to_dict(),
        "semantic_validation_contract": [
            "model output schema must validate before any artifact registration",
            "all target units must be materially engaged",
            "protected proof/no-answer and opening-return pressure must be preserved",
            "generic vividness, summary compression, rival imitation, finality, and phase-shift claims are refused",
        ],
        "must_not": [
            "add a new object list",
            "add decorative motion or vividness",
            "turn the passage into rival mimicry",
            "alter nonselected regions",
        ],
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "target_unit_integration_policy_v1_controller",
    }


def _build_protected_effects_and_forbidden_changes(
    subject: ResidualGenerationAuthorizationSubject,
) -> dict[str, object]:
    source = subject.payloads["protected_effects_and_forbidden_changes"]
    return {
        "source_work_order_packet_id": subject.work_order_packet_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "protected_effects": list(source.get("protected_effects", [])),
        "forbidden_changes": list(source.get("forbidden_changes", [])),
        "additional_authorization_forbidden_changes": [
            "nonselected region edits",
            "generic vividness",
            "rival mimicry",
            "abstract causality explanation",
            "full rewrite",
            "finality claim",
            "phase-shift claim",
        ],
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_residual_generation_contract(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    decision: str,
) -> dict[str, object]:
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    unit_map = subject.payloads["object_motion_target_unit_map"]
    target_units = [
        dict(unit)
        for unit in unit_map.get("target_units", [])
        if isinstance(unit, dict)
    ]
    return {
        "selected_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.current_best_candidate_packet_id,
        "current_best_candidate": subject.current_best_candidate_packet_id,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "authoritative_target_units": target_units,
        "target_unit_ids": list(subject.target_unit_ids),
        "target_unit_hashes": {
            str(unit.get("unit_id")): str(unit.get("before_text_sha256") or "")
            for unit in target_units
        },
        "mechanism_contract": list(adapter.mechanism_contract),
        "prompt_contract_id": adapter.prompt_contract_id,
        "prompt_instructions": list(adapter.prompt_instructions),
        "generation_schema_name": adapter.generation_schema.name,
        "generation_schema_version": adapter.generation_schema.version,
        "materiality_policy": adapter.materiality_policy.to_dict(),
        "materiality_policy_id": adapter.materiality_policy.policy_id,
        "materiality_policy_version": adapter.materiality_policy.policy_version,
        "semantic_validation_contract": [
            "schema validation before artifact registration",
            "selected-region materiality validation",
            "target-unit material engagement validation",
            "protected-effect preservation validation",
            "forbidden leakage/finality/phase-shift validation",
        ],
        "protected_effects": list(
            subject.payloads["protected_effects_and_forbidden_changes"].get(
                "protected_effects",
                [],
            )
        ),
        "forbidden_operations": list(
            subject.payloads["protected_effects_and_forbidden_changes"].get(
                "forbidden_changes",
                [],
            )
        ),
        "materiality_requirements": [
            "selected-region material change required",
            "target-unit mapping is necessary but insufficient",
            "controller assembles final candidate text",
            "no nonselected-region edits",
            "no finality or phase-shift claim",
        ],
        "target_specific_ablation_controls": list(adapter.ablation_controls),
        "target_specific_reader_state_focus": list(
            adapter.reader_state_evaluation_focus
        ),
        "stop_test_policy": dict(adapter.stop_test_policy),
        **_placeholder_supersession_metadata(subject),
        "one_attempt_budget": 1 if generation_authorized else 0,
        "generation_authorized": generation_authorized,
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "residual_generation_contract_v1_controller",
    }


def _build_future_generator_contract_ref(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    packet_dir: Path,
    decision: str,
) -> dict[str, object]:
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    return {
        "authorization_packet_id": packet_dir.name,
        "work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.current_best_candidate_packet_id,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "selected_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "target_unit_ids": list(subject.target_unit_ids),
        **_placeholder_supersession_metadata(subject),
        "generation_attempt_budget": 1 if generation_authorized else 0,
        "authorization_consumed": False,
        "live_model_call_authorized_for_generation": generation_authorized,
        "max_model_calls_for_future_generation": 1 if generation_authorized else 0,
        "required_after_generation": [
            "executed ablation",
            "reader-state evaluation",
            "evidence synthesis",
        ],
        "forbidden": [
            "finality claim",
            "phase-shift claim",
            "nonselected region edits",
            "generic vividness",
            "rival mimicry",
        ],
        "controller_owns_assembly_and_gates": True,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "future_generator_contract_ref_v1_controller",
    }


def _build_authorization_gate_report(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    decision: str,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    budget = payloads["generation_attempt_budget"]
    gate_results = [
        _gate_result("work_order_packet_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("work_order_validated", True),
        _gate_result("one_generation_attempt_authorized", generation_authorized),
        _gate_result("base_candidate_identified", bool(subject.current_best_candidate_packet_id)),
        _gate_result("selected_region_identified", subject.selected_region_id == SELECTED_REGION_ID),
        _gate_result("selected_region_hash_recorded", bool(subject.selected_region_sha256)),
        _gate_result("target_units_identified", subject.target_unit_count >= 1),
        _gate_result("target_unit_integration_policy_recorded", True),
        _gate_result("protected_effects_recorded", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_openai_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "candidate_generated",
            False,
            ["authorization records permission only; no candidate was generated"],
            record=False,
        ),
        _gate_result(
            "authorization_consumed",
            False,
            ["future generation has not consumed this authorization"],
            record=False,
        ),
        _gate_result(
            "ablation_authorized",
            False,
            ["ablation requires a later generated candidate"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_authorized",
            False,
            ["reader-state evaluation requires a later generated candidate"],
            record=False,
        ),
        _gate_result(
            "synthesis_authorized",
            False,
            ["synthesis requires later proof/evaluation evidence"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["authorization packet is not finalization evidence"],
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
            ["operator review is not human validation"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "candidate has not been generated",
        "authorization is not consumed",
        "ablation remains unauthorized",
        "reader-state evaluation remains unauthorized",
        "synthesis remains unauthorized",
        "strongest rival remains blocking",
        "human validation is absent",
        "finalization remains ineligible",
    ]
    return {
        "accepted": generation_authorized,
        "decision": decision,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "operator_reviewed": True,
        "generation_authorized": generation_authorized,
        "generation_attempt_budget": budget["generation_attempt_budget"],
        **_placeholder_supersession_metadata(subject),
        "authorization_consumed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "live_model_call_authorized_for_generation": generation_authorized,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "synthesis_authorized": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
        "human_validation_present": False,
        "strongest_rival_defeated": False,
        "strongest_rival_still_blocks": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "One bounded residual intervention generation attempt is authorized, "
            "but no candidate has been generated and finalization remains fail-closed."
        )
        if generation_authorized
        else (
            "Operator review was recorded, but residual generation is not authorized."
        ),
        "worker": "authorization_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    packet_dir: Path,
    decision: str,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=RESIDUAL_GENERATION_AUTHORIZATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="residual_generation_authorization_packet",
    )
    generation_authorized = decision == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "residual_generation_authorization_packet"],
        "counts": {
            **counts,
            "authorization_artifacts": counts["produced_artifacts"],
            "required_authorization_artifacts": counts["required_artifacts"],
            "model_calls": 0,
            "candidate_artifacts_created": 0,
        },
        "work_order_packet_id": subject.work_order_packet_id,
        "work_order_packet_dir": str(subject.work_order_packet_dir),
        "source_selection_packet_id": subject.source_selection_packet_id,
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "target_unit_count": subject.target_unit_count,
        "target_unit_ids": list(subject.target_unit_ids),
        **_placeholder_supersession_metadata(subject),
        "operator_reviewed": True,
        "decision": decision,
        "generation_authorized": generation_authorized,
        "generation_attempt_budget": 1 if generation_authorized else 0,
        "authorization_consumed": False,
        "candidate_generated": False,
        "live_model_call_authorized_for_generation": generation_authorized,
        "max_model_calls_for_future_generation": 1 if generation_authorized else 0,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "synthesis_authorized": False,
        "next_recommended_action": (
            NEXT_RECOMMENDED_ACTION if generation_authorized else "review_work_order_decision"
        ),
        "gate_report": payloads["authorization_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_still_blocks": True,
        "worker": "residual_generation_authorization_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: ResidualGenerationAuthorizationSubject,
    packet_dir: Path,
    decision: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["residual_generation_authorization_packet"]
    return {
        "accepted": packet["generation_authorized"],
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
        "current_best_candidate_packet_id": subject.current_best_candidate_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_count": subject.target_unit_count,
        **_placeholder_supersession_metadata(subject),
        "generation_contract_artifact_id": artifacts[
            "residual_generation_contract"
        ].id,
        "generation_authorized": packet["generation_authorized"],
        "generation_attempt_budget": packet["generation_attempt_budget"],
        "authorization_consumed": False,
        "candidate_generated": False,
        "live_model_call_authorized_for_generation": packet[
            "live_model_call_authorized_for_generation"
        ],
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": packet["next_recommended_action"],
        "model_calls": 0,
        "gate_report": payloads["authorization_gate_report"],
    }


def _candidate_packet_dir(
    config: AbiConfig,
    manifest: dict[str, Any],
    packet_id: str,
) -> Path | None:
    packet_dir_value = manifest.get("current_best_candidate_packet_dir")
    if isinstance(packet_dir_value, str) and packet_dir_value:
        packet_dir = _resolve_path(config, packet_dir_value)
        if packet_dir.exists() and packet_dir.is_dir():
            text_path = packet_dir / "macro_recomposed_candidate_text.json"
            if text_path.exists():
                return packet_dir
    fallback = config.run_dir(str(manifest.get("run_id") or "")) / "bounded_macro_recomposition" / packet_id
    if (fallback / "macro_recomposed_candidate_text.json").exists():
        return fallback
    return None


def _linked_later_authorization_or_generation(
    connection: sqlite3.Connection,
    subject: ResidualGenerationAuthorizationSubject,
) -> ArtifactRecord | None:
    source_ids = set(subject.source_parent_ids)
    if subject.work_order_packet_artifact_id:
        source_ids.add(subject.work_order_packet_artifact_id)
    candidate_link_fields = (
        "authorized_work_order_packet_id",
        "source_work_order_packet_id",
        "work_order_packet_id",
    )
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type in REQUIRED_WORK_ORDER_ARTIFACTS:
            continue
        if artifact.type == "residual_generation_authorization_packet" and (
            source_ids.intersection(artifact.parent_ids)
            or _artifact_payload_links_work_order(
                artifact,
                subject.work_order_packet_id,
                candidate_link_fields,
            )
        ):
            if _authorization_artifact_is_placeholder(artifact):
                continue
            return artifact
        if artifact.type in {
            "macro_recomposed_candidate_text",
            "macro_recomposition_packet",
            "object_event_recomposition_packet",
            "object_event_recomposed_candidate_text",
        } and _artifact_payload_links_work_order(
            artifact,
            subject.work_order_packet_id,
            candidate_link_fields,
        ):
            return artifact
    return None


def _placeholder_authorization_context(
    connection: sqlite3.Connection,
    subject: ResidualGenerationAuthorizationSubject,
) -> dict[str, str | None]:
    source_ids = set(subject.source_parent_ids)
    if subject.work_order_packet_artifact_id:
        source_ids.add(subject.work_order_packet_artifact_id)
    candidate_link_fields = (
        "authorized_work_order_packet_id",
        "source_work_order_packet_id",
        "work_order_packet_id",
    )
    placeholders: list[tuple[str, ArtifactRecord, dict[str, Any]]] = []
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type != "residual_generation_authorization_packet":
            continue
        if not (
            source_ids.intersection(artifact.parent_ids)
            or _artifact_payload_links_work_order(
                artifact,
                subject.work_order_packet_id,
                candidate_link_fields,
            )
        ):
            continue
        payload = _artifact_payload(artifact)
        if not isinstance(payload, dict) or not payload_has_placeholder_generation_contract(
            payload
        ):
            continue
        placeholders.append(
            (
                str(payload.get("packet_id") or Path(artifact.path).parent.name),
                artifact,
                payload,
            )
        )
    if not placeholders:
        return {}
    placeholders.sort(key=lambda item: item[1].created_at)
    packet_id, artifact, _payload = placeholders[-1]
    return {
        "previous_placeholder_authorization_packet_id": packet_id,
        "previous_placeholder_authorization_artifact_id": artifact.id,
        "previous_placeholder_authorization_path": artifact.path,
    }


def _authorization_artifact_is_placeholder(artifact: ArtifactRecord) -> bool:
    payload = _artifact_payload(artifact)
    return isinstance(payload, dict) and payload_has_placeholder_generation_contract(payload)


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any] | None:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, json.JSONDecodeError):
        return None
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    return payload if isinstance(payload, dict) else None


def _artifact_payload_links_work_order(
    artifact: ArtifactRecord,
    work_order_packet_id: str,
    fields: tuple[str, ...],
) -> bool:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, json.JSONDecodeError):
        return False
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        return False
    for field in fields:
        if payload.get(field) == work_order_packet_id:
            return True
    return False


def _has_final_or_phase_shift_claim(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("finalization_eligible") is True
        or payload.get("phase_shift_claim") is True
        or payload.get("no_phase_shift_claim") is False
        or payload.get("no_final_claim") is False
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
    return config.root / value


def _refusal(
    *,
    work_order_packet: Path,
    decision: str | None,
    message: str,
) -> ResidualGenerationAuthorizationResult:
    return ResidualGenerationAuthorizationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "work_order_packet": str(work_order_packet),
            "decision": decision,
            "artifact_ids": {},
            "counts": {
                "model_calls": 0,
                "candidate_artifacts_created": 0,
            },
            "selected_residual_target_id": None,
            "selected_region_id": None,
            "selected_region_sha256": None,
            "target_unit_count": 0,
            "generation_authorized": False,
            "generation_attempt_budget": 0,
            "authorization_consumed": False,
            "candidate_generated": False,
            "live_model_call_authorized_for_generation": False,
            "ablation_authorized": False,
            "reader_state_eval_authorized": False,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "model_calls": 0,
            "next_recommended_action": "review_refusal_before_generation",
        },
    )
