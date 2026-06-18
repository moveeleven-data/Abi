from abi.config import AbiConfig
from abi.controller.gates import get_gate, record_gate, required_gate_records
from abi.controller.state import ensure_active_run
from abi.db import connect, get_counts


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_record_gate_stores_and_queries_result(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        gate = record_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
            passed=False,
            blocking_defects=["db not initialized"],
        )
        stored = get_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
        )

    assert gate.id.startswith("gate_")
    assert stored == gate
    assert stored.passed is False
    assert stored.blocking_defects == ["db not initialized"]


def test_gate_record_can_be_updated_without_duplicates(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        first = record_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
            passed=False,
            blocking_defects=["missing"],
        )
        second = record_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
            passed=True,
            blocking_defects=[],
        )
        stored = get_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
        )
        counts = get_counts(connection)

    assert second.id == first.id
    assert stored == second
    assert counts["gates"] == 1


def test_required_gate_records_reports_missing_gates(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        record_gate(
            connection,
            run_id=run.id,
            gate_name="infrastructure_initialized",
            passed=True,
        )
        gates = required_gate_records(connection, run_id=run.id)

    assert gates["infrastructure_initialized"] is not None
    assert gates["artifact_registry_ready"] is None
    assert gates["required_phase0_tests_passed"] is None
