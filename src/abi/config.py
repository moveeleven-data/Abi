"""Runtime configuration for Abi Phase 0."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_DB_PATH = Path("db") / "abi.sqlite"
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_OUTPUTS_DIR = Path("outputs")


@dataclass(frozen=True)
class AbiConfig:
    """Filesystem locations used by the Phase 0 runtime."""

    root: Path
    db_path: Path
    runs_dir: Path
    outputs_dir: Path

    @classmethod
    def from_env(cls, root: Path | str | None = None) -> "AbiConfig":
        resolved_root = Path(root or os.getcwd()).resolve()
        return cls(
            root=resolved_root,
            db_path=_path_from_env("ABI_DB_PATH", DEFAULT_DB_PATH, resolved_root),
            runs_dir=_path_from_env("ABI_RUNS_DIR", DEFAULT_RUNS_DIR, resolved_root),
            outputs_dir=_path_from_env("ABI_OUTPUTS_DIR", DEFAULT_OUTPUTS_DIR, resolved_root),
        )

    def ensure_directories(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def output_dir(self, run_id: str) -> Path:
        return self.outputs_dir / run_id


def _path_from_env(name: str, default: Path, root: Path) -> Path:
    value = os.environ.get(name)
    path = Path(value) if value else default
    if not path.is_absolute():
        path = root / path
    return path.resolve()
