# Method

## The data

A small online shop, 2024-01-01 to 2025-12-31, as a function of two numbers: `orders` and `seed`.

- Customers: `max(50, orders // 10)`; who orders is drawn with a power-law weight (`1 / rank^0.4`), so a few customers order
  often and many order once. Each has a country, an acquisition channel and a signup date that is never after their first
  order.
- Products: `max(40, min(2000, orders // 50))`, in eight categories, each with a price and a cost.
- Orders: a status drawn from pending (8 %), shipped (12 %), completed (70 %), cancelled (10 %); one to five lines each, a
  discount on one line in five, the unit price the product price within +/-10 %.
- Payments: a captured payment for the full amount, or two captured parts, a partial payment, and failed attempts first.

## The mess

The true data is then written as a source system would deliver it:

| Fault | What the warehouse must do |
|---|---|
| A customer arrives as one to three versions with different `updated_at` | keep the latest |
| Status typed as `Completed`, ` SHIPPED `, `canceled`, ... | one of four spellings |
| 1 % of the orders appear twice | one row per order |
| 0.5 % of the payments appear twice | count each payment once |
| Payments with status `failed` | not money received |

## What is checked, and against what

`verify` regenerates the true data from `manifest.json` (orders, seed) and computes, from NumPy arrays only: per-order units,
gross, discount, net, revenue, margin, paid amount and payment state; per-customer order count, lifetime revenue, first and
last order, cohort; the monthly mart; the cohort retention table; and per-product units and revenue. Each column of each mart
is read back from the warehouse file (`read_only`) and compared row by row: integers and strings for equality, the two ratio
columns with a relative tolerance of 1e-12. A difference is reported as a failed check and exits with code 1.

The point of the independent path is that a mistake in a SQL model (a join that fans out, a filter that drops cancelled orders
twice) shows up as a difference, where a dbt test written from the same idea would pass.

## The benchmark

`bench` runs, for each size: generate the raw files; `dbt build` from an empty warehouse file, `--repeat` times; then `verify`
once. The reported time is the median over the builds. *Wall* is the `elapsed_time` that dbt writes in `run_results.json` (it leaves out starting Python); per-model, per-layer
and per-test times add up the `execution_time` of each node in `run_results.json`, so with several threads they can add up
to more than the wall time. If a build fails or a check differs, the benchmark says so and exits with code 1: a time is never
reported for a warehouse that is wrong.
