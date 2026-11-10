"""Build time of the whole warehouse for growing amounts of raw data, with every mart checked after each build."""

from __future__ import annotations

import os
import platform
import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dbtwh import __version__, gen, runner, verify


def environment(command: str, **extra: object) -> dict[str, object]:
    v = runner.versions()
    return {
        "dbtwh": __version__,
        "python": platform.python_version(),
        **v,
        "system": f"{platform.system()} {platform.machine()}",
        "cpus": os.cpu_count(),
        "command": command,
        **extra,
    }


def median(values: list[float]) -> float:
    return statistics.median(values)


def run_size(
    orders: int, repeat: int, seed: int, threads: int, workdir: Path, fmt: str, progress: Callable[[str], None]
) -> dict[str, Any]:
    raw = workdir / f"raw_{orders}"
    progress(f"{orders:,} orders: generating")
    t0 = time.perf_counter()
    rows = gen.write(orders, seed, raw, fmt)
    gen_s = time.perf_counter() - t0
    raw_bytes = sum(f.stat().st_size for f in raw.glob(f"*.{fmt}"))
    db = workdir / f"wh_{orders}.duckdb"
    walls: list[float] = []
    runs: list[runner.BuildResult] = []
    for i in range(repeat):
        progress(f"{orders:,} orders: dbt build {i + 1} of {repeat}")
        res = runner.build(raw, db, workdir / f"dbt_{orders}", threads, fmt, quiet=True)
        if not res.success:
            names = ", ".join(n.name for n in res.failed())
            raise runner.BuildError(f"dbt build failed at {orders:,} orders: {names}")
        walls.append(res.seconds)
        runs.append(res)
    progress(f"{orders:,} orders: checking every mart against the independent calculation")
    checks = verify.verify(raw, db)
    nodes: dict[str, dict[str, object]] = {}
    for name in (n.name for n in runs[0].nodes if n.kind == "model"):
        secs = [next(n.seconds for n in r.nodes if n.name == name and n.kind == "model") for r in runs]
        nodes[name] = {"layer": runner.layer_of(name), "median_s": median(secs)}
    last = runs[-1]
    out = {
        "orders": orders,
        "rows": rows,
        "raw_bytes": raw_bytes,
        "generate_s": gen_s,
        "build_s": median(walls),
        "models_s": median([r.kind_seconds("model") for r in runs]),
        "data_tests_s": median([r.kind_seconds("test") for r in runs]),
        "unit_tests_s": median([r.kind_seconds("unit_test") for r in runs]),
        "layers_s": {
            layer: median([r.layer_seconds(layer) for r in runs]) for layer in ("staging", "intermediate", "marts")
        },
        "nodes": nodes,
        "summary": runner.summary(last),
        "warehouse_bytes": db.stat().st_size,
        "checks": len(checks),
        "verified": all(c.ok for c in checks),
        "mismatches": [f"{c.name}: {c.detail}" for c in checks if not c.ok],
    }
    for f in raw.glob("*"):
        f.unlink()
    raw.rmdir()
    db.unlink(missing_ok=True)
    return out


def run_bench(
    sizes: list[int],
    repeat: int,
    seed: int,
    threads: int,
    command: str,
    workdir: Path | None = None,
    fmt: str = "parquet",
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        results = [run_size(n, repeat, seed, threads, Path(tmp), fmt, progress) for n in sizes]
    env = environment(
        command, seed=seed, repeat=repeat, threads=threads, format=fmt, seconds=round(time.perf_counter() - t0, 1)
    )
    return {"environment": env, "sizes": results}
