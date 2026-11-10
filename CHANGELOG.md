# Changelog

## 1.0.0

First release.

- A dbt project on DuckDB: five sources, five staging views, two intermediate tables and five marts (an order fact with an
  enforced contract, customers, products, monthly revenue, cohort retention).
- 49 data tests (including a custom generic test and five singular tests) and 5 unit tests.
- A generator of raw shop data (Parquet or CSV) with realistic faults: customer versions, odd status spellings, duplicated
  orders and payments, failed payments.
- An independent NumPy calculation of every mart and a verifier that compares it column by column with the warehouse.
- A benchmark of the whole build for growing sizes, rebuilt into Markdown and a figure from its JSON.
- A command line (`generate`, `build`, `verify`, `demo`, `bench`, `render`, `project`) with exit codes for a pipeline.
- Docker image (no network, read-only, no capabilities); CI on Python 3.11 to 3.14, Linux, Windows and macOS.
