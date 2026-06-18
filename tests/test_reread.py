import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.state import PHASE2_MINIMAL_REREAD_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.modules.reread import REREAD_ARTIFACT_TYPES, build_reread_payloads, run_reread_demo


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_reread_payloads_are_deterministic():
    first = build_reread_payloads()
    second = build_reread_payloads()

    assert first == second
    assert tuple(first) == REREAD_ARTIFACT_TYPES
    assert first["reread_draft_version"]["text"].startswith(
        "The table is still there in the morning."
    )
    assert first["reread_recomposed_draft"]["text"].startswith(
        "The table is still there in the morning."
    )
    assert first["reread_counterfactual_result"]["delta"]["targeted_failure_reduced"] is True
    assert first["reread_gate_report"]["passed"] is True
    assert first["reread_packet"]["loop_shape"] == [
        "reader-state trace",
        "diagnosed failure",
        "targeted intervention",
        "counterfactual proof",
    ]


def test_reread_demo_registers_all_artifacts_and_parent_ids(tmp_path):
    config = config_for(tmp_path)

    result = run_reread_demo(config)

    assert set(result.artifact_ids) == set(REREAD_ARTIFACT_TYPES)
    assert result.gate_result["passed"] is True
    assert result.payloads["reread_gate_report"]["passed"] is True
    assert "reread_counterfactual_result" in result.artifact_ids

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.run_id)
        latest_run = get_latest_run(connection)

    reread_artifacts = {
        artifact.type: artifact for artifact in artifacts if artifact.type in REREAD_ARTIFACT_TYPES
    }
    assert set(reread_artifacts) == set(REREAD_ARTIFACT_TYPES)
    assert latest_run.active_phase == PHASE2_MINIMAL_REREAD_ACTIVE_PHASE
    for artifact_type in REREAD_ARTIFACT_TYPES:
        assert reread_artifacts[artifact_type].parent_ids
    assert result.abi_ear_packet_artifact_id in reread_artifacts["reread_formal_problem"].parent_ids
    assert len(reread_artifacts["reread_packet"].parent_ids) == 13

    for artifact_type, artifact_path in result.artifact_paths.items():
        path = (
            tmp_path
            / "runs"
            / result.run_id
            / "reread"
            / result.packet_id
            / f"{artifact_type}.json"
        )
        assert artifact_path == str(path)
        assert path.is_file()
        envelope = json.loads(path.read_text(encoding="utf-8"))
        assert envelope["schema_version"] == "1"
        assert envelope["artifact_type"] == artifact_type
        assert envelope["run_id"] == result.run_id
        assert envelope["lineage_id"] == "minimal_reread_v1_benchmark"
        assert envelope["parent_ids"] == reread_artifacts[artifact_type].parent_ids
        assert envelope["created_by"] == "minimal_reread_v1_stub"
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is None
        assert envelope["payload"] == result.payloads[artifact_type]


def test_reread_demo_packet_directory_is_unique_per_invocation(tmp_path):
    config = config_for(tmp_path)

    first = run_reread_demo(config)
    first_paths = dict(first.artifact_paths)
    first_file_contents = {
        artifact_type: path.read_text(encoding="utf-8")
        for artifact_type, artifact_path in first_paths.items()
        for path in [tmp_path / Path(artifact_path).relative_to(tmp_path)]
    }
    second = run_reread_demo(config)

    assert first.run_id == second.run_id
    assert first.packet_id == "packet_0001"
    assert second.packet_id == "packet_0002"
    assert first.artifact_ids != second.artifact_ids
    assert set(first.artifact_paths.values()).isdisjoint(set(second.artifact_paths.values()))
    assert first.payloads == second.payloads

    for artifact_type, artifact_path in first_paths.items():
        path = tmp_path / Path(artifact_path).relative_to(tmp_path)
        assert path.is_file()
        assert path.read_text(encoding="utf-8") == first_file_contents[artifact_type]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, first.run_id)
    reread_artifacts = [artifact for artifact in artifacts if artifact.type in REREAD_ARTIFACT_TYPES]
    assert len(reread_artifacts) == len(REREAD_ARTIFACT_TYPES) * 2


def test_reread_demo_preserves_finalization_refusal(tmp_path):
    config = config_for(tmp_path)
    result = run_reread_demo(config)

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=result.run_id)

    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
    assert report.failed_gates == []
