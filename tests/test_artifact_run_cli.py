import json

from abi.cli import main


def test_artifact_list_show_and_run_commands(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "ear", "demo"]) == 0
    demo_payload = json.loads(capsys.readouterr().out)
    artifact_id = demo_payload["artifact_ids"]["abi_ear_packet"]
    run_id = demo_payload["run_id"]

    assert main(["--root", str(tmp_path), "artifact", "list"]) == 0
    artifact_list = json.loads(capsys.readouterr().out)
    listed_artifact_ids = {artifact["id"] for artifact in artifact_list["artifacts"]}
    assert artifact_id in listed_artifact_ids

    assert main(["--root", str(tmp_path), "artifact", "show", artifact_id]) == 0
    artifact_show = json.loads(capsys.readouterr().out)
    assert artifact_show["artifact"]["id"] == artifact_id
    assert artifact_show["content"]["schema_version"] == "1"
    assert artifact_show["content"]["artifact_type"] == "abi_ear_packet"
    assert artifact_show["content"]["model_call_id"] is None

    assert main(["--root", str(tmp_path), "run", "list"]) == 0
    run_list = json.loads(capsys.readouterr().out)
    listed_run_ids = {run["id"] for run in run_list["runs"]}
    assert run_id in listed_run_ids

    assert main(["--root", str(tmp_path), "run", "latest"]) == 0
    latest_run = json.loads(capsys.readouterr().out)
    assert latest_run["run"]["id"] == run_id

    assert main(["--root", str(tmp_path), "run", "show", run_id]) == 0
    run_show = json.loads(capsys.readouterr().out)
    assert run_show["run"]["id"] == run_id
    assert run_show["run"]["active_phase"] == "phase1_abi_ear"


def test_artifact_and_run_show_missing_records_return_failure(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "artifact", "show", "artifact_missing"]) == 1
    artifact_show = json.loads(capsys.readouterr().out)
    assert artifact_show["artifact"] is None

    assert main(["--root", str(tmp_path), "run", "show", "run_missing"]) == 1
    run_show = json.loads(capsys.readouterr().out)
    assert run_show["run"] is None
