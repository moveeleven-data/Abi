"""Bounded macro recomposition from autonomous evidence synthesis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
    ModelValidationError,
    WorkerRole,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID = "bounded_macro_recomposition_v1"
BOUNDED_MACRO_RECOMPOSITION_CREATED_BY = "bounded_macro_recomposition_v1_controller"
BOUNDED_MACRO_RECOMPOSITION_CLIENTS = ("fake", "openai")
BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT = 8
BOUNDED_MACRO_RECOMPOSITION_REQUIRED_MODEL_CALLS = 1
BOUNDED_MACRO_RECOMPOSITION_PROMPT_CONTRACT_ID = (
    "autonomous.bounded_macro_recomposition.v1"
)

BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES = (
    "macro_recomposition_subject_manifest",
    "macro_recomposition_brief_ref",
    "macro_recomposition_work_order",
    "protected_effects_and_forbidden_changes",
    "macro_recomposition_plan",
    "macro_patch_or_section_plan",
    "macro_recomposed_candidate_text",
    "macro_recomposition_diff_report",
    "macro_rival_pressure_check",
    "macro_recomposition_gate_report",
    "macro_recomposition_packet",
)

REQUIRED_SYNTHESIS_ARTIFACT_FILES = (
    "autonomous_evidence_synthesis_packet.json",
    "best_current_candidate_selection.json",
    "macro_recomposition_brief.json",
    "local_law_case_notes.json",
    "residual_blocker_map.json",
    "rival_pressure_summary.json",
    "exhausted_handle_report.json",
    "failed_or_rejected_repairs.json",
    "strategic_decision_report.json",
)

OPTIONAL_SYNTHESIS_ARTIFACT_FILES = (
    "reader_state_evidence_adjudication.json",
    "reader_state_tension_report.json",
)

TARGET_MOVEMENT = "middle_and_return_movement"
READER_STATE_MACRO_2_TARGET_SCOPE = "reader_state_informed_macro_2"

REQUIRED_SEMANTIC_CONSTRAINT_IDS = (
    "proof_from_inside_line",
    "cosmic_silence_as_isolation_condition",
    "return_without_regression",
    "no_outside_answer_or_rescue",
    "strongest_rival_pressure",
    "table_dust_spoon_saucer_local_field",
    "record_law_proof_answer_compression_preserved",
)

ACTIVE_TRANSFORMATION_TARGET_IDS = (
    "middle_abstraction_ladder_compression",
    "proof_line_redundancy_cleanup",
    "no_outside_answer_pressure_preservation",
    "final_return_closure_embodiment",
    "object_event_pressure_without_pressure_naming",
)

MATERIAL_REQUIRED_ACTIVE_TARGET_IDS = (
    "middle_abstraction_ladder_compression",
    "proof_line_redundancy_cleanup",
    "no_outside_answer_pressure_preservation",
    "final_return_closure_embodiment",
)

READER_STATE_MACRO_2_ACTIVE_TARGET_IDS = (
    "proof_no_outside_answer_refinement",
    "final_return_echo_reread_strength",
    "thesis_visible_proof_language_reduction",
    "opening_return_transformation_strengthening",
    "preserve_reader_state_partial_gain",
)

READER_STATE_MACRO_2_MATERIAL_REQUIRED_TARGET_IDS = (
    "proof_no_outside_answer_refinement",
    "final_return_echo_reread_strength",
    "thesis_visible_proof_language_reduction",
    "opening_return_transformation_strengthening",
)

SUPPORTED_TARGET_SCOPES = (
    TARGET_MOVEMENT,
    READER_STATE_MACRO_2_TARGET_SCOPE,
    "proof_no_outside_answer_refinement",
    "final_return_echo_reread_strength",
    "reader_state_opening_return_transformation",
)


@dataclass(frozen=True)
class BoundedMacroRecompositionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class MacroSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_artifact_ids: dict[str, str]
    synthesis_payloads: dict[str, dict[str, Any]]
    selected_best_candidate: dict[str, Any]
    base_packet_dir: Path
    base_packet_id: str
    base_packet_kind: str
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str
    base_word_count: int
    source_parent_ids: tuple[str, ...]
    fixture_only: bool
    normalized_brief: NormalizedMacroRecompositionBrief


@dataclass(frozen=True)
class NormalizedMacroRecompositionBrief:
    brief_type: str
    target_scope: str
    target_movement: str
    target_submovement: tuple[str, ...]
    active_transformation_target_ids: tuple[str, ...]
    material_required_target_ids: tuple[str, ...]
    protected_effects: tuple[str, ...]
    forbidden_changes: tuple[str, ...]
    success_criteria: tuple[str, ...]
    source_reader_state_evidence: dict[str, Any]
    source_reader_state_tensions: dict[str, Any]
    reader_state_evidence_packet_id: str | None
    selected_best_candidate_packet_id: str
    selected_best_candidate_text_sha256: str | None
    requires_future_ablation_or_reader_eval: bool
    reader_state_informed: bool


@dataclass(frozen=True)
class RecomposedText:
    text: str
    target_start_index: int
    target_end_index: int
    unchanged_prefix: list[str]
    original_target: list[str]
    replacement: list[str]


def run_bounded_macro_recomposition(
    config: AbiConfig,
    *,
    client_name: str,
    synthesis_packet: Path,
    allow_live_model: bool = False,
    max_model_calls: int = BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> BoundedMacroRecompositionResult:
    if client_name not in BOUNDED_MACRO_RECOMPOSITION_CLIENTS:
        return _refusal(
            message=f"Unsupported bounded macro recomposition client: {client_name}",
            synthesis_packet=synthesis_packet,
        )
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Bounded macro recomposition OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    f"Bounded macro recomposition OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )
        if max_model_calls < BOUNDED_MACRO_RECOMPOSITION_REQUIRED_MODEL_CALLS:
            return _refusal(
                message=(
                    "Bounded macro recomposition OpenAI path refused; "
                    f"max-model-calls {max_model_calls} is below required budget "
                    f"{BOUNDED_MACRO_RECOMPOSITION_REQUIRED_MODEL_CALLS}."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )

    initialize_database(config)
    with connect(config.db_path) as connection:
        try:
            subject = _load_macro_subject(connection, config, synthesis_packet)
        except ValueError as error:
            return _refusal(
                message=f"Bounded macro recomposition refused; {error}",
                synthesis_packet=synthesis_packet,
                client_name=client_name,
            )
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Bounded macro recomposition refused; synthesis run is not "
                    f"registered: {subject.run_id}"
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "bounded_macro_recomposition")
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
            created_by=BOUNDED_MACRO_RECOMPOSITION_CREATED_BY,
            fixture_only=subject.fixture_only,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        model_results: list[ModelDriverResult] = []
        model_payload: dict[str, object] | None = None
        model_call_id: str | None = None

        payloads["macro_recomposition_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir,
            client_name=client_name,
            max_model_calls=max_model_calls,
        )
        artifacts["macro_recomposition_subject_manifest"] = writer.write_artifact(
            "macro_recomposition_subject_manifest",
            payloads["macro_recomposition_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["macro_recomposition_brief_ref"] = _build_brief_ref(subject)
        artifacts["macro_recomposition_brief_ref"] = writer.write_artifact(
            "macro_recomposition_brief_ref",
            payloads["macro_recomposition_brief_ref"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                *list(subject.source_parent_ids),
            ],
        )

        payloads["macro_recomposition_work_order"] = _build_work_order(subject)
        artifacts["macro_recomposition_work_order"] = writer.write_artifact(
            "macro_recomposition_work_order",
            payloads["macro_recomposition_work_order"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                artifacts["macro_recomposition_brief_ref"].id,
            ],
        )

        payloads["protected_effects_and_forbidden_changes"] = _build_protected_effects(
            subject
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["macro_recomposition_brief_ref"].id,
                artifacts["macro_recomposition_work_order"].id,
            ],
        )

        if client_name == "openai":
            connection.commit()
            factory = client_factory or _default_openai_client_factory
            result = _run_live_macro_recomposition_model(
                config=config,
                subject=subject,
                packet_dir=packet_dir,
                model_client=factory(configured_model),
                work_order=payloads["macro_recomposition_work_order"],
                protected_effects=payloads["protected_effects_and_forbidden_changes"],
                parent_ids=[
                    artifacts["macro_recomposition_work_order"].id,
                    artifacts["protected_effects_and_forbidden_changes"].id,
                ],
            )
            model_results.append(result)
            if not result.accepted or result.parsed_payload is None:
                return _failure_result(
                    subject=subject,
                    packet_dir=packet_dir,
                    client_name=client_name,
                    model=configured_model,
                    artifacts=artifacts,
                    model_results=model_results,
                    message=_model_failure_message(result),
                )
            model_payload = result.parsed_payload
            model_call_id = result.model_call.id

        payloads["macro_recomposition_plan"] = _build_recomposition_plan(
            subject,
            model_payload=model_payload,
            model_call_id=model_call_id,
        )
        plan_parent_ids = [
            artifacts["macro_recomposition_work_order"].id,
            artifacts["protected_effects_and_forbidden_changes"].id,
        ]
        if model_payload is None:
            artifacts["macro_recomposition_plan"] = writer.write_artifact(
                "macro_recomposition_plan",
                payloads["macro_recomposition_plan"],
                parent_ids=plan_parent_ids,
            )
        else:
            artifacts["macro_recomposition_plan"] = _write_model_tagged_artifact(
                connection=connection,
                subject=subject,
                packet_dir=packet_dir,
                result=model_results[-1],
                artifact_type="macro_recomposition_plan",
                payload=payloads["macro_recomposition_plan"],
                parent_ids=plan_parent_ids,
            )

        recomposed = (
            _fake_recompose_text(subject)
            if model_payload is None
            else _model_recompose_text(subject, model_payload)
        )
        payloads["macro_patch_or_section_plan"] = _build_patch_or_section_plan(
            subject,
            recomposed,
            model_payload=model_payload,
            model_call_id=model_call_id,
        )
        patch_parent_ids = [
            artifacts["macro_recomposition_plan"].id,
            artifacts["protected_effects_and_forbidden_changes"].id,
        ]
        if model_payload is None:
            artifacts["macro_patch_or_section_plan"] = writer.write_artifact(
                "macro_patch_or_section_plan",
                payloads["macro_patch_or_section_plan"],
                parent_ids=patch_parent_ids,
            )
        else:
            artifacts["macro_patch_or_section_plan"] = _write_model_tagged_artifact(
                connection=connection,
                subject=subject,
                packet_dir=packet_dir,
                result=model_results[-1],
                artifact_type="macro_patch_or_section_plan",
                payload=payloads["macro_patch_or_section_plan"],
                parent_ids=patch_parent_ids,
            )
            model_results[-1] = _link_model_result(
                connection=connection,
                result=model_results[-1],
                parsed_artifact=artifacts["macro_patch_or_section_plan"],
            )

        payloads["macro_recomposed_candidate_text"] = _build_recomposed_candidate(
            subject,
            recomposed,
            model_call_id=model_call_id,
        )
        artifacts["macro_recomposed_candidate_text"] = writer.write_artifact(
            "macro_recomposed_candidate_text",
            payloads["macro_recomposed_candidate_text"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                subject.base_candidate_artifact_id or artifacts["macro_recomposition_subject_manifest"].id,
            ],
        )

        payloads["macro_recomposition_diff_report"] = _build_diff_report(
            subject,
            recomposed,
            payloads["macro_recomposed_candidate_text"],
            model_payload=model_payload,
        )
        artifacts["macro_recomposition_diff_report"] = writer.write_artifact(
            "macro_recomposition_diff_report",
            payloads["macro_recomposition_diff_report"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                artifacts["macro_recomposed_candidate_text"].id,
            ],
        )

        payloads["macro_rival_pressure_check"] = _build_rival_pressure_check(
            subject,
            payloads["macro_recomposed_candidate_text"],
        )
        artifacts["macro_rival_pressure_check"] = writer.write_artifact(
            "macro_rival_pressure_check",
            payloads["macro_rival_pressure_check"],
            parent_ids=[
                artifacts["macro_recomposed_candidate_text"].id,
                artifacts["macro_recomposition_diff_report"].id,
            ],
        )

        payloads["macro_recomposition_gate_report"] = _build_gate_report(
            subject=subject,
            subject_manifest=payloads["macro_recomposition_subject_manifest"],
            protected_effects=payloads["protected_effects_and_forbidden_changes"],
            diff_report=payloads["macro_recomposition_diff_report"],
            rival_check=payloads["macro_rival_pressure_check"],
            model_payload=model_payload,
        )
        artifacts["macro_recomposition_gate_report"] = writer.write_artifact(
            "macro_recomposition_gate_report",
            payloads["macro_recomposition_gate_report"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                artifacts["macro_recomposed_candidate_text"].id,
                artifacts["macro_recomposition_diff_report"].id,
                artifacts["macro_rival_pressure_check"].id,
            ],
        )

        payloads["macro_recomposition_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_results=model_results,
        )
        artifacts["macro_recomposition_packet"] = writer.write_artifact(
            "macro_recomposition_packet",
            payloads["macro_recomposition_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "macro_recomposition_packet"
            ],
        )

        gate_report = payloads["macro_recomposition_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="bounded_macro_recomposition_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        )

    payload = {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_dir": str(packet_dir),
        "packet_id": packet_dir.name,
        "client": client_name,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "counts": {
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "model": configured_model if client_name == "openai" else None,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "gate_report": payloads["macro_recomposition_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    return BoundedMacroRecompositionResult(
        exit_code=0,
        payload=payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
        model_results=tuple(model_results),
    )


def _load_macro_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> MacroSubject:
    resolved_packet_dir = _resolve_path(config, synthesis_packet_dir)
    if not resolved_packet_dir.exists() or not resolved_packet_dir.is_dir():
        raise ValueError(f"synthesis packet directory not found: {synthesis_packet_dir}")
    missing = [
        file_name
        for file_name in REQUIRED_SYNTHESIS_ARTIFACT_FILES
        if not (resolved_packet_dir / file_name).exists()
    ]
    if missing:
        raise ValueError(
            "synthesis packet is missing required artifacts: " + ", ".join(missing)
        )
    payloads = {
        file_name.removesuffix(".json"): _read_payload(resolved_packet_dir / file_name)
        for file_name in REQUIRED_SYNTHESIS_ARTIFACT_FILES
    }
    for file_name in OPTIONAL_SYNTHESIS_ARTIFACT_FILES:
        path = resolved_packet_dir / file_name
        if path.exists():
            payloads[file_name.removesuffix(".json")] = _read_payload(path)
    packet = payloads["autonomous_evidence_synthesis_packet"]
    best = payloads["best_current_candidate_selection"]
    selected = best.get("selected_best_candidate")
    if not isinstance(selected, dict):
        raise ValueError("best_current_candidate_selection lacks selected_best_candidate")
    normalized_brief = _normalize_macro_recomposition_brief(
        payloads=payloads,
        selected=selected,
    )
    if selected.get("packet_id") == "packet_0022":
        raise ValueError("synthesis-selected base is the failed pivot packet_0022")
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("synthesis packet has no run_id")
    synthesis_artifact_ids = packet.get("artifact_ids", {})
    if not isinstance(synthesis_artifact_ids, dict):
        synthesis_artifact_ids = {}
    base_packet_dir = _resolve_path(config, Path(str(selected.get("packet_dir", ""))))
    if not base_packet_dir.exists():
        raise ValueError(f"selected best candidate packet not found: {base_packet_dir}")
    base_packet_kind = str(selected.get("packet_kind") or "")
    base_payload = _load_base_candidate_payload(base_packet_dir, base_packet_kind)
    base_text = str(base_payload.get("text") or "")
    if not base_text:
        raise ValueError("selected best candidate packet has no candidate text")
    expected_hash = selected.get("selected_best_candidate_text_sha256") or selected.get(
        "text_sha256"
    )
    actual_hash = sha256_text(base_text)
    if expected_hash and str(expected_hash) != actual_hash:
        raise ValueError("selected best candidate text hash does not match base text")
    source_parent_ids = _source_parent_ids(connection, resolved_packet_dir, synthesis_artifact_ids)
    base_candidate_artifact_id = selected.get("candidate_artifact_id")
    if isinstance(base_candidate_artifact_id, str):
        source_parent_ids = _unique([*source_parent_ids, base_candidate_artifact_id])
    return MacroSubject(
        run_id=run_id,
        synthesis_packet_dir=resolved_packet_dir,
        synthesis_packet_id=str(packet.get("packet_id") or resolved_packet_dir.name),
        synthesis_artifact_ids={
            str(key): str(value) for key, value in synthesis_artifact_ids.items()
        },
        synthesis_payloads=payloads,
        selected_best_candidate=selected,
        base_packet_dir=base_packet_dir,
        base_packet_id=str(selected.get("packet_id") or base_packet_dir.name),
        base_packet_kind=base_packet_kind,
        base_candidate_artifact_id=(
            base_candidate_artifact_id if isinstance(base_candidate_artifact_id, str) else None
        ),
        base_text=base_text,
        base_text_sha256=actual_hash,
        base_word_count=len(_words(base_text)),
        source_parent_ids=tuple(source_parent_ids),
        fixture_only=any(
            bool(payload.get("fixture_only"))
            for payload in payloads.values()
            if isinstance(payload, dict)
        ),
        normalized_brief=normalized_brief,
    )


def _normalize_macro_recomposition_brief(
    *,
    payloads: dict[str, dict[str, Any]],
    selected: dict[str, Any],
) -> NormalizedMacroRecompositionBrief:
    brief = payloads["macro_recomposition_brief"]
    adjudication = payloads.get("reader_state_evidence_adjudication", {})
    tensions = payloads.get("reader_state_tension_report", {})
    brief_type = str(brief.get("brief_type") or "macro_recomposition_brief_v1")
    selected_packet_id = str(selected.get("packet_id") or "")
    if not selected_packet_id:
        raise ValueError("selected best candidate has no packet_id")
    selected_hash = selected.get("selected_best_candidate_text_sha256") or selected.get(
        "text_sha256"
    )
    selected_hash_text = str(selected_hash) if selected_hash else None
    if "reader_state_informed_macro_2" in brief_type or brief.get(
        "reader_state_evidence_consumed"
    ):
        expected_packet_id = str(
            brief.get("current_best_base_candidate_packet_id")
            or _dict_value(brief.get("current_best_base_candidate"), "packet_id")
            or selected_packet_id
        )
        if expected_packet_id != selected_packet_id:
            raise ValueError(
                "macro recomposition brief base does not match selected best candidate"
            )
        submovement = _string_tuple(brief.get("target_movement_or_submovement"))
        if not submovement:
            submovement = (
                "proof/no-outside-answer refinement",
                "final return echo / reread strength",
                "reduce thesis-visible proof language",
                "increase first-read object-event vividness without weakening macro structure",
            )
        return NormalizedMacroRecompositionBrief(
            brief_type=brief_type,
            target_scope=READER_STATE_MACRO_2_TARGET_SCOPE,
            target_movement=READER_STATE_MACRO_2_TARGET_SCOPE,
            target_submovement=submovement,
            active_transformation_target_ids=READER_STATE_MACRO_2_ACTIVE_TARGET_IDS,
            material_required_target_ids=READER_STATE_MACRO_2_MATERIAL_REQUIRED_TARGET_IDS,
            protected_effects=tuple(
                _unique(
                    [
                        *list(brief.get("protected_effects", [])),
                        *list(brief.get("protected_effects_to_preserve", [])),
                        "packet_0008 partial reread gain",
                        "table/dust/spoon/saucer/ring causal field",
                        "reduced overexplanation achieved by macro recomposition",
                        "strongest-rival pressure as active constraint",
                    ]
                )
            ),
            forbidden_changes=tuple(_string_tuple(brief.get("forbidden_changes"))),
            success_criteria=tuple(
                _string_tuple(brief.get("success_criteria"))
                or _string_tuple(brief.get("ablation_and_evaluation_plan_after_recomposition"))
            ),
            source_reader_state_evidence=dict(adjudication),
            source_reader_state_tensions=dict(tensions),
            reader_state_evidence_packet_id=str(
                brief.get("reader_state_evidence_packet_id")
                or adjudication.get("packet_id")
                or ""
            )
            or None,
            selected_best_candidate_packet_id=selected_packet_id,
            selected_best_candidate_text_sha256=selected_hash_text,
            requires_future_ablation_or_reader_eval=True,
            reader_state_informed=True,
        )

    target = str(brief.get("target_region_or_movement") or "")
    if target != TARGET_MOVEMENT:
        raise ValueError(
            "macro recomposition brief has unsupported target; expected a supported "
            f"target scope such as {TARGET_MOVEMENT} or {READER_STATE_MACRO_2_TARGET_SCOPE}"
        )
    if brief.get("allowed_scale") != "bounded_macro_recomposition_not_full_rewrite":
        raise ValueError("macro recomposition brief does not require bounded scale")
    return NormalizedMacroRecompositionBrief(
        brief_type=brief_type,
        target_scope=TARGET_MOVEMENT,
        target_movement=TARGET_MOVEMENT,
        target_submovement=(TARGET_MOVEMENT,),
        active_transformation_target_ids=ACTIVE_TRANSFORMATION_TARGET_IDS,
        material_required_target_ids=MATERIAL_REQUIRED_ACTIVE_TARGET_IDS,
        protected_effects=tuple(_string_tuple(brief.get("protected_effects_to_preserve"))),
        forbidden_changes=tuple(_string_tuple(brief.get("forbidden_changes"))),
        success_criteria=tuple(_string_tuple(brief.get("success_criteria"))),
        source_reader_state_evidence=dict(adjudication),
        source_reader_state_tensions=dict(tensions),
        reader_state_evidence_packet_id=None,
        selected_best_candidate_packet_id=selected_packet_id,
        selected_best_candidate_text_sha256=selected_hash_text,
        requires_future_ablation_or_reader_eval=True,
        reader_state_informed=False,
    )


def _run_live_macro_recomposition_model(
    *,
    config: AbiConfig,
    subject: MacroSubject,
    packet_dir: Path,
    model_client: ModelClient,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    target = _target_window(subject.base_text)
    request = WorkerRequest(
        run_id=subject.run_id,
        worker_role=WorkerRole.BOUNDED_MACRO_RECOMPOSER,
        prompt_contract_id=BOUNDED_MACRO_RECOMPOSITION_PROMPT_CONTRACT_ID,
        schema=BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        input_text=_prompt_for_live_macro_recomposition(
            subject=subject,
            target=target,
            work_order=work_order,
            protected_effects=protected_effects,
        ),
        input_artifact_ids=list(parent_ids),
        input_packet_path=str(subject.synthesis_packet_dir),
        lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        parent_ids=list(parent_ids),
        fixture_only=False,
        output_dir=str(packet_dir),
        register_parsed_artifact=False,
        parsed_payload_validator=lambda payload: _validate_live_macro_payload(
            subject=subject,
            payload=payload,
        ),
    )
    return driver.run(request)


def _prompt_for_live_macro_recomposition(
    *,
    subject: MacroSubject,
    target: RecomposedText,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
) -> str:
    return _canonical_json(
        {
            "task": (
                "Propose target-addressed bounded replacements for the "
                "controller-owned middle/return movement."
                if subject.normalized_brief.reader_state_informed
                else "Propose one bounded replacement section for the controller-owned "
                "middle/return movement."
            ),
            "controller_owns": [
                "source_synthesis_packet",
                "base_candidate_choice",
                "base_candidate_text",
                "target_paragraph_indices",
                "target_paragraph_refs",
                "target_paragraph_before_text_hashes",
                "before_section_text",
                "protected_semantic_constraints",
                "active_transformation_targets",
                "target_coverage_validation",
                "final_text_assembly",
                "diff_report",
                "gates",
                "finalization",
            ],
            "model_may_own": [
                "replacement_section_text",
                "target_paragraph_replacements",
                "plan wording",
                "section plan wording",
                "rationale",
                "local-law explanation",
                "uncertainty",
                "predicted reader-state effect",
                "semantic constraint mapping claims",
                "active target mapping claims",
            ],
            "model_must_not_own": [
                "full artifact text",
                "opening or prefix rewrite",
                "base candidate choice",
                "before text",
                "source packet IDs",
                "gate pass/fail",
                "strongest-rival defeated status",
                "finality",
                "phase-shift claim",
            ],
            "source_synthesis_packet_id": subject.synthesis_packet_id,
            "base_candidate_packet_id": subject.base_packet_id,
            "base_candidate_text_sha256": subject.base_text_sha256,
            "target_movement": subject.normalized_brief.target_movement,
            "target_scope": subject.normalized_brief.target_scope,
            "target_submovement": list(subject.normalized_brief.target_submovement),
            "target_paragraph_start_index": target.target_start_index,
            "target_paragraph_end_index": target.target_end_index,
            "unchanged_prefix_text": "\n\n".join(target.unchanged_prefix),
            "before_section_text": "\n\n".join(target.original_target),
            "protected_semantic_constraints": _semantic_constraints(),
            "active_transformation_targets": _active_transformation_targets(
                subject,
                target,
            ),
            "work_order": work_order,
            "protected_effects_and_forbidden_changes": protected_effects,
            "macro_recomposition_brief": subject.synthesis_payloads[
                "macro_recomposition_brief"
            ],
            "rival_pressure_summary": subject.synthesis_payloads[
                "rival_pressure_summary"
            ],
            "output_rule": (
                "Return bounded replacements only, not the full artifact. Include "
                "exactly one constraint_mapping item for every protected "
                "constraint_id and exactly one active_target_mapping item for "
                "every active target_id. For reader_state_informed_macro_2, you "
                "must also return target_paragraph_replacements keyed by the "
                "controller target_paragraph_ref values. Replace every target "
                "paragraph marked material_change_required; do not copy target "
                "paragraphs unchanged. If two active targets share a paragraph, "
                "the paragraph replacement must satisfy both. The controller will "
                "assemble final text and reject copied paragraphs, hash mismatches, "
                "missing target refs, and unsupported target coverage claims. For "
                "non-reader-state macro recomposition, return "
                "target_paragraph_replacements as an empty array."
            ),
        }
    )


def _write_model_tagged_artifact(
    *,
    connection: sqlite3.Connection,
    subject: MacroSubject,
    packet_dir: Path,
    result: ModelDriverResult,
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> ArtifactRecord:
    writer = PacketWriter(
        connection=connection,
        run_id=subject.run_id,
        packet_dir=packet_dir,
        lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        created_by=f"model_driver:{result.model_call.provider}:{result.model_call.model}",
        fixture_only=False,
        model_call_id=result.model_call.id,
    )
    return writer.write_artifact(artifact_type, payload, parent_ids=parent_ids)


def _link_model_result(
    *,
    connection: sqlite3.Connection,
    result: ModelDriverResult,
    parsed_artifact: ArtifactRecord,
) -> ModelDriverResult:
    linked_call = link_model_call_parsed_artifact(
        connection,
        model_call_id=result.model_call.id,
        parsed_output_artifact_id=parsed_artifact.id,
    )
    return ModelDriverResult(
        model_call=linked_call,
        parsed_payload=result.parsed_payload,
        parsed_artifact=parsed_artifact,
    )


def _failure_result(
    *,
    subject: MacroSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    model_results: list[ModelDriverResult],
    message: str,
) -> BoundedMacroRecompositionResult:
    payload = {
        "accepted": False,
        "refused": True,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "synthesis_packet": str(subject.synthesis_packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "message": message,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    return BoundedMacroRecompositionResult(
        exit_code=1,
        payload=payload,
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _model_failure_message(result: ModelDriverResult) -> str:
    detail = result.model_call.error_message or result.model_call.status
    return f"Bounded macro recomposition refused during live recomposition: {detail}"


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _build_subject_manifest(
    subject: MacroSubject,
    packet_dir: Path,
    *,
    client_name: str,
    max_model_calls: int,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "max_model_calls": max_model_calls,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_artifact_ids": subject.synthesis_artifact_ids,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_kind": subject.base_packet_kind,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_artifact_id": subject.base_candidate_artifact_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "base_candidate_word_count": subject.base_word_count,
        "base_from_synthesis_selected_best_candidate": True,
        "failed_pivot_packet_used_as_base": subject.base_packet_id == "packet_0022",
        "original_candidate_used_as_base": False,
        "packet_0030_used_as_base": subject.base_packet_id == "packet_0030",
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "reader_state_evidence_packet_id": subject.normalized_brief.reader_state_evidence_packet_id,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_subject_manifest_v1_controller",
    }


def _build_brief_ref(subject: MacroSubject) -> dict[str, object]:
    brief = subject.synthesis_payloads["macro_recomposition_brief"]
    return {
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "macro_recomposition_brief_artifact_id": subject.synthesis_artifact_ids.get(
            "macro_recomposition_brief"
        ),
        "brief_type": brief.get("brief_type"),
        "normalized_target_scope": subject.normalized_brief.target_scope,
        "normalized_target_movement": subject.normalized_brief.target_movement,
        "normalized_target_submovement": list(
            subject.normalized_brief.target_submovement
        ),
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "reader_state_evidence_packet_id": subject.normalized_brief.reader_state_evidence_packet_id,
        "target_region_or_movement": brief.get("target_region_or_movement"),
        "target_movement_or_submovement": list(
            brief.get("target_movement_or_submovement", [])
            if isinstance(brief.get("target_movement_or_submovement"), list)
            else []
        ),
        "allowed_scale": brief.get("allowed_scale"),
        "protected_effects_to_preserve": list(subject.normalized_brief.protected_effects),
        "forbidden_changes": list(subject.normalized_brief.forbidden_changes),
        "success_criteria": list(subject.normalized_brief.success_criteria),
        "active_transformation_target_ids": list(
            subject.normalized_brief.active_transformation_target_ids
        ),
        "ablation_plan_after_recomposition": list(
            brief.get("ablation_plan_after_recomposition", [])
        ),
        "not_candidate_artifact": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_brief_ref_v1_controller",
    }


def _build_work_order(subject: MacroSubject) -> dict[str, object]:
    target = _target_window(subject.base_text)
    target_paragraphs = _target_paragraph_specs(subject, target)
    return {
        "work_order_id": f"macro_recomposition_{subject.synthesis_packet_id}",
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "selected_reader_state_evidence_packet_id": (
            subject.normalized_brief.reader_state_evidence_packet_id
        ),
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "target_paragraph_start_index": target.target_start_index,
        "target_paragraph_end_index": target.target_end_index,
        "target_paragraphs": target_paragraphs,
        "before_section_text": "\n\n".join(target.original_target),
        "selected_candidate_text": subject.base_text,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "allowed_touch": "multiple adjacent spans in the middle/return movement",
        "protected_semantic_constraints": _semantic_constraints(),
        "active_transformation_targets": _active_transformation_targets(subject, target),
        "protected_effects": list(subject.normalized_brief.protected_effects),
        "forbidden_changes": list(subject.normalized_brief.forbidden_changes),
        "reader_state_evidence_adjudication": subject.normalized_brief.source_reader_state_evidence,
        "reader_state_tension_report": subject.normalized_brief.source_reader_state_tensions,
        "controller_owns": [
            "source packet references",
            "base candidate text",
            "macro target spans",
            "before section text",
            "protected effects",
            "forbidden changes",
            "protected semantic constraints",
            "active transformation targets",
            "target coverage validation",
            "text assembly",
            "diff report",
            "gate report",
            "finalization status",
        ],
        "model_may_own_if_live_later": [
            "recomposition plan wording",
            "replacement section text",
            "rationale",
            "local-law explanation",
            "uncertainty",
            "predicted reader-state effect",
            "semantic constraint mapping",
            "active target mapping claims",
        ],
        "model_must_not_own": [
            "finalization fields",
            "gate pass/fail",
            "before text",
            "source packet IDs",
            "phase-shift claim",
            "unrestricted full rewrite authority",
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_work_order_v1_controller",
    }


def _build_protected_effects(subject: MacroSubject) -> dict[str, object]:
    protected = _unique(
        [
            *list(subject.normalized_brief.protected_effects),
            "table/dust/spoon/saucer local field",
            "proof from inside the line it integrates",
            "cosmic silence as isolation condition of proof",
            "return without regression",
            "strongest-rival pressure",
            "best current candidate's useful record/law/proof/answer compression",
        ]
    )
    forbidden = _unique(
        [
            *list(subject.normalized_brief.forbidden_changes),
            "rewriting the whole artifact",
            "thinning the opening scene",
            "repeating local record/law/proof/answer compression as the main move",
            "naming pressure more often instead of embodying pressure",
            "adding outside rescue",
            "weakening cosmic silence into mere lack of help",
            "marking final or phase-shift success",
        ]
    )
    return {
        "protected_effects": protected,
        "forbidden_changes": forbidden,
        "best_current_candidate_repair_preserved": True,
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "reader_state_evidence_packet_id": subject.normalized_brief.reader_state_evidence_packet_id,
        "strongest_rival_pressure_must_remain_active": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_recomposition_plan(
    subject: MacroSubject,
    *,
    model_payload: dict[str, object] | None = None,
    model_call_id: str | None = None,
) -> dict[str, object]:
    if model_payload is not None:
        plan = model_payload["macro_recomposition_plan"]
        if not isinstance(plan, dict):
            raise TypeError("macro_recomposition_plan must be an object")
        return {
            "plan_id": f"bounded_macro_plan_{sha256_text(subject.base_text)[:12]}",
            "target_movement": subject.normalized_brief.target_movement,
            "target_scope": subject.normalized_brief.target_scope,
            "target_submovement": list(subject.normalized_brief.target_submovement),
            "bounded_macro_recomposition": True,
            "full_rewrite": False,
            "plan_summary": plan["plan_summary"],
            "plan_steps": list(plan["plan_steps"]),
            "model_owned_fields": [
                "plan_summary",
                "plan_steps",
                "rationale",
                "local_law_explanation",
                "uncertainty",
                "predicted_reader_state_effect",
            ],
            "source_model_call_id": model_call_id,
            "rationale": model_payload["rationale"],
            "local_law_explanation": model_payload["local_law_explanation"],
            "uncertainty": model_payload["uncertainty"],
            "predicted_reader_state_effect": model_payload[
                "predicted_reader_state_effect"
            ],
            "not_finalization_eligible": True,
            "no_phase_shift_claim": True,
            "worker": "macro_recomposition_plan_v1_model_driver",
        }
    return {
        "plan_id": f"bounded_macro_plan_{sha256_text(subject.base_text)[:12]}",
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "plan_steps": _fake_plan_steps(subject),
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_plan_v1_fake_controller",
    }


def _fake_plan_steps(subject: MacroSubject) -> list[dict[str, object]]:
    if subject.normalized_brief.reader_state_informed:
        return [
            {
                "step_id": "macro_step_001",
                "action": "preserve the synthesis-selected macro candidate as base",
                "rationale": (
                    f"The synthesis selected {subject.base_packet_id}; the controller "
                    "must not fall back to an earlier local-patch candidate."
                ),
            },
            {
                "step_id": "macro_step_002",
                "action": "refine proof/no-outside-answer carry through local objects",
                "rationale": (
                    "Reader-state evidence says proof/no-answer logic remains partial "
                    "or thesis-visible."
                ),
            },
            {
                "step_id": "macro_step_003",
                "action": "strengthen the final return echo without weakening the opening",
                "rationale": (
                    "The opening became more necessary on reread, but the ending still "
                    "does not fully transform the opening."
                ),
            },
            {
                "step_id": "macro_step_004",
                "action": "preserve strongest-rival pressure for later testing",
                "rationale": (
                    "The strongest rival still blocks first-read vividness and lived "
                    "object-event pressure."
                ),
            },
        ]
    return [
        {
            "step_id": "macro_step_001",
            "action": "preserve opening scene and current useful compression",
            "rationale": (
                "The synthesis selected the current best candidate as the base."
            ),
        },
        {
            "step_id": "macro_step_002",
            "action": "replace the middle proof ladder with object/event sequence",
            "rationale": "The failed pivot showed pressure must be embodied rather than named.",
        },
        {
            "step_id": "macro_step_003",
            "action": "recompose return as record-bearing change, not explanatory closure",
            "rationale": "The return must carry contradiction internally.",
        },
        {
            "step_id": "macro_step_004",
            "action": "leave strongest-rival pressure unresolved and test later by executed ablation",
            "rationale": "No internal packet has closed rival pressure.",
        },
    ]


def _build_patch_or_section_plan(
    subject: MacroSubject,
    recomposed: RecomposedText,
    *,
    model_payload: dict[str, object] | None = None,
    model_call_id: str | None = None,
) -> dict[str, object]:
    coverage_report = _build_target_coverage_report(
        subject,
        recomposed,
        recomposed.replacement,
        model_payload=model_payload,
    )
    payload = {
        "section_plan_id": f"macro_section_{sha256_text(''.join(recomposed.replacement))[:12]}",
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "target_paragraph_start_index": recomposed.target_start_index,
        "target_paragraph_end_index": recomposed.target_end_index,
        "unchanged_prefix_paragraph_count": len(recomposed.unchanged_prefix),
        "replacement_paragraph_count": len(recomposed.replacement),
        "changed_paragraph_count": coverage_report[
            "materially_changed_target_paragraph_count"
        ],
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "before_section_text": "\n\n".join(recomposed.original_target),
        "replacement_section_text": "\n\n".join(recomposed.replacement),
        "target_coverage_report": coverage_report,
        "source_base_text_sha256": subject.base_text_sha256,
        "rationale": (
            "Replace the middle/return movement as one adjacent bounded section, "
            "preserving the selected base opening and object field."
        ),
        "worker": "macro_patch_or_section_plan_v1_fake_controller",
    }
    if subject.normalized_brief.reader_state_informed:
        payload.update(
            {
                "target_paragraph_replacements": (
                    list(model_payload["target_paragraph_replacements"])
                    if model_payload is not None
                    else _controller_target_paragraph_replacements(subject, recomposed)
                ),
                "controller_assembled_from_target_paragraph_replacements": (
                    model_payload is not None
                ),
                "model_replacement_section_text_authoritative": False
                if model_payload is not None
                else None,
            }
        )
    if model_payload is not None:
        section_plan = model_payload["section_plan"]
        if not isinstance(section_plan, dict):
            raise TypeError("section_plan must be an object")
        payload.update(
            {
                "model_section_plan": section_plan,
                "constraint_mapping": list(model_payload["constraint_mapping"]),
                "active_target_mapping": list(model_payload["active_target_mapping"]),
                "semantic_constraint_claims_model_reported": True,
                "semantic_constraint_satisfaction_not_proven": True,
                "requires_internal_reader_or_ablation_validation": True,
                "source_model_call_id": model_call_id,
                "rationale": section_plan["rationale"],
                "worker": "macro_patch_or_section_plan_v1_model_driver",
            }
        )
    return payload


def _controller_target_paragraph_replacements(
    subject: MacroSubject,
    recomposed: RecomposedText,
) -> list[dict[str, object]]:
    specs = _target_paragraph_specs(subject, recomposed)
    replacements: list[dict[str, object]] = []
    for index, spec in enumerate(specs):
        replacement_text = (
            recomposed.replacement[index]
            if index < len(recomposed.replacement)
            else str(spec["before_text"])
        )
        replacements.append(
            {
                "target_paragraph_ref": spec["target_paragraph_ref"],
                "before_text_sha256": spec["before_text_sha256"],
                "replacement_text": replacement_text,
                "active_target_ids_covered": list(spec["active_target_ids"]),
                "material_change_summary": (
                    "controller-authored deterministic replacement for active targets"
                    if bool(spec["material_change_required"])
                    else "controller-authored preservation target"
                ),
                "preserved_effects": list(spec["protected_effects"]),
                "risk_notes": "fixture/fake target-addressed replacement; no improvement claim",
                "uncertainty": "requires executed ablation or internal reader-state testing",
            }
        )
    return replacements


def _build_recomposed_candidate(
    subject: MacroSubject,
    recomposed: RecomposedText,
    *,
    model_call_id: str | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": f"bounded_macro_recomposition_{sha256_text(recomposed.text)[:12]}",
        "text": recomposed.text,
        "text_sha256": sha256_text(recomposed.text),
        "word_count": len(_words(recomposed.text)),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "assembled_by_controller": True,
        "source_model_call_id": model_call_id,
        "candidate_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": subject.fixture_only if model_call_id is None else False,
        "requires_executed_ablation_before_improvement_claim": True,
        "worker": (
            "macro_recomposed_candidate_text_v1_controller_assembled_from_model"
            if model_call_id
            else "macro_recomposed_candidate_text_v1_fake_controller"
        ),
    }


def _build_diff_report(
    subject: MacroSubject,
    recomposed: RecomposedText,
    candidate: dict[str, object],
    *,
    model_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    coverage_report = _build_target_coverage_report(
        subject,
        recomposed,
        recomposed.replacement,
        model_payload=model_payload,
    )
    return {
        "base_candidate_packet_id": subject.base_packet_id,
        "base_text_sha256": subject.base_text_sha256,
        "revised_text_sha256": candidate["text_sha256"],
        "base_word_count": subject.base_word_count,
        "revised_word_count": candidate["word_count"],
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "opening_scene_preserved": True,
        "unchanged_prefix_paragraph_count": len(recomposed.unchanged_prefix),
        "target_coverage_report": coverage_report,
        "changed_paragraph_start_index": recomposed.target_start_index,
        "changed_paragraph_end_index": recomposed.target_end_index,
        "changed_spans": [
            {
                "changed_span_id": "macro_change_001",
                "movement": subject.normalized_brief.target_movement,
                "target_scope": subject.normalized_brief.target_scope,
                "before_text": "\n\n".join(recomposed.original_target),
                "after_text": "\n\n".join(recomposed.replacement),
                "operation_type": "bounded_section_recomposition",
                "inside_target": True,
                "rationale": "Turn proof/return explanation into object-event sequence.",
            }
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_diff_report_v1_controller",
    }


def _build_rival_pressure_check(
    subject: MacroSubject,
    candidate: dict[str, object],
) -> dict[str, object]:
    rival = subject.synthesis_payloads["rival_pressure_summary"]
    text = str(candidate["text"]).lower()
    object_terms = ["table", "dust", "spoon", "saucer", "ring"]
    return {
        "strongest_rival_present": bool(rival.get("strongest_rival_present")),
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "object_field_terms_preserved": [
            term for term in object_terms if term in text
        ],
        "current_candidate_closes_gap": False,
        "reason": (
            "The bounded recomposition preserves rival pressure for later testing; "
            "it does not claim to beat the strongest rival."
        ),
        "requires_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_rival_pressure_check_v1_controller",
    }


def _build_gate_report(
    *,
    subject: MacroSubject,
    subject_manifest: dict[str, object],
    protected_effects: dict[str, object],
    diff_report: dict[str, object],
    rival_check: dict[str, object],
    model_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    constraint_mapping_complete = bool(model_payload) and _constraint_mapping_complete(
        model_payload
    )
    coverage_report = diff_report.get("target_coverage_report", {})
    if not isinstance(coverage_report, dict):
        coverage_report = {}
    macro_target_coverage_passed = bool(
        coverage_report.get("macro_target_coverage_passed")
    )
    macro_materiality_passed = bool(coverage_report.get("macro_materiality_passed"))
    gate_results = [
        _gate_result("macro_recomposition_packet_exists", True),
        _gate_result("synthesis_packet_consumed", True),
        _gate_result(
            "best_candidate_used_as_base",
            subject_manifest["base_from_synthesis_selected_best_candidate"]
            and subject.base_packet_id != "packet_0022",
        ),
        _gate_result("macro_recomposition_bounded", bool(diff_report["bounded_macro_recomposition"])),
        _gate_result(
            "protected_effects_recorded",
            bool(protected_effects["protected_effects"])
            and bool(protected_effects["forbidden_changes"]),
        ),
        _gate_result(
            "rival_pressure_preserved",
            bool(rival_check["strongest_rival_pressure_preserved"]),
        ),
        _gate_result(
            "reader_state_informed_brief_consumed",
            True,
            [],
            record=subject.normalized_brief.reader_state_informed,
        ),
        _gate_result(
            "constraint_mapping_complete",
            constraint_mapping_complete if model_payload is not None else True,
        ),
        _gate_result("macro_target_coverage_passed", macro_target_coverage_passed),
        _gate_result("macro_materiality_passed", macro_materiality_passed),
        _gate_result(
            "semantic_constraint_satisfaction_proven",
            False,
            [
                "semantic constraint satisfaction is model-reported only and "
                "requires internal reader or executed ablation validation"
            ],
        ),
        _gate_result(
            "macro_recomposition_executed_ablation_completed",
            False,
            ["macro recomposition has not yet been tested by executed ablation"],
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            [
                "strongest-rival pressure remains blocking",
                "macro candidate requires executed ablation before any improvement claim",
            ],
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is intentionally absent"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    return {
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "non_final": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "strongest_rival_pressure_preserved": True,
        "reader_state_informed_brief_consumed": (
            subject.normalized_brief.reader_state_informed
        ),
        "target_scope": subject.normalized_brief.target_scope,
        "constraint_mapping_complete": (
            constraint_mapping_complete if model_payload is not None else True
        ),
        "semantic_constraint_mapping_complete": (
            constraint_mapping_complete if model_payload is not None else True
        ),
        "semantic_constraint_claims_model_reported": model_payload is not None,
        "semantic_constraint_satisfaction_not_proven": True,
        "requires_internal_reader_or_ablation_validation": True,
        "macro_target_coverage_passed": macro_target_coverage_passed,
        "macro_materiality_passed": macro_materiality_passed,
        "active_transformation_targets_covered": list(
            coverage_report.get("active_targets_covered", [])
        ),
        "active_transformation_targets_missing": list(
            coverage_report.get("active_targets_missing", [])
        ),
        "ready_for_executed_ablation": bool(
            coverage_report.get("ready_for_executed_ablation")
        ),
        "target_coverage_report": coverage_report,
        "requires_executed_ablation_before_improvement_claim": True,
        "operator_approval_absent": True,
        "profile": "autonomous_creative_candidate",
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            (
                "semantic constraint satisfaction is not proven by structural "
                "model-output validation"
            ),
            "macro recomposition has not yet been tested by executed ablation",
            "strongest-rival pressure remains blocking",
            "internal operator approval is absent",
        ],
        "summary_verdict": (
            "Bounded macro recomposition produced a candidate for later executed "
            "ablation, but it is not final and makes no improvement claim."
        ),
        "worker": "macro_recomposition_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: MacroSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": subject.normalized_brief.target_movement,
        "target_scope": subject.normalized_brief.target_scope,
        "target_submovement": list(subject.normalized_brief.target_submovement),
        "reader_state_informed_brief": subject.normalized_brief.reader_state_informed,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "model": model,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "diff_report_artifact_id": artifacts["macro_recomposition_diff_report"].id,
        "rival_pressure_check_artifact_id": artifacts["macro_rival_pressure_check"].id,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "target_coverage_report": payloads["macro_recomposition_diff_report"].get(
            "target_coverage_report"
        ),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_packet_v1_controller",
    }


def _fake_recompose_text(subject: MacroSubject) -> RecomposedText:
    target = _target_window(subject.base_text)
    replacement = (
        _fake_reader_state_macro_2_replacement()
        if subject.normalized_brief.reader_state_informed
        else _fake_macro_1_replacement()
    )
    text = "\n\n".join([*target.unchanged_prefix, *replacement])
    return RecomposedText(
        text=text,
        target_start_index=target.target_start_index,
        target_end_index=target.target_end_index,
        unchanged_prefix=target.unchanged_prefix,
        original_target=target.original_target,
        replacement=replacement,
    )


def _model_recompose_text(
    subject: MacroSubject,
    model_payload: dict[str, object],
) -> RecomposedText:
    target = _target_window(subject.base_text)
    if subject.normalized_brief.reader_state_informed:
        replacement = _target_addressed_replacement_paragraphs(subject, model_payload)
    else:
        replacement_text = str(model_payload["replacement_section_text"]).strip()
        replacement = _paragraphs(replacement_text)
    text = "\n\n".join([*target.unchanged_prefix, *replacement])
    return RecomposedText(
        text=text,
        target_start_index=target.target_start_index,
        target_end_index=target.target_end_index,
        unchanged_prefix=target.unchanged_prefix,
        original_target=target.original_target,
        replacement=replacement,
    )


def _target_window(base_text: str) -> RecomposedText:
    paragraphs = _paragraphs(base_text)
    start = _target_start(paragraphs)
    return RecomposedText(
        text=base_text,
        target_start_index=start,
        target_end_index=len(paragraphs),
        unchanged_prefix=paragraphs[:start],
        original_target=paragraphs[start:],
        replacement=[],
    )


def _semantic_constraints() -> list[dict[str, str]]:
    descriptions = {
        "proof_from_inside_line": (
            "Proof must arise endogenously from the line or object sequence it "
            "integrates, not from a summary pasted over it."
        ),
        "cosmic_silence_as_isolation_condition": (
            "Cosmic silence/no outside answer must function as the formal "
            "isolation condition of proof, not as mere mood."
        ),
        "return_without_regression": (
            "The return must bring the opening back changed, not regress to an "
            "untouched starting point."
        ),
        "no_outside_answer_or_rescue": (
            "The replacement must not solve the pressure by importing rescue, "
            "answer, proof, or permission from outside the local field."
        ),
        "strongest_rival_pressure": (
            "The replacement must preserve strongest-rival pressure rather than "
            "claiming victory over it."
        ),
        "table_dust_spoon_saucer_local_field": (
            "The domestic table/dust/spoon/saucer field must remain the local "
            "causal field."
        ),
        "record_law_proof_answer_compression_preserved": (
            "The useful record/law/proof/answer compression from the selected "
            "base must be preserved or explicitly transformed by the macro brief."
        ),
    }
    return [
        {"constraint_id": constraint_id, "description": descriptions[constraint_id]}
        for constraint_id in REQUIRED_SEMANTIC_CONSTRAINT_IDS
    ]


def _active_transformation_targets(
    subject: MacroSubject,
    target: RecomposedText,
) -> list[dict[str, object]]:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    target_ids = subject.normalized_brief.active_transformation_target_ids
    target_ref_by_id = _active_target_ref_map(paragraph_refs, target_ids)
    descriptions = _active_target_descriptions()
    return [
        {
            "target_id": target_id,
            "description": descriptions[target_id],
            "target_paragraph_ref": target_ref_by_id[target_id],
            "material_change_required": (
                target_id in subject.normalized_brief.material_required_target_ids
            ),
        }
        for target_id in target_ids
    ]


def _active_target_descriptions() -> dict[str, str]:
    return {
        "middle_abstraction_ladder_compression": (
            "Compress the middle abstraction ladder into embodied object/event "
            "pressure rather than repeating explanatory scaffolding."
        ),
        "proof_line_redundancy_cleanup": (
            "Clean up proof-line redundancy by making proof arise through the "
            "replacement movement instead of repeating the proof label."
        ),
        "no_outside_answer_pressure_preservation": (
            "Preserve no-outside-answer pressure as a formal condition in the "
            "target section, not as a stated mood."
        ),
        "final_return_closure_embodiment": (
            "Embody the return closure as changed local relation rather than a "
            "summarizing ending."
        ),
        "object_event_pressure_without_pressure_naming": (
            "Carry pressure through object/event relations without merely naming "
            "pressure more often."
        ),
        "proof_no_outside_answer_refinement": (
            "Make proof and no-outside-answer pressure occur through the local "
            "object sequence rather than through visible thesis language."
        ),
        "final_return_echo_reread_strength": (
            "Strengthen the final return so rereading the opening changes its "
            "necessity without claiming closure."
        ),
        "thesis_visible_proof_language_reduction": (
            "Reduce proof-language that reads as commentary while preserving "
            "the proof function."
        ),
        "opening_return_transformation_strengthening": (
            "Make the return echo the opening as altered local relation, not as "
            "a summary of the architecture."
        ),
        "preserve_reader_state_partial_gain": (
            "Preserve the macro candidate's partial reader-state gain and local "
            "causal field while addressing remaining blockers."
        ),
    }


def _target_paragraph_specs(
    subject: MacroSubject,
    target: RecomposedText,
) -> list[dict[str, object]]:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    target_ref_by_id = _active_target_ref_map(
        paragraph_refs,
        subject.normalized_brief.active_transformation_target_ids,
    )
    descriptions = _active_target_descriptions()
    active_ids_by_ref: dict[str, list[str]] = {ref: [] for ref in paragraph_refs}
    for target_id in subject.normalized_brief.active_transformation_target_ids:
        target_ref = target_ref_by_id[target_id]
        refs = paragraph_refs if target_ref == "target_section" else [target_ref]
        for ref in refs:
            active_ids_by_ref.setdefault(ref, []).append(target_id)

    specs: list[dict[str, object]] = []
    material_ids = set(subject.normalized_brief.material_required_target_ids)
    protected = list(subject.normalized_brief.protected_effects)
    forbidden = list(subject.normalized_brief.forbidden_changes)
    for index, before_text in enumerate(target.original_target):
        ref = paragraph_refs[index]
        active_ids = _unique(active_ids_by_ref.get(ref, []))
        material_change_required = any(target_id in material_ids for target_id in active_ids)
        instruction_parts = [
            descriptions[target_id]
            for target_id in active_ids
            if target_id in descriptions and target_id in material_ids
        ]
        if not instruction_parts:
            instruction_parts = [
                descriptions[target_id]
                for target_id in active_ids
                if target_id in descriptions
            ]
        specs.append(
            {
                "target_paragraph_ref": ref,
                "before_text": before_text,
                "before_text_sha256": sha256_text(before_text),
                "word_count": len(_words(before_text)),
                "active_target_ids": active_ids,
                "material_change_required": material_change_required,
                "transformation_instruction": " ".join(instruction_parts)
                or "Preserve this paragraph unless the controller assigned a material target.",
                "protected_effects": protected,
                "forbidden_failures": forbidden,
            }
        )
    return specs


def _validate_live_macro_payload(
    *,
    subject: MacroSubject,
    payload: dict[str, object],
) -> None:
    _validate_section_plan(subject, payload)
    _validate_constraint_mapping(payload)
    _validate_active_target_mapping(
        payload,
        subject.normalized_brief.active_transformation_target_ids,
    )
    _validate_forbidden_live_macro_claims(payload)
    if subject.normalized_brief.reader_state_informed:
        replacement_paragraphs = _target_addressed_replacement_paragraphs(
            subject,
            payload,
        )
        _validate_replacement_text(subject, "\n\n".join(replacement_paragraphs))
    else:
        _validate_replacement_section(subject, payload)
        replacement_paragraphs = _paragraphs(str(payload["replacement_section_text"]))
    coverage_report = _build_target_coverage_report(
        subject,
        _target_window(subject.base_text),
        replacement_paragraphs,
        model_payload=payload,
    )
    if not coverage_report["macro_target_coverage_passed"]:
        missing = ", ".join(coverage_report["active_targets_missing"])
        raise ModelValidationError(f"macro target coverage failed: {missing}")
    if not coverage_report["macro_materiality_passed"]:
        raise ModelValidationError(
            "macro materiality failed: target section is insufficiently changed"
        )


def _fake_macro_1_replacement() -> list[str]:
    return [
        (
            "The deeper pattern does not arrive as a sentence placed over the room. "
            "It starts where the room is already busy: the ring drying lighter at "
            "one edge, the dust dragged into a narrow fan by a passing shoe, the "
            "spoon turning a small seam of light toward the cracked saucer. Each "
            "object keeps its own history, but none of the histories stays sealed. "
            "The table gathers them without becoming an explanation of them."
        ),
        (
            "Pressure enters through these crossings. The cup leaves the ring, the "
            "ring changes the wood, the dust records the shoe, and the shoe belongs "
            "to a body that had already left the kitchen before morning could name "
            "what happened. Nothing needs to announce a law. The law is the way one "
            "condition presses into the next until the boundary between them becomes "
            "visible enough to hurt."
        ),
        (
            "No answer comes from outside that pressure. The silence above the room "
            "is not a refusal of comfort added for mood; it is the condition that "
            "keeps the proof honest. If help arrived from beyond the line, the line "
            "would no longer have to carry what it had made. The table would become "
            "a prop in someone else's solution. Instead it stays local, and the "
            "local facts have to bear each other all the way through."
        ),
        (
            "So return cannot mean going back to the untouched table. The table was "
            "never untouched. The ring, the dust, the spoon, the saucer, the weak "
            "light, the small engine-hum of the refrigerator: they are not damage "
            "laid over a purer beginning. They are the beginning finding out what it "
            "was able to include. The room comes back to itself with the record "
            "still in it."
        ),
        (
            "In the morning, the table is still there. The dust is still under it. "
            "The spoon is still on its side. Nothing has been rescued from the room, "
            "and nothing has escaped into an answer elsewhere. Yet the facts no "
            "longer sit as separate proofs waiting to be named. They lean into one "
            "another, and the table holds the leaning: a small world returning, not "
            "unchanged, but with enough of its own pressure inside it to be read."
        ),
    ]


def _fake_reader_state_macro_2_replacement() -> list[str]:
    return [
        (
            "The room does not need a theorem added above it. The table keeps the "
            "ring where the cup had been, and the ring keeps changing as the wood "
            "dries around its edge. Dust still collects under the leg. The spoon "
            "still faces the saucer with its small dull glint. These marks do not "
            "argue; they hold one another close enough that the argument has to "
            "happen inside them."
        ),
        (
            "Proof begins there, in the way no mark can finish itself. The cup is "
            "gone, but the ring is not free of it. The shoe is gone, but the dust "
            "keeps the path. The hand is gone, but the spoon has remembered its "
            "turn toward the chipped rim. Nothing descends to certify the room. "
            "Each trace has to become the condition by which another trace can be "
            "read."
        ),
        (
            "That is why the silence above the room matters without becoming an "
            "announcement. It seals the kitchen inside its own evidence. No rescue "
            "arrives to explain the ring. No outside answer gathers the dust into "
            "meaning. If the line is going to prove anything, it must prove it by "
            "letting the table, the spoon, the saucer, and the morning light press "
            "on one another until their relation is the proof."
        ),
        (
            "The return therefore has to touch the first room again. The same table "
            "stands there, but the table is no longer only the place where objects "
            "were left. It is the place where absence has taken local shape. The "
            "ring is a boundary, the dust is a path, the spoon is an angle of use, "
            "and the saucer is the small rim against which the angle becomes "
            "visible."
        ),
        (
            "Morning does not solve this. It gives the room back with its evidence "
            "still inside it. The table is still there; the dust is still under it; "
            "the spoon still leans beside the saucer. What has changed is the way "
            "the beginning returns: not as a scene waiting for a lesson, but as the "
            "local field that already carried the lesson in its marks."
        ),
    ]


def _validate_section_plan(
    subject: MacroSubject,
    payload: dict[str, object],
) -> None:
    section_plan = payload.get("section_plan")
    if not isinstance(section_plan, dict):
        raise ModelValidationError("section_plan must be an object")
    target_movement = str(section_plan.get("target_movement") or "")
    if target_movement != subject.normalized_brief.target_movement:
        raise ModelValidationError("section_plan.target_movement must match controller target")
    if section_plan.get("bounded") is not True:
        raise ModelValidationError("section_plan.bounded must be true")
    if section_plan.get("full_rewrite") is not False:
        raise ModelValidationError("section_plan.full_rewrite must be false")


def _validate_constraint_mapping(payload: dict[str, object]) -> None:
    mapping = payload.get("constraint_mapping")
    if not isinstance(mapping, list):
        raise ModelValidationError("constraint_mapping must be a list")
    seen: set[str] = set()
    for item in mapping:
        if not isinstance(item, dict):
            raise ModelValidationError("constraint_mapping entries must be objects")
        constraint_id = str(item.get("constraint_id") or "")
        if constraint_id in seen:
            raise ModelValidationError(f"duplicate constraint_id: {constraint_id}")
        seen.add(constraint_id)
        excerpt = str(item.get("supporting_replacement_excerpt") or "").strip()
        if not excerpt:
            raise ModelValidationError(
                f"constraint_mapping[{constraint_id}] supporting excerpt is empty"
            )
    expected = set(REQUIRED_SEMANTIC_CONSTRAINT_IDS)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ModelValidationError(
            "constraint_mapping must contain exactly the required constraint IDs; "
            f"missing={missing}, extra={extra}"
        )


def _validate_active_target_mapping(
    payload: dict[str, object],
    expected_target_ids: tuple[str, ...],
) -> None:
    mapping = payload.get("active_target_mapping")
    if not isinstance(mapping, list):
        raise ModelValidationError("active_target_mapping must be a list")
    seen: set[str] = set()
    for item in mapping:
        if not isinstance(item, dict):
            raise ModelValidationError("active_target_mapping entries must be objects")
        target_id = str(item.get("target_id") or "")
        if target_id in seen:
            raise ModelValidationError(f"duplicate active target_id: {target_id}")
        seen.add(target_id)
        excerpt = str(item.get("supporting_replacement_excerpt") or "").strip()
        if not excerpt:
            raise ModelValidationError(
                f"active_target_mapping[{target_id}] supporting excerpt is empty"
            )
        unchanged = item.get("unchanged")
        if unchanged is True and not str(item.get("unchanged_justification") or "").strip():
            raise ModelValidationError(
                f"active_target_mapping[{target_id}] unchanged target requires justification"
            )
    expected = set(expected_target_ids)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ModelValidationError(
            "active_target_mapping must contain exactly the active target IDs; "
            f"missing={missing}, extra={extra}"
        )


def _constraint_mapping_complete(payload: dict[str, object]) -> bool:
    try:
        _validate_constraint_mapping(payload)
    except ModelValidationError:
        return False
    return True


def _active_target_mapping_complete(payload: dict[str, object]) -> bool:
    try:
        _validate_active_target_mapping(payload, ACTIVE_TRANSFORMATION_TARGET_IDS)
    except ModelValidationError:
        return False
    return True


def _active_target_mapping_complete_for_subject(
    subject: MacroSubject,
    payload: dict[str, object],
) -> bool:
    try:
        _validate_active_target_mapping(
            payload,
            subject.normalized_brief.active_transformation_target_ids,
        )
    except ModelValidationError:
        return False
    return True


def _build_target_coverage_report(
    subject: MacroSubject,
    target: RecomposedText,
    replacement_paragraphs: list[str],
    *,
    model_payload: dict[str, object] | None,
) -> dict[str, object]:
    paragraph_refs = _target_paragraph_refs(target.original_target)
    active_target_ids = subject.normalized_brief.active_transformation_target_ids
    material_required_ids = set(subject.normalized_brief.material_required_target_ids)
    target_ref_by_id = _active_target_ref_map(paragraph_refs, active_target_ids)
    paragraph_comparison = _paragraph_materiality_comparison(
        target.original_target,
        replacement_paragraphs,
    )
    material_refs = {
        str(row["target_paragraph_ref"])
        for row in paragraph_comparison
        if bool(row["materially_changed"])
    }
    unchanged_target_paragraphs = [
        row for row in paragraph_comparison if not bool(row["materially_changed"])
    ]
    mapping_by_target = _active_mapping_by_target(model_payload, active_target_ids)
    active_targets_covered: list[str] = []
    active_targets_missing: list[str] = []
    unchanged_with_justification: list[dict[str, object]] = []
    for target_id in active_target_ids:
        mapping = mapping_by_target.get(target_id)
        target_ref = target_ref_by_id[target_id]
        paragraph_material = (
            bool(material_refs)
            if target_ref == "target_section"
            else target_ref in material_refs
        )
        unchanged = bool(mapping.get("unchanged")) if mapping else False
        justification = str(mapping.get("unchanged_justification") or "") if mapping else ""
        if unchanged:
            unchanged_with_justification.append(
                {
                    "target_id": target_id,
                    "target_paragraph_ref": target_ref,
                    "justification": justification,
                }
            )
        covered = bool(mapping) and paragraph_material
        if (
            mapping
            and unchanged
            and target_id not in material_required_ids
            and justification.strip()
        ):
            covered = True
        if covered:
            active_targets_covered.append(target_id)
        else:
            active_targets_missing.append(target_id)
    materiality_required_count = min(
        len(paragraph_refs),
        max(2, (len(paragraph_refs) + 1) // 2),
    )
    materially_changed_count = len(material_refs)
    macro_materiality_passed = materially_changed_count >= materiality_required_count
    macro_target_coverage_passed = not active_targets_missing and macro_materiality_passed
    return {
        "target_paragraph_count": len(target.original_target),
        "replacement_paragraph_count": len(replacement_paragraphs),
        "materially_changed_target_paragraph_count": materially_changed_count,
        "unchanged_target_paragraph_count": len(unchanged_target_paragraphs),
        "paragraph_comparison": paragraph_comparison,
        "active_transformation_targets": list(active_target_ids),
        "active_targets_covered": active_targets_covered,
        "active_targets_missing": active_targets_missing,
        "unchanged_target_paragraphs_with_justification": unchanged_with_justification,
        "macro_target_coverage_passed": macro_target_coverage_passed,
        "controller_target_coverage_passed": macro_target_coverage_passed,
        "macro_materiality_passed": macro_materiality_passed,
        "active_target_mapping_complete": bool(model_payload)
        and _active_target_mapping_complete_for_subject(subject, model_payload),
        "model_active_target_mapping_complete": bool(model_payload)
        and _active_target_mapping_complete_for_subject(subject, model_payload),
        "ready_for_executed_ablation": macro_target_coverage_passed,
    }


def _paragraph_materiality_comparison(
    before_paragraphs: list[str],
    replacement_paragraphs: list[str],
) -> list[dict[str, object]]:
    rows = []
    for index, before in enumerate(before_paragraphs):
        after = replacement_paragraphs[index] if index < len(replacement_paragraphs) else ""
        before_words = _normalized_words(before)
        after_words = _normalized_words(after)
        materially_changed = _materially_changed_words(before_words, after_words)
        rows.append(
            {
                "target_paragraph_ref": _target_paragraph_ref(index),
                "before_sha256": sha256_text(before),
                "after_sha256": sha256_text(after),
                "before_word_count": len(before_words),
                "after_word_count": len(after_words),
                "normalized_text_equal": before_words == after_words,
                "materially_changed": materially_changed,
            }
        )
    return rows


def _materially_changed_words(before_words: list[str], after_words: list[str]) -> bool:
    if not before_words and not after_words:
        return False
    if before_words == after_words:
        return False
    before_counts = _word_counts(before_words)
    after_counts = _word_counts(after_words)
    overlap = sum(
        min(count, after_counts.get(word, 0)) for word, count in before_counts.items()
    )
    max_count = max(len(before_words), len(after_words), 1)
    changed_count = max_count - overlap
    changed_ratio = changed_count / max_count
    return changed_count >= 6 and changed_ratio >= 0.18


def _word_counts(words: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return counts


def _normalized_words(text: str) -> list[str]:
    words: list[str] = []
    current = []
    for character in text.lower():
        if character.isalnum():
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _active_mapping_by_target(
    model_payload: dict[str, object] | None,
    active_target_ids: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if not model_payload:
        return _fake_active_target_mapping(active_target_ids)
    mapping = model_payload.get("active_target_mapping", [])
    if not isinstance(mapping, list):
        return {}
    return {
        str(item.get("target_id")): item
        for item in mapping
        if isinstance(item, dict) and item.get("target_id")
    }


def _fake_active_target_mapping(
    active_target_ids: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    return {
        target_id: {
            "target_id": target_id,
            "unchanged": False,
            "unchanged_justification": "",
            "supporting_replacement_excerpt": "deterministic fake replacement section",
        }
        for target_id in active_target_ids
    }


def _target_paragraph_refs(paragraphs: list[str]) -> list[str]:
    return [_target_paragraph_ref(index) for index, _paragraph in enumerate(paragraphs)]


def _target_paragraph_ref(index: int) -> str:
    return f"target_p{index + 1:03d}"


def _active_target_ref_map(
    paragraph_refs: list[str],
    active_target_ids: tuple[str, ...],
) -> dict[str, str]:
    first_ref = paragraph_refs[0] if paragraph_refs else "target_section"
    second_ref = paragraph_refs[1] if len(paragraph_refs) > 1 else first_ref
    last_ref = paragraph_refs[-1] if paragraph_refs else "target_section"
    default_refs = {
        "middle_abstraction_ladder_compression": first_ref,
        "proof_line_redundancy_cleanup": second_ref,
        "no_outside_answer_pressure_preservation": second_ref,
        "final_return_closure_embodiment": last_ref,
        "object_event_pressure_without_pressure_naming": "target_section",
        "proof_no_outside_answer_refinement": second_ref,
        "final_return_echo_reread_strength": last_ref,
        "thesis_visible_proof_language_reduction": "target_section",
        "opening_return_transformation_strengthening": last_ref,
        "preserve_reader_state_partial_gain": "target_section",
    }
    return {target_id: default_refs.get(target_id, "target_section") for target_id in active_target_ids}


def _target_addressed_replacement_paragraphs(
    subject: MacroSubject,
    payload: dict[str, object],
) -> list[str]:
    target = _target_window(subject.base_text)
    specs = _target_paragraph_specs(subject, target)
    spec_by_ref = {str(spec["target_paragraph_ref"]): spec for spec in specs}
    replacements = payload.get("target_paragraph_replacements")
    if not isinstance(replacements, list):
        raise ModelValidationError(
            "target_paragraph_replacements is required for reader_state_informed_macro_2"
        )

    material_target_ids = set(subject.normalized_brief.material_required_target_ids)
    material_refs = {
        str(spec["target_paragraph_ref"])
        for spec in specs
        if bool(spec["material_change_required"])
    }
    seen_refs: dict[str, dict[str, object]] = {}
    covered_material_targets: set[str] = set()
    for item in replacements:
        if not isinstance(item, dict):
            raise ModelValidationError("target_paragraph_replacements entries must be objects")
        ref = str(item.get("target_paragraph_ref") or "")
        if ref not in spec_by_ref:
            raise ModelValidationError(f"unsupported target_paragraph_ref: {ref}")
        if ref in seen_refs:
            raise ModelValidationError(f"duplicate target_paragraph_ref: {ref}")
        spec = spec_by_ref[ref]
        before_hash = str(item.get("before_text_sha256") or "")
        if before_hash != spec["before_text_sha256"]:
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] before_text_sha256 mismatch"
            )
        replacement_text = str(item.get("replacement_text") or "").strip()
        if not replacement_text:
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] replacement_text is empty"
            )
        active_ids_covered = _string_tuple(item.get("active_target_ids_covered"))
        allowed_target_ids = set(_string_tuple(spec.get("active_target_ids")))
        unsupported = sorted(set(active_ids_covered) - allowed_target_ids)
        if unsupported:
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] covers unassigned active target IDs: "
                + ", ".join(unsupported)
            )
        before_words = _normalized_words(str(spec["before_text"]))
        after_words = _normalized_words(replacement_text)
        materially_changed = _materially_changed_words(before_words, after_words)
        if bool(spec["material_change_required"]) and not materially_changed:
            required_ids = sorted(allowed_target_ids & material_target_ids)
            raise ModelValidationError(
                f"target_paragraph_replacements[{ref}] copied or insufficiently changed "
                f"for material targets: {', '.join(required_ids)}"
            )
        if materially_changed:
            covered_material_targets.update(
                target_id for target_id in active_ids_covered if target_id in material_target_ids
            )
        seen_refs[ref] = item

    missing_refs = sorted(material_refs - set(seen_refs))
    if missing_refs:
        raise ModelValidationError(
            "missing target paragraph replacement: " + ", ".join(missing_refs)
        )
    missing_targets = sorted(material_target_ids - covered_material_targets)
    if missing_targets:
        raise ModelValidationError(
            "target paragraph replacements do not cover material active targets: "
            + ", ".join(missing_targets)
        )

    return [
        str(seen_refs[ref]["replacement_text"]).strip()
        if ref in seen_refs
        else str(spec_by_ref[ref]["before_text"])
        for ref in _target_paragraph_refs(target.original_target)
    ]


def _validate_replacement_section(
    subject: MacroSubject,
    payload: dict[str, object],
) -> None:
    replacement_text = str(payload.get("replacement_section_text") or "").strip()
    _validate_replacement_text(subject, replacement_text)


def _validate_replacement_text(subject: MacroSubject, replacement_text: str) -> None:
    if not replacement_text:
        raise ModelValidationError("replacement_section_text must not be empty")
    target = _target_window(subject.base_text)
    replacement_paragraphs = _paragraphs(replacement_text)
    if not replacement_paragraphs:
        raise ModelValidationError("replacement_section_text must contain paragraphs")
    prefix_text = "\n\n".join(target.unchanged_prefix).strip()
    opening = target.unchanged_prefix[0] if target.unchanged_prefix else ""
    replacement_lower = replacement_text.lower()
    if opening and replacement_text.startswith(opening[:80]):
        raise ModelValidationError(
            "replacement_section_text rewrites or repeats the controller-owned prefix"
        )
    if prefix_text and prefix_text[:160].lower() in replacement_lower:
        raise ModelValidationError(
            "replacement_section_text includes controller-owned prefix text"
        )
    if replacement_text.strip() == subject.base_text.strip():
        raise ModelValidationError("replacement_section_text must not be the full base text")


def _validate_forbidden_live_macro_claims(payload: dict[str, object]) -> None:
    text = _flatten_strings(payload).lower()
    forbidden_markers = {
        "final artifact": "final artifact claim",
        "finalization eligible": "finalization claim",
        "finalisation eligible": "finalization claim",
        "human validated": "human-validation claim",
        "phase-shift": "phase-shift claim",
        "phase shift": "phase-shift claim",
        "paper-ready": "paper-readiness claim",
        "outside rescue arrives": "outside-rescue violation",
        "rescued from outside": "outside-rescue violation",
        "answer arrives from outside": "outside-answer violation",
        "answer is supplied from outside": "outside-answer violation",
        "proof comes from outside": "proof-from-outside violation",
        "proof arrives from outside": "proof-from-outside violation",
        "proof is supplied from outside": "proof-from-outside violation",
        "discard the table": "local-field discard violation",
        "remove the table": "local-field discard violation",
        "without the table": "local-field discard violation",
        "discard the dust": "local-field discard violation",
        "discard the spoon": "local-field discard violation",
        "discard the saucer": "local-field discard violation",
    }
    for marker, reason in forbidden_markers.items():
        if marker in text:
            raise ModelValidationError(f"{reason}: {marker}")


def _flatten_strings(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_flatten_strings(child) for child in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten_strings(child) for child in value)
    return ""


def _load_base_candidate_payload(packet_dir: Path, packet_kind: str) -> dict[str, Any]:
    if packet_kind == "bounded_macro_recomposition":
        return _read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    if packet_kind == "ablation_informed_revision":
        return _read_payload(packet_dir / "cycle2_revised_candidate_text.json")
    if packet_kind == "autonomous_revision":
        return _read_payload(packet_dir / "revised_candidate_text.json")
    raise ValueError(f"unsupported selected best candidate packet kind: {packet_kind}")


def _source_parent_ids(
    connection: sqlite3.Connection,
    synthesis_packet_dir: Path,
    synthesis_artifact_ids: dict[object, object],
) -> list[str]:
    parent_ids = [str(value) for value in synthesis_artifact_ids.values() if isinstance(value, str)]
    packet_artifact = _artifact_for_path(
        connection,
        synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json",
    )
    if packet_artifact is not None:
        parent_ids.append(packet_artifact.id)
    return _unique(parent_ids)


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
    return row_to_artifact(row) if row is not None else None


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required artifact is missing: {path.name}")
    envelope = read_json_file(path)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"artifact payload is not an object: {path.name}")
    return payload


def _resolve_path(config: AbiConfig, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (config.root / path).resolve()


def _target_start(paragraphs: list[str]) -> int:
    if len(paragraphs) <= 1:
        return 0
    needles = (
        "There is a deeper pattern",
        "A line of life and mind",
        "That is why the sky",
    )
    for index, paragraph in enumerate(paragraphs):
        if any(needle in paragraph for needle in needles):
            return index
    return min(max(1, len(paragraphs) - 4), len(paragraphs) - 1)


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _words(text: str) -> list[str]:
    return [word for word in text.split() if word]


def _unique(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        value_text = str(value)
        if value_text not in result:
            result.append(value_text)
    return result


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value,)
    return ()


def _dict_value(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _gate_result(
    gate_name: str,
    passed: bool,
    blocking_defects: list[str] | None = None,
    *,
    record: bool = True,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "record": record,
        "blocking_defects": list(blocking_defects or ([] if passed else [f"{gate_name} is missing"])),
    }


def _refusal(
    *,
    message: str,
    synthesis_packet: Path,
    client_name: str | None = None,
    model: str | None = None,
) -> BoundedMacroRecompositionResult:
    payload = {
        "accepted": False,
        "refused": True,
        "client": client_name,
        "model": model,
        "synthesis_packet": str(synthesis_packet),
        "message": message,
        "counts": {"model_calls": 0},
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
    }
    return BoundedMacroRecompositionResult(exit_code=1, payload=payload)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
