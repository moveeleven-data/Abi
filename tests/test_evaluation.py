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
)
from abi.model_schemas import EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA
from abi.model_schemas import EVALUATION_BEST_OF_N_BASELINE_SCHEMA
from abi.modules.evaluation import (
    EVALUATION_ARTIFACT_TYPES,
    EVALUATION_REQUIRED_MODEL_CALLS,
    run_evaluation_demo,
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


def read_envelope(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_fake_evaluation_demo_creates_required_packet(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_evaluation_demo(config, client_name="fake")

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert set(result.payload["artifact_ids"]) == set(EVALUATION_ARTIFACT_TYPES)
    assert result.payload["counts"]["model_calls"] == EVALUATION_REQUIRED_MODEL_CALLS
    assert result.payload["human_trace"]["fixture_only"] is True
    assert result.payload["human_trace"]["not_real_validation"] is True
    assert result.payload["candidate_flags"]["non_final"] is True
    assert result.payload["candidate_flags"]["not_human_validated"] is True
    assert result.payload["candidate_flags"]["not_finalization_eligible"] is True
    assert result.payload["candidate_flags"]["finalization_eligible"] is False
    assert result.payload["candidate_flags"]["human_validation_claim"] is False
    assert result.payload["candidate_flags"]["phase_shift_claim"] is False
    assert result.payload["baseline_flags"]["direct_prompt_fixture_only"] is True
    assert result.payload["baseline_flags"]["direct_prompt_not_real_validation"] is True
    assert result.payload["baseline_flags"]["best_of_n_fixture_only"] is True
    assert result.payload["baseline_flags"]["best_of_n_not_real_validation"] is True

    model_calls = result.payload["model_calls"]
    assert len(model_calls) == 2
    assert {call["status"] for call in model_calls} == {MODEL_CALL_SUCCESS}
    assert all(call["parsed_output_artifact_id"] for call in model_calls)

    model_artifact_types = {
        "evaluation_best_of_n_baseline_summary",
        "evaluation_baseline_comparison_report",
    }
    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)

    assert latest_run.active_phase == "phase11_evaluation_baselines"
    evaluation_artifacts = {
        artifact.type: artifact for artifact in artifacts if artifact.type in EVALUATION_ARTIFACT_TYPES
    }
    assert set(evaluation_artifacts) == set(EVALUATION_ARTIFACT_TYPES)
    for artifact_type, artifact in evaluation_artifacts.items():
        envelope = read_envelope(artifact.path)
        assert envelope["artifact_type"] == artifact_type
        assert artifact.parent_ids
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))
        if artifact_type in model_artifact_types:
            assert envelope["model_call_id"] is not None
        else:
            assert envelope["model_call_id"] is None

    packet = read_envelope(result.payload["artifact_paths"]["evaluation_packet"])["payload"]
    assert packet["finalization_eligible"] is False
    assert "no phase-shift claim" in packet["claims_not_made"]
    assert packet["counts"]["evaluation_artifacts"] == len(EVALUATION_ARTIFACT_TYPES)


def test_fake_evaluation_demo_is_deterministic_and_uses_unique_packet_dirs(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    first = run_evaluation_demo(config, client_name="fake")
    second = run_evaluation_demo(config, client_name="fake")

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert first.payload["counts"] == second.payload["counts"]
    assert set(first.payload["artifact_paths"].values()).isdisjoint(
        set(second.payload["artifact_paths"].values())
    )
    first_subject = read_envelope(first.payload["artifact_paths"]["evaluation_subject"])["payload"]
    second_subject = read_envelope(second.payload["artifact_paths"]["evaluation_subject"])["payload"]
    assert first_subject["candidate_id"] == second_subject["candidate_id"]


def test_evaluation_budget_guard_refuses_before_run(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_evaluation_demo(
        config,
        client_name="fake",
        max_model_calls=EVALUATION_REQUIRED_MODEL_CALLS - 1,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "max-model-calls" in result.payload["message"]
    assert not config.db_path.exists()


def test_fake_evaluation_invalid_output_records_failure_without_packet(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_evaluation_demo(
        config,
        client_name="fake",
        fake_mode="invalid",
        fake_target_schema=EVALUATION_BEST_OF_N_BASELINE_SCHEMA,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "evaluation_best_of_n_baseline_summary" not in result.payload["artifact_ids"]
    assert "evaluation_packet" not in result.payload["artifact_ids"]


def test_fake_evaluation_client_failure_records_failure_without_packet(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_evaluation_demo(
        config,
        client_name="fake",
        fake_mode="failure",
        fake_target_schema=EVALUATION_BASELINE_COMPARISON_REPORT_SCHEMA,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["status"] == MODEL_CALL_CLIENT_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "simulated fake evaluation client failure" in failed_call["error_message"]
    assert "evaluation_baseline_comparison_report" not in result.payload["artifact_ids"]
    assert "evaluation_packet" not in result.payload["artifact_ids"]


def test_openai_evaluation_refuses_without_allow_before_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_evaluation_demo(config, client_name="openai")

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert not config.db_path.exists()


def test_openai_evaluation_refuses_without_key_before_run(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)
    config = config_for(tmp_path)

    result = run_evaluation_demo(
        config,
        client_name="openai",
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert not config.db_path.exists()


def test_evaluation_cli_fake_and_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)

    fake_exit = main(["--root", str(tmp_path), "evaluation", "demo", "--client", "fake"])
    fake_payload = json.loads(capsys.readouterr().out)

    assert fake_exit == 0
    assert fake_payload["client"] == "fake"
    assert fake_payload["counts"]["model_calls"] == EVALUATION_REQUIRED_MODEL_CALLS

    openai_exit = main(["--root", str(tmp_path), "evaluation", "demo", "--client", "openai"])
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]


def test_readme_documents_evaluation_demo_command():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert r".\.venv\Scripts\abi.exe evaluation demo --client fake" in readme


def test_fake_evaluation_preserves_finalization_fail_closed(tmp_path):
    write_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_evaluation_demo(config, client_name="fake")

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=result.payload["run_id"])

    assert report.refused is True
    assert report.missing_gates == [
        "infrastructure_initialized",
        "artifact_registry_ready",
        "required_phase0_tests_passed",
    ]
