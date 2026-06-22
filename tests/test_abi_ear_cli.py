import ast
import json
from pathlib import Path

from abi.cli import main
from abi.modules.abi_ear import ABI_EAR_ARTIFACT_TYPES, BENCHMARK_INPUT


def test_abi_ear_demo_cli_outputs_summary(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    exit_code = main(["--root", str(tmp_path), "ear", "demo"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["benchmark_input"] == BENCHMARK_INPUT
    assert payload["packet_id"] == "packet_0001"
    assert set(payload["artifact_ids"]) == set(ABI_EAR_ARTIFACT_TYPES)
    assert payload["packet_artifact_id"] == payload["artifact_ids"]["abi_ear_packet"]
    assert payload["gate_result"]["passed"] is True
    assert Path(payload["packet_dir"]) == (
        tmp_path / "runs" / payload["run_id"] / "abi_ear" / "packet_0001"
    )
    assert Path(payload["packet_dir"]).is_dir()


def test_readme_describes_abi():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert readme.startswith("# Abi")
    assert "germ -> differentiation -> pressure -> crisis -> recomposition -> return" in readme


def test_source_uses_no_model_or_api_client_imports():
    cli_source = Path("src/abi/cli.py").read_text(encoding="utf-8")
    assert "abi.modules.human_calibration" not in cli_source
    assert "abi.modules.evaluation" not in cli_source
    assert "abi.modules.final_artifact" not in cli_source
    assert "export-reader-kit" not in cli_source

    forbidden_import_roots = {"openai", "requests", "httpx", "urllib", "socket"}
    forbidden_source_markers = {
        "api_key",
        "chat.completions",
        "responses.create",
    }
    live_adapter_paths = {
        Path("src/abi/live_model.py"),
        Path("src/abi/openai_adapter.py"),
        Path("src/abi/modules/autonomous_revision.py"),
        Path("src/abi/modules/internal_reader_lab.py"),
        Path("src/abi/modules/internal_reader_state_evaluation.py"),
        Path("src/abi/modules/ablation_informed_revision.py"),
        Path("src/abi/modules/bounded_macro_recomposition.py"),
        Path("src/abi/modules/live_abi_ear.py"),
        Path("src/abi/modules/live_reread.py"),
        Path("src/abi/modules/production_run.py"),
        Path("src/abi/modules/evaluation.py"),
        Path("src/abi/modules/executed_ablation.py"),
        Path("src/abi/modules/final_artifact.py"),
        Path("src/abi/modules/pilot_artifact_set.py"),
    }

    for path in Path("src/abi").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", maxsplit=1)[0])

        assert not (imported_roots & forbidden_import_roots), path
        if path in live_adapter_paths:
            continue
        lowered = source.lower()
        for marker in forbidden_source_markers:
            assert marker not in lowered, path
