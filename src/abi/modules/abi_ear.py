"""Abi Ear v1 deterministic benchmark pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from abi.artifacts import ArtifactRecord
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import PHASE1_ABI_EAR_ACTIVE_PHASE, ensure_active_run
from abi.controller.state import set_active_phase
from abi.db import connect
from abi.packets import PacketWriter, create_packet_dir


BENCHMARK_INPUT = "The table is still there in the morning."
ABI_EAR_LINEAGE_ID = "abi_ear_v1_benchmark"
ABI_EAR_GATE_NAME = "abi_ear_v1_benchmark"

ABI_EAR_ARTIFACT_TYPES = (
    "abi_ear_germ_analysis",
    "abi_ear_variants",
    "abi_ear_field_model",
    "abi_ear_moves",
    "abi_ear_ranked_move_sequence",
    "abi_ear_prose_inventions",
    "abi_ear_refined_invention",
    "abi_ear_reread_trace",
    "abi_ear_ablation_report",
    "abi_ear_gate_report",
    "abi_ear_packet",
)


@dataclass(frozen=True)
class AbiEarRunResult:
    run_id: str
    packet_id: str
    packet_dir: str
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
            "benchmark_input": BENCHMARK_INPUT,
            "artifact_ids": self.artifact_ids,
            "artifact_paths": self.artifact_paths,
            "gate_result": self.gate_result,
            "packet_artifact_id": self.artifact_ids["abi_ear_packet"],
        }


def run_abi_ear_demo(config: AbiConfig) -> AbiEarRunResult:
    run, _ = ensure_active_run(config)
    output_dir = create_packet_dir(config.run_dir(run.id) / "abi_ear")

    payloads = build_benchmark_payloads(BENCHMARK_INPUT)
    artifacts: dict[str, ArtifactRecord] = {}

    with connect(config.db_path) as connection:
        set_active_phase(connection, run.id, PHASE1_ABI_EAR_ACTIVE_PHASE)
        writer = PacketWriter(
            connection=connection,
            run_id=run.id,
            packet_dir=output_dir,
            lineage_id=ABI_EAR_LINEAGE_ID,
            created_by="abi_ear_v1_stub",
            fixture_only=False,
        )
        artifacts["abi_ear_germ_analysis"] = writer.write_artifact(
            "abi_ear_germ_analysis",
            payloads["abi_ear_germ_analysis"],
            parent_ids=[],
        )
        artifacts["abi_ear_variants"] = writer.write_artifact(
            "abi_ear_variants",
            payloads["abi_ear_variants"],
            parent_ids=[artifacts["abi_ear_germ_analysis"].id],
        )
        artifacts["abi_ear_field_model"] = writer.write_artifact(
            "abi_ear_field_model",
            payloads["abi_ear_field_model"],
            parent_ids=[artifacts["abi_ear_germ_analysis"].id],
        )
        artifacts["abi_ear_moves"] = writer.write_artifact(
            "abi_ear_moves",
            payloads["abi_ear_moves"],
            parent_ids=[
                artifacts["abi_ear_germ_analysis"].id,
                artifacts["abi_ear_field_model"].id,
            ],
        )
        artifacts["abi_ear_ranked_move_sequence"] = writer.write_artifact(
            "abi_ear_ranked_move_sequence",
            payloads["abi_ear_ranked_move_sequence"],
            parent_ids=[
                artifacts["abi_ear_moves"].id,
                artifacts["abi_ear_field_model"].id,
            ],
        )
        artifacts["abi_ear_prose_inventions"] = writer.write_artifact(
            "abi_ear_prose_inventions",
            payloads["abi_ear_prose_inventions"],
            parent_ids=[
                artifacts["abi_ear_field_model"].id,
                artifacts["abi_ear_ranked_move_sequence"].id,
            ],
        )
        artifacts["abi_ear_refined_invention"] = writer.write_artifact(
            "abi_ear_refined_invention",
            payloads["abi_ear_refined_invention"],
            parent_ids=[
                artifacts["abi_ear_prose_inventions"].id,
                artifacts["abi_ear_ranked_move_sequence"].id,
            ],
        )
        artifacts["abi_ear_reread_trace"] = writer.write_artifact(
            "abi_ear_reread_trace",
            payloads["abi_ear_reread_trace"],
            parent_ids=[
                artifacts["abi_ear_refined_invention"].id,
                artifacts["abi_ear_germ_analysis"].id,
                artifacts["abi_ear_field_model"].id,
            ],
        )
        artifacts["abi_ear_ablation_report"] = writer.write_artifact(
            "abi_ear_ablation_report",
            payloads["abi_ear_ablation_report"],
            parent_ids=[
                artifacts["abi_ear_refined_invention"].id,
                artifacts["abi_ear_ranked_move_sequence"].id,
                artifacts["abi_ear_reread_trace"].id,
            ],
        )
        artifacts["abi_ear_gate_report"] = writer.write_artifact(
            "abi_ear_gate_report",
            payloads["abi_ear_gate_report"],
            parent_ids=[
                artifacts["abi_ear_germ_analysis"].id,
                artifacts["abi_ear_variants"].id,
                artifacts["abi_ear_moves"].id,
                artifacts["abi_ear_prose_inventions"].id,
                artifacts["abi_ear_ablation_report"].id,
            ],
        )
        gate_report = payloads["abi_ear_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=run.id,
            gate_name=ABI_EAR_GATE_NAME,
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=ABI_EAR_LINEAGE_ID,
        )
        artifacts["abi_ear_packet"] = writer.write_artifact(
            "abi_ear_packet",
            payloads["abi_ear_packet"],
            parent_ids=[artifacts[artifact_type].id for artifact_type in ABI_EAR_ARTIFACT_TYPES[:-1]],
        )

    return AbiEarRunResult(
        run_id=run.id,
        packet_id=output_dir.name,
        packet_dir=str(output_dir),
        artifact_ids={artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        artifact_paths={artifact_type: artifact.path for artifact_type, artifact in artifacts.items()},
        gate_result={
            "gate_name": ABI_EAR_GATE_NAME,
            "passed": bool(payloads["abi_ear_gate_report"]["passed"]),
            "blocking_defects": list(payloads["abi_ear_gate_report"]["blocking_defects"]),
            "summary_verdict": payloads["abi_ear_gate_report"]["summary_verdict"],
        },
        payloads=payloads,
        gate_record=gate_record,
    )


def build_benchmark_payloads(germ_text: str = BENCHMARK_INPUT) -> dict[str, object]:
    germ_analysis = analyze_germ(germ_text)
    variants = generate_variants(germ_text, germ_analysis)
    field_model = build_field_model(germ_text, germ_analysis)
    moves = compose_moves(germ_text, field_model)
    ranked_move_sequence = rank_moves(moves, field_model)
    prose_inventions = compose_developments(germ_text, field_model, ranked_move_sequence)
    refined_invention = refine_invention(prose_inventions, ranked_move_sequence)
    reread_trace = trace_reread(refined_invention, germ_text, field_model)
    ablation_report = report_ablation(refined_invention, germ_text, ranked_move_sequence, reread_trace)
    gate_report = evaluate_gate_packet(
        germ_analysis=germ_analysis,
        variants=variants,
        field_model=field_model,
        moves=moves,
        ranked_move_sequence=ranked_move_sequence,
        prose_inventions=prose_inventions,
        refined_invention=refined_invention,
        reread_trace=reread_trace,
        ablation_report=ablation_report,
    )
    packet = build_packet_summary(
        germ_text=germ_text,
        germ_analysis=germ_analysis,
        variants=variants,
        moves=moves,
        prose_inventions=prose_inventions,
        gate_report=gate_report,
    )

    return {
        "abi_ear_germ_analysis": germ_analysis,
        "abi_ear_variants": variants,
        "abi_ear_field_model": field_model,
        "abi_ear_moves": moves,
        "abi_ear_ranked_move_sequence": ranked_move_sequence,
        "abi_ear_prose_inventions": prose_inventions,
        "abi_ear_refined_invention": refined_invention,
        "abi_ear_reread_trace": reread_trace,
        "abi_ear_ablation_report": ablation_report,
        "abi_ear_gate_report": gate_report,
        "abi_ear_packet": packet,
    }


def analyze_germ(germ_text: str) -> dict[str, object]:
    word_forces = [
        {
            "word": "The",
            "role": "definite article",
            "force": "assumes a known object before any scene is explained",
            "pressure": 0.48,
        },
        {
            "word": "table",
            "role": "object",
            "force": "anchors the germ in domestic matter rather than abstract mood",
            "pressure": 0.74,
        },
        {
            "word": "is",
            "role": "state verb",
            "force": "makes existence immediate and resistant to explanation",
            "pressure": 0.55,
        },
        {
            "word": "still",
            "role": "temporal hinge",
            "force": "implies a prior threat of removal or change",
            "pressure": 0.92,
        },
        {
            "word": "there",
            "role": "place marker",
            "force": "turns location into evidence while withholding the location",
            "pressure": 0.81,
        },
        {
            "word": "in",
            "role": "container preposition",
            "force": "puts the observation inside a bounded interval",
            "pressure": 0.43,
        },
        {
            "word": "the",
            "role": "definite article",
            "force": "treats morning as expected and repeatable",
            "pressure": 0.39,
        },
        {
            "word": "morning",
            "role": "arrival time",
            "force": "converts survival through night into proof",
            "pressure": 0.88,
        },
    ]
    return {
        "worker": "germ_analyzer_v1_stub",
        "input": germ_text,
        "word_forces": word_forces,
        "future_opened": [
            "something may have tried to remove or transform the table overnight",
            "the observer's relief may be less stable than the table",
            "morning can become a test rather than a neutral time",
        ],
        "risks": [
            "the sentence can flatten into mere domestic realism",
            "the table can become symbolic too quickly",
            "the withheld night can feel evasive if never pressured",
        ],
        "fertility_score": 0.86,
    }


def generate_variants(germ_text: str, germ_analysis: dict[str, object]) -> dict[str, object]:
    variants = [
        (
            "v01",
            "The table is still there when morning comes.",
            "keeps the core fact and lets morning act as an arrival",
            "softens the sentence toward inevitability",
        ),
        (
            "v02",
            "In the morning, the table has not moved.",
            "moves time to the front and makes immobility explicit",
            "turns the table into a measured condition",
        ),
        (
            "v03",
            "Morning finds the table still there.",
            "gives morning agency without adding a character",
            "makes time the discovering force",
        ),
        (
            "v04",
            "The table remains there by morning.",
            "compresses the overnight test into one result",
            "emphasizes survival through an unseen interval",
        ),
        (
            "v05",
            "At morning, the table is there again.",
            "adds recurrence while preserving the plain object",
            "opens a cycle of disappearance and return",
        ),
        (
            "v06",
            "The table waits in the same place until morning.",
            "personifies without importing a full agent",
            "makes stillness active and patient",
        ),
        (
            "v07",
            "By morning, the table has become proof of staying.",
            "names the evidentiary pressure inside the germ",
            "risks abstraction but clarifies the field",
        ),
        (
            "v08",
            "The morning leaves the table exactly where it was.",
            "lets morning be responsible for non-change",
            "makes stability feel like an action",
        ),
        (
            "v09",
            "The table is there, still, in the morning.",
            "isolates still as the sentence's hinge",
            "raises the pressure on delayed recognition",
        ),
        (
            "v10",
            "Nothing has taken the table by morning.",
            "exposes the absent threat implied by still",
            "pulls negative space into the foreground",
        ),
    ]
    return {
        "worker": "variant_generator_v1_stub",
        "input": germ_text,
        "source_fertility_score": germ_analysis["fertility_score"],
        "variants": [
            {
                "id": variant_id,
                "text": text,
                "rationale": rationale,
                "predicted_field_shift": predicted_field_shift,
            }
            for variant_id, text, rationale, predicted_field_shift in variants
        ],
    }


def build_field_model(germ_text: str, germ_analysis: dict[str, object]) -> dict[str, object]:
    return {
        "worker": "field_model_builder_v1_stub",
        "selected_germ": germ_text,
        "objects": [
            {"name": "table", "function": "stable object under overnight pressure"},
            {"name": "morning", "function": "returning test condition"},
            {"name": "unseen night", "function": "withheld interval where change was possible"},
            {"name": "observer", "function": "registers evidence but is not foregrounded"},
        ],
        "local_laws": [
            "plain objects carry the strongest pressure",
            "the night can imply action without being narrated",
            "morning verifies rather than explains",
            "each return to the table must alter the meaning of still",
        ],
        "latent_oppositions": [
            "stasis versus aftermath",
            "evidence versus explanation",
            "domestic scale versus metaphysical pressure",
            "relief versus suspicion",
        ],
        "negative_space": [
            "who expected the table to be gone",
            "what happened in the night",
            "why this ordinary object matters",
        ],
        "scale_ceiling": "one room, one night, one object, one changed interpretation",
        "forbidden_imports": [
            "external backstory",
            "named supernatural machinery",
            "new locations outside the room",
            "explicit explanation of the night",
        ],
        "possible_returns": [
            "the opening sentence returns as evidence",
            "still returns as a changed word",
            "morning returns as judgment instead of light",
        ],
        "analysis_pressure": germ_analysis["fertility_score"],
    }


def compose_moves(germ_text: str, field_model: dict[str, object]) -> dict[str, object]:
    move_specs = [
        ("m01", "delay recognition", "Let morning arrive before the observer understands relief."),
        ("m02", "object as witness", "Treat the table as the only reliable testimony."),
        ("m03", "negative interval", "Make the night felt only through morning evidence."),
        ("m04", "pressure on still", "Return to still after it has gained threat."),
        ("m05", "scale refusal", "Keep the field inside the room."),
        ("m06", "absent removal", "Imply that nothing taking the table is an event."),
        ("m07", "surface audit", "Inspect scratches and dust instead of explaining causes."),
        ("m08", "observer displacement", "Make the observer less stable than the table."),
        ("m09", "morning as verdict", "Let light judge the room without announcing judgment."),
        ("m10", "ordinary diction", "Keep sentences plain enough to protect the object."),
        ("m11", "return with changed grammar", "Repeat the opening with a shifted stress pattern."),
        ("m12", "withheld agency", "Refuse to name what might have moved the table."),
        ("m13", "evidence inversion", "Make survival feel stranger than disappearance."),
        ("m14", "small measurement", "Use one leg, one mark, or one cup ring as proof."),
        ("m15", "anti-revelation", "End with knowledge narrowing rather than expanding."),
        ("m16", "latent cycle", "Suggest this morning has happened before."),
        ("m17", "domestic law", "Let household order behave like a physical law."),
        ("m18", "line break of causality", "Place cause after consequence in local sequence."),
        ("m19", "return payoff", "Make the final return alter the first sentence."),
        ("m20", "risk containment", "Name no system larger than the table can bear."),
    ]
    moves = []
    for index, (move_id, operation_name, new_material) in enumerate(move_specs, start=1):
        pressure_delta = round(0.22 + index * 0.025, 3)
        derivation_distance = round(0.10 + (index % 5) * 0.08, 3)
        return_payoff = round(0.34 + ((21 - index) % 7) * 0.07, 3)
        moves.append(
            {
                "id": move_id,
                "parent_material": germ_text if index <= 4 else field_model["scale_ceiling"],
                "operation_name": operation_name,
                "new_material": new_material,
                "predicted_field_delta": _predicted_delta_for_move(move_id),
                "pressure_delta": pressure_delta,
                "derivation_distance": derivation_distance,
                "return_payoff": return_payoff,
                "risk": _risk_for_move(move_id),
            }
        )
    return {
        "worker": "move_composer_v1_stub",
        "input_germ": germ_text,
        "moves": moves,
    }


def rank_moves(moves: dict[str, object], field_model: dict[str, object]) -> dict[str, object]:
    rank_order = [
        "m04",
        "m03",
        "m19",
        "m02",
        "m13",
        "m09",
        "m08",
        "m14",
        "m12",
        "m01",
        "m11",
        "m06",
        "m15",
        "m10",
        "m16",
        "m05",
        "m17",
        "m18",
        "m20",
        "m07",
    ]
    move_by_id = {move["id"]: move for move in moves["moves"]}
    ranked = []
    for rank, move_id in enumerate(rank_order, start=1):
        move = move_by_id[move_id]
        surprise_before = round(0.95 - rank * 0.018, 3)
        necessity_after = round(0.72 + (21 - rank) * 0.011, 3)
        ranked.append(
            {
                "rank": rank,
                "move_id": move_id,
                "operation_name": move["operation_name"],
                "surprise_before": surprise_before,
                "necessity_after": necessity_after,
                "combined_score": round((surprise_before + necessity_after) / 2, 3),
                "risk": move["risk"],
            }
        )
    return {
        "worker": "retrospective_inevitability_judge_v1_stub",
        "ranked_moves": ranked,
        "selected_sequence": rank_order[:8],
        "field_constraints_used": field_model["local_laws"],
        "risks": [
            "overreading stillness",
            "letting explanation outrun object pressure",
        ],
    }


def compose_developments(
    germ_text: str,
    field_model: dict[str, object],
    ranked_move_sequence: dict[str, object],
) -> dict[str, object]:
    selected = ranked_move_sequence["selected_sequence"]
    inventions = [
        {
            "id": "p01",
            "title": "Cup Ring",
            "used_move_ids": selected[:5],
            "text": (
                "The table is still there in the morning. The cup ring has dried on its "
                "edge, pale as a second moon, and no chair admits to having watched it."
            ),
        },
        {
            "id": "p02",
            "title": "Inventory",
            "used_move_ids": selected[2:7],
            "text": (
                "In the morning the table remains. The room takes inventory around it: "
                "four legs, one shadow, the untouched square where fear had stood."
            ),
        },
        {
            "id": "p03",
            "title": "Still",
            "used_move_ids": selected[1:8],
            "text": (
                "Morning does not explain the night. It only shows the table, still "
                "there, making the word still carry more than rest."
            ),
        },
    ]
    return {
        "worker": "development_composer_v1_stub",
        "input_germ": germ_text,
        "scale_ceiling": field_model["scale_ceiling"],
        "prose_inventions": inventions,
    }


def refine_invention(
    prose_inventions: dict[str, object],
    ranked_move_sequence: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "development_composer_refiner_v1_stub",
        "source_invention_ids": ["p01", "p03"],
        "used_move_ids": ranked_move_sequence["selected_sequence"][:8],
        "text": (
            "The table is still there in the morning.\n\n"
            "The cup ring has dried at the edge, and the dust keeps the shape of every "
            "thing that did not happen. Four legs hold the room to its promise. Nothing "
            "has taken the table, which is why the room feels less certain than the "
            "wood.\n\n"
            "By the time the light reaches the floor, there has been no revelation. "
            "Only the table, still there. Only morning, returning the sentence with the "
            "weight moved onto still."
        ),
        "refinement_notes": [
            "keeps the original sentence intact as the opening",
            "uses domestic evidence instead of external explanation",
            "returns to still as a changed word",
        ],
    }


def trace_reread(
    refined_invention: dict[str, object],
    germ_text: str,
    field_model: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "reread_tracer_v1_stub",
        "first_read_opening_interpretation": "A plain object remains in place after night.",
        "second_read_opening_interpretation": (
            "The table's remaining has become evidence that the room and observer were "
            "under pressure before the first sentence began."
        ),
        "changed_opening_words": ["table", "still", "there", "morning"],
        "supporting_lines_or_passages": [
            "the dust keeps the shape of every thing that did not happen",
            "the room feels less certain than the wood",
            "returning the sentence with the weight moved onto still",
        ],
        "reread_gain_estimate": 0.74,
        "unsupported_claims": [],
        "source_germ": germ_text,
        "field_returns": field_model["possible_returns"],
        "refined_invention_excerpt": refined_invention["text"].split("\n\n")[0],
    }


def report_ablation(
    refined_invention: dict[str, object],
    germ_text: str,
    ranked_move_sequence: dict[str, object],
    reread_trace: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "ablation_reporter_v1_stub",
        "source_germ": germ_text,
        "tested_removals_or_replacements": [
            {
                "id": "a01",
                "target_type": "word",
                "target": "still",
                "change": "replace with already",
                "predicted_effect_loss": "removes the overnight pressure hinge",
                "verdict": "fatal loss",
            },
            {
                "id": "a02",
                "target_type": "word",
                "target": "morning",
                "change": "replace with later",
                "predicted_effect_loss": "weakens the return as a test condition",
                "verdict": "major loss",
            },
            {
                "id": "a03",
                "target_type": "move",
                "target": "m03",
                "change": "explain the night directly",
                "predicted_effect_loss": "collapses negative interval into backstory",
                "verdict": "fatal loss",
            },
            {
                "id": "a04",
                "target_type": "move",
                "target": "m19",
                "change": "remove final return to still",
                "predicted_effect_loss": "leaves the opening unchanged on reread",
                "verdict": "major loss",
            },
        ],
        "selected_moves_tested": ranked_move_sequence["selected_sequence"][:4],
        "reread_gain_after_ablations": {
            "baseline": reread_trace["reread_gain_estimate"],
            "without_still": 0.21,
            "without_negative_interval": 0.28,
        },
        "refined_invention_length_chars": len(refined_invention["text"]),
    }


def evaluate_gate_packet(
    *,
    germ_analysis: dict[str, object],
    variants: dict[str, object],
    field_model: dict[str, object],
    moves: dict[str, object],
    ranked_move_sequence: dict[str, object],
    prose_inventions: dict[str, object],
    refined_invention: dict[str, object],
    reread_trace: dict[str, object],
    ablation_report: dict[str, object],
) -> dict[str, object]:
    defects = []
    if len(germ_analysis["word_forces"]) != 8:
        defects.append("word-level germ analysis does not cover the benchmark words")
    if len(variants["variants"]) != 10:
        defects.append("variant count is not ten")
    if len(moves["moves"]) != 20:
        defects.append("move count is not twenty")
    if len(prose_inventions["prose_inventions"]) < 3:
        defects.append("fewer than three prose inventions")
    if not refined_invention["text"].startswith(BENCHMARK_INPUT):
        defects.append("refined invention does not preserve the benchmark opening")
    if reread_trace["unsupported_claims"]:
        defects.append("reread trace contains unsupported claims")
    if len(ablation_report["tested_removals_or_replacements"]) < 4:
        defects.append("ablation report is too small")

    gate_scores = {
        "word_analysis_coverage": 1.0 if len(germ_analysis["word_forces"]) == 8 else 0.0,
        "variant_count": len(variants["variants"]) / 10,
        "move_count": len(moves["moves"]) / 20,
        "invention_count": min(len(prose_inventions["prose_inventions"]) / 3, 1.0),
        "reread_support": 1.0 if not reread_trace["unsupported_claims"] else 0.0,
        "ablation_sensitivity": 1.0,
        "field_constraint_fit": 1.0 if field_model["forbidden_imports"] else 0.0,
        "ranking_completeness": len(ranked_move_sequence["ranked_moves"]) / 20,
    }
    return {
        "worker": "gate_evaluator_v1_stub",
        "gate_name": ABI_EAR_GATE_NAME,
        "passed": not defects,
        "blocking_defects": defects,
        "gate_scores": gate_scores,
        "summary_verdict": (
            "Abi Ear v1 benchmark packet passes deterministic local gates."
            if not defects
            else "Abi Ear v1 benchmark packet is blocked by local gate defects."
        ),
    }


def build_packet_summary(
    *,
    germ_text: str,
    germ_analysis: dict[str, object],
    variants: dict[str, object],
    moves: dict[str, object],
    prose_inventions: dict[str, object],
    gate_report: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "packet_summarizer_v1_stub",
        "benchmark_input": germ_text,
        "artifact_types": list(ABI_EAR_ARTIFACT_TYPES),
        "counts": {
            "word_forces": len(germ_analysis["word_forces"]),
            "variants": len(variants["variants"]),
            "moves": len(moves["moves"]),
            "prose_inventions": len(prose_inventions["prose_inventions"]),
        },
        "gate_summary": {
            "gate_name": gate_report["gate_name"],
            "passed": gate_report["passed"],
            "blocking_defects": gate_report["blocking_defects"],
            "summary_verdict": gate_report["summary_verdict"],
        },
        "lineage_id": ABI_EAR_LINEAGE_ID,
    }


def _predicted_delta_for_move(move_id: str) -> str:
    deltas = {
        "m01": "recognition lags behind observation",
        "m02": "object becomes evidentiary center",
        "m03": "unseen night becomes active negative space",
        "m04": "still changes from duration to pressure",
        "m05": "field resists inflation",
        "m06": "absence of removal becomes event",
        "m07": "surface details replace explanation",
        "m08": "observer inherits instability",
        "m09": "morning becomes verdict",
        "m10": "plain diction protects benchmark scale",
        "m11": "return changes grammar of the opening",
        "m12": "agency remains withheld",
        "m13": "remaining becomes stranger than vanishing",
        "m14": "measurement makes evidence tactile",
        "m15": "ending narrows rather than resolves",
        "m16": "cycle pressure enters quietly",
        "m17": "domestic order behaves like law",
        "m18": "causality is felt backward",
        "m19": "final return reprices the first sentence",
        "m20": "risk stays inside object scale",
    }
    return deltas[move_id]


def _risk_for_move(move_id: str) -> str:
    risks = {
        "m01": "may feel coy",
        "m02": "may over-symbolize the table",
        "m03": "may frustrate explanation hunger",
        "m04": "may lean too heavily on one word",
        "m05": "may feel too narrow",
        "m06": "may imply a larger plot",
        "m07": "may become decorative detail",
        "m08": "may import psychology too soon",
        "m09": "may personify morning too strongly",
        "m10": "may underplay strangeness",
        "m11": "may feel mechanical",
        "m12": "may appear evasive",
        "m13": "may invert too explicitly",
        "m14": "may over-specify proof",
        "m15": "may under-satisfy closure",
        "m16": "may imply omitted history",
        "m17": "may become allegory",
        "m18": "may confuse sequence",
        "m19": "may announce its own reread effect",
        "m20": "may be too cautious",
    }
    return risks[move_id]
