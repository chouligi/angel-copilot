from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil

import pytest


@pytest.fixture()
def deals_fixtures_root(tmp_path: Path) -> Path:
    source_root = Path(__file__).parent / "fixtures" / "deals"
    destination = tmp_path / "deals"
    shutil.copytree(source_root, destination)
    _touch_tree(destination)
    return destination


def _touch_tree(root: Path) -> None:
    now = datetime.now(timezone.utc).timestamp()
    for path in sorted(root.rglob("*"), reverse=True):
        os.utime(path, (now, now))
    os.utime(root, (now, now))
