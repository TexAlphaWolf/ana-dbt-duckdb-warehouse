from __future__ import annotations

from pathlib import Path

import pytest

from dbtwh import bench, report, runner


def test_run_bench_records_times_and_checks(tmp_path: Path) -> None:
    msgs: list[str] = []
    res = bench.run_bench([200, 400], 2, 3, 2, "bench --sizes 200,400", tmp_path, progress=msgs.append)
    assert [s["orders"] for s in res["sizes"]] == [200, 400]
    for s in res["sizes"]:
        assert s["verified"] and s["checks"] == 31 and s["mismatches"] == []
        assert s["summary"]["passed"] == 66 and s["build_s"] > 0 and s["warehouse_bytes"] > 0
        assert set(s["layers_s"]) == {"staging", "intermediate", "marts"}
        assert len(s["nodes"]) == 12 and s["rows"]["orders"] >= s["orders"]
    env = res["environment"]
    assert env["seed"] == 3 and env["repeat"] == 2 and env["threads"] == 2 and env["format"] == "parquet"
    assert any("dbt build 2 of 2" in m for m in msgs)
    assert not list(tmp_path.iterdir())  # generated files and warehouses are removed


def test_render_is_a_pure_function_of_the_json(tmp_path: Path) -> None:
    res = bench.run_bench([200], 1, 1, 2, "x", tmp_path)
    text = report.render_markdown(res)
    assert text == report.render_markdown(res)
    assert "| 200 |" in text and "1 build(s)" in text and "31 of 31" in text
    res["sizes"][0]["verified"] = False
    res["sizes"][0]["mismatches"] = ["a: b"]
    assert "MISMATCH (1)" in report.render_markdown(res)


def test_a_failing_build_stops_the_benchmark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*_a: object, **_k: object) -> runner.BuildResult:
        return runner.BuildResult(False, 1.0, [runner.Node("fct_orders", "model", "marts", "error", 0.1)])

    monkeypatch.setattr(runner, "build", failing)
    with pytest.raises(runner.BuildError, match="fct_orders"):
        bench.run_bench([200], 1, 1, 2, "x", tmp_path)
