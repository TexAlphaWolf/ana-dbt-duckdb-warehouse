"""Running dbt (as a library, in this process) and reading what it reports."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent / "dbt_project"
LAYERS = {"stg_": "staging", "int_": "intermediate"}


class BuildError(RuntimeError):
    """dbt could not run (a bad project, no raw files); a failing test is not this: it is in the result."""


def layer_of(name: str) -> str:
    for prefix, layer in LAYERS.items():
        if name.startswith(prefix):
            return layer
    return "marts"


@dataclass
class Node:
    name: str
    kind: str  # model, test, unit_test
    layer: str  # staging, intermediate, marts (tests and unit tests: the layer of what they test is not tracked)
    status: str
    seconds: float


@dataclass
class BuildResult:
    success: bool
    seconds: float  # wall time of the dbt command
    nodes: list[Node] = field(default_factory=list)

    def count(self, kind: str, status: str | None = None) -> int:
        return sum(1 for n in self.nodes if n.kind == kind and (status is None or n.status == status))

    def failed(self) -> list[Node]:
        return [n for n in self.nodes if n.status in ("fail", "error")]

    def layer_seconds(self, layer: str) -> float:
        return sum(n.seconds for n in self.nodes if n.kind == "model" and n.layer == layer)

    def kind_seconds(self, kind: str) -> float:
        return sum(n.seconds for n in self.nodes if n.kind == kind)


def versions() -> dict[str, str]:
    return {p: metadata.version(p) for p in ("dbt-core", "dbt-duckdb", "duckdb", "numpy")}


def parse_run_results(path: Path) -> list[Node]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[Node] = []
    for r in data["results"]:
        uid: str = r["unique_id"]
        parts = uid.split(".")
        kind = {"model": "model", "test": "test", "unit_test": "unit_test"}.get(parts[0], parts[0])
        name = parts[2]
        out.append(
            Node(name, kind, layer_of(name) if kind == "model" else "-", r["status"], float(r["execution_time"]))
        )
    return out


def run_dbt(
    command: list[str], raw: Path, db: Path, workdir: Path, threads: int = 4, fmt: str = "parquet", quiet: bool = False
) -> BuildResult:
    """Run one dbt command against raw files in `raw`, writing the warehouse to `db` and dbt's files to `workdir`.

    dbt runs in its own process: it keeps the DuckDB file open for as long as it lives, and a child process also keeps
    its settings (environment, paths) out of this one.
    """
    if not raw.is_dir():
        raise BuildError(f"{raw} is not a folder of raw files")
    ext = "csv" if fmt == "csv" else "parquet"
    if not (raw / f"orders.{ext}").exists():
        raise BuildError(f"{raw / ('orders.' + ext)} not found: run 'dbtwh generate' first (format {fmt})")
    workdir.mkdir(parents=True, exist_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)
    profiles = workdir / "profiles"  # dbt writes a small file next to profiles.yml: keep that out of the package
    profiles.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT / "profiles.yml", profiles / "profiles.yml")
    env = {
        **os.environ,
        "WH_RAW": str(raw),
        "WH_DB": str(db),
        "WH_THREADS": str(threads),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        "DBT_VERSION_CHECK": "false",
    }
    args = [
        sys.executable, "-c", "from dbt.cli.main import cli; cli()",
        *(["--quiet"] if quiet else []),
        *command,
        "--project-dir", str(PROJECT),
        "--profiles-dir", str(profiles),
        "--target-path", str(workdir / "target"),
        "--log-path", str(workdir / "logs"),
    ]  # fmt: skip
    if fmt == "csv":
        args += ["--vars", json.dumps({"raw_reader": "read_csv", "raw_ext": "csv"})]
    rr = workdir / "target" / "run_results.json"
    rr.unlink(missing_ok=True)  # so that a result file means this run wrote it
    try:
        proc = subprocess.run(args, env=env, capture_output=quiet, text=True, check=False)
    except OSError as exc:  # pragma: no cover
        raise BuildError(f"could not start dbt: {exc}") from exc
    if proc.returncode not in (0, 1) or (proc.returncode == 1 and not rr.exists() and command[0] != "docs"):
        # exit code 1 with results is "ran, and something failed"; anything else is dbt itself failing
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-8:]
        raise BuildError(f"dbt could not run (exit code {proc.returncode}). " + " | ".join(tail))
    nodes = parse_run_results(rr) if rr.exists() else []
    elapsed = float(json.loads(rr.read_text(encoding="utf-8")).get("elapsed_time", 0.0)) if rr.exists() else 0.0
    return BuildResult(proc.returncode == 0, elapsed, nodes)


def build(
    raw: Path, db: Path, workdir: Path, threads: int = 4, fmt: str = "parquet", quiet: bool = False
) -> BuildResult:
    """`dbt build`: models, data tests and unit tests, in dependency order, from a fresh warehouse file."""
    if db.exists():
        db.unlink()
    return run_dbt(["build"], raw, db, workdir, threads, fmt, quiet)


def docs(raw: Path, db: Path, workdir: Path, threads: int = 4, fmt: str = "parquet") -> Path:
    """`dbt docs generate --static`: one HTML file with the lineage graph and every description."""
    run_dbt(["docs", "generate", "--static"], raw, db, workdir, threads, fmt, quiet=True)
    out = workdir / "target" / "static_index.html"
    if not out.exists():
        raise BuildError("dbt did not write static_index.html")
    return out


def summary(res: BuildResult) -> dict[str, Any]:
    return {
        "models": res.count("model"),
        "data_tests": res.count("test"),
        "unit_tests": res.count("unit_test"),
        "passed": sum(1 for n in res.nodes if n.status in ("pass", "success")),
        "failed": len(res.failed()),
    }
