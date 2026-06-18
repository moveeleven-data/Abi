import json
from pathlib import Path

from abi.artifacts import get_artifact, list_artifacts
from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.state import get_latest_run
from abi.db import connect
from abi.model_calls import (
    MODEL_CALL_CLIENT_FAILED,
    MODEL_CALL_SUCCESS,
    MODEL_CALL_VALIDATION_FAILED,
    list_model_calls,
)
from abi.model_schemas import REREAD_CONSEQUENCE_GRAPH_SCHEMA
from abi.modules.live_reread import (
    LIVE_REREAD_ARTIFACT_TYPES,
    LIVE_REREAD_LINEAGE_ID,
    LIVE_MINIMAL_REREAD_MODEL_SCHEMAS,
    run_live_reread_packet_demo,
)


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_fake_live_reread_packet_creates_required_artifacts_and_model_calls(tmp_path):
    config = config_for(tmp_path)

    result = run_live_reread_packet_demo(config, client_name="fake")

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert result.payload["counts"]["artifacts"] == 13
    assert result.payload["counts"]["model_artifacts"] == 12
    assert result.payload["counts"]["counterfactual_results"] == 1
    assert set(result.payload["artifact_ids"]) == set(LIVE_REREAD_ARTIFACT_TYPES)
    assert Path(result.payload["packet_dir"]).is_dir()

    model_calls = result.payload["model_calls"]
    assert len(model_calls) == 12
    assert {call["status"] for call in model_calls} == {MODEL_CALL_SUCCESS}

    model_artifact_types = {schema.artifact_type for schema in LIVE_MINIMAL_REREAD_MODEL_SCHEMAS}
    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)

    assert latest_run.active_phase == "phase9_live_minimal_reread"
    artifact_by_type = {artifact.type: artifact for artifact in artifacts}
    for artifact_type in model_artifact_types:
        artifact = artifact_by_type[artifact_type]
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["model_call_id"] is not None
        assert envelope["fixture_only"] is True
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))
    assert artifact_by_type["live_reread_packet"].lineage_id == LIVE_REREAD_LINEAGE_ID
    assert artifact_by_type["live_reread_counterfactual_result"].parent_ids
    assert artifact_by_type["live_reread_gate_report"].parent_ids


def test_fake_live_reread_packet_is_deterministic_and_uses_unique_packet_dirs(tmp_path):
    config = config_for(tmp_path)

    first = run_live_reread_packet_demo(config, client_name="fake")
    second = run_live_reread_packet_demo(config, client_name="fake")

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert first.payload["counts"] == second.payload["counts"]
    first_paths = set(first.payload["artifact_paths"].values())
    second_paths = set(second.payload["artifact_paths"].values())
    assert first_paths.isdisjoint(second_paths)


def test_fake_live_reread_budget_guard_refuses_before_run(tmp_path):
    config = config_for(tmp_path)

    result = run_live_reread_packet_demo(
        config,
        client_name="fake",
        max_model_calls=11,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "max-model-calls" in result.payload["message"]
    assert not config.db_path.exists()


def test_fake_live_reread_invalid_output_records_validation_failure_without_artifact(tmp_path):
    config = config_for(tmp_path)

    result = run_live_reread_packet_demo(
        config,
        client_name="fake",
        fake_mode="invalid",
        fake_target_schema=REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    )

    assert result.exit_code == 1
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == REREAD_CONSEQUENCE_GRAPH_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert REREAD_CONSEQUENCE_GRAPH_SCHEMA.artifact_type not in result.payload["artifact_ids"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])

    assert {artifact.type for artifact in artifacts} == {
        "live_reread_formal_problem",
        "live_reread_germ_afterimage_pair",
    }


def test_fake_live_reread_client_failure_records_failure_without_artifact(tmp_path):
    config = config_for(tmp_path)

    result = run_live_reread_packet_demo(
        config,
        client_name="fake",
        fake_mode="failure",
        fake_target_schema=REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    )

    assert result.exit_code == 1
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["status"] == MODEL_CALL_CLIENT_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "simulated fake reread packet client failure" in failed_call["error_message"]

    with connect(config.db_path) as connection:
        calls = list_model_calls(connection, run_id=result.payload["run_id"])
        artifact = get_artifact(connection, failed_call["parsed_output_artifact_id"])

    assert calls[-1].status == MODEL_CALL_CLIENT_FAILED
    assert artifact is None


def test_openai_live_reread_refuses_without_allow_before_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config = config_for(tmp_path)

    result = run_live_reread_packet_demo(config, client_name="openai")

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert not config.db_path.exists()


def test_openai_live_reread_refuses_without_openai_key_before_run(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = config_for(tmp_path)

    result = run_live_reread_packet_demo(
        config,
        client_name="openai",
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert not config.db_path.exists()


def test_live_reread_cli_fake_and_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_exit = main(["--root", str(tmp_path), "reread", "live-demo", "--client", "fake"])
    fake_payload = json.loads(capsys.readouterr().out)

    assert fake_exit == 0
    assert fake_payload["client"] == "fake"
    assert fake_payload["counts"]["counterfactual_results"] == 1

    openai_exit = main(["--root", str(tmp_path), "reread", "live-demo", "--client", "openai"])
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]


def test_fake_live_reread_preserves_finalization_fail_closed(tmp_path):
    config = config_for(tmp_path)
    result = run_live_reread_packet_demo(config, client_name="fake")

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=result.payload["run_id"])

    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
