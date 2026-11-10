"""Raw data for a small online shop, with the mess a warehouse has to clean.

The generator first builds the *true* data (customers, products, orders, order lines, payments), from which `truth.py`
computes the numbers the warehouse must reproduce. It then writes the *raw* files the way a source system would deliver
them, with faults dbt has to undo:

* customers arrive as change records: a customer can have two or three versions, only the latest is true;
* order statuses come in any case, with stray spaces, and "canceled" as well as "cancelled";
* some orders and some payments are delivered twice;
* payments include failed attempts, which must not count as money received.

Everything is a function of (orders, seed).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray

Ints = NDArray[np.int64]
Times = NDArray[np.datetime64]

START = np.datetime64("2024-01-01T00:00:00")
END = np.datetime64("2025-12-31T23:59:59")
SIGNUP_FROM = np.datetime64("2023-01-01", "D")
SIGNUP_TO = np.datetime64("2025-09-30", "D")
COUNTRIES = ["IT", "DE", "FR", "ES", "GB", "NL", "SE", "PL"]
CHANNELS = ["organic", "paid_search", "social", "email", "referral"]
CATEGORIES = ["audio", "video", "lighting", "cables", "stands", "cases", "mixers", "accessories"]
STATUSES = ["pending", "shipped", "completed", "cancelled"]
STATUS_WEIGHTS = [0.08, 0.12, 0.70, 0.10]
MIN_ORDERS = 100
DUP_ORDER_RATE = 0.01
DUP_PAYMENT_RATE = 0.005


class GenError(ValueError):
    pass


@dataclass(frozen=True)
class Truth:
    """The clean data: what really happened."""

    n_customers: int
    cust_country: NDArray[np.object_]
    cust_email: NDArray[np.object_]
    cust_channel: NDArray[np.object_]
    cust_signup: NDArray[np.datetime64]
    prod_category: NDArray[np.object_]
    prod_price: Ints
    prod_cost: Ints
    order_customer: Ints  # customer_id - 1 (a position)
    order_at: Times
    order_status: NDArray[np.object_]
    item_order: Ints  # order position (order_id - 1)
    item_line: Ints
    item_product: Ints  # product position
    item_qty: Ints
    item_price: Ints
    item_discount: Ints
    pay_order: Ints
    pay_at: Times
    pay_method: NDArray[np.object_]
    pay_status: NDArray[np.object_]
    pay_amount: Ints

    @property
    def n_orders(self) -> int:
        return len(self.order_at)


def customers_for(orders: int) -> int:
    return max(50, orders // 10)


def build(orders: int, seed: int) -> Truth:
    if orders < MIN_ORDERS:
        raise GenError(f"need at least {MIN_ORDERS} orders; got {orders}")
    rng = np.random.default_rng(seed)
    nc, npr = customers_for(orders), max(40, min(2000, orders // 50))
    cust_country = np.array(COUNTRIES, dtype=object)[
        rng.choice(len(COUNTRIES), nc, p=[0.30, 0.18, 0.15, 0.12, 0.10, 0.06, 0.05, 0.04])
    ]
    cust_channel = np.array(CHANNELS, dtype=object)[rng.choice(len(CHANNELS), nc, p=[0.35, 0.25, 0.15, 0.15, 0.10])]
    days = int((SIGNUP_TO - SIGNUP_FROM).astype(int))
    cust_signup = SIGNUP_FROM + rng.integers(0, days + 1, nc).astype("timedelta64[D]")
    cust_email = np.array([f"user{i + 1}@example.com" for i in range(nc)], dtype=object)

    prod_category = np.array(CATEGORIES, dtype=object)[rng.integers(0, len(CATEGORIES), npr)]
    prod_price = rng.integers(500, 50_001, npr).astype(np.int64)
    prod_cost = (prod_price * rng.uniform(0.30, 0.70, npr)).astype(np.int64)

    # a few customers order a lot: weights fall with the customer's position
    w = 1.0 / np.arange(1, nc + 1) ** 0.4
    order_customer = rng.choice(nc, orders, p=w / w.sum()).astype(np.int64)
    signup_s = cust_signup.astype("datetime64[s]")[order_customer]
    lo = np.maximum(signup_s, START)
    span = (END - lo).astype("timedelta64[s]").astype(np.int64)
    order_at = lo + (rng.random(orders) * (span + 1)).astype(np.int64).astype("timedelta64[s]")
    order_status = np.array(STATUSES, dtype=object)[rng.choice(4, orders, p=STATUS_WEIGHTS)]

    lines = rng.choice([1, 2, 3, 4, 5], orders, p=[0.35, 0.30, 0.20, 0.10, 0.05]).astype(np.int64)
    n_items = int(lines.sum())
    item_order = np.repeat(np.arange(orders, dtype=np.int64), lines)
    starts = np.cumsum(lines) - lines
    item_line = (np.arange(n_items, dtype=np.int64) - np.repeat(starts, lines) + 1).astype(np.int64)
    pw = 1.0 / np.arange(1, npr + 1) ** 0.3
    item_product = rng.choice(npr, n_items, p=pw / pw.sum()).astype(np.int64)
    item_qty = rng.integers(1, 5, n_items).astype(np.int64)
    item_price = (prod_price[item_product] * rng.uniform(0.90, 1.10, n_items)).astype(np.int64)
    gross = item_qty * item_price
    has_discount = rng.random(n_items) < 0.20
    item_discount = np.where(has_discount, (gross * rng.uniform(0.05, 0.30, n_items)).astype(np.int64), 0).astype(
        np.int64
    )

    net = np.bincount(item_order, weights=(gross - item_discount), minlength=orders).astype(np.int64)
    pay_order, pay_at, pay_method, pay_status, pay_amount = payments(rng, order_status, order_at, net)
    return Truth(
        nc, cust_country, cust_email, cust_channel, cust_signup, prod_category, prod_price, prod_cost,
        order_customer, order_at, order_status, item_order, item_line, item_product, item_qty, item_price,
        item_discount, pay_order, pay_at, pay_method, pay_status, pay_amount,
    )  # fmt: skip


def payments(
    rng: np.random.Generator, status: NDArray[np.object_], at: Times, net: Ints
) -> tuple[Ints, Times, NDArray[np.object_], NDArray[np.object_], Ints]:
    n = len(status)
    pos = np.arange(n, dtype=np.int64)
    paid_status = (status == "completed") | (status == "shipped")
    methods = np.array(["card", "transfer", "wallet"], dtype=object)
    rows_order: list[Ints] = []
    rows_at: list[Times] = []
    rows_amount: list[Ints] = []
    rows_status: list[NDArray[np.object_]] = []

    def add(sel: NDArray[np.bool_], amount: Ints, minutes: Ints, state: str) -> None:
        rows_order.append(pos[sel])
        rows_at.append(at[sel] + minutes.astype("timedelta64[m]"))
        rows_amount.append(amount)
        rows_status.append(np.full(int(sel.sum()), state, dtype=object))

    # failed attempts: 8% of orders that were paid, 30% of cancelled ones (the amount asked, never received)
    failed = (paid_status & (rng.random(n) < 0.08)) | ((status == "cancelled") & (rng.random(n) < 0.30))
    add(failed, net[failed], rng.integers(1, 10, int(failed.sum())).astype(np.int64), "failed")
    # captured: 95% of paid orders in full (a fifth of them split in two), 5% only partly
    u = rng.random(n)
    full = paid_status & (u < 0.95)
    partial = paid_status & ~full
    split = full & (rng.random(n) < 0.20)
    single = full & ~split
    add(single, net[single], rng.integers(10, 60, int(single.sum())).astype(np.int64), "captured")
    first = (net[split] * rng.uniform(0.3, 0.7, int(split.sum()))).astype(np.int64)
    add(split, first, rng.integers(10, 60, int(split.sum())).astype(np.int64), "captured")
    add(split, net[split] - first, rng.integers(60, 600, int(split.sum())).astype(np.int64), "captured")
    part = (net[partial] * rng.uniform(0.4, 0.9, int(partial.sum()))).astype(np.int64)
    add(partial, part, rng.integers(10, 60, int(partial.sum())).astype(np.int64), "captured")

    order = np.concatenate(rows_order)
    when = np.concatenate(rows_at)
    amount = np.concatenate(rows_amount)
    state = np.concatenate(rows_status)
    perm = rng.permutation(len(order))  # not in a convenient order
    order, when, amount, state = order[perm], when[perm], amount[perm], state[perm]
    method = methods[rng.integers(0, 3, len(order))]
    return order, when, method, state, amount


def padded(s: str) -> str:
    return f" {s} "


def messy_status(rng: np.random.Generator, status: NDArray[np.object_]) -> NDArray[np.object_]:
    """The status as a source system might have typed it."""
    out = status.copy()
    n = len(out)
    canceled = (status == "cancelled") & (rng.random(n) < 0.30)
    out[canceled] = "canceled"
    form = rng.integers(0, 4, n)
    forms: list[Callable[[str], str]] = [str.lower, str.upper, str.title, padded]
    for k, fn in enumerate(forms):
        sel = form == k
        if sel.any():
            out[sel] = [fn(s) for s in out[sel]]
    return out


def raw_tables(t: Truth, seed: int) -> dict[str, dict[str, object]]:
    """The raw files as column dictionaries, with the faults described at the top of this module."""
    rng = np.random.default_rng(seed + 1_000_003)
    nc, n = t.n_customers, t.n_orders
    ids = np.arange(1, nc + 1, dtype=np.int64)
    extra_a = ids[rng.random(nc) < 0.30]  # one older version
    extra_b = ids[rng.random(nc) < 0.10]  # two older versions
    old_ids = np.concatenate([extra_a, extra_b, extra_b])
    old_country = np.array(COUNTRIES, dtype=object)[rng.integers(0, len(COUNTRIES), len(old_ids))]
    old_email = np.array([f"old{i}.{k}@example.org" for k, i in enumerate(old_ids)], dtype=object)
    base = np.datetime64("2025-10-01T00:00:00")
    cid = np.concatenate([ids, old_ids])
    upd = np.concatenate([
        np.full(nc, base),
        base - (rng.integers(1, 500, len(old_ids)) * 3600 * 24 + np.arange(len(old_ids))).astype("timedelta64[s]"),
    ])  # fmt: skip
    country = np.concatenate([t.cust_country, old_country])
    email = np.concatenate([t.cust_email, old_email])
    channel = np.concatenate([t.cust_channel, t.cust_channel[old_ids - 1]])
    signup = np.concatenate([t.cust_signup, t.cust_signup[old_ids - 1]]).astype("datetime64[s]")  # a DATE in the file
    perm = rng.permutation(len(cid))
    customers = {
        "customer_id": cid[perm], "email": email[perm], "country": country[perm], "channel": channel[perm],
        "signup_date": signup[perm], "updated_at": upd[perm],
    }  # fmt: skip

    npr = len(t.prod_price)
    products = {
        "product_id": np.arange(1, npr + 1, dtype=np.int64), "category": t.prod_category,
        "price_cents": t.prod_price, "cost_cents": t.prod_cost,
    }  # fmt: skip

    status = messy_status(rng, t.order_status)
    dup = np.flatnonzero(rng.random(n) < DUP_ORDER_RATE)
    sel = np.concatenate([np.arange(n), dup])
    o = {
        "order_id": sel + 1, "customer_id": t.order_customer[sel] + 1, "ordered_at": t.order_at[sel],
        "status": status[sel],
    }  # fmt: skip
    p = rng.permutation(len(sel))
    orders = {k: v[p] for k, v in o.items()}

    items = {
        "order_id": t.item_order + 1, "line_no": t.item_line, "product_id": t.item_product + 1,
        "quantity": t.item_qty, "unit_price_cents": t.item_price, "discount_cents": t.item_discount,
    }  # fmt: skip

    npay = len(t.pay_order)
    pdup = np.flatnonzero(rng.random(npay) < DUP_PAYMENT_RATE)
    ps = np.concatenate([np.arange(npay), pdup])
    pay_ids = np.concatenate([np.arange(1, npay + 1), pdup + 1])
    payments_ = {
        "payment_id": pay_ids, "order_id": t.pay_order[ps] + 1, "paid_at": t.pay_at[ps],
        "method": t.pay_method[ps], "status": t.pay_status[ps], "amount_cents": t.pay_amount[ps],
    }  # fmt: skip
    return {"customers": customers, "products": products, "orders": orders, "order_items": items, "payments": payments_}


def write(orders: int, seed: int, out: Path, fmt: str = "parquet") -> dict[str, int]:
    """Write the raw files and a manifest; returns the number of rows of each."""
    if fmt not in ("parquet", "csv"):
        raise GenError("format must be parquet or csv")
    t = build(orders, seed)
    tables = raw_tables(t, seed)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    con = duckdb.connect()
    try:
        for name, cols in tables.items():
            data = cols  # noqa: F841  (DuckDB finds the dictionary by this name)
            target = out / f"{name}.{fmt}"
            opt = "(FORMAT parquet, COMPRESSION zstd)" if fmt == "parquet" else "(FORMAT csv, HEADER)"
            select = ", ".join("signup_date::DATE AS signup_date" if c == "signup_date" else c for c in cols)
            con.execute(f"COPY (SELECT {select} FROM data) TO '{target.as_posix()}' {opt}")
            counts[name] = len(next(iter(cols.values())))  # type: ignore[arg-type]
    finally:
        con.close()
    (out / "manifest.json").write_text(
        json.dumps({"orders": orders, "seed": seed, "format": fmt, "rows": counts}, indent=1) + "\n", encoding="utf-8"
    )
    return counts
