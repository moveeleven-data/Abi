import json
from pathlib import Path

from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.gates import record_gate
from abi.controller.policy import (
    AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES,
    FINAL_ARTIFACT_REQUIRED_GATES,
    GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
    GATE_PROFILE_CANDIDATE_RELEASE,
    GATE_PROFILE_FINAL_ARTIFACT,
    GATE_PROFILE_INFRASTRUCTURE,
    gate_catalog_to_dict,
)
from abi.controller.release_readiness import evaluate_release_readiness
from abi.controller.state import ensure_active_run
from abi.db import connect


HUMAN_OR_PUBLIC_GATES = {
    "real_human_validation_passed",
    "human_trace_import",
    "human_reader_data",
    "paper_evidence",
    "public_validation",
    "paper_grade_validation",
    "final_paper_approval",
}


def config_for(tmp_path: Path) -> AbiConfig:
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_gate_catalog_exposes_autonomous_profile() -> None:
    catalog = gate_catalog_to_dict()

    assert set(catalog["profiles"]) == {
        GATE_PROFILE_INFRASTRUCTURE,
        GATE_PROFILE_CANDIDATE_RELEASE,
        GATE_PROFILE_FINAL_ARTIFACT,
        GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
    }
    autonomous_profile = catalog["profiles"][GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE]
    assert autonomous_profile["required_gates"] == list(
        AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES
    )
    assert not (
        set(AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES) & HUMAN_OR_PUBLIC_GATES
    )
    assert "real_human_validation_passed" in FINAL_ARTIFACT_REQUIRED_GATES


def test_gate_list_and_finalization_status_cli_emit_internal_blockers(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "gate", "list"]) == 0
    gate_payload = json.loads(capsys.readouterr().out)
    assert GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE in gate_payload["profiles"]

    assert main(["--root", str(tmp_path), "finalization", "status"]) == 0
    default_payload = json.loads(capsys.readouterr().out)
    assert default_payload["profile"] == GATE_PROFILE_INFRASTRUCTURE
    assert default_payload["eligible"] is False
    assert "infrastructure_initialized" in default_payload["missing_gates"]

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "finalization",
                "status",
                "--profile",
                GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
            ]
        )
        == 0
    )
    autonomous_payload = json.loads(capsys.readouterr().out)
    assert autonomous_payload["profile"] == GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
    assert autonomous_payload["eligible"] is False
    assert autonomous_payload["missing_gates"] == list(
        AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES
    )
    assert "autonomous_candidate_packet_exists" in autonomous_payload["missing_gates"]
    blocker_text = json.dumps(autonomous_payload["blockers"]).lower()
    assert "human" not in blocker_text
    assert "paper" not in blocker_text
    assert "public" not in blocker_text


def test_autonomous_profile_refuses_missing_internal_gates(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        readiness = evaluate_release_readiness(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
        report = check_finalization(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert readiness.eligible is False
    assert report.refused is True
    assert readiness.missing_gates == list(AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES)
    assert "autonomous_candidate_packet_exists" in report.missing_gates
    assert "Finalization refused for profile autonomous_creative_candidate" in report.message
    assert "real_human_validation_passed" not in report.message
    assert "paper" not in report.message.lower()
    assert "public" not in report.message.lower()


def test_failed_autonomous_gate_refuses_finalization(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        for gate_name in AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES:
            record_gate(
                connection,
                run_id=run.id,
                gate_name=gate_name,
                passed=gate_name != "hostile_reader_report_exists",
            )
        report = check_finalization(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert report.refused is True
    assert report.missing_gates == []
    assert report.failed_gates == ["hostile_reader_report_exists"]


def test_controlled_autonomous_profile_can_become_eligible(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        for gate_name in AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES:
            record_gate(connection, run_id=run.id, gate_name=gate_name, passed=True)
        readiness = evaluate_release_readiness(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
        report = check_finalization(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert readiness.eligible is True
    assert readiness.fixture_only_blockers == []
    assert readiness.non_final_blockers == []
    assert readiness.artifact_blockers == []
    assert "internally eligible" in readiness.recommended_next_action
    assert report.refused is False


def test_legacy_final_artifact_profile_remains_external_and_fail_closed(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "finalize", "--profile", "final_artifact"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["refused"] is True
    assert payload["profile"] == GATE_PROFILE_FINAL_ARTIFACT
    assert "final_artifact_packet_exists" in payload["missing_gates"]
    assert "real_human_validation_passed" in payload["missing_gates"]
    assert any("no final artifact packet" in blocker for blocker in payload["artifact_blockers"])
