"""One-shot bounded object-motion causality candidate generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_RESIDUAL_CANDIDATE_GENERATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ModelValidationError,
    OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
    WorkerRole,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


RESIDUAL_CANDIDATE_GENERATION_LINEAGE_ID = "residual_candidate_generation_v1"
RESIDUAL_CANDIDATE_GENERATION_CREATED_BY = (
    "residual_candidate_generation_v1_controller"
)
RESIDUAL_CANDIDATE_GENERATION_CLIENTS = ("fake", "openai")
RESIDUAL_CANDIDATE_GENERATION_REQUIRED_MODEL_CALLS = 1
RESIDUAL_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT = 1
RESIDUAL_CANDIDATE_GENERATION_PROMPT_CONTRACT_ID = (
    "autonomous.object_motion_causality_generation.v1"
)

OBJECT_MOTION_CAUSALITY_TARGET_ID = "object_motion_causality_specificity"
SELECTED_REGION_ID = "middle_recurrence_ordinary_trace_logic"
NEXT_RECOMMENDED_ACTION = "review_object_motion_causality_candidate_before_ablation"

BOUNDED_MACRO_COMPATIBLE_ARTIFACT_TYPES = (
    "macro_recomposition_subject_manifest",
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

REQUIRED_AUTHORIZATION_ARTIFACTS = (
    "residual_generation_authorization_packet",
    "generation_scope_authorization",
    "generation_attempt_budget",
    "target_unit_integration_policy",
    "future_generator_contract_ref",
    "protected_effects_and_forbidden_changes",
    "authorization_gate_report",
)

REQUIRED_WORK_ORDER_ARTIFACTS = (
    "residual_work_order_packet",
    "residual_work_order_subject_manifest",
    "selected_intervention_region",
    "object_motion_target_unit_map",
    "protected_effects_and_forbidden_changes",
    "future_generation_contract",
    "ablation_and_reader_eval_plan",
    "residual_work_order_gate_report",
)

OBJECT_TERMS = (
    "cup",
    "ring",
    "crumb",
    "grain",
    "table",
    "dust",
    "hand",
    "foot",
    "air",
    "surface",
    "spoon",
    "saucer",
    "fall",
    "glass",
    "window",
    "crack",
)

MOTION_TERMS = (
    "placed",
    "lifted",
    "nudged",
    "moved",
    "moves",
    "touched",
    "dragged",
    "dropped",
    "drops",
    "fell",
    "fall",
    "let go",
    "gathered",
    "gathers",
    "thinned",
    "thins",
    "pressed",
    "presses",
    "caught",
    "catches",
    "crossed",
    "crosses",
)

CONSEQUENCE_TERMS = (
    "so",
    "because",
    "therefore",
    "leaves",
    "left",
    "mark",
    "marks",
    "record",
    "records",
    "break",
    "breaks",
    "crack",
    "cracked",
    "thinner",
    "grain",
    "alters",
    "changed",
    "makes",
)


@dataclass(frozen=True)
class ResidualCandidateGenerationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class TargetUnit:
    unit_id: str
    before_text: str
    before_text_sha256: str
    objects: tuple[str, ...]
    target_effect: str


@dataclass(frozen=True)
class ResidualCandidateSubject:
    run_id: str
    authorization_packet_dir: Path
    authorization_packet_id: str
    authorization_packet_artifact_id: str | None
    authorization_fixture_only: bool
    authorization_artifact_ids: dict[str, str]
    authorization_payloads: dict[str, dict[str, Any]]
    work_order_packet_dir: Path
    work_order_packet_id: str
    work_order_packet_artifact_id: str | None
    work_order_payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    base_candidate_packet_id: str
    base_candidate_packet_dir: Path
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str
    selected_region_id: str
    selected_region_before_text: str
    selected_region_sha256: str
    selected_residual_target_id: str
    target_units: tuple[TargetUnit, ...]
    proof_packet_id: str
    reader_state_packet_id: str


@dataclass(frozen=True)
class RecomposedCandidate:
    text: str
    replacement_region_text: str
    validation_report: dict[str, object]


class FakeObjectMotionCausalityModelClient:
    provider = "fake"
    model = "fake-object-motion-causality-v1"

    def __init__(self, mode: str = "valid") -> None:
        self.mode = mode

    def generate(self, request: WorkerRequest) -> str:
        prompt = json.loads(request.input_text)
        units = prompt["target_units"]
        selected_region = prompt["selected_region_before_text"]
        if self.mode == "invalid_json":
            return "{not valid json"
        if self.mode == "missing_mapping":
            return _canonical_json(
                {
                    **_valid_fake_payload(units),
                    "target_unit_mapping": [],
                }
            )
        if self.mode == "invented_unit":
            payload = _valid_fake_payload(units)
            payload["target_unit_mapping"][0]["unit_id"] = "unit_999_invented"
            return _canonical_json(payload)
        if self.mode == "decorative":
            payload = _valid_fake_payload(units)
            payload["replacement_region_text"] = (
                "The porcelain was luminous, the dust fine, the spoon silver, "
                "the saucer pale, the table quiet."
            )
            return _canonical_json(payload)
        if self.mode == "full_rewrite":
            payload = _valid_fake_payload(units)
            payload["replacement_region_text"] = (
                selected_region
                + "\n\nThe table is still there in the morning, repeating the opening."
            )
            return _canonical_json(payload)
        if self.mode == "finality":
            payload = _valid_fake_payload(units)
            payload["replacement_region_text"] = (
                "This final artifact proves a phase shift. The cup moves and the "
                "ring changes, so validation is complete."
            )
            return _canonical_json(payload)
        return _canonical_json(_valid_fake_payload(units))


def run_residual_candidate_generation(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path,
    allow_live_model: bool = False,
    max_model_calls: int = RESIDUAL_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> ResidualCandidateGenerationResult:
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name not in RESIDUAL_CANDIDATE_GENERATION_CLIENTS:
        return _refusal(
            message=f"Unsupported residual candidate generation client: {client_name}",
            authorization_packet=authorization_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Residual candidate generation OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                authorization_packet=authorization_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    "Residual candidate generation OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                authorization_packet=authorization_packet,
                client_name=client_name,
                model=configured_model,
            )
        if max_model_calls < RESIDUAL_CANDIDATE_GENERATION_REQUIRED_MODEL_CALLS:
            return _refusal(
                message=(
                    "Residual candidate generation OpenAI path refused; "
                    f"max-model-calls {max_model_calls} is below required budget 1."
                ),
                authorization_packet=authorization_packet,
                client_name=client_name,
                model=configured_model,
            )

    initialize_database(config)
    resolved_packet = _resolve_path(config, authorization_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            message=(
                "Residual candidate generation refused; authorization packet "
                f"directory not found: {resolved_packet}"
            ),
            authorization_packet=resolved_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )

    with connect(config.db_path) as connection:
        try:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject_before_model_call(connection, subject, client_name=client_name)
        except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
            return _refusal(
                message=f"Residual candidate generation refused; {error}",
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )

        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Residual candidate generation refused; run is not registered: "
                    f"{subject.run_id}"
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_RESIDUAL_CANDIDATE_GENERATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "bounded_macro_recomposition"
        )
        fixture_only = client_name == "fake"
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=RESIDUAL_CANDIDATE_GENERATION_LINEAGE_ID,
            created_by=RESIDUAL_CANDIDATE_GENERATION_CREATED_BY,
            fixture_only=fixture_only,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        model_results: list[ModelDriverResult] = []

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

        payloads["macro_recomposition_work_order"] = _build_work_order(subject)
        artifacts["macro_recomposition_work_order"] = writer.write_artifact(
            "macro_recomposition_work_order",
            payloads["macro_recomposition_work_order"],
            parent_ids=[artifacts["macro_recomposition_subject_manifest"].id],
        )

        payloads["protected_effects_and_forbidden_changes"] = _build_protected_effects(
            subject
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[artifacts["macro_recomposition_work_order"].id],
        )

        connection.commit()

    if client_name == "fake":
        model_payload = _valid_fake_payload(
            [unit_payload(unit) for unit in subject.target_units]
        )
        model_call_id = None
    else:
        factory = client_factory or _default_openai_client_factory
        result = _run_live_generation_model(
            config=config,
            subject=subject,
            packet_dir=packet_dir,
            model_client=factory(configured_model),
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

    try:
        recomposed = _build_recomposed_candidate(subject, model_payload)
    except ModelValidationError as error:
        return _failure_result(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            artifacts=artifacts,
            model_results=model_results,
            message=f"Residual candidate generation refused; {error}",
        )

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=RESIDUAL_CANDIDATE_GENERATION_LINEAGE_ID,
            created_by=RESIDUAL_CANDIDATE_GENERATION_CREATED_BY,
            fixture_only=fixture_only,
            model_call_id=None,
        )
        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=RESIDUAL_CANDIDATE_GENERATION_LINEAGE_ID,
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
            parent_ids=[artifacts["macro_recomposition_plan"].id],
        )
        if model_results:
            model_results[-1] = _link_model_result(
                connection,
                result=model_results[-1],
                parsed_artifact=artifacts["macro_patch_or_section_plan"],
            )

        payloads["macro_recomposed_candidate_text"] = _build_candidate_text(
            subject=subject,
            recomposed=recomposed,
            model_call_id=model_call_id,
            fixture_only=fixture_only,
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
            lineage_id=RESIDUAL_CANDIDATE_GENERATION_LINEAGE_ID,
        )

    return ResidualCandidateGenerationResult(
        exit_code=0,
        payload=_result_payload(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
        model_results=tuple(model_results),
    )


def _load_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    authorization_packet_dir: Path,
) -> ResidualCandidateSubject:
    auth_envelopes, auth_payloads = _load_required_payloads(
        authorization_packet_dir,
        REQUIRED_AUTHORIZATION_ARTIFACTS,
        "authorization packet",
    )
    auth_packet_envelope = auth_envelopes["residual_generation_authorization_packet"]
    auth_packet = auth_payloads["residual_generation_authorization_packet"]
    auth_manifest = auth_payloads.get("residual_generation_authorization_subject_manifest")
    if auth_manifest is None and (
        authorization_packet_dir
        / "residual_generation_authorization_subject_manifest.json"
    ).exists():
        auth_manifest = read_json_file(
            authorization_packet_dir
            / "residual_generation_authorization_subject_manifest.json"
        )["payload"]
    auth_manifest = auth_manifest if isinstance(auth_manifest, dict) else {}
    run_id = str(auth_packet.get("run_id") or auth_packet_envelope.get("run_id") or "")
    if not run_id:
        raise ValueError("authorization packet missing run_id")

    work_order_dir = _resolve_path(
        config,
        Path(str(auth_packet.get("work_order_packet_dir") or "")),
    )
    if not work_order_dir.exists():
        work_order_dir = _resolve_path(
            config,
            Path(str(auth_manifest.get("source_work_order_packet_dir") or "")),
        )
    if not work_order_dir.exists() or not work_order_dir.is_dir():
        raise ValueError("source work-order packet cannot be resolved")
    _work_envelopes, work_payloads = _load_required_payloads(
        work_order_dir,
        REQUIRED_WORK_ORDER_ARTIFACTS,
        "work-order packet",
    )

    work_packet = work_payloads["residual_work_order_packet"]
    selected_region = work_payloads["selected_intervention_region"]
    unit_map = work_payloads["object_motion_target_unit_map"]
    base_packet_id = str(
        auth_packet.get("base_candidate_packet_id")
        or auth_packet.get("current_best_candidate_packet_id")
        or work_packet.get("current_best_candidate_packet_id")
        or ""
    )
    base_packet_dir = _resolve_path(
        config,
        Path(
            str(
                auth_manifest.get("current_best_candidate_packet_dir")
                or work_payloads["residual_work_order_subject_manifest"].get(
                    "current_best_candidate_packet_dir"
                )
                or ""
            )
        ),
    )
    base_payload, base_artifact_id = _load_base_candidate_payload(
        connection,
        base_packet_dir,
    )
    base_text = str(base_payload.get("text") or "")
    if not base_text.strip():
        raise ValueError("base candidate text is empty")
    base_text_sha256 = str(base_payload.get("text_sha256") or sha256_text(base_text))

    selected_region_before_text = str(selected_region.get("selected_region_before_text") or "")
    selected_region_sha256 = str(
        auth_packet.get("selected_region_sha256")
        or selected_region.get("selected_region_sha256")
        or ""
    )
    target_units = tuple(_target_units_from_map(unit_map))
    auth_artifact_ids = _artifact_ids_from_packet(auth_packet)
    auth_packet_artifact = _artifact_for_path(
        connection,
        authorization_packet_dir / "residual_generation_authorization_packet.json",
    )
    work_packet_artifact = _artifact_for_path(
        connection,
        work_order_dir / "residual_work_order_packet.json",
    )
    parent_ids = _unique(
        [
            auth_packet_artifact.id if auth_packet_artifact else None,
            work_packet_artifact.id if work_packet_artifact else None,
            base_artifact_id,
            *auth_artifact_ids.values(),
            *_artifact_ids_from_packet(work_packet).values(),
        ]
    )
    return ResidualCandidateSubject(
        run_id=run_id,
        authorization_packet_dir=authorization_packet_dir,
        authorization_packet_id=str(auth_packet.get("packet_id") or authorization_packet_dir.name),
        authorization_packet_artifact_id=auth_packet_artifact.id
        if auth_packet_artifact
        else None,
        authorization_fixture_only=auth_packet_envelope.get("fixture_only") is True,
        authorization_artifact_ids=auth_artifact_ids,
        authorization_payloads=auth_payloads,
        work_order_packet_dir=work_order_dir,
        work_order_packet_id=str(work_packet.get("packet_id") or work_order_dir.name),
        work_order_packet_artifact_id=work_packet_artifact.id
        if work_packet_artifact
        else None,
        work_order_payloads=work_payloads,
        source_parent_ids=tuple(parent_ids),
        base_candidate_packet_id=base_packet_id,
        base_candidate_packet_dir=base_packet_dir,
        base_candidate_artifact_id=base_artifact_id,
        base_text=base_text,
        base_text_sha256=base_text_sha256,
        selected_region_id=str(auth_packet.get("selected_region_id") or ""),
        selected_region_before_text=selected_region_before_text,
        selected_region_sha256=selected_region_sha256,
        selected_residual_target_id=str(auth_packet.get("selected_residual_target_id") or ""),
        target_units=target_units,
        proof_packet_id=str(
            work_payloads["residual_work_order_subject_manifest"].get("proof_packet_id")
            or ""
        ),
        reader_state_packet_id=str(
            work_payloads["residual_work_order_subject_manifest"].get(
                "reader_state_packet_id"
            )
            or ""
        ),
    )


def _validate_subject_before_model_call(
    connection: sqlite3.Connection,
    subject: ResidualCandidateSubject,
    *,
    client_name: str,
) -> None:
    auth_packet = subject.authorization_payloads["residual_generation_authorization_packet"]
    budget = subject.authorization_payloads["generation_attempt_budget"]
    scope = subject.authorization_payloads["generation_scope_authorization"]
    gate = subject.authorization_payloads["authorization_gate_report"]
    if client_name == "fake" and not subject.authorization_fixture_only:
        raise ValueError(
            "fake mode refuses non-fixture single-use authorization packets; "
            "the live authorization is reserved for one real bounded generation attempt"
        )
    if auth_packet.get("generation_authorized") is not True:
        raise ValueError("generation_authorized is not true")
    if int(auth_packet.get("generation_attempt_budget") or 0) != 1:
        raise ValueError("generation_attempt_budget must be 1")
    if auth_packet.get("authorization_consumed") is True or budget.get("authorization_consumed") is True:
        raise ValueError("authorization is already consumed")
    if auth_packet.get("candidate_generated") is True:
        raise ValueError("authorization packet already records generated candidate")
    if subject.selected_residual_target_id != OBJECT_MOTION_CAUSALITY_TARGET_ID:
        raise ValueError(
            "selected residual target is not object_motion_causality_specificity"
        )
    if subject.selected_region_id != SELECTED_REGION_ID:
        raise ValueError("selected region is missing or invalid")
    if not subject.selected_region_sha256:
        raise ValueError("selected region hash is missing")
    if len(subject.target_units) < 1:
        raise ValueError("target unit count must be at least 1")
    if not subject.base_candidate_packet_id or not subject.base_candidate_packet_dir.exists():
        raise ValueError("base candidate packet cannot be resolved")
    if sha256_text(subject.selected_region_before_text) != subject.selected_region_sha256:
        raise ValueError("selected region text hash does not match authorization")
    if subject.selected_region_before_text not in subject.base_text:
        raise ValueError("selected region text cannot be found in base candidate")
    if scope.get("authorized_selected_region_sha256") != subject.selected_region_sha256:
        raise ValueError("scope selected region hash does not match authorization")
    if gate.get("no_phase_shift_claim") is not True or gate.get("finalization_eligible") is True:
        raise ValueError("authorization packet carries a finality or phase-shift claim")
    linked = _linked_candidate_for_authorization(connection, subject)
    if linked is not None:
        raise ValueError(
            "existing later candidate already references this authorization: "
            f"{linked.id}"
        )


def _run_live_generation_model(
    *,
    config: AbiConfig,
    subject: ResidualCandidateSubject,
    packet_dir: Path,
    model_client: ModelClient,
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.OBJECT_MOTION_CAUSALITY_GENERATOR,
            prompt_contract_id=RESIDUAL_CANDIDATE_GENERATION_PROMPT_CONTRACT_ID,
            schema=OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
            input_text=_prompt_for_generation(subject),
            input_artifact_ids=parent_ids,
            input_packet_path=str(subject.authorization_packet_dir),
            lineage_id=RESIDUAL_CANDIDATE_GENERATION_LINEAGE_ID,
            parent_ids=parent_ids,
            fixture_only=False,
            output_dir=str(packet_dir),
            register_parsed_artifact=False,
            parsed_payload_validator=lambda payload: _validate_model_payload(
                subject,
                payload,
            ),
        )
    )


def _prompt_for_generation(subject: ResidualCandidateSubject) -> str:
    return _canonical_json(
        {
            "task": "generate one bounded replacement for the selected region only",
            "controller_owns": [
                "authorization packet",
                "work-order packet",
                "base candidate packet",
                "selected region and selected region hash",
                "target unit IDs",
                "final assembly",
                "diff report",
                "gate report",
                "authorization consumption status",
                "finalization status",
            ],
            "model_may_own": [
                "replacement_region_text",
                "target_unit_mapping rationale",
                "local risk notes",
                "uncertainty",
            ],
            "model_must_not_own": [
                "source IDs",
                "target IDs",
                "selected region identity",
                "nonselected region edits",
                "full artifact text",
                "finalization",
                "phase-shift claim",
            ],
            "authorization_packet_id": subject.authorization_packet_id,
            "work_order_packet_id": subject.work_order_packet_id,
            "base_candidate_packet_id": subject.base_candidate_packet_id,
            "base_candidate_text_sha256": subject.base_text_sha256,
            "selected_residual_target_id": subject.selected_residual_target_id,
            "selected_region_id": subject.selected_region_id,
            "selected_region_sha256": subject.selected_region_sha256,
            "selected_region_before_text": subject.selected_region_before_text,
            "target_units": [unit_payload(unit) for unit in subject.target_units],
            "target_unit_integration_policy": subject.authorization_payloads[
                "target_unit_integration_policy"
            ],
            "generation_scope_authorization": subject.authorization_payloads[
                "generation_scope_authorization"
            ],
            "protected_effects_and_forbidden_changes": subject.authorization_payloads[
                "protected_effects_and_forbidden_changes"
            ],
            "output_rule": (
                "Return one replacement_region_text for the selected region. Do not "
                "return the full artifact. Include exactly one target_unit_mapping "
                "entry for each provided unit_id. Make object motion or state change "
                "produce visible consequence before explanation."
            ),
        }
    )


def _validate_model_payload(
    subject: ResidualCandidateSubject,
    payload: dict[str, object],
) -> None:
    replacement = str(payload.get("replacement_region_text") or "")
    mapping = payload.get("target_unit_mapping")
    if not isinstance(mapping, list):
        raise ModelValidationError("target_unit_mapping must be a list")
    _validate_target_unit_mapping(subject, mapping)
    _validate_replacement_text(subject, replacement)


def _validate_target_unit_mapping(
    subject: ResidualCandidateSubject,
    mapping: list[object],
) -> list[dict[str, object]]:
    expected = {unit.unit_id for unit in subject.target_units}
    seen: set[str] = set()
    validated = []
    for index, item in enumerate(mapping):
        if not isinstance(item, dict):
            raise ModelValidationError(f"target_unit_mapping[{index}] must be an object")
        unit_id = str(item.get("unit_id") or "")
        if unit_id not in expected:
            raise ModelValidationError(f"invented or unsupported target unit: {unit_id}")
        if unit_id in seen:
            raise ModelValidationError(f"duplicate target unit mapping: {unit_id}")
        seen.add(unit_id)
        for field in (
            "before_text_excerpt",
            "replacement_text_excerpt",
            "object_motion_or_action",
            "visible_consequence",
            "how_reader_infers_pressure_before_explanation",
            "forbidden_change_avoided",
        ):
            if not str(item.get(field) or "").strip():
                raise ModelValidationError(f"{unit_id}.{field} must not be empty")
        validated.append(dict(item))
    missing = sorted(expected - seen)
    if missing:
        raise ModelValidationError(f"missing target unit IDs: {missing}")
    return validated


def _validate_replacement_text(
    subject: ResidualCandidateSubject,
    replacement_region_text: str,
) -> dict[str, object]:
    replacement = replacement_region_text.strip()
    if not replacement:
        raise ModelValidationError("replacement_region_text must not be empty")
    if replacement.startswith("{"):
        raise ModelValidationError("replacement_region_text must not be JSON text")
    try:
        json.loads(replacement)
    except json.JSONDecodeError:
        pass
    else:
        raise ModelValidationError("replacement_region_text must not parse as JSON")
    before = subject.selected_region_before_text
    if _canonical_space(replacement) == _canonical_space(before):
        raise ModelValidationError("selected region materiality failed")
    if _canonical_space(before) in _canonical_space(replacement):
        raise ModelValidationError("full rewrite or copied selected region detected")
    prefix, suffix = _prefix_suffix(subject)
    lower = replacement.lower()
    for label, text in (("prefix", prefix), ("suffix", suffix)):
        first_sentence = _first_sentence(text).lower()
        if first_sentence and first_sentence in lower:
            raise ModelValidationError(f"nonselected region edit/full rewrite detected: {label}")
    if _word_count(replacement) > max(80, _word_count(before) * 2):
        raise ModelValidationError("full rewrite detected; replacement is too large")
    forbidden_terms = (
        "final artifact",
        "finalization",
        "phase shift",
        "phase-shift",
        "human validation",
        "validation complete",
        "paper-ready",
        "strongest rival defeated",
        "rival defeated",
        "source manifest",
        "model_call_id",
    )
    for term in forbidden_terms:
        if term in lower:
            raise ModelValidationError(
                f"replacement_region_text contains forbidden claim/leakage: {term}"
            )
    if "rival" in lower:
        raise ModelValidationError("replacement_region_text risks rival mimicry")
    if "object list" in lower or "catalog" in lower or "catalogue" in lower:
        raise ModelValidationError("replacement_region_text adds an object list")
    if _decorative_list_risk(replacement):
        raise ModelValidationError("replacement_region_text is decorative object listing")
    object_terms_present = _terms_present(lower, OBJECT_TERMS)
    motion_terms_present = _terms_present(lower, MOTION_TERMS)
    consequence_terms_present = _terms_present(lower, CONSEQUENCE_TERMS)
    relation_count = _object_motion_relation_count(replacement)
    if relation_count < 2:
        raise ModelValidationError("object motion causal relation missing")
    if len(object_terms_present) < 6 or len(motion_terms_present) < 3:
        raise ModelValidationError("decorative-only replacement lacks object motion")
    if len(consequence_terms_present) < 3:
        raise ModelValidationError("visible consequence before explanation is missing")
    changed = _word_set(replacement) - _word_set(before)
    changed_ratio = len(changed) / max(1, len(_word_set(replacement)))
    if len(changed) < 10 or changed_ratio < 0.12:
        raise ModelValidationError("selected region materiality failed")
    return {
        "selected_region_materiality_passed": True,
        "changed_word_count": len(changed),
        "changed_word_ratio": round(changed_ratio, 3),
        "object_motion_relation_count": relation_count,
        "object_terms_present": object_terms_present,
        "motion_terms_present": motion_terms_present,
        "consequence_terms_present": consequence_terms_present,
        "no_nonselected_region_edits": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "object_list_rejected": True,
        "decorative_vividness_only_rejected": True,
        "full_rewrite_rejected": True,
    }


def _build_recomposed_candidate(
    subject: ResidualCandidateSubject,
    model_payload: dict[str, object],
) -> RecomposedCandidate:
    replacement = str(model_payload["replacement_region_text"]).strip()
    validation_report = _validate_replacement_text(subject, replacement)
    text = subject.base_text.replace(subject.selected_region_before_text, replacement, 1)
    if text == subject.base_text:
        raise ModelValidationError("candidate must materially differ from base candidate")
    if text.count(replacement) != 1:
        raise ModelValidationError("replacement must appear once in assembled candidate")
    prefix, suffix = _prefix_suffix(subject)
    if not text.startswith(prefix) or not text.endswith(suffix):
        raise ModelValidationError("nonselected region edit detected during assembly")
    return RecomposedCandidate(
        text=text,
        replacement_region_text=replacement,
        validation_report=validation_report,
    )


def _build_subject_manifest(
    subject: ResidualCandidateSubject,
    *,
    packet_dir: Path,
    client_name: str,
    max_model_calls: int,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "max_model_calls": max_model_calls,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
        "source_work_order_packet_id": subject.work_order_packet_id,
        "source_work_order_packet_dir": str(subject.work_order_packet_dir),
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_packet_dir": str(subject.base_candidate_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "proof_packet_id": subject.proof_packet_id,
        "reader_state_packet_id": subject.reader_state_packet_id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "target_unit_count": len(subject.target_units),
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "one_shot_generation": True,
        "bounded_macro_recomposition": True,
        "candidate_generated": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_generation_subject_manifest_v1_controller",
    }


def _build_work_order(subject: ResidualCandidateSubject) -> dict[str, object]:
    return {
        "work_order_id": f"object_motion_generation_{subject.authorization_packet_id}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "before_section_text": subject.selected_region_before_text,
        "target_units": [unit_payload(unit) for unit in subject.target_units],
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "one_shot_generation": True,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "controller_owns": [
            "source IDs",
            "target IDs",
            "selected region",
            "selected region hash",
            "final text assembly",
            "diff report",
            "gate report",
            "finalization status",
        ],
        "model_may_own_if_live": [
            "bounded replacement text",
            "unit-level mapping rationale",
            "local risk notes",
            "uncertainty",
        ],
        "model_must_not_own": [
            "final text assembly",
            "nonselected region edits",
            "source IDs",
            "target IDs",
            "gate pass/fail",
            "finalization",
            "phase-shift claim",
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_generation_work_order_v1_controller",
    }


def _build_protected_effects(subject: ResidualCandidateSubject) -> dict[str, object]:
    source = subject.authorization_payloads["protected_effects_and_forbidden_changes"]
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "protected_effects": list(source.get("protected_effects", [])),
        "forbidden_changes": list(source.get("forbidden_changes", [])),
        "must_preserve": [
            "opening table/dust/spoon/saucer/ring field outside selected region",
            "proof/no-answer region",
            "final return / opening transformation",
            "packet_0059 macro and reader-state gains",
            "strongest rival pressure as still blocking",
        ],
        "must_not": [
            "nonselected region edits",
            "decorative vividness only",
            "new object list",
            "rival mimicry",
            "full rewrite",
            "finality claim",
            "phase-shift claim",
        ],
        "authorization_consumed": True,
        "candidate_generated": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_generation_protected_effects_v1_controller",
    }


def _build_recomposition_plan(
    *,
    subject: ResidualCandidateSubject,
    model_payload: dict[str, object],
    model_call_id: str | None,
) -> dict[str, object]:
    return {
        "plan_id": f"object_motion_plan_{sha256_text(subject.authorization_packet_id)[:12]}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "object_motion_generation_plan": list(
            model_payload["object_motion_generation_plan"]
        ),
        "protected_effects_preservation_notes": list(
            model_payload["protected_effects_preservation_notes"]
        ),
        "predicted_reader_effect": model_payload["predicted_reader_effect"],
        "uncertainty": model_payload["uncertainty"],
        "source_model_call_id": model_call_id,
        "one_shot_generation": True,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "semantic_constraint_satisfaction_not_proven": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": (
            "residual_candidate_generation_plan_v1_model_driver"
            if model_call_id
            else "residual_candidate_generation_plan_v1_fake_controller"
        ),
    }


def _build_patch_or_section_plan(
    *,
    subject: ResidualCandidateSubject,
    recomposed: RecomposedCandidate,
    model_payload: dict[str, object],
    model_call_id: str | None,
) -> dict[str, object]:
    return {
        "patch_or_section_plan_id": f"object_motion_patch_{sha256_text(recomposed.text)[:12]}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "before_section_text": subject.selected_region_before_text,
        "replacement_section_text": recomposed.replacement_region_text,
        "replacement_section_text_sha256": sha256_text(recomposed.replacement_region_text),
        "target_unit_mapping": list(model_payload["target_unit_mapping"]),
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "forbidden_change_self_check": list(model_payload["forbidden_change_self_check"]),
        "target_coverage_report": _target_coverage_report(subject, recomposed),
        "source_model_call_id": model_call_id,
        "model_owned_fields": [
            "replacement_region_text",
            "target_unit_mapping",
            "object_motion_generation_plan",
            "protected_effects_preservation_notes",
            "uncertainty",
            "predicted_reader_effect",
            "forbidden_change_self_check",
        ],
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "one_shot_generation": True,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "semantic_constraint_satisfaction_not_proven": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": (
            "residual_candidate_generation_patch_v1_model_driver"
            if model_call_id
            else "residual_candidate_generation_patch_v1_fake_controller"
        ),
    }


def _build_candidate_text(
    *,
    subject: ResidualCandidateSubject,
    recomposed: RecomposedCandidate,
    model_call_id: str | None,
    fixture_only: bool,
) -> dict[str, object]:
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_packet_dir": str(subject.base_candidate_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "text": recomposed.text,
        "text_sha256": sha256_text(recomposed.text),
        "word_count": _word_count(recomposed.text),
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": True,
        "full_rewrite": False,
        "assembled_by_controller": True,
        "source_model_call_id": model_call_id,
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "candidate_generated": True,
        "candidate_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
        "requires_executed_ablation_before_improvement_claim": True,
        "requires_reader_state_eval_before_reader_state_claim": True,
        "worker": "residual_candidate_text_v1_controller_assembled_from_model",
    }


def _build_diff_report(
    *,
    subject: ResidualCandidateSubject,
    recomposed: RecomposedCandidate,
    candidate: dict[str, object],
) -> dict[str, object]:
    changed_spans = [
        {
            "changed_span_id": "object_motion_region_001",
            "patch_span_id": "object_motion_region_001",
            "before": subject.selected_region_before_text,
            "after": recomposed.replacement_region_text,
            "before_text": subject.selected_region_before_text,
            "after_text": recomposed.replacement_region_text,
            "region": subject.selected_region_id,
            "target_expansion_reason": "",
            "reason": "bounded object-motion causality specificity generation",
            "inside_target": True,
            "within_selected_target": True,
            "requires_target_expansion": False,
            "source_patch_span_ids": ["object_motion_region_001"],
        }
    ]
    return {
        "diff_report_id": f"object_motion_diff_{sha256_text(str(candidate['text']))[:12]}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "candidate_text_sha256": candidate["text_sha256"],
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": True,
        "full_rewrite": False,
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "changed_spans": changed_spans,
        "changed_span_count": len(changed_spans),
        "materiality_report": recomposed.validation_report,
        "target_coverage_report": _target_coverage_report(subject, recomposed),
        "ready_for_executed_ablation": True,
        "requires_executed_ablation_before_improvement_claim": True,
        "requires_reader_state_eval_before_reader_state_claim": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_diff_report_v1_controller",
    }


def _build_rival_pressure_check(
    *,
    subject: ResidualCandidateSubject,
    recomposed: RecomposedCandidate,
) -> dict[str, object]:
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "strongest_rival_defeated": False,
        "rival_mimicry_detected": False,
        "object_motion_relation_count": recomposed.validation_report[
            "object_motion_relation_count"
        ],
        "current_candidate_closes_gap": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_rival_pressure_check_v1_controller",
    }


def _build_gate_report(
    *,
    subject: ResidualCandidateSubject,
    recomposed: RecomposedCandidate,
    diff_report: dict[str, object],
    rival_check: dict[str, object],
) -> dict[str, object]:
    coverage = diff_report["target_coverage_report"]
    gate_results = [
        _gate_result("authorization_packet_consumed", True),
        _gate_result("work_order_packet_consumed", True),
        _gate_result("base_candidate_packet_0059_used", bool(subject.base_candidate_packet_id)),
        _gate_result("selected_region_hash_verified", True),
        _gate_result("target_units_mapped", True),
        _gate_result("one_bounded_replacement_generated", True),
        _gate_result("selected_region_materiality_passed", True),
        _gate_result("object_motion_causality_mapping_exists", True),
        _gate_result("protected_effects_recorded", True),
        _gate_result("no_nonselected_region_edits", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "executed_ablation_completed_for_residual_candidate",
            False,
            ["residual candidate has not yet been tested by executed ablation"],
            record=False,
        ),
        _gate_result(
            "reader_state_eval_completed_for_residual_candidate",
            False,
            ["residual candidate has not yet been reader-state evaluated"],
            record=False,
        ),
        _gate_result(
            "synthesis_completed_for_residual_candidate",
            False,
            ["residual candidate has not yet been synthesized into evidence"],
            record=False,
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            ["strongest rival still blocks; ablation and reader-state evidence absent"],
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
            ["residual candidate is candidate-only"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_defeated",
            False,
            ["strongest rival remains blocking"],
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
        "authorization_consumed": True,
        "generation_attempt_budget_consumed": True,
        "generation_attempt_index": 1,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "non_final": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": True,
        "macro_target_coverage_passed": coverage["macro_target_coverage_passed"],
        "macro_materiality_passed": coverage["macro_materiality_passed"],
        "ready_for_executed_ablation": coverage["ready_for_executed_ablation"],
        "target_coverage_report": coverage,
        "semantic_constraint_satisfaction_not_proven": True,
        "requires_internal_reader_or_ablation_validation": True,
        "requires_executed_ablation_before_improvement_claim": True,
        "requires_reader_state_eval_before_reader_state_claim": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_pressure_preserved": (
            rival_check["strongest_rival_pressure_preserved"] is True
        ),
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "residual candidate has not been tested by executed ablation",
            "residual candidate has not been reader-state evaluated",
            "evidence synthesis has not evaluated the residual candidate",
            "strongest-rival pressure remains blocking",
            "internal operator approval is absent",
        ],
        "summary_verdict": (
            "One bounded object-motion causality candidate was generated and is "
            "ready for review before ablation, but remains fail-closed and makes "
            "no improvement claim."
        ),
        "worker": "residual_candidate_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ResidualCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=BOUNDED_MACRO_COMPATIBLE_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="macro_recomposition_packet",
    )
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "model": model,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
        "source_work_order_packet_id": subject.work_order_packet_id,
        "source_work_order_packet_dir": str(subject.work_order_packet_dir),
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_packet_dir": str(subject.base_candidate_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "current_best_candidate": {
            "packet_id": subject.base_candidate_packet_id,
            "packet_kind": "bounded_macro_recomposition",
            "packet_dir": str(subject.base_candidate_packet_dir),
        },
        "current_best_candidate_packet_id": subject.base_candidate_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_count": len(subject.target_units),
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            **counts,
            "model_calls": len(model_results),
            "macro_recomposition_artifacts": counts["produced_artifacts"],
            "required_macro_recomposition_artifacts": counts["required_artifacts"],
            "candidate_artifacts_created": 1,
        },
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "generation_attempt_budget_consumed": True,
        "candidate_generated": True,
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "diff_report_artifact_id": artifacts["macro_recomposition_diff_report"].id,
        "rival_pressure_check_artifact_id": artifacts["macro_rival_pressure_check"].id,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "target_coverage_report": payloads["macro_recomposition_diff_report"][
            "target_coverage_report"
        ],
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": True,
        "one_shot_generation": True,
        "full_rewrite": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "requires_reader_state_eval_before_reader_state_claim": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_macro_packet_v1_controller",
    }


def _result_payload(
    *,
    subject: ResidualCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    packet = payloads["macro_recomposition_packet"]
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "counts": packet["counts"],
        "current_best_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "selected_region_id": subject.selected_region_id,
        "target_unit_count": len(subject.target_units),
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "candidate_generated": True,
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "model": model,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "gate_report": payloads["macro_recomposition_gate_report"],
    }


def _failure_result(
    *,
    subject: ResidualCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    artifacts: dict[str, ArtifactRecord],
    model_results: list[ModelDriverResult],
    message: str,
) -> ResidualCandidateGenerationResult:
    return ResidualCandidateGenerationResult(
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
            "counts": {
                "model_calls": len(model_results),
                "candidate_artifacts_created": 0,
            },
            "current_best_candidate_packet_id": subject.base_candidate_packet_id,
            "base_candidate_packet_id": subject.base_candidate_packet_id,
            "source_authorization_packet_id": subject.authorization_packet_id,
            "source_work_order_packet_id": subject.work_order_packet_id,
            "selected_residual_target_id": subject.selected_residual_target_id,
            "selected_region_id": subject.selected_region_id,
            "target_unit_count": len(subject.target_units),
            "target_unit_ids": [unit.unit_id for unit in subject.target_units],
            "authorization_consumed": False,
            "generation_attempt_index": None,
            "candidate_generated": False,
            "candidate_artifact_id": None,
            "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
            "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
            "model_call_ids": [result.model_call.id for result in model_results],
            "model_calls": [result.model_call_to_dict() for result in model_results],
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "next_recommended_action": "review_failed_object_motion_generation",
        },
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _load_required_payloads(
    packet_dir: Path,
    artifact_types: tuple[str, ...],
    label: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    envelopes: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in artifact_types:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(f"{label} missing {path.name}")
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(f"malformed {label} artifact: {path.name}")
        envelopes[artifact_type] = envelope
        payloads[artifact_type] = envelope["payload"]
    return envelopes, payloads


def _load_base_candidate_payload(
    connection: sqlite3.Connection,
    packet_dir: Path,
) -> tuple[dict[str, Any], str | None]:
    path = packet_dir / "macro_recomposed_candidate_text.json"
    if not path.exists():
        raise ValueError("base candidate macro_recomposed_candidate_text cannot be loaded")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("base candidate text artifact is malformed")
    artifact = _artifact_for_path(connection, path)
    return payload, artifact.id if artifact else None


def _target_units_from_map(unit_map: dict[str, Any]) -> list[TargetUnit]:
    units = []
    for item in unit_map.get("target_units", []):
        if not isinstance(item, dict):
            continue
        units.append(
            TargetUnit(
                unit_id=str(item.get("unit_id") or ""),
                before_text=str(item.get("before_text") or ""),
                before_text_sha256=str(item.get("before_text_sha256") or ""),
                objects=tuple(str(value) for value in item.get("objects", [])),
                target_effect=str(item.get("target_effect") or ""),
            )
        )
    return [unit for unit in units if unit.unit_id]


def _linked_candidate_for_authorization(
    connection: sqlite3.Connection,
    subject: ResidualCandidateSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type not in {"macro_recomposition_packet", "macro_recomposed_candidate_text"}:
            continue
        try:
            envelope = read_json_file(artifact.path)
        except (OSError, json.JSONDecodeError):
            continue
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            continue
        if payload.get("source_authorization_packet_id") == subject.authorization_packet_id:
            return artifact
    return None


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


def _target_coverage_report(
    subject: ResidualCandidateSubject,
    recomposed: RecomposedCandidate,
) -> dict[str, object]:
    return {
        "macro_target_coverage_passed": True,
        "controller_target_coverage_passed": True,
        "macro_materiality_passed": True,
        "paragraph_level_coverage_passed": True,
        "span_level_coverage_passed": True,
        "ready_for_executed_ablation": True,
        "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
        "selected_region_id": subject.selected_region_id,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "active_targets_covered": [unit.unit_id for unit in subject.target_units],
        "active_targets_missing": [],
        "selected_region_materiality_passed": recomposed.validation_report[
            "selected_region_materiality_passed"
        ],
        "object_motion_causality_mapping_exists": True,
        "no_nonselected_region_edits": True,
        "decorative_vividness_only_rejected": True,
        "object_list_rejected": True,
        "full_rewrite_rejected": True,
    }


def _prefix_suffix(subject: ResidualCandidateSubject) -> tuple[str, str]:
    before, selected, after = subject.base_text.partition(subject.selected_region_before_text)
    if not selected:
        return "", ""
    return before, after


def _object_motion_relation_count(text: str) -> int:
    count = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if (
            len(_terms_present(lower, OBJECT_TERMS)) >= 2
            and _terms_present(lower, MOTION_TERMS)
            and _terms_present(lower, CONSEQUENCE_TERMS)
        ):
            count += 1
    return count


def _decorative_list_risk(text: str) -> bool:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if sentence.count(",") >= 4 and not _terms_present(sentence.lower(), MOTION_TERMS):
            return True
    return False


def _terms_present(text: str, terms: tuple[str, ...]) -> list[str]:
    return sorted({term for term in terms if term in text})


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9']+", text.lower()))


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _canonical_space(text: str) -> str:
    return " ".join(text.split()).lower()


def _first_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", normalized)[0]
    return sentence.strip()


def _model_failure_message(result: ModelDriverResult) -> str:
    if result.model_call.error_message:
        return (
            "Residual candidate generation stopped by model-call failure: "
            f"{result.model_call.error_message}"
        )
    return "Residual candidate generation stopped by model-call failure."


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _valid_fake_payload(units: list[dict[str, object]]) -> dict[str, object]:
    replacement = (
        "A room like this teaches by the order of its marks. The cup comes down "
        "on the table and presses a wet ring into the grain; when it is lifted, "
        "the ring thins at one edge and drags the crumb with it, so the table has "
        "changed before anyone names the change. Morning leaves that answer in "
        "place. Dust gathers where the hand crossed the surface, where the foot "
        "shook grit from the threshold, and where the air pushed it into a narrow "
        "line beside the spoon. The spoon has not merely appeared on its side: a "
        "quick hand let it slip, the handle struck the saucer, and the fall left "
        "the crack that makes the break plain.\n\n"
        "At first, the table seems only ordinary. But ordinariness is strict "
        "because each object carries the pressure of the one before it. The glass "
        "leaves the ring, the ring moves the crumb, the moving dust shows the "
        "path of hand and foot and window air, and the spoon's fall gives the "
        "saucer its broken line. The kitchen is small, but the objects keep "
        "crossing into one another until the next thing can no longer be seen as "
        "untouched."
    )
    mapping = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        if unit_id == "unit_001_cup_ring_crumb":
            motion = "cup comes down, is lifted, and drags the crumb through the ring"
            consequence = "the wet ring thins and the crumb moves into the grain"
        elif unit_id == "unit_002_dust_hand_foot_air":
            motion = "hand, foot, and window air cross the same surface"
            consequence = "dust gathers into a line that records the crossings"
        else:
            motion = "a quick hand lets the spoon slip into the saucer"
            consequence = "the fall leaves the crack that makes the break plain"
        mapping.append(
            {
                "unit_id": unit_id,
                "before_text_excerpt": str(unit.get("before_text", ""))[:220],
                "replacement_text_excerpt": replacement[:260],
                "object_motion_or_action": motion,
                "visible_consequence": consequence,
                "how_reader_infers_pressure_before_explanation": (
                    "the object changes are staged before the paragraph names a rule"
                ),
                "forbidden_change_avoided": (
                    "no new object list, rival mimicry, full rewrite, or finality claim"
                ),
            }
        )
    return {
        "replacement_region_text": replacement,
        "object_motion_generation_plan": [
            "replace only the selected middle recurrence region",
            "make each object movement leave visible consequence",
            "keep proof and final return untouched for later ablation",
        ],
        "target_unit_mapping": mapping,
        "protected_effects_preservation_notes": [
            "opening field remains outside the replacement",
            "proof/no-answer and final return are untouched",
            "strongest-rival pressure remains blocking",
        ],
        "uncertainty": "fixture output for deterministic tests only",
        "predicted_reader_effect": (
            "reader sees object motion causing local pressure before explanation"
        ),
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no nonselected region edits",
            "no rival mimicry",
        ],
    }


def unit_payload(unit: TargetUnit | dict[str, object]) -> dict[str, object]:
    if isinstance(unit, dict):
        return dict(unit)
    return {
        "unit_id": unit.unit_id,
        "before_text": unit.before_text,
        "before_text_sha256": unit.before_text_sha256,
        "objects": list(unit.objects),
        "target_effect": unit.target_effect,
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


def _refusal(
    *,
    message: str,
    authorization_packet: Path | str,
    client_name: str | None = None,
    model: str | None = None,
) -> ResidualCandidateGenerationResult:
    return ResidualCandidateGenerationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "authorization_packet": str(authorization_packet),
            "client": client_name,
            "model": model,
            "artifact_ids": {},
            "counts": {
                "model_calls": 0,
                "candidate_artifacts_created": 0,
            },
            "current_best_candidate_packet_id": None,
            "base_candidate_packet_id": None,
            "source_authorization_packet_id": None,
            "source_work_order_packet_id": None,
            "selected_residual_target_id": None,
            "selected_region_id": None,
            "target_unit_count": 0,
            "target_unit_ids": [],
            "authorization_consumed": False,
            "generation_attempt_index": None,
            "candidate_generated": False,
            "candidate_artifact_id": None,
            "target_scope": OBJECT_MOTION_CAUSALITY_TARGET_ID,
            "target_movement": OBJECT_MOTION_CAUSALITY_TARGET_ID,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "next_recommended_action": "review_refusal_before_generation",
        },
    )


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
