from __future__ import annotations

import json
from pathlib import Path

import pytest

from angelcopilot_batch.assistant import (
    CodexRunner,
    build_assistant_runner,
    parse_assessment_json,
    validate_assessment_payload,
)


def test_parse_assessment_json__extracts_embedded_json() -> None:
    raw_output = (
        "Result:\n```json\n"
        "{\"deal_id\":\"d1\",\"company_name\":\"Acme\",\"category_scores\":"
        "{\"Team\":4.0,\"Market\":4.0,\"Product\":4.0,\"Traction\":4.0,"
        "\"Unit Economics\":4.0,\"Defensibility\":4.0,\"Terms\":4.0},"
        "\"risk_flags\":[],\"sectors\":[\"AI\"],\"geographies\":[\"US\"],"
        "\"rationale\":\"ok\","
        "\"citations\":[{\"id\":\"D1\",\"source\":\"memo\",\"date\":\"2026-01-01\",\"url\":\"provided://memo\",\"note\":\"n\"}],"
        "\"category_rationales\":{\"Team\":\"ok\",\"Market\":\"ok\",\"Product\":\"ok\",\"Traction\":\"ok\","
        "\"Unit Economics\":\"ok\",\"Defensibility\":\"ok\",\"Terms\":\"ok\"},"
        "\"web_sweep_findings\":[\"f1\"],\"web_sweep_sources\":[\"s1\"],"
        "\"milestones_to_monitor\":[\"m1\"],\"key_unknowns\":[\"u1\"],"
        "\"return_scenarios\":["
        "{\"scenario\":\"Pessimistic\",\"multiple\":\"0.3x\",\"probability\":\"30%\",\"rationale\":\"r\"},"
        "{\"scenario\":\"Base\",\"multiple\":\"3x\",\"probability\":\"50%\",\"rationale\":\"r\"},"
        "{\"scenario\":\"Optimistic\",\"multiple\":\"12x\",\"probability\":\"20%\",\"rationale\":\"r\"}"
        "],\"assessment_limitations\":\"none\","
        "\"verdict_one_liner\":\"Strong team but too early for conviction.\","
        "\"why_not_invest_now\":[\"Terms are stretched\",\"Traction evidence is thin\"],"
        "\"what_would_upgrade_to_invest\":[\"Show retention\",\"Clarify unit economics\"],"
        "\"assessment_process\":{\"single_deal_equivalent\":\"yes\",\"used_full_rubric\":true,"
        "\"performed_web_sweep\":true,\"reconciled_docs_with_web\":true,"
        "\"built_three_case_return_model\":true}}\n```"
    )

    payload = parse_assessment_json(raw_output)

    assert payload["deal_id"] == "d1"
    assert payload["company_name"] == "Acme"
    assert payload["verdict_one_liner"] == "Strong team but too early for conviction."


def test_validate_assessment_payload__raises_for_missing_fields() -> None:
    with pytest.raises(ValueError, match="Missing required field"):
        validate_assessment_payload({"deal_id": "d1"})


def test_codex_runner__builds_expected_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> object:
        observed["cmd"] = args[0]
        observed["input"] = kwargs.get("input")
        class Result:
            stdout = json.dumps(
                {
                    "deal_id": "d1",
                    "company_name": "Acme",
                    "category_scores": {
                        "Team": 4.0,
                        "Market": 4.0,
                        "Product": 4.0,
                        "Traction": 4.0,
                        "Unit Economics": 4.0,
                        "Defensibility": 4.0,
                        "Terms": 4.0,
                    },
                    "risk_flags": [],
                    "sectors": ["AI"],
                    "geographies": ["US"],
                    "rationale": "ok",
                    "citations": [
                        {"id": "D1", "source": "memo", "date": "2026-01-01", "url": "provided://memo", "note": "n"}
                    ],
                    "category_rationales": {
                        "Team": "ok",
                        "Market": "ok",
                        "Product": "ok",
                        "Traction": "ok",
                        "Unit Economics": "ok",
                        "Defensibility": "ok",
                        "Terms": "ok",
                    },
                    "web_sweep_findings": ["f1"],
                    "web_sweep_sources": ["s1"],
                    "milestones_to_monitor": ["m1"],
                    "key_unknowns": ["u1"],
                    "return_scenarios": [
                        {"scenario": "Pessimistic", "multiple": "0.3x", "probability": "30%", "rationale": "r"},
                        {"scenario": "Base", "multiple": "3x", "probability": "50%", "rationale": "r"},
                        {"scenario": "Optimistic", "multiple": "12x", "probability": "20%", "rationale": "r"},
                    ],
                    "assessment_limitations": "none",
                    "verdict_one_liner": "Strong team but early traction.",
                    "why_not_invest_now": ["Terms are stretched", "Traction evidence is thin"],
                    "what_would_upgrade_to_invest": ["Show retention", "Clarify unit economics"],
                    "assessment_process": {
                        "single_deal_equivalent": "yes",
                        "used_full_rubric": True,
                        "performed_web_sweep": True,
                        "reconciled_docs_with_web": True,
                        "built_three_case_return_model": True,
                    },
                }
            )
            returncode = 0

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    runner = CodexRunner()

    result = runner.run_assessment("prompt text", cwd=tmp_path)

    cmd = observed["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == "codex"
    assert cmd[1] == "--search"
    assert cmd[2] == "exec"
    assert cmd[-1] == "-"
    assert observed["input"] == "prompt text"
    assert result["deal_id"] == "d1"
    assert result["verdict_one_liner"] == "Strong team but early traction."


def test_build_assistant_runner__raises_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda command: None)
    with pytest.raises(RuntimeError, match="Required CLI 'codex' was not found in PATH"):
        build_assistant_runner("codex")
