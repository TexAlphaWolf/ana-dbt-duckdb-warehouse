# Contributing

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov
```

No service is needed; the tests run real `dbt build` commands on small generated data (about a minute in all).
`DBTWH_TEST_ORDERS` and `DBTWH_TEST_SEED` run the same tests on other generated data (CI also uses 30,000 orders with seed 11).

Rules that keep the project honest:

- **A new model needs three things:** its SQL under `src/dbtwh/dbt_project/models/`, its columns described and tested in the
  `_*.yml` next to it, and (if it is a mart) a column check in `verify.py` against a calculation in `truth.py` that does not
  use SQL. A model whose numbers are only tested by SQL has not been checked.
- **A new kind of mess** goes in `gen.py` (`raw_tables`), with a line in `docs/method.md` and a test in `tests/test_gen.py`
  that shows it is present in the raw files.
- **Numbers in the README come from `docs/bench.json`**, and `tests/test_docs.py` checks them. After a new measurement
  (`tools/run_full.ps1`), copy `bench.json`, `bench.md` and `summary.png` into `docs/` and update the text if a number moved.
