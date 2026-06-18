"""Minimal Abi Reread deterministic Phase 2 pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from abi.artifacts import ArtifactRecord, get_artifact, register_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import PHASE2_MINIMAL_REREAD_ACTIVE_PHASE, set_active_phase
from abi.db import connect
from abi.hashing import sha256_file
from abi.ids import artifact_id as make_artifact_id
from abi.modules.abi_ear import BENCHMARK_INPUT, build_benchmark_payloads, run_abi_ear_demo


REREAD_LINEAGE_ID = "minimal_reread_v1_benchmark"
REREAD_GATE_NAME = "minimal_reread_v1_benchmark"

REREAD_ARTIFACT_TYPES = (
    "reread_formal_problem",
    "reread_germ_afterimage_pair",
    "reread_consequence_graph",
    "reread_draft_version",
    "reread_first_read_trace",
    "reread_reread_trace",
    "reread_failure_diagnosis",
    "reread_intervention",
    "reread_recomposed_draft",
    "reread_counterfactual_result",
    "reread_irreducibility_report",
    "reread_gate_report",
    "reread_packet",
)


@dataclass(frozen=True)
class RereadRunResult:
    run_id: str
    packet_id: str
    packet_dir: str
    abi_ear_packet_artifact_id: str
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
            "abi_ear_packet_artifact_id": self.abi_ear_packet_artifact_id,
            "benchmark_input": BENCHMARK_INPUT,
            "artifact_ids": self.artifact_ids,
            "artifact_paths": self.artifact_paths,
            "gate_result": self.gate_result,
            "packet_artifact_id": self.artifact_ids["reread_packet"],
        }


def run_reread_demo(config: AbiConfig) -> RereadRunResult:
    abi_ear_result = run_abi_ear_demo(config)
    run_id = abi_ear_result.run_id
    output_dir = _next_packet_dir(config.run_dir(run_id) / "reread")
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads = build_reread_payloads(build_benchmark_payloads(BENCHMARK_INPUT))
    artifacts: dict[str, ArtifactRecord] = {}
    abi_ear_packet_artifact_id = abi_ear_result.artifact_ids["abi_ear_packet"]

    with connect(config.db_path) as connection:
        set_active_phase(connection, run_id, PHASE2_MINIMAL_REREAD_ACTIVE_PHASE)
        artifacts["reread_formal_problem"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_formal_problem",
            payload=payloads["reread_formal_problem"],
            parent_ids=[abi_ear_packet_artifact_id],
        )
        artifacts["reread_germ_afterimage_pair"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_germ_afterimage_pair",
            payload=payloads["reread_germ_afterimage_pair"],
            parent_ids=[
                abi_ear_packet_artifact_id,
                artifacts["reread_formal_problem"].id,
            ],
        )
        artifacts["reread_consequence_graph"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_consequence_graph",
            payload=payloads["reread_consequence_graph"],
            parent_ids=[
                artifacts["reread_formal_problem"].id,
                artifacts["reread_germ_afterimage_pair"].id,
            ],
        )
        artifacts["reread_draft_version"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_draft_version",
            payload=payloads["reread_draft_version"],
            parent_ids=[
                artifacts["reread_germ_afterimage_pair"].id,
                artifacts["reread_consequence_graph"].id,
            ],
        )
        artifacts["reread_first_read_trace"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_first_read_trace",
            payload=payloads["reread_first_read_trace"],
            parent_ids=[artifacts["reread_draft_version"].id],
        )
        artifacts["reread_reread_trace"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_reread_trace",
            payload=payloads["reread_reread_trace"],
            parent_ids=[
                artifacts["reread_draft_version"].id,
                artifacts["reread_germ_afterimage_pair"].id,
            ],
        )
        artifacts["reread_failure_diagnosis"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_failure_diagnosis",
            payload=payloads["reread_failure_diagnosis"],
            parent_ids=[
                artifacts["reread_first_read_trace"].id,
                artifacts["reread_reread_trace"].id,
            ],
        )
        artifacts["reread_intervention"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_intervention",
            payload=payloads["reread_intervention"],
            parent_ids=[artifacts["reread_failure_diagnosis"].id],
        )
        artifacts["reread_recomposed_draft"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_recomposed_draft",
            payload=payloads["reread_recomposed_draft"],
            parent_ids=[
                artifacts["reread_draft_version"].id,
                artifacts["reread_intervention"].id,
            ],
        )
        artifacts["reread_counterfactual_result"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_counterfactual_result",
            payload=payloads["reread_counterfactual_result"],
            parent_ids=[
                artifacts["reread_draft_version"].id,
                artifacts["reread_recomposed_draft"].id,
                artifacts["reread_intervention"].id,
            ],
        )
        artifacts["reread_irreducibility_report"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_irreducibility_report",
            payload=payloads["reread_irreducibility_report"],
            parent_ids=[
                artifacts["reread_counterfactual_result"].id,
                artifacts["reread_germ_afterimage_pair"].id,
            ],
        )
        artifacts["reread_gate_report"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_gate_report",
            payload=payloads["reread_gate_report"],
            parent_ids=[
                artifacts["reread_formal_problem"].id,
                artifacts["reread_counterfactual_result"].id,
                artifacts["reread_irreducibility_report"].id,
            ],
        )
        gate_report = payloads["reread_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=run_id,
            gate_name=REREAD_GATE_NAME,
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=REREAD_LINEAGE_ID,
        )
        artifacts["reread_packet"] = _write_and_register(
            connection,
            run_id=run_id,
            output_dir=output_dir,
            artifact_type="reread_packet",
            payload=payloads["reread_packet"],
            parent_ids=[
                abi_ear_packet_artifact_id,
                *[artifacts[artifact_type].id for artifact_type in REREAD_ARTIFACT_TYPES[:-1]],
            ],
        )

    return RereadRunResult(
        run_id=run_id,
        packet_id=output_dir.name,
        packet_dir=str(output_dir),
        abi_ear_packet_artifact_id=abi_ear_packet_artifact_id,
        artifact_ids={artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        artifact_paths={artifact_type: artifact.path for artifact_type, artifact in artifacts.items()},
        gate_result={
            "gate_name": REREAD_GATE_NAME,
            "passed": bool(payloads["reread_gate_report"]["passed"]),
            "blocking_defects": list(payloads["reread_gate_report"]["blocking_defects"]),
            "summary_verdict": payloads["reread_gate_report"]["summary_verdict"],
        },
        payloads=payloads,
        gate_record=gate_record,
    )


def build_reread_payloads(abi_ear_payloads: dict[str, object] | None = None) -> dict[str, object]:
    ear_payloads = abi_ear_payloads or build_benchmark_payloads(BENCHMARK_INPUT)
    formal_problem = define_formal_problem(ear_payloads)
    germ_afterimage_pair = pair_germ_afterimage(ear_payloads, formal_problem)
    consequence_graph = build_consequence_graph(formal_problem, germ_afterimage_pair)
    draft_version = compose_draft_version(germ_afterimage_pair, consequence_graph)
    first_read_trace = trace_blind_first_read(draft_version, formal_problem)
    reread_trace = trace_second_read(draft_version, germ_afterimage_pair, consequence_graph)
    failure_diagnosis = diagnose_failure(first_read_trace, reread_trace, formal_problem)
    intervention = target_intervention(failure_diagnosis, consequence_graph)
    recomposed_draft = recompose_draft(draft_version, intervention)
    counterfactual_result = evaluate_counterfactual(
        draft_version,
        recomposed_draft,
        intervention,
        reread_trace,
    )
    irreducibility_report = report_irreducibility(
        germ_afterimage_pair,
        intervention,
        counterfactual_result,
    )
    gate_report = evaluate_reread_gate(
        formal_problem=formal_problem,
        germ_afterimage_pair=germ_afterimage_pair,
        consequence_graph=consequence_graph,
        draft_version=draft_version,
        first_read_trace=first_read_trace,
        reread_trace=reread_trace,
        failure_diagnosis=failure_diagnosis,
        intervention=intervention,
        recomposed_draft=recomposed_draft,
        counterfactual_result=counterfactual_result,
        irreducibility_report=irreducibility_report,
    )
    packet = build_reread_packet_summary(
        formal_problem=formal_problem,
        draft_version=draft_version,
        recomposed_draft=recomposed_draft,
        counterfactual_result=counterfactual_result,
        gate_report=gate_report,
    )
    return {
        "reread_formal_problem": formal_problem,
        "reread_germ_afterimage_pair": germ_afterimage_pair,
        "reread_consequence_graph": consequence_graph,
        "reread_draft_version": draft_version,
        "reread_first_read_trace": first_read_trace,
        "reread_reread_trace": reread_trace,
        "reread_failure_diagnosis": failure_diagnosis,
        "reread_intervention": intervention,
        "reread_recomposed_draft": recomposed_draft,
        "reread_counterfactual_result": counterfactual_result,
        "reread_irreducibility_report": irreducibility_report,
        "reread_gate_report": gate_report,
        "reread_packet": packet,
    }


def define_formal_problem(abi_ear_payloads: dict[str, object]) -> dict[str, object]:
    ear_packet = abi_ear_payloads["abi_ear_packet"]
    return {
        "worker": "formal_problem_builder_v1_stub",
        "benchmark_input": BENCHMARK_INPUT,
        "source_packet_counts": ear_packet["counts"],
        "problem_statement": (
            "Make the opening sentence become more necessary after reread than it was "
            "on first encounter."
        ),
        "initial_reader_state": {
            "opening_assumption": "plain domestic persistence",
            "noticed_terms": ["table", "still", "morning"],
            "unnoticed_pressure": ["there", "night gap", "evidence without explanation"],
        },
        "target_reader_state": {
            "opening_assumption": "the table is evidence of an unseen overnight test",
            "required_shift": "still changes from neutral duration to causal pressure",
        },
        "success_conditions": [
            "blind first read under-interprets the opening",
            "reread trace explains what changed and where",
            "intervention improves the causal return without importing backstory",
            "counterfactual comparison shows loss when intervention is removed",
        ],
        "forbidden_shortcuts": [
            "explaining the night directly",
            "adding a new setting",
            "using a named reader agent",
            "claiming success without counterfactual comparison",
        ],
    }


def pair_germ_afterimage(
    abi_ear_payloads: dict[str, object],
    formal_problem: dict[str, object],
) -> dict[str, object]:
    refined = abi_ear_payloads["abi_ear_refined_invention"]
    return {
        "worker": "germ_afterimage_pairer_v1_stub",
        "germ": BENCHMARK_INPUT,
        "afterimage": (
            "Only morning, returning the sentence with the weight moved onto still."
        ),
        "source_refined_invention_excerpt": refined["text"].split("\n\n")[-1],
        "reader_state_delta": {
            "from": formal_problem["initial_reader_state"]["opening_assumption"],
            "to": formal_problem["target_reader_state"]["opening_assumption"],
        },
        "load_bearing_words": ["table", "still", "there", "morning"],
    }


def build_consequence_graph(
    formal_problem: dict[str, object],
    germ_afterimage_pair: dict[str, object],
) -> dict[str, object]:
    nodes = [
        {"id": "n01", "label": "table remains", "kind": "germ fact"},
        {"id": "n02", "label": "night remains unnarrated", "kind": "negative interval"},
        {"id": "n03", "label": "first read sees ordinary persistence", "kind": "reader state"},
        {"id": "n04", "label": "evidence accumulates around non-events", "kind": "field pressure"},
        {"id": "n05", "label": "still becomes causal hinge", "kind": "afterimage"},
        {"id": "n06", "label": "opening rereads as proof", "kind": "target state"},
    ]
    edges = [
        {"from": "n01", "to": "n03", "relation": "initially appears as"},
        {"from": "n02", "to": "n04", "relation": "pressurizes"},
        {"from": "n04", "to": "n05", "relation": "reweights"},
        {"from": "n05", "to": "n06", "relation": "causes"},
        {"from": "n01", "to": "n06", "relation": "returns as evidence"},
    ]
    return {
        "worker": "consequence_graph_builder_v1_stub",
        "problem_statement": formal_problem["problem_statement"],
        "germ": germ_afterimage_pair["germ"],
        "nodes": nodes,
        "edges": edges,
        "cycle": ["n01", "n03", "n04", "n05", "n06", "n01"],
        "structural_claim": "The opening must be ordinary first and evidentiary second.",
    }


def compose_draft_version(
    germ_afterimage_pair: dict[str, object],
    consequence_graph: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "draft_composer_v1_stub",
        "version_id": "draft_v1",
        "used_graph_nodes": [node["id"] for node in consequence_graph["nodes"]],
        "text": (
            "The table is still there in the morning.\n\n"
            "Dust has kept a square around each leg. The cup ring has dried, and the "
            "chairs face the table as if they have been waiting to be counted.\n\n"
            "Nothing explains the night. The room only offers the table again, and the "
            "word still has less rest in it than before."
        ),
        "intended_afterimage": germ_afterimage_pair["afterimage"],
        "known_weakness": "The first draft names the changed word before fully proving the change.",
    }


def trace_blind_first_read(
    draft_version: dict[str, object],
    formal_problem: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "blind_first_read_tracer_v1_stub",
        "draft_version_id": draft_version["version_id"],
        "opening_read": "A quiet room is being described after night.",
        "noticed_evidence": ["dust around the legs", "cup ring", "chairs facing the table"],
        "missed_evidence": ["why the table matters", "why still is unstable"],
        "reader_state": {
            "confidence": 0.42,
            "interpretation": formal_problem["initial_reader_state"]["opening_assumption"],
        },
        "blind_spots": [
            "sees stillness as atmosphere rather than causal pressure",
            "does not yet connect non-events to proof",
        ],
    }


def trace_second_read(
    draft_version: dict[str, object],
    germ_afterimage_pair: dict[str, object],
    consequence_graph: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "reread_trace_builder_v1_stub",
        "draft_version_id": draft_version["version_id"],
        "opening_reread": (
            "The table's presence now reads as proof that something could have displaced it."
        ),
        "changed_opening_words": germ_afterimage_pair["load_bearing_words"],
        "supporting_nodes": ["n02", "n04", "n05", "n06"],
        "supporting_passages": [
            "Dust has kept a square around each leg.",
            "Nothing explains the night.",
            "the word still has less rest in it than before",
        ],
        "reader_state": {
            "confidence": 0.76,
            "interpretation": germ_afterimage_pair["reader_state_delta"]["to"],
        },
        "cycle_used": consequence_graph["cycle"],
    }


def diagnose_failure(
    first_read_trace: dict[str, object],
    reread_trace: dict[str, object],
    formal_problem: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "failure_diagnoser_v1_stub",
        "failure_id": "f01",
        "diagnosed_failure": (
            "The draft produces reread gain, but the first read can identify the intended "
            "pressure too early because the final sentence explains still directly."
        ),
        "evidence": {
            "first_read_blind_spots": first_read_trace["blind_spots"],
            "reread_confidence": reread_trace["reader_state"]["confidence"],
            "target_shift": formal_problem["target_reader_state"]["required_shift"],
        },
        "severity": "medium",
        "repair_requirement": (
            "Move the explanation of still into image and syntax rather than naming it."
        ),
    }


def target_intervention(
    failure_diagnosis: dict[str, object],
    consequence_graph: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "targeted_intervention_builder_v1_stub",
        "intervention_id": "i01",
        "targets_failure_id": failure_diagnosis["failure_id"],
        "operation": "replace explanatory close with concrete return",
        "target_passage": "the word still has less rest in it than before",
        "replacement_strategy": [
            "keep the opening unchanged",
            "remove direct explanation of still",
            "make the table's unchanged position deliver the reread pressure",
        ],
        "affected_graph_nodes": ["n04", "n05", "n06"],
        "expected_effect": consequence_graph["structural_claim"],
    }


def recompose_draft(
    draft_version: dict[str, object],
    intervention: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "recomposer_v1_stub",
        "version_id": "draft_v2",
        "source_version_id": draft_version["version_id"],
        "intervention_id": intervention["intervention_id"],
        "text": (
            "The table is still there in the morning.\n\n"
            "Dust has kept a square around each leg. The cup ring has dried, and the "
            "chairs face the table as if they have been waiting to be counted.\n\n"
            "Nothing explains the night. The room offers the table again: four legs, "
            "one ring, the same place under the window. Morning stops there."
        ),
        "change_log": [
            "removed direct explanation of still",
            "ended on repeated evidence rather than interpretation",
            "kept scale inside the room",
        ],
    }


def evaluate_counterfactual(
    draft_version: dict[str, object],
    recomposed_draft: dict[str, object],
    intervention: dict[str, object],
    reread_trace: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "counterfactual_evaluator_v1_stub",
        "counterfactual_id": "cf01",
        "tested_condition": "remove intervention i01 and restore explanatory close",
        "baseline_version_id": draft_version["version_id"],
        "intervention_version_id": recomposed_draft["version_id"],
        "predicted_without_intervention": {
            "reread_gain": 0.52,
            "failure": "reader can name the intended effect before rereading",
        },
        "predicted_with_intervention": {
            "reread_gain": 0.79,
            "repair": "reader must infer the changed weight from object evidence",
        },
        "delta": {
            "reread_gain": 0.27,
            "targeted_failure_reduced": True,
        },
        "intervention_id": intervention["intervention_id"],
        "uses_previous_reread_trace_confidence": reread_trace["reader_state"]["confidence"],
    }


def report_irreducibility(
    germ_afterimage_pair: dict[str, object],
    intervention: dict[str, object],
    counterfactual_result: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "irreducibility_reporter_v1_stub",
        "load_bearing_elements": [
            {
                "element": "still",
                "why_irreducible": "removing it collapses duration and threat into plain presence",
            },
            {
                "element": "unchanged table position",
                "why_irreducible": "the counterfactual proof needs the same object to return",
            },
            {
                "element": intervention["intervention_id"],
                "why_irreducible": "it prevents the draft from explaining its own reread effect",
            },
        ],
        "germ_afterimage_dependency": germ_afterimage_pair["reader_state_delta"],
        "counterfactual_delta": counterfactual_result["delta"],
        "verdict": "The minimal loop is structurally irreducible for the benchmark.",
    }


def evaluate_reread_gate(
    *,
    formal_problem: dict[str, object],
    germ_afterimage_pair: dict[str, object],
    consequence_graph: dict[str, object],
    draft_version: dict[str, object],
    first_read_trace: dict[str, object],
    reread_trace: dict[str, object],
    failure_diagnosis: dict[str, object],
    intervention: dict[str, object],
    recomposed_draft: dict[str, object],
    counterfactual_result: dict[str, object],
    irreducibility_report: dict[str, object],
) -> dict[str, object]:
    defects = []
    if not formal_problem["success_conditions"]:
        defects.append("formal problem has no success conditions")
    if not germ_afterimage_pair["afterimage"]:
        defects.append("germ/afterimage pair is incomplete")
    if len(consequence_graph["nodes"]) < 6 or len(consequence_graph["edges"]) < 5:
        defects.append("consequence graph is too small")
    if not draft_version["text"].startswith(BENCHMARK_INPUT):
        defects.append("draft version does not preserve benchmark opening")
    if not first_read_trace["blind_spots"]:
        defects.append("blind first-read trace has no blind spots")
    if not reread_trace["changed_opening_words"]:
        defects.append("reread trace does not identify changed opening words")
    if not failure_diagnosis["repair_requirement"]:
        defects.append("failure diagnosis does not specify repair")
    if not intervention["replacement_strategy"]:
        defects.append("intervention has no replacement strategy")
    if not recomposed_draft["text"].startswith(BENCHMARK_INPUT):
        defects.append("recomposed draft does not preserve benchmark opening")
    if not counterfactual_result["delta"]["targeted_failure_reduced"]:
        defects.append("counterfactual does not reduce the targeted failure")
    if "irreducible" not in irreducibility_report["verdict"]:
        defects.append("irreducibility report does not give an irreducibility verdict")

    gate_scores = {
        "formal_problem": 1.0 if not defects else 0.9,
        "trace_delta": round(
            reread_trace["reader_state"]["confidence"] - first_read_trace["reader_state"]["confidence"],
            3,
        ),
        "counterfactual_gain": counterfactual_result["delta"]["reread_gain"],
        "irreducibility": 1.0 if "irreducible" in irreducibility_report["verdict"] else 0.0,
    }
    return {
        "worker": "reread_gate_evaluator_v1_stub",
        "gate_name": REREAD_GATE_NAME,
        "passed": not defects,
        "blocking_defects": defects,
        "gate_scores": gate_scores,
        "summary_verdict": (
            "Minimal reread benchmark packet passes deterministic local gates."
            if not defects
            else "Minimal reread benchmark packet is blocked by local gate defects."
        ),
    }


def build_reread_packet_summary(
    *,
    formal_problem: dict[str, object],
    draft_version: dict[str, object],
    recomposed_draft: dict[str, object],
    counterfactual_result: dict[str, object],
    gate_report: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "reread_packet_summarizer_v1_stub",
        "benchmark_input": BENCHMARK_INPUT,
        "artifact_types": list(REREAD_ARTIFACT_TYPES),
        "loop_shape": [
            "reader-state trace",
            "diagnosed failure",
            "targeted intervention",
            "counterfactual proof",
        ],
        "problem_statement": formal_problem["problem_statement"],
        "versions": {
            "draft": draft_version["version_id"],
            "recomposed": recomposed_draft["version_id"],
        },
        "counterfactual_summary": counterfactual_result["delta"],
        "gate_summary": {
            "gate_name": gate_report["gate_name"],
            "passed": gate_report["passed"],
            "blocking_defects": gate_report["blocking_defects"],
            "summary_verdict": gate_report["summary_verdict"],
        },
        "lineage_id": REREAD_LINEAGE_ID,
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
        REREAD_LINEAGE_ID,
    )
    existing = get_artifact(connection, expected_id)
    if existing is not None:
        return existing
    return register_artifact(
        connection,
        run_id=run_id,
        artifact_type=artifact_type,
        path=path,
        lineage_id=REREAD_LINEAGE_ID,
        parent_ids=parent_ids,
    )


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
