import json

from abi.cli import main
from abi.controller.gates import REQUIRED_PHASE0_GATES


def test_controller_demo_emits_structured_decision(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    exit_code = main(["--root", str(tmp_path), "controller", "demo"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["run_id"].startswith("run_")
    assert payload["decision"] == "refuse_finalization"
    assert payload["eligible_to_finalize"] is False
    assert payload["missing_gates"] == list(REQUIRED_PHASE0_GATES)
    assert payload["failed_gates"] == []
    assert payload["blocking_defects"] == {}
    assert payload["blocker_report"]["recommended_next_action"] == (
        "resolve required gate blockers before finalization"
    )


def test_controller_status_and_blockers_emit_valid_json(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "controller", "demo"]) == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "controller", "status"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["decision"] == "refuse_finalization"
    assert status_payload["blocker_report"]["missing_gates"] == list(REQUIRED_PHASE0_GATES)

    assert main(["--root", str(tmp_path), "controller", "blockers"]) == 0
    blockers_payload = json.loads(capsys.readouterr().out)
    assert blockers_payload["missing_gates"] == list(REQUIRED_PHASE0_GATES)
    assert blockers_payload["failed_gates"] == []
    assert blockers_payload["blockers"]


def test_controller_commands_remain_available(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "controller", "demo"]) == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "controller", "status"]) == 0
    assert main(["--root", str(tmp_path), "controller", "blockers"]) == 0
