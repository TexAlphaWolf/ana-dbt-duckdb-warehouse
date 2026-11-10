from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from dbtwh import gen, runner

ORDERS = int(os.environ.get("DBTWH_TEST_ORDERS", "3000"))
SEED = int(os.environ.get("DBTWH_TEST_SEED", "1"))


@dataclass(frozen=True)
class Warehouse:
    raw: Path
    db: Path
    work: Path
    result: runner.BuildResult


@pytest.fixture(scope="session")
def truth() -> gen.Truth:
    return gen.build(ORDERS, SEED)


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Warehouse:
    """One real dbt build, shared by the tests that only read it."""
    base = tmp_path_factory.mktemp("wh")
    raw, work = base / "raw", base / "dbt"
    gen.write(ORDERS, SEED, raw)
    db = work / "warehouse.duckdb"
    return Warehouse(raw, db, work, runner.build(raw, db, work, threads=2, quiet=True))
