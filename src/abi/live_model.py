"""Guarded live model worker entrypoints for Phase 7A."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os

from abi.config import AbiConfig
from abi.controller.state import ensure_active_run
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ABI_EAR_FIELD_MODEL_SCHEMA,
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    WorkerRole,
    WorkerSchema,
)


LIVE_WORKER_ABI_EAR_GERM_ANALYSIS = "abi_ear_germ_analysis"
LIVE_WORKER_ABI_EAR_FIELD_MODEL = "abi_ear_field_model"
LIVE_WORKERS = (
    LIVE_WORKER_ABI_EAR_GERM_ANALYSIS,
    LIVE_WORKER_ABI_EAR_FIELD_MODEL,
)
LIVE_MODEL_DEFAULT = "gpt-5.5"
LIVE_ABI_EAR_GERM_TEXT = "The table is still there in the morning."
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
ABI_OPENAI_MODEL_ENV = "ABI_OPENAI_MODEL"


@dataclass(frozen=True)
class LiveModelCommandResult:
    exit_code: int
    payload: dict[str, object]
    driver_result: ModelDriverResult | None = None


@dataclass(frozen=True)
class LiveWorkerSpec:
    worker: str
    worker_role: WorkerRole
    schema: WorkerSchema
    lineage_id: str
    prompt_contract_id: str


LIVE_WORKER_SPECS = {
    LIVE_WORKER_ABI_EAR_GERM_ANALYSIS: LiveWorkerSpec(
        worker=LIVE_WORKER_ABI_EAR_GERM_ANALYSIS,
        worker_role=WorkerRole.ABI_EAR_GERM_ANALYZER,
        schema=ABI_EAR_GERM_ANALYSIS_SCHEMA,
        lineage_id="phase7a_live_abi_ear_germ_analysis",
        prompt_contract_id="phase7a.live.abi_ear_germ_analysis",
    ),
    LIVE_WORKER_ABI_EAR_FIELD_MODEL: LiveWorkerSpec(
        worker=LIVE_WORKER_ABI_EAR_FIELD_MODEL,
        worker_role=WorkerRole.ABI_EAR_FIELD_MODEL_BUILDER,
        schema=ABI_EAR_FIELD_MODEL_SCHEMA,
        lineage_id="phase7b_live_abi_ear_field_model",
        prompt_contract_id="phase7b.live.abi_ear_field_model",
    ),
}


def run_live_abi_ear_worker(
    config: AbiConfig,
    *,
    allow_live_model: bool,
    worker: str = LIVE_WORKER_ABI_EAR_GERM_ANALYSIS,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> LiveModelCommandResult:
    worker_spec = LIVE_WORKER_SPECS.get(worker)
    if worker_spec is None:
        return _refusal(
            worker=worker,
            model=model,
            message=f"Live model worker is not available: {worker}",
        )
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if not allow_live_model:
        return _refusal(
            worker=worker,
            model=configured_model,
            message=(
                "Live model command refused; pass --allow-live-model to opt in explicitly."
            ),
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if not resolved_api_key:
        return _refusal(
            worker=worker,
            model=configured_model,
            message=f"Live model command refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    run, _ = ensure_active_run(config)
    factory = client_factory or _default_openai_client_factory
    client = factory(configured_model)
    request = WorkerRequest(
        run_id=run.id,
        worker_role=worker_spec.worker_role,
        prompt_contract_id=worker_spec.prompt_contract_id,
        schema=worker_spec.schema,
        input_text=LIVE_ABI_EAR_GERM_TEXT,
        lineage_id=worker_spec.lineage_id,
        fixture_only=False,
    )
    result = ModelDriver(config=config, client=client).run(request)
    payload = {
        "refused": False,
        "worker": worker,
        "model": configured_model,
        "accepted": result.accepted,
        "model_call": result.model_call_to_dict(),
        "parsed_artifact_id": (
            result.parsed_artifact.id if result.parsed_artifact is not None else None
        ),
    }
    return LiveModelCommandResult(
        exit_code=0 if result.accepted else 1,
        payload=payload,
        driver_result=result,
    )


def run_live_abi_ear_germ_analysis(
    config: AbiConfig,
    *,
    allow_live_model: bool,
    worker: str = LIVE_WORKER_ABI_EAR_GERM_ANALYSIS,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> LiveModelCommandResult:
    return run_live_abi_ear_worker(
        config,
        allow_live_model=allow_live_model,
        worker=worker,
        api_key=api_key,
        model=model,
        client_factory=client_factory,
    )


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _refusal(*, worker: str, model: str | None, message: str) -> LiveModelCommandResult:
    return LiveModelCommandResult(
        exit_code=1,
        payload={
            "refused": True,
            "worker": worker,
            "model": model,
            "accepted": False,
            "model_call": None,
            "parsed_artifact_id": None,
            "message": message,
        },
    )
