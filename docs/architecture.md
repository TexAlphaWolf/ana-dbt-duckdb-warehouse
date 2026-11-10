# Architecture

## From raw files to marts

```text
raw files (Parquet or CSV)            dbt, on DuckDB                                  checked by
------------------------   ---------------------------------------------   -------------------------
customers  (change records)   staging (views)     intermediate (tables)   marts (tables)
products                      stg_customers       int_order_totals        fct_orders        <- data contract
orders     (duplicates)  -->  stg_products   -->  int_order_payments -->  dim_customers
order_items                   stg_orders                                  dim_products       49 data tests
payments   (failed attempts)  stg_order_items                             mart_monthly_revenue  5 unit tests
                              stg_payments                                mart_cohort_retention
                                                                                |
                         gen.py --> truth.py (NumPy, no SQL) ------ verify.py --+  31 column checks
```

| Layer | Models | What it does |
|---|---|---|
| sources | `raw.*` | The five raw files, read in place with `read_parquet` or `read_csv` (the path and the reader are variables, so the models do not change with the format). |
| staging (views) | `stg_*` | One model per source. Types, the status spelling (`clean_status` macro: any case, spaces, `canceled` becomes `cancelled`), and the removal of repeated rows: the latest version of a customer, one copy of an order, one copy of a payment. No business logic. |
| intermediate (tables) | `int_order_totals`, `int_order_payments` | One row per order: what was bought (lines, units, gross, discount, net, cost) and what was received (captured payments only). |
| marts (tables) | `fct_orders`, `dim_customers`, `dim_products`, `mart_monthly_revenue`, `mart_cohort_retention` | What an analyst queries. `fct_orders` has an enforced contract: dbt checks column names and types before it builds the table. |

Money is an integer number of cents everywhere, so sums never depend on the order of the additions and the warehouse can be
compared with the independent calculation for exact equality.

## The checks

- **49 data tests** declared in the `_*.yml` files next to the models: `unique`, `not_null`, `accepted_values`,
  `relationships`, one custom generic test (`non_negative`) and five singular tests in `tests/` that state a business rule as
  a query that must return nothing (revenue is the same number in every mart, no order is overpaid, a cancelled order has no
  money, a cohort is 100 % active in its first month, nobody orders before signing up).
- **5 unit tests** (`unit_tests:` in the YAML): a model is fed a few rows written in the test and its output is compared with
  the expected rows, without reading any file. They cover the duplicate and status rules of staging and the totals and
  payment rules of the intermediate models.
- **`verify`** is not a dbt feature: `gen.py` first builds the true data, `truth.py` computes every mart from it with NumPy
  (no SQL, no dbt), and `verify.py` compares each column of each mart row by row with what dbt wrote (31 checks; counts and
  money exactly, ratios to a relative tolerance of 1e-12).

## Files

| Path | Role |
|---|---|
| `src/dbtwh/gen.py` | The true data, then the raw files with their faults and a `manifest.json` (orders, seed, format). |
| `src/dbtwh/truth.py` | The expected marts, computed from the true data. |
| `src/dbtwh/dbt_project/` | The dbt project (models, tests, macros, profile), shipped inside the package. |
| `src/dbtwh/runner.py` | Runs dbt in a child process and reads `run_results.json` (time and status of every node). |
| `src/dbtwh/verify.py` | Compares the warehouse with `truth.py`. |
| `src/dbtwh/bench.py`, `report.py` | Build time for growing sizes; Markdown and figure rebuilt from the JSON. |
| `src/dbtwh/cli.py` | `generate`, `build`, `verify`, `demo`, `bench`, `render`, `project`. |

dbt runs in a child process because it keeps the DuckDB file open for as long as it lives; it also keeps dbt's settings out
of the calling process. Its own files (`target/`, `logs/`, a copy of `profiles.yml`) go to `--workdir`, so the installed
package is never written to and the Docker image can run with a read-only root filesystem.
