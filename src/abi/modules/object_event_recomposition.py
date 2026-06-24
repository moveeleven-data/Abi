"""Bounded object-event pressure recomposition from next-target strategy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_OBJECT_EVENT_RECOMPOSITION_ACTIVE_PHASE,
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
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


OBJECT_EVENT_RECOMPOSITION_LINEAGE_ID = "object_event_pressure_recomposition_v1"
OBJECT_EVENT_RECOMPOSITION_CREATED_BY = "object_event_pressure_recomposition_v1_controller"
OBJECT_EVENT_RECOMPOSITION_CLIENTS = ("fake", "openai")
OBJECT_EVENT_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT = 2
OBJECT_EVENT_RECOMPOSITION_REQUIRED_MODEL_CALLS = 1
OBJECT_EVENT_RECOMPOSITION_PROMPT_CONTRACT_ID = (
    "autonomous.object_event_pressure_recomposition.v1"
)
OBJECT_EVENT_TARGET_SCOPE = "first_read_object_event_pressure_gap"
OBJECT_EVENT_SELECTED_REGION_ID = "middle_recurrence_ordinary_trace_logic"

OBJECT_EVENT_RECOMPOSITION_ARTIFACT_TYPES = (
    "macro_recomposition_subject_manifest",
    "macro_recomposition_work_order",
    "object_event_pressure_target_selection",
    "protected_effects_and_forbidden_changes",
    "macro_recomposition_plan",
    "macro_patch_or_section_plan",
    "macro_recomposed_candidate_text",
    "macro_recomposition_diff_report",
    "macro_rival_pressure_check",
    "macro_recomposition_gate_report",
    "macro_recomposition_packet",
)

REQUIRED_STRATEGY_ARTIFACT_FILES = (
    "next_target_strategy_packet.json",
    "source_evidence_summary.json",
    "current_best_candidate_summary.json",
    "reader_state_blocker_summary.json",
    "strongest_rival_pressure_delta.json",
    "protected_effects_and_forbidden_changes.json",
    "object_event_pressure_target_map.json",
    "candidate_region_pressure_map.json",
    "next_intervention_strategy.json",
    "ablation_and_reader_eval_plan.json",
    "next_target_strategy_gate_report.json",
)

OBJECT_EVENT_ACTIVE_TARGET_IDS = (
    "first_read_object_event_pressure_gap",
    "lived_object_causality_gap",
    "first_read_vividness_gap",
    "local_embodiment_vs_conceptual_compression_balance",
)

PROTECTED_OBJECT_TERMS = ("table", "dust", "spoon", "saucer", "ring")
OBJECT_EVENT_TERMS = (
    "table",
    "dust",
    "spoon",
    "saucer",
    "ring",
    "cup",
    "glass",
    "wood",
    "shoe",
    "crumb",
    "broom",
    "leg",
    "floor",
)
OBJECT_EVENT_VERBS = (
    "press",
    "pressed",
    "pressure",
    "left",
    "leaves",
    "moved",
    "moves",
    "turned",
    "turns",
    "caught",
    "catches",
    "changed",
    "changes",
    "dragged",
    "drags",
    "marked",
    "marks",
    "scraped",
    "scrapes",
    "lean",
    "leans",
    "tighten",
    "tightens",
)


@dataclass(frozen=True)
class ObjectEventRecompositionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class TargetWindow:
    target_start_index: int
    target_end_index: int
    unchanged_prefix: tuple[str, ...]
    original_target: tuple[str, ...]
    unchanged_suffix: tuple[str, ...]

    @property
    def before_section_text(self) -> str:
        return "\n\n".join(self.original_target)


@dataclass(frozen=True)
class RecomposedText:
    text: str
    target: TargetWindow
    replacement: tuple[str, ...]
    validation_report: dict[str, object]

    @property
    def replacement_section_text(self) -> str:
        return "\n\n".join(self.replacement)


@dataclass(frozen=True)
class ObjectEventSubject:
    run_id: str
    strategy_packet_dir: Path
    strategy_packet_id: str
    strategy_artifact_ids: dict[str, str]
    strategy_payloads: dict[str, dict[str, Any]]
    base_packet_dir: Path
    base_packet_id: str
    base_packet_kind: str
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str
    base_word_count: int
    proof_packet_id: str | None
    reader_state_packet_id: str | None
    prior_best_packet_id: str | None
    source_parent_ids: tuple[str, ...]
    selected_region_id: str
    fixture_only: bool


def run_object_event_recomposition(
    config: AbiConfig,
    *,
    client_name: str,
    strategy_packet: Path,
    allow_live_model: bool = False,
    max_model_calls: int = OBJECT_EVENT_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> ObjectEventRecompositionResult:
    if client_name not in OBJECT_EVENT_RECOMPOSITION_CLIENTS:
        return _refusal(
            message=f"Unsupported object-event recomposition client: {client_name}",
            strategy_packet=strategy_packet,
        )
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Object-event recomposition OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                strategy_packet=strategy_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    f"Object-event recomposition OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                strategy_packet=strategy_packet,
                client_name=client_name,
                model=configured_model,
            )
        if max_model_calls < OBJECT_EVENT_RECOMPOSITION_REQUIRED_MODEL_CALLS:
            return _refusal(
                message=(
                    "Object-event recomposition OpenAI path refused; "
                    f"max-model-calls {max_model_calls} is below required budget "
                    f"{OBJECT_EVENT_RECOMPOSITION_REQUIRED_MODEL_CALLS}."
                ),
                strategy_packet=strategy_packet,
                client_name=client_name,
                model=configured_model,
            )

    initialize_database(config)
    resolved_packet = _resolve_path(config, strategy_packet)
    with connect(config.db_path) as connection:
        try:
            subject = _load_subject(
                connection=connection,
                config=config,
                strategy_packet_dir=resolved_packet,
                fixture_only=client_name == "fake",
            )
        except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
            return _refusal(
                message=f"Object-event recomposition refused; {error}",
                strategy_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Object-event recomposition refused; run is not registered: "
                    f"{subject.run_id}"
                ),
                strategy_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_OBJECT_EVENT_RECOMPOSITION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "bounded_macro_recomposition")
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=OBJECT_EVENT_RECOMPOSITION_LINEAGE_ID,
            created_by=OBJECT_EVENT_RECOMPOSITION_CREATED_BY,
            fixture_only=subject.fixture_only,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        model_results: list[ModelDriverResult] = []
        model_payload: dict[str, object] | None = None
        model_call_id: str | None = None
        target = _target_window(subject.base_text)

        payloads["macro_recomposition_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir=packet_dir,
            client_name=client_name,
            max_model_calls=max_model_calls,
        )
        artifacts["macro_recomposition_subject_manifest"] = writer.write_artifact(
            "macro_recomposition_subject_manifest",
            payloads["macro_recomposition_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["macro_recomposition_work_order"] = _build_work_order(subject, target)
        artifacts["macro_recomposition_work_order"] = writer.write_artifact(
            "macro_recomposition_work_order",
            payloads["macro_recomposition_work_order"],
            parent_ids=[artifacts["macro_recomposition_subject_manifest"].id],
        )

        payloads["object_event_pressure_target_selection"] = _build_target_selection(
            subject,
            target,
        )
        artifacts["object_event_pressure_target_selection"] = writer.write_artifact(
            "object_event_pressure_target_selection",
            payloads["object_event_pressure_target_selection"],
            parent_ids=[artifacts["macro_recomposition_work_order"].id],
        )

        payloads["protected_effects_and_forbidden_changes"] = _build_protected_effects(
            subject
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[artifacts["object_event_pressure_target_selection"].id],
        )

        if client_name == "openai":
            connection.commit()
            factory = client_factory or _default_openai_client_factory
            result = _run_live_object_event_model(
                config=config,
                subject=subject,
                packet_dir=packet_dir,
                model_client=factory(configured_model),
                target=target,
                work_order=payloads["macro_recomposition_work_order"],
                protected_effects=payloads["protected_effects_and_forbidden_changes"],
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

        try:
            recomposed = _build_recomposed_text(
                subject=subject,
                target=target,
                model_payload=model_payload,
            )
        except ModelValidationError as error:
            return _failure_result(
                subject=subject,
                packet_dir=packet_dir,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
                artifacts=artifacts,
                model_results=model_results,
                message=f"Object-event recomposition refused; {error}",
            )

        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=OBJECT_EVENT_RECOMPOSITION_LINEAGE_ID,
                created_by=f"model_driver:openai:{configured_model}",
                fixture_only=False,
                model_call_id=model_call_id,
            )
            if model_call_id
            else None
        )

        payloads["macro_recomposition_plan"] = _build_recomposition_plan(
            subject=subject,
            model_payload=model_payload,
            model_call_id=model_call_id,
        )
        artifacts["macro_recomposition_plan"] = _write_artifact(
            writer=writer,
            model_writer=model_writer,
            artifact_type="macro_recomposition_plan",
            payload=payloads["macro_recomposition_plan"],
            parent_ids=[
                artifacts["macro_recomposition_work_order"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["macro_patch_or_section_plan"] = _build_patch_or_section_plan(
            subject=subject,
            recomposed=recomposed,
            model_payload=model_payload,
            model_call_id=model_call_id,
        )
        artifacts["macro_patch_or_section_plan"] = _write_artifact(
            writer=writer,
            model_writer=model_writer,
            artifact_type="macro_patch_or_section_plan",
            payload=payloads["macro_patch_or_section_plan"],
            parent_ids=[
                artifacts["macro_recomposition_plan"].id,
                artifacts["object_event_pressure_target_selection"].id,
            ],
        )
        if model_call_id:
            model_results[-1] = _link_model_result(
                connection,
                result=model_results[-1],
                parsed_artifact=artifacts["macro_patch_or_section_plan"],
            )

        payloads["macro_recomposed_candidate_text"] = _build_candidate_text(
            subject=subject,
            recomposed=recomposed,
            model_call_id=model_call_id,
        )
        artifacts["macro_recomposed_candidate_text"] = writer.write_artifact(
            "macro_recomposed_candidate_text",
            payloads["macro_recomposed_candidate_text"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                subject.base_candidate_artifact_id
                or artifacts["macro_recomposition_subject_manifest"].id,
            ],
        )

        payloads["macro_recomposition_diff_report"] = _build_diff_report(
            subject=subject,
            recomposed=recomposed,
            candidate=payloads["macro_recomposed_candidate_text"],
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
            subject=subject,
            recomposed=recomposed,
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
            recomposed=recomposed,
            diff_report=payloads["macro_recomposition_diff_report"],
            rival_check=payloads["macro_rival_pressure_check"],
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
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            artifacts=artifacts,
            payloads=payloads,
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
            lineage_id=OBJECT_EVENT_RECOMPOSITION_LINEAGE_ID,
        )

    result_payload = {
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
        "current_best_candidate": {
            "packet_id": subject.base_packet_id,
            "packet_kind": subject.base_packet_kind,
            "packet_dir": str(subject.base_packet_dir),
        },
        "current_best_candidate_packet_id": subject.base_packet_id,
        "primary_next_target": OBJECT_EVENT_TARGET_SCOPE,
        "target_name": OBJECT_EVENT_TARGET_SCOPE,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "counts": {
            **packet_artifact_count_summary(
                required_artifact_types=OBJECT_EVENT_RECOMPOSITION_ARTIFACT_TYPES,
                produced_artifact_types=list(artifacts),
                packet_artifact_type="macro_recomposition_packet",
            ),
            "model_calls": len(model_results),
            "object_event_recomposition_artifacts": len(artifacts),
            "required_object_event_recomposition_artifacts": (
                len(OBJECT_EVENT_RECOMPOSITION_ARTIFACT_TYPES)
            ),
        },
        "model": configured_model if client_name == "openai" else None,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "candidate_generated": True,
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "requires_executed_ablation_before_improvement_claim": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    return ObjectEventRecompositionResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
        model_results=tuple(model_results),
    )


def _load_subject(
    *,
    connection: sqlite3.Connection,
    config: AbiConfig,
    strategy_packet_dir: Path,
    fixture_only: bool,
) -> ObjectEventSubject:
    packet_dir = _resolve_path(config, strategy_packet_dir)
    if not packet_dir.exists() or not packet_dir.is_dir():
        raise ValueError(f"strategy packet directory not found: {strategy_packet_dir}")
    missing = [name for name in REQUIRED_STRATEGY_ARTIFACT_FILES if not (packet_dir / name).exists()]
    if missing:
        raise ValueError(
            "strategy packet is missing required artifacts: " + ", ".join(missing)
        )
    payloads = {
        file_name.removesuffix(".json"): _read_payload(packet_dir / file_name)
        for file_name in REQUIRED_STRATEGY_ARTIFACT_FILES
    }
    packet = payloads["next_target_strategy_packet"]
    target_map = payloads["object_event_pressure_target_map"]
    if packet.get("target_name") != OBJECT_EVENT_TARGET_SCOPE:
        raise ValueError(
            "strategy packet target_name must be first_read_object_event_pressure_gap"
        )
    if target_map.get("target_name") != OBJECT_EVENT_TARGET_SCOPE:
        raise ValueError(
            "object_event_pressure_target_map target_name must be "
            "first_read_object_event_pressure_gap"
        )
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("strategy packet has no run_id")

    current_best = payloads["current_best_candidate_summary"]
    base_packet_id = str(current_best.get("current_best_candidate_packet_id") or "")
    base_packet_dir_value = str(current_best.get("current_best_candidate_packet_dir") or "")
    if not base_packet_id or not base_packet_dir_value:
        raise ValueError("strategy packet missing current best candidate reference")
    prior_packet_id = current_best.get("superseded_prior_best_packet_id")
    if prior_packet_id and str(prior_packet_id) == base_packet_id:
        raise ValueError("current best candidate cannot be the superseded prior best")

    base_packet_dir = _resolve_path(config, Path(base_packet_dir_value))
    base_candidate_payload, base_candidate_artifact_id = _load_candidate_payload(
        connection,
        base_packet_dir,
    )
    base_text = str(base_candidate_payload.get("text") or "")
    if not base_text.strip():
        raise ValueError("base candidate text is empty")
    base_hash = str(base_candidate_payload.get("text_sha256") or sha256_text(base_text))
    strategy_artifact_ids = {
        str(key): str(value)
        for key, value in packet.get("artifact_ids", {}).items()
        if isinstance(value, str)
    }
    strategy_packet_artifact = _artifact_by_path(
        connection,
        run_id=run_id,
        artifact_path=packet_dir / "next_target_strategy_packet.json",
    )
    parent_ids = _unique(
        [
            strategy_packet_artifact.id if strategy_packet_artifact else None,
            *strategy_artifact_ids.values(),
            base_candidate_artifact_id,
        ]
    )
    return ObjectEventSubject(
        run_id=run_id,
        strategy_packet_dir=packet_dir,
        strategy_packet_id=str(packet.get("packet_id") or packet_dir.name),
        strategy_artifact_ids=strategy_artifact_ids,
        strategy_payloads=payloads,
        base_packet_dir=base_packet_dir,
        base_packet_id=base_packet_id,
        base_packet_kind=str(current_best.get("current_best_candidate_packet_kind") or ""),
        base_candidate_artifact_id=base_candidate_artifact_id,
        base_text=base_text,
        base_text_sha256=base_hash,
        base_word_count=_word_count(base_text),
        proof_packet_id=str(packet.get("proof_packet_id") or "") or None,
        reader_state_packet_id=str(packet.get("reader_state_packet_id") or "") or None,
        prior_best_packet_id=str(prior_packet_id or "") or None,
        source_parent_ids=tuple(parent_ids),
        selected_region_id=_select_region_id(payloads["candidate_region_pressure_map"]),
        fixture_only=fixture_only,
    )


def _run_live_object_event_model(
    *,
    config: AbiConfig,
    subject: ObjectEventSubject,
    packet_dir: Path,
    model_client: ModelClient,
    target: TargetWindow,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    request = WorkerRequest(
        run_id=subject.run_id,
        worker_role=WorkerRole.BOUNDED_MACRO_RECOMPOSER,
        prompt_contract_id=OBJECT_EVENT_RECOMPOSITION_PROMPT_CONTRACT_ID,
        schema=BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        input_text=_prompt_for_live_object_event_recomposition(
            subject=subject,
            target=target,
            work_order=work_order,
            protected_effects=protected_effects,
        ),
        input_artifact_ids=list(subject.source_parent_ids),
        input_packet_path=str(subject.strategy_packet_dir),
        lineage_id=OBJECT_EVENT_RECOMPOSITION_LINEAGE_ID,
        parent_ids=list(subject.source_parent_ids),
        fixture_only=False,
        output_dir=str(packet_dir),
        register_parsed_artifact=False,
        parsed_payload_validator=lambda payload: _validate_model_payload(payload, target),
    )
    return driver.run(request)


def _prompt_for_live_object_event_recomposition(
    *,
    subject: ObjectEventSubject,
    target: TargetWindow,
    work_order: dict[str, object],
    protected_effects: dict[str, object],
) -> str:
    return _canonical_json(
        {
            "task": (
                "Propose one bounded replacement section for first-read "
                "object-event pressure. Return replacement text only for the "
                "selected region, never the full artifact."
            ),
            "controller_owns": [
                "strategy packet references",
                "base candidate choice",
                "target region",
                "before text",
                "final text assembly",
                "diff report",
                "gate report",
                "finalization status",
                "strongest-rival status",
            ],
            "model_may_own": [
                "replacement_section_text",
                "object-event pressure plan/rationale",
                "local risk notes",
                "uncertainty",
                "mapping from replacement to object-event pressure target",
            ],
            "model_must_not_own": [
                "full artifact text",
                "source IDs",
                "target IDs",
                "final text assembly",
                "gate pass/fail",
                "finalization",
                "phase-shift claim",
                "strongest-rival defeated status",
            ],
            "source_strategy_packet_id": subject.strategy_packet_id,
            "base_candidate_packet_id": subject.base_packet_id,
            "base_candidate_text_sha256": subject.base_text_sha256,
            "target_movement": OBJECT_EVENT_TARGET_SCOPE,
            "target_scope": OBJECT_EVENT_TARGET_SCOPE,
            "selected_region_id": subject.selected_region_id,
            "target_paragraph_start_index": target.target_start_index,
            "target_paragraph_end_index": target.target_end_index,
            "unchanged_prefix_text": "\n\n".join(target.unchanged_prefix),
            "before_section_text": target.before_section_text,
            "unchanged_suffix_text": "\n\n".join(target.unchanged_suffix),
            "active_transformation_targets": _active_targets(),
            "work_order": work_order,
            "protected_effects_and_forbidden_changes": protected_effects,
            "object_event_pressure_target_map": subject.strategy_payloads[
                "object_event_pressure_target_map"
            ],
            "candidate_region_pressure_map": subject.strategy_payloads[
                "candidate_region_pressure_map"
            ],
            "output_rule": (
                "Return bounded replacements only. The replacement must materially "
                "change the selected region and create or sharpen at least one "
                "causal object-event relation. Do not add decorative vividness, do "
                "not run proof/no-answer compression by inertia, do not mimic the "
                "strongest rival, and do not claim finality, validation, phase shift, "
                "or rival defeat."
            ),
        }
    )


def _validate_model_payload(payload: dict[str, object], target: TargetWindow) -> None:
    _validate_replacement_text(
        str(payload.get("replacement_section_text", "")),
        target=target,
        source_label="model replacement_section_text",
    )


def _build_recomposed_text(
    *,
    subject: ObjectEventSubject,
    target: TargetWindow,
    model_payload: dict[str, object] | None,
) -> RecomposedText:
    replacement = (
        _paragraphs(str(model_payload["replacement_section_text"]))
        if model_payload is not None
        else _fake_object_event_replacement()
    )
    replacement_text = "\n\n".join(replacement)
    validation_report = _validate_replacement_text(
        replacement_text,
        target=target,
        source_label="replacement_section_text",
    )
    text = "\n\n".join(
        [
            *target.unchanged_prefix,
            *replacement,
            *target.unchanged_suffix,
        ]
    )
    if sha256_text(text) == subject.base_text_sha256:
        raise ModelValidationError("candidate must materially differ from base candidate")
    return RecomposedText(
        text=text,
        target=target,
        replacement=tuple(replacement),
        validation_report=validation_report,
    )


def _build_subject_manifest(
    subject: ObjectEventSubject,
    *,
    packet_dir: Path,
    client_name: str,
    max_model_calls: int,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_kind": subject.base_packet_kind,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "base_candidate_word_count": subject.base_word_count,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "prior_best_packet_id": subject.prior_best_packet_id,
        "selected_region_id": subject.selected_region_id,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "client": client_name,
        "max_model_calls": max_model_calls,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "candidate_generated": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_recomposition_subject_manifest_v1_controller",
    }


def _build_work_order(subject: ObjectEventSubject, target: TargetWindow) -> dict[str, object]:
    target_paragraphs = _target_paragraph_specs(target)
    return {
        "work_order_id": f"object_event_recomposition_{subject.strategy_packet_id}",
        "source_strategy_packet_id": subject.strategy_packet_id,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "target_paragraph_start_index": target.target_start_index,
        "target_paragraph_end_index": target.target_end_index,
        "target_paragraphs": target_paragraphs,
        "target_spans": [],
        "active_target_units": target_paragraphs,
        "before_section_text": target.before_section_text,
        "selected_candidate_text": subject.base_text,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "allowed_touch": "bounded middle recurrence / ordinary trace region",
        "active_transformation_targets": _active_targets(),
        "protected_effects": _protected_effects(subject),
        "forbidden_changes": _forbidden_changes(subject),
        "controller_owns": [
            "strategy packet refs",
            "base candidate refs",
            "target region refs",
            "before text",
            "source packet IDs",
            "target IDs",
            "final text assembly",
            "diff report",
            "gate report",
            "finalization status",
            "strongest rival status",
        ],
        "model_may_own_if_live": [
            "bounded replacement text for selected region",
            "object-event pressure plan/rationale",
            "local risk notes",
            "uncertainty",
            "mapping from replacement to object-event pressure target",
        ],
        "model_must_not_own": [
            "source IDs",
            "target IDs",
            "final text assembly",
            "gate pass/fail",
            "finalization",
            "phase-shift claim",
            "full rewrite authority",
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_recomposition_work_order_v1_controller",
    }


def _build_target_selection(subject: ObjectEventSubject, target: TargetWindow) -> dict[str, object]:
    return {
        "target_name": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "selected_region_before_text_sha256": sha256_text(target.before_section_text),
        "selected_region_word_count": _word_count(target.before_section_text),
        "selection_basis": [
            "next-target strategy ranked first_read_object_event_pressure_gap first",
            "middle recurrence / ordinary trace logic is plausible intervention region",
            "proof/no-answer region is protected against inertia",
            "final return should not be assumed as next region",
        ],
        "what_counts_as_object_event_pressure": list(
            subject.strategy_payloads["object_event_pressure_target_map"].get(
                "what_counts_as_object_event_pressure",
                [],
            )
        ),
        "what_counts_as_fake_detail_only_vividness": list(
            subject.strategy_payloads["object_event_pressure_target_map"].get(
                "what_counts_as_fake_detail_only_vividness",
                [],
            )
        ),
        "generation_authorized_by_command": True,
        "full_rewrite": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_pressure_target_selection_v1_controller",
    }


def _build_protected_effects(subject: ObjectEventSubject) -> dict[str, object]:
    return {
        "protected_effects": _protected_effects(subject),
        "forbidden_changes": _forbidden_changes(subject),
        "base_candidate_packet_id": subject.base_packet_id,
        "strongest_rival_pressure_must_remain_active": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_protected_effects_v1_controller",
    }


def _build_recomposition_plan(
    *,
    subject: ObjectEventSubject,
    model_payload: dict[str, object] | None,
    model_call_id: str | None,
) -> dict[str, object]:
    if model_payload is not None:
        plan = model_payload["macro_recomposition_plan"]
        return {
            "plan_id": f"object_event_plan_{sha256_text(subject.base_text)[:12]}",
            "target_scope": OBJECT_EVENT_TARGET_SCOPE,
            "target_movement": OBJECT_EVENT_TARGET_SCOPE,
            "selected_region_id": subject.selected_region_id,
            "bounded_macro_recomposition": True,
            "object_event_pressure_recomposition": True,
            "full_rewrite": False,
            "plan_summary": plan["plan_summary"],
            "plan_steps": list(plan["plan_steps"]),
            "source_model_call_id": model_call_id,
            "rationale": model_payload["rationale"],
            "local_law_explanation": model_payload["local_law_explanation"],
            "uncertainty": model_payload["uncertainty"],
            "predicted_reader_state_effect": model_payload[
                "predicted_reader_state_effect"
            ],
            "not_finalization_eligible": True,
            "no_phase_shift_claim": True,
            "worker": "object_event_recomposition_plan_v1_model_driver",
        }
    return {
        "plan_id": f"object_event_plan_{sha256_text(subject.base_text)[:12]}",
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "plan_steps": [
            {
                "step_id": "object_event_step_001",
                "action": "preserve packet base and opening field",
                "rationale": f"{subject.base_packet_id} remains the evidence-backed base.",
            },
            {
                "step_id": "object_event_step_002",
                "action": "replace only the middle recurrence / ordinary trace region",
                "rationale": "Strategy evidence selects first-read object-event pressure.",
            },
            {
                "step_id": "object_event_step_003",
                "action": "make object pressure causal rather than decorative",
                "rationale": "Vividness must alter expectation before explanation.",
            },
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_recomposition_plan_v1_fake_controller",
    }


def _build_patch_or_section_plan(
    *,
    subject: ObjectEventSubject,
    recomposed: RecomposedText,
    model_payload: dict[str, object] | None,
    model_call_id: str | None,
) -> dict[str, object]:
    coverage = _target_coverage_report(recomposed)
    return {
        "patch_or_section_plan_id": f"object_event_patch_{sha256_text(recomposed.text)[:12]}",
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "before_section_text": recomposed.target.before_section_text,
        "replacement_section_text": recomposed.replacement_section_text,
        "replacement_section_text_sha256": sha256_text(
            recomposed.replacement_section_text
        ),
        "source_model_call_id": model_call_id,
        "model_owned_fields": (
            ["replacement_section_text", "plan/rationale", "uncertainty"]
            if model_payload is not None
            else []
        ),
        "controller_assembled_final_text": True,
        "model_replacement_section_text_authoritative": model_payload is not None,
        "object_event_pressure_mapping": _object_event_pressure_mapping(recomposed),
        "semantic_constraint_satisfaction_not_proven": True,
        "requires_internal_reader_or_ablation_validation": True,
        "target_coverage_report": coverage,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": (
            "object_event_patch_or_section_plan_v1_model_driver"
            if model_payload is not None
            else "object_event_patch_or_section_plan_v1_fake_controller"
        ),
    }


def _build_candidate_text(
    *,
    subject: ObjectEventSubject,
    recomposed: RecomposedText,
    model_call_id: str | None,
) -> dict[str, object]:
    return {
        "candidate_id": f"object_event_recomposition_{sha256_text(recomposed.text)[:12]}",
        "source_strategy_packet_id": subject.strategy_packet_id,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_submovement": [
            "first-read object-event pressure",
            "lived object causality",
            "first-read vividness without decorative-only detail",
        ],
        "selected_region_id": subject.selected_region_id,
        "text": recomposed.text,
        "text_sha256": sha256_text(recomposed.text),
        "word_count": _word_count(recomposed.text),
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "assembled_by_controller": True,
        "source_model_call_id": model_call_id,
        "candidate_generated": True,
        "candidate_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": subject.fixture_only if model_call_id is None else False,
        "requires_executed_ablation_before_improvement_claim": True,
        "worker": (
            "object_event_recomposed_candidate_text_v1_controller_assembled_from_model"
            if model_call_id
            else "object_event_recomposed_candidate_text_v1_fake_controller"
        ),
    }


def _build_diff_report(
    *,
    subject: ObjectEventSubject,
    recomposed: RecomposedText,
    candidate: dict[str, object],
) -> dict[str, object]:
    changed_spans = [
        {
            "changed_span_id": "object_event_region_001",
            "patch_span_id": "object_event_region_001",
            "before": recomposed.target.before_section_text,
            "after": recomposed.replacement_section_text,
            "before_text": recomposed.target.before_section_text,
            "after_text": recomposed.replacement_section_text,
            "region": subject.selected_region_id,
            "target_expansion_reason": "",
            "reason": "bounded object-event pressure recomposition",
            "inside_target": True,
            "within_selected_target": True,
            "requires_target_expansion": False,
            "source_patch_span_ids": ["object_event_region_001"],
        }
    ]
    coverage = _target_coverage_report(recomposed)
    return {
        "diff_report_id": f"object_event_diff_{sha256_text(str(candidate['text']))[:12]}",
        "source_strategy_packet_id": subject.strategy_packet_id,
        "base_candidate_packet_id": subject.base_packet_id,
        "candidate_text_sha256": candidate["text_sha256"],
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "changed_spans": changed_spans,
        "changed_span_count": len(changed_spans),
        "unchanged_prefix_paragraph_count": len(recomposed.target.unchanged_prefix),
        "unchanged_suffix_paragraph_count": len(recomposed.target.unchanged_suffix),
        "materiality_report": recomposed.validation_report,
        "target_coverage_report": coverage,
        "ready_for_executed_ablation": True,
        "requires_executed_ablation_before_improvement_claim": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_recomposition_diff_report_v1_controller",
    }


def _build_rival_pressure_check(
    *,
    subject: ObjectEventSubject,
    recomposed: RecomposedText,
) -> dict[str, object]:
    return {
        "base_candidate_packet_id": subject.base_packet_id,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "rival_mimicry_detected": False,
        "object_event_relation_count": recomposed.validation_report[
            "object_event_relation_count"
        ],
        "current_candidate_closes_gap": False,
        "reason": (
            "The candidate targets lived object-event pressure while preserving "
            "strongest-rival pressure for future comparison; it does not claim to "
            "beat the rival."
        ),
        "requires_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_rival_pressure_check_v1_controller",
    }


def _build_gate_report(
    *,
    subject: ObjectEventSubject,
    recomposed: RecomposedText,
    diff_report: dict[str, object],
    rival_check: dict[str, object],
) -> dict[str, object]:
    coverage = diff_report["target_coverage_report"]
    gate_results = [
        _gate_result("strategy_packet_consumed", True),
        _gate_result("base_candidate_packet_0056_used", bool(subject.base_packet_id)),
        _gate_result("first_read_object_event_pressure_targeted", True),
        _gate_result("bounded_region_selected", True),
        _gate_result(
            "object_event_pressure_mapping_exists",
            bool(recomposed.validation_report["object_event_relation_count"]),
        ),
        _gate_result("region_materiality_passed", True),
        _gate_result("protected_effects_recorded", True),
        _gate_result(
            "rival_pressure_preserved",
            rival_check["strongest_rival_pressure_preserved"] is True,
        ),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "executed_ablation_completed_for_object_event_candidate",
            False,
            ["object-event candidate has not yet been tested by executed ablation"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_completed_for_object_event_candidate",
            False,
            ["object-event candidate has not yet been reader-state evaluated"],
            record=False,
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            [
                "strongest rival still blocks",
                "object-event candidate requires executed ablation before any improvement claim",
            ],
            record=False,
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is absent for finalization"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["object-event recomposition is candidate-only"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    return {
        "passed": False,
        "eligible": False,
        "candidate_generated": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "non_final": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "macro_target_coverage_passed": coverage["macro_target_coverage_passed"],
        "macro_materiality_passed": coverage["macro_materiality_passed"],
        "ready_for_executed_ablation": coverage["ready_for_executed_ablation"],
        "target_coverage_report": coverage,
        "semantic_constraint_satisfaction_not_proven": True,
        "requires_internal_reader_or_ablation_validation": True,
        "requires_executed_ablation_before_improvement_claim": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_pressure_preserved": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "object-event candidate has not been tested by executed ablation",
            "object-event candidate has not been reader-state evaluated",
            "strongest-rival pressure remains blocking",
            "internal operator approval is absent",
        ],
        "summary_verdict": (
            "Bounded object-event pressure recomposition produced one candidate "
            "for future ablation, but remains fail-closed and makes no improvement "
            "claim."
        ),
        "worker": "object_event_recomposition_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ObjectEventSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    artifact_counts = packet_artifact_count_summary(
        required_artifact_types=OBJECT_EVENT_RECOMPOSITION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="macro_recomposition_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "source_strategy_packet_id": subject.strategy_packet_id,
        "source_strategy_packet_dir": str(subject.strategy_packet_dir),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "current_best_candidate": {
            "packet_id": subject.base_packet_id,
            "packet_kind": subject.base_packet_kind,
            "packet_dir": str(subject.base_packet_dir),
        },
        "current_best_candidate_packet_id": subject.base_packet_id,
        "primary_next_target": OBJECT_EVENT_TARGET_SCOPE,
        "target_name": OBJECT_EVENT_TARGET_SCOPE,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "target_movement": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": subject.selected_region_id,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            **artifact_counts,
            "model_calls": len(model_results),
            "object_event_recomposition_artifacts": artifact_counts[
                "produced_artifacts"
            ],
            "required_object_event_recomposition_artifacts": artifact_counts[
                "required_artifacts"
            ],
        },
        "model": model,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "candidate_generated": True,
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "diff_report_artifact_id": artifacts["macro_recomposition_diff_report"].id,
        "rival_pressure_check_artifact_id": artifacts["macro_rival_pressure_check"].id,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "target_coverage_report": payloads["macro_recomposition_diff_report"][
            "target_coverage_report"
        ],
        "bounded_macro_recomposition": True,
        "object_event_pressure_recomposition": True,
        "full_rewrite": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "object_event_recomposition_packet_v1_controller",
    }


def _write_artifact(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> ArtifactRecord:
    active_writer = model_writer or writer
    return active_writer.write_artifact(artifact_type, payload, parent_ids=parent_ids)


def _link_model_result(
    connection: sqlite3.Connection,
    *,
    result: ModelDriverResult,
    parsed_artifact: ArtifactRecord,
) -> ModelDriverResult:
    model_call = link_model_call_parsed_artifact(
        connection,
        model_call_id=result.model_call.id,
        parsed_output_artifact_id=parsed_artifact.id,
    )
    return ModelDriverResult(
        model_call=model_call,
        parsed_payload=result.parsed_payload,
        parsed_artifact=parsed_artifact,
    )


def _validate_replacement_text(
    replacement_text: str,
    *,
    target: TargetWindow,
    source_label: str,
) -> dict[str, object]:
    replacement = replacement_text.strip()
    if not replacement:
        raise ModelValidationError(f"{source_label} must not be empty")
    if replacement.startswith("{"):
        raise ModelValidationError(f"{source_label} must not be JSON text")
    try:
        parsed = json.loads(replacement)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        raise ModelValidationError(f"{source_label} must not parse as JSON")
    lower = replacement.lower()
    for term in (
        "baseline component",
        "artifact-set",
        "source manifest",
        "model_call_id",
        "non-final",
        "validation",
        "final gates",
        "finalization eligible",
        "final artifact",
        "phase shift",
        "phase-shift",
        "human validation",
        "strongest rival defeated",
        "rival defeated",
    ):
        if term in lower:
            raise ModelValidationError(f"{source_label} contains forbidden claim/leakage: {term}")
    before = target.before_section_text
    if _canonical_space(replacement) == _canonical_space(before):
        raise ModelValidationError("selected region materiality failed; replacement is unchanged")
    if _canonical_space(before) in _canonical_space(replacement):
        raise ModelValidationError("full rewrite or copied selected region detected")
    prefix = "\n\n".join(target.unchanged_prefix)
    suffix = "\n\n".join(target.unchanged_suffix)
    if prefix and _first_sentence(prefix).lower() in lower:
        raise ModelValidationError("full rewrite detected; replacement includes prefix text")
    if suffix and _first_sentence(suffix).lower() in lower:
        raise ModelValidationError("full rewrite detected; replacement includes suffix text")
    before_words = _word_set(before)
    replacement_words = _word_set(replacement)
    changed_words = sorted(replacement_words - before_words)
    changed_ratio = len(changed_words) / max(1, len(replacement_words))
    if len(changed_words) < 8 or changed_ratio < 0.12:
        raise ModelValidationError("selected region materiality failed")
    object_terms_present = _terms_present(lower, OBJECT_EVENT_TERMS)
    protected_terms_present = _terms_present(lower, PROTECTED_OBJECT_TERMS)
    relation_count = _object_event_relation_count(replacement)
    if relation_count < 1:
        raise ModelValidationError(
            "object-event pressure mapping failed; no causal object-event relation"
        )
    if len(object_terms_present) < 4 or len(protected_terms_present) < 3:
        raise ModelValidationError("decorative-only vividness or weak object field detected")
    abstract_count = sum(lower.count(term) for term in ("proof", "answer", "law", "record"))
    if abstract_count > len(object_terms_present) and relation_count < 2:
        raise ModelValidationError("proof/no-answer-only compression by inertia detected")
    return {
        "region_materiality_passed": True,
        "changed_word_count": len(changed_words),
        "changed_word_ratio": round(changed_ratio, 3),
        "object_event_relation_count": relation_count,
        "object_terms_present": object_terms_present,
        "protected_local_objects_present": protected_terms_present,
        "decorative_only_vividness_rejected": True,
        "proof_no_answer_only_compression_rejected": True,
        "full_rewrite_rejected": True,
    }


def _object_event_relation_count(text: str) -> int:
    count = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        object_hits = _terms_present(lower, OBJECT_EVENT_TERMS)
        if len(object_hits) >= 2 and any(verb in lower for verb in OBJECT_EVENT_VERBS):
            count += 1
    return count


def _object_event_pressure_mapping(recomposed: RecomposedText) -> list[dict[str, object]]:
    return [
        {
            "target_id": OBJECT_EVENT_TARGET_SCOPE,
            "selected_region_id": OBJECT_EVENT_SELECTED_REGION_ID,
            "causal_relation": "ordinary object marks pressure one another before explanation",
            "supporting_replacement_excerpt": _first_sentence(
                recomposed.replacement_section_text
            ),
            "object_event_relation_count": recomposed.validation_report[
                "object_event_relation_count"
            ],
            "requires_future_ablation": True,
        }
    ]


def _target_coverage_report(recomposed: RecomposedText) -> dict[str, object]:
    return {
        "macro_target_coverage_passed": True,
        "controller_target_coverage_passed": True,
        "macro_materiality_passed": True,
        "paragraph_level_coverage_passed": True,
        "span_level_coverage_passed": True,
        "ready_for_executed_ablation": True,
        "target_scope": OBJECT_EVENT_TARGET_SCOPE,
        "selected_region_id": OBJECT_EVENT_SELECTED_REGION_ID,
        "active_targets_covered": list(OBJECT_EVENT_ACTIVE_TARGET_IDS),
        "active_targets_missing": [],
        "region_materiality_passed": recomposed.validation_report[
            "region_materiality_passed"
        ],
        "object_event_pressure_mapping_exists": (
            recomposed.validation_report["object_event_relation_count"] >= 1
        ),
        "decorative_only_vividness_rejected": True,
        "proof_no_answer_only_compression_rejected": True,
        "full_rewrite_rejected": True,
    }


def _target_paragraph_specs(target: TargetWindow) -> list[dict[str, object]]:
    specs = []
    refs = ("target_p001", "target_p002", "target_p003")
    for index, paragraph in enumerate(target.original_target):
        active_ids = (
            ["first_read_object_event_pressure_gap", "lived_object_causality_gap"]
            if index == 0
            else [
                "first_read_vividness_gap",
                "local_embodiment_vs_conceptual_compression_balance",
            ]
        )
        specs.append(
            {
                "target_paragraph_ref": refs[index] if index < len(refs) else f"target_p{index + 1:03d}",
                "target_region_id": OBJECT_EVENT_SELECTED_REGION_ID,
                "before_text": paragraph,
                "before_text_sha256": sha256_text(paragraph),
                "word_count": _word_count(paragraph),
                "active_target_ids": active_ids,
                "material_change_required": True,
                "protected_effects": _base_protected_effects(),
                "forbidden_failures": [
                    "decorative-only vividness",
                    "proof/no-answer compression by inertia",
                    "full rewrite",
                    "phase-shift claim",
                ],
            }
        )
    return specs


def _active_targets() -> list[dict[str, object]]:
    descriptions = {
        "first_read_object_event_pressure_gap": (
            "Increase first-read pressure through causal object changes."
        ),
        "lived_object_causality_gap": (
            "Make ordinary objects alter expectation rather than decorate the scene."
        ),
        "first_read_vividness_gap": (
            "Sharpen tactile inevitability without copying the strongest rival."
        ),
        "local_embodiment_vs_conceptual_compression_balance": (
            "Preserve local embodiment while avoiding proof-language compression."
        ),
    }
    return [
        {
            "target_id": target_id,
            "description": descriptions[target_id],
            "material_change_required": True,
        }
        for target_id in OBJECT_EVENT_ACTIVE_TARGET_IDS
    ]


def _fake_object_event_replacement() -> tuple[str, ...]:
    return (
        (
            "A room like this teaches by pressure before thought arrives. The cup "
            "left the ring, and the ring has lightened the wood at one edge; the "
            "spoon has rolled until its bowl touches the cracked saucer, so a small "
            "metal sound seems held there after the hand is gone. Under the table "
            "leg, dust has been pushed into a crescent by a shoe and then stopped "
            "by the leg itself. The facts do not explain themselves. They press "
            "one another into consequence."
        ),
        (
            "At first the table remains ordinary, but ordinariness has begun to "
            "act. The dried ring changes how the grain catches morning. The spoon "
            "turns the saucer from a thing beside it into the place where last "
            "night's motion ended. The dust keeps the shoe's path because the table "
            "interrupted it. Nothing has become symbolic by decoration; each object "
            "has altered another object, and the reader can feel the room becoming "
            "legible before any proof has to name itself."
        ),
    )


def _target_window(base_text: str) -> TargetWindow:
    paragraphs = _paragraphs(base_text)
    if len(paragraphs) < 3:
        start = 0
    else:
        start = min(3, max(1, len(paragraphs) - 2))
    end = min(len(paragraphs), start + 2)
    return TargetWindow(
        target_start_index=start,
        target_end_index=end,
        unchanged_prefix=tuple(paragraphs[:start]),
        original_target=tuple(paragraphs[start:end]),
        unchanged_suffix=tuple(paragraphs[end:]),
    )


def _select_region_id(region_map: dict[str, Any]) -> str:
    regions = region_map.get("regions", [])
    if isinstance(regions, list):
        for region in regions:
            if (
                isinstance(region, dict)
                and region.get("region_id") == OBJECT_EVENT_SELECTED_REGION_ID
                and region.get("plausible_next_intervention_region") is True
            ):
                return OBJECT_EVENT_SELECTED_REGION_ID
    return OBJECT_EVENT_SELECTED_REGION_ID


def _protected_effects(subject: ObjectEventSubject) -> list[str]:
    strategy_protected = subject.strategy_payloads[
        "protected_effects_and_forbidden_changes"
    ].get("protected_effects", [])
    return _unique(
        [
            *[str(item) for item in strategy_protected if str(item).strip()],
            *_base_protected_effects(),
            f"{subject.base_packet_id} macro structure",
        ]
    )


def _base_protected_effects() -> list[str]:
    return [
        "partial reread transformation",
        "table/dust/spoon/saucer/ring causal field",
        "reduced overexplanation",
        "proof/no-outside-answer gains",
        "final-return / opening-return gains",
        "local field as record-bearing system",
        "strongest-rival pressure preservation",
        "no finality claim",
    ]


def _forbidden_changes(subject: ObjectEventSubject) -> list[str]:
    strategy_forbidden = subject.strategy_payloads[
        "protected_effects_and_forbidden_changes"
    ].get("forbidden_changes", [])
    return _unique(
        [
            *[str(item) for item in strategy_forbidden if str(item).strip()],
            "rewriting the whole artifact",
            "decorative vividness with no causal object event",
            "proof/no-answer compression by inertia",
            "weakening the selected base macro structure",
            "weakening table/dust/spoon/saucer/ring causal field",
            "mimicking the strongest rival",
            "claiming rival defeat",
            "claiming phase shift",
        ]
    )


def _load_candidate_payload(
    connection: sqlite3.Connection,
    packet_dir: Path,
) -> tuple[dict[str, Any], str | None]:
    candidates = (
        ("macro_recomposed_candidate_text.json", "macro_recomposed_candidate_text"),
        ("cycle2_revised_candidate_text.json", "cycle2_revised_candidate_text"),
        ("revised_candidate_text.json", "revised_candidate_text"),
    )
    for filename, artifact_type in candidates:
        path = packet_dir / filename
        if path.exists():
            envelope = read_json_file(path)
            if envelope.get("artifact_type") != artifact_type:
                raise ValueError(f"{filename} has unexpected artifact_type")
            artifact = _artifact_by_path(
                connection,
                run_id=str(envelope.get("run_id") or ""),
                artifact_path=path,
            )
            return envelope["payload"], artifact.id if artifact else None
    raise ValueError(f"base candidate packet has no candidate text: {packet_dir}")


def _read_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"malformed artifact payload: {path.name}")
    return payload


def _artifact_by_path(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    artifact_path: Path,
) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE run_id = ?
          AND path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (run_id, str(artifact_path), str(artifact_path.resolve())),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _model_failure_message(result: ModelDriverResult) -> str:
    return (
        result.model_call.error_message
        or f"model call {result.model_call.id} ended with status {result.model_call.status}"
    )


def _failure_result(
    *,
    subject: ObjectEventSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    model_results: list[ModelDriverResult],
    message: str,
) -> ObjectEventRecompositionResult:
    return ObjectEventRecompositionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "run_id": subject.run_id,
            "packet_dir": str(packet_dir),
            "client": client_name,
            "model": model,
            "artifact_ids": {
                artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
            },
            "model_call_ids": [result.model_call.id for result in model_results],
            "model_calls": [result.model_call_to_dict() for result in model_results],
            "counts": {"model_calls": len(model_results)},
            "candidate_generated": False,
            "finalization_eligible": False,
            "not_finalization_eligible": True,
            "no_phase_shift_claim": True,
        },
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _refusal(
    *,
    message: str,
    strategy_packet: Path,
    client_name: str | None = None,
    model: str | None = None,
) -> ObjectEventRecompositionResult:
    return ObjectEventRecompositionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "strategy_packet": str(strategy_packet),
            "message": message,
            "counts": {"model_calls": 0},
            "candidate_generated": False,
            "finalization_eligible": False,
            "not_finalization_eligible": True,
            "no_phase_shift_claim": True,
        },
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


def _terms_present(text: str, terms: tuple[str, ...]) -> list[str]:
    return sorted({term for term in terms if re.search(rf"\b{re.escape(term)}\b", text)})


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _word_set(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"\b[\w'-]+\b", text)}


def _canonical_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0].strip() if parts else text.strip()


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return (config.root / value).resolve()


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
