import json

from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.gates import REQUIRED_PHASE0_GATES, record_gate
from abi.controller.state import ensure_active_run
from abi.db import connect


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_missing_required_gates_block_finalization(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        report = check_finalization(connection, run_id=run.id)

    assert report.refused is True
    assert report.run_id == run.id
    assert report.missing_gates == list(REQUIRED_PHASE0_GATES)
    assert report.failed_gates == []
    assert "missing gates" in report.message
    assert "infrastructure_initialized" in report.message


def test_failed_gate_blocks_finalization_with_blocker_report(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        record_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
            passed=True,
        )
        record_gate(
            connection,
            run_id=run.id,
            gate_name="artifact_registry_ready",
            passed=False,
            blocking_defects=["registry fixture not registered"],
        )
        report = check_finalization(connection, run_id=run.id)

    assert report.to_dict() == {
        "run_id": run.id,
        "refused": True,
        "missing_gates": ["required_phase0_tests_passed"],
        "failed_gates": ["artifact_registry_ready"],
        "message": (
            "Finalization refused; missing gates: required_phase0_tests_passed; "
            "failed gates: artifact_registry_ready."
        ),
    }


def test_all_required_gates_satisfy_finalization_check(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        for gate_name in REQUIRED_PHASE0_GATES:
            record_gate(connection, run_id=run.id, gate_name=gate_name, passed=True)
        report = check_finalization(connection, run_id=run.id)

    assert report.refused is False
    assert report.missing_gates == []
    assert report.failed_gates == []


def test_cli_finalize_refuses_missing_gates(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "finalize"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["refused"] is True
    assert payload["missing_gates"] == list(REQUIRED_PHASE0_GATES)
    assert payload["failed_gates"] == []
