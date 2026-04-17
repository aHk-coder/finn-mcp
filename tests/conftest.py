from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURE_DIR


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()
