from __future__ import annotations

from pathlib import Path
import shutil

import pytest


@pytest.fixture()
def deals_fixtures_root(tmp_path: Path) -> Path:
    source_root = Path(__file__).parent / "fixtures" / "deals"
    destination = tmp_path / "deals"
    shutil.copytree(source_root, destination)
    return destination
