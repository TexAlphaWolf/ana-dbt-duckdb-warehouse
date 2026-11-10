# Benchmark

Run on Linux x86_64, 12 CPUs, Python 3.14.10, dbt-core 1.12.6, dbt-duckdb 1.11.1, DuckDB 2.0.0; dbt with 4 threads; seed 1; each time is the median of 5 build(s); 92.7 s in all; command `bench --sizes 10000,100000,1000000 --repeat 5 --threads 4 --out /out`.

## 1. Build time by size

`dbt build` from an empty warehouse file: 12 models, 49 data tests and 5 unit tests, run in dependency order. *Wall* is the elapsed time dbt reports for the whole run (`run_results.json`); the other times add up what each node took, and nodes run in parallel, so they can add up to more than the wall time.

| Orders | Raw rows | Raw Parquet | Wall (s) | Models (s) | Data tests (s) | Unit tests (s) | Warehouse file | Checks that match |
|---|---|---|---|---|---|---|---|---|
| 10,000 | 44,573 | 0.4 MiB | 1.75 | 1.08 | 3.07 | 0.99 | 2.3 MiB | 31 of 31 |
| 100,000 | 445,805 | 4.1 MiB | 1.85 | 1.20 | 3.05 | 0.91 | 7.0 MiB | 31 of 31 |
| 1,000,000 | 4,438,827 | 42.3 MiB | 2.79 | 2.13 | 4.33 | 1.06 | 90.5 MiB | 31 of 31 |

## 2. Each model at 1,000,000 orders

| Model | Layer | Time (s) |
|---|---|---|
| fct_orders | marts | 0.47 |
| int_order_totals | intermediate | 0.31 |
| int_order_payments | intermediate | 0.30 |
| stg_order_items | staging | 0.20 |
| dim_customers | marts | 0.18 |
| dim_products | marts | 0.13 |
| stg_customers | staging | 0.09 |
| stg_products | staging | 0.08 |
| stg_orders | staging | 0.08 |
| stg_payments | staging | 0.07 |
| mart_cohort_retention | marts | 0.06 |
| mart_monthly_revenue | marts | 0.05 |

## 3. Time in each layer (sum of its models, seconds)

| Orders | staging | intermediate | marts |
|---|---|---|---|
| 10,000 | 0.54 | 0.16 | 0.27 |
| 100,000 | 0.54 | 0.20 | 0.47 |
| 1,000,000 | 0.54 | 0.61 | 0.90 |
