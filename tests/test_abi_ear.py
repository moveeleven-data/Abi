import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.state import PHASE1_ABI_EAR_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.modules.abi_ear import (
    ABI_EAR_ARTIFACT_TYPES,
    BENCHMARK_INPUT,
    build_benchmark_payloads,
    run_abi_ear_demo,
)


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_abi_ear_payloads_are_deterministic():
    first = build_benchmark_payloads(BENCHMARK_INPUT)
    second = build_benchmark_payloads(BENCHMARK_INPUT)

    assert first == second
    assert tuple(first) == ABI_EAR_ARTIFACT_TYPES
    assert len(first["abi_ear_variants"]["variants"]) == 10
    assert len(first["abi_ear_moves"]["moves"]) == 20
    assert len(first["abi_ear_prose_inventions"]["prose_inventions"]) >= 3
    assert first["abi_ear_refined_invention"]["text"].startswith(BENCHMARK_INPUT)
    assert first["abi_ear_gate_report"]["passed"] is True


def test_abi_ear_demo_registers_all_artifacts_and_parent_ids(tmp_path):
    config = config_for(tmp_path)

    result = run_abi_ear_demo(config)

    assert set(result.artifact_ids) == set(ABI_EAR_ARTIFACT_TYPES)
    assert result.gate_result["passed"] is True
    assert result.payloads["abi_ear_gate_report"]["passed"] is True

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.run_id)
        latest_run = get_latest_run(connection)

    artifacts_by_type = {artifact.type: artifact for artifact in artifacts}
    assert set(artifacts_by_type) == set(ABI_EAR_ARTIFACT_TYPES)
    assert latest_run.active_phase == PHASE1_ABI_EAR_ACTIVE_PHASE
    assert artifacts_by_type["abi_ear_germ_analysis"].parent_ids == []
    for artifact_type in ABI_EAR_ARTIFACT_TYPES[1:]:
        assert artifacts_by_type[artifact_type].parent_ids
    assert len(artifacts_by_type["abi_ear_packet"].parent_ids) == 10

    for artifact_type, artifact_path in result.artifact_paths.items():
        path = (
            tmp_path
            / "runs"
            / result.run_id
            / "abi_ear"
            / result.packet_id
            / f"{artifact_type}.json"
        )
        assert artifact_path == str(path)
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == result.payloads[artifact_type]


def test_abi_ear_demo_does_not_overwrite_previous_registered_paths(tmp_path):
    config = config_for(tmp_path)

    first = run_abi_ear_demo(config)
    first_paths = dict(first.artifact_paths)
    first_file_contents = {
        artifact_type: path.read_text(encoding="utf-8")
        for artifact_type, artifact_path in first_paths.items()
        for path in [tmp_path / Path(artifact_path).relative_to(tmp_path)]
    }
    second = run_abi_ear_demo(config)

    assert first.run_id == second.run_id
    assert first.packet_id == "packet_0001"
    assert second.packet_id == "packet_0002"
    assert first.artifact_ids != second.artifact_ids
    assert set(first.artifact_paths) == set(second.artifact_paths)
    assert set(first.artifact_paths.values()).isdisjoint(set(second.artifact_paths.values()))
    assert first.payloads == second.payloads

    for artifact_type, artifact_path in first_paths.items():
        path = tmp_path / Path(artifact_path).relative_to(tmp_path)
        assert path.is_file()
        assert path.read_text(encoding="utf-8") == first_file_contents[artifact_type]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, first.run_id)
    assert len(artifacts) == len(ABI_EAR_ARTIFACT_TYPES) * 2
