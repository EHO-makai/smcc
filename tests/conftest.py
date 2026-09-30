from datetime import date
from pathlib import Path

import pytest

from smcc import Store

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def smcc_dir() -> Path:
    return REPO_ROOT / ".smcc"


@pytest.fixture(scope="session")
def store(smcc_dir: Path) -> Store:
    return Store(smcc_dir)


@pytest.fixture()
def today() -> date:
    return date(2026, 9, 30)
