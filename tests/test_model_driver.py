import json
from pathlib import Path

from abi.artifacts import get_artifact, list_artifacts
from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.state import ensure_active_run
from abi.db import connect
from abi.model_calls import (
    MODEL_CALL_CLIENT_FAILED,
    MODEL_CALL_SUCCESS,
    MODEL_CALL_VALIDATION_FAILED,
    get_model_call,
    list_model_calls,
)
from abi.model_driver import run_model_driver_demo
from abi.model_schemas import ABI_EAR_GERM_ANALYSIS_SCHEMA, WorkerRole


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_valid_fake_structured_output_is_accepted_and_registered(tmp_path):
    config = config_for(tmp_path)
    result = run_model_driver_demo(config)

    assert result.accepted is True
    assert result.model_call.status == MODEL_CALL_SUCCESS
    assert result.parsed_artifact is not None
    assert result.parsed_payload is not None

    with connect(config.db_path) as connection:
        stored_call = get_model_call(connection, result.model_call.id)
        stored_artifact = get_artifact(connection, result.parsed_artifact.id)

    assert stored_call == result.model_call
    assert stored_call.input_hash
    assert stored_call.schema_name == ABI_EAR_GERM_ANALYSIS_SCHEMA.name
    assert stored_call.schema_version == ABI_EAR_GERM_ANALYSIS_SCHEMA.version
    assert stored_call.worker_role == WorkerRole.ABI_EAR_GERM_ANALYZER.value
    assert stored_call.provider == "fake"
    assert stored_call.model == "fake-structured-output-v1"
    assert stored_call.raw_output_path is not None
    assert Path(stored_call.raw_output_path).is_file()
    assert stored_call.parsed_output_artifact_id == result.parsed_artifact.id
    assert stored_artifact == result.parsed_artifact

    envelope = json.loads(Path(result.parsed_artifact.path).read_text(encoding="utf-8"))
    assert envelope["schema_version"] == "1"
    assert envelope["artifact_type"] == ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type
    assert envelope["model_call_id"] == result.model_call.id
    assert envelope["created_by"] == "model_driver:fake:fake-structured-output-v1"
    assert envelope["fixture_only"] is True
    assert envelope["payload"] == result.parsed_payload


def test_invalid_fake_output_is_rejected_and_does_not_register_artifact(tmp_path):
    config = config_for(tmp_path)

    result = run_model_driver_demo(config, mode="invalid_json")

    assert result.accepted is False
    assert result.model_call.status == MODEL_CALL_VALIDATION_FAILED
    assert result.parsed_artifact is None
    assert result.model_call.parsed_output_artifact_id is None
    assert "invalid JSON" in result.model_call.error_message
    assert Path(result.model_call.raw_output_path).is_file()

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.model_call.run_id)
        model_calls = list_model_calls(connection)

    assert artifacts == []
    assert model_calls == [result.model_call]


def test_malformed_fake_output_is_rejected_and_does_not_register_artifact(tmp_path):
    config = config_for(tmp_path)

    result = run_model_driver_demo(config, mode="malformed")

    assert result.accepted is False
    assert result.model_call.status == MODEL_CALL_VALIDATION_FAILED
    assert result.parsed_artifact is None
    assert "word_forces must be list" in result.model_call.error_message

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.model_call.run_id)

    assert artifacts == []


def test_schema_valid_minimal_fake_output_is_accepted(tmp_path):
    config = config_for(tmp_path)

    result = run_model_driver_demo(config, mode="minimal")

    assert result.accepted is True
    assert result.parsed_payload == {
        "germ_text": "The table is still there in the morning.",
        "word_forces": [],
        "fertility_score": 0.0,
        "risks": [],
    }


def test_simulated_client_failure_records_failed_call_without_artifact(tmp_path):
    config = config_for(tmp_path)

    result = run_model_driver_demo(config, mode="failure")

    assert result.accepted is False
    assert result.model_call.status == MODEL_CALL_CLIENT_FAILED
    assert result.model_call.parsed_output_artifact_id is None
    assert result.parsed_artifact is None
    assert "simulated fake client failure" in result.model_call.error_message
    assert Path(result.model_call.raw_output_path).is_file()

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.model_call.run_id)

    assert artifacts == []


def test_model_driver_requires_no_external_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = config_for(tmp_path)

    result = run_model_driver_demo(config)

    assert result.accepted is True


def test_model_driver_cli_and_existing_artifact_inspection(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "model-driver", "demo"]) == 0
    demo_payload = json.loads(capsys.readouterr().out)
    model_call_id = demo_payload["model_call"]["id"]
    artifact_id = demo_payload["parsed_artifact_id"]

    assert main(["--root", str(tmp_path), "model-call", "list"]) == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert [record["id"] for record in list_payload["model_calls"]] == [model_call_id]

    assert main(["--root", str(tmp_path), "model-call", "show", model_call_id]) == 0
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload["model_call"]["id"] == model_call_id
    assert show_payload["model_call"]["status"] == MODEL_CALL_SUCCESS

    assert main(["--root", str(tmp_path), "artifact", "show", artifact_id]) == 0
    artifact_payload = json.loads(capsys.readouterr().out)
    assert artifact_payload["artifact"]["id"] == artifact_id
    assert artifact_payload["content"]["model_call_id"] == model_call_id
    assert artifact_payload["content"]["payload"]["germ_text"] == (
        "The table is still there in the morning."
    )


def test_model_driver_does_not_change_finalization_fail_closed(tmp_path):
    config = config_for(tmp_path)
    ensure_active_run(config)
    result = run_model_driver_demo(config)

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=result.model_call.run_id)

    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
