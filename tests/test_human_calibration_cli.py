import json
from pathlib import Path

from abi.cli import main
from abi.modules.human_calibration import CALIBRATION_ARTIFACT_TYPES


def write_fixtures(root: Path) -> None:
    fixture_dir = root / "fixtures" / "human_calibration"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "protocol.md").write_text(
        """# Fixture Human Calibration Protocol

This is fixture-only protocol material for deterministic scaffold testing. It is
not real validation and does not describe collected live human data.

Readers would report first-read memory, opening interpretation, retained images,
predictions, attention drops, confusion, overexplicitness, post-ending opening
reread, changed interpretation, paraphrase attempt, details that gained force,
and details that felt fake.
""",
        encoding="utf-8",
        newline="\n",
    )
    (fixture_dir / "human_reader_trial.json").write_text(
        json.dumps(
            {
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
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (fixture_dir / "baseline_direct_prompt.md").write_text(
        """# Fixture Baseline Direct Prompt

This fixture baseline represents a deterministic comparison target only. It is
not real validation, not a live survey result, and not production generation.

Baseline text:

The table is still there in the morning because it symbolizes memory. The room
is quiet, and the reader understands that the table means permanence.
""",
        encoding="utf-8",
        newline="\n",
    )


def test_calibration_demo_cli_outputs_summary(tmp_path, capsys, monkeypatch):
    write_fixtures(tmp_path)
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    exit_code = main(["--root", str(tmp_path), "calibration", "demo"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["packet_id"] == "packet_0001"
    assert set(payload["artifact_ids"]) == set(CALIBRATION_ARTIFACT_TYPES)
    assert payload["packet_artifact_id"] == payload["artifact_ids"]["calibration_packet"]
    assert payload["gate_result"]["passed"] is True
    assert payload["fixture_only"] is True
    assert payload["not_real_validation"] is True
    assert Path(payload["fixture_dir"]) == tmp_path / "fixtures" / "human_calibration"
    assert Path(payload["packet_dir"]) == (
        tmp_path / "runs" / payload["run_id"] / "calibration" / "packet_0001"
    )
    assert Path(payload["packet_dir"]).is_dir()

    assert main(["--root", str(tmp_path), "status"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["latest_run"]["active_phase"] == "phase5_human_calibration"


def test_readme_documents_calibration_demo_command():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert r".\.venv\Scripts\abi.exe calibration demo" in readme
