# Limitations

- **Synthetic data.** The shop is generated: no real orders, no real customers. Its faults are the ones listed in
  `method.md`; real sources have more kinds (late data, edits of old rows, mixed currencies, time zones).
- **One engine.** DuckDB, in one file, on one machine. Times say nothing about a warehouse on a server such as BigQuery,
  Snowflake or Postgres, where the same models would need small changes (`date_trunc`, `date_diff`, the file readers).
- **Full rebuild.** Every model is a view or a table rebuilt from scratch. There are no incremental models, snapshots or
  seeds; a customer's history is reduced to the latest version.
- **Times are medians of a few builds on one computer.** The data tests are the larger part of the build time at the larger
  sizes and they run in parallel, so changing `--threads` changes the wall time more than it changes the sum of the times.
- **The independent calculation shares the generator's rules.** `truth.py` does not use SQL or dbt, but it encodes the same
  business rules (what counts as revenue, what a cohort is). It catches mistakes in the SQL, not a wrong rule.
- **No orchestration.** No scheduler, no incremental loading, no alerting; `dbtwh build` is one command and its exit code is
  1 if any node fails.
- **dbt's anonymous usage statistics and version check are turned off** by the runner; nothing is sent anywhere.
