# Security

## Model

dbtwh is a command line program that **generates synthetic data, runs dbt on a local DuckDB file, and writes files**. It
starts no service, opens no network connection and sends nothing anywhere (dbt's usage statistics and version check are
turned off).

- **What it reads:** Parquet or CSV files in the folder given with `--raw` (the five files `generate` writes and a
  `manifest.json`), read by DuckDB as data. The only SQL that runs is the dbt project shipped in the package.
- **What it writes:** only where the options say: `generate --out`, `build --db` and `--workdir` (dbt's `target/`, `logs/`),
  `demo --out`, `bench --out`, `render -o` and `--figure`, `project OUT`.
- **The Docker image** runs as an unprivileged user and works with a read-only root filesystem (plus `--tmpfs /tmp` for
  matplotlib's cache), no capabilities and no network (`--network none`); see `tools/docker_e2e.sh`.
- **No real data** is in the repository: everything the tests and the benchmark use is generated from a seed.

## Reporting

If you find a vulnerability, please open a private security advisory on the GitHub repository (Security tab) rather than a
public issue.
