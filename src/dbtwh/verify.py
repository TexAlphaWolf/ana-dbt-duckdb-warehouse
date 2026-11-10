"""Compare the tables dbt built with what `truth.expected` says they must hold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray

from dbtwh import gen, truth


class VerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    rows: int
    ok: bool
    detail: str = ""


def _col(rel: duckdb.DuckDBPyRelation, name: str) -> NDArray[np.object_]:
    return np.asarray(rel.fetchnumpy()[name])


def read_manifest(raw: Path) -> dict[str, object]:
    path = raw / "manifest.json"
    if not path.exists():
        raise VerifyError(f"{path} not found: the raw folder must come from 'dbtwh generate'")
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def same(name: str, got: NDArray[np.generic], want: NDArray[np.generic], rows: int | None = None) -> Check:
    n = len(want) if rows is None else rows
    if len(got) != len(want):
        return Check(name, n, False, f"{len(got)} values, expected {len(want)}")
    bad = np.flatnonzero(got != want)
    if len(bad):
        i = int(bad[0])
        return Check(name, n, False, f"{len(bad)} differ; first at row {i}: got {got[i]!r}, expected {want[i]!r}")
    return Check(name, n, True)


def close(name: str, got: NDArray[np.float64], want: NDArray[np.float64]) -> Check:
    if len(got) != len(want):
        return Check(name, len(want), False, f"{len(got)} values, expected {len(want)}")
    bad = np.flatnonzero(~np.isclose(got, want, rtol=1e-12, atol=0.0))
    if len(bad):
        i = int(bad[0])
        return Check(
            name, len(want), False, f"{len(bad)} differ; first at row {i}: got {got[i]!r}, expected {want[i]!r}"
        )
    return Check(name, len(want), True)


def verify(raw: Path, db: Path) -> list[Check]:
    """Every column of every mart against the independent calculation, row by row."""
    man = read_manifest(raw)
    if not db.exists():
        raise VerifyError(f"{db} not found: run 'dbtwh build' first")
    exp = truth.expected(gen.build(int(man["orders"]), int(man["seed"])))  # type: ignore[call-overload]
    con = duckdb.connect(str(db), read_only=True)
    out: list[Check] = []
    try:
        q = con.sql("select * from fct_orders order by order_id").fetchnumpy()
        ids = np.asarray(q["order_id"])
        out.append(same("fct_orders: one row per order", ids, np.arange(1, len(exp.status) + 1)))
        for c, want in (("units", exp.units), ("gross_cents", exp.gross), ("discount_cents", exp.discount), ("net_cents", exp.net),
                        ("revenue_cents", exp.revenue), ("margin_cents", exp.margin), ("paid_cents", exp.paid)):  # fmt: skip
            out.append(same(f"fct_orders.{c}", np.asarray(q[c]), want))
        out.append(same("fct_orders.status", np.asarray(q["status"], dtype=object), exp.status))
        out.append(same("fct_orders.payment_state", np.asarray(q["payment_state"], dtype=object), exp.state))

        d = con.sql("select * from dim_customers order by customer_id").fetchnumpy()
        out.append(
            same(
                "dim_customers: one row per customer",
                np.asarray(d["customer_id"]),
                np.arange(1, len(exp.order_count) + 1),
            )
        )
        out.append(same("dim_customers.order_count", np.asarray(d["order_count"]), exp.order_count))
        out.append(same("dim_customers.lifetime_revenue_cents", np.asarray(d["lifetime_revenue_cents"]), exp.lifetime))
        ordered = exp.order_count > 0
        first = np.ma.filled(np.ma.masked_invalid(d["first_order_at"].astype("datetime64[s]").astype(np.int64)), 0)
        last = np.ma.filled(np.ma.masked_invalid(d["last_order_at"].astype("datetime64[s]").astype(np.int64)), 0)
        isnull = np.asarray(np.ma.getmaskarray(d["first_order_at"]) | np.isnat(np.ma.getdata(d["first_order_at"])))
        out.append(same("dim_customers.first_order_at", np.where(isnull, 0, first), np.where(ordered, exp.first_at, 0)))
        out.append(same("dim_customers.last_order_at", np.where(isnull, 0, last), np.where(ordered, exp.last_at, 0)))
        out.append(same("dim_customers: no orders means no cohort", isnull, ~ordered))
        want_country, want_email = _customer_truth(int(man["orders"]), int(man["seed"]))  # type: ignore[call-overload]
        out.append(
            same("dim_customers.country (the latest version)", np.asarray(d["country"], dtype=object), want_country)
        )
        out.append(same("dim_customers.email (the latest version)", np.asarray(d["email"], dtype=object), want_email))

        m = con.sql("select * from mart_monthly_revenue order by order_month").fetchnumpy()
        months = (np.asarray(m["order_month"]).astype("datetime64[M]") - exp.month0).astype(np.int64)
        out.append(same("mart_monthly_revenue.order_month", months, exp.m_month))
        out.append(same("mart_monthly_revenue: one row per month with orders", np.asarray(m["orders"]), exp.m_orders))
        out.append(same("mart_monthly_revenue.units", np.asarray(m["units"]), exp.m_units))
        out.append(same("mart_monthly_revenue.net_revenue_cents", np.asarray(m["net_revenue_cents"]), exp.m_net))
        out.append(same("mart_monthly_revenue.gross_margin_cents", np.asarray(m["gross_margin_cents"]), exp.m_margin))
        out.append(
            close(
                "mart_monthly_revenue.avg_order_value_cents",
                np.asarray(m["avg_order_value_cents"], dtype=np.float64),
                exp.m_aov,
            )
        )

        ch = con.sql("select * from mart_cohort_retention order by cohort_month, months_since").fetchnumpy()
        cohort = (np.asarray(ch["cohort_month"]).astype("datetime64[M]") - exp.month0).astype(np.int64)
        out.append(same("mart_cohort_retention.cohort_month", cohort, exp.c_cohort))
        out.append(same("mart_cohort_retention.months_since", np.asarray(ch["months_since"]), exp.c_since))
        out.append(same("mart_cohort_retention.cohort_size", np.asarray(ch["cohort_size"]), exp.c_size))
        out.append(same("mart_cohort_retention.active_customers", np.asarray(ch["active_customers"]), exp.c_active))
        out.append(
            close(
                "mart_cohort_retention.retention_rate", np.asarray(ch["retention_rate"], dtype=np.float64), exp.c_rate
            )
        )

        p = con.sql("select * from dim_products order by product_id").fetchnumpy()
        out.append(same("dim_products.units_sold", np.asarray(p["units_sold"]), exp.p_units))
        out.append(same("dim_products.revenue_cents", np.asarray(p["revenue_cents"]), exp.p_revenue))
    finally:
        con.close()
    return out


def _customer_truth(orders: int, seed: int) -> tuple[NDArray[np.object_], NDArray[np.object_]]:
    t = gen.build(orders, seed)
    return t.cust_country, t.cust_email
