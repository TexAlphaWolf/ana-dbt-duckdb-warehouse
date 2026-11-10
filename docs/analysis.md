# Analysis of the benchmark

Source: [`bench.json`](bench.json), rendered in [`bench.md`](bench.md). One run in Docker on Linux x86_64 with 12 CPUs,
Python 3.14.10, dbt-core 1.12.6, dbt-duckdb 1.11.1, DuckDB 2.0.0 and NumPy 2.5.4. Raw data of 10,000, 100,000 and 1,000,000
orders (seed 1, Parquet); dbt with 4 threads; each time is the median of 5 builds from an empty warehouse file. After each
size, every mart was compared with the independent calculation.

## 1. Correctness

| Orders | Raw rows | dbt nodes passed | Column checks that match |
|---|---|---|---|
| 10,000 | 44,573 | 66 of 66 | 31 of 31 |
| 100,000 | 445,805 | 66 of 66 | 31 of 31 |
| 1,000,000 | 4,438,827 | 66 of 66 | 31 of 31 |

No mismatch at any size. The two kinds of check are independent: the dbt tests ask whether the data obeys rules (unique keys,
valid statuses, revenue adding up the same way in every mart); the verifier asks whether each number is the right number,
by recomputing it from the clean data in NumPy. A join that multiplies rows or a filter applied twice could pass the first
kind and not the second; `tests/test_build.py` shows the second kind failing when a number is changed.

## 2. How the time grows

| Orders | Wall (s) | Models (s) | Data tests (s) | Unit tests (s) |
|---|---|---|---|---|
| 10,000 | 1.75 | 1.08 | 3.07 | 0.99 |
| 100,000 | 1.85 | 1.20 | 3.05 | 0.91 |
| 1,000,000 | 2.79 | 2.13 | 4.33 | 1.06 |

- **Data grew 99.6 times (rows), the build 1.59 times.** The wall time at 10,000 orders is mostly fixed cost: the nodes of
  the graph are started and the 66 statements are sent whatever their size. The models' summed time grows 1.97 times, the
  data tests' 1.41 times, the unit tests' not at all (1.07 times, within noise: they read no data).
- **The tests are the larger share of the work**: 59.8%, 59.1% and 57.6% of the summed node time at the three sizes. They
  run in parallel with 4 threads, which is why the run takes 2.79 s while the nodes add up to 7.51 s at 1,000,000 orders.
- **Throughput at the top size**: 1,000,000 orders in 2.79 s is about 359,000 orders per second, including all the tests.

## 3. Where the model time goes

| Orders | staging | intermediate | marts |
|---|---|---|---|
| 10,000 | 0.54 | 0.16 | 0.27 |
| 100,000 | 0.54 | 0.20 | 0.47 |
| 1,000,000 | 0.54 | 0.61 | 0.90 |

- **Staging does not grow (1.0 times)** because staging models are views: building one only stores a query. The data is
  read later, by the intermediate tables that use them and by the tests on the views.
- **The intermediate tables grow 3.9 times and the marts 3.3 times** while the data grows 100 times: DuckDB scans and
  aggregates the 2.2 million order lines and 1.1 million payments of the largest size in about 0.3 s each.
- **The slowest model at 1,000,000 orders is `fct_orders` (0.47 s)**, which joins the cleaned orders with both intermediate
  tables; then `int_order_totals` (0.31 s) and `int_order_payments` (0.30 s), which aggregate the lines and the payments.

## 4. Size

| Orders | Raw Parquet | Warehouse file |
|---|---|---|
| 10,000 | 0.4 MiB | 2.3 MiB |
| 100,000 | 4.1 MiB | 7.0 MiB |
| 1,000,000 | 42.3 MiB | 90.5 MiB |

The warehouse holds more than the raw files (intermediate tables and marts, five of them with one row per order or per
customer) and does not compress as hard as zstd Parquet: 2.1 times the raw size at 1,000,000 orders. At small sizes the
file has a fixed part (the catalogue and its blocks), so the ratio is higher.

## What these numbers do not say

- They are one machine, one engine and a generated shop; see [`limitations.md`](limitations.md).
- The times are medians of 5 builds. The sums of node times count nodes that run at the same time, so they are not
  additive with the wall time.
- The generated data has about 2.2 order lines per order, about 150,000 customers at most and a power-law
  activity; a real shop with wider tables or more distinct values per column would cost more per row.
