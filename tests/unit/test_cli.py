from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from angelcopilot import cli


def test_batch_run__passes_assistant_model_to_job(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run_batch_job(**kwargs: object) -> object:
        observed.update(kwargs)
        return SimpleNamespace(assessments=[])

    monkeypatch.setattr(cli, "run_batch_job", fake_run_batch_job)

    exit_code = cli.main(
        [
            "batch",
            "run",
            "--deals-root",
            "/tmp/deals",
            "--assistant",
            "codex",
            "--assistant-model",
            "gpt-5.5",
            "--no-pdf",
        ]
    )

    assert exit_code == 0
    assert observed["assistant_model"] == "gpt-5.5"
    assert observed["deals_root"] == "/tmp/deals"
    assert observed["assistant"] == "codex"
    assert observed["cwd"] == Path.cwd()
