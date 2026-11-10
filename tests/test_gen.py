from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pytest

from dbtwh import gen


def test_same_seed_same_data_other_seed_other_data() -> None:
    a, b, c = gen.build(500, 3), gen.build(500, 3), gen.build(500, 4)
    assert np.array_equal(a.item_price, b.item_price) and np.array_equal(a.order_at, b.order_at)
    assert not np.array_equal(a.item_price, c.item_price)


def test_sizes_and_ranges(truth: gen.Truth) -> None:
    assert truth.n_orders == len(truth.order_status)
    assert truth.n_customers == gen.customers_for(truth.n_orders)
    assert set(np.unique(truth.order_status)) <= set(gen.STATUSES)
    assert (truth.item_qty >= 1).all() and (truth.item_price > 0).all() and (truth.item_discount >= 0).all()
    assert (truth.item_discount <= truth.item_qty * truth.item_price).all()
    assert (truth.pay_amount > 0).all()


def test_customers_sign_up_before_their_first_order(truth: gen.Truth) -> None:
    first = np.full(truth.n_customers, np.datetime64("2100-01-01"), dtype="datetime64[s]")
    np.minimum.at(first, truth.order_customer, truth.order_at.astype("datetime64[s]"))
    ordered = np.bincount(truth.order_customer, minlength=truth.n_customers) > 0
    assert (truth.cust_signup.astype("datetime64[D]")[ordered] <= first[ordered].astype("datetime64[D]")).all()


def test_raw_files_carry_the_mess(tmp_path: Path, truth: gen.Truth) -> None:
    counts = gen.write(truth.n_orders, 1, tmp_path)
    assert counts["orders"] > truth.n_orders  # duplicated orders
    assert counts["customers"] > truth.n_customers  # older versions of customers
    assert counts["payments"] > len(truth.pay_order)
    con = duckdb.connect()
    try:
        statuses = {r[0] for r in con.sql(f"select distinct status from '{tmp_path / 'orders.parquet'}'").fetchall()}
        ids = con.execute(f"select count(*), count(distinct order_id) from '{tmp_path / 'orders.parquet'}'").fetchone()
    finally:
        con.close()
    assert len(statuses) > len(gen.STATUSES)  # more spellings than statuses
    assert any(s != s.strip() for s in statuses) and any(s.isupper() for s in statuses) and "canceled" in statuses
    assert ids is not None and ids[0] > ids[1]


@pytest.mark.parametrize("fmt", ["parquet", "csv"])
def test_write_makes_every_file_and_a_manifest(tmp_path: Path, fmt: str) -> None:
    counts = gen.write(200, 2, tmp_path, fmt)
    assert sorted(counts) == ["customers", "order_items", "orders", "payments", "products"]
    for name in counts:
        assert (tmp_path / f"{name}.{fmt}").stat().st_size > 0
    assert '"seed": 2' in (tmp_path / "manifest.json").read_text(encoding="utf-8")


def test_errors(tmp_path: Path) -> None:
    with pytest.raises(gen.GenError):
        gen.build(gen.MIN_ORDERS - 1, 1)
    with pytest.raises(gen.GenError):
        gen.write(200, 1, tmp_path, "xml")
