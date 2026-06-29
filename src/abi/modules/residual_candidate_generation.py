"""One-shot bounded object-motion causality candidate generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import difflib
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
    RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
)
from abi.modules.residual_targets import (
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    SELECTED_REGION_ID,
    TACTILE_INEVITABILITY_TARGET_ID,
    ResidualMaterialityPolicy,
    hostile_scaffold_mapping_failures,
    materiality_policy_payload,
    payload_has_placeholder_generation_contract,
    replacement_hostile_scaffold_failures,
    replacement_tactile_failures,
    require_residual_target_adapter,
    semantic_preflight_failures_for_work_order,
    tactile_mapping_failures,
    target_generation_readiness_failures,
    target_adapter_metadata,
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
REQUIRED_CHANGED_UNIQUE_WORD_COUNT = 10
REQUIRED_CHANGED_RATIO = 0.12
HOSTILE_ORDINARY_TABLE_UNIT_ID = "ordinary_table_no_scaffold_signage"
HOSTILE_ORDINARY_TABLE_SENTENCE_POLISH_FAILURE = (
    "ordinary_table_no_scaffold_signage remained sentence-polishing / near-synonym; "
    'materially re-author the ordinary-table moment rather than swapping '
    '"seems ordinary" for "is just there"'
)

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
    "residual_generation_contract",
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

FIXTURE_BACKUP_OBJECT_TERMS = (
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

FIXTURE_BACKUP_MOTION_TERMS = (
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

FIXTURE_BACKUP_CONSEQUENCE_TERMS = (
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

TERM_STOPWORDS = {
    "and",
    "the",
    "that",
    "this",
    "with",
    "where",
    "when",
    "into",
    "from",
    "because",
    "before",
    "after",
    "again",
    "same",
    "each",
    "only",
    "must",
    "should",
    "would",
    "could",
    "have",
    "has",
    "had",
    "been",
    "being",
    "will",
    "shall",
    "not",
    "one",
    "two",
    "all",
}


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
    current_motion_action_state: str
    current_consequence: str
    current_physical_relation: str = ""
    source_unit_role: str = ""


@dataclass(frozen=True)
class MaterialityReport:
    before_word_count: int
    replacement_word_count: int
    before_unique_word_count: int
    replacement_unique_word_count: int
    changed_unique_word_count: int
    changed_unique_word_ratio: float
    required_changed_unique_word_count: int
    required_changed_ratio: float
    exact_copy: bool
    selected_region_copied_inside_replacement: bool
    under_materiality: bool
    failed_materiality_reason: str | None
    target_unit_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "before_word_count": self.before_word_count,
            "replacement_word_count": self.replacement_word_count,
            "before_unique_word_count": self.before_unique_word_count,
            "replacement_unique_word_count": self.replacement_unique_word_count,
            "changed_unique_word_count": self.changed_unique_word_count,
            "changed_unique_word_ratio": round(self.changed_unique_word_ratio, 6),
            "required_changed_unique_word_count": (
                self.required_changed_unique_word_count
            ),
            "required_changed_ratio": self.required_changed_ratio,
            "exact_copy": self.exact_copy,
            "selected_region_copied_inside_replacement": (
                self.selected_region_copied_inside_replacement
            ),
            "near_copy_or_under_materiality": self.under_materiality,
            "failed_materiality_reason": self.failed_materiality_reason,
            "target_unit_ids": list(self.target_unit_ids),
        }


class MaterialityValidationError(ModelValidationError):
    def __init__(self, report: MaterialityReport) -> None:
        super().__init__(_materiality_failure_message(report))
        self.report = report


class ResidualInterventionValidationError(ModelValidationError):
    def __init__(self, validation_report: dict[str, object]) -> None:
        super().__init__(_validation_failure_message(validation_report))
        self.validation_report = validation_report
        compatibility = validation_report.get("materiality_report")
        self.report = (
            _materiality_report_from_compatibility_dict(compatibility)
            if isinstance(compatibility, dict)
            else None
        )


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
        if self.mode == "near_copy":
            return _canonical_json(_near_copy_payload(units, selected_region))
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
        model_payload = _valid_fake_payload_for_subject(subject)
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
            validation_report = _validation_report_from_model_results(
                subject,
                model_results,
            )
            return _failure_result(
                subject=subject,
                packet_dir=packet_dir,
                client_name=client_name,
                model=configured_model,
                artifacts=artifacts,
                model_results=model_results,
                message=_model_failure_message(result),
                materiality_report=_materiality_report_from_validation_report(
                    validation_report
                ),
                validation_report=validation_report,
            )
        model_payload = result.parsed_payload
        model_call_id = result.model_call.id

    try:
        recomposed = _build_recomposed_candidate(subject, model_payload)
    except ModelValidationError as error:
        validation_report = (
            error.validation_report
            if isinstance(error, ResidualInterventionValidationError)
            else None
        )
        materiality_report = _materiality_report_from_validation_report(validation_report)
        if materiality_report is None and isinstance(error, MaterialityValidationError):
            materiality_report = error.report
        return _failure_result(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            artifacts=artifacts,
            model_results=model_results,
            message=f"Residual candidate generation refused; {error}",
            materiality_report=materiality_report,
            validation_report=validation_report,
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
    semantic_failures = semantic_preflight_failures_for_work_order(work_payloads)
    if semantic_failures:
        raise ValueError(
            "source work-order semantic preflight failed: "
            + "; ".join(semantic_failures)
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
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    readiness_failures = target_generation_readiness_failures(
        subject.selected_residual_target_id
    )
    if readiness_failures:
        raise ValueError(
            "target generation readiness failed: "
            + "; ".join(readiness_failures)
        )
    for artifact_type, payload in subject.authorization_payloads.items():
        if payload_has_placeholder_generation_contract(payload):
            raise ValueError(
                "authorization packet uses placeholder generation contract and is "
                "not generation-authoritative: "
                f"{artifact_type}"
            )
    if subject.selected_region_id != SELECTED_REGION_ID:
        raise ValueError("selected region is missing or invalid")
    if not subject.selected_region_sha256:
        raise ValueError("selected region hash is missing")
    if len(subject.target_units) < 1:
        raise ValueError("target unit count must be at least 1")
    for unit in subject.target_units:
        if not unit.before_text.strip():
            raise ValueError(f"target unit {unit.unit_id} before_text is missing")
        if not unit.objects:
            raise ValueError(f"target unit {unit.unit_id} object labels are missing")
        if not unit.current_motion_action_state.strip():
            raise ValueError(
                f"target unit {unit.unit_id} current motion or physical relation is missing"
            )
        if not unit.current_consequence.strip():
            raise ValueError(f"target unit {unit.unit_id} current_consequence is missing")
    if not subject.base_candidate_packet_id or not subject.base_candidate_packet_dir.exists():
        raise ValueError("base candidate packet cannot be resolved")
    if sha256_text(subject.selected_region_before_text) != subject.selected_region_sha256:
        raise ValueError("selected region text hash does not match authorization")
    if subject.selected_region_before_text not in subject.base_text:
        raise ValueError("selected region text cannot be found in base candidate")
    if scope.get("authorized_selected_region_sha256") != subject.selected_region_sha256:
        raise ValueError("scope selected region hash does not match authorization")
    contract = subject.authorization_payloads.get("residual_generation_contract", {})
    if contract.get("selected_residual_target_id") not in {None, subject.selected_residual_target_id}:
        raise ValueError("generation contract target does not match authorization")
    if contract.get("target_adapter_version") and contract.get(
        "target_adapter_version"
    ) != adapter.target_spec_version:
        raise ValueError("generation contract target adapter version is stale")
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
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    driver = ModelDriver(config=config, client=model_client)
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=adapter.worker_role,
            prompt_contract_id=adapter.prompt_contract_id,
            schema=adapter.generation_schema,
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
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
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
            "target_adapter": target_adapter_metadata(subject.selected_residual_target_id),
            "target_prompt_instructions": list(adapter.prompt_instructions),
            "target_mechanism_contract": list(adapter.mechanism_contract),
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
            "residual_generation_contract": subject.authorization_payloads.get(
                "residual_generation_contract",
                {},
            ),
            "materiality_policy": materiality_policy_payload(
                subject.selected_residual_target_id
            ),
            "materiality_requirement": _materiality_requirement_payload(subject),
            "hostile_scaffold_generation_feedback": (
                _hostile_scaffold_generation_feedback(subject)
                if subject.selected_residual_target_id
                == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
                else None
            ),
            "target_unit_overlap_feedback": {
                "overlapping_units_must_be_reconciled": True,
                "instructions": [
                    "produce one integrated selected-region replacement",
                    "reconcile overlapping target units in one coherent passage",
                    "do not write separate duplicated unit rewrites",
                    "do not make the passage busier to satisfy unit coverage",
                    "each target_unit_mapping item must identify how the integrated replacement addresses that unit",
                ],
            },
            "output_rule": (
                "Return one replacement_region_text for the selected region. Do not "
                "return the full artifact. Include exactly one target-unit mapping "
                "entry for each provided unit_id using the schema requested by the "
                "target adapter. The replacement must be materially re-authored, "
                "not a local tightening pass."
            ),
        }
    )


def _materiality_requirement_payload(
    subject: ResidualCandidateSubject,
) -> dict[str, object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    policy = adapter.materiality_policy
    payload: dict[str, object] = {
        "selected_region_materiality_required": True,
        "replacement_must_be_genuinely_reauthored": True,
        "preserve_protected_effects_not_sentence_architecture": True,
        "lexical_substitutions_are_insufficient": True,
        "target_unit_mappings_are_necessary_but_insufficient": True,
        "must_clear_controller_materiality_check": True,
        "required_changed_unique_word_count": REQUIRED_CHANGED_UNIQUE_WORD_COUNT,
        "required_changed_ratio": REQUIRED_CHANGED_RATIO,
        "before_word_count": _word_count(subject.selected_region_before_text),
        "before_unique_word_count": len(_word_set(subject.selected_region_before_text)),
        "do_not_merely_tighten_local_phrases": True,
        "stage_object_motion_causing_visible_consequence_before_explanation": True,
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_mechanism_contract": list(adapter.mechanism_contract),
        "materiality_policy": policy.to_dict(),
        "materiality_policy_id": policy.policy_id,
        "materiality_policy_version": policy.policy_version,
        "primary_materiality_scope": policy.primary_materiality_scope,
        "whole_region_guard": dict(policy.whole_region_guard),
        "target_bearing_scope": dict(policy.target_bearing_scope),
        "target_unit_scope": dict(policy.target_unit_scope),
        "overlap_cluster_policy": dict(policy.overlap_cluster_policy),
        "prompt_feedback": list(policy.prompt_feedback),
        "remain_bounded_to_selected_region": True,
        "do_not_rewrite_whole_artifact": True,
        "do_not_add_decorative_vividness_or_new_object_lists": True,
    }
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        payload["hostile_scaffold_generation_feedback"] = (
            _hostile_scaffold_generation_feedback(subject)
        )
    return payload


def _hostile_scaffold_generation_feedback(
    subject: ResidualCandidateSubject,
) -> dict[str, object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    policy = adapter.materiality_policy
    target_bearing = dict(policy.target_bearing_scope)
    target_unit = dict(policy.target_unit_scope)
    target_bearing_unique_floor = int(
        target_bearing.get("absolute_change_floor", policy.absolute_change_floor)
    )
    target_bearing_ratio_floor = float(
        target_bearing.get("ratio_floor", policy.ratio_floor)
    )
    target_unit_unique_floor = int(
        target_unit.get("absolute_change_floor", policy.absolute_change_floor)
    )
    target_unit_token_floor = int(
        target_unit.get("token_edit_distance_floor", policy.token_edit_distance_floor)
    )
    return {
        "feedback_kind": "hostile_scaffold_generation_materiality_feedback_v1",
        "selected_residual_target_id": subject.selected_residual_target_id,
        "active_materiality_policy_id": policy.policy_id,
        "active_thresholds": {
            "target_bearing_changed_unique_word_count_floor": (
                target_bearing_unique_floor
            ),
            "target_bearing_changed_unique_word_ratio_floor": (
                target_bearing_ratio_floor
            ),
            "per_unit_changed_unique_word_count_floor": target_unit_unique_floor,
            "per_unit_changed_unique_word_ratio_floor": float(
                target_unit.get("ratio_floor", policy.ratio_floor)
            ),
            "per_unit_token_edit_distance_floor": target_unit_token_floor,
        },
        "ordinary_language_thresholds": [
            (
                "The selected target-bearing region must add at least "
                f"{target_bearing_unique_floor} changed unique words."
            ),
            (
                "The selected target-bearing region must reach a changed unique "
                f"word ratio of at least {target_bearing_ratio_floor}."
            ),
            (
                "Each hostile-scaffold target unit must add at least "
                f"{target_unit_unique_floor} changed unique words."
            ),
            (
                "Each hostile-scaffold target unit must move at least "
                f"{target_unit_token_floor} tokens where that floor applies."
            ),
        ],
        "required_target_units": [
            {
                "target_unit_id": unit.unit_id,
                "before_text": unit.before_text,
                "before_text_sha256": unit.before_text_sha256,
                "unit_specific_feedback": (
                    [
                        (
                            "Do not satisfy this unit by changing "
                            '"seems only ordinary" to "is just there" '
                            "or any similarly small sentence-polish variant."
                        ),
                        (
                            "Make the ordinary-table moment carry hostile-scaffold "
                            "reduction through object relation, local pressure, "
                            "or reader encounter."
                        ),
                        (
                            "Keep the intervention bounded to the selected region "
                            "and do not add generic vividness."
                        ),
                    ]
                    if unit.unit_id == HOSTILE_ORDINARY_TABLE_UNIT_ID
                    else []
                ),
            }
            for unit in subject.target_units
        ],
        "unit_specific_feedback": [
            {
                "target_unit_id": HOSTILE_ORDINARY_TABLE_UNIT_ID,
                "failure_to_avoid": (
                    'near-synonym sentence polishing such as "At first, the '
                    'table is just there."'
                ),
                "required_operation": (
                    "materially re-author the ordinary-table moment through "
                    "object relation, local pressure, or reader encounter"
                ),
                "protected_bounds": [
                    "do not rewrite outside the selected region",
                    "do not add generic vividness",
                    "do not imitate the rival",
                ],
            }
        ],
        "failure_shapes_from_packet_0064_regression": [
            {
                "shape": "ordinary_table_sentence_polish",
                "example": "At first, the table is only ordinary.",
                "why_it_fails": (
                    "too close to the source sentence; one local substitution "
                    "does not materially re-author the unit"
                ),
            },
            {
                "shape": "small_kitchen_rule_reorder",
                "example": (
                    "In the small kitchen, one thing enters another, leaves a "
                    "mark, and the mark changes how the next thing is read."
                ),
                "why_it_fails": (
                    "too close to the source rule sentence; reordering or "
                    "lexical tightening does not transfer meaning into the "
                    "object sequence"
                ),
            },
        ],
        "model_feedback": [
            "lexical tightening is insufficient",
            "one-word substitutions are insufficient",
            "preserving target sentence architecture is insufficient",
            'ordinary_table_no_scaffold_signage must not be satisfied by changing "seems only ordinary" to "is just there"',
            "every hostile-scaffold target unit must be materially re-authored",
            "the target-bearing selected region must clear the active materiality policy",
            "reduce scaffold by making the object sequence carry meaning, not by summarizing the thesis",
            "preserve packet_0063 object/tactile causal field",
            "preserve proof/no-answer and opening-return effects as protected references",
            "do not rewrite outside the selected region",
            "do not add generic vividness",
            "do not imitate the rival",
            "do not make finality or phase-shift claims",
        ],
        "semantic_leakage_feedback": [
            "Do not replace one visible thesis with another.",
            (
                "Do not introduce object lists with explanatory labels such as "
                '"their pressure is what counts" or '
                '"ordinary things keep their own pressure."'
            ),
            "Avoid colon-led thesis sentences that announce what the objects mean.",
            "The object sequence must make the relation legible without naming the rule.",
            "Each target unit must solve a distinct local scaffold problem.",
            "Do not reuse one long object-list sentence as the answer to multiple target units.",
            (
                "Physical/object pressure may remain when embodied in object "
                "relations, but abstract pressure as a thesis label is not sufficient."
            ),
        ],
        "diagnostic_labels": [
            "strong_scaffold_reduction",
            "scaffold_reduction_with_leakage",
            "material_but_scaffolded",
            "target_unit_collapsed_into_neighbor",
            "abstract_pressure_label",
            "thesis_before_object_sequence",
            "valid_direction_but_under_material",
            "scaffold_reduction_missing",
            "vague_summary",
            "object_field_weakened",
            "protected_reference_damage",
            "generic_vividness",
            "rival_imitation",
        ],
    }


def _validate_model_payload(
    subject: ResidualCandidateSubject,
    payload: dict[str, object],
) -> None:
    replacement = str(payload.get("replacement_region_text") or "")
    mapping = _mapping_from_model_payload(subject, payload)
    validated_mapping = _validate_target_unit_mapping(subject, mapping)
    if subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        failures = tactile_mapping_failures(
            payload,
            {unit.unit_id for unit in subject.target_units},
        )
        if failures:
            raise ModelValidationError("; ".join(failures))
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        failures = hostile_scaffold_mapping_failures(
            payload,
            {unit.unit_id for unit in subject.target_units},
        )
        if failures:
            raise ModelValidationError("; ".join(failures))
    _validate_replacement_text(
        subject,
        replacement,
        validated_mapping,
        model_payload=payload,
    )


def _mapping_from_model_payload(
    subject: ResidualCandidateSubject,
    payload: dict[str, object],
) -> list[object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    if adapter.generation_schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA:
        mapping = payload.get("target_unit_mappings")
        if not isinstance(mapping, list):
            raise ModelValidationError("target_unit_mappings must be a list")
        return [
            {
                "unit_id": item.get("target_unit_id"),
                "before_text_excerpt": item.get("before_text_sha256"),
                "replacement_text_excerpt": item.get("visible_consequence"),
                "object_motion_or_action": item.get("material_relation_or_action"),
                "visible_consequence": item.get("visible_consequence"),
                "how_reader_infers_pressure_before_explanation": item.get(
                    "intended_first_read_effect"
                ),
                "forbidden_change_avoided": "; ".join(
                    str(value)
                    for value in payload.get("forbidden_change_self_check", [])
                    if isinstance(value, str)
                ),
            }
            for item in mapping
            if isinstance(item, dict)
        ]
    mapping = payload.get("target_unit_mapping")
    if not isinstance(mapping, list):
        raise ModelValidationError("target_unit_mapping must be a list")
    return mapping


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


def _materiality_report(
    subject: ResidualCandidateSubject,
    replacement: str,
) -> MaterialityReport:
    before = subject.selected_region_before_text
    before_words = _words(before)
    replacement_words = _words(replacement)
    before_word_set = set(before_words)
    replacement_word_set = set(replacement_words)
    changed = replacement_word_set - before_word_set
    changed_ratio = len(changed) / max(1, len(replacement_word_set))
    exact_copy = _canonical_space(replacement) == _canonical_space(before)
    copied_inside = _canonical_space(before) in _canonical_space(replacement)
    failed_reason = None
    if exact_copy:
        failed_reason = "replacement is an exact normalized copy"
    elif copied_inside:
        failed_reason = "replacement contains the selected region unchanged"
    elif len(changed) < REQUIRED_CHANGED_UNIQUE_WORD_COUNT:
        failed_reason = (
            "changed unique word count below required threshold: "
            f"{len(changed)} < {REQUIRED_CHANGED_UNIQUE_WORD_COUNT}"
        )
    elif changed_ratio < REQUIRED_CHANGED_RATIO:
        failed_reason = (
            "changed unique word ratio below required threshold: "
            f"{changed_ratio:.6f} < {REQUIRED_CHANGED_RATIO}"
        )
    return MaterialityReport(
        before_word_count=len(before_words),
        replacement_word_count=len(replacement_words),
        before_unique_word_count=len(before_word_set),
        replacement_unique_word_count=len(replacement_word_set),
        changed_unique_word_count=len(changed),
        changed_unique_word_ratio=changed_ratio,
        required_changed_unique_word_count=REQUIRED_CHANGED_UNIQUE_WORD_COUNT,
        required_changed_ratio=REQUIRED_CHANGED_RATIO,
        exact_copy=exact_copy,
        selected_region_copied_inside_replacement=copied_inside,
        under_materiality=failed_reason is not None,
        failed_materiality_reason=failed_reason,
        target_unit_ids=tuple(unit.unit_id for unit in subject.target_units),
    )


def _validate_replacement_text(
    subject: ResidualCandidateSubject,
    replacement_region_text: str,
    target_unit_mapping: list[dict[str, object]],
    model_payload: dict[str, object] | None = None,
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
    validation_report = _collect_residual_intervention_validation(
        subject=subject,
        replacement=replacement,
        target_unit_mapping=target_unit_mapping,
        model_payload=model_payload or {},
    )
    if validation_report["passed"] is not True:
        raise ResidualInterventionValidationError(validation_report)
    return validation_report


def _collect_residual_intervention_validation(
    *,
    subject: ResidualCandidateSubject,
    replacement: str,
    target_unit_mapping: list[dict[str, object]],
    model_payload: dict[str, object],
) -> dict[str, object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    policy = adapter.materiality_policy
    lower = replacement.lower()
    term_contract = _artifact_driven_term_contract(subject, target_unit_mapping)
    whole = _measure_text_materiality(
        scope_id="whole_selected_region",
        before=subject.selected_region_before_text,
        after=replacement,
        selected_region_before=subject.selected_region_before_text,
    )
    target_before, target_after, target_indexes = _target_bearing_scope_text(
        subject,
        replacement,
    )
    target_bearing = _measure_text_materiality(
        scope_id="target_bearing_scope",
        before=target_before,
        after=target_after,
        selected_region_before=subject.selected_region_before_text,
    )
    protected_context = _protected_context_report(
        subject=subject,
        replacement=replacement,
        target_paragraph_indexes=target_indexes,
    )

    failures = _empty_failure_buckets()
    whole_failures = _materiality_scope_failures(
        whole,
        policy=policy,
        scope_policy=policy.whole_region_guard,
        enforce_primary=(
            policy.whole_region_guard.get("enforce_primary_thresholds") is True
        ),
        enforce_ratio=(
            policy.whole_region_guard.get("do_not_enforce_global_ratio_floor") is not True
        ),
    )
    failures["whole_region_guard_failures"].extend(whole_failures)

    target_bearing_failures: list[str] = []
    if policy.primary_materiality_scope == "target_bearing_scope":
        target_bearing_failures = _materiality_scope_failures(
            target_bearing,
            policy=policy,
            scope_policy=policy.target_bearing_scope,
            enforce_primary=True,
            enforce_ratio=True,
        )
    failures["target_bearing_materiality_failures"].extend(target_bearing_failures)

    if _decorative_list_risk(
        replacement,
        motion_terms=term_contract["motion_terms"],
    ):
        failures["generic_decorative_vividness_failures"].append(
            "replacement_region_text is decorative object listing"
        )

    if subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        for failure in replacement_tactile_failures(
            replacement_text=replacement,
            unit_labels=[label for unit in subject.target_units for label in unit.objects],
        ):
            if "decorative" in failure or "generic" in failure:
                failures["generic_decorative_vividness_failures"].append(failure)
            elif "abstract" in failure:
                failures["abstract_inevitability_failures"].append(failure)
            else:
                failures["tactile_semantic_failures"].append(failure)
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        hostile_failures = replacement_hostile_scaffold_failures(
            replacement_text=replacement,
            selected_region_before_text=subject.selected_region_before_text,
            target_units=[unit_payload(unit) for unit in subject.target_units],
            model_payload=model_payload,
        )
        for category, category_failures in hostile_failures.items():
            failures.setdefault(category, []).extend(category_failures)

    object_terms_present = _terms_present(lower, term_contract["object_terms"])
    motion_terms_present = _terms_present(lower, term_contract["motion_terms"])
    consequence_terms_present = _terms_present(lower, term_contract["consequence_terms"])
    missing_unit_object_terms = _missing_unit_object_terms(subject, lower)
    if (
        missing_unit_object_terms
        and subject.selected_residual_target_id != HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    ):
        failures["object_motion_relabel_failures"].append(
            "replacement_region_text missing artifact-derived object terms for "
            f"target units: {', '.join(missing_unit_object_terms)}"
        )
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        relation_count = _hostile_scaffold_relation_count(replacement)
        if relation_count < 2:
            failures["object_field_preservation_failures"].append(
                "object/tactile pressure relation missing"
            )
    else:
        relation_count = _object_motion_relation_count(
            replacement,
            object_terms=term_contract["object_terms"],
            motion_terms=term_contract["motion_terms"],
            consequence_terms=term_contract["consequence_terms"],
        )
        if relation_count < 2:
            failures["object_motion_relabel_failures"].append(
                "object motion causal relation missing"
            )
        if len(object_terms_present) < term_contract["required_object_term_count"] or len(
            motion_terms_present
        ) < term_contract["required_motion_term_count"]:
            failures["object_motion_relabel_failures"].append(
                "decorative-only replacement lacks object motion"
            )
        if len(consequence_terms_present) < term_contract["required_consequence_term_count"]:
            failures["object_motion_relabel_failures"].append(
                "visible consequence before explanation is missing"
            )

    unit_reports = _target_unit_materiality_reports(
        subject=subject,
        replacement=replacement,
        target_unit_mapping=target_unit_mapping,
        policy=policy,
        failures=failures,
    )
    cluster_reports = _overlap_cluster_reports(
        subject=subject,
        replacement=replacement,
        unit_reports=unit_reports,
        policy=policy,
        failures=failures,
    )
    hostile_semantic_leakage_report: dict[str, object] | None = None
    unit_collapse_report: dict[str, object] | None = None
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        hostile_semantic_leakage_report = _hostile_scaffold_semantic_leakage_report(
            replacement,
        )
        failures["scaffold_leakage_failures"].extend(
            str(failure)
            for failure in hostile_semantic_leakage_report.get("failures", [])
        )
        unit_collapse_report = _hostile_unit_collapse_report(unit_reports)
        failures["unit_collapse_failures"].extend(
            str(failure) for failure in unit_collapse_report.get("failures", [])
        )
        _apply_hostile_unit_collapse_classifications(
            unit_reports=unit_reports,
            unit_collapse_report=unit_collapse_report,
        )
    if (
        subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID
        and protected_context["scope_failure"]
    ):
        failures["protected_context_scope_failures"].append(
            str(protected_context["scope_failure"])
        )

    target_specific_mapping_report: dict[str, object] = {
        "selected_residual_target_id": subject.selected_residual_target_id,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "target_unit_mapping_count": len(target_unit_mapping),
    }
    if subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        target_specific_mapping_report.update(
            {
                "tactile_inevitability_mapping_exists": True,
                "contact_force_material_necessity_encoded": (
                    not failures["tactile_semantic_failures"]
                ),
                "distinct_from_object_motion_causality": (
                    not failures["object_motion_relabel_failures"]
                ),
            }
        )
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        target_specific_mapping_report.update(
            {
                "hostile_scaffold_visibility_mapping_exists": True,
                "scaffold_pressure_reduced": (
                    not failures.get("scaffold_leakage_failures")
                ),
                "proof_no_answer_preserved": (
                    not failures.get("proof_no_answer_deletion_failures")
                ),
                "object_field_preserved": (
                    not failures.get("object_field_preservation_failures")
                ),
            }
        )

    all_failures = [
        failure
        for bucket in failures.values()
        for failure in bucket
    ]
    passed = not all_failures
    compatibility = _compatibility_materiality_report(
        subject=subject,
        whole=whole,
        failures=whole_failures,
    )
    return {
        "passed": passed,
        "selected_region_materiality_passed": passed,
        "changed_word_count": compatibility["changed_unique_word_count"],
        "changed_word_ratio": round(float(compatibility["changed_unique_word_ratio"]), 3),
        "materiality_report": compatibility,
        "materiality_policy": policy.to_dict(),
        "materiality_policy_id": policy.policy_id,
        "materiality_policy_version": policy.policy_version,
        "primary_materiality_scope": policy.primary_materiality_scope,
        "residual_materiality_report": {
            "whole_region_guard": {
                **whole,
                "passed": not whole_failures,
                "failures": whole_failures,
            },
            "target_bearing_scope": {
                **target_bearing,
                "target_paragraph_indexes": list(target_indexes),
                "passed": not target_bearing_failures,
                "failures": target_bearing_failures,
            },
            "protected_context": protected_context,
        },
        "target_unit_materiality_report": {
            "required_unit_count": len(subject.target_units),
            "all_required_units_materially_engaged": all(
                item["materiality_passed"] and item["semantic_passed"]
                for item in unit_reports
            ),
            "units": unit_reports,
        },
        "overlap_cluster_report": {
            "clusters": cluster_reports,
            "overlap_cluster_count": len(cluster_reports),
            "all_overlap_clusters_passed": all(
                item["cluster_materiality_passed"] for item in cluster_reports
            ),
        },
        "residual_intervention_validation_report": {
            "passed": passed,
            "failure_count": len(all_failures),
            "failure_categories": {
                key: list(value) for key, value in failures.items() if value
            },
            "failures": all_failures,
            "controller_final_validation_result": "passed" if passed else "refused",
        },
        "object_motion_relation_count": relation_count,
        "object_terms_present": object_terms_present,
        "motion_terms_present": motion_terms_present,
        "consequence_terms_present": consequence_terms_present,
        "object_terms_source": "target_units_from_work_order",
        "target_specific_mapping_report": target_specific_mapping_report,
        "hostile_scaffold_semantic_leakage_report": hostile_semantic_leakage_report,
        "unit_collapse_report": unit_collapse_report,
        "hostile_scaffold_generation_feedback": (
            _hostile_scaffold_generation_feedback(subject)
            if subject.selected_residual_target_id
            == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
            else None
        ),
        "required_object_term_count": term_contract["required_object_term_count"],
        "required_motion_term_count": term_contract["required_motion_term_count"],
        "required_consequence_term_count": term_contract[
            "required_consequence_term_count"
        ],
        "no_nonselected_region_edits": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "object_list_rejected": True,
        "decorative_vividness_only_rejected": True,
        "full_rewrite_rejected": True,
    }


def _empty_failure_buckets() -> dict[str, list[str]]:
    return {
        "whole_region_guard_failures": [],
        "target_bearing_materiality_failures": [],
        "target_unit_materiality_failures": [],
        "overlap_cluster_failures": [],
        "tactile_semantic_failures": [],
        "object_motion_relabel_failures": [],
        "generic_decorative_vividness_failures": [],
        "abstract_inevitability_failures": [],
        "protected_context_scope_failures": [],
        "scaffold_leakage_failures": [],
        "proof_no_answer_deletion_failures": [],
        "object_field_preservation_failures": [],
        "tactile_object_pressure_preservation_failures": [],
        "vagueness_or_summary_failures": [],
        "decorative_vividness_failures": [],
        "rival_mimicry_failures": [],
        "finality_or_phase_shift_claim_failures": [],
        "unit_collapse_failures": [],
    }


def _materiality_scope_failures(
    measurement: dict[str, object],
    *,
    policy: ResidualMaterialityPolicy,
    scope_policy: dict[str, object],
    enforce_primary: bool,
    enforce_ratio: bool,
) -> list[str]:
    failures: list[str] = []
    scope_id = str(measurement["scope_id"])
    if measurement["exact_copy"] is True and scope_policy.get("exact_copy_fails", True):
        failures.append(f"{scope_id}: exact normalized copy")
    if (
        measurement["selected_region_copied_inside_replacement"] is True
        and scope_policy.get("selected_region_copy_fails", True)
    ):
        failures.append(f"{scope_id}: selected region copied inside replacement")
    token_floor = int(
        scope_policy.get("token_edit_distance_floor", policy.token_edit_distance_floor)
    )
    if token_floor and int(measurement["token_edit_distance"]) < token_floor:
        failures.append(
            f"{scope_id}: token edit distance below floor "
            f"{measurement['token_edit_distance']} < {token_floor}"
        )
    similarity_ceiling = float(
        scope_policy.get(
            "sequence_similarity_ceiling",
            policy.sequence_similarity_ceiling,
        )
    )
    if (
        similarity_ceiling
        and float(measurement["sequence_similarity"]) > similarity_ceiling
    ):
        failures.append(
            f"{scope_id}: sequence similarity above ceiling "
            f"{measurement['sequence_similarity']} > {similarity_ceiling}"
        )
    if not enforce_primary:
        return failures
    absolute_floor = int(
        scope_policy.get("absolute_change_floor", policy.absolute_change_floor)
    )
    if int(measurement["changed_unique_word_count"]) < absolute_floor:
        failures.append(
            f"{scope_id}: changed_unique_word_count below floor "
            f"{measurement['changed_unique_word_count']} < {absolute_floor}"
        )
    if enforce_ratio:
        ratio_floor = float(scope_policy.get("ratio_floor", policy.ratio_floor))
        if float(measurement["changed_unique_word_ratio"]) < ratio_floor:
            failures.append(
                f"{scope_id}: changed_unique_word_ratio below floor "
                f"{measurement['changed_unique_word_ratio']} < {ratio_floor}"
            )
    sentence_floor = int(
        scope_policy.get("changed_sentence_floor", policy.changed_sentence_floor)
    )
    if int(measurement["changed_sentence_count"]) < sentence_floor:
        failures.append(
            f"{scope_id}: changed sentence count below floor "
            f"{measurement['changed_sentence_count']} < {sentence_floor}"
        )
    return failures


def _measure_text_materiality(
    *,
    scope_id: str,
    before: str,
    after: str,
    selected_region_before: str,
) -> dict[str, object]:
    before_words = _words(before)
    after_words = _words(after)
    before_set = set(before_words)
    after_set = set(after_words)
    changed = after_set - before_set
    token_edit_distance = _token_edit_distance(before_words, after_words)
    before_sentences = _sentences(before)
    after_sentences = _sentences(after)
    changed_sentence_count = _changed_sentence_count(before_sentences, after_sentences)
    return {
        "scope_id": scope_id,
        "before_word_count": len(before_words),
        "replacement_word_count": len(after_words),
        "before_unique_word_count": len(before_set),
        "replacement_unique_word_count": len(after_set),
        "changed_unique_word_count": len(changed),
        "changed_unique_word_ratio": round(
            len(changed) / max(1, len(after_set)),
            6,
        ),
        "symmetric_unique_word_difference": len(before_set ^ after_set),
        "token_edit_distance": token_edit_distance,
        "token_edit_distance_ratio": round(
            token_edit_distance / max(1, len(before_words), len(after_words)),
            6,
        ),
        "sequence_similarity": round(
            difflib.SequenceMatcher(a=before_words, b=after_words).ratio(),
            6,
        ),
        "before_sentence_count": len(before_sentences),
        "replacement_sentence_count": len(after_sentences),
        "changed_sentence_count": changed_sentence_count,
        "exact_copy": _canonical_space(after) == _canonical_space(before),
        "selected_region_copied_inside_replacement": (
            bool(selected_region_before.strip())
            and _canonical_space(selected_region_before) in _canonical_space(after)
        ),
        "new_unique_words": sorted(changed),
    }


def _target_bearing_scope_text(
    subject: ResidualCandidateSubject,
    replacement: str,
) -> tuple[str, str, tuple[int, ...]]:
    before_paragraphs = _paragraphs(subject.selected_region_before_text)
    after_paragraphs = _paragraphs(replacement)
    indexes = _target_bearing_paragraph_indexes(subject, before_paragraphs)
    before = "\n\n".join(before_paragraphs[index] for index in indexes)
    after = "\n\n".join(
        after_paragraphs[index]
        for index in indexes
        if index < len(after_paragraphs)
    )
    if not before or not after:
        return subject.selected_region_before_text, replacement, (0,)
    return before, after, indexes


def _target_bearing_paragraph_indexes(
    subject: ResidualCandidateSubject,
    paragraphs: list[str],
) -> tuple[int, ...]:
    indexes: list[int] = []
    for index, paragraph in enumerate(paragraphs):
        paragraph_key = _canonical_space(paragraph)
        if any(_canonical_space(unit.before_text) in paragraph_key for unit in subject.target_units):
            indexes.append(index)
    if indexes:
        return tuple(indexes)
    target_terms = {
        term
        for unit in subject.target_units
        for label in unit.objects
        for term in _significant_terms(label)
    }
    for index, paragraph in enumerate(paragraphs):
        if len(_terms_present(paragraph.lower(), tuple(sorted(target_terms)))) >= 2:
            indexes.append(index)
    return tuple(indexes or [0])


def _protected_context_report(
    *,
    subject: ResidualCandidateSubject,
    replacement: str,
    target_paragraph_indexes: tuple[int, ...],
) -> dict[str, object]:
    before_paragraphs = _paragraphs(subject.selected_region_before_text)
    after_paragraphs = _paragraphs(replacement)
    protected_indexes = [
        index for index in range(len(before_paragraphs)) if index not in target_paragraph_indexes
    ]
    before = "\n\n".join(before_paragraphs[index] for index in protected_indexes)
    after = "\n\n".join(
        after_paragraphs[index]
        for index in protected_indexes
        if index < len(after_paragraphs)
    )
    if not before:
        return {
            "protected_context_present": False,
            "protected_context_preserved": True,
            "scope_failure": None,
        }
    measurement = _measure_text_materiality(
        scope_id="protected_context",
        before=before,
        after=after,
        selected_region_before=subject.selected_region_before_text,
    )
    return {
        **measurement,
        "protected_context_present": True,
        "protected_context_preserved": (
            measurement["exact_copy"] is True
            or float(measurement["sequence_similarity"]) >= 0.70
        ),
        "scope_failure": (
            None
            if after
            else "protected context disappeared from replacement"
        ),
    }


def _target_unit_materiality_reports(
    *,
    subject: ResidualCandidateSubject,
    replacement: str,
    target_unit_mapping: list[dict[str, object]],
    policy: ResidualMaterialityPolicy,
    failures: dict[str, list[str]],
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    mapping_by_unit = {
        str(item.get("target_unit_id") or item.get("unit_id") or ""): item
        for item in target_unit_mapping
    }
    for unit in subject.target_units:
        excerpt = _unit_replacement_excerpt(unit, replacement)
        measurement = _measure_text_materiality(
            scope_id=f"target_unit:{unit.unit_id}",
            before=unit.before_text,
            after=excerpt,
            selected_region_before=subject.selected_region_before_text,
        )
        materiality_failures: list[str] = []
        if policy.primary_materiality_scope == "target_bearing_scope":
            materiality_failures = _materiality_scope_failures(
                measurement,
                policy=policy,
                scope_policy=policy.target_unit_scope,
                enforce_primary=True,
                enforce_ratio=True,
            )
            materiality_failures.extend(
                _hostile_unit_specific_materiality_failures(
                    selected_residual_target_id=subject.selected_residual_target_id,
                    unit=unit,
                    replacement_excerpt=excerpt,
                    measurement=measurement,
                    policy=policy,
                )
            )
            failures["target_unit_materiality_failures"].extend(
                f"{unit.unit_id}: {failure}" for failure in materiality_failures
            )
        semantic = _target_unit_semantic_report(
            unit=unit,
            replacement_excerpt=excerpt,
            mapping=mapping_by_unit.get(unit.unit_id, {}),
            selected_residual_target_id=subject.selected_residual_target_id,
        )
        for failure in semantic["failures"]:
            bucket = "tactile_semantic_failures"
            if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
                bucket = "scaffold_leakage_failures"
            elif "object-motion relabel" in failure:
                bucket = "object_motion_relabel_failures"
            failures[bucket].append(f"{unit.unit_id}: {failure}")
        reports.append(
            {
                "target_unit_id": unit.unit_id,
                "source_unit_role": unit.source_unit_role,
                "before_text_sha256": unit.before_text_sha256,
                "replacement_excerpt": excerpt,
                "materiality": measurement,
                "materiality_passed": not materiality_failures,
                "materiality_failures": materiality_failures,
                "semantic_passed": semantic["passed"],
                "semantic_failures": semantic["failures"],
                "classification": _target_unit_classification(
                    selected_residual_target_id=subject.selected_residual_target_id,
                    materiality_failures=materiality_failures,
                    semantic_failures=semantic["failures"],
                ),
            }
        )
    return reports


def _hostile_unit_specific_materiality_failures(
    *,
    selected_residual_target_id: str,
    unit: TargetUnit,
    replacement_excerpt: str,
    measurement: dict[str, object],
    policy: ResidualMaterialityPolicy,
) -> list[str]:
    if selected_residual_target_id != HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return []
    if unit.unit_id != HOSTILE_ORDINARY_TABLE_UNIT_ID:
        return []
    before = _canonical_space(unit.before_text)
    after = _canonical_space(replacement_excerpt)
    token_floor = int(
        policy.target_unit_scope.get(
            "token_edit_distance_floor",
            policy.token_edit_distance_floor,
        )
    )
    token_distance = int(measurement["token_edit_distance"])
    sentence_polish = (
        "seems only ordinary" in before
        and (
            "table is just there" in after
            or ("table" in after and "just there" in after)
            or (
                token_distance < token_floor
                and "table" in after
                and ("ordinary" in after or "just" in after)
            )
        )
    )
    if not sentence_polish:
        return []
    return [HOSTILE_ORDINARY_TABLE_SENTENCE_POLISH_FAILURE]


def _overlap_cluster_reports(
    *,
    subject: ResidualCandidateSubject,
    replacement: str,
    unit_reports: list[dict[str, object]],
    policy: ResidualMaterialityPolicy,
    failures: dict[str, list[str]],
) -> list[dict[str, object]]:
    by_hash: dict[str, list[TargetUnit]] = {}
    for unit in subject.target_units:
        by_hash.setdefault(unit.before_text_sha256, []).append(unit)
    reports: list[dict[str, object]] = []
    report_by_unit = {
        str(report["target_unit_id"]): report for report in unit_reports
    }
    for before_hash, units in by_hash.items():
        if len(units) < 2:
            continue
        before = units[0].before_text
        after = _cluster_replacement_excerpt(units, replacement)
        measurement = _measure_text_materiality(
            scope_id=f"overlap_cluster:{before_hash[:12]}",
            before=before,
            after=after,
            selected_region_before=subject.selected_region_before_text,
        )
        cluster_failures = _materiality_scope_failures(
            measurement,
            policy=policy,
            scope_policy=policy.target_unit_scope,
            enforce_primary=False,
            enforce_ratio=False,
        )
        integrated = bool(after.strip())
        if not integrated:
            cluster_failures.append("overlap cluster has no integrated replacement")
        failures["overlap_cluster_failures"].extend(cluster_failures)
        member_results = [
            {
                "target_unit_id": unit.unit_id,
                "semantic_passed": report_by_unit[unit.unit_id]["semantic_passed"],
                "semantic_failures": report_by_unit[unit.unit_id]["semantic_failures"],
            }
            for unit in units
        ]
        reports.append(
            {
                "overlap_cluster_id": f"overlap_{before_hash[:12]}",
                "member_unit_ids": [unit.unit_id for unit in units],
                "shared_before_hash": before_hash,
                "integrated_replacement_found": integrated,
                "materiality": measurement,
                "cluster_materiality_passed": not cluster_failures,
                "cluster_failures": cluster_failures,
                "member_semantic_results": member_results,
            }
        )
    return reports


def _target_unit_semantic_report(
    *,
    unit: TargetUnit,
    replacement_excerpt: str,
    mapping: dict[str, object],
    selected_residual_target_id: str,
) -> dict[str, object]:
    if selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return _hostile_target_unit_semantic_report(
            unit=unit,
            replacement_excerpt=replacement_excerpt,
        )
    if selected_residual_target_id != TACTILE_INEVITABILITY_TARGET_ID:
        return {"passed": True, "failures": []}
    replacement_lower = replacement_excerpt.lower()
    failures: list[str] = []
    role_terms = _tactile_terms_for_unit_role(unit.source_unit_role)
    if not _terms_present(replacement_lower, role_terms):
        failures.append("missing tactile necessity for source-unit role")
    if _object_motion_only_tactile_unit(unit, replacement_lower):
        failures.append("object-motion relabel without tactile necessity")
    if any(term in replacement_lower for term in ("inevitability", "inevitable", "non-optional")):
        failures.append("abstract inevitability explanation")
    return {"passed": not failures, "failures": failures}


def _hostile_target_unit_semantic_report(
    *,
    unit: TargetUnit,
    replacement_excerpt: str,
) -> dict[str, object]:
    failures: list[str] = []
    lower = replacement_excerpt.lower()
    if _hostile_abstract_pressure_label(lower):
        failures.append(
            "abstract_pressure_label: ordinary/object pressure is named as an "
            "interpretive label instead of carried by object relation"
        )
    if _hostile_thesis_before_object_sequence(replacement_excerpt):
        failures.append(
            "thesis_before_object_sequence: object list follows an explanatory "
            "lead-in instead of making the relation legible first"
        )
    if _hostile_interpretive_label(lower):
        failures.append(
            "scaffold_reduction_with_leakage: interpretive label remains visible "
            "where the object sequence should carry the relation"
        )
    if failures and not any("abstract_pressure_label" in failure for failure in failures):
        failures.append(
            "material_but_scaffolded: target unit is materially re-authored but "
            "still names the relation too explicitly"
        )
    return {"passed": not failures, "failures": failures}


def _hostile_scaffold_semantic_leakage_report(
    replacement: str,
) -> dict[str, object]:
    diagnostics: list[dict[str, object]] = []
    for sentence in _sentences(replacement):
        lower = sentence.lower()
        if _hostile_abstract_pressure_label(lower):
            diagnostics.append(
                _hostile_leakage_diagnostic(
                    leakage_class="abstract_pressure_label",
                    sentence=sentence,
                    reason=(
                        "pressure is used as an interpretive label rather than "
                        "being embodied in object relation"
                    ),
                )
            )
        if _hostile_interpretive_label(lower):
            diagnostics.append(
                _hostile_leakage_diagnostic(
                    leakage_class="interpretive_label",
                    sentence=sentence,
                    reason=(
                        "the sentence names what counts, matters, or carries a "
                        "rule before the object sequence earns it"
                    ),
                )
            )
        if _hostile_colon_introduced_explanation(sentence):
            diagnostics.append(
                _hostile_leakage_diagnostic(
                    leakage_class="colon_introduced_explanation",
                    sentence=sentence,
                    reason=(
                        "colon-led lead-in announces an explanation for the "
                        "object list"
                    ),
                )
            )
        if _hostile_thesis_before_object_sequence(sentence):
            diagnostics.append(
                _hostile_leakage_diagnostic(
                    leakage_class="thesis_before_object_sequence",
                    sentence=sentence,
                    reason=(
                        "an explanatory thesis appears before the objects carry "
                        "the relation"
                    ),
                )
            )
        if _hostile_object_list_after_explanatory_lead_in(sentence):
            diagnostics.append(
                _hostile_leakage_diagnostic(
                    leakage_class="object_list_used_as_proof_after_explanatory_lead_in",
                    sentence=sentence,
                    reason=(
                        "object list is used as proof after a scaffolded lead-in"
                    ),
                )
            )
    unique_diagnostics = _unique_diagnostics(diagnostics)
    return {
        "failed": bool(unique_diagnostics),
        "leakage_classes": sorted(
            {str(item["leakage_class"]) for item in unique_diagnostics}
        ),
        "likely_offending_spans": [
            str(item["offending_span"]) for item in unique_diagnostics
        ],
        "diagnostics": unique_diagnostics,
        "failures": [
            (
                f"{item['leakage_class']}: {item['reason']}; "
                f"offending_span={item['offending_span']!r}"
            )
            for item in unique_diagnostics
        ],
    }


def _hostile_leakage_diagnostic(
    *,
    leakage_class: str,
    sentence: str,
    reason: str,
) -> dict[str, object]:
    return {
        "leakage_class": leakage_class,
        "offending_span": " ".join(sentence.split()),
        "reason": reason,
    }


def _unique_diagnostics(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    unique_items: list[dict[str, object]] = []
    for item in items:
        key = (str(item.get("leakage_class")), str(item.get("offending_span")))
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items


def _hostile_abstract_pressure_label(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "keep their own pressure",
            "keeps its own pressure",
            "pressure is what counts",
            "their pressure is what counts",
            "pressure field",
        )
    )


def _hostile_interpretive_label(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "what counts",
            "makes them matter",
            "make them matter",
            "matter because",
            "that is the rule",
            "rule the marks carry",
            "the rule the marks carry",
        )
    )


def _hostile_colon_introduced_explanation(sentence: str) -> bool:
    if ":" not in sentence:
        return False
    lead, _sep, body = sentence.partition(":")
    lead_lower = lead.lower()
    body_lower = body.lower()
    if not _hostile_explanatory_lead_in(lead_lower):
        return False
    return len(_terms_present(body_lower, _hostile_object_sequence_terms())) >= 2


def _hostile_thesis_before_object_sequence(sentence: str) -> bool:
    lower = sentence.lower()
    if not _hostile_explanatory_lead_in(lower):
        return False
    object_count = len(_terms_present(lower, _hostile_object_sequence_terms()))
    return object_count >= 3 and (
        ":" in sentence
        or any(
            phrase in lower
            for phrase in (
                "because",
                "so the",
                "therefore",
                "what counts",
                "that is the rule",
            )
        )
    )


def _hostile_object_list_after_explanatory_lead_in(sentence: str) -> bool:
    if ":" not in sentence:
        return False
    lead, _sep, body = sentence.partition(":")
    return _hostile_explanatory_lead_in(lead.lower()) and len(
        _terms_present(body.lower(), _hostile_object_sequence_terms())
    ) >= 4


def _hostile_explanatory_lead_in(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "ordinary things keep",
            "ordinary things",
            "their own pressure",
            "what counts",
            "rule",
            "means",
            "matter because",
            "makes them matter",
            "the marks carry",
        )
    )


def _hostile_object_sequence_terms() -> tuple[str, ...]:
    return (
        "table",
        "ring",
        "glass",
        "trace",
        "dust",
        "window",
        "spoon",
        "saucer",
        "mark",
        "marks",
        "surface",
        "contact",
        "fall",
        "break",
    )


def _hostile_unit_collapse_report(
    unit_reports: list[dict[str, object]],
) -> dict[str, object]:
    groups: list[dict[str, object]] = []
    for index, report in enumerate(unit_reports):
        excerpt = str(report.get("replacement_excerpt") or "")
        normalized = _canonical_space(excerpt)
        if _word_count(normalized) < 8:
            continue
        unit_id = str(report.get("target_unit_id") or "")
        matches = [unit_id]
        for other in unit_reports[index + 1 :]:
            other_excerpt = str(other.get("replacement_excerpt") or "")
            other_normalized = _canonical_space(other_excerpt)
            if _word_count(other_normalized) < 8:
                continue
            if (
                normalized == other_normalized
                or difflib.SequenceMatcher(
                    a=normalized,
                    b=other_normalized,
                ).ratio()
                >= 0.97
            ):
                matches.append(str(other.get("target_unit_id") or ""))
        if len(matches) >= 2:
            leakage = _hostile_scaffold_semantic_leakage_report(excerpt)
            severity = "failure" if leakage["failed"] is True else "warning"
            groups.append(
                {
                    "collapsed_target_unit_ids": matches,
                    "shared_replacement_excerpt": excerpt,
                    "severity": severity,
                    "semantic_leakage_classes": leakage["leakage_classes"],
                }
            )
    failed_collapsed_ids = sorted(
        {
            unit_id
            for group in groups
            if group["severity"] == "failure"
            for unit_id in group["collapsed_target_unit_ids"]
            if unit_id
        }
    )
    return {
        "unit_collapse_detected": bool(groups),
        "unit_collapse_failure_detected": bool(failed_collapsed_ids),
        "collapsed_target_unit_ids": failed_collapsed_ids,
        "collapse_groups": groups,
        "failures": [
            (
                "duplicate replacement sentence reused for distinct hostile "
                f"target units: {', '.join(group['collapsed_target_unit_ids'])}"
            )
            for group in groups
            if group["severity"] == "failure"
        ],
    }


def _apply_hostile_unit_collapse_classifications(
    *,
    unit_reports: list[dict[str, object]],
    unit_collapse_report: dict[str, object],
) -> None:
    collapsed = {
        str(unit_id)
        for unit_id in unit_collapse_report.get("collapsed_target_unit_ids", [])
    }
    if not collapsed:
        return
    for report in unit_reports:
        if str(report.get("target_unit_id")) not in collapsed:
            continue
        failures = report.setdefault("semantic_failures", [])
        if isinstance(failures, list):
            failures.append(
                "target_unit_collapsed_into_neighbor: duplicate replacement "
                "sentence reused for distinct hostile target units"
            )
        report["semantic_passed"] = False
        report["classification"] = "target_unit_collapsed_into_neighbor"


def _target_unit_classification(
    *,
    selected_residual_target_id: str,
    materiality_failures: list[str],
    semantic_failures: list[str],
) -> str:
    if selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return _hostile_target_unit_classification(
            materiality_failures=materiality_failures,
            semantic_failures=semantic_failures,
        )
    if semantic_failures:
        if any("object-motion relabel" in failure for failure in semantic_failures):
            return "object_motion_relabel"
        if any("abstract" in failure for failure in semantic_failures):
            return "abstract_explanation"
        return "semantic_failure"
    if materiality_failures:
        return "valid_direction_but_under_material"
    return "strong_tactile_intervention"


def _hostile_target_unit_classification(
    *,
    materiality_failures: list[str],
    semantic_failures: list[str],
) -> str:
    joined = " ".join(semantic_failures).lower()
    if "target_unit_collapsed_into_neighbor" in joined:
        return "target_unit_collapsed_into_neighbor"
    if "abstract_pressure_label" in joined:
        return "abstract_pressure_label"
    if "thesis_before_object_sequence" in joined:
        return "thesis_before_object_sequence"
    if "scaffold_reduction_with_leakage" in joined:
        return "scaffold_reduction_with_leakage"
    if "material_but_scaffolded" in joined:
        return "material_but_scaffolded"
    if "rival" in joined:
        return "rival_imitation"
    if "generic" in joined or "decorative" in joined or "vividness" in joined:
        return "generic_vividness"
    if "summary" in joined or "vague" in joined:
        return "vague_summary"
    if "proof" in joined or "answer" in joined or "opening" in joined:
        return "protected_reference_damage"
    if "object" in joined or "tactile" in joined or "pressure" in joined:
        return "object_field_weakened"
    if semantic_failures:
        return "scaffold_reduction_missing"
    if materiality_failures:
        return "valid_direction_but_under_material"
    return "strong_scaffold_reduction"


def _unit_replacement_excerpt(unit: TargetUnit, replacement: str) -> str:
    sentences = _sentences(replacement)
    if not sentences:
        return replacement
    label_terms = _unit_label_terms(unit)
    scored = [
        (len(_terms_present(sentence.lower(), label_terms)), index, sentence)
        for index, sentence in enumerate(sentences)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score = scored[0][0]
    if best_score <= 0:
        return sentences[0]
    # Keep the excerpt bounded and deterministic; one strong sentence is enough
    # unless the unit has another adjacent sentence with several labels.
    primary_index = scored[0][1]
    adjacent = [
        sentences[index]
        for index in (primary_index - 1, primary_index + 1)
        if 0 <= index < len(sentences)
        and len(_terms_present(sentences[index].lower(), label_terms)) >= 2
    ]
    excerpt_parts = _unique([scored[0][2], *adjacent])
    return " ".join(excerpt_parts)


def _cluster_replacement_excerpt(units: list[TargetUnit], replacement: str) -> str:
    sentences = _sentences(replacement)
    terms = tuple(sorted({term for unit in units for term in _unit_label_terms(unit)}))
    selected = [
        sentence
        for sentence in sentences
        if len(_terms_present(sentence.lower(), terms)) >= 2
    ]
    return " ".join(_unique(selected)) or replacement


def _unit_label_terms(unit: TargetUnit) -> tuple[str, ...]:
    terms: set[str] = set()
    for label in unit.objects:
        terms.update(_significant_terms(label))
    return tuple(sorted(terms))


def _tactile_terms_for_unit_role(role: str) -> tuple[str, ...]:
    general = {
        "contact",
        "touch",
        "touched",
        "pressure",
        "pressed",
        "weight",
        "resistance",
        "friction",
        "compression",
        "residue",
        "settling",
        "settled",
        "absorption",
        "absorbed",
        "impact",
        "breakage",
        "displacement",
        "surface",
        "against",
        "into",
    }
    by_role = {
        "contact_residue_displacement": {
            "contact",
            "pressure",
            "residue",
            "displacement",
            "taken",
            "tightens",
            "meets",
            "grain",
            "into",
        },
        "surface_residue_disturbance": {
            "contact",
            "pressed",
            "pressure",
            "residue",
            "settling",
            "settled",
            "gathers",
            "surface",
        },
        "impact_breakage": {
            "impact",
            "weight",
            "pressure",
            "force",
            "against",
            "struck",
            "compression",
            "fracture",
            "split",
            "breakage",
        },
    }
    return tuple(sorted(general | by_role.get(role, set())))


def _object_motion_only_tactile_unit(unit: TargetUnit, replacement_lower: str) -> bool:
    if unit.source_unit_role != "impact_breakage":
        return False
    motion_terms = ("fall", "released", "release", "dropped", "drop", "visible")
    tactile_terms = (
        "impact",
        "weight",
        "pressure",
        "force",
        "against",
        "struck",
        "compression",
        "fracture",
        "split",
        "breakage",
    )
    return bool(_terms_present(replacement_lower, motion_terms)) and not bool(
        _terms_present(replacement_lower, tactile_terms)
    )


def _paragraphs(text: str) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text)]
    return [paragraph for paragraph in paragraphs if paragraph]


def _sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]


def _changed_sentence_count(before: list[str], after: list[str]) -> int:
    count = 0
    for index in range(max(len(before), len(after))):
        before_sentence = _canonical_space(before[index]) if index < len(before) else ""
        after_sentence = _canonical_space(after[index]) if index < len(after) else ""
        if before_sentence != after_sentence:
            count += 1
    return count


def _token_edit_distance(before: list[str], after: list[str]) -> int:
    if len(before) < len(after):
        before, after = after, before
    previous = list(range(len(after) + 1))
    for row_index, before_token in enumerate(before, 1):
        current = [row_index] + [0] * len(after)
        for column_index, after_token in enumerate(after, 1):
            current[column_index] = min(
                previous[column_index] + 1,
                current[column_index - 1] + 1,
                previous[column_index - 1] + (before_token != after_token),
            )
        previous = current
    return previous[-1]


def _compatibility_materiality_report(
    *,
    subject: ResidualCandidateSubject,
    whole: dict[str, object],
    failures: list[str],
) -> dict[str, object]:
    failed_reason = "; ".join(failures) if failures else None
    return {
        "before_word_count": whole["before_word_count"],
        "replacement_word_count": whole["replacement_word_count"],
        "before_unique_word_count": whole["before_unique_word_count"],
        "replacement_unique_word_count": whole["replacement_unique_word_count"],
        "changed_unique_word_count": whole["changed_unique_word_count"],
        "changed_unique_word_ratio": whole["changed_unique_word_ratio"],
        "required_changed_unique_word_count": REQUIRED_CHANGED_UNIQUE_WORD_COUNT,
        "required_changed_ratio": REQUIRED_CHANGED_RATIO,
        "exact_copy": whole["exact_copy"],
        "selected_region_copied_inside_replacement": (
            whole["selected_region_copied_inside_replacement"]
        ),
        "near_copy_or_under_materiality": bool(failures),
        "failed_materiality_reason": failed_reason,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "token_edit_distance": whole["token_edit_distance"],
        "sequence_similarity": whole["sequence_similarity"],
        "changed_sentence_count": whole["changed_sentence_count"],
    }


def _artifact_driven_term_contract(
    subject: ResidualCandidateSubject,
    target_unit_mapping: list[dict[str, object]],
) -> dict[str, Any]:
    object_terms = _artifact_object_terms(subject)
    motion_terms = _artifact_motion_terms(subject, target_unit_mapping)
    consequence_terms = _artifact_consequence_terms(subject, target_unit_mapping)
    if not object_terms:
        raise ModelValidationError("target units do not provide object terms")
    if not motion_terms:
        raise ModelValidationError("target units do not provide action terms")
    if not consequence_terms:
        raise ModelValidationError("target units do not provide consequence terms")
    return {
        "object_terms": object_terms,
        "motion_terms": motion_terms,
        "consequence_terms": consequence_terms,
        "required_object_term_count": min(
            len(object_terms),
            max(2, len(subject.target_units) * 2),
        ),
        "required_motion_term_count": min(3, len(motion_terms)),
        "required_consequence_term_count": min(3, len(consequence_terms)),
    }


def _artifact_object_terms(subject: ResidualCandidateSubject) -> tuple[str, ...]:
    terms: set[str] = set()
    for unit in subject.target_units:
        for label in unit.objects:
            terms.update(_significant_terms(label))
    return tuple(sorted(terms))


def _artifact_motion_terms(
    subject: ResidualCandidateSubject,
    target_unit_mapping: list[dict[str, object]],
) -> tuple[str, ...]:
    mapping_by_unit = {
        str(item.get("unit_id") or ""): item for item in target_unit_mapping
    }
    terms: set[str] = set()
    for unit in subject.target_units:
        terms.update(_significant_terms(unit.current_motion_action_state))
        mapping = mapping_by_unit.get(unit.unit_id, {})
        terms.update(_significant_terms(str(mapping.get("object_motion_or_action") or "")))
    terms -= set(_artifact_object_terms(subject))
    if not terms:
        terms.update(FIXTURE_BACKUP_MOTION_TERMS)
    return tuple(sorted(terms))


def _artifact_consequence_terms(
    subject: ResidualCandidateSubject,
    target_unit_mapping: list[dict[str, object]],
) -> tuple[str, ...]:
    mapping_by_unit = {
        str(item.get("unit_id") or ""): item for item in target_unit_mapping
    }
    terms: set[str] = set()
    for unit in subject.target_units:
        terms.update(_significant_terms(unit.current_consequence))
        terms.update(_significant_terms(unit.target_effect))
        mapping = mapping_by_unit.get(unit.unit_id, {})
        terms.update(_significant_terms(str(mapping.get("visible_consequence") or "")))
        terms.update(
            _significant_terms(
                str(mapping.get("how_reader_infers_pressure_before_explanation") or "")
            )
        )
    terms -= set(_artifact_object_terms(subject))
    if not terms:
        terms.update(FIXTURE_BACKUP_CONSEQUENCE_TERMS)
    return tuple(sorted(terms))


def _missing_unit_object_terms(
    subject: ResidualCandidateSubject,
    replacement_lower: str,
) -> list[str]:
    missing = []
    for unit in subject.target_units:
        object_terms = set()
        for label in unit.objects:
            object_terms.update(_significant_terms(label))
        if not object_terms:
            missing.append(unit.unit_id)
            continue
        if not _terms_present(replacement_lower, tuple(sorted(object_terms))):
            missing.append(unit.unit_id)
    return missing


def _build_recomposed_candidate(
    subject: ResidualCandidateSubject,
    model_payload: dict[str, object],
) -> RecomposedCandidate:
    replacement = str(model_payload["replacement_region_text"]).strip()
    validation_report = _validate_replacement_text(
        subject,
        replacement,
        _mapping_from_model_payload(subject, model_payload),
        model_payload=model_payload,
    )
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
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_residual_target_id": subject.selected_residual_target_id,
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "target_unit_count": len(subject.target_units),
        "authorization_consumed": False,
        "planned_authorization_consumption_on_success": True,
        "generation_attempt_index": 1,
        "one_shot_generation": True,
        "bounded_macro_recomposition": True,
        "candidate_generated": False,
        "candidate_generation_intended": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_generation_subject_manifest_v1_controller",
    }


def _build_work_order(subject: ResidualCandidateSubject) -> dict[str, object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    return {
        "work_order_id": f"residual_intervention_{subject.authorization_packet_id}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "before_section_text": subject.selected_region_before_text,
        "target_units": [unit_payload(unit) for unit in subject.target_units],
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "authorization_consumed": False,
        "planned_authorization_consumption_on_success": True,
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
        "materiality_requirement": _materiality_requirement_payload(subject),
        "prompt_contract_id": adapter.prompt_contract_id,
        "prompt_instructions": list(adapter.prompt_instructions),
        "mechanism_contract": list(adapter.mechanism_contract),
        "target_unit_overlap_feedback": {
            "overlapping_units_must_be_reconciled": True,
            "produce_one_integrated_replacement": True,
            "do_not_duplicate_unit_rewrites": True,
            "do_not_make_passage_busier_to_satisfy_unit_coverage": True,
        },
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
        "target_scope": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
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
        "authorization_consumed": False,
        "planned_authorization_consumption_on_success": True,
        "candidate_generated": False,
        "candidate_generation_intended": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "residual_candidate_generation_protected_effects_v1_controller",
    }


def _model_plan_steps(model_payload: dict[str, object]) -> list[object]:
    value = model_payload.get("object_motion_generation_plan")
    if isinstance(value, list):
        return list(value)
    value = model_payload.get("intervention_plan")
    return list(value) if isinstance(value, list) else []


def _model_protected_notes(model_payload: dict[str, object]) -> list[object]:
    value = model_payload.get("protected_effects_preservation_notes")
    if isinstance(value, list):
        return list(value)
    value = model_payload.get("protected_effects_notes")
    return list(value) if isinstance(value, list) else []


def _model_predicted_reader_effect(
    subject: ResidualCandidateSubject,
    model_payload: dict[str, object],
) -> object:
    if "predicted_reader_effect" in model_payload:
        return model_payload["predicted_reader_effect"]
    if subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        return "reader feels material consequence before interpretation explains it"
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return "reader feels object-field pressure without visible scaffold"
    return ""


def _model_target_unit_mapping(
    subject: ResidualCandidateSubject,
    model_payload: dict[str, object],
) -> list[object]:
    adapter = require_residual_target_adapter(subject.selected_residual_target_id)
    if adapter.generation_schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA:
        value = model_payload.get("target_unit_mappings")
        return list(value) if isinstance(value, list) else []
    value = model_payload.get("target_unit_mapping")
    return list(value) if isinstance(value, list) else []


def _build_recomposition_plan(
    *,
    subject: ResidualCandidateSubject,
    model_payload: dict[str, object],
    model_call_id: str | None,
) -> dict[str, object]:
    return {
        "plan_id": f"residual_intervention_plan_{sha256_text(subject.authorization_packet_id)[:12]}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "intervention_plan": _model_plan_steps(model_payload),
        "object_motion_generation_plan": _model_plan_steps(model_payload),
        "protected_effects_preservation_notes": _model_protected_notes(model_payload),
        "predicted_reader_effect": _model_predicted_reader_effect(subject, model_payload),
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
        "patch_or_section_plan_id": f"residual_intervention_patch_{sha256_text(recomposed.text)[:12]}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "before_section_text": subject.selected_region_before_text,
        "replacement_section_text": recomposed.replacement_region_text,
        "replacement_section_text_sha256": sha256_text(recomposed.replacement_region_text),
        "target_unit_mapping": _mapping_from_model_payload(subject, model_payload),
        "target_unit_mappings": _model_target_unit_mapping(subject, model_payload),
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "forbidden_change_self_check": list(model_payload["forbidden_change_self_check"]),
        "target_coverage_report": _target_coverage_report(subject, recomposed),
        "source_model_call_id": model_call_id,
        "model_owned_fields": [
            "replacement_region_text",
            "target_unit_mapping",
            "target_unit_mappings",
            "object_motion_generation_plan/intervention_plan",
            "protected_effects_preservation_notes/protected_effects_notes",
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
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "residual_materiality_report": recomposed.validation_report.get(
            "residual_materiality_report"
        ),
        "target_unit_materiality_report": recomposed.validation_report.get(
            "target_unit_materiality_report"
        ),
        "overlap_cluster_report": recomposed.validation_report.get(
            "overlap_cluster_report"
        ),
        "residual_intervention_validation_report": recomposed.validation_report.get(
            "residual_intervention_validation_report"
        ),
        "text": recomposed.text,
        "text_sha256": sha256_text(recomposed.text),
        "word_count": _word_count(recomposed.text),
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": (
            subject.selected_residual_target_id == OBJECT_MOTION_CAUSALITY_TARGET_ID
        ),
        "residual_intervention_generation": True,
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
            "changed_span_id": f"{subject.selected_residual_target_id}_region_001",
            "patch_span_id": f"{subject.selected_residual_target_id}_region_001",
            "before": subject.selected_region_before_text,
            "after": recomposed.replacement_region_text,
            "before_text": subject.selected_region_before_text,
            "after_text": recomposed.replacement_region_text,
            "region": subject.selected_region_id,
            "target_expansion_reason": "",
            "reason": f"bounded {subject.selected_residual_target_id} generation",
            "inside_target": True,
            "within_selected_target": True,
            "requires_target_expansion": False,
            "source_patch_span_ids": [f"{subject.selected_residual_target_id}_region_001"],
        }
    ]
    return {
        "diff_report_id": f"residual_intervention_diff_{sha256_text(str(candidate['text']))[:12]}",
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "candidate_text_sha256": candidate["text_sha256"],
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "selected_region_sha256": subject.selected_region_sha256,
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": (
            subject.selected_residual_target_id == OBJECT_MOTION_CAUSALITY_TARGET_ID
        ),
        "residual_intervention_generation": True,
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
        "target_scope": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "strongest_rival_defeated": False,
        "rival_mimicry_detected": False,
        "object_motion_relation_count": recomposed.validation_report[
            "object_motion_relation_count"
        ],
        "target_specific_mapping_report": recomposed.validation_report.get(
            "target_specific_mapping_report",
            {},
        ),
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
        _gate_result("target_specific_mapping_exists", True),
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
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": (
            subject.selected_residual_target_id == OBJECT_MOTION_CAUSALITY_TARGET_ID
        ),
        "residual_intervention_generation": True,
        "target_specific_ablation_controls": list(
            require_residual_target_adapter(
                subject.selected_residual_target_id
            ).ablation_controls
        ),
        "target_specific_reader_state_focus": list(
            require_residual_target_adapter(
                subject.selected_residual_target_id
            ).reader_state_evaluation_focus
        ),
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
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
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
        "residual_materiality_report": payloads["macro_recomposition_diff_report"][
            "materiality_report"
        ].get("residual_materiality_report"),
        "target_unit_materiality_report": payloads["macro_recomposition_diff_report"][
            "materiality_report"
        ].get("target_unit_materiality_report"),
        "overlap_cluster_report": payloads["macro_recomposition_diff_report"][
            "materiality_report"
        ].get("overlap_cluster_report"),
        "residual_intervention_validation_report": payloads[
            "macro_recomposition_diff_report"
        ]["materiality_report"].get("residual_intervention_validation_report"),
        "bounded_macro_recomposition": True,
        "object_motion_causality_generation": (
            subject.selected_residual_target_id == OBJECT_MOTION_CAUSALITY_TARGET_ID
        ),
        "residual_intervention_generation": True,
        "one_shot_generation": True,
        "full_rewrite": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "requires_reader_state_eval_before_reader_state_claim": True,
        "next_recommended_action": require_residual_target_adapter(
            subject.selected_residual_target_id
        ).review_action,
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
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "model": model,
        "model_call_ids": [result.model_call.id for result in model_results],
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "next_recommended_action": require_residual_target_adapter(
            subject.selected_residual_target_id
        ).review_action,
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
    materiality_report: MaterialityReport | dict[str, object] | None = None,
    validation_report: dict[str, object] | None = None,
) -> ResidualCandidateGenerationResult:
    if isinstance(materiality_report, MaterialityReport):
        materiality_payload = materiality_report.to_dict()
    else:
        materiality_payload = materiality_report
    validation_payload = validation_report or {}
    failure_categories = {}
    residual_validation = validation_payload.get("residual_intervention_validation_report")
    if isinstance(residual_validation, dict):
        failure_categories = residual_validation.get("failure_categories") or {}
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
            "target_scope": subject.selected_residual_target_id,
            "target_movement": subject.selected_residual_target_id,
            **target_adapter_metadata(subject.selected_residual_target_id),
            "model_call_ids": [result.model_call.id for result in model_results],
            "model_calls": [result.model_call_to_dict() for result in model_results],
            "materiality_report": materiality_payload,
            "residual_materiality_report": validation_payload.get(
                "residual_materiality_report"
            ),
            "target_unit_materiality_report": validation_payload.get(
                "target_unit_materiality_report"
            ),
            "overlap_cluster_report": validation_payload.get("overlap_cluster_report"),
            "hostile_scaffold_semantic_leakage_report": validation_payload.get(
                "hostile_scaffold_semantic_leakage_report"
            ),
            "unit_collapse_report": validation_payload.get("unit_collapse_report"),
            "residual_intervention_validation_report": residual_validation,
            "validation_failure_categories": failure_categories,
            "hostile_scaffold_generation_feedback": validation_payload.get(
                "hostile_scaffold_generation_feedback"
            ),
            "failed_materiality_reason": (
                materiality_payload["failed_materiality_reason"]
                if materiality_payload
                else None
            ),
            "before_word_count": (
                materiality_payload["before_word_count"] if materiality_payload else None
            ),
            "replacement_word_count": (
                materiality_payload["replacement_word_count"]
                if materiality_payload
                else None
            ),
            "changed_unique_word_count": (
                materiality_payload["changed_unique_word_count"]
                if materiality_payload
                else None
            ),
            "changed_unique_word_ratio": (
                materiality_payload["changed_unique_word_ratio"]
                if materiality_payload
                else None
            ),
            "required_changed_unique_word_count": REQUIRED_CHANGED_UNIQUE_WORD_COUNT,
            "required_changed_ratio": REQUIRED_CHANGED_RATIO,
            "exact_copy": materiality_payload["exact_copy"] if materiality_payload else None,
            "near_copy_or_under_materiality": (
                materiality_payload["near_copy_or_under_materiality"]
                if materiality_payload
                else None
            ),
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "next_recommended_action": "review_failed_residual_intervention_generation",
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
    target_id = str(unit_map.get("selected_residual_target_id") or "")
    for item in unit_map.get("target_units", []):
        if not isinstance(item, dict):
            continue
        before_text = str(item.get("before_text") or "")
        objects = tuple(str(value) for value in item.get("objects", []) if str(value))
        if not objects and target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
            objects = tuple(sorted(_significant_terms(before_text))[:5])
        units.append(
            TargetUnit(
                unit_id=str(item.get("unit_id") or ""),
                before_text=before_text,
                before_text_sha256=str(item.get("before_text_sha256") or ""),
                objects=objects,
                target_effect=str(item.get("target_effect") or ""),
                current_motion_action_state=str(
                    item.get("current_motion_action_state")
                    or item.get("current_physical_relation")
                    or item.get("allowed_operation")
                    or item.get("weakness")
                    or ""
                ),
                current_consequence=str(
                    item.get("current_consequence")
                    or item.get("target_effect")
                    or item.get("intended_first_read_effect")
                    or ""
                ),
                current_physical_relation=str(item.get("current_physical_relation") or ""),
                source_unit_role=str(item.get("source_unit_role") or ""),
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
        if payload.get("source_authorization_packet_id") != subject.authorization_packet_id:
            continue
        if artifact.type == "macro_recomposed_candidate_text" and (
            payload.get("candidate_generated") is True
            and payload.get("authorization_consumed") is True
        ):
            return artifact
        if artifact.type == "macro_recomposition_packet" and (
            payload.get("candidate_generated") is True
            and payload.get("authorization_consumed") is True
            and payload.get("candidate_artifact_id")
        ):
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
        "target_scope": subject.selected_residual_target_id,
        "target_movement": subject.selected_residual_target_id,
        **target_adapter_metadata(subject.selected_residual_target_id),
        "selected_region_id": subject.selected_region_id,
        "target_unit_ids": [unit.unit_id for unit in subject.target_units],
        "active_targets_covered": [unit.unit_id for unit in subject.target_units],
        "active_targets_missing": [],
        "selected_region_materiality_passed": recomposed.validation_report[
            "selected_region_materiality_passed"
        ],
        "object_motion_causality_mapping_exists": True,
        "target_specific_mapping_exists": True,
        "target_specific_ablation_controls": list(
            require_residual_target_adapter(
                subject.selected_residual_target_id
            ).ablation_controls
        ),
        "target_specific_reader_state_focus": list(
            require_residual_target_adapter(
                subject.selected_residual_target_id
            ).reader_state_evaluation_focus
        ),
        "target_specific_mapping_report": recomposed.validation_report.get(
            "target_specific_mapping_report",
            {},
        ),
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


def _object_motion_relation_count(
    text: str,
    *,
    object_terms: tuple[str, ...],
    motion_terms: tuple[str, ...],
    consequence_terms: tuple[str, ...],
) -> int:
    count = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if (
            len(_terms_present(lower, object_terms)) >= 2
            and _terms_present(lower, motion_terms)
            and _terms_present(lower, consequence_terms)
        ):
            count += 1
    return count


def _hostile_scaffold_relation_count(text: str) -> int:
    object_terms = (
        "table",
        "dust",
        "spoon",
        "saucer",
        "ring",
        "cup",
        "crumb",
        "grain",
        "surface",
        "mark",
    )
    pressure_terms = (
        "pressure",
        "mark",
        "trace",
        "contact",
        "crossing",
        "crossings",
        "weight",
        "carried",
        "leans",
        "pulls",
        "gathers",
        "turns",
    )
    count = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if _terms_present(lower, object_terms) and _terms_present(lower, pressure_terms):
            count += 1
    return count


def _decorative_list_risk(
    text: str,
    *,
    motion_terms: tuple[str, ...] = FIXTURE_BACKUP_MOTION_TERMS,
) -> bool:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if sentence.count(",") >= 4 and not _terms_present(sentence.lower(), motion_terms):
            return True
    return False


def _terms_present(text: str, terms: tuple[str, ...]) -> list[str]:
    return sorted({term for term in terms if term in text})


def _significant_terms(text: str) -> set[str]:
    return {
        word
        for word in _words(text)
        if len(word) >= 3 and word not in TERM_STOPWORDS
    }


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text.lower())


def _word_set(text: str) -> set[str]:
    return set(_words(text))


def _word_count(text: str) -> int:
    return len(_words(text))


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


def _materiality_failure_message(report: MaterialityReport) -> str:
    payload = report.to_dict()
    return (
        "selected region materiality failed: "
        f"before_word_count={payload['before_word_count']}; "
        f"replacement_word_count={payload['replacement_word_count']}; "
        f"changed_unique_word_count={payload['changed_unique_word_count']}; "
        f"changed_unique_word_ratio={payload['changed_unique_word_ratio']}; "
        f"required_changed_unique_word_count={payload['required_changed_unique_word_count']}; "
        f"required_changed_ratio={payload['required_changed_ratio']}; "
        f"exact_copy={payload['exact_copy']}; "
        f"near_copy_or_under_materiality={payload['near_copy_or_under_materiality']}; "
        f"failed_materiality_reason={payload['failed_materiality_reason']}; "
        f"target_unit_ids={','.join(str(value) for value in payload['target_unit_ids'])}"
    )


def _validation_failure_message(validation_report: dict[str, object]) -> str:
    residual = validation_report.get("residual_intervention_validation_report")
    failures: list[str] = []
    categories: dict[str, object] = {}
    if isinstance(residual, dict):
        failures = [str(item) for item in residual.get("failures", [])]
        raw_categories = residual.get("failure_categories")
        categories = raw_categories if isinstance(raw_categories, dict) else {}
    if not failures:
        return "residual intervention validation failed"
    prefix = (
        "selected region materiality failed"
        if categories.get("whole_region_guard_failures")
        else "residual intervention validation failed"
    )
    return f"{prefix}: " + "; ".join(failures)


def _validation_report_from_model_results(
    subject: ResidualCandidateSubject,
    model_results: list[ModelDriverResult],
) -> dict[str, object] | None:
    for result in reversed(model_results):
        error_message = result.model_call.error_message or ""
        if "materiality" not in error_message and "validation" not in error_message:
            continue
        raw_output_path = result.model_call.raw_output_path
        if not raw_output_path:
            continue
        try:
            raw_output = Path(raw_output_path).read_text(encoding="utf-8")
            payload = json.loads(raw_output)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        replacement = payload.get("replacement_region_text")
        if not isinstance(replacement, str) or not replacement.strip():
            continue
        try:
            mapping = _mapping_from_model_payload(subject, payload)
            validated_mapping = _validate_target_unit_mapping(subject, mapping)
            return _collect_residual_intervention_validation(
                subject=subject,
                replacement=replacement.strip(),
                target_unit_mapping=validated_mapping,
                model_payload=payload,
            )
        except ModelValidationError:
            return {
                "materiality_report": _materiality_report(subject, replacement).to_dict(),
                "residual_intervention_validation_report": {
                    "passed": False,
                    "failure_count": 1,
                    "failure_categories": {
                        "schema_or_mapping_failures": [error_message],
                    },
                    "failures": [error_message],
                    "controller_final_validation_result": "refused",
                },
            }
    return None


def _materiality_report_from_validation_report(
    validation_report: dict[str, object] | None,
) -> dict[str, object] | None:
    if not validation_report:
        return None
    value = validation_report.get("materiality_report")
    return dict(value) if isinstance(value, dict) else None


def _materiality_report_from_compatibility_dict(
    payload: object,
) -> MaterialityReport | None:
    if not isinstance(payload, dict):
        return None
    return MaterialityReport(
        before_word_count=int(payload.get("before_word_count") or 0),
        replacement_word_count=int(payload.get("replacement_word_count") or 0),
        before_unique_word_count=int(payload.get("before_unique_word_count") or 0),
        replacement_unique_word_count=int(
            payload.get("replacement_unique_word_count") or 0
        ),
        changed_unique_word_count=int(payload.get("changed_unique_word_count") or 0),
        changed_unique_word_ratio=float(payload.get("changed_unique_word_ratio") or 0),
        required_changed_unique_word_count=int(
            payload.get("required_changed_unique_word_count")
            or REQUIRED_CHANGED_UNIQUE_WORD_COUNT
        ),
        required_changed_ratio=float(
            payload.get("required_changed_ratio") or REQUIRED_CHANGED_RATIO
        ),
        exact_copy=payload.get("exact_copy") is True,
        selected_region_copied_inside_replacement=(
            payload.get("selected_region_copied_inside_replacement") is True
        ),
        under_materiality=payload.get("near_copy_or_under_materiality") is True,
        failed_materiality_reason=(
            str(payload.get("failed_materiality_reason"))
            if payload.get("failed_materiality_reason")
            else None
        ),
        target_unit_ids=tuple(
            str(value) for value in payload.get("target_unit_ids", [])
        ),
    )


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


def _valid_fake_payload_for_subject(subject: ResidualCandidateSubject) -> dict[str, object]:
    units = [unit_payload(unit) for unit in subject.target_units]
    if subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID:
        return _valid_tactile_fake_payload(units)
    if subject.selected_residual_target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        return _valid_hostile_scaffold_fake_payload(units)
    return _valid_fake_payload(units)


def _valid_tactile_fake_payload(units: list[dict[str, object]]) -> dict[str, object]:
    replacement = _tactile_replacement_from_units(units)
    mappings = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        relation = str(unit.get("current_physical_relation") or unit.get("current_motion_action_state") or "")
        mappings.append(
            {
                "target_unit_id": unit_id,
                "before_text_sha256": str(unit.get("before_text_sha256") or ""),
                "mechanism_operation": "make contact, pressure, residue, displacement, or breakage materially causal",
                "material_relation_or_action": relation
                or "material contact leaves a visible consequence",
                "visible_consequence": str(unit.get("target_effect") or "the surface keeps the mark"),
                "intended_first_read_effect": (
                    "the reader feels the material consequence before explanation names it"
                ),
                "protected_effects_preserved": [
                    "current-best partial reread transformation",
                    "proof/no-answer gains",
                    "return structure preservation",
                ],
                "covered_target_ids": [unit_id, TACTILE_INEVITABILITY_TARGET_ID],
            }
        )
    return {
        "replacement_region_text": replacement,
        "target_unit_mappings": mappings,
        "intervention_plan": [
            "replace only the selected middle recurrence region",
            "preserve object-motion gains while adding tactile necessity",
            "keep interpretation after material consequence",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "replacement_region_text covers only the selected region",
                "risk_note": "controller assembles the final candidate",
            },
            {
                "constraint_id": "avoid_generic_vividness",
                "how_satisfied": "force and contact relations carry the change",
                "risk_note": "no new object inventory is introduced",
            },
        ],
        "protected_effects_notes": [
            "opening, proof, and final return remain outside the replacement",
            "strongest-rival pressure remains blocking",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no nonselected region edits",
            "no rival mimicry",
            "no abstract inevitability explanation",
        ],
        "uncertainty": "fixture output for deterministic tests only",
    }


def _valid_hostile_scaffold_fake_payload(
    units: list[dict[str, object]],
) -> dict[str, object]:
    replacement = (
        "The cup ring dries at one rim and pulls the crumb deeper into the grain; "
        "the mark is already on the table before anyone reaches for a name. Dust "
        "from hand, foot, and air gathers in the same pale run, and the spoon "
        "turns toward the saucer's broken edge. At first the table is only "
        "itself. Its surface keeps the crossings as a small pressure: cup to "
        "ring, ring to crumb, dust to path, spoon to saucer. The kitchen stays "
        "small, and every mark leans on another mark until the room's weight is "
        "carried by the things."
    )
    mappings = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        labels = " ".join(
            str(value)
            for value in unit.get("objects", [])
            if isinstance(value, str)
        )
        mappings.append(
            {
                "target_unit_id": unit_id,
                "before_text_sha256": str(unit.get("before_text_sha256") or ""),
                "mechanism_operation": (
                    "reduce visible scaffold by letting material marks and contact "
                    "carry pressure"
                ),
                "material_relation_or_action": (
                    labels
                    or str(unit.get("current_motion_action_state") or "object pressure")
                ),
                "visible_consequence": (
                    "the object field carries the local consequence before the line "
                    "turns explanatory"
                ),
                "intended_first_read_effect": (
                    "reader feels the relation from marks and pressure rather than "
                    "from visible scaffold"
                ),
                "protected_effects_preserved": [
                    "proof/no-answer pressure remains outside the selected region",
                    "opening-return and reread gains remain protected",
                    "table dust spoon saucer ring causal field remains active",
                ],
                "covered_target_ids": [
                    unit_id,
                    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
                ],
            }
        )
    return {
        "replacement_region_text": replacement,
        "target_unit_mappings": mappings,
        "intervention_plan": [
            "replace only the selected middle recurrence region",
            "reduce visible scaffold without deleting proof/no-answer pressure",
            "preserve tactile/object gains and protected references outside the region",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "replacement_region_text covers only the selected region",
                "risk_note": "controller assembles the final candidate",
            },
            {
                "constraint_id": "hostile_scaffold_visibility_generation_materiality_v1",
                "how_satisfied": "object marks carry pressure before explanation",
                "risk_note": "requires later ablation and reader-state evaluation",
            },
        ],
        "protected_effects_notes": [
            "proof/no-answer pressure preserved",
            "opening-return reread gains preserved",
            "object/tactile field with table, dust, spoon, saucer, and ring preserved",
            "strongest-rival pressure remains blocking",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no nonselected region edits",
            "no rival imitation",
            "no vague summary compression",
        ],
        "uncertainty": "fixture output for deterministic tests only",
    }


def _tactile_replacement_from_units(units: list[dict[str, object]]) -> str:
    sentences = []
    for unit in units:
        labels = [str(value) for value in unit.get("objects", []) if str(value)]
        if not labels:
            labels = ["object", "surface", "mark"]
        label_phrase = " ".join(labels[:5])
        relation = str(
            unit.get("current_physical_relation")
            or unit.get("current_motion_action_state")
            or "contact pressure leaves a mark"
        )
        sentences.append(
            f"The {label_phrase} relation works through contact and pressure: "
            f"{relation}, so a visible mark remains as material consequence before "
            "any explanation names it."
        )
    return (
        " ".join(sentences)
        + "\n\nAt first, the room seems only ordinary. But ordinary things are "
        "strict about what reaches them. Pressure crosses a surface and the mark "
        "changes what the next object can be; residue, displacement, and breakage "
        "hold the force locally before thought turns it into a rule."
    )


def _near_copy_payload(
    units: list[dict[str, object]],
    selected_region: str,
) -> dict[str, object]:
    payload = _valid_fake_payload(units)
    replacement = selected_region
    replacements = (
        ("ordinary", "common"),
        ("seems", "appears"),
        ("small", "minor"),
        ("changed", "altered"),
        ("answer", "reply"),
        ("object", "thing"),
    )
    for before, after in replacements:
        replacement = re.sub(rf"\b{re.escape(before)}\b", after, replacement, count=1)
    payload["replacement_region_text"] = replacement
    for mapping in payload["target_unit_mapping"]:
        mapping["replacement_text_excerpt"] = payload["replacement_region_text"][:260]
    return payload


def unit_payload(unit: TargetUnit | dict[str, object]) -> dict[str, object]:
    if isinstance(unit, dict):
        return dict(unit)
    return {
        "unit_id": unit.unit_id,
        "before_text": unit.before_text,
        "before_text_sha256": unit.before_text_sha256,
        "objects": list(unit.objects),
        "target_effect": unit.target_effect,
        "current_motion_action_state": unit.current_motion_action_state,
        "current_consequence": unit.current_consequence,
        "current_physical_relation": unit.current_physical_relation,
        "source_unit_role": unit.source_unit_role,
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
            "target_scope": None,
            "target_movement": None,
            "finalization_eligible": False,
            "no_phase_shift_claim": True,
            "next_recommended_action": "review_refusal_before_generation",
        },
    )


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
