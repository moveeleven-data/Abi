import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.control import inspect_active_run
from abi.controller.finalization import check_finalization
from abi.controller.state import PHASE4_PRODUCTION_HARNESS_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.modules.production_harness import (
    HARNESS_ARTIFACT_TYPES,
    build_production_harness_payloads,
    run_production_harness_demo,
)


SOURCE_NOTE = """# Table Benchmark Source Note

The table remains the benchmark object because it is ordinary enough to resist
ornament and stable enough to carry causal pressure.

The production harness should preserve the sentence's small room, the unseen
night, and the morning verification without importing a larger plot.
"""

THEORY_FRAGMENT = """# Reread Theory Fragment

A successful Abi artifact makes the opening sentence change its force after the
reader has crossed the artifact once.

The source kernel should track claims, motifs, images, and risks separately so
later production work can compose from explicit lineage rather than hidden
context.
"""


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def write_fixtures(root: Path) -> Path:
    fixture_dir = root / "fixtures" / "production_harness"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "source_note.md").write_text(SOURCE_NOTE, encoding="utf-8", newline="\n")
    (fixture_dir / "theory_fragment.md").write_text(
        THEORY_FRAGMENT,
        encoding="utf-8",
        newline="\n",
    )
    return fixture_dir


def test_production_harness_payloads_are_deterministic(tmp_path):
    fixture_dir = write_fixtures(tmp_path)

    first = build_production_harness_payloads(fixture_dir)
    second = build_production_harness_payloads(fixture_dir)

    assert first == second
    assert tuple(first) == HARNESS_ARTIFACT_TYPES
    assert first["harness_source_manifest"]["source_count"] == 2
    assert len(first["harness_claim_cards"]["claim_cards"]) == 4
    assert len(first["harness_motif_cards"]["motif_cards"]) == 4
    assert len(first["harness_image_cards"]["image_cards"]) == 3
    assert len(first["harness_risk_cards"]["risk_cards"]) == 3
    assert first["harness_gate_report"]["passed"] is True


def test_harness_demo_registers_all_artifacts_and_parent_ids(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_production_harness_demo(config)

    assert set(result.artifact_ids) == set(HARNESS_ARTIFACT_TYPES)
    assert result.gate_result["passed"] is True
    assert result.payloads["harness_gate_report"]["passed"] is True

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.run_id)
        latest_run = get_latest_run(connection)

    harness_artifacts = {
        artifact.type: artifact for artifact in artifacts if artifact.type in HARNESS_ARTIFACT_TYPES
    }
    assert set(harness_artifacts) == set(HARNESS_ARTIFACT_TYPES)
    assert latest_run.active_phase == PHASE4_PRODUCTION_HARNESS_ACTIVE_PHASE
    assert harness_artifacts["harness_source_manifest"].parent_ids == []
    for artifact_type in HARNESS_ARTIFACT_TYPES[1:]:
        assert harness_artifacts[artifact_type].parent_ids
    assert len(harness_artifacts["harness_packet"].parent_ids) == 10

    for artifact_type, artifact_path in result.artifact_paths.items():
        path = (
            tmp_path
            / "runs"
            / result.run_id
            / "harness"
            / result.packet_id
            / f"{artifact_type}.json"
        )
        assert artifact_path == str(path)
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == result.payloads[artifact_type]


def test_harness_demo_packet_directory_is_unique_per_invocation(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    first = run_production_harness_demo(config)
    first_paths = dict(first.artifact_paths)
    first_file_contents = {
        artifact_type: path.read_text(encoding="utf-8")
        for artifact_type, artifact_path in first_paths.items()
        for path in [tmp_path / Path(artifact_path).relative_to(tmp_path)]
    }
    second = run_production_harness_demo(config)

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
    harness_artifacts = [artifact for artifact in artifacts if artifact.type in HARNESS_ARTIFACT_TYPES]
    assert len(harness_artifacts) == len(HARNESS_ARTIFACT_TYPES) * 2


def test_harness_demo_preserves_controller_and_finalization_refusal(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_production_harness_demo(config)

    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
        report = check_finalization(connection, run_id=result.run_id)

    assert decision.decision == "refuse_finalization"
    assert decision.active_phase == PHASE4_PRODUCTION_HARNESS_ACTIVE_PHASE
    assert decision.eligible_to_finalize is False
    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
