"""Reader-state evaluation for selected nonlocal-law target candidates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_EVALUATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import MODEL_CALL_VALIDATION_FAILED, link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ModelValidationError,
    SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA,
    SELECTED_READER_STATE_REQUIRED_RISK_PROBES,
    WorkerRole,
)
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_consolidated_target_selection import (
    SELECTED_RISK_ID,
    SELECTED_TARGET_SEED_ID,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
)
from abi.modules.nonlocal_law_selected_target_candidate_ablation import (
    ABLATION_CONTROL_IDS,
    NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES,
    RISKS_TO_TEST,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_LINEAGE_ID = (
    "nonlocal_law_selected_target_reader_state_evaluation_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CREATED_BY = (
    "nonlocal_law_selected_target_reader_state_evaluation_v1_controller"
)
NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CLIENTS = ("fake", "openai")
NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_REQUIRED_MODEL_CALLS = 1
NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_MAX_MODEL_CALLS_DEFAULT = 1
PROMPT_CONTRACT_ID = (
    "autonomous.selected_nonlocal_law_candidate_reader_state_evaluation.v1"
)
NEXT_RECOMMENDED_ACTION = "synthesize_selected_nonlocal_law_candidate_evidence"
FAILED_NEXT_RECOMMENDED_ACTION = (
    "fix_selected_target_reader_state_risk_probe_contract_before_live_retry"
)
RISK_PROBE_CONTRACT_FAILURE_CLASS = (
    "selected_target_reader_state_risk_probe_contract_failure"
)
RISK_PROBE_CONTRACT_FAILURE_REASON = "missing_required_risk_probes"

QUALITATIVE_RESULTS = (
    "improved",
    "preserved",
    "worsened",
    "mixed",
    "active_risk",
    "narrowed_but_blocking",
    "unsupported",
    "requires_synthesis",
)
STRONGEST_RIVAL_RESULTS = (
    "narrowed_but_blocking",
    "unchanged_blocking",
    "worsened",
    "requires_synthesis",
)
EXPECTED_OVEREXPLAINED_PHRASES = (
    "changes the next glance",
    "changes the order of seeing",
    "later seeing must be changed",
    "condition through which the next perception has to pass",
)

NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_ARTIFACT_TYPES = (
    "source_ablation_intake_summary",
    "selected_target_candidate_reader_state_subject",
    "base_packet_0002_reader_state_control_subject",
    "selected_target_ablation_reader_state_matrix",
    "living_event_sequence_reader_state_report",
    "static_trace_reduction_reader_state_report",
    "causal_bridge_reader_state_report",
    "consequence_before_naming_reader_state_report",
    "causal_mechanism_overexplained_probe_report",
    "explanation_earned_preservation_report",
    "packet_0002_gains_preservation_report",
    "non_imitation_reader_state_report",
    "strongest_rival_pressure_status_report",
    "selected_target_risk_probe_report",
    "synthesis_readiness_report",
    "selected_target_reader_state_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_selected_target_reader_state_evaluation_packet",
)

FAILED_NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_ARTIFACT_TYPES = (
    "failed_reader_state_evaluation_diagnostic",
    "failed_reader_state_evaluation_gate_report",
    "nonlocal_law_selected_target_reader_state_failed_evaluation_packet",
)

REQUIRED_RISK_PROBE_IDS = tuple(SELECTED_READER_STATE_REQUIRED_RISK_PROBES)


@dataclass(frozen=True)
class NonlocalLawSelectedTargetReaderStateEvaluationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class ExistingSelectedTargetReaderStateEvaluation:
    artifact: ArtifactRecord
    payload: dict[str, Any]
    packet_id: str
    client: str
    model_backed: bool
    provisional: bool
    usable_for_synthesis: bool


@dataclass(frozen=True)
class NonlocalLawSelectedTargetReaderStateSubject:
    run_id: str
    ablation_packet_dir: Path
    ablation_packet_id: str
    ablation_payloads: dict[str, dict[str, Any]]
    ablation_artifact_ids: dict[str, str]
    source_parent_ids: tuple[str, ...]
    source_candidate_packet_dir: Path
    candidate_text: str
    candidate_text_sha256: str
    candidate_word_count: int
    base_packet_dir: Path
    base_text: str
    base_text_sha256: str
    source_gate_reader_state_eval_authorized_alias_missing: bool
    normalized_reader_state_eval_authorized_from_readiness: bool


class FakeSelectedNonlocalLawCandidateReaderStateModelClient:
    provider = "fake"
    model = "fake-selected-nonlocal-law-reader-state-v1"

    def __init__(
        self,
        mode: str = "valid",
        *,
        provider: str = "fake",
        model: str = "fake-selected-nonlocal-law-reader-state-v1",
    ) -> None:
        self.mode = mode
        self.provider = provider
        self.model = model

    def generate(self, request: WorkerRequest) -> str:
        prompt = json.loads(request.input_text)
        payload = _valid_model_payload(prompt)
        if self.mode == "finality":
            payload["finality_claimed"] = True
        elif self.mode == "phase_shift":
            payload["phase_shift_claimed"] = True
        elif self.mode == "rival_defeat":
            payload["strongest_rival_defeated_claimed"] = True
        elif self.mode == "current_best_supersession":
            payload["current_best_supersession_claimed"] = True
        elif self.mode == "generation_recommended":
            payload["generation_recommended"] = True
        elif self.mode == "synthesis_authorized":
            payload["synthesis_authorized"] = True
        elif self.mode == "missing_risk":
            missing_id = REQUIRED_RISK_PROBE_IDS[-1]
            payload["risk_probe_results_by_id"].pop(missing_id, None)
            payload["risk_probe_results"] = [
                risk
                for risk in payload["risk_probe_results"]
                if risk["risk_id"] != missing_id
            ]
        elif self.mode == "invalid_json":
            return "{not valid json"
        return _canonical_json(payload)


def run_nonlocal_law_selected_target_reader_state_evaluation(
    config: AbiConfig,
    *,
    client_name: str,
    ablation_packet: Path | str,
    operator_reviewed: bool = False,
    allow_live_model: bool = False,
    max_model_calls: int = (
        NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_MAX_MODEL_CALLS_DEFAULT
    ),
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> NonlocalLawSelectedTargetReaderStateEvaluationResult:
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name not in NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Unsupported selected nonlocal law reader-state client: "
                f"{client_name}"
            ),
        )
    if not operator_reviewed:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            ablation_packet=ablation_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                "pass --operator-reviewed after reviewing the ablation packet."
            ),
        )
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            ablation_packet=ablation_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                "max-model-calls must be non-negative."
            ),
        )
    if client_name == "openai" and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                "pass --allow-live-model to opt in explicitly."
            ),
        )
    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == "openai" and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                f"{OPENAI_API_KEY_ENV} is not set."
            ),
        )
    if (
        client_name == "openai"
        and max_model_calls < NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_REQUIRED_MODEL_CALLS
    ):
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                f"max-model-calls {max_model_calls} is below required budget 1."
            ),
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, ablation_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            ablation_packet=resolved_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                f"ablation packet directory not found: {resolved_packet}"
            ),
        )

    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, config, resolved_packet)
            superseded_evaluation = _validate_subject_before_evaluation(
                connection,
                subject,
                client_name=client_name,
            )
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=configured_model if client_name == "openai" else None,
                    ablation_packet=resolved_packet,
                    message=(
                        "Selected nonlocal law candidate reader-state evaluation "
                        f"refused; run is not registered: {subject.run_id}"
                    ),
                )
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_EVALUATION_ACTIVE_PHASE,
            )
    except (
        KeyError,
        TypeError,
        ValueError,
        FileNotFoundError,
        json.JSONDecodeError,
    ) as error:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            ablation_packet=resolved_packet,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                f"{error}"
            ),
        )

    packet_dir = create_packet_dir(
        config.run_dir(subject.run_id)
        / "nonlocal_law_selected_target_reader_state_evaluation"
    )
    model_results: list[ModelDriverResult] = []
    if client_name == "openai":
        factory = client_factory or _default_openai_client_factory
        model_result = _run_live_reader_state_model(
            config=config,
            subject=subject,
            packet_dir=packet_dir,
            model_client=factory(configured_model),
        )
        model_results.append(model_result)
        if not model_result.accepted or model_result.parsed_payload is None:
            return _failed_evaluation_result(
                config=config,
                subject=subject,
                client_name=client_name,
                model=configured_model,
                model_results=model_results,
                message=_model_failure_message(model_result),
            )
        model_payload = model_result.parsed_payload
    else:
        model_payload = _valid_model_payload(_prompt_packet(subject))
        model_payload["fixture_only"] = True

    try:
        _validate_model_payload_for_subject(subject, model_payload)
    except ModelValidationError as error:
        if client_name == "openai":
            return _failed_evaluation_result(
                config=config,
                subject=subject,
                client_name=client_name,
                model=configured_model,
                model_results=model_results,
                message=(
                    "Selected nonlocal law candidate reader-state evaluation refused; "
                    f"{error}"
                ),
            )
        return _model_failure_result(
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            ablation_packet=resolved_packet,
            model_results=model_results,
            message=(
                "Selected nonlocal law candidate reader-state evaluation refused; "
                f"{error}"
            ),
        )

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CREATED_BY,
            fixture_only=client_name == "fake",
            model_call_id=None,
        )
        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_LINEAGE_ID,
                created_by=f"model_driver:openai:{configured_model}",
                fixture_only=False,
                model_call_id=model_results[-1].model_call.id,
            )
            if model_results
            else None
        )
        payloads, artifacts = _write_evaluation_artifacts(
            writer=writer,
            model_writer=model_writer,
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_payload=model_payload,
            model_results=model_results,
            superseded_evaluation=superseded_evaluation,
        )
        if model_results:
            linked_call = link_model_call_parsed_artifact(
                connection,
                model_call_id=model_results[-1].model_call.id,
                parsed_output_artifact_id=artifacts[
                    "living_event_sequence_reader_state_report"
                ].id,
            )
            model_results[-1] = ModelDriverResult(
                model_call=linked_call,
                parsed_payload=model_results[-1].parsed_payload,
                parsed_artifact=artifacts["living_event_sequence_reader_state_report"],
            )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_reader_state_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["selected_target_reader_state_gate_report"][
                    "unresolved_blockers"
                ]
            ),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_LINEAGE_ID,
        )

    return NonlocalLawSelectedTargetReaderStateEvaluationResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=packet_dir,
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
    ablation_packet_dir: Path,
) -> NonlocalLawSelectedTargetReaderStateSubject:
    _envelopes, ablation_payloads = _load_required_payloads(
        ablation_packet_dir,
        NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES,
        "selected-target ablation packet",
    )
    packet = ablation_payloads["nonlocal_law_selected_target_candidate_ablation_packet"]
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("ablation packet missing run_id")

    ablation_artifact_ids = {
        artifact_type: artifact.id
        for artifact_type in NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ABLATION_ARTIFACT_TYPES
        if (
            artifact := _artifact_for_path(
                connection,
                ablation_packet_dir / f"{artifact_type}.json",
            )
        )
        is not None
    }
    candidate_dir = _resolve_source_candidate_dir(config, packet, run_id)
    candidate_payload = _load_payload(
        candidate_dir / "generated_candidate_text.json",
        "source selected-target candidate generated text",
    )
    candidate_text = candidate_payload.get("text")
    if not isinstance(candidate_text, str) or not candidate_text.strip():
        raise ValueError("source candidate generated_candidate_text.payload.text missing")
    candidate_sha = sha256_text(candidate_text)
    if candidate_payload.get("text_sha256") != candidate_sha:
        raise ValueError("source candidate generated text hash mismatch")
    if packet.get("candidate_text_sha256") != candidate_sha:
        raise ValueError("candidate_text_sha256 mismatch")

    base_id = str(packet.get("source_base_candidate_packet_id") or "")
    base_dir = config.run_dir(run_id) / "nonlocal_law_guided_candidate" / base_id
    base_payload = _load_payload(
        base_dir / "generated_candidate_text.json",
        "base packet_0002 generated text",
    )
    base_text = base_payload.get("text")
    if not isinstance(base_text, str) or not base_text.strip():
        raise ValueError("base packet_0002 generated_candidate_text.payload.text missing")
    base_sha = sha256_text(base_text)
    if packet.get("base_text_sha256") != base_sha:
        raise ValueError("base_text_sha256 mismatch")

    gate = ablation_payloads["selected_target_candidate_ablation_gate_report"]
    readiness = ablation_payloads["reader_state_eval_readiness_report"]
    alias_missing = gate.get("reader_state_eval_authorized") is None
    normalized_reader_state_eval_authorized = bool(
        readiness.get("reader_state_evaluation_authorized") is True
    )
    parent_ids = _unique(
        [
            *ablation_artifact_ids.values(),
            *[
                str(value)
                for value in dict(packet.get("artifact_ids") or {}).values()
                if value
            ],
            _artifact_id_for_path(connection, candidate_dir / "generated_candidate_text.json"),
            _artifact_id_for_path(connection, base_dir / "generated_candidate_text.json"),
        ]
    )
    return NonlocalLawSelectedTargetReaderStateSubject(
        run_id=run_id,
        ablation_packet_dir=ablation_packet_dir,
        ablation_packet_id=str(packet.get("packet_id") or ablation_packet_dir.name),
        ablation_payloads=ablation_payloads,
        ablation_artifact_ids=ablation_artifact_ids,
        source_parent_ids=tuple(parent_ids),
        source_candidate_packet_dir=candidate_dir,
        candidate_text=candidate_text,
        candidate_text_sha256=candidate_sha,
        candidate_word_count=len(candidate_text.split()),
        base_packet_dir=base_dir,
        base_text=base_text,
        base_text_sha256=base_sha,
        source_gate_reader_state_eval_authorized_alias_missing=alias_missing,
        normalized_reader_state_eval_authorized_from_readiness=(
            normalized_reader_state_eval_authorized
        ),
    )


def _validate_subject_before_evaluation(
    connection: sqlite3.Connection,
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    *,
    client_name: str,
) -> ExistingSelectedTargetReaderStateEvaluation | None:
    packet = subject.ablation_payloads["nonlocal_law_selected_target_candidate_ablation_packet"]
    readiness = subject.ablation_payloads["reader_state_eval_readiness_report"]
    health = subject.ablation_payloads["project_health_scope_guard_report"]
    _require_bool(packet, "accepted", True)
    _require_bool(packet, "ablation_executed", True)
    _require_bool(packet, "candidate_generated", False)
    _require_equal(packet, "model_calls", 0)
    _require_equal(packet, "source_candidate_packet_id", "packet_0001")
    _require_equal(packet, "source_authorization_packet_id", "packet_0002")
    _require_equal(packet, "source_work_order_packet_id", "packet_0002")
    _require_equal(packet, "source_target_selection_packet_id", "packet_0002")
    _require_equal(packet, "source_consolidation_packet_id", "packet_0002")
    _require_equal(
        packet,
        "source_base_candidate_packet_id",
        EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    )
    _require_equal(
        packet,
        "prior_current_best_candidate_packet_id",
        EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(packet, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(packet, "selected_risk_id", SELECTED_RISK_ID)
    _require_bool(packet, "ready_for_reader_state_evaluation", True)
    _require_bool(readiness, "ready_for_reader_state_evaluation", True)
    _require_bool(readiness, "reader_state_evaluation_authorized", False)
    _require_bool(
        readiness,
        "reader_state_evaluation_requires_separate_command",
        True,
    )
    if (
        subject.source_gate_reader_state_eval_authorized_alias_missing
        and subject.normalized_reader_state_eval_authorized_from_readiness
    ):
        raise ValueError("reader-state authorization alias cannot be normalized")
    if packet.get("candidate_text_sha256") != subject.candidate_text_sha256:
        raise ValueError("candidate_text_sha256 mismatch")
    if packet.get("base_text_sha256") != subject.base_text_sha256:
        raise ValueError("base_text_sha256 mismatch")
    missing_controls = [
        control for control in ABLATION_CONTROL_IDS if control not in _control_ids(subject)
    ]
    if missing_controls:
        raise ValueError("ablation controls missing: " + ", ".join(missing_controls))
    if not _law_bearing_choices(subject):
        raise ValueError("law-bearing choices missing")
    if len(_risks_to_test(subject)) < len(RISKS_TO_TEST):
        raise ValueError("risks_to_test missing")
    if packet.get("source_chain_coherent") is not True and health.get("source_chain_coherent") is not True:
        raise ValueError("source_chain_coherent must be true")
    if _payload_has_final_or_phase_claim(subject.ablation_payloads):
        raise ValueError(
            "ablation packet carries finality, phase-shift, rival-defeat, or current-best claim"
        )

    existing = _accepted_reader_state_for_ablation(connection, subject)
    if client_name == "fake" and existing:
        raise ValueError("accepted reader-state evaluation packet already exists")
    live_existing = [evaluation for evaluation in existing if evaluation.model_backed]
    if client_name == "openai" and live_existing:
        raise ValueError("model-backed reader-state evaluation packet already exists")
    fake_existing = [
        evaluation for evaluation in existing if evaluation.provisional and not evaluation.model_backed
    ]
    return fake_existing[-1] if client_name == "openai" and fake_existing else None


def _run_live_reader_state_model(
    *,
    config: AbiConfig,
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    packet_dir: Path,
    model_client: ModelClient,
) -> ModelDriverResult:
    return ModelDriver(config=config, client=model_client).run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=(
                WorkerRole.SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATOR
            ),
            prompt_contract_id=PROMPT_CONTRACT_ID,
            schema=SELECTED_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA,
            input_text=_canonical_json(_prompt_packet(subject)),
            input_artifact_ids=list(subject.source_parent_ids),
            input_packet_path=str(subject.ablation_packet_dir),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_LINEAGE_ID,
            parent_ids=list(subject.source_parent_ids),
            fixture_only=False,
            output_dir=str(packet_dir),
            register_parsed_artifact=False,
        )
    )


def _prompt_packet(subject: NonlocalLawSelectedTargetReaderStateSubject) -> dict[str, object]:
    return {
        "task": "evaluate selected nonlocal law candidate reader-state effect",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": "SelectedNonlocalLawCandidateReaderStateEvaluationOutput@1",
        "central_question": (
            "Does packet_0001 make object traces feel like active conditions for "
            "later perception, or does it merely explain that object traces are "
            "active conditions?"
        ),
        "source_ablation_packet_id": subject.ablation_packet_id,
        "source_candidate_packet_id": "packet_0001",
        "source_base_candidate_packet_id": "packet_0002",
        "prior_current_best_candidate_packet_id": "packet_0063",
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_text": subject.candidate_text,
        "base_text_sha256": subject.base_text_sha256,
        "base_packet_0002_text": subject.base_text,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "law_bearing_choices": list(_law_bearing_choices(subject)),
        "risks_to_test": list(_risks_to_test(subject)),
        "required_risk_probe_ids": list(REQUIRED_RISK_PROBE_IDS),
        "required_risk_probe_labels_by_id": dict(
            SELECTED_READER_STATE_REQUIRED_RISK_PROBES
        ),
        "risk_probe_output_contract": {
            "field": "risk_probe_results_by_id",
            "required_ids": list(REQUIRED_RISK_PROBE_IDS),
            "missing_any_required_probe_invalidates_model_call": True,
            "do_not_omit_inactive_probes": True,
            "do_not_paraphrase_or_merge_probe_ids": True,
        },
        "reader_state_focus": [
            "do object traces become active conditions?",
            "does sequence feel live rather than retrospective?",
            "do causal bridges change the reader's order of seeing?",
            "does consequence arrive before naming?",
            "does the causal mechanism become overexplained?",
            "does explanation remain earned?",
            "does packet_0002's field remain preserved?",
            "does it avoid rival imitation?",
            "does strongest-rival pressure remain active?",
        ],
        "model_must_not": [
            "generate or rewrite text",
            "authorize synthesis",
            "update current best",
            "claim strongest-rival defeat",
            "claim finality or phase shift",
            "universalize the local law",
        ],
    }


def _validate_model_payload_for_subject(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    payload: dict[str, object],
) -> None:
    for field in (
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
        "current_best_supersession_claimed",
        "generation_recommended",
        "immediate_finalization_recommended",
        "synthesis_authorized",
        "current_best_updated",
    ):
        if payload.get(field) is not False:
            raise ModelValidationError(f"{field} must be false")
    if payload.get("strongest_rival_remains_blocking") is not True:
        raise ModelValidationError("strongest_rival_remains_blocking must be true")
    if payload.get("rival_imitation_detected") is not False:
        raise ModelValidationError("rival_imitation_detected must be false")
    if payload.get("forbidden_rival_hits") not in ([], None):
        raise ModelValidationError("forbidden_rival_hits must be empty")
    risk_probe_results_by_id = payload.get("risk_probe_results_by_id")
    if not isinstance(risk_probe_results_by_id, dict):
        raise ModelValidationError("risk_probe_results_by_id is required")
    missing_risk_ids = [
        risk_id for risk_id in REQUIRED_RISK_PROBE_IDS if risk_id not in risk_probe_results_by_id
    ]
    if missing_risk_ids:
        raise ModelValidationError(
            "model output missing risk probes: " + ", ".join(missing_risk_ids)
        )
    _ = subject


def _write_evaluation_artifacts(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingSelectedTargetReaderStateEvaluation | None,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="source_ablation_intake_summary",
        payload=_build_source_intake(subject, packet_dir),
        parent_ids=_source_parent_ids(subject, superseded_evaluation),
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_candidate_reader_state_subject",
        payload=_build_candidate_subject(subject),
        parent_ids=[artifacts["source_ablation_intake_summary"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="base_packet_0002_reader_state_control_subject",
        payload=_build_base_subject(subject),
        parent_ids=[artifacts["selected_target_candidate_reader_state_subject"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_ablation_reader_state_matrix",
        payload=_build_matrix(subject, model_payload),
        parent_ids=[artifacts["base_packet_0002_reader_state_control_subject"].id],
    )

    model_artifact_payloads = {
        "living_event_sequence_reader_state_report": _build_living_event_report(
            subject,
            model_payload,
        ),
        "static_trace_reduction_reader_state_report": _build_static_trace_report(
            subject,
            model_payload,
        ),
        "causal_bridge_reader_state_report": _build_causal_bridge_report(
            subject,
            model_payload,
        ),
        "consequence_before_naming_reader_state_report": _build_consequence_report(
            subject,
            model_payload,
        ),
        "causal_mechanism_overexplained_probe_report": _build_overexplained_report(
            subject,
            model_payload,
        ),
        "explanation_earned_preservation_report": _build_explanation_report(
            subject,
            model_payload,
        ),
        "packet_0002_gains_preservation_report": _build_packet_0002_gains_report(
            subject,
            model_payload,
        ),
        "non_imitation_reader_state_report": _build_non_imitation_report(
            subject,
            model_payload,
        ),
        "strongest_rival_pressure_status_report": _build_strongest_rival_report(
            subject,
            model_payload,
        ),
        "selected_target_risk_probe_report": _build_risk_probe_report(
            subject,
            model_payload,
        ),
    }
    parent_id = artifacts["selected_target_ablation_reader_state_matrix"].id
    for artifact_type, payload in model_artifact_payloads.items():
        payloads[artifact_type] = payload
        artifacts[artifact_type] = _write_artifact(
            writer=writer,
            model_writer=model_writer,
            artifact_type=artifact_type,
            payload=payload,
            parent_ids=[parent_id],
        )
        parent_id = artifacts[artifact_type].id

    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="synthesis_readiness_report",
        payload=_build_synthesis_readiness(
            subject,
            client_name,
            model_payload,
            model_results,
        ),
        parent_ids=[parent_id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="selected_target_reader_state_gate_report",
        payload=_build_gate_report(subject, client_name, model_results),
        parent_ids=[artifacts["synthesis_readiness_report"].id],
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="project_health_scope_guard_report",
        payload=_build_health_report(subject, client_name, model_results),
        parent_ids=[artifacts["selected_target_reader_state_gate_report"].id],
    )
    payloads["nonlocal_law_selected_target_reader_state_evaluation_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=model,
            model_payload=model_payload,
            model_results=model_results,
            payloads=payloads,
            artifacts=artifacts,
            superseded_evaluation=superseded_evaluation,
        )
    )
    artifacts["nonlocal_law_selected_target_reader_state_evaluation_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_reader_state_evaluation_packet",
            payloads["nonlocal_law_selected_target_reader_state_evaluation_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type
                != "nonlocal_law_selected_target_reader_state_evaluation_packet"
            ],
        )
    )
    return payloads, artifacts


def _build_source_intake(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    packet_dir: Path,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "candidate_text_sha256": subject.candidate_text_sha256,
        "base_text_sha256": subject.base_text_sha256,
        "candidate_text_extracted_from": "generated_candidate_text.payload.text",
        "ablation_controls_consumed": list(ABLATION_CONTROL_IDS),
        "law_bearing_choices_consumed": list(_law_bearing_choices(subject)),
        "risks_to_test_consumed": list(_risks_to_test(subject)),
        "source_gate_reader_state_eval_authorized_alias_missing": (
            subject.source_gate_reader_state_eval_authorized_alias_missing
        ),
        "normalized_reader_state_eval_authorized_from_readiness": (
            subject.normalized_reader_state_eval_authorized_from_readiness
        ),
        "source_ablation_ready_for_reader_state": True,
        **_evaluation_safety_fields(model_calls=0),
        "worker": "source_ablation_intake_summary_v1_controller",
    }


def _build_candidate_subject(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "candidate_text": subject.candidate_text,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "reader_state_subject": True,
        **_evaluation_safety_fields(model_calls=0),
        "worker": "selected_target_candidate_reader_state_subject_v1_controller",
    }


def _build_base_subject(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "base_packet_id": "packet_0002",
        "base_packet_0002_text": subject.base_text,
        "base_text_sha256": subject.base_text_sha256,
        "control_subject": True,
        **_evaluation_safety_fields(model_calls=0),
        "worker": "base_packet_0002_reader_state_control_subject_v1_controller",
    }


def _build_matrix(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "central_question": (
            "Does packet_0001 make object traces feel like active conditions for "
            "later perception, or does it merely explain that object traces are "
            "active conditions?"
        ),
        "ablation_controls": [
            {"control_id": control_id, "reader_state_result_claimed": False}
            for control_id in ABLATION_CONTROL_IDS
        ],
        "ablation_control_count": len(ABLATION_CONTROL_IDS),
        "overall_selected_target_reader_state_result": model_payload[
            "overall_selected_target_reader_state_result"
        ],
        **_evaluation_safety_fields(model_calls=0),
        "worker": "selected_target_ablation_reader_state_matrix_v1_controller",
    }


def _build_living_event_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["living_event_sequence_result"],
        "summary": model_payload["living_event_sequence_summary"],
        "evidence_from_candidate": model_payload["living_event_sequence_evidence"],
        "ablation_control_basis": [
            "full_selected_target_intervention",
            "remove_living_event_sequence_repair",
            "restore_static_retrospective_trace",
        ],
        "reader_state_question": "do object traces become active conditions?",
        "not_final_evidence": True,
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "living_event_sequence_reader_state_report_v1_controller",
    }


def _build_static_trace_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["static_trace_reduction_result"],
        "summary": model_payload["static_trace_reduction_summary"],
        "evidence": model_payload["static_trace_reduction_evidence"],
        "comparison_to_packet_0002": model_payload[
            "static_trace_comparison_to_packet_0002"
        ],
        "remaining_static_trace_risk": model_payload["remaining_static_trace_risk"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "static_trace_reduction_reader_state_report_v1_controller",
    }


def _build_causal_bridge_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["causal_bridge_result"],
        "summary": model_payload["causal_bridge_summary"],
        "bridge_examples": model_payload["bridge_examples"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "causal_bridge_reader_state_report_v1_controller",
    }


def _build_consequence_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["consequence_before_naming_result"],
        "summary": model_payload["consequence_before_naming_summary"],
        "before_naming_evidence": model_payload["before_naming_evidence"],
        "explanation_entry_point": model_payload["explanation_entry_point"],
        "risk_if_overstated": model_payload["risk_if_overstated"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "consequence_before_naming_reader_state_report_v1_controller",
    }


def _build_overexplained_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["causal_mechanism_overexplained_result"],
        "summary": model_payload["causal_mechanism_overexplained_summary"],
        "overexplained_phrases": list(model_payload["overexplained_phrases"]),
        "risk_status": model_payload["risk_status"],
        "next_target_implication": model_payload["next_target_implication"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "causal_mechanism_overexplained_probe_report_v1_controller",
    }


def _build_explanation_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["explanation_earned_result"],
        "explanation_earned": model_payload["explanation_earned"],
        "explanation_abolished": False,
        "explanation_timing_summary": model_payload["explanation_earned_summary"],
        "remaining_explicitness_risk": model_payload["remaining_explicitness_risk"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "explanation_earned_preservation_report_v1_controller",
    }


def _build_packet_0002_gains_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["packet_0002_gains_preserved_result"],
        "preserved_strengths": list(model_payload["preserved_strengths"]),
        "weakened_strengths": list(model_payload["weakened_strengths"]),
        "object_field_preserved": model_payload["object_field_preserved"],
        "proof_no_answer_pressure_preserved": model_payload[
            "proof_no_answer_pressure_preserved"
        ],
        "return_structure_preserved": model_payload["return_structure_preserved"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "packet_0002_gains_preservation_report_v1_controller",
    }


def _build_non_imitation_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "result": model_payload["non_imitation_result"],
        "rival_imitation_detected": False,
        "forbidden_rival_hits": [],
        "forbidden_rival_mode_hits": [],
        "non_imitation_evidence": model_payload["non_imitation_evidence"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "non_imitation_reader_state_report_v1_controller",
    }


def _build_strongest_rival_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "strongest_rival_pressure_result": model_payload[
            "strongest_rival_pressure_result"
        ],
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "pressure_summary": model_payload["pressure_summary"],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "strongest_rival_pressure_status_report_v1_controller",
    }


def _build_risk_probe_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    risk_probe_results = _risk_probe_results(model_payload)
    risk_probe_results_by_id = _risk_probe_results_by_id(model_payload)
    return {
        **_source_fields(subject),
        "risk_probe_count": len(risk_probe_results),
        "risk_probe_results": risk_probe_results,
        "risk_probe_results_by_id": risk_probe_results_by_id,
        "all_required_risk_probes_present": True,
        "missing_risk_probe_ids": [],
        "missing_risk_probe_labels": [],
        **_evaluation_safety_fields(model_calls=_model_call_count(model_payload)),
        "worker": "selected_target_risk_probe_report_v1_controller",
    }


def _build_synthesis_readiness(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    client_name: str,
    model_payload: dict[str, object],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    model_backed = client_name == "openai" and bool(model_results)
    return {
        **_source_fields(subject),
        "ready_for_synthesis": model_backed,
        "usable_for_synthesis": model_backed,
        "synthesis_authorized": False,
        "synthesis_requires_separate_command": True,
        "current_best_updated": False,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "synthesis_recommendation": model_payload["synthesis_recommendation"],
        **_reader_state_mode_fields(client_name, model_results, None),
        **_evaluation_safety_fields(model_calls=len(model_results)),
        "worker": "synthesis_readiness_report_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    client_name: str,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    model_backed = client_name == "openai" and bool(model_results)
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_ablation_accepted", True),
        _gate_result("source_ablation_ready_for_reader_state", True),
        _gate_result("candidate_text_loaded_from_payload_text", True),
        _gate_result("base_packet_0002_control_loaded", True),
        _gate_result("reader_state_evaluation_executed", True),
        _gate_result("model_backed", model_backed, record=model_backed),
        _gate_result("usable_for_synthesis", model_backed, record=model_backed),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_current_best_updated", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result("no_strongest_rival_defeat_claim", True),
        _gate_result(
            "synthesis_authorized",
            False,
            ["synthesis requires a separate command"],
            record=False,
        ),
        _gate_result(
            "current_best_updated",
            False,
            ["reader-state evaluation does not update current best"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_pressure_resolved",
            False,
            ["strongest rival pressure remains blocking"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["reader-state evaluation is not finalization evidence"],
            record=False,
        ),
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "unresolved_blockers": [
            "synthesis is not authorized by reader-state evaluation",
            "current best is not updated",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        "missing_gates": [],
        "final_gates_marked_passed": [],
        **_evaluation_safety_fields(model_calls=len(model_results)),
        "worker": "selected_target_reader_state_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    client_name: str,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    checks = [
        _check("source_ablation_accepted", True),
        _check("candidate_text_loaded_from_payload_text", True),
        _check("base_packet_0002_control_loaded", True),
        _check("no_generation_authorized", True),
        _check("no_candidate_generated", True),
        _check("no_current_best_updated", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
    ]
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "source_chain_coherent": True,
        **_reader_state_mode_fields(client_name, model_results, None),
        **_evaluation_safety_fields(model_calls=len(model_results)),
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    model_results: list[ModelDriverResult],
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    superseded_evaluation: ExistingSelectedTargetReaderStateEvaluation | None,
) -> dict[str, object]:
    model_backed = client_name == "openai" and bool(model_results)
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_reader_state_evaluation_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "model": model,
        **_source_fields(subject),
        "candidate_text_sha256": subject.candidate_text_sha256,
        "base_text_sha256": subject.base_text_sha256,
        "reader_state_evaluation_executed": True,
        "living_event_sequence_result": model_payload["living_event_sequence_result"],
        "static_trace_reduction_result": model_payload["static_trace_reduction_result"],
        "causal_bridge_result": model_payload["causal_bridge_result"],
        "consequence_before_naming_result": model_payload[
            "consequence_before_naming_result"
        ],
        "causal_mechanism_overexplained_result": model_payload[
            "causal_mechanism_overexplained_result"
        ],
        "explanation_earned_result": model_payload["explanation_earned_result"],
        "packet_0002_gains_preserved_result": model_payload[
            "packet_0002_gains_preserved_result"
        ],
        "non_imitation_result": model_payload["non_imitation_result"],
        "strongest_rival_pressure_result": model_payload[
            "strongest_rival_pressure_result"
        ],
        "overall_selected_target_reader_state_result": model_payload[
            "overall_selected_target_reader_state_result"
        ],
        "reader_state_summary": model_payload["reader_state_summary"],
        "risk_probe_count": len(_risk_probe_results(model_payload)),
        "risk_probe_results": _risk_probe_results(model_payload),
        "risk_probe_results_by_id": _risk_probe_results_by_id(model_payload),
        "all_required_risk_probes_present": True,
        "missing_risk_probe_ids": [],
        "missing_risk_probe_labels": [],
        "ready_for_synthesis": model_backed,
        "synthesis_authorized": False,
        "current_best_updated": False,
        **_reader_state_mode_fields(
            client_name,
            model_results,
            superseded_evaluation,
        ),
        "counts": {**counts, "model_calls": len(model_results)},
        "model_calls": len(model_results),
        "model_call_ids": [result.model_call.id for result in model_results],
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_reader_state_evaluation_packet",
        ],
        "gate_report": payloads["selected_target_reader_state_gate_report"],
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        **_evaluation_safety_fields(model_calls=len(model_results)),
        "worker": "nonlocal_law_selected_target_reader_state_evaluation_packet_v1_controller",
    }


def _source_fields(subject: NonlocalLawSelectedTargetReaderStateSubject) -> dict[str, object]:
    packet = subject.ablation_payloads["nonlocal_law_selected_target_candidate_ablation_packet"]
    return {
        "source_ablation_packet_id": subject.ablation_packet_id,
        "source_ablation_packet_dir": str(subject.ablation_packet_dir),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_target_selection_packet_id": packet.get("source_target_selection_packet_id"),
        "source_consolidation_packet_id": packet.get("source_consolidation_packet_id"),
        "source_loop_review_packet_id": packet.get("source_loop_review_packet_id"),
        "source_reader_state_packet_id": packet.get("source_reader_state_packet_id"),
        "source_synthesis_packet_id": packet.get("source_synthesis_packet_id"),
        "source_base_candidate_packet_id": packet.get("source_base_candidate_packet_id"),
        "prior_current_best_candidate_packet_id": packet.get(
            "prior_current_best_candidate_packet_id"
        ),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_reader_state_evaluation_packet"]
    return {
        **packet,
        "model_call_ids": [result.model_call.id for result in model_results],
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _risk_probe_results(model_payload: dict[str, object]) -> list[dict[str, object]]:
    results = model_payload.get("risk_probe_results")
    if isinstance(results, list):
        return [dict(result) for result in results if isinstance(result, dict)]
    by_id = _risk_probe_results_by_id(model_payload)
    return [
        {
            "risk_id": risk_id,
            "risk_label": SELECTED_READER_STATE_REQUIRED_RISK_PROBES[risk_id],
            **by_id[risk_id],
        }
        for risk_id in REQUIRED_RISK_PROBE_IDS
    ]


def _risk_probe_results_by_id(
    model_payload: dict[str, object],
) -> dict[str, dict[str, object]]:
    results = model_payload.get("risk_probe_results_by_id")
    if not isinstance(results, dict):
        return {}
    return {
        risk_id: dict(results[risk_id])
        for risk_id in REQUIRED_RISK_PROBE_IDS
        if isinstance(results.get(risk_id), dict)
    }


def _valid_model_payload(prompt: dict[str, object]) -> dict[str, object]:
    risk_probe_results_by_id = {
        risk_id: {
            "result": (
                "active_risk"
                if risk_id == "causal_mechanism_overexplained"
                else "requires_synthesis"
            ),
            "summary": (
                f"{risk_label} remains an evaluation risk, not a final result."
            ),
            "evidence": (
                "The selected-target candidate is reviewable but requires synthesis."
            ),
            "risk_status": (
                "active_risk"
                if risk_id == "causal_mechanism_overexplained"
                else "requires_synthesis"
            ),
            "next_target_implication": (
                "Carry this probe into synthesis before changing current-best state."
            ),
        }
        for risk_id, risk_label in SELECTED_READER_STATE_REQUIRED_RISK_PROBES.items()
    }
    risk_probe_results = [
        {
            "risk_id": risk_id,
            "risk_label": SELECTED_READER_STATE_REQUIRED_RISK_PROBES[risk_id],
            **risk_probe_results_by_id[risk_id],
        }
        for risk_id in REQUIRED_RISK_PROBE_IDS
    ]
    return {
        "living_event_sequence_result": "improved",
        "living_event_sequence_summary": (
            "Object traces more often function as active conditions before explanation."
        ),
        "living_event_sequence_evidence": (
            "Ring, dust, spoon, saucer crack, hum, and light change the order of seeing."
        ),
        "static_trace_reduction_result": "improved",
        "static_trace_reduction_summary": (
            "The candidate reduces finished-evidence trace behavior but does not remove the risk."
        ),
        "static_trace_reduction_evidence": (
            "Objects act on later perception instead of only reporting what happened."
        ),
        "static_trace_comparison_to_packet_0002": (
            "Compared with packet_0002, sequence pressure is more locally active."
        ),
        "remaining_static_trace_risk": "Some explanatory naming may still freeze the trace.",
        "causal_bridge_result": "improved",
        "causal_bridge_summary": "Local bridges are visible across the object field.",
        "bridge_examples": {
            "ring_grain": "The ring changes how grain is crossed by the next glance.",
            "dust_bare_strip": "Dust and bare strip redirect the eye path.",
            "spoon_saucer_crack": "The spoon tick makes the saucer fracture newly present.",
            "hum_order_of_seeing": "The hum changes the order in which the room is seen.",
        },
        "consequence_before_naming_result": "preserved",
        "consequence_before_naming_summary": (
            "Consequences generally arrive before naming, though the naming remains explicit."
        ),
        "before_naming_evidence": "Object relations precede the room's instructive claim.",
        "explanation_entry_point": "Explanation enters after the object-event sequence.",
        "risk_if_overstated": "The repair may name its own mechanism too directly.",
        "causal_mechanism_overexplained_result": "active_risk",
        "causal_mechanism_overexplained_summary": (
            "The candidate may still overexplain how perception is changed."
        ),
        "overexplained_phrases": list(EXPECTED_OVEREXPLAINED_PHRASES),
        "risk_status": "active_risk",
        "next_target_implication": (
            "Future evidence should test whether mechanism can stay enacted rather than named."
        ),
        "explanation_earned_result": "mixed",
        "explanation_earned": "mixed",
        "explanation_earned_summary": (
            "Explanation remains delayed but sometimes declares the law."
        ),
        "explanation_abolished": False,
        "remaining_explicitness_risk": "Explicit causal naming remains a live risk.",
        "packet_0002_gains_preserved_result": "preserved",
        "preserved_strengths": [
            "table/ring/dust/spoon/saucer/light field",
            "proof/no-answer pressure",
            "return-through-same-materials structure",
        ],
        "weakened_strengths": ["object-field delicacy may be overloaded"],
        "object_field_preserved": True,
        "proof_no_answer_pressure_preserved": True,
        "return_structure_preserved": True,
        "non_imitation_result": "preserved",
        "rival_imitation_detected": False,
        "forbidden_rival_hits": [],
        "forbidden_rival_mode_hits": [],
        "non_imitation_evidence": "No rival object sequence, scene, cadence, or plot is imported.",
        "strongest_rival_pressure_result": "narrowed_but_blocking",
        "strongest_rival_remains_blocking": True,
        "strongest_rival_defeated_claimed": False,
        "pressure_summary": (
            "The selected target narrows one gap, but strongest-rival pressure remains blocking."
        ),
        "overall_selected_target_reader_state_result": "requires_synthesis",
        "reader_state_summary": (
            "The selected-target candidate is promising reader-state evidence, not a proof."
        ),
        "risk_probe_results": risk_probe_results,
        "risk_probe_results_by_id": risk_probe_results_by_id,
        "synthesis_recommendation": (
            "Run selected nonlocal law candidate evidence synthesis after live evaluation."
        ),
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "current_best_supersession_claimed": False,
        "generation_recommended": False,
        "immediate_finalization_recommended": False,
        "synthesis_authorized": False,
        "current_best_updated": False,
    }


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


def _load_payload(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"{label} not found")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact is malformed")
    return payload


def _resolve_source_candidate_dir(
    config: AbiConfig,
    packet: dict[str, Any],
    run_id: str,
) -> Path:
    source_dir = packet.get("source_candidate_packet_dir")
    if isinstance(source_dir, str) and source_dir.strip():
        path = Path(source_dir)
        return path if path.is_absolute() else config.root / path
    source_id = str(packet.get("source_candidate_packet_id") or "")
    return config.run_dir(run_id) / "nonlocal_law_selected_target_candidate" / source_id


def _accepted_reader_state_for_ablation(
    connection: sqlite3.Connection,
    subject: NonlocalLawSelectedTargetReaderStateSubject,
) -> list[ExistingSelectedTargetReaderStateEvaluation]:
    evaluations: list[ExistingSelectedTargetReaderStateEvaluation] = []
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type != "nonlocal_law_selected_target_reader_state_evaluation_packet":
            continue
        payload = _artifact_payload(artifact)
        if payload.get("source_ablation_packet_id") != subject.ablation_packet_id:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("reader_state_evaluation_executed") is True
            and _accepted_evaluation_has_canonical_risk_surface(payload)
        ):
            evaluations.append(_classify_existing_reader_state_evaluation(artifact, payload))
    return evaluations


def _accepted_evaluation_has_canonical_risk_surface(payload: dict[str, Any]) -> bool:
    if payload.get("all_required_risk_probes_present") is not True:
        return False
    by_id = payload.get("risk_probe_results_by_id")
    return isinstance(by_id, dict) and set(by_id) == set(REQUIRED_RISK_PROBE_IDS)


def _classify_existing_reader_state_evaluation(
    artifact: ArtifactRecord,
    payload: dict[str, Any],
) -> ExistingSelectedTargetReaderStateEvaluation:
    client = str(payload.get("client") or "")
    model_calls = payload.get("model_calls")
    model_backed = bool(payload.get("model_backed") is True) or (
        client == "openai" and isinstance(model_calls, int) and model_calls > 0
    )
    provisional = bool(payload.get("provisional_reader_state_evaluation") is True) or (
        client == "fake" or not model_backed
    )
    usable_for_synthesis = (
        bool(payload.get("usable_for_synthesis") is True)
        and model_backed
        and not provisional
    )
    return ExistingSelectedTargetReaderStateEvaluation(
        artifact=artifact,
        payload=payload,
        packet_id=str(payload.get("packet_id") or Path(artifact.path).parent.name),
        client=client,
        model_backed=model_backed,
        provisional=provisional,
        usable_for_synthesis=usable_for_synthesis,
    )


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        return {}
    return envelope["payload"]


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


def _artifact_id_for_path(connection: sqlite3.Connection, path: Path) -> str | None:
    artifact = _artifact_for_path(connection, path)
    return artifact.id if artifact else None


def _control_ids(subject: NonlocalLawSelectedTargetReaderStateSubject) -> set[str]:
    packet = subject.ablation_payloads["nonlocal_law_selected_target_candidate_ablation_packet"]
    matrix = subject.ablation_payloads["selected_target_ablation_control_matrix"]
    controls = set(_string_list(packet.get("ablation_controls")))
    controls.update(_string_list(matrix.get("control_ids")))
    for row in _object_items(matrix.get("ablation_controls")):
        controls.add(str(row.get("control_id")))
    return controls


def _law_bearing_choices(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
) -> list[str]:
    payload = subject.ablation_payloads["law_bearing_choice_map"]
    choices = payload.get("law_bearing_choices") or payload.get("choices_to_test")
    if not isinstance(choices, list):
        return []
    return [str(choice) for choice in choices if str(choice)]


def _risks_to_test(subject: NonlocalLawSelectedTargetReaderStateSubject) -> list[str]:
    packet = subject.ablation_payloads["nonlocal_law_selected_target_candidate_ablation_packet"]
    law_map = subject.ablation_payloads["law_bearing_choice_map"]
    risks = packet.get("risks_to_test") or law_map.get("risks_to_test")
    if not isinstance(risks, list):
        return []
    return [str(risk) for risk in risks if str(risk)]


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finalization_eligible",
                "final_artifact",
                "final_claim",
                "current_best_updated",
                "candidate_superiority_claimed",
                "current_best_supersession_claimed",
            } and item is True:
                return True
            if key in {
                "phase_shift_claim",
                "phase_shift_claimed",
                "strongest_rival_defeated",
                "strongest_rival_defeated_claimed",
                "strongest_rival_defeat_claim",
            } and item is True:
                return True
            if key in {"no_final_claim", "no_phase_shift_claim"} and item is False:
                return True
            if _payload_has_final_or_phase_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_final_or_phase_claim(item) for item in value)
    return False


def _model_failure_result(
    *,
    client_name: str,
    model: str | None,
    ablation_packet: Path | str,
    model_results: list[ModelDriverResult],
    message: str,
) -> NonlocalLawSelectedTargetReaderStateEvaluationResult:
    return NonlocalLawSelectedTargetReaderStateEvaluationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "message": message,
            "ablation_packet": str(ablation_packet),
            "reader_state_evaluation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "model_calls": len(model_results),
            "model_call_ids": [result.model_call.id for result in model_results],
            "artifact_ids": {},
            "artifact_paths": {},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
        model_results=tuple(model_results),
    )


def _model_failure_message(result: ModelDriverResult) -> str:
    return (
        "Selected nonlocal law candidate reader-state evaluation refused; model "
        f"call {result.model_call.status}: "
        f"{result.model_call.error_message or 'no parsed output'}"
    )


def _failed_evaluation_result(
    *,
    config: AbiConfig,
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    message: str,
) -> NonlocalLawSelectedTargetReaderStateEvaluationResult:
    validation_report = _failed_validation_report(model_results, message)
    with connect(config.db_path) as connection:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_reader_state_failed_evaluation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )
        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        common = {
            "accepted": False,
            "refused": True,
            "message": message,
            "client": client_name,
            "model": model,
            **_source_fields(subject),
            **validation_report,
            "model_call_ids": [result.model_call.id for result in model_results],
            "reader_state_evaluation_executed": False,
            "usable_for_synthesis": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "model_calls": len(model_results),
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "current_best_supersession_claimed": False,
            "next_recommended_action": FAILED_NEXT_RECOMMENDED_ACTION,
        }
        payloads["failed_reader_state_evaluation_diagnostic"] = {
            **common,
            "worker": "failed_reader_state_evaluation_diagnostic_v1_controller",
        }
        artifacts["failed_reader_state_evaluation_diagnostic"] = writer.write_artifact(
            "failed_reader_state_evaluation_diagnostic",
            payloads["failed_reader_state_evaluation_diagnostic"],
            parent_ids=list(subject.source_parent_ids),
        )
        payloads["failed_reader_state_evaluation_gate_report"] = {
            **_source_fields(subject),
            **validation_report,
            "passed": False,
            "eligible": False,
            "reader_state_evaluation_executed": False,
            "usable_for_synthesis": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "model_calls": len(model_results),
            "unresolved_blockers": [message],
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "worker": "failed_reader_state_evaluation_gate_report_v1_controller",
        }
        artifacts["failed_reader_state_evaluation_gate_report"] = writer.write_artifact(
            "failed_reader_state_evaluation_gate_report",
            payloads["failed_reader_state_evaluation_gate_report"],
            parent_ids=[artifacts["failed_reader_state_evaluation_diagnostic"].id],
        )
        counts = packet_artifact_count_summary(
            required_artifact_types=(
                FAILED_NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_ARTIFACT_TYPES
            ),
            produced_artifact_types=list(artifacts),
            packet_artifact_type=(
                "nonlocal_law_selected_target_reader_state_failed_evaluation_packet"
            ),
        )
        payloads[
            "nonlocal_law_selected_target_reader_state_failed_evaluation_packet"
        ] = {
            **common,
            "packet_id": packet_dir.name,
            "packet_dir": str(packet_dir),
            "counts": {**counts, "model_calls": len(model_results)},
            "artifact_ids": {
                artifact_type: artifact.id
                for artifact_type, artifact in artifacts.items()
            },
            "worker": (
                "nonlocal_law_selected_target_reader_state_failed_evaluation_packet"
                "_v1_controller"
            ),
        }
        artifacts[
            "nonlocal_law_selected_target_reader_state_failed_evaluation_packet"
        ] = writer.write_artifact(
            "nonlocal_law_selected_target_reader_state_failed_evaluation_packet",
            payloads[
                "nonlocal_law_selected_target_reader_state_failed_evaluation_packet"
            ],
            parent_ids=[
                artifacts["failed_reader_state_evaluation_diagnostic"].id,
                artifacts["failed_reader_state_evaluation_gate_report"].id,
            ],
        )
    return NonlocalLawSelectedTargetReaderStateEvaluationResult(
        exit_code=1,
        payload={
            **payloads[
                "nonlocal_law_selected_target_reader_state_failed_evaluation_packet"
            ],
            "artifact_paths": {
                artifact_type: str(packet_dir / f"{artifact_type}.json")
                for artifact_type in artifacts
            },
            "validation_report": validation_report,
        },
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _failed_validation_report(
    model_results: list[ModelDriverResult],
    message: str,
) -> dict[str, object]:
    latest_result = model_results[-1] if model_results else None
    output_payload = (
        _model_output_payload_for_result(latest_result)
        if latest_result is not None
        else {}
    )
    missing_ids = _missing_risk_probe_ids(output_payload)
    validation_failures = [
        latest_result.model_call.error_message
        if latest_result is not None and latest_result.model_call.error_message
        else message
    ]
    model_call_status = latest_result.model_call.status if latest_result else None
    failure_class = (
        RISK_PROBE_CONTRACT_FAILURE_CLASS
        if missing_ids
        else "selected_target_reader_state_live_validation_failure"
    )
    failure_reason = (
        RISK_PROBE_CONTRACT_FAILURE_REASON
        if missing_ids
        else (
            "structured_output_validation_failed"
            if model_call_status == MODEL_CALL_VALIDATION_FAILED
            else "controller_validation_failed"
        )
    )
    return {
        "model_call_status": model_call_status,
        "failure_class": failure_class,
        "failure_reason": failure_reason,
        "validation_failures": validation_failures,
        "missing_risk_probe_ids": missing_ids,
        "missing_risk_probe_labels": [
            SELECTED_READER_STATE_REQUIRED_RISK_PROBES[risk_id]
            for risk_id in missing_ids
        ],
        "model_output_keys": sorted(output_payload),
        "raw_output_path": (
            latest_result.model_call.raw_output_path if latest_result is not None else None
        ),
    }


def _missing_risk_probe_ids(output_payload: dict[str, object]) -> list[str]:
    if not output_payload:
        return []
    by_id = output_payload.get("risk_probe_results_by_id")
    if isinstance(by_id, dict):
        present_ids = {str(risk_id) for risk_id in by_id}
    elif isinstance(output_payload.get("risk_probe_results"), list):
        present_ids = {
            str(item.get("risk_id"))
            for item in _object_items(output_payload.get("risk_probe_results"))
            if item.get("risk_id") in REQUIRED_RISK_PROBE_IDS
        }
    else:
        present_ids = set()
    return [risk_id for risk_id in REQUIRED_RISK_PROBE_IDS if risk_id not in present_ids]


def _model_output_payload_for_result(
    model_result: ModelDriverResult | None,
) -> dict[str, object]:
    if model_result is None or model_result.model_call.raw_output_path is None:
        return {}
    try:
        raw_output = Path(model_result.model_call.raw_output_path).read_text(
            encoding="utf-8"
        )
        payload = json.loads(raw_output)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_payload_artifact(
    *,
    writer: PacketWriter,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> None:
    payloads[artifact_type] = payload
    artifacts[artifact_type] = writer.write_artifact(
        artifact_type,
        payload,
        parent_ids=parent_ids,
    )


def _write_artifact(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> ArtifactRecord:
    return (model_writer or writer).write_artifact(
        artifact_type,
        payload,
        parent_ids=parent_ids,
    )


def _source_parent_ids(
    subject: NonlocalLawSelectedTargetReaderStateSubject,
    superseded_evaluation: ExistingSelectedTargetReaderStateEvaluation | None,
) -> list[str]:
    parent_ids = list(subject.source_parent_ids)
    if superseded_evaluation is not None:
        parent_ids.append(superseded_evaluation.artifact.id)
    return parent_ids


def _reader_state_mode_fields(
    client_name: str,
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingSelectedTargetReaderStateEvaluation | None,
) -> dict[str, object]:
    model_backed = client_name == "openai" and bool(model_results)
    provisional = not model_backed
    fields: dict[str, object] = {
        "model_backed": model_backed,
        "reader_state_evaluation_mode": (
            "model_backed_live" if model_backed else "deterministic_fake_verification"
        ),
        "provisional_reader_state_evaluation": provisional,
        "usable_for_command_verification": True,
        "usable_for_synthesis": model_backed,
        "ready_for_live_reader_state_evaluation": not model_backed,
        "ready_for_synthesis": model_backed,
    }
    if not model_backed:
        fields["synthesis_ready_only_after_model_backed_evaluation"] = True
    else:
        fields["synthesis_ready_only_after_model_backed_evaluation"] = False
    if superseded_evaluation is not None:
        fields.update(
            {
                "superseded_reader_state_evaluation_packet_id": (
                    superseded_evaluation.packet_id
                ),
                "supersession_reason": (
                    "model_backed_selected_target_reader_state_evaluation_supersedes_fake_evaluation"
                ),
                "superseded_evaluation_client": superseded_evaluation.client,
                "superseded_evaluation_model_backed": superseded_evaluation.model_backed,
                "superseded_evaluation_was_provisional": superseded_evaluation.provisional,
            }
        )
    return fields


def _evaluation_safety_fields(*, model_calls: int) -> dict[str, object]:
    return {
        "reader_state_evaluation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "synthesis_authorized": False,
        "current_best_updated": False,
        "model_calls": model_calls,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "current_best_supersession_claimed": False,
    }


def _model_call_count(model_payload: dict[str, object]) -> int:
    return 0 if model_payload.get("fixture_only") is True else 1


def _object_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


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


def _refusal(
    *,
    client_name: str,
    model: str | None,
    ablation_packet: Path | str,
    message: str,
) -> NonlocalLawSelectedTargetReaderStateEvaluationResult:
    return NonlocalLawSelectedTargetReaderStateEvaluationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "message": message,
            "ablation_packet": str(ablation_packet),
            "reader_state_evaluation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "model_calls": 0,
            "artifact_ids": {},
            "artifact_paths": {},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(f"{field_name} must be {str(expected).lower()}")


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
