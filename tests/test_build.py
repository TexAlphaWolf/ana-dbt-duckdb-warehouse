"""A real dbt build, and the proof that the checks can fail."""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from dbtwh import gen, runner, verify

from .conftest import Warehouse


def test_build_passes_everything(warehouse: Warehouse) -> None:
    s = runner.summary(warehouse.result)
    assert s == {"models": 12, "data_tests": 49, "unit_tests": 5, "passed": 66, "failed": 0}
    assert warehouse.result.success and warehouse.result.seconds > 0


def test_layers_and_timings(warehouse: Warehouse) -> None:
    res = warehouse.result
    layers = {n.layer for n in res.nodes if n.kind == "model"}
    assert layers == {"staging", "intermediate", "marts"}
    assert all(res.layer_seconds(layer) > 0 for layer in layers)
    assert res.kind_seconds("test") > 0 and res.kind_seconds("unit_test") > 0


def test_every_mart_matches_the_independent_calculation(warehouse: Warehouse) -> None:
    checks = verify.verify(warehouse.raw, warehouse.db)
    assert len(checks) == 31
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_verify_notices_a_wrong_number(warehouse: Warehouse, tmp_path: Path) -> None:
    db = tmp_path / "copy.duckdb"
    shutil.copyfile(warehouse.db, db)
    con = duckdb.connect(str(db))
    try:
        con.execute("update fct_orders set net_cents = net_cents + 1 where order_id = 7")
        con.execute("update mart_monthly_revenue set net_revenue_cents = net_revenue_cents - 100")
    finally:
        con.close()
    bad = {c.name for c in verify.verify(warehouse.raw, db) if not c.ok}
    assert "fct_orders.net_cents" in bad and "mart_monthly_revenue.net_revenue_cents" in bad
    assert "fct_orders.units" not in bad


def test_verify_errors(warehouse: Warehouse, tmp_path: Path) -> None:
    with pytest.raises(verify.VerifyError):
        verify.verify(warehouse.raw, tmp_path / "none.duckdb")
    with pytest.raises(verify.VerifyError):
        verify.verify(tmp_path, warehouse.db)


def test_dbt_tests_catch_bad_raw_data(tmp_path: Path) -> None:
    """An order line for a product that does not exist, and a negative quantity: dbt must say so."""
    raw = tmp_path / "raw"
    gen.write(300, 1, raw)
    lines = raw / "order_items.parquet"
    con = duckdb.connect()
    try:
        con.execute(
            f"copy (select * from '{lines.as_posix()}' union all select 1, 99, 999999, -2, 100, 0) "
            f"to '{(raw / 'bad.parquet').as_posix()}' (format parquet)"
        )
    finally:
        con.close()
    (raw / "bad.parquet").replace(lines)
    res = runner.build(raw, tmp_path / "w.duckdb", tmp_path / "dbt", threads=2, quiet=True)
    assert not res.success
    names = [n.name for n in res.failed()]
    assert any("relationships" in n and "product" in n for n in names), names
    assert any("non_negative" in n or "revenue_reconciles" in n for n in names), names


def test_csv_gives_the_same_warehouse(tmp_path: Path, warehouse: Warehouse) -> None:
    raw = tmp_path / "raw"
    gen.write(gen.build(300, 1).n_orders, 1, raw, "csv")
    res = runner.build(raw, tmp_path / "w.duckdb", tmp_path / "dbt", threads=2, fmt="csv", quiet=True)
    assert res.success and runner.summary(res)["passed"] == 66
    assert all(c.ok for c in verify.verify(raw, tmp_path / "w.duckdb"))


def test_docs_are_one_html_file(warehouse: Warehouse) -> None:
    page = runner.docs(warehouse.raw, warehouse.db, warehouse.work)
    text = page.read_text(encoding="utf-8")
    assert "fct_orders" in text and "mart_cohort_retention" in text


def test_build_errors(tmp_path: Path) -> None:
    with pytest.raises(runner.BuildError):
        runner.build(tmp_path / "missing", tmp_path / "w.duckdb", tmp_path / "dbt")
    (tmp_path / "empty").mkdir()
    with pytest.raises(runner.BuildError):
        runner.build(tmp_path / "empty", tmp_path / "w.duckdb", tmp_path / "dbt")


def test_parse_run_results_names_kinds_and_layers(warehouse: Warehouse) -> None:
    nodes = {n.name: n for n in warehouse.result.nodes}
    assert nodes["fct_orders"].layer == "marts" and nodes["stg_orders"].layer == "staging"
    assert nodes["int_order_totals"].layer == "intermediate"
    assert runner.layer_of("mart_monthly_revenue") == "marts"
