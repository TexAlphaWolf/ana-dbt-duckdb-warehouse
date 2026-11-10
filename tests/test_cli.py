from __future__ import annotations

import json
from pathlib import Path

import pytest

from dbtwh import cli

from .conftest import Warehouse


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_generate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "generate", "--orders", "300", "--seed", "5", "--out", str(tmp_path / "r"))
    assert code == 0 and "written: 5 parquet files and manifest.json" in out
    assert (tmp_path / "r" / "orders.parquet").exists()


def test_build_then_verify(warehouse: Warehouse, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        capsys, "build", "--raw", str(warehouse.raw), "--db", str(warehouse.work / "again.duckdb"),
        "--workdir", str(warehouse.work), "--threads", "2", "--quiet",
    )  # fmt: skip
    assert code == 0 and "12 models, 49 data tests, 5 unit tests: 66 passed, 0 failed" in out
    code, out, _ = run(capsys, "verify", "--raw", str(warehouse.raw), "--db", str(warehouse.db))
    assert code == 0 and "31 of 31 checks match the independent calculation" in out


def test_verify_exit_code_is_1_on_a_difference(
    warehouse: Warehouse, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil

    import duckdb

    db = tmp_path / "x.duckdb"
    shutil.copyfile(warehouse.db, db)
    con = duckdb.connect(str(db))
    con.execute("update dim_products set units_sold = units_sold + 1")
    con.close()
    code, out, _ = run(capsys, "verify", "--raw", str(warehouse.raw), "--db", str(db))
    assert code == 1 and "FAIL dim_products.units_sold" in out and "30 of 31" in out


def test_demo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "demo", "--orders", "300", "--threads", "2", "--out", str(tmp_path / "d"))
    assert code == 0 and "31 of 31 checks match" in out and "66 passed, 0 failed" in out


def test_docs_flag_writes_the_page(warehouse: Warehouse, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        capsys, "build", "--raw", str(warehouse.raw), "--db", str(warehouse.work / "d2.duckdb"),
        "--workdir", str(warehouse.work), "--threads", "2", "--quiet", "--docs",
    )  # fmt: skip
    assert code == 0 and "documentation:" in out and "static_index.html" in out


def test_bench_render_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "b"
    code, out, _ = run(
        capsys, "bench", "--sizes", "200,400", "--repeat", "1", "--threads", "2", "--out", str(out_dir),
        "--workdir", str(tmp_path),
    )  # fmt: skip
    assert code == 0 and "written:" in out
    data = json.loads((out_dir / "bench.json").read_text(encoding="utf-8"))
    assert [s["orders"] for s in data["sizes"]] == [200, 400] and all(s["verified"] for s in data["sizes"])
    assert data["sizes"][0]["checks"] == 31 and data["environment"]["repeat"] == 1
    assert (out_dir / "summary.png").read_bytes()[1:4] == b"PNG"
    again = tmp_path / "again.md"
    code, _, _ = run(
        capsys, "render", str(out_dir / "bench.json"), "-o", str(again), "--figure", str(tmp_path / "f.png")
    )
    assert code == 0 and again.read_text(encoding="utf-8") == (out_dir / "bench.md").read_text(encoding="utf-8")
    code, out, _ = run(capsys, "render", str(out_dir / "bench.json"))
    assert code == 0 and out.startswith("# Benchmark")
    assert not list(tmp_path.glob("tmp*"))  # the generated files are removed


def test_project_copies_the_dbt_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(capsys, "project", str(tmp_path / "p"))
    assert (
        code == 0 and (tmp_path / "p" / "dbt_project.yml").exists() and (tmp_path / "p" / "models" / "marts").is_dir()
    )
    code, _, err = run(capsys, "project", str(tmp_path / "p"))
    assert code == 2 and "already exists" in err


@pytest.mark.parametrize(
    "args",
    [
        ["generate", "--orders", "5"],
        ["bench", "--sizes", "abc"],
        ["bench", "--sizes", "50"],
        ["build", "--raw", "/nonexistent"],
        ["verify", "--raw", "/nonexistent"],
    ],
)
def test_errors_are_exit_code_2(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, *args)
    assert code == 2 and err.startswith("error:")


def test_no_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 2
