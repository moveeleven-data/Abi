import json

from abi.cli import main
from abi.config import AbiConfig
from abi.controller.state import ensure_active_run
from abi.db import connect, get_counts


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_init_creates_database_and_run_folders(tmp_path):
    config = config_for(tmp_path)

    run, created = ensure_active_run(config)

    assert created is True
    assert config.db_path.exists()
    assert config.run_dir(run.id).is_dir()
    assert config.output_dir(run.id).is_dir()
    with connect(config.db_path) as connection:
        counts = get_counts(connection)
    assert counts == {"runs": 1, "artifacts": 0, "gates": 0}


def test_init_reports_existing_active_run(tmp_path):
    config = config_for(tmp_path)
    first_run, first_created = ensure_active_run(config)

    second_run, second_created = ensure_active_run(config)

    assert first_created is True
    assert second_created is False
    assert second_run.id == first_run.id


def test_cli_init_and_status_report_current_state(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "init"]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["created_run"] is True
    assert init_payload["active_run_id"].startswith("run_")

    assert main(["--root", str(tmp_path), "status"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["database_path"] == str(tmp_path / "db" / "abi.sqlite")
    assert status_payload["run_count"] == 1
    assert status_payload["latest_run"]["id"] == init_payload["active_run_id"]
    assert status_payload["artifact_count"] == 0
    assert status_payload["gate_count"] == 0
