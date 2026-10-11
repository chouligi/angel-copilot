"""Live smoke test for Codex's compliance with the assessment contract."""

from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest

from angelcopilot.assistant import CodexRunner
from angelcopilot.pipeline import DEFAULT_RUNTIME_SKILL_PATH, build_skill_native_prompt


@pytest.mark.live_codex
@pytest.mark.skipif(
    any(os.environ.get(name, "").lower() in {"1", "true"} for name in ("CI", "CODEX_CI"))
    and os.environ.get("ANGELCOPILOT_RUN_LIVE_CODEX_TESTS") != "1",
    reason="Live Codex smoke tests run locally by default; set ANGELCOPILOT_RUN_LIVE_CODEX_TESTS=1 to enable in CI.",
)
def test_codex_luna_low__returns_contract_valid_assessment(tmp_path: Path) -> None:
    if not shutil.which("codex"):
        pytest.skip("Codex CLI is not installed")
    if not DEFAULT_RUNTIME_SKILL_PATH.is_file():
        pytest.fail(f"Runtime AngelCopilot skill not found: {DEFAULT_RUNTIME_SKILL_PATH}")

    deal_id = "contract_smoke_fixture"
    deal_path = tmp_path / "deal_docs"
    deal_path.mkdir()
    (deal_path / "brief.md").write_text(
        """# Fictional contract smoke test startup

This is a fabricated company used only to test output formatting. It has no
verified customers, revenue, financing, team credentials, or public sources.
Treat all company-specific claims as unknown. Do not invent facts or a cheque.
""",
        encoding="utf-8",
    )
    profile_path = tmp_path / "profile.md"
    profile_path.write_text(
        "region: Europe\ncurrency: EUR\nNo ticket range supplied.\n",
        encoding="utf-8",
    )

    prompt = build_skill_native_prompt(
        deal_id=deal_id,
        deal_path=deal_path,
        profile_path=profile_path,
        runtime_skill_path=DEFAULT_RUNTIME_SKILL_PATH,
    )
    runner = CodexRunner(model="gpt-6-luna", reasoning_effort="low")
    payload = runner.run_assessment(prompt, cwd=tmp_path)

    assert payload["schema_version"] == 3
    assert payload["assessment_mode"] == "screening"
    assert payload["screening"]["recommendation"] in {"PURSUE", "CONSIDER", "PASS"}
    assert payload["deal_id"] == deal_id
