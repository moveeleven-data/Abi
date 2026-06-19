"""Sealed model driver for fake and guarded live structured outputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Protocol

from abi.artifacts import ArtifactRecord
from abi.config import AbiConfig
from abi.controller.state import ensure_active_run, utc_now
from abi.db import connect
from abi.hashing import sha256_text
from abi.ids import model_call_id as make_model_call_id
from abi.model_calls import (
    MODEL_CALL_CLIENT_FAILED,
    MODEL_CALL_SUCCESS,
    MODEL_CALL_VALIDATION_FAILED,
    ModelCallRecord,
    record_model_call,
)
from abi.model_schemas import (
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    ModelValidationError,
    WorkerRole,
    WorkerSchema,
    parse_and_validate_structured_output,
)
from abi.packets import PacketWriter


FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-structured-output-v1"
MODEL_DRIVER_LINEAGE_ID = "phase6b_model_driver_fake_client"
MODEL_DRIVER_PROMPT_CONTRACT_ID = "phase6b.fake.abi_ear_germ_analysis"
MODEL_DRIVER_DEMO_INPUT = "The table is still there in the morning."


class ModelClient(Protocol):
    provider: str
    model: str

    def generate(self, request: "WorkerRequest") -> str:
        """Return raw structured output text or raise a client failure."""


class ModelClientError(RuntimeError):
    """Raised by model clients to record client_failed calls."""


class FakeModelClientError(ModelClientError):
    """Raised by the fake client to simulate client failure."""


@dataclass(frozen=True)
class WorkerRequest:
    run_id: str
    worker_role: WorkerRole
    prompt_contract_id: str
    schema: WorkerSchema
    input_text: str
    input_artifact_ids: list[str] = field(default_factory=list)
    input_packet_path: str | None = None
    lineage_id: str | None = MODEL_DRIVER_LINEAGE_ID
    parent_ids: list[str] = field(default_factory=list)
    fixture_only: bool | None = True
    output_dir: str | None = None
    register_parsed_artifact: bool = True
    parsed_payload_validator: Callable[[dict[str, object]], None] | None = None

    def input_hash(self) -> str:
        return sha256_text(
            json.dumps(
                {
                    "worker_role": self.worker_role.value,
                    "prompt_contract_id": self.prompt_contract_id,
                    "schema_name": self.schema.name,
                    "schema_version": self.schema.version,
                    "input_text": self.input_text,
                    "input_artifact_ids": list(self.input_artifact_ids),
                    "input_packet_path": self.input_packet_path,
                    "register_parsed_artifact": self.register_parsed_artifact,
                    "has_parsed_payload_validator": self.parsed_payload_validator is not None,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )


@dataclass(frozen=True)
class ModelDriverResult:
    model_call: ModelCallRecord
    parsed_payload: dict[str, object] | None
    parsed_artifact: ArtifactRecord | None

    @property
    def accepted(self) -> bool:
        return self.model_call.status == MODEL_CALL_SUCCESS

    def to_cli_summary(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "model_call": self.model_call_to_dict(),
            "parsed_artifact_id": (
                self.parsed_artifact.id if self.parsed_artifact is not None else None
            ),
        }

    def model_call_to_dict(self) -> dict[str, object]:
        from abi.model_calls import model_call_to_dict

        return model_call_to_dict(self.model_call)


class FakeModelClient:
    provider = FAKE_PROVIDER
    model = FAKE_MODEL

    def __init__(self, mode: str = "valid") -> None:
        self.mode = mode

    def generate(self, request: WorkerRequest) -> str:
        if self.mode == "valid":
            return _canonical_json(
                {
                    "germ_text": request.input_text,
                    "word_forces": [
                        {
                            "word": "table",
                            "force": "anchors the fake structured output in an object",
                        },
                        {
                            "word": "still",
                            "force": "marks persistence as the local pressure point",
                        },
                    ],
                    "fertility_score": 0.5,
                    "risks": ["fixture output is not real validation"],
                }
            )
        if self.mode == "minimal":
            return _canonical_json(
                {
                    "germ_text": request.input_text,
                    "word_forces": [],
                    "fertility_score": 0.0,
                    "risks": [],
                }
            )
        if self.mode == "invalid_json":
            return "{not valid json"
        if self.mode == "malformed":
            return _canonical_json({"germ_text": request.input_text, "word_forces": "wrong"})
        if self.mode == "failure":
            raise FakeModelClientError("simulated fake client failure")
        raise FakeModelClientError(f"unknown fake client mode: {self.mode}")


class ModelDriver:
    def __init__(self, *, config: AbiConfig, client: ModelClient) -> None:
        self.config = config
        self.client = client

    def run(self, request: WorkerRequest) -> ModelDriverResult:
        created_at = utc_now()
        call_id = make_model_call_id(
            request.run_id,
            request.worker_role.value,
            request.schema.name,
            request.schema.version,
            created_at,
        )
        if request.output_dir is None:
            call_dir = self.config.run_dir(request.run_id) / "model_calls" / call_id
        else:
            call_dir = Path(request.output_dir) / "model_calls" / call_id
        call_dir.mkdir(parents=True, exist_ok=True)
        raw_output_path = call_dir / "raw_output.txt"
        input_hash = request.input_hash()

        try:
            raw_output = self.client.generate(request)
        except ModelClientError as error:
            failure_path = call_dir / "client_failure.json"
            failure_path.write_text(
                _canonical_json({"error_message": str(error), "status": MODEL_CALL_CLIENT_FAILED}),
                encoding="utf-8",
                newline="\n",
            )
            return self._record_result(
                request=request,
                call_id=call_id,
                created_at=created_at,
                input_hash=input_hash,
                raw_output_path=failure_path,
                status=MODEL_CALL_CLIENT_FAILED,
                error_message=str(error),
                parsed_payload=None,
                parsed_artifact=None,
            )

        raw_output_path.write_text(raw_output, encoding="utf-8", newline="\n")
        try:
            parsed_payload = parse_and_validate_structured_output(raw_output, request.schema)
            if request.parsed_payload_validator is not None:
                request.parsed_payload_validator(parsed_payload)
        except ModelValidationError as error:
            return self._record_result(
                request=request,
                call_id=call_id,
                created_at=created_at,
                input_hash=input_hash,
                raw_output_path=raw_output_path,
                status=MODEL_CALL_VALIDATION_FAILED,
                error_message=str(error),
                parsed_payload=None,
                parsed_artifact=None,
            )

        parsed_artifact = None
        if request.register_parsed_artifact:
            with connect(self.config.db_path) as connection:
                writer = PacketWriter(
                    connection=connection,
                    run_id=request.run_id,
                    packet_dir=call_dir,
                    lineage_id=request.lineage_id,
                    created_by=f"model_driver:{self.client.provider}:{self.client.model}",
                    fixture_only=request.fixture_only,
                    model_call_id=call_id,
                )
                parsed_artifact = writer.write_artifact(
                    request.schema.artifact_type,
                    parsed_payload,
                    parent_ids=_artifact_parent_ids(request),
                )

        return self._record_result(
            request=request,
            call_id=call_id,
            created_at=created_at,
            input_hash=input_hash,
            raw_output_path=raw_output_path,
            status=MODEL_CALL_SUCCESS,
            error_message=None,
            parsed_payload=parsed_payload,
            parsed_artifact=parsed_artifact,
        )

    def _record_result(
        self,
        *,
        request: WorkerRequest,
        call_id: str,
        created_at: str,
        input_hash: str,
        raw_output_path: Path,
        status: str,
        error_message: str | None,
        parsed_payload: dict[str, object] | None,
        parsed_artifact: ArtifactRecord | None,
    ) -> ModelDriverResult:
        record = ModelCallRecord(
            id=call_id,
            run_id=request.run_id,
            worker_role=request.worker_role.value,
            prompt_contract_id=request.prompt_contract_id,
            input_artifact_ids=list(request.input_artifact_ids),
            input_packet_path=request.input_packet_path,
            input_hash=input_hash,
            schema_name=request.schema.name,
            schema_version=request.schema.version,
            provider=self.client.provider,
            model=self.client.model,
            raw_output_path=str(raw_output_path),
            parsed_output_artifact_id=(
                parsed_artifact.id if parsed_artifact is not None else None
            ),
            status=status,
            error_message=error_message,
            created_at=created_at,
        )
        with connect(self.config.db_path) as connection:
            record_model_call(connection, record)
        return ModelDriverResult(
            model_call=record,
            parsed_payload=parsed_payload,
            parsed_artifact=parsed_artifact,
        )


def run_model_driver_demo(config: AbiConfig, *, mode: str = "valid") -> ModelDriverResult:
    run, _ = ensure_active_run(config)
    request = WorkerRequest(
        run_id=run.id,
        worker_role=WorkerRole.ABI_EAR_GERM_ANALYZER,
        prompt_contract_id=MODEL_DRIVER_PROMPT_CONTRACT_ID,
        schema=ABI_EAR_GERM_ANALYSIS_SCHEMA,
        input_text=MODEL_DRIVER_DEMO_INPUT,
    )
    driver = ModelDriver(config=config, client=FakeModelClient(mode=mode))
    return driver.run(request)


def _artifact_parent_ids(request: WorkerRequest) -> list[str]:
    return list(request.parent_ids or request.input_artifact_ids)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
