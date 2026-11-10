"""What the warehouse must contain, computed from the true data with NumPy.

This shares no code with the dbt models: it works on the clean arrays the generator made before it spoilt them, so it
checks that dbt really undoes the mess (duplicates, old customer versions, spelling of statuses, failed payments).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dbtwh.gen import Truth

Ints = NDArray[np.int64]
Floats = NDArray[np.float64]


@dataclass(frozen=True)
class Expected:
    # fct_orders, one entry per order (position = order_id - 1)
    status: NDArray[np.object_]
    units: Ints
    gross: Ints
    discount: Ints
    net: Ints
    revenue: Ints
    margin: Ints
    paid: Ints
    state: NDArray[np.object_]
    # dim_customers, one per customer
    order_count: Ints
    lifetime: Ints
    first_at: Ints  # seconds since epoch, 0 where the customer never ordered
    last_at: Ints
    cohort_idx: Ints  # month index of the first order, -1 where none
    # mart_monthly_revenue, one per month from `month0`
    month0: np.datetime64
    m_month: Ints
    m_orders: Ints
    m_units: Ints
    m_net: Ints
    m_margin: Ints
    m_aov: Floats
    # mart_cohort_retention, sorted by (cohort, months_since)
    c_cohort: Ints
    c_since: Ints
    c_size: Ints
    c_active: Ints
    c_rate: Floats
    # dim_products
    p_units: Ints
    p_revenue: Ints


def expected(t: Truth) -> Expected:
    n = t.n_orders
    gross_line = t.item_qty * t.item_price
    net_line = gross_line - t.item_discount

    def per_order(w: NDArray[np.int64]) -> Ints:
        return np.rint(np.bincount(t.item_order, weights=w.astype(np.float64), minlength=n)).astype(np.int64)

    units, gross, discount, net = (
        per_order(t.item_qty),
        per_order(gross_line),
        per_order(t.item_discount),
        per_order(net_line),
    )
    cost = per_order(t.item_qty * t.prod_cost[t.item_product])
    is_rev = t.order_status != "cancelled"
    revenue = np.where(is_rev, net, 0).astype(np.int64)
    margin = np.where(is_rev, net - cost, 0).astype(np.int64)
    cap = t.pay_status == "captured"
    paid = np.rint(np.bincount(t.pay_order[cap], weights=t.pay_amount[cap].astype(np.float64), minlength=n)).astype(
        np.int64
    )
    state = np.where(~is_rev, "not_due", np.where(paid == 0, "unpaid", np.where(paid < net, "partial", "paid"))).astype(
        object
    )

    nc = t.n_customers
    seconds = t.order_at.astype("datetime64[s]").astype(np.int64)
    cust = t.order_customer
    order_count = np.bincount(cust[is_rev], minlength=nc).astype(np.int64)
    lifetime = np.rint(np.bincount(cust[is_rev], weights=revenue[is_rev].astype(np.float64), minlength=nc)).astype(
        np.int64
    )
    big = np.iinfo(np.int64).max
    first = np.full(nc, big, dtype=np.int64)
    last = np.zeros(nc, dtype=np.int64)
    np.minimum.at(first, cust[is_rev], seconds[is_rev])
    np.maximum.at(last, cust[is_rev], seconds[is_rev])
    ordered = order_count > 0
    first[~ordered] = 0

    months = t.order_at.astype("datetime64[M]")
    month0 = months.min()
    mi = (months - month0).astype(np.int64)
    k = int(mi.max()) + 1
    cohort_idx = np.full(nc, -1, dtype=np.int64)
    cohort_idx[ordered] = (first[ordered].astype("datetime64[s]").astype("datetime64[M]") - month0).astype(np.int64)

    m_orders = np.bincount(mi[is_rev], minlength=k).astype(np.int64)
    m_units = np.rint(np.bincount(mi[is_rev], weights=units[is_rev].astype(np.float64), minlength=k)).astype(np.int64)
    m_net = np.rint(np.bincount(mi[is_rev], weights=revenue[is_rev].astype(np.float64), minlength=k)).astype(np.int64)
    m_margin = np.rint(np.bincount(mi[is_rev], weights=margin[is_rev].astype(np.float64), minlength=k)).astype(np.int64)
    present = m_orders > 0
    m_aov = np.where(present, m_net / np.maximum(m_orders, 1), 0.0)

    pairs = np.unique(cust[is_rev].astype(np.int64) * k + mi[is_rev])
    p_cust, p_month = pairs // k, pairs % k
    since = p_month - cohort_idx[p_cust]
    key = cohort_idx[p_cust] * k + since
    active_by_key = np.bincount(key, minlength=k * k)
    size_by_cohort = np.bincount(cohort_idx[ordered], minlength=k).astype(np.int64)
    keys = np.flatnonzero(active_by_key)
    c_cohort, c_since = keys // k, keys % k
    c_active = active_by_key[keys].astype(np.int64)
    c_size = size_by_cohort[c_cohort]

    npr = len(t.prod_price)
    p_units = np.rint(
        np.bincount(
            t.item_product[is_rev[t.item_order]],
            weights=t.item_qty[is_rev[t.item_order]].astype(np.float64),
            minlength=npr,
        )
    ).astype(np.int64)
    p_revenue = np.rint(
        np.bincount(
            t.item_product[is_rev[t.item_order]],
            weights=net_line[is_rev[t.item_order]].astype(np.float64),
            minlength=npr,
        )
    ).astype(np.int64)
    return Expected(
        t.order_status, units, gross, discount, net, revenue, margin, paid, state,
        order_count, lifetime, first, last, cohort_idx,
        month0, np.flatnonzero(present).astype(np.int64), m_orders[present], m_units[present], m_net[present], m_margin[present], m_aov[present],
        c_cohort, c_since, c_size, c_active, c_active / c_size,
        p_units, p_revenue,
    )  # fmt: skip
