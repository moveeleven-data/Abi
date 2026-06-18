import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.gates import list_gates
from abi.controller.policy import FINAL_ARTIFACT_REQUIRED_GATES, GATE_PROFILE_FINAL_ARTIFACT
from abi.controller.release_readiness import evaluate_release_readiness
from abi.controller.state import get_latest_run
from abi.db import connect
from abi.modules.final_artifact import (
    FINAL_ARTIFACT_ARTIFACT_TYPES,
    FINAL_ARTIFACT_REQUIRED_MODEL_CALLS,
    run_final_artifact_packet,
)


SOURCE_NOTE = """# Source Note

The table is the ordinary object the production scaffold must keep visible. It
stays in a small room while the unseen night supplies pressure.
"""

THEORY_FRAGMENT = """# Theory Fragment

A reread succeeds when the opening sentence has more force after the artifact
has been crossed once.
"""

PROTOCOL = """# Fixture Human Calibration Protocol

This is fixture-only protocol material for deterministic scaffold testing. It is
not a live human study and not real validation.
"""

TRIAL = {
    "fixture_only": True,
    "not_real_validation": True,
    "trial_id": "fixture_trial_001",
    "reader_label": "fixture_reader_alpha",
    "artifact_label": "table_morning_fixture",
    "first_read": {
        "opening_interpretation": "A domestic object remained in place overnight.",
        "retained_images": ["table", "morning light"],
        "predictions": ["the room may reveal what happened at night"],
        "attention_drops": [],
        "confusion": ["why the table matters is not yet clear"],
        "overexplicitness": [],
    },
    "reread": {
        "post_ending_opening_reread": "The opening now reads as evidence.",
        "changed_interpretation": "Still becomes pressure, not rest.",
        "paraphrase_attempt": "The table surviving the night makes the room feel tested.",
        "details_that_gained_force": ["dust square", "morning stops there"],
        "details_that_felt_fake": [],
    },
}

BASELINE = """# Fixture Baseline Direct Prompt

This fixture baseline represents a deterministic comparison target only. It is
not real validation, not a live survey result, and not production generation.
"""


def config_for(tmp_path: Path) -> AbiConfig:
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def write_fixtures(root: Path) -> None:
    production_dir = root / "fixtures" / "production_harness"
    production_dir.mkdir(parents=True, exist_ok=True)
    (production_dir / "source_note.md").write_text(SOURCE_NOTE, encoding="utf-8", newline="\n")
    (production_dir / "theory_fragment.md").write_text(
        THEORY_FRAGMENT,
        encoding="utf-8",
        newline="\n",
    )

    calibration_dir = root / "fixtures" / "human_calibration"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    (calibration_dir / "protocol.md").write_text(PROTOCOL, encoding="utf-8", newline="\n")
    (calibration_dir / "human_reader_trial.json").write_text(
        json.dumps(TRIAL, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (calibration_dir / "baseline_direct_prompt.md").write_text(
        BASELINE,
        encoding="utf-8",
        newline="\n",
    )


def read_payload(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["payload"]


def test_fake_final_artifact_packet_creates_required_scaffold(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_final_artifact_packet(config, client_name="fake")

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert set(result.payload["artifact_ids"]) == set(FINAL_ARTIFACT_ARTIFACT_TYPES)
    assert result.payload["counts"]["final_artifact_artifacts"] == 11
    assert result.payload["counts"]["model_calls"] == FINAL_ARTIFACT_REQUIRED_MODEL_CALLS
    assert Path(result.payload["packet_dir"]) == (
        tmp_path / "runs" / result.payload["run_id"] / "final_artifact" / "packet_0001"
    )

    candidate = read_payload(result.payload["artifact_paths"]["final_artifact_candidate_text"])
    assert candidate["non_final"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["not_finalization_eligible"] is True
    assert candidate["no_phase_shift_claim"] is True
    assert candidate["human_validation_claim"] is False
    assert candidate["phase_shift_claim"] is False

    readiness = read_payload(result.payload["artifact_paths"]["finalization_readiness_report"])
    assert readiness["eligible"] is False
    assert readiness["current_run_ineligible"] is True
    assert readiness["final_artifact_profile_refuses"] is True
    assert "real_human_validation_passed" in readiness["missing_gates"]
    assert readiness["final_gates_marked_passed"] == []

    packet = read_payload(result.payload["artifact_paths"]["final_artifact_packet"])
    assert packet["non_final"] is True
    assert packet["not_human_validated"] is True
    assert packet["not_finalization_eligible"] is True
    assert packet["no_phase_shift_claim"] is True
    assert packet["finalization_eligible"] is False
    assert packet["fixture_or_scaffold_evidence_present"] is True

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        gates = list_gates(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)
        profile_readiness = evaluate_release_readiness(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert latest_run.active_phase == "phase13_final_artifact_packet"
    assert not ({gate.gate_name for gate in gates} & set(FINAL_ARTIFACT_REQUIRED_GATES))
    final_artifacts = {
        artifact.type: artifact
        for artifact in artifacts
        if artifact.type in FINAL_ARTIFACT_ARTIFACT_TYPES
    }
    assert set(final_artifacts) == set(FINAL_ARTIFACT_ARTIFACT_TYPES)
    for artifact in final_artifacts.values():
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["artifact_type"] == artifact.type
        assert envelope["model_call_id"] is None
        assert artifact.parent_ids
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))

    assert profile_readiness.eligible is False
    assert any("final artifact packet" in blocker for blocker in profile_readiness.non_final_blockers)


def test_final_artifact_packet_uses_unique_packet_dirs(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    first = run_final_artifact_packet(config, client_name="fake")
    second = run_final_artifact_packet(config, client_name="fake")

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert set(first.payload["artifact_paths"].values()).isdisjoint(
        set(second.payload["artifact_paths"].values())
    )


def test_openai_final_artifact_packet_refuses_without_allow_before_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_final_artifact_packet(config, client_name="openai")

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert not config.db_path.exists()


def test_openai_final_artifact_packet_refuses_without_key_before_run(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_final_artifact_packet(
        config,
        client_name="openai",
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert not config.db_path.exists()


def test_final_artifact_cli_fake_and_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)

    fake_exit = main(["--root", str(tmp_path), "final-artifact", "packet", "--client", "fake"])
    fake_payload = json.loads(capsys.readouterr().out)

    assert fake_exit == 0
    assert fake_payload["client"] == "fake"
    assert set(fake_payload["artifact_ids"]) == set(FINAL_ARTIFACT_ARTIFACT_TYPES)

    openai_exit = main(["--root", str(tmp_path), "final-artifact", "packet", "--client", "openai"])
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]


def test_final_artifact_packet_preserves_finalization_fail_closed(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_final_artifact_packet(config, client_name="fake")

    with connect(config.db_path) as connection:
        legacy_report = check_finalization(connection, run_id=result.payload["run_id"])
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert legacy_report.refused is True
    assert final_report.refused is True
    assert "real_human_validation_passed" in final_report.missing_gates
    assert final_report.release_readiness is not None
    assert final_report.release_readiness.eligible is False


def test_readme_documents_final_artifact_packet_command():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert r".\.venv\Scripts\abi.exe final-artifact packet --client fake" in readme
