from abi.config import AbiConfig
from abi.controller.control import decide_run, inspect_active_run
from abi.controller.finalization import check_finalization
from abi.controller.gates import REQUIRED_PHASE0_GATES, record_gate
from abi.controller.state import ensure_active_run
from abi.db import connect
from abi.modules.reread import run_reread_demo


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_missing_required_gates_create_refuse_finalization_decision(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)

    assert decision.to_dict()["run_id"] == run.id
    assert decision.decision == "refuse_finalization"
    assert decision.eligible_to_finalize is False
    assert decision.missing_gates == list(REQUIRED_PHASE0_GATES)
    assert decision.failed_gates == []
    assert decision.blocking_defects == {}
    assert decision.blocker_report.blockers == [
        "missing required gate: infrastructure_initialized",
        "missing required gate: artifact_registry_ready",
        "missing required gate: required_phase0_tests_passed",
    ]


def test_failed_required_gate_refuses_finalization(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        record_gate(connection, run_id=run.id, gate_name="infrastructure_initialized", passed=True)
        record_gate(connection, run_id=run.id, gate_name="artifact_registry_ready", passed=False)
        record_gate(connection, run_id=run.id, gate_name="required_phase0_tests_passed", passed=True)
        decision = inspect_active_run(connection)
        report = check_finalization(connection, run_id=run.id)

    assert decision.decision == "refuse_finalization"
    assert decision.missing_gates == []
    assert decision.failed_gates == ["artifact_registry_ready"]
    assert decision.blocking_defects == {}
    assert report.refused is True
    assert report.failed_gates == ["artifact_registry_ready"]


def test_blocking_defects_refuse_finalization(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        record_gate(connection, run_id=run.id, gate_name="infrastructure_initialized", passed=True)
        record_gate(
            connection,
            run_id=run.id,
            gate_name="artifact_registry_ready",
            passed=True,
            blocking_defects=["registered artifact path is missing"],
        )
        record_gate(connection, run_id=run.id, gate_name="required_phase0_tests_passed", passed=True)
        decision = inspect_active_run(connection)
        report = check_finalization(connection, run_id=run.id)

    assert decision.decision == "refuse_finalization"
    assert decision.eligible_to_finalize is False
    assert decision.missing_gates == []
    assert decision.failed_gates == []
    assert decision.blocking_defects == {
        "artifact_registry_ready": ["registered artifact path is missing"]
    }
    assert decision.blocker_report.blockers == [
        "blocking defects on gate artifact_registry_ready: registered artifact path is missing"
    ]
    assert report.refused is True
    assert report.failed_gates == ["artifact_registry_ready"]


def test_all_required_gates_passing_produces_eligible_decision(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        for gate_name in REQUIRED_PHASE0_GATES:
            record_gate(connection, run_id=run.id, gate_name=gate_name, passed=True)
        active_decision = inspect_active_run(connection)
        direct_decision = decide_run(connection, run=run)
        report = check_finalization(connection, run_id=run.id)

    assert active_decision.decision == "finalize"
    assert direct_decision.eligible_to_finalize is True
    assert direct_decision.missing_gates == []
    assert direct_decision.failed_gates == []
    assert direct_decision.blocking_defects == {}
    assert direct_decision.recommended_next_action == "finalize"
    assert report.refused is False


def test_normal_live_demo_state_still_refuses_finalization(tmp_path):
    config = config_for(tmp_path)
    result = run_reread_demo(config)

    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
        report = check_finalization(connection, run_id=result.run_id)

    assert decision.decision == "refuse_finalization"
    assert decision.eligible_to_finalize is False
    assert decision.active_phase == "phase2_minimal_reread"
    assert decision.missing_gates == list(REQUIRED_PHASE0_GATES)
    assert report.refused is True
