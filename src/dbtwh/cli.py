"""Command line: generate, build, verify, demo, bench, render."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from dbtwh import __version__, bench, gen, report, runner, verify


def parse_sizes(text: str) -> list[int]:
    try:
        sizes = [int(p.replace("_", "")) for p in text.split(",") if p.strip()]
    except ValueError as exc:
        raise gen.GenError(f"--sizes must be integers separated by commas ({exc})") from exc
    if not sizes or any(s < gen.MIN_ORDERS for s in sizes):
        raise gen.GenError(f"--sizes needs at least one size, each of {gen.MIN_ORDERS} orders or more")
    return sizes


def cmd_generate(a: argparse.Namespace) -> int:
    counts = gen.write(a.orders, a.seed, Path(a.out), a.format)
    print(f"written: {len(counts)} {a.format} files and manifest.json in {a.out}")
    print(", ".join(f"{v:,} {k}" for k, v in counts.items()))
    return 0


def print_build(res: runner.BuildResult) -> None:
    s = runner.summary(res)
    print(f"dbt build: {s['models']} models, {s['data_tests']} data tests, {s['unit_tests']} unit tests: "
          f"{s['passed']} passed, {s['failed']} failed, in {res.seconds:.1f} s")  # fmt: skip
    for n in res.failed():
        print(f"  FAILED {n.kind} {n.name}")


def cmd_build(a: argparse.Namespace) -> int:
    raw, work = Path(a.raw), Path(a.workdir)
    db = Path(a.db) if a.db else work / "warehouse.duckdb"
    res = runner.build(raw, db, work, a.threads, a.format, quiet=a.quiet)
    print_build(res)
    if a.docs:
        print(f"documentation: {runner.docs(raw, db, work, a.threads, a.format)}")
    print(f"warehouse: {db}")
    return 0 if res.success else 1


def print_checks(checks: list[verify.Check]) -> int:
    bad = [c for c in checks if not c.ok]
    for c in checks:
        print(f"{'ok  ' if c.ok else 'FAIL'} {c.name} ({c.rows:,} rows){'' if c.ok else ': ' + c.detail}")
    print(f"{len(checks) - len(bad)} of {len(checks)} checks match the independent calculation")
    return 1 if bad else 0


def cmd_verify(a: argparse.Namespace) -> int:
    raw, work = Path(a.raw), Path(a.workdir)
    db = Path(a.db) if a.db else work / "warehouse.duckdb"
    return print_checks(verify.verify(raw, db))


def cmd_demo(a: argparse.Namespace) -> int:
    out = Path(a.out)
    raw, work = out / "raw", out / "dbt"
    counts = gen.write(a.orders, a.seed, raw, a.format)
    print(", ".join(f"{v:,} {k}" for k, v in counts.items()))
    res = runner.build(raw, work / "warehouse.duckdb", work, a.threads, a.format, quiet=True)
    print_build(res)
    code = print_checks(verify.verify(raw, work / "warehouse.duckdb"))
    return 1 if (code or not res.success) else 0


def cmd_bench(a: argparse.Namespace) -> int:
    def progress(msg: str) -> None:
        print(msg, flush=True)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    result = bench.run_bench(
        parse_sizes(a.sizes),
        a.repeat,
        a.seed,
        a.threads,
        a.cmdline,
        Path(a.workdir) if a.workdir else None,
        a.format,
        progress,
    )
    (out / "bench.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    (out / "bench.md").write_text(report.render_markdown(result), encoding="utf-8")
    report.bench_figure(result, out / "summary.png")
    print(f"written: {out / 'bench.json'}, {out / 'bench.md'}, {out / 'summary.png'}")
    return 0 if all(s["verified"] for s in result["sizes"]) else 1


def cmd_render(a: argparse.Namespace) -> int:
    data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    text = report.render_markdown(data)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"written: {a.output}")
    else:
        print(text, end="")
    if a.figure:
        report.bench_figure(data, Path(a.figure))
        print(f"written: {a.figure}")
    return 0


def cmd_project(a: argparse.Namespace) -> int:
    """Copy the dbt project out of the package, to read it or to run dbt by hand."""
    dest = Path(a.out)
    if dest.exists():
        raise gen.GenError(f"{dest} already exists")
    shutil.copytree(runner.PROJECT, dest, ignore=shutil.ignore_patterns("__pycache__", "target", "logs"))
    print(f"written: the dbt project in {dest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dbtwh", description="A dbt + DuckDB warehouse, checked against an independent calculation."
    )
    p.add_argument("--version", action="version", version=f"dbtwh {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--format", choices=["parquet", "csv"], default="parquet")

    g = sub.add_parser("generate", help="write raw files (customers, products, orders, order_items, payments)")
    g.add_argument("--orders", type=int, default=10_000)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--out", default="raw")
    common(g)
    g.set_defaults(func=cmd_generate)

    b = sub.add_parser("build", help="dbt build: models, data tests and unit tests; exit 1 if any fails")
    b.add_argument("--raw", default="raw")
    b.add_argument("--db", help="warehouse file (default: WORKDIR/warehouse.duckdb)")
    b.add_argument("--workdir", default="dbt-out", help="where dbt writes target/ and logs/")
    b.add_argument("--threads", type=int, default=4)
    b.add_argument("--docs", action="store_true", help="also write the static documentation page")
    b.add_argument("--quiet", action="store_true")
    common(b)
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("verify", help="compare every mart with the independent calculation; exit 1 on a difference")
    v.add_argument("--raw", default="raw")
    v.add_argument("--db")
    v.add_argument("--workdir", default="dbt-out")
    v.set_defaults(func=cmd_verify)

    d = sub.add_parser("demo", help="generate, build and verify in one go")
    d.add_argument("--orders", type=int, default=10_000)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--threads", type=int, default=4)
    d.add_argument("--out", default="demo")
    common(d)
    d.set_defaults(func=cmd_demo)

    n = sub.add_parser("bench", help="build time for growing sizes; every mart is checked after each build")
    n.add_argument("--sizes", default="10000,100000,1000000")
    n.add_argument("--repeat", type=int, default=3)
    n.add_argument("--seed", type=int, default=1)
    n.add_argument("--threads", type=int, default=4)
    n.add_argument(
        "--workdir", help="where the generated files go while running (default: the system temporary folder)"
    )
    n.add_argument("--out", default="dbtwh-out")
    common(n)
    n.set_defaults(func=cmd_bench)

    r = sub.add_parser("render", help="rebuild the Markdown (and the figure) from bench.json")
    r.add_argument("file")
    r.add_argument("-o", "--output")
    r.add_argument("--figure")
    r.set_defaults(func=cmd_render)

    pr = sub.add_parser("project", help="copy the dbt project to a folder")
    pr.add_argument("out")
    pr.set_defaults(func=cmd_project)
    return p


def main(argv: list[str] | None = None) -> int:
    given = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(given)
    args.cmdline = " ".join(given)
    try:
        return int(args.func(args))
    except (gen.GenError, runner.BuildError, verify.VerifyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
