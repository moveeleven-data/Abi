import json
from pathlib import Path

from abi.artifacts import get_artifact, list_artifacts
from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.db import connect
from abi.live_model import LIVE_WORKER_ABI_EAR_GERM_ANALYSIS, run_live_abi_ear_germ_analysis
from abi.model_calls import (
    MODEL_CALL_CLIENT_FAILED,
    MODEL_CALL_SUCCESS,
    MODEL_CALL_VALIDATION_FAILED,
    get_model_call,
)
from abi.model_driver import ModelClientError, WorkerRequest
from abi.model_schemas import ABI_EAR_GERM_ANALYSIS_SCHEMA, WorkerRole


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


class CountingLiveClientFactory:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.constructed = 0
        self.clients: list[StubLiveClient] = []

    def __call__(self, model: str) -> "StubLiveClient":
        self.constructed += 1
        client = StubLiveClient(mode=self.mode, model=model)
        self.clients.append(client)
        return client


class StubLiveClient:
    provider = "openai"

    def __init__(self, *, mode: str, model: str) -> None:
        self.mode = mode
        self.model = model
        self.calls = 0

    def generate(self, request: WorkerRequest) -> str:
        self.calls += 1
        if self.mode == "valid":
            return json.dumps(
                {
                    "germ_text": request.input_text,
                    "word_forces": [
                        {"word": "table", "force": "object pressure"},
                        {"word": "still", "force": "temporal hinge"},
                    ],
                    "fertility_score": 0.75,
                    "risks": ["stubbed live adapter output"],
                },
                sort_keys=True,
            )
        if self.mode == "invalid":
            return json.dumps({"germ_text": request.input_text, "word_forces": "bad"})
        if self.mode == "failure":
            raise ModelClientError("stubbed live client failure")
        raise AssertionError(f"unknown stub mode: {self.mode}")


def test_missing_allow_live_model_refuses_before_client_call(tmp_path):
    config = config_for(tmp_path)
    factory = CountingLiveClientFactory("valid")

    result = run_live_abi_ear_germ_analysis(
        config,
        allow_live_model=False,
        api_key="stub-key",
        client_factory=factory,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert factory.constructed == 0
    assert not config.db_path.exists()


def test_missing_openai_key_refuses_before_client_call(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = config_for(tmp_path)
    factory = CountingLiveClientFactory("valid")

    result = run_live_abi_ear_germ_analysis(
        config,
        allow_live_model=True,
        api_key=None,
        client_factory=factory,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert factory.constructed == 0
    assert not config.db_path.exists()


def test_stubbed_live_success_creates_model_call_and_artifact(tmp_path):
    config = config_for(tmp_path)
    factory = CountingLiveClientFactory("valid")

    result = run_live_abi_ear_germ_analysis(
        config,
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-model",
        client_factory=factory,
    )

    assert result.exit_code == 0
    assert factory.constructed == 1
    assert factory.clients[0].calls == 1
    assert result.driver_result is not None
    assert result.driver_result.accepted is True

    model_call = result.driver_result.model_call
    assert model_call.status == MODEL_CALL_SUCCESS
    assert model_call.worker_role == WorkerRole.ABI_EAR_GERM_ANALYZER.value
    assert model_call.schema_name == ABI_EAR_GERM_ANALYSIS_SCHEMA.name
    assert model_call.schema_version == ABI_EAR_GERM_ANALYSIS_SCHEMA.version
    assert model_call.provider == "openai"
    assert model_call.model == "stub-live-model"
    assert model_call.parsed_output_artifact_id is not None

    with connect(config.db_path) as connection:
        stored_call = get_model_call(connection, model_call.id)
        artifact = get_artifact(connection, model_call.parsed_output_artifact_id)

    assert stored_call == model_call
    assert artifact is not None
    envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    assert envelope["model_call_id"] == model_call.id
    assert envelope["fixture_only"] is False
    assert envelope["created_by"] == "model_driver:openai:stub-live-model"
    assert envelope["payload"]["germ_text"] == "The table is still there in the morning."


def test_stubbed_live_validation_failure_records_failure_without_artifact(tmp_path):
    config = config_for(tmp_path)
    factory = CountingLiveClientFactory("invalid")

    result = run_live_abi_ear_germ_analysis(
        config,
        allow_live_model=True,
        api_key="stub-key",
        client_factory=factory,
    )

    assert result.exit_code == 1
    assert result.driver_result is not None
    assert result.driver_result.model_call.status == MODEL_CALL_VALIDATION_FAILED
    assert result.driver_result.model_call.parsed_output_artifact_id is None
    assert result.driver_result.parsed_artifact is None

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.driver_result.model_call.run_id)

    assert artifacts == []


def test_stubbed_live_client_failure_records_failure_without_artifact(tmp_path):
    config = config_for(tmp_path)
    factory = CountingLiveClientFactory("failure")

    result = run_live_abi_ear_germ_analysis(
        config,
        allow_live_model=True,
        api_key="stub-key",
        client_factory=factory,
    )

    assert result.exit_code == 1
    assert result.driver_result is not None
    assert result.driver_result.model_call.status == MODEL_CALL_CLIENT_FAILED
    assert result.driver_result.model_call.parsed_output_artifact_id is None
    assert "stubbed live client failure" in result.driver_result.model_call.error_message

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.driver_result.model_call.run_id)

    assert artifacts == []


def test_live_worker_cli_refuses_without_allow_flag(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "model-driver",
            "live-demo",
            "--worker",
            LIVE_WORKER_ABI_EAR_GERM_ANALYSIS,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["refused"] is True
    assert "--allow-live-model" in payload["message"]


def test_live_worker_cli_refuses_without_openai_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "model-driver",
            "live-demo",
            "--worker",
            LIVE_WORKER_ABI_EAR_GERM_ANALYSIS,
            "--allow-live-model",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["refused"] is True
    assert "OPENAI_API_KEY" in payload["message"]


def test_live_worker_preserves_finalization_fail_closed(tmp_path):
    config = config_for(tmp_path)
    factory = CountingLiveClientFactory("valid")
    result = run_live_abi_ear_germ_analysis(
        config,
        allow_live_model=True,
        api_key="stub-key",
        client_factory=factory,
    )

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=result.driver_result.model_call.run_id)

    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
