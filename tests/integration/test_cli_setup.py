from __future__ import annotations

from argparse import Namespace
import sys

import pytest

from angelcopilot_batch import cli


def test__run_setup__invokes_playwright_install(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], check: bool) -> None:
        observed["command"] = command
        observed["check"] = check

    monkeypatch.setattr("subprocess.run", fake_run)

    status = cli._run_setup(Namespace())

    assert status == 0
    assert observed["check"] is True
    assert observed["command"] == [sys.executable, "-m", "playwright", "install", "chromium"]
