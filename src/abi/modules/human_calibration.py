"""Deterministic Phase 5 human calibration scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from abi.artifacts import ArtifactRecord, get_artifact, register_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import PHASE5_HUMAN_CALIBRATION_ACTIVE_PHASE, ensure_active_run
from abi.controller.state import set_active_phase
from abi.db import connect
from abi.hashing import sha256_file
from abi.ids import artifact_id as make_artifact_id


CALIBRATION_LINEAGE_ID = "human_calibration_v1_fixture"
CALIBRATION_GATE_NAME = "human_calibration_v1_fixture"
FIXTURE_RELATIVE_DIR = Path("fixtures") / "human_calibration"

CALIBRATION_ARTIFACT_TYPES = (
    "calibration_protocol",
    "calibration_human_reader_trial",
    "calibration_first_read_trace",
    "calibration_reread_trace",
    "calibration_reader_state_transition",
    "calibration_blind_comparison",
    "calibration_baseline_comparison",
    "calibration_summary",
    "calibration_evaluation_report",
    "calibration_gate_report",
    "calibration_packet",
)


@dataclass(frozen=True)
class CalibrationRunResult:
    run_id: str
    packet_id: str
    packet_dir: str
    fixture_dir: str
    artifact_ids: dict[str, str]
    artifact_paths: dict[str, str]
    gate_result: dict[str, object]
    payloads: dict[str, object]
    gate_record: GateRecord

    def to_cli_summary(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "packet_id": self.packet_id,
            "packet_dir": self.packet_dir,
            "fixture_dir": self.fixture_dir,
            "artifact_ids": self.artifact_ids,
            "artifact_paths": self.artifact_paths,
            "gate_result": self.gate_result,
            "packet_artifact_id": self.artifact_ids["calibration_packet"],
            "fixture_only": True,
            "not_real_validation": True,
        }


def run_human_calibration_demo(config: AbiConfig) -> CalibrationRunResult:
    run, _ = ensure_active_run(config)
    fixture_dir = config.root / FIXTURE_RELATIVE_DIR
    output_dir = _next_packet_dir(config.run_dir(run.id) / "calibration")
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads = build_human_calibration_payloads(fixture_dir)
    artifacts: dict[str, ArtifactRecord] = {}

    with connect(config.db_path) as connection:
        set_active_phase(connection, run.id, PHASE5_HUMAN_CALIBRATION_ACTIVE_PHASE)
        artifacts["calibration_protocol"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_protocol",
            payload=payloads["calibration_protocol"],
            parent_ids=[],
        )
        artifacts["calibration_human_reader_trial"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_human_reader_trial",
            payload=payloads["calibration_human_reader_trial"],
            parent_ids=[artifacts["calibration_protocol"].id],
        )
        artifacts["calibration_first_read_trace"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_first_read_trace",
            payload=payloads["calibration_first_read_trace"],
            parent_ids=[artifacts["calibration_human_reader_trial"].id],
        )
        artifacts["calibration_reread_trace"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_reread_trace",
            payload=payloads["calibration_reread_trace"],
            parent_ids=[artifacts["calibration_human_reader_trial"].id],
        )
        artifacts["calibration_reader_state_transition"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_reader_state_transition",
            payload=payloads["calibration_reader_state_transition"],
            parent_ids=[
                artifacts["calibration_first_read_trace"].id,
                artifacts["calibration_reread_trace"].id,
            ],
        )
        artifacts["calibration_blind_comparison"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_blind_comparison",
            payload=payloads["calibration_blind_comparison"],
            parent_ids=[
                artifacts["calibration_reader_state_transition"].id,
                artifacts["calibration_protocol"].id,
            ],
        )
        artifacts["calibration_baseline_comparison"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_baseline_comparison",
            payload=payloads["calibration_baseline_comparison"],
            parent_ids=[
                artifacts["calibration_reader_state_transition"].id,
                artifacts["calibration_blind_comparison"].id,
            ],
        )
        artifacts["calibration_summary"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_summary",
            payload=payloads["calibration_summary"],
            parent_ids=[
                artifacts["calibration_reader_state_transition"].id,
                artifacts["calibration_baseline_comparison"].id,
            ],
        )
        artifacts["calibration_evaluation_report"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_evaluation_report",
            payload=payloads["calibration_evaluation_report"],
            parent_ids=[
                artifacts["calibration_summary"].id,
                artifacts["calibration_blind_comparison"].id,
                artifacts["calibration_baseline_comparison"].id,
            ],
        )
        artifacts["calibration_gate_report"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_gate_report",
            payload=payloads["calibration_gate_report"],
            parent_ids=[
                artifacts["calibration_protocol"].id,
                artifacts["calibration_reader_state_transition"].id,
                artifacts["calibration_evaluation_report"].id,
            ],
        )
        gate_report = payloads["calibration_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=run.id,
            gate_name=CALIBRATION_GATE_NAME,
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=CALIBRATION_LINEAGE_ID,
        )
        artifacts["calibration_packet"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="calibration_packet",
            payload=payloads["calibration_packet"],
            parent_ids=[
                artifacts[artifact_type].id for artifact_type in CALIBRATION_ARTIFACT_TYPES[:-1]
            ],
        )

    return CalibrationRunResult(
        run_id=run.id,
        packet_id=output_dir.name,
        packet_dir=str(output_dir),
        fixture_dir=str(fixture_dir),
        artifact_ids={artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        artifact_paths={artifact_type: artifact.path for artifact_type, artifact in artifacts.items()},
        gate_result={
            "gate_name": CALIBRATION_GATE_NAME,
            "passed": bool(payloads["calibration_gate_report"]["passed"]),
            "blocking_defects": list(payloads["calibration_gate_report"]["blocking_defects"]),
            "summary_verdict": payloads["calibration_gate_report"]["summary_verdict"],
            "fixture_only": True,
            "not_real_validation": True,
        },
        payloads=payloads,
        gate_record=gate_record,
    )


def build_human_calibration_payloads(fixture_dir: Path | str) -> dict[str, object]:
    fixtures = read_calibration_fixtures(Path(fixture_dir))
    protocol = build_calibration_protocol(fixtures)
    trial = build_human_reader_trial(fixtures, protocol)
    first_read_trace = build_first_read_trace(trial)
    reread_trace = build_reread_trace(trial)
    transition = build_reader_state_transition(first_read_trace, reread_trace)
    blind_comparison = build_blind_comparison(trial, transition)
    baseline_comparison = build_baseline_comparison(fixtures, transition, blind_comparison)
    summary = build_calibration_summary(transition, blind_comparison, baseline_comparison)
    evaluation_report = build_evaluation_report(protocol, trial, transition, summary)
    gate_report = evaluate_calibration_gate(
        protocol=protocol,
        trial=trial,
        first_read_trace=first_read_trace,
        reread_trace=reread_trace,
        transition=transition,
        blind_comparison=blind_comparison,
        baseline_comparison=baseline_comparison,
        summary=summary,
        evaluation_report=evaluation_report,
    )
    packet = build_calibration_packet_summary(protocol, trial, transition, gate_report)
    return {
        "calibration_protocol": protocol,
        "calibration_human_reader_trial": trial,
        "calibration_first_read_trace": first_read_trace,
        "calibration_reread_trace": reread_trace,
        "calibration_reader_state_transition": transition,
        "calibration_blind_comparison": blind_comparison,
        "calibration_baseline_comparison": baseline_comparison,
        "calibration_summary": summary,
        "calibration_evaluation_report": evaluation_report,
        "calibration_gate_report": gate_report,
        "calibration_packet": packet,
    }


def read_calibration_fixtures(fixture_dir: Path) -> dict[str, object]:
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"Human calibration fixture directory not found: {fixture_dir}")

    protocol_path = fixture_dir / "protocol.md"
    trial_path = fixture_dir / "human_reader_trial.json"
    baseline_path = fixture_dir / "baseline_direct_prompt.md"
    for path in (protocol_path, trial_path, baseline_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing human calibration fixture: {path}")

    return {
        "protocol_path": str(protocol_path),
        "protocol_text": protocol_path.read_text(encoding="utf-8"),
        "protocol_sha256": sha256_file(protocol_path),
        "trial_path": str(trial_path),
        "trial": json.loads(trial_path.read_text(encoding="utf-8")),
        "trial_sha256": sha256_file(trial_path),
        "baseline_path": str(baseline_path),
        "baseline_text": baseline_path.read_text(encoding="utf-8"),
        "baseline_sha256": sha256_file(baseline_path),
    }


def build_calibration_protocol(fixtures: dict[str, object]) -> dict[str, object]:
    return {
        "worker": "calibration_protocol_builder_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "source_path": fixtures["protocol_path"],
        "source_sha256": fixtures["protocol_sha256"],
        "protocol_scope": "deterministic scaffold for future human-reader evaluation",
        "required_reader_reports": [
            "first-read memory",
            "opening interpretation",
            "retained images",
            "predictions",
            "attention drops",
            "confusion",
            "overexplicitness",
            "post-ending opening reread",
            "changed interpretation",
            "paraphrase attempt",
            "details that gained force",
            "details that felt fake",
        ],
        "fixture_disclaimer": "Fixture records are not live human validation.",
    }


def build_human_reader_trial(
    fixtures: dict[str, object],
    protocol: dict[str, object],
) -> dict[str, object]:
    trial = fixtures["trial"]
    return {
        "worker": "human_reader_trial_fixture_loader_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "source_path": fixtures["trial_path"],
        "source_sha256": fixtures["trial_sha256"],
        "trial_id": trial["trial_id"],
        "reader_label": trial["reader_label"],
        "artifact_label": trial["artifact_label"],
        "protocol_report_fields": protocol["required_reader_reports"],
        "first_read": trial["first_read"],
        "reread": trial["reread"],
    }


def build_first_read_trace(trial: dict[str, object]) -> dict[str, object]:
    first_read = trial["first_read"]
    return {
        "worker": "calibration_first_read_tracer_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "trial_id": trial["trial_id"],
        "opening_interpretation": first_read["opening_interpretation"],
        "retained_images": first_read["retained_images"],
        "predictions": first_read["predictions"],
        "attention_drops": first_read["attention_drops"],
        "confusion": first_read["confusion"],
        "overexplicitness": first_read["overexplicitness"],
    }


def build_reread_trace(trial: dict[str, object]) -> dict[str, object]:
    reread = trial["reread"]
    return {
        "worker": "calibration_reread_tracer_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "trial_id": trial["trial_id"],
        "post_ending_opening_reread": reread["post_ending_opening_reread"],
        "changed_interpretation": reread["changed_interpretation"],
        "paraphrase_attempt": reread["paraphrase_attempt"],
        "details_that_gained_force": reread["details_that_gained_force"],
        "details_that_felt_fake": reread["details_that_felt_fake"],
    }


def build_reader_state_transition(
    first_read_trace: dict[str, object],
    reread_trace: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "reader_state_transition_builder_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "before_state": {
            "opening_interpretation": first_read_trace["opening_interpretation"],
            "retained_images": first_read_trace["retained_images"],
            "confusion": first_read_trace["confusion"],
        },
        "after_state": {
            "opening_interpretation": reread_trace["post_ending_opening_reread"],
            "changed_interpretation": reread_trace["changed_interpretation"],
            "details_that_gained_force": reread_trace["details_that_gained_force"],
        },
        "changed_opening_interpretation": reread_trace["changed_interpretation"],
        "newly_connected_fragments": [
            "table",
            "morning light",
            "cup ring",
            "dust square",
        ],
        "motif_role_changes": {
            "table": "from domestic object to evidence",
            "still": "from duration to pressure",
            "morning": "from setting to verification",
        },
        "paraphrase_loss": "The fixture paraphrase loses the exact pressure of still.",
        "unsupported_depth_flags": [],
    }


def build_blind_comparison(
    trial: dict[str, object],
    transition: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "blind_comparison_fixture_builder_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "comparison_id": "fixture_blind_comparison_001",
        "artifact_labels_hidden": True,
        "candidate_a": {
            "label": "artifact_a",
            "source": "abi_fixture_candidate",
            "observed_transition": transition["changed_opening_interpretation"],
        },
        "candidate_b": {
            "label": "artifact_b",
            "source": "baseline_fixture_candidate",
            "observed_transition": "reader recognizes stated symbolism without delayed reread gain",
        },
        "fixture_preference": "artifact_a",
        "basis": "greater reader-state transition in fixture trace",
        "trial_id": trial["trial_id"],
    }


def build_baseline_comparison(
    fixtures: dict[str, object],
    transition: dict[str, object],
    blind_comparison: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "baseline_comparison_fixture_builder_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "baseline_path": fixtures["baseline_path"],
        "baseline_sha256": fixtures["baseline_sha256"],
        "baseline_type": "fixture_direct_prompt",
        "baseline_summary": _last_paragraph(str(fixtures["baseline_text"])),
        "abi_fixture_delta": transition["changed_opening_interpretation"],
        "baseline_fixture_delta": blind_comparison["candidate_b"]["observed_transition"],
        "deterministic_verdict": "fixture abi candidate shows stronger reread scaffold than fixture baseline",
    }


def build_calibration_summary(
    transition: dict[str, object],
    blind_comparison: dict[str, object],
    baseline_comparison: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "calibration_summary_builder_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "reader_state_equation": "Artwork = Artifact + DeltaReaderState",
        "transition_present": bool(transition["changed_opening_interpretation"]),
        "blind_comparison_fixture_preference": blind_comparison["fixture_preference"],
        "baseline_verdict": baseline_comparison["deterministic_verdict"],
        "limitations": [
            "fixture data is synthetic and deterministic",
            "no live human survey was collected",
            "no external survey integration was used",
        ],
    }


def build_evaluation_report(
    protocol: dict[str, object],
    trial: dict[str, object],
    transition: dict[str, object],
    summary: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "paper_grade_evaluation_report_builder_v1_stub",
        "fixture_only": True,
        "not_real_validation": True,
        "title": "Fixture Paper-Grade Evaluation Scaffold",
        "abstract": (
            "This deterministic fixture report demonstrates the artifact structure for "
            "future reader-state calibration. It is not evidence of real reader validation."
        ),
        "method_stub": protocol["protocol_scope"],
        "trial_fixture_id": trial["trial_id"],
        "reader_state_transition": transition,
        "summary": summary,
        "claims_not_made": [
            "no validated human success",
            "no live survey result",
            "no statistical inference",
        ],
    }


def evaluate_calibration_gate(
    *,
    protocol: dict[str, object],
    trial: dict[str, object],
    first_read_trace: dict[str, object],
    reread_trace: dict[str, object],
    transition: dict[str, object],
    blind_comparison: dict[str, object],
    baseline_comparison: dict[str, object],
    summary: dict[str, object],
    evaluation_report: dict[str, object],
) -> dict[str, object]:
    defects = []
    payloads = [
        protocol,
        trial,
        first_read_trace,
        reread_trace,
        transition,
        blind_comparison,
        baseline_comparison,
        summary,
        evaluation_report,
    ]
    if any(not payload.get("fixture_only") for payload in payloads):
        defects.append("all calibration payloads must be marked fixture_only")
    if any(not payload.get("not_real_validation") for payload in payloads):
        defects.append("all calibration payloads must be marked not_real_validation")
    if not transition["changed_opening_interpretation"]:
        defects.append("reader-state transition does not identify changed opening interpretation")
    if transition["unsupported_depth_flags"]:
        defects.append("reader-state transition contains unsupported depth flags")
    if not blind_comparison["artifact_labels_hidden"]:
        defects.append("blind comparison fixture does not hide labels")
    if not baseline_comparison["baseline_type"]:
        defects.append("baseline comparison has no baseline type")
    if "no validated human success" not in evaluation_report["claims_not_made"]:
        defects.append("evaluation report must refuse claims of validated human success")

    return {
        "worker": "calibration_gate_evaluator_v1_stub",
        "gate_name": CALIBRATION_GATE_NAME,
        "fixture_only": True,
        "not_real_validation": True,
        "passed": not defects,
        "blocking_defects": defects,
        "gate_scores": {
            "protocol_fields": len(protocol["required_reader_reports"]),
            "transition_fragments": len(transition["newly_connected_fragments"]),
            "blind_comparison_present": 1.0,
            "baseline_comparison_present": 1.0,
            "fixture_disclaimer_present": 1.0 if not defects else 0.0,
        },
        "summary_verdict": (
            "Human calibration fixture packet passes deterministic scaffold gates."
            if not defects
            else "Human calibration fixture packet is blocked by scaffold gate defects."
        ),
    }


def build_calibration_packet_summary(
    protocol: dict[str, object],
    trial: dict[str, object],
    transition: dict[str, object],
    gate_report: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "calibration_packet_summarizer_v1_stub",
        "artifact_types": list(CALIBRATION_ARTIFACT_TYPES),
        "fixture_only": True,
        "not_real_validation": True,
        "counts": {
            "protocol_fields": len(protocol["required_reader_reports"]),
            "trial_first_read_images": len(trial["first_read"]["retained_images"]),
            "transition_fragments": len(transition["newly_connected_fragments"]),
        },
        "reader_state_equation": "Artwork = Artifact + DeltaReaderState",
        "gate_summary": {
            "gate_name": gate_report["gate_name"],
            "passed": gate_report["passed"],
            "blocking_defects": gate_report["blocking_defects"],
            "summary_verdict": gate_report["summary_verdict"],
        },
        "lineage_id": CALIBRATION_LINEAGE_ID,
    }


def _write_and_register(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    output_dir: Path,
    artifact_type: str,
    payload: object,
    parent_ids: list[str],
) -> ArtifactRecord:
    path = output_dir / f"{artifact_type}.json"
    path.write_text(_canonical_json(payload), encoding="utf-8", newline="\n")
    return _register_or_get_artifact(
        connection,
        run_id=run_id,
        artifact_type=artifact_type,
        path=path,
        parent_ids=parent_ids,
    )


def _next_packet_dir(base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    used_numbers = []
    for child in base_dir.iterdir():
        if child.is_dir() and child.name.startswith("packet_"):
            suffix = child.name.removeprefix("packet_")
            if suffix.isdecimal():
                used_numbers.append(int(suffix))
    next_number = max(used_numbers, default=0) + 1
    return base_dir / f"packet_{next_number:04d}"


def _register_or_get_artifact(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    artifact_type: str,
    path: Path,
    parent_ids: list[str],
) -> ArtifactRecord:
    content_hash = sha256_file(path)
    expected_id = make_artifact_id(
        run_id,
        artifact_type,
        str(path),
        content_hash,
        parent_ids,
        CALIBRATION_LINEAGE_ID,
    )
    existing = get_artifact(connection, expected_id)
    if existing is not None:
        return existing
    return register_artifact(
        connection,
        run_id=run_id,
        artifact_type=artifact_type,
        path=path,
        lineage_id=CALIBRATION_LINEAGE_ID,
        parent_ids=parent_ids,
    )


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _last_paragraph(text: str) -> str:
    paragraphs = [paragraph.replace("\n", " ").strip() for paragraph in text.split("\n\n")]
    return next(paragraph for paragraph in reversed(paragraphs) if paragraph and not paragraph.startswith("#"))
