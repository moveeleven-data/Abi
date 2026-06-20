import json
from pathlib import Path

from abi.cli import main
from abi.modules.reread import REREAD_ARTIFACT_TYPES


def test_reread_demo_cli_outputs_summary(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    exit_code = main(["--root", str(tmp_path), "reread", "demo"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["benchmark_input"] == "The table is still there in the morning."
    assert payload["packet_id"] == "packet_0001"
    assert set(payload["artifact_ids"]) == set(REREAD_ARTIFACT_TYPES)
    assert payload["packet_artifact_id"] == payload["artifact_ids"]["reread_packet"]
    assert payload["gate_result"]["passed"] is True
    assert payload["artifact_ids"]["reread_counterfactual_result"]
    assert Path(payload["packet_dir"]) == (
        tmp_path / "runs" / payload["run_id"] / "reread" / "packet_0001"
    )
    assert Path(payload["packet_dir"]).is_dir()

    assert main(["--root", str(tmp_path), "status"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["latest_run"]["active_phase"] == "phase2_minimal_reread"


def test_reread_demo_command_remains_available(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "reread", "demo"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["packet_id"] == "packet_0001"
