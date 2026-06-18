"""Evaluation, baselines, and human-trace import scaffold for Phase 11."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path

from abi.artifacts import ArtifactRecord, get_artifact, list_all_artifacts
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import PHASE11_EVALUATION_BASELINES_ACTIVE_PHASE, set_active_phase
from abi.db import connect, initialize_database
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient, ModelClientError, ModelDriver, ModelDriverResult
from abi.model_driver import WorkerRequest
from abi.model_schemas import (
    EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA,
    EVALUATION_BEST_OF_N_BASELINE_SCHEMA,
    EVALUATION_MODEL_SCHEMAS,
    WorkerRole,
    WorkerSchema,
)
from abi.modules.human_calibration import FIXTURE_RELATIVE_DIR, build_human_calibration_payloads
from abi.modules.production_run import (
    PRODUCTION_RUN_CLIENT_FAKE,
    PRODUCTION_RUN_MAX_MODEL_CALLS_DEFAULT,
    run_production_live_demo,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


EVALUATION_LINEAGE_ID = "phase11_evaluation_baselines"
EVALUATION_GATE_NAME = "evaluation_baselines_v1"
EVALUATION_PROMPT_CONTRACT_PREFIX = "phase11.evaluation_baselines"
EVALUATION_CLIENT_FAKE = "fake"
EVALUATION_CLIENT_OPENAI = "openai"
EVALUATION_CLIENTS = (EVALUATION_CLIENT_FAKE, EVALUATION_CLIENT_OPENAI)
EVALUATION_MAX_MODEL_CALLS_DEFAULT = 12
EVALUATION_REQUIRED_MODEL_CALLS = len(EVALUATION_MODEL_SCHEMAS)
EVALUATION_FAKE_PROVIDER = "fake"
EVALUATION_FAKE_MODEL = "fake-evaluation-baselines-v1"
EVALUATION_ARTIFACT_TYPES = (
    "evaluation_subject",
    "evaluation_candidate_artifact_ref",
    "evaluation_direct_prompt_baseline",
    "evaluation_best_of_n_baseline_summary",
    "evaluation_blind_comparison_protocol",
    "evaluation_blind_comparison_result",
    "evaluation_human_trace_import",
    "evaluation_reader_state_transition_comparison",
    "evaluation_baseline_comparison_report",
    "evaluation_gate_report",
    "evaluation_packet",
)


@dataclass(frozen=True)
class EvaluationResult:
    exit_code: int
    payload: dict[str, object]
    model_results: tuple[ModelDriverResult, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class EvaluationSubject:
    run_id: str
    production_packet_artifact: ArtifactRecord
    production_packet_payload: dict[str, object]
    candidate_artifact: ArtifactRecord
    candidate_payload: dict[str, object]


@dataclass(frozen=True)
class EvaluationWorkerSpec:
    schema: WorkerSchema
    worker_role: WorkerRole
    prompt_contract_id: str
    parent_artifact_types: tuple[str, ...]

    @property
    def artifact_type(self) -> str:
        return self.schema.artifact_type


EVALUATION_WORKERS = (
    EvaluationWorkerSpec(
        schema=EVALUATION_BEST_OF_N_BASELINE_SCHEMA,
        worker_role=WorkerRole.EVALUATION_BASELINE_SUMMARIZER,
        prompt_contract_id=f"{EVALUATION_PROMPT_CONTRACT_PREFIX}.best_of_n_baseline",
        parent_artifact_types=("evaluation_direct_prompt_baseline",),
    ),
    EvaluationWorkerSpec(
        schema=EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA,
        worker_role=WorkerRole.EVALUATION_COMPARISON_REPORTER,
        prompt_contract_id=f"{EVALUATION_PROMPT_CONTRACT_PREFIX}.comparison_report",
        parent_artifact_types=(
            "evaluation_candidate_artifact_ref",
            "evaluation_best_of_n_baseline_summary",
            "evaluation_reader_state_transition_comparison",
        ),
    ),
)


class FakeEvaluationClient:
    provider = EVALUATION_FAKE_PROVIDER
    model = EVALUATION_FAKE_MODEL

    def __init__(
        self,
        *,
        mode: str = "valid",
        target_schema: WorkerSchema = EVALUATION_BEST_OF_N_BASELINE_SCHEMA,
    ) -> None:
        self.mode = mode
        self.target_schema = target_schema

    def generate(self, request: WorkerRequest) -> str:
        if request.schema == self.target_schema and self.mode == "invalid":
            return "{not valid json"
        if request.schema == self.target_schema and self.mode == "failure":
            raise ModelClientError("simulated fake evaluation client failure")
        if self.mode not in ("valid", "invalid", "failure"):
            raise ModelClientError(f"unknown fake evaluation client mode: {self.mode}")
        if request.schema == EVALUATION_BEST_OF_N_BASELINE_SCHEMA:
            return _canonical_json(_fake_best_of_n_baseline_payload())
        if request.schema == EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA:
            return _canonical_json(_fake_baseline_comparison_report_payload())
        raise ModelClientError(f"unsupported fake evaluation schema: {request.schema.name}")


def run_evaluation_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool = False,
    max_model_calls: int = EVALUATION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    fake_mode: str = "valid",
    fake_target_schema: WorkerSchema = EVALUATION_BEST_OF_N_BASELINE_SCHEMA,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> EvaluationResult:
    if client_name not in EVALUATION_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            message=f"Evaluation demo client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < EVALUATION_REQUIRED_MODEL_CALLS:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == EVALUATION_CLIENT_OPENAI else None,
            message=(
                "Evaluation demo refused; max-model-calls "
                f"{max_model_calls} is below required budget {EVALUATION_REQUIRED_MODEL_CALLS}."
            ),
        )

    if client_name == EVALUATION_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message="Evaluation demo refused; pass --allow-live-model to opt in explicitly.",
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == EVALUATION_CLIENT_OPENAI and not resolved_api_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=f"Evaluation demo refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    subject = _load_or_create_production_subject(config)
    packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "evaluation")
    with connect(config.db_path) as connection:
        set_active_phase(connection, subject.run_id, PHASE11_EVALUATION_BASELINES_ACTIVE_PHASE)

    if client_name == EVALUATION_CLIENT_FAKE:
        client = FakeEvaluationClient(mode=fake_mode, target_schema=fake_target_schema)
        fixture_only = True
        model_name = client.model
    else:
        factory = client_factory or _default_openai_client_factory
        client = factory(configured_model)
        fixture_only = False
        model_name = configured_model

    return _run_evaluation_packet(
        config=config,
        subject=subject,
        packet_dir=packet_dir,
        client_name=client_name,
        model=model_name,
        model_client=client,
        fixture_only=fixture_only,
        max_model_calls=max_model_calls,
    )


def _load_or_create_production_subject(config: AbiConfig) -> EvaluationSubject:
    subject = _load_latest_production_subject(config)
    if subject is not None:
        return subject
    result = run_production_live_demo(
        config,
        client_name=PRODUCTION_RUN_CLIENT_FAKE,
        max_model_calls=PRODUCTION_RUN_MAX_MODEL_CALLS_DEFAULT,
    )
    if result.exit_code != 0:
        raise RuntimeError(f"Unable to create fake production subject: {result.payload['message']}")
    subject = _load_latest_production_subject(config)
    if subject is None:
        raise RuntimeError("Fake production subject was not registered")
    return subject


def _load_latest_production_subject(config: AbiConfig) -> EvaluationSubject | None:
    if not config.db_path.exists():
        return None
    initialize_database(config)
    with connect(config.db_path) as connection:
        production_packets = [
            artifact
            for artifact in list_all_artifacts(connection)
            if artifact.type == "production_packet"
        ]
        if not production_packets:
            return None
        production_packet_artifact = production_packets[-1]
        production_packet = read_json_file(production_packet_artifact.path)
        production_payload = production_packet["payload"]
        candidate_id = production_payload["candidate_artifact_id"]
        candidate_artifact = get_artifact(connection, candidate_id)
        if candidate_artifact is None:
            raise RuntimeError(f"Production candidate artifact not found: {candidate_id}")
    candidate_payload = read_json_file(candidate_artifact.path)["payload"]
    return EvaluationSubject(
        run_id=production_packet_artifact.run_id,
        production_packet_artifact=production_packet_artifact,
        production_packet_payload=production_payload,
        candidate_artifact=candidate_artifact,
        candidate_payload=candidate_payload,
    )


def _run_evaluation_packet(
    *,
    config: AbiConfig,
    subject: EvaluationSubject,
    packet_dir: Path,
    client_name: str,
    model: str,
    model_client: ModelClient,
    fixture_only: bool,
    max_model_calls: int,
) -> EvaluationResult:
    calibration_payloads = build_human_calibration_payloads(config.root / FIXTURE_RELATIVE_DIR)
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, object]] = {}
    model_results: list[ModelDriverResult] = []

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=EVALUATION_LINEAGE_ID,
            created_by="evaluation_baselines_scaffold",
            fixture_only=fixture_only,
        )
        payloads["evaluation_subject"] = _build_evaluation_subject_payload(subject)
        artifacts["evaluation_subject"] = writer.write_artifact(
            "evaluation_subject",
            payloads["evaluation_subject"],
            parent_ids=[subject.production_packet_artifact.id],
        )
        payloads["evaluation_candidate_artifact_ref"] = _build_candidate_ref_payload(subject)
        artifacts["evaluation_candidate_artifact_ref"] = writer.write_artifact(
            "evaluation_candidate_artifact_ref",
            payloads["evaluation_candidate_artifact_ref"],
            parent_ids=[subject.candidate_artifact.id, artifacts["evaluation_subject"].id],
        )
        payloads["evaluation_direct_prompt_baseline"] = _build_direct_prompt_baseline_payload(
            calibration_payloads
        )
        artifacts["evaluation_direct_prompt_baseline"] = writer.write_artifact(
            "evaluation_direct_prompt_baseline",
            payloads["evaluation_direct_prompt_baseline"],
            parent_ids=[artifacts["evaluation_subject"].id],
        )

    driver = ModelDriver(config=config, client=model_client)
    result = _run_model_worker(
        driver=driver,
        worker=EVALUATION_WORKERS[0],
        subject=subject,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
        fixture_only=fixture_only,
    )
    model_results.append(result)
    if not result.accepted or result.parsed_artifact is None or result.parsed_payload is None:
        return _failure_result(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            message="Evaluation demo stopped by model-call failure.",
        )
    artifacts[result.parsed_artifact.type] = result.parsed_artifact
    payloads[result.parsed_artifact.type] = result.parsed_payload

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=EVALUATION_LINEAGE_ID,
            created_by="evaluation_baselines_scaffold",
            fixture_only=fixture_only,
        )
        payloads["evaluation_blind_comparison_protocol"] = _build_blind_protocol_payload()
        artifacts["evaluation_blind_comparison_protocol"] = writer.write_artifact(
            "evaluation_blind_comparison_protocol",
            payloads["evaluation_blind_comparison_protocol"],
            parent_ids=[
                artifacts["evaluation_candidate_artifact_ref"].id,
                artifacts["evaluation_direct_prompt_baseline"].id,
                artifacts["evaluation_best_of_n_baseline_summary"].id,
            ],
        )
        payloads["evaluation_human_trace_import"] = _build_human_trace_import_payload(
            calibration_payloads
        )
        artifacts["evaluation_human_trace_import"] = writer.write_artifact(
            "evaluation_human_trace_import",
            payloads["evaluation_human_trace_import"],
            parent_ids=[
                artifacts["evaluation_candidate_artifact_ref"].id,
                artifacts["evaluation_blind_comparison_protocol"].id,
            ],
        )
        payloads["evaluation_blind_comparison_result"] = _build_blind_result_payload(
            payloads=payloads
        )
        artifacts["evaluation_blind_comparison_result"] = writer.write_artifact(
            "evaluation_blind_comparison_result",
            payloads["evaluation_blind_comparison_result"],
            parent_ids=[
                artifacts["evaluation_blind_comparison_protocol"].id,
                artifacts["evaluation_human_trace_import"].id,
            ],
        )
        payloads["evaluation_reader_state_transition_comparison"] = (
            _build_reader_state_transition_comparison_payload(payloads=payloads)
        )
        artifacts["evaluation_reader_state_transition_comparison"] = writer.write_artifact(
            "evaluation_reader_state_transition_comparison",
            payloads["evaluation_reader_state_transition_comparison"],
            parent_ids=[
                artifacts["evaluation_blind_comparison_result"].id,
                artifacts["evaluation_human_trace_import"].id,
                artifacts["evaluation_best_of_n_baseline_summary"].id,
            ],
        )

    if len(model_results) + 1 > max_model_calls:
        return _failure_result(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            message="Evaluation demo stopped by max-model-calls budget.",
        )

    result = _run_model_worker(
        driver=driver,
        worker=EVALUATION_WORKERS[1],
        subject=subject,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
        fixture_only=fixture_only,
    )
    model_results.append(result)
    if not result.accepted or result.parsed_artifact is None or result.parsed_payload is None:
        return _failure_result(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            message="Evaluation demo stopped by model-call failure.",
        )
    artifacts[result.parsed_artifact.type] = result.parsed_artifact
    payloads[result.parsed_artifact.type] = result.parsed_payload

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=EVALUATION_LINEAGE_ID,
            created_by="evaluation_baselines_scaffold",
            fixture_only=fixture_only,
        )
        payloads["evaluation_gate_report"] = _build_gate_report_payload(
            payloads=payloads,
            model_results=model_results,
            max_model_calls=max_model_calls,
        )
        artifacts["evaluation_gate_report"] = writer.write_artifact(
            "evaluation_gate_report",
            payloads["evaluation_gate_report"],
            parent_ids=[
                artifacts["evaluation_candidate_artifact_ref"].id,
                artifacts["evaluation_human_trace_import"].id,
                artifacts["evaluation_baseline_comparison_report"].id,
            ],
        )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name=EVALUATION_GATE_NAME,
            passed=bool(payloads["evaluation_gate_report"]["passed"]),
            blocking_defects=list(payloads["evaluation_gate_report"]["blocking_defects"]),
            lineage_id=EVALUATION_LINEAGE_ID,
        )
        payloads["evaluation_packet"] = _build_packet_summary_payload(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            max_model_calls=max_model_calls,
        )
        artifacts["evaluation_packet"] = writer.write_artifact(
            "evaluation_packet",
            payloads["evaluation_packet"],
            parent_ids=[artifacts[artifact_type].id for artifact_type in EVALUATION_ARTIFACT_TYPES[:-1]],
        )

    return EvaluationResult(
        exit_code=0,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=str(packet_dir),
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            refused=False,
            accepted=True,
            message=None,
        ),
        model_results=tuple(model_results),
        gate_record=gate_record,
    )


def _run_model_worker(
    *,
    driver: ModelDriver,
    worker: EvaluationWorkerSpec,
    subject: EvaluationSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    fixture_only: bool,
) -> ModelDriverResult:
    parent_ids = [
        artifacts[artifact_type].id
        for artifact_type in worker.parent_artifact_types
        if artifact_type in artifacts
    ]
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=worker.worker_role,
            prompt_contract_id=worker.prompt_contract_id,
            schema=worker.schema,
            input_text=_model_input_text(subject=subject, payloads=payloads),
            input_artifact_ids=parent_ids,
            input_packet_path=str(packet_dir),
            lineage_id=EVALUATION_LINEAGE_ID,
            parent_ids=parent_ids,
            fixture_only=fixture_only,
            output_dir=str(packet_dir),
        )
    )


def _build_evaluation_subject_payload(subject: EvaluationSubject) -> dict[str, object]:
    return {
        "worker": "evaluation_subject_builder_v1",
        "production_packet_artifact_id": subject.production_packet_artifact.id,
        "production_packet_lineage_id": subject.production_packet_artifact.lineage_id,
        "candidate_artifact_id": subject.candidate_artifact.id,
        "candidate_id": subject.candidate_payload["candidate_id"],
        "candidate_flags": _candidate_flags(subject.candidate_payload),
        "scope": "Phase 11 evaluation scaffold only",
        "claims_not_made": [
            "no final artifact claim",
            "no phase-shift claim",
            "no real human validation claim",
        ],
    }


def _build_candidate_ref_payload(subject: EvaluationSubject) -> dict[str, object]:
    return {
        "worker": "evaluation_candidate_artifact_reference_v1",
        "candidate_artifact_id": subject.candidate_artifact.id,
        "candidate_artifact_path": subject.candidate_artifact.path,
        "candidate_id": subject.candidate_payload["candidate_id"],
        "text": subject.candidate_payload["text"],
        "candidate_flags": _candidate_flags(subject.candidate_payload),
        "source_recomposed_draft_artifact_id": subject.candidate_payload[
            "source_recomposed_draft_artifact_id"
        ],
    }


def _build_direct_prompt_baseline_payload(
    calibration_payloads: dict[str, object],
) -> dict[str, object]:
    baseline = calibration_payloads["calibration_baseline_comparison"]
    return {
        "worker": "evaluation_direct_prompt_baseline_fixture_v1",
        "baseline_id": "direct_prompt_fixture_baseline_v1",
        "baseline_type": "direct_prompt_fixture",
        "fixture_only": True,
        "fake": True,
        "not_real_validation": True,
        "baseline_path": baseline["baseline_path"],
        "baseline_sha256": baseline["baseline_sha256"],
        "text_summary": baseline["baseline_summary"],
        "baseline_limit": (
            "This fixture baseline explains symbolism directly and is not a generated "
            "or validated external comparison."
        ),
    }


def _build_blind_protocol_payload() -> dict[str, object]:
    return {
        "worker": "evaluation_blind_comparison_protocol_v1",
        "fixture_only": True,
        "not_real_validation": True,
        "protocol_id": "evaluation_blind_protocol_fixture_v1",
        "artifact_labels_hidden": True,
        "comparison_axes": [
            "opening interpretation shift",
            "retained image specificity",
            "paraphrase loss",
            "unsupported depth flags",
        ],
        "claims_not_made": [
            "no real blind study was run",
            "no statistical inference",
            "no phase-shift claim",
        ],
    }


def _build_human_trace_import_payload(
    calibration_payloads: dict[str, object],
) -> dict[str, object]:
    trial = calibration_payloads["calibration_human_reader_trial"]
    transition = calibration_payloads["calibration_reader_state_transition"]
    return {
        "worker": "evaluation_human_trace_import_v1",
        "fixture_only": True,
        "not_real_validation": True,
        "source_path": trial["source_path"],
        "source_sha256": trial["source_sha256"],
        "trial_id": trial["trial_id"],
        "reader_label": trial["reader_label"],
        "first_read": trial["first_read"],
        "reread": trial["reread"],
        "reader_state_transition": transition,
        "claims_not_made": [
            "no live survey result",
            "no real human validation claim",
        ],
    }


def _build_blind_result_payload(
    *,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    human_trace = payloads["evaluation_human_trace_import"]
    best_of_n = payloads["evaluation_best_of_n_baseline_summary"]
    return {
        "worker": "evaluation_blind_comparison_result_fixture_v1",
        "fixture_only": True,
        "not_real_validation": True,
        "comparison_id": "evaluation_blind_result_fixture_v1",
        "artifact_labels_hidden": True,
        "candidate_a": {
            "label": "artifact_a",
            "source": "candidate_artifact_fixture_ref",
            "observed_transition": human_trace["reader_state_transition"][
                "changed_opening_interpretation"
            ],
        },
        "candidate_b": {
            "label": "artifact_b",
            "source": best_of_n["selected_baseline_id"],
            "observed_transition": "fixture baseline states meaning before reread pressure can accrue",
        },
        "fixture_preference": "artifact_a",
        "preference_is_not_validation": True,
        "claims_not_made": [
            "no real blind study was run",
            "no baseline victory claim",
        ],
    }


def _build_reader_state_transition_comparison_payload(
    *,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    human_trace = payloads["evaluation_human_trace_import"]
    direct_baseline = payloads["evaluation_direct_prompt_baseline"]
    return {
        "worker": "evaluation_reader_state_transition_comparer_v1",
        "fixture_only": True,
        "not_real_validation": True,
        "candidate_transition": human_trace["reader_state_transition"],
        "direct_prompt_baseline_id": direct_baseline["baseline_id"],
        "baseline_transition_stub": {
            "changed_opening_interpretation": (
                "reader recognizes stated symbolism without delayed reread gain"
            ),
            "unsupported_depth_flags": ["fixture baseline is explanatory by construction"],
        },
        "comparison_limits": [
            "fixture trace only",
            "not real human validation",
            "not a phase-shift claim",
        ],
    }


def _build_gate_report_payload(
    *,
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    max_model_calls: int,
) -> dict[str, object]:
    candidate_flags = payloads["evaluation_candidate_artifact_ref"]["candidate_flags"]
    human_trace = payloads["evaluation_human_trace_import"]
    direct_baseline = payloads["evaluation_direct_prompt_baseline"]
    comparison_report = payloads["evaluation_baseline_comparison_report"]
    defects = []
    if not candidate_flags["non_final"]:
        defects.append("candidate must remain non-final")
    if not candidate_flags["not_human_validated"]:
        defects.append("candidate must remain not human validated")
    if not candidate_flags["not_finalization_eligible"]:
        defects.append("candidate must remain not finalization eligible")
    if candidate_flags["human_validation_claim"]:
        defects.append("candidate must not make a human validation claim")
    if candidate_flags["phase_shift_claim"]:
        defects.append("candidate must not make a phase-shift claim")
    if not human_trace["fixture_only"] or not human_trace["not_real_validation"]:
        defects.append("human-trace import must be fixture-only and not real validation")
    if not direct_baseline["fixture_only"] or not direct_baseline["not_real_validation"]:
        defects.append("direct prompt baseline must be fixture-only and not real validation")
    if "no phase-shift claim" not in comparison_report["claims_not_made"]:
        defects.append("comparison report must refuse phase-shift claims")
    if len(model_results) > max_model_calls:
        defects.append("evaluation model-call count exceeds max-model-calls budget")

    return {
        "worker": "evaluation_gate_evaluator_v1",
        "gate_name": EVALUATION_GATE_NAME,
        "fixture_only": True,
        "not_real_validation": True,
        "passed": not defects,
        "blocking_defects": defects,
        "gate_scores": {
            "candidate_non_final": 1.0 if candidate_flags["non_final"] else 0.0,
            "human_trace_fixture": 1.0
            if human_trace["fixture_only"] and human_trace["not_real_validation"]
            else 0.0,
            "direct_baseline_fixture": 1.0
            if direct_baseline["fixture_only"] and direct_baseline["not_real_validation"]
            else 0.0,
            "model_calls": len(model_results),
        },
        "finalization_gate": False,
        "finalization_eligible": False,
        "summary_verdict": (
            "Evaluation fixture packet passes scaffold gates without making validation claims."
            if not defects
            else "Evaluation fixture packet is blocked by scaffold gate defects."
        ),
    }


def _build_packet_summary_payload(
    *,
    client_name: str,
    model: str,
    subject: EvaluationSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    max_model_calls: int,
) -> dict[str, object]:
    return {
        "worker": "evaluation_packet_summarizer_v1",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "client": client_name,
        "model": model,
        "artifact_types": list(EVALUATION_ARTIFACT_TYPES),
        "artifact_ids": {artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        "production_packet_artifact_id": subject.production_packet_artifact.id,
        "candidate_artifact_id": subject.candidate_artifact.id,
        "candidate_flags": payloads["evaluation_candidate_artifact_ref"]["candidate_flags"],
        "human_trace": {
            "fixture_only": payloads["evaluation_human_trace_import"]["fixture_only"],
            "not_real_validation": payloads["evaluation_human_trace_import"][
                "not_real_validation"
            ],
        },
        "baseline_flags": {
            "direct_prompt_fixture_only": payloads["evaluation_direct_prompt_baseline"][
                "fixture_only"
            ],
            "direct_prompt_not_real_validation": payloads["evaluation_direct_prompt_baseline"][
                "not_real_validation"
            ],
            "best_of_n_fixture_only": payloads["evaluation_best_of_n_baseline_summary"][
                "fixture_only"
            ],
            "best_of_n_not_real_validation": payloads[
                "evaluation_best_of_n_baseline_summary"
            ]["not_real_validation"],
        },
        "model_call_ids": [result.model_call.id for result in model_results],
        "counts": {
            "evaluation_artifacts": len(EVALUATION_ARTIFACT_TYPES),
            "model_calls": len(model_results),
            "max_model_calls": max_model_calls,
        },
        "gate_summary": {
            "gate_name": payloads["evaluation_gate_report"]["gate_name"],
            "passed": payloads["evaluation_gate_report"]["passed"],
            "blocking_defects": payloads["evaluation_gate_report"]["blocking_defects"],
            "summary_verdict": payloads["evaluation_gate_report"]["summary_verdict"],
        },
        "claims_not_made": [
            "no final artifact claim",
            "no phase-shift claim",
            "no real human validation claim",
        ],
        "finalization_eligible": False,
        "lineage_id": EVALUATION_LINEAGE_ID,
    }


def _summary_payload(
    *,
    client_name: str,
    model: str | None,
    subject: EvaluationSubject | None,
    packet_dir: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    refused: bool,
    accepted: bool,
    message: str | None,
) -> dict[str, object]:
    return {
        "refused": refused,
        "accepted": accepted,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id if subject is not None else None,
        "packet_id": Path(packet_dir).name if packet_dir else None,
        "packet_dir": packet_dir,
        "required_artifact_types": list(EVALUATION_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "production_packet_artifact_id": (
            subject.production_packet_artifact.id if subject is not None else None
        ),
        "candidate_artifact_id": subject.candidate_artifact.id if subject is not None else None,
        "candidate_flags": payloads.get("evaluation_candidate_artifact_ref", {}).get(
            "candidate_flags",
            {},
        ),
        "human_trace": _human_trace_summary(payloads),
        "baseline_flags": _baseline_flags(payloads),
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "counts": {
            "evaluation_artifacts": len(payloads),
            "required_evaluation_artifacts": len(EVALUATION_ARTIFACT_TYPES),
            "model_calls": len(model_results),
        },
        "gate_result": _gate_result(payloads),
        "message": message,
    }


def _human_trace_summary(payloads: dict[str, dict[str, object]]) -> dict[str, object]:
    human_trace = payloads.get("evaluation_human_trace_import")
    if human_trace is None:
        return {}
    return {
        "fixture_only": human_trace["fixture_only"],
        "not_real_validation": human_trace["not_real_validation"],
        "trial_id": human_trace["trial_id"],
    }


def _baseline_flags(payloads: dict[str, dict[str, object]]) -> dict[str, object]:
    direct = payloads.get("evaluation_direct_prompt_baseline")
    best = payloads.get("evaluation_best_of_n_baseline_summary")
    return {
        "direct_prompt_fixture_only": direct["fixture_only"] if direct else None,
        "direct_prompt_not_real_validation": direct["not_real_validation"] if direct else None,
        "best_of_n_fixture_only": best["fixture_only"] if best else None,
        "best_of_n_not_real_validation": best["not_real_validation"] if best else None,
    }


def _gate_result(payloads: dict[str, dict[str, object]]) -> dict[str, object] | None:
    gate_report = payloads.get("evaluation_gate_report")
    if gate_report is None:
        return None
    return {
        "gate_name": gate_report["gate_name"],
        "passed": gate_report["passed"],
        "blocking_defects": gate_report["blocking_defects"],
        "summary_verdict": gate_report["summary_verdict"],
        "finalization_eligible": gate_report["finalization_eligible"],
    }


def _failure_result(
    *,
    client_name: str,
    model: str,
    subject: EvaluationSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    message: str,
) -> EvaluationResult:
    return EvaluationResult(
        exit_code=1,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=str(packet_dir),
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            refused=False,
            accepted=False,
            message=message,
        ),
        model_results=tuple(model_results),
    )


def _refusal(*, client_name: str, model: str | None, message: str) -> EvaluationResult:
    return EvaluationResult(
        exit_code=1,
        payload={
            "refused": True,
            "accepted": False,
            "client": client_name,
            "model": model,
            "run_id": None,
            "packet_id": None,
            "packet_dir": None,
            "artifact_ids": {},
            "model_calls": [],
            "message": message,
        },
    )


def _candidate_flags(candidate_payload: dict[str, object]) -> dict[str, object]:
    return {
        "non_final": candidate_payload["non_final"],
        "candidate_only": candidate_payload["candidate_only"],
        "not_human_validated": candidate_payload["not_human_validated"],
        "not_finalization_eligible": candidate_payload["not_finalization_eligible"],
        "finalization_eligible": candidate_payload["finalization_eligible"],
        "human_validated": candidate_payload["human_validated"],
        "human_validation_claim": candidate_payload["human_validation_claim"],
        "phase_shift_claim": candidate_payload["phase_shift_claim"],
    }


def _model_input_text(
    *,
    subject: EvaluationSubject,
    payloads: dict[str, dict[str, object]],
) -> str:
    return _canonical_json(
        {
            "candidate_id": subject.candidate_payload["candidate_id"],
            "candidate_flags": _candidate_flags(subject.candidate_payload),
            "available_payloads": payloads,
        }
    )


def _fake_best_of_n_baseline_payload() -> dict[str, object]:
    return {
        "baseline_set_id": "best_of_n_fixture_set_v1",
        "fixture_only": True,
        "not_real_validation": True,
        "generated_by": "fake_evaluation_client",
        "n": 3,
        "baseline_candidates": [
            {
                "id": "baseline_n_01",
                "summary": "Explains the table as memory before the reader can discover pressure.",
                "known_limit": "front-loads meaning",
            },
            {
                "id": "baseline_n_02",
                "summary": "Keeps the room and table but treats morning as atmosphere.",
                "known_limit": "weakens reread causality",
            },
            {
                "id": "baseline_n_03",
                "summary": "Adds plot around the room and loses the benchmark object.",
                "known_limit": "expands beyond the source constraint",
            },
        ],
        "selected_baseline_id": "baseline_n_02",
        "selection_rationale": "Fixture baseline keeps closest surface overlap with the candidate.",
        "risks": ["fixture baseline set is not a generated or validated external comparison"],
    }


def _fake_baseline_comparison_report_payload() -> dict[str, object]:
    return {
        "comparison_id": "baseline_comparison_fixture_report_v1",
        "fixture_only": True,
        "not_real_validation": True,
        "candidate_id": "candidate_table_morning_scaffold_v1",
        "baseline_ids": ["direct_prompt_fixture_baseline_v1", "baseline_n_02"],
        "observed_reader_state_delta": {
            "candidate": "fixture trace marks still as pressure after reread",
            "baseline": "fixture baseline states symbolism without delayed pressure",
        },
        "comparison_summary": (
            "The fixture comparison preserves candidate lineage and baseline limits, "
            "but does not claim that Abi has beaten a real baseline."
        ),
        "claims_not_made": [
            "no phase-shift claim",
            "no real human validation claim",
            "no final artifact claim",
        ],
        "risks": ["fixture comparison cannot support external validation claims"],
    }


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
