"""The documentation must say what the measurements say."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dbtwh import cli

ROOT = Path(__file__).resolve().parent.parent
BENCH = json.loads((ROOT / "docs" / "bench.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
ANALYSIS = (ROOT / "docs" / "analysis.md").read_text(encoding="utf-8")
S = {s["orders"]: s for s in BENCH["sizes"]}
SMALL, MID, BIG = S[10_000], S[100_000], S[1_000_000]


def sec(v: float) -> str:
    return f"{v:,.2f}" if v < 10 else f"{v:,.1f}"


def mib(n: float) -> str:
    return f"{n / 2**20:,.1f} MiB"


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def rows(s: dict[str, object]) -> int:
    return sum(s["rows"].values())  # type: ignore[attr-defined, no-any-return]


def test_the_benchmark_is_what_the_text_says_it_is() -> None:
    env = BENCH["environment"]
    assert env["dbtwh"] == "1.0.0" and env["seed"] == 1 and env["repeat"] == 5 and env["threads"] == 4
    assert env["cpus"] == 12 and env["format"] == "parquet" and env["python"] == "3.14.10"
    assert (env["dbt-core"], env["dbt-duckdb"], env["duckdb"], env["numpy"]) == ("1.12.6", "1.11.1", "2.0.0", "2.5.4")
    assert sorted(S) == [10_000, 100_000, 1_000_000]
    for s in S.values():
        assert s["summary"] == {"models": 12, "data_tests": 49, "unit_tests": 5, "passed": 66, "failed": 0}
        assert s["checks"] == 31 and s["verified"] is True and s["mismatches"] == []


def test_bench_markdown_is_the_render_of_the_json(tmp_path: Path) -> None:
    out = tmp_path / "again.md"
    assert cli.main(["render", str(ROOT / "docs" / "bench.json"), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == (ROOT / "docs" / "bench.md").read_text(encoding="utf-8")


def test_figure_exists() -> None:
    assert (ROOT / "docs" / "summary.png").stat().st_size > 10_000


@pytest.mark.parametrize("text", [README, ANALYSIS], ids=["README", "analysis"])
def test_no_scaffold_left(text: str) -> None:
    assert not re.search(r"work in progress|TODO|TBD|lorem|measurements pending|provisional", text, re.I)


@pytest.mark.parametrize("name", ["README.md", "docs/analysis.md"])
def test_local_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target).exists(), f"{name}: broken link {target}"


def test_readme_headline_numbers() -> None:
    assert f"({rows(SMALL):,} raw rows)" in README and f"({rows(BIG):,} raw rows)" in README
    assert f"{sec(BIG['build_s'])} s**, against {sec(SMALL['build_s'])} s for 10,000" in README
    assert f"{rows(BIG) / rows(SMALL):.1f} times the rows for {BIG['build_s'] / SMALL['build_s']:.2f} times" in README
    assert f"models take {sec(BIG['models_s'])} s" in README and f"data tests {sec(BIG['data_tests_s'])} s" in README
    assert f"unit tests {sec(BIG['unit_tests_s'])} s" in README
    for s in (SMALL, BIG):
        share = s["data_tests_s"] / (s["models_s"] + s["data_tests_s"] + s["unit_tests_s"])
        assert pct(share) in README
    L0, L1 = SMALL["layers_s"], BIG["layers_s"]
    assert f"{sec(L1['staging'])} s at every size" in README and L0["staging"] == pytest.approx(L1["staging"], abs=0.05)
    assert f"({sec(L0['intermediate'])} s to {sec(L1['intermediate'])} s)" in README
    assert f"({sec(L0['marts'])} s to {sec(L1['marts'])} s)" in README
    slowest = max(BIG["nodes"].items(), key=lambda kv: kv[1]["median_s"])
    assert slowest[0] == "fct_orders" and f"`fct_orders`, {sec(slowest[1]['median_s'])} s" in README
    assert (
        f"{mib(BIG['warehouse_bytes'])} at 1,000,000" in README and f"{mib(BIG['raw_bytes'])} of compressed" in README
    )
    assert f"{BIG['warehouse_bytes'] / BIG['raw_bytes']:.1f} times" in README


def test_analysis_tables_match_the_json() -> None:
    for s in S.values():
        n = s["orders"]
        assert f"| {n:,} | {rows(s):,} | 66 of 66 | 31 of 31 |" in ANALYSIS
        t = f"| {n:,} | {sec(s['build_s'])} | {sec(s['models_s'])} | {sec(s['data_tests_s'])} | {sec(s['unit_tests_s'])} |"
        assert t in ANALYSIS
        L = s["layers_s"]
        assert f"| {n:,} | {sec(L['staging'])} | {sec(L['intermediate'])} | {sec(L['marts'])} |" in ANALYSIS
        assert f"| {n:,} | {mib(s['raw_bytes'])} | {mib(s['warehouse_bytes'])} |" in ANALYSIS


def test_analysis_derived_claims() -> None:
    assert (
        f"{rows(BIG) / rows(SMALL):.1f} times (rows), the build {BIG['build_s'] / SMALL['build_s']:.2f} times"
        in ANALYSIS
    )
    assert f"data tests' {BIG['data_tests_s'] / SMALL['data_tests_s']:.2f} times" in ANALYSIS
    assert f"{BIG['models_s'] / SMALL['models_s']:.2f} times," in ANALYSIS
    assert f"{BIG['unit_tests_s'] / SMALL['unit_tests_s']:.2f} times, within noise" in ANALYSIS
    shares = [s["data_tests_s"] / (s["models_s"] + s["data_tests_s"] + s["unit_tests_s"]) for s in (SMALL, MID, BIG)]
    assert f"{pct(shares[0])}, {pct(shares[1])} and {pct(shares[2])}" in ANALYSIS
    total = BIG["models_s"] + BIG["data_tests_s"] + BIG["unit_tests_s"]
    assert f"nodes add up to {total:.2f} s" in ANALYSIS
    assert f"about {round(1_000_000 / BIG['build_s'], -3):,.0f} orders per second" in ANALYSIS
    L0, L1 = SMALL["layers_s"], BIG["layers_s"]
    assert (
        f"grow {L1['intermediate'] / L0['intermediate']:.1f} times and the marts {L1['marts'] / L0['marts']:.1f} times"
        in ANALYSIS
    )
    assert f"{L1['staging'] / L0['staging']:.1f} times)" in ANALYSIS
    nodes = BIG["nodes"]
    for name in ("fct_orders", "int_order_totals", "int_order_payments"):
        assert (
            f"{name}` ({sec(nodes[name]['median_s'])} s)" in ANALYSIS
            or f"({sec(nodes[name]['median_s'])} s)" in ANALYSIS
        )
    assert f"{BIG['warehouse_bytes'] / BIG['raw_bytes']:.1f} times the raw size" in ANALYSIS


def test_readme_output_matches_a_real_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["demo", "--orders", "10000", "--seed", "1", "--threads", "2", "--out", str(tmp_path)]) == 0
    got = capsys.readouterr().out.strip().splitlines()
    block = re.search(r"```text\n(.*?)```", README, re.S)
    assert block is not None
    want = block.group(1).strip().splitlines()
    assert got[0] == want[0]
    assert re.sub(r", in [\d.]+ s$", "", got[1]) == re.sub(r", in [\d.]+ s$", "", want[1])
    assert got[-1] == want[-1]
    assert sum(line.startswith("ok   ") for line in got) == 31
