import json
from pathlib import Path

from abi.cli import main
from abi.modules.production_harness import HARNESS_ARTIFACT_TYPES


def write_fixtures(root: Path) -> None:
    fixture_dir = root / "fixtures" / "production_harness"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "source_note.md").write_text(
        """# Table Benchmark Source Note

The table remains the benchmark object because it is ordinary enough to resist
ornament and stable enough to carry causal pressure.

The production harness should preserve the sentence's small room, the unseen
night, and the morning verification without importing a larger plot.
""",
        encoding="utf-8",
        newline="\n",
    )
    (fixture_dir / "theory_fragment.md").write_text(
        """# Reread Theory Fragment

A successful Abi artifact makes the opening sentence change its force after the
reader has crossed the artifact once.

The source kernel should track claims, motifs, images, and risks separately so
later production work can compose from explicit lineage rather than hidden
context.
""",
        encoding="utf-8",
        newline="\n",
    )


def test_harness_demo_cli_outputs_summary(tmp_path, capsys, monkeypatch):
    write_fixtures(tmp_path)
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    exit_code = main(["--root", str(tmp_path), "harness", "demo"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["packet_id"] == "packet_0001"
    assert set(payload["artifact_ids"]) == set(HARNESS_ARTIFACT_TYPES)
    assert payload["packet_artifact_id"] == payload["artifact_ids"]["harness_packet"]
    assert payload["gate_result"]["passed"] is True
    assert Path(payload["fixture_dir"]) == tmp_path / "fixtures" / "production_harness"
    assert Path(payload["packet_dir"]) == (
        tmp_path / "runs" / payload["run_id"] / "harness" / "packet_0001"
    )
    assert Path(payload["packet_dir"]).is_dir()

    assert main(["--root", str(tmp_path), "status"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["latest_run"]["active_phase"] == "phase4_production_harness"


def test_harness_demo_command_remains_available(tmp_path, capsys, monkeypatch):
    write_fixtures(tmp_path)
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "harness", "demo"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["packet_id"] == "packet_0001"
