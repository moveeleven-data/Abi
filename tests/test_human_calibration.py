import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.control import inspect_active_run
from abi.controller.finalization import check_finalization
from abi.controller.state import PHASE5_HUMAN_CALIBRATION_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.modules.human_calibration import (
    CALIBRATION_ARTIFACT_TYPES,
    build_human_calibration_payloads,
    run_human_calibration_demo,
)


PROTOCOL = """# Fixture Human Calibration Protocol

This is fixture-only protocol material for deterministic scaffold testing. It is
not real validation and does not describe collected live human data.

Readers would report first-read memory, opening interpretation, retained images,
predictions, attention drops, confusion, overexplicitness, post-ending opening
reread, changed interpretation, paraphrase attempt, details that gained force,
and details that felt fake.
"""

TRIAL = {
    "fixture_only": True,
    "not_real_validation": True,
    "trial_id": "fixture_trial_001",
    "reader_label": "fixture_reader_alpha",
    "artifact_label": "table_morning_fixture",
    "first_read": {
        "opening_interpretation": "A domestic object remained in place overnight.",
        "retained_images": ["table", "morning light", "cup ring"],
        "predictions": ["the room may reveal what happened at night"],
        "attention_drops": ["direct explanation of still felt early"],
        "confusion": ["why the table matters is not yet clear"],
        "overexplicitness": ["naming the changed word reduces discovery"],
    },
    "reread": {
        "post_ending_opening_reread": (
            "The opening now reads as evidence that something could have taken the table."
        ),
        "changed_interpretation": "Still becomes pressure, not rest.",
        "paraphrase_attempt": "The table surviving the night makes the room feel tested.",
        "details_that_gained_force": ["dust square", "cup ring", "morning stops there"],
        "details_that_felt_fake": [],
    },
}

BASELINE = """# Fixture Baseline Direct Prompt

This fixture baseline represents a deterministic comparison target only. It is
not real validation, not a live survey result, and not production generation.

Baseline text:

The table is still there in the morning because it symbolizes memory. The room
is quiet, and the reader understands that the table means permanence.
"""


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def write_fixtures(root: Path) -> Path:
    fixture_dir = root / "fixtures" / "human_calibration"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "protocol.md").write_text(PROTOCOL, encoding="utf-8", newline="\n")
    (fixture_dir / "human_reader_trial.json").write_text(
        json.dumps(TRIAL, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (fixture_dir / "baseline_direct_prompt.md").write_text(
        BASELINE,
        encoding="utf-8",
        newline="\n",
    )
    return fixture_dir


def test_human_calibration_payloads_are_deterministic_and_marked_fixture(tmp_path):
    fixture_dir = write_fixtures(tmp_path)

    first = build_human_calibration_payloads(fixture_dir)
    second = build_human_calibration_payloads(fixture_dir)

    assert first == second
    assert tuple(first) == CALIBRATION_ARTIFACT_TYPES
    assert first["calibration_gate_report"]["passed"] is True
    assert first["calibration_reader_state_transition"]["changed_opening_interpretation"]
    assert first["calibration_packet"]["not_real_validation"] is True
    assert first["calibration_evaluation_report"]["claims_not_made"] == [
        "no validated human success",
        "no live survey result",
        "no statistical inference",
    ]
    for payload in first.values():
        assert payload["fixture_only"] is True
        assert payload["not_real_validation"] is True


def test_calibration_demo_registers_all_artifacts_and_parent_ids(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_human_calibration_demo(config)

    assert set(result.artifact_ids) == set(CALIBRATION_ARTIFACT_TYPES)
    assert result.gate_result["passed"] is True
    assert result.gate_result["not_real_validation"] is True

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.run_id)
        latest_run = get_latest_run(connection)

    calibration_artifacts = {
        artifact.type: artifact for artifact in artifacts if artifact.type in CALIBRATION_ARTIFACT_TYPES
    }
    assert set(calibration_artifacts) == set(CALIBRATION_ARTIFACT_TYPES)
    assert latest_run.active_phase == PHASE5_HUMAN_CALIBRATION_ACTIVE_PHASE
    assert calibration_artifacts["calibration_protocol"].parent_ids == []
    for artifact_type in CALIBRATION_ARTIFACT_TYPES[1:]:
        assert calibration_artifacts[artifact_type].parent_ids
    assert len(calibration_artifacts["calibration_packet"].parent_ids) == 10

    for artifact_type, artifact_path in result.artifact_paths.items():
        path = (
            tmp_path
            / "runs"
            / result.run_id
            / "calibration"
            / result.packet_id
            / f"{artifact_type}.json"
        )
        assert artifact_path == str(path)
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == result.payloads[artifact_type]


def test_calibration_demo_packet_directory_is_unique_per_invocation(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    first = run_human_calibration_demo(config)
    first_paths = dict(first.artifact_paths)
    first_file_contents = {
        artifact_type: path.read_text(encoding="utf-8")
        for artifact_type, artifact_path in first_paths.items()
        for path in [tmp_path / Path(artifact_path).relative_to(tmp_path)]
    }
    second = run_human_calibration_demo(config)

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
    calibration_artifacts = [
        artifact for artifact in artifacts if artifact.type in CALIBRATION_ARTIFACT_TYPES
    ]
    assert len(calibration_artifacts) == len(CALIBRATION_ARTIFACT_TYPES) * 2


def test_calibration_demo_preserves_controller_and_finalization_refusal(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_human_calibration_demo(config)

    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
        report = check_finalization(connection, run_id=result.run_id)

    assert decision.decision == "refuse_finalization"
    assert decision.active_phase == PHASE5_HUMAN_CALIBRATION_ACTIVE_PHASE
    assert decision.eligible_to_finalize is False
    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
