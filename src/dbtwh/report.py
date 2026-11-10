"""Markdown and figures built from a benchmark result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from dbtwh import __version__

LAYER_COLORS = {"staging": "#56b4e9", "intermediate": "#e69f00", "marts": "#009e73"}


def mib(n: float) -> str:
    return f"{n / 2**20:,.1f} MiB"


def secs(v: float) -> str:
    return f"{v:,.2f}" if v < 10 else f"{v:,.1f}"


def render_markdown(bench: dict[str, Any]) -> str:
    env = bench["environment"]
    sizes = bench["sizes"]
    out = [
        "# Benchmark",
        "",
        f"Run on {env['system']}, {env['cpus']} CPUs, Python {env['python']}, dbt-core {env['dbt-core']}, dbt-duckdb "
        f"{env['dbt-duckdb']}, DuckDB {env['duckdb']}; dbt with {env['threads']} threads; seed {env['seed']}; each time is the "
        f"median of {env['repeat']} build(s); {env['seconds']} s in all; command `{env['command']}`.",
        "",
        "## 1. Build time by size",
        "",
        "`dbt build` from an empty warehouse file: 12 models, 49 data tests and 5 unit tests, run in dependency order. "
        "*Wall* is the elapsed time dbt reports for the whole run (`run_results.json`); the other times add up what each node took, and nodes run in parallel, "
        "so they can add up to more than the wall time.",
        "",
        "| Orders | Raw rows | Raw Parquet | Wall (s) | Models (s) | Data tests (s) | Unit tests (s) | Warehouse file | Checks that match |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sizes:
        rows = sum(s["rows"].values())
        ok = f"{s['checks']} of {s['checks']}" if s["verified"] else f"MISMATCH ({len(s['mismatches'])})"
        out.append(
            f"| {s['orders']:,} | {rows:,} | {mib(s['raw_bytes'])} | {secs(s['build_s'])} | {secs(s['models_s'])} | "
            f"{secs(s['data_tests_s'])} | {secs(s['unit_tests_s'])} | {mib(s['warehouse_bytes'])} | {ok} |"
        )
    big = sizes[-1]
    out += [
        "",
        f"## 2. Each model at {big['orders']:,} orders",
        "",
        "| Model | Layer | Time (s) |",
        "|---|---|---|",
    ]
    for name, n in sorted(big["nodes"].items(), key=lambda kv: -kv[1]["median_s"]):
        out.append(f"| {name} | {n['layer']} | {secs(n['median_s'])} |")
    out += [
        "",
        "## 3. Time in each layer (sum of its models, seconds)",
        "",
        "| Orders | staging | intermediate | marts |",
        "|---|---|---|---|",
    ]
    for s in sizes:
        L = s["layers_s"]
        out.append(f"| {s['orders']:,} | {secs(L['staging'])} | {secs(L['intermediate'])} | {secs(L['marts'])} |")
    return "\n".join(out) + "\n"


def bench_figure(bench: dict[str, Any], path: Path) -> None:
    sizes = bench["sizes"]
    n = [s["orders"] for s in sizes]
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    a.plot(n, [s["build_s"] for s in sizes], marker="o", color="#0072b2", label="whole build (wall)")
    a.plot(n, [s["models_s"] for s in sizes], marker="s", ls="--", color="#009e73", label="models (sum)")
    a.plot(n, [s["data_tests_s"] for s in sizes], marker="^", ls="--", color="#d55e00", label="data tests (sum)")
    a.set_xscale("log")
    a.set_ylim(0, None)
    a.set_xticks(n, [f"{v:,}" for v in n])
    a.set_xlabel("orders (about 2.2 order lines each)")
    a.set_ylabel("seconds")
    a.set_title("dbt build time against size")
    a.legend(fontsize=8)
    a.grid(alpha=0.25)
    big = sizes[-1]
    items = sorted(big["nodes"].items(), key=lambda kv: kv[1]["median_s"])
    b.barh([k for k, _ in items], [v["median_s"] for _, v in items], color=[LAYER_COLORS[v["layer"]] for _, v in items])
    for i, (_, v) in enumerate(items):
        b.text(v["median_s"], i, f" {v['median_s']:.2f}", va="center", fontsize=8)
    b.set_xlabel("seconds")
    b.set_title(f"Each model at {big['orders']:,} orders")
    handles = [Rectangle((0, 0), 1, 1, color=c) for c in LAYER_COLORS.values()]
    b.legend(handles, list(LAYER_COLORS), loc="lower right", fontsize=8)
    fig.suptitle(
        f"dbtwh {__version__}: dbt {bench['environment']['dbt-core']} on DuckDB {bench['environment']['duckdb']}",
        fontsize=10,
    )
    fig.savefig(path, dpi=130)
    plt.close(fig)
