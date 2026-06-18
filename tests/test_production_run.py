import json
from pathlib import Path

from abi.artifacts import list_artifacts
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
from abi.model_schemas import (
    ABI_EAR_VARIANTS_SCHEMA,
    LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS,
    LIVE_MINIMAL_REREAD_MODEL_SCHEMAS,
    REREAD_CONSEQUENCE_GRAPH_SCHEMA,
)
from abi.modules.production_run import (
    PRODUCTION_RUN_ARTIFACT_TYPES,
    PRODUCTION_RUN_REQUIRED_MODEL_CALLS,
    run_production_live_demo,
)


SOURCE_NOTE = """# Source Note

The table is the ordinary object the production scaffold must keep visible. It
stays in a small room while the unseen night supplies pressure.

Morning verifies the interval without turning the object into a symbol too
quickly.
"""

THEORY_FRAGMENT = """# Theory Fragment

A reread succeeds when the opening sentence has more force after the artifact
has been crossed once.

Production lineage should stay explicit so every later candidate can name its
source cards, packets, and limits.
"""


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def write_harness_fixtures(root: Path) -> None:
    fixture_dir = root / "fixtures" / "production_harness"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "source_note.md").write_text(SOURCE_NOTE, encoding="utf-8", newline="\n")
    (fixture_dir / "theory_fragment.md").write_text(
        THEORY_FRAGMENT,
        encoding="utf-8",
        newline="\n",
    )


def read_payload(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["payload"]


def test_fake_production_live_demo_creates_controlled_packet(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_live_demo(config, client_name="fake")

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert set(result.payload["artifact_ids"]) == set(PRODUCTION_RUN_ARTIFACT_TYPES)
    assert result.payload["counts"]["production_artifacts"] == 10
    assert result.payload["counts"]["upstream_model_calls"] == PRODUCTION_RUN_REQUIRED_MODEL_CALLS
    assert result.payload["counts"]["candidate_artifacts"] == 1
    assert Path(result.payload["packet_dir"]) == (
        tmp_path / "runs" / result.payload["run_id"] / "production" / "packet_0001"
    )

    candidate = read_payload(result.payload["artifact_paths"]["production_candidate_artifact"])
    assert candidate["non_final"] is True
    assert candidate["candidate_only"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["not_finalization_eligible"] is True
    assert candidate["finalization_eligible"] is False
    assert candidate["human_validated"] is False
    assert candidate["human_validation_claim"] is False

    packet = read_payload(result.payload["artifact_paths"]["production_packet"])
    for key in (
        "source_manifest_artifact_id",
        "harness_packet_reference_artifact_id",
        "selected_germ_artifact_id",
        "target_effect_artifact_id",
        "live_abi_ear_packet_reference_artifact_id",
        "live_reread_packet_reference_artifact_id",
        "candidate_artifact_id",
        "candidate_report_artifact_id",
        "production_gate_report_artifact_id",
    ):
        assert packet[key]
    assert packet["finalization_eligible"] is False
    assert packet["not_human_validated"] is True

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)
        model_calls = list_model_calls(connection, run_id=result.payload["run_id"])

    assert latest_run.active_phase == "phase10_source_to_artifact_production_run"
    assert len(model_calls) == PRODUCTION_RUN_REQUIRED_MODEL_CALLS
    assert {call.status for call in model_calls} == {MODEL_CALL_SUCCESS}

    production_artifacts = {
        artifact.type: artifact for artifact in artifacts if artifact.type in PRODUCTION_RUN_ARTIFACT_TYPES
    }
    assert set(production_artifacts) == set(PRODUCTION_RUN_ARTIFACT_TYPES)
    for artifact in production_artifacts.values():
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["artifact_type"] == artifact.type
        assert envelope["fixture_only"] is True
        assert envelope["model_call_id"] is None
        assert artifact.parent_ids
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))

    model_artifact_types = {
        schema.artifact_type
        for schema in LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS + LIVE_MINIMAL_REREAD_MODEL_SCHEMAS
    }
    for artifact in artifacts:
        if artifact.type in model_artifact_types:
            envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
            assert envelope["model_call_id"] is not None


def test_fake_production_live_demo_uses_unique_packet_dirs(tmp_path):
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    first = run_production_live_demo(config, client_name="fake")
    second = run_production_live_demo(config, client_name="fake")

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert first.payload["counts"] == second.payload["counts"]
    assert set(first.payload["artifact_paths"].values()).isdisjoint(
        set(second.payload["artifact_paths"].values())
    )
    assert read_payload(first.payload["artifact_paths"]["production_candidate_artifact"])["text"] == read_payload(
        second.payload["artifact_paths"]["production_candidate_artifact"]
    )["text"]


def test_production_budget_guard_refuses_before_run(tmp_path):
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_live_demo(
        config,
        client_name="fake",
        max_model_calls=PRODUCTION_RUN_REQUIRED_MODEL_CALLS - 1,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "max-model-calls" in result.payload["message"]
    assert not config.db_path.exists()


def test_production_fake_invalid_output_records_failure_without_production_packet(tmp_path):
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_live_demo(
        config,
        client_name="fake",
        ear_fake_mode="invalid",
        ear_fake_target_schema=ABI_EAR_VARIANTS_SCHEMA,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["artifact_ids"] == {}
    failed_call = result.ear_result.payload["model_calls"][-1]
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert ABI_EAR_VARIANTS_SCHEMA.artifact_type not in result.ear_result.payload["artifact_ids"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])

    assert not ({artifact.type for artifact in artifacts} & set(PRODUCTION_RUN_ARTIFACT_TYPES))


def test_production_fake_client_failure_records_failure_without_production_packet(tmp_path):
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_live_demo(
        config,
        client_name="fake",
        reread_fake_mode="failure",
        reread_fake_target_schema=REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["artifact_ids"] == {}
    failed_call = result.reread_result.payload["model_calls"][-1]
    assert failed_call["status"] == MODEL_CALL_CLIENT_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert REREAD_CONSEQUENCE_GRAPH_SCHEMA.artifact_type not in result.reread_result.payload[
        "artifact_ids"
    ]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])

    assert not ({artifact.type for artifact in artifacts} & set(PRODUCTION_RUN_ARTIFACT_TYPES))


def test_openai_production_refuses_without_allow_before_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_live_demo(config, client_name="openai")

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert not config.db_path.exists()


def test_openai_production_refuses_without_key_before_run(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_live_demo(
        config,
        client_name="openai",
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert not config.db_path.exists()


def test_production_cli_fake_and_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_harness_fixtures(tmp_path)

    fake_exit = main(["--root", str(tmp_path), "production", "live-demo", "--client", "fake"])
    fake_payload = json.loads(capsys.readouterr().out)

    assert fake_exit == 0
    assert fake_payload["client"] == "fake"
    assert fake_payload["counts"]["upstream_model_calls"] == PRODUCTION_RUN_REQUIRED_MODEL_CALLS

    openai_exit = main(["--root", str(tmp_path), "production", "live-demo", "--client", "openai"])
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]


def test_fake_production_preserves_finalization_fail_closed(tmp_path):
    write_harness_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_production_live_demo(config, client_name="fake")

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=result.payload["run_id"])

    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
