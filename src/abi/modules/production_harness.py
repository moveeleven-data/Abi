"""Deterministic Phase 4 production harness scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from abi.artifacts import ArtifactRecord, get_artifact, register_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import PHASE4_PRODUCTION_HARNESS_ACTIVE_PHASE, set_active_phase
from abi.controller.state import ensure_active_run
from abi.db import connect
from abi.hashing import sha256_file
from abi.ids import artifact_id as make_artifact_id


HARNESS_LINEAGE_ID = "production_harness_v1_fixture"
HARNESS_GATE_NAME = "production_harness_v1_fixture"
FIXTURE_RELATIVE_DIR = Path("fixtures") / "production_harness"

HARNESS_ARTIFACT_TYPES = (
    "harness_source_manifest",
    "harness_source_cards",
    "harness_claim_cards",
    "harness_motif_cards",
    "harness_image_cards",
    "harness_risk_cards",
    "harness_canon_kernel",
    "harness_artifact_genome",
    "harness_candidate_lineage",
    "harness_gate_report",
    "harness_packet",
)


@dataclass(frozen=True)
class HarnessRunResult:
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
            "packet_artifact_id": self.artifact_ids["harness_packet"],
        }


def run_production_harness_demo(config: AbiConfig) -> HarnessRunResult:
    run, _ = ensure_active_run(config)
    fixture_dir = config.root / FIXTURE_RELATIVE_DIR
    output_dir = _next_packet_dir(config.run_dir(run.id) / "harness")
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads = build_production_harness_payloads(fixture_dir)
    artifacts: dict[str, ArtifactRecord] = {}

    with connect(config.db_path) as connection:
        set_active_phase(connection, run.id, PHASE4_PRODUCTION_HARNESS_ACTIVE_PHASE)
        artifacts["harness_source_manifest"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_source_manifest",
            payload=payloads["harness_source_manifest"],
            parent_ids=[],
        )
        artifacts["harness_source_cards"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_source_cards",
            payload=payloads["harness_source_cards"],
            parent_ids=[artifacts["harness_source_manifest"].id],
        )
        artifacts["harness_claim_cards"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_claim_cards",
            payload=payloads["harness_claim_cards"],
            parent_ids=[artifacts["harness_source_cards"].id],
        )
        artifacts["harness_motif_cards"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_motif_cards",
            payload=payloads["harness_motif_cards"],
            parent_ids=[
                artifacts["harness_source_cards"].id,
                artifacts["harness_claim_cards"].id,
            ],
        )
        artifacts["harness_image_cards"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_image_cards",
            payload=payloads["harness_image_cards"],
            parent_ids=[
                artifacts["harness_source_cards"].id,
                artifacts["harness_motif_cards"].id,
            ],
        )
        artifacts["harness_risk_cards"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_risk_cards",
            payload=payloads["harness_risk_cards"],
            parent_ids=[
                artifacts["harness_claim_cards"].id,
                artifacts["harness_motif_cards"].id,
                artifacts["harness_image_cards"].id,
            ],
        )
        artifacts["harness_canon_kernel"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_canon_kernel",
            payload=payloads["harness_canon_kernel"],
            parent_ids=[
                artifacts["harness_source_manifest"].id,
                artifacts["harness_claim_cards"].id,
                artifacts["harness_motif_cards"].id,
                artifacts["harness_risk_cards"].id,
            ],
        )
        artifacts["harness_artifact_genome"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_artifact_genome",
            payload=payloads["harness_artifact_genome"],
            parent_ids=[
                artifacts["harness_canon_kernel"].id,
                artifacts["harness_image_cards"].id,
                artifacts["harness_risk_cards"].id,
            ],
        )
        artifacts["harness_candidate_lineage"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_candidate_lineage",
            payload=payloads["harness_candidate_lineage"],
            parent_ids=[
                artifacts["harness_artifact_genome"].id,
                artifacts["harness_canon_kernel"].id,
            ],
        )
        artifacts["harness_gate_report"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_gate_report",
            payload=payloads["harness_gate_report"],
            parent_ids=[
                artifacts["harness_source_manifest"].id,
                artifacts["harness_source_cards"].id,
                artifacts["harness_claim_cards"].id,
                artifacts["harness_candidate_lineage"].id,
            ],
        )
        gate_report = payloads["harness_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=run.id,
            gate_name=HARNESS_GATE_NAME,
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=HARNESS_LINEAGE_ID,
        )
        artifacts["harness_packet"] = _write_and_register(
            connection,
            run_id=run.id,
            output_dir=output_dir,
            artifact_type="harness_packet",
            payload=payloads["harness_packet"],
            parent_ids=[artifacts[artifact_type].id for artifact_type in HARNESS_ARTIFACT_TYPES[:-1]],
        )

    return HarnessRunResult(
        run_id=run.id,
        packet_id=output_dir.name,
        packet_dir=str(output_dir),
        fixture_dir=str(fixture_dir),
        artifact_ids={artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        artifact_paths={artifact_type: artifact.path for artifact_type, artifact in artifacts.items()},
        gate_result={
            "gate_name": HARNESS_GATE_NAME,
            "passed": bool(payloads["harness_gate_report"]["passed"]),
            "blocking_defects": list(payloads["harness_gate_report"]["blocking_defects"]),
            "summary_verdict": payloads["harness_gate_report"]["summary_verdict"],
        },
        payloads=payloads,
        gate_record=gate_record,
    )


def build_production_harness_payloads(fixture_dir: Path | str) -> dict[str, object]:
    sources = read_fixture_sources(Path(fixture_dir))
    source_manifest = build_source_manifest(sources)
    source_cards = build_source_cards(source_manifest, sources)
    claim_cards = build_claim_cards(source_cards)
    motif_cards = build_motif_cards(source_cards, claim_cards)
    image_cards = build_image_cards(source_cards, motif_cards)
    risk_cards = build_risk_cards(claim_cards, motif_cards, image_cards)
    canon_kernel = build_canon_kernel(source_manifest, claim_cards, motif_cards, risk_cards)
    artifact_genome = build_artifact_genome(canon_kernel, image_cards, risk_cards)
    candidate_lineage = build_candidate_lineage(artifact_genome, canon_kernel)
    gate_report = evaluate_harness_gate(
        source_manifest=source_manifest,
        source_cards=source_cards,
        claim_cards=claim_cards,
        motif_cards=motif_cards,
        image_cards=image_cards,
        risk_cards=risk_cards,
        canon_kernel=canon_kernel,
        artifact_genome=artifact_genome,
        candidate_lineage=candidate_lineage,
    )
    packet = build_harness_packet_summary(
        source_manifest=source_manifest,
        claim_cards=claim_cards,
        motif_cards=motif_cards,
        image_cards=image_cards,
        risk_cards=risk_cards,
        gate_report=gate_report,
    )
    return {
        "harness_source_manifest": source_manifest,
        "harness_source_cards": source_cards,
        "harness_claim_cards": claim_cards,
        "harness_motif_cards": motif_cards,
        "harness_image_cards": image_cards,
        "harness_risk_cards": risk_cards,
        "harness_canon_kernel": canon_kernel,
        "harness_artifact_genome": artifact_genome,
        "harness_candidate_lineage": candidate_lineage,
        "harness_gate_report": gate_report,
        "harness_packet": packet,
    }


def read_fixture_sources(fixture_dir: Path) -> list[dict[str, object]]:
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"Production harness fixture directory not found: {fixture_dir}")

    paths = sorted(fixture_dir.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No production harness Markdown fixtures found in: {fixture_dir}")

    sources = []
    for index, path in enumerate(paths, start=1):
        text = path.read_text(encoding="utf-8")
        title = _first_heading(text) or path.stem.replace("_", " ").title()
        sources.append(
            {
                "id": f"source_{index:02d}",
                "path": str(path),
                "filename": path.name,
                "title": title,
                "sha256": sha256_file(path),
                "byte_count": len(text.encode("utf-8")),
                "line_count": len(text.splitlines()),
                "text": text,
            }
        )
    return sources


def build_source_manifest(sources: list[dict[str, object]]) -> dict[str, object]:
    return {
        "worker": "production_source_manifest_builder_v1_stub",
        "source_count": len(sources),
        "sources": [
            {
                "id": source["id"],
                "path": source["path"],
                "filename": source["filename"],
                "title": source["title"],
                "sha256": source["sha256"],
                "byte_count": source["byte_count"],
                "line_count": source["line_count"],
            }
            for source in sources
        ],
    }


def build_source_cards(
    source_manifest: dict[str, object],
    sources: list[dict[str, object]],
) -> dict[str, object]:
    cards = []
    for source in sources:
        paragraphs = _paragraphs(source["text"])
        cards.append(
            {
                "id": f"card_{source['id']}",
                "source_id": source["id"],
                "title": source["title"],
                "summary": paragraphs[0],
                "supporting_excerpt": paragraphs[-1],
                "source_sha256": source["sha256"],
                "production_use": _source_use(str(source["filename"])),
            }
        )
    return {
        "worker": "production_source_card_builder_v1_stub",
        "source_manifest_count": source_manifest["source_count"],
        "source_cards": cards,
    }


def build_claim_cards(source_cards: dict[str, object]) -> dict[str, object]:
    return {
        "worker": "production_claim_card_builder_v1_stub",
        "claim_cards": [
            {
                "id": "claim_01",
                "source_card_ids": ["card_source_01"],
                "claim": "The table remains the benchmark object because ordinary matter can carry causal pressure.",
                "confidence": 0.91,
            },
            {
                "id": "claim_02",
                "source_card_ids": ["card_source_01", "card_source_02"],
                "claim": "Production should preserve the small room, unseen night, and morning verification.",
                "confidence": 0.88,
            },
            {
                "id": "claim_03",
                "source_card_ids": ["card_source_02"],
                "claim": "The opening sentence must change force after a complete crossing of the artifact.",
                "confidence": 0.93,
            },
            {
                "id": "claim_04",
                "source_card_ids": [card["id"] for card in source_cards["source_cards"]],
                "claim": "Explicit cards keep later lineage visible instead of hidden in context.",
                "confidence": 0.86,
            },
        ],
    }


def build_motif_cards(
    source_cards: dict[str, object],
    claim_cards: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_motif_card_builder_v1_stub",
        "motif_cards": [
            {
                "id": "motif_01",
                "motif": "ordinary object under causal pressure",
                "source_card_ids": ["card_source_01"],
                "claim_ids": ["claim_01"],
            },
            {
                "id": "motif_02",
                "motif": "unseen interval verified by morning",
                "source_card_ids": ["card_source_01"],
                "claim_ids": ["claim_02"],
            },
            {
                "id": "motif_03",
                "motif": "opening force altered by reread",
                "source_card_ids": ["card_source_02"],
                "claim_ids": ["claim_03"],
            },
            {
                "id": "motif_04",
                "motif": "visible lineage instead of hidden context",
                "source_card_ids": [card["id"] for card in source_cards["source_cards"]],
                "claim_ids": [card["id"] for card in claim_cards["claim_cards"]],
            },
        ],
    }


def build_image_cards(
    source_cards: dict[str, object],
    motif_cards: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_image_card_builder_v1_stub",
        "image_cards": [
            {
                "id": "image_01",
                "image": "a table still in a small room after an unseen night",
                "motif_ids": ["motif_01", "motif_02"],
                "source_card_ids": ["card_source_01"],
            },
            {
                "id": "image_02",
                "image": "morning acting as verification rather than decoration",
                "motif_ids": ["motif_02", "motif_03"],
                "source_card_ids": ["card_source_01", "card_source_02"],
            },
            {
                "id": "image_03",
                "image": "cards arranged as visible production lineage",
                "motif_ids": ["motif_04"],
                "source_card_ids": [card["id"] for card in source_cards["source_cards"]],
            },
        ],
    }


def build_risk_cards(
    claim_cards: dict[str, object],
    motif_cards: dict[str, object],
    image_cards: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_risk_card_builder_v1_stub",
        "risk_cards": [
            {
                "id": "risk_01",
                "risk": "ornament can make the table symbolic too quickly",
                "mitigation": "keep ordinary object pressure ahead of explanation",
                "claim_ids": ["claim_01"],
                "motif_ids": ["motif_01"],
                "image_ids": ["image_01"],
            },
            {
                "id": "risk_02",
                "risk": "a larger plot can erase the benchmark room",
                "mitigation": "treat the unseen night as negative space",
                "claim_ids": ["claim_02"],
                "motif_ids": ["motif_02"],
                "image_ids": ["image_02"],
            },
            {
                "id": "risk_03",
                "risk": "hidden context can make later lineage unverifiable",
                "mitigation": "derive production moves from explicit cards",
                "claim_ids": [card["id"] for card in claim_cards["claim_cards"]],
                "motif_ids": [card["id"] for card in motif_cards["motif_cards"]],
                "image_ids": [card["id"] for card in image_cards["image_cards"]],
            },
        ],
    }


def build_canon_kernel(
    source_manifest: dict[str, object],
    claim_cards: dict[str, object],
    motif_cards: dict[str, object],
    risk_cards: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_canon_kernel_builder_v1_stub",
        "kernel_id": "canon_kernel_table_morning_v1",
        "source_ids": [source["id"] for source in source_manifest["sources"]],
        "core_claim_ids": [card["id"] for card in claim_cards["claim_cards"]],
        "core_motif_ids": [card["id"] for card in motif_cards["motif_cards"]],
        "guardrail_risk_ids": [card["id"] for card in risk_cards["risk_cards"]],
        "kernel_statement": (
            "A production run must keep ordinary object pressure, reread transformation, "
            "and explicit lineage visible before any future live generation."
        ),
    }


def build_artifact_genome(
    canon_kernel: dict[str, object],
    image_cards: dict[str, object],
    risk_cards: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_artifact_genome_builder_v1_stub",
        "genome_id": "artifact_genome_table_morning_v1",
        "kernel_id": canon_kernel["kernel_id"],
        "genes": [
            {
                "id": "gene_01",
                "name": "ordinary matter first",
                "image_ids": ["image_01"],
                "risk_ids": ["risk_01"],
            },
            {
                "id": "gene_02",
                "name": "negative interval",
                "image_ids": ["image_02"],
                "risk_ids": ["risk_02"],
            },
            {
                "id": "gene_03",
                "name": "visible lineage",
                "image_ids": [card["id"] for card in image_cards["image_cards"]],
                "risk_ids": [card["id"] for card in risk_cards["risk_cards"]],
            },
        ],
    }


def build_candidate_lineage(
    artifact_genome: dict[str, object],
    canon_kernel: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_candidate_lineage_builder_v1_stub",
        "lineage_id": "candidate_lineage_fixture_v1",
        "kernel_id": canon_kernel["kernel_id"],
        "genome_id": artifact_genome["genome_id"],
        "stages": [
            {"id": "stage_01", "name": "source intake", "depends_on": []},
            {"id": "stage_02", "name": "card distillation", "depends_on": ["stage_01"]},
            {"id": "stage_03", "name": "kernel lock", "depends_on": ["stage_02"]},
            {"id": "stage_04", "name": "candidate lineage scaffold", "depends_on": ["stage_03"]},
        ],
        "not_generation": True,
    }


def evaluate_harness_gate(
    *,
    source_manifest: dict[str, object],
    source_cards: dict[str, object],
    claim_cards: dict[str, object],
    motif_cards: dict[str, object],
    image_cards: dict[str, object],
    risk_cards: dict[str, object],
    canon_kernel: dict[str, object],
    artifact_genome: dict[str, object],
    candidate_lineage: dict[str, object],
) -> dict[str, object]:
    defects = []
    if source_manifest["source_count"] < 2:
        defects.append("fewer than two fixture sources")
    if len(source_cards["source_cards"]) != source_manifest["source_count"]:
        defects.append("source card count does not match manifest")
    if len(claim_cards["claim_cards"]) < 4:
        defects.append("claim card count is too small")
    if len(motif_cards["motif_cards"]) < 4:
        defects.append("motif card count is too small")
    if len(image_cards["image_cards"]) < 3:
        defects.append("image card count is too small")
    if len(risk_cards["risk_cards"]) < 3:
        defects.append("risk card count is too small")
    if not canon_kernel["kernel_statement"]:
        defects.append("canon kernel has no kernel statement")
    if not artifact_genome["genes"]:
        defects.append("artifact genome has no genes")
    if not candidate_lineage["not_generation"]:
        defects.append("candidate lineage must remain non-generative")

    return {
        "worker": "production_harness_gate_evaluator_v1_stub",
        "gate_name": HARNESS_GATE_NAME,
        "passed": not defects,
        "blocking_defects": defects,
        "gate_scores": {
            "source_manifest": source_manifest["source_count"],
            "source_cards": len(source_cards["source_cards"]),
            "claim_cards": len(claim_cards["claim_cards"]),
            "motif_cards": len(motif_cards["motif_cards"]),
            "image_cards": len(image_cards["image_cards"]),
            "risk_cards": len(risk_cards["risk_cards"]),
            "non_generation_lineage": 1.0 if candidate_lineage["not_generation"] else 0.0,
        },
        "summary_verdict": (
            "Production harness fixture packet passes deterministic local gates."
            if not defects
            else "Production harness fixture packet is blocked by local gate defects."
        ),
    }


def build_harness_packet_summary(
    *,
    source_manifest: dict[str, object],
    claim_cards: dict[str, object],
    motif_cards: dict[str, object],
    image_cards: dict[str, object],
    risk_cards: dict[str, object],
    gate_report: dict[str, object],
) -> dict[str, object]:
    return {
        "worker": "production_harness_packet_summarizer_v1_stub",
        "artifact_types": list(HARNESS_ARTIFACT_TYPES),
        "counts": {
            "sources": source_manifest["source_count"],
            "claims": len(claim_cards["claim_cards"]),
            "motifs": len(motif_cards["motif_cards"]),
            "images": len(image_cards["image_cards"]),
            "risks": len(risk_cards["risk_cards"]),
        },
        "gate_summary": {
            "gate_name": gate_report["gate_name"],
            "passed": gate_report["passed"],
            "blocking_defects": gate_report["blocking_defects"],
            "summary_verdict": gate_report["summary_verdict"],
        },
        "lineage_id": HARNESS_LINEAGE_ID,
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
        HARNESS_LINEAGE_ID,
    )
    existing = get_artifact(connection, expected_id)
    if existing is not None:
        return existing
    return register_artifact(
        connection,
        run_id=run_id,
        artifact_type=artifact_type,
        path=path,
        lineage_id=HARNESS_LINEAGE_ID,
        parent_ids=parent_ids,
    )


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _paragraphs(text: str) -> list[str]:
    return [
        paragraph.replace("\n", " ").strip()
        for paragraph in text.split("\n\n")
        if paragraph.strip() and not paragraph.strip().startswith("#")
    ]


def _source_use(filename: str) -> str:
    if filename == "source_note.md":
        return "benchmark object and source constraints"
    if filename == "theory_fragment.md":
        return "reread success condition and lineage constraint"
    return "production fixture support"
