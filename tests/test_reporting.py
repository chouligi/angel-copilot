from __future__ import annotations

from pathlib import Path

from angelcopilot_batch.models import AssessmentResult
from angelcopilot_batch.reporting import write_batch_outputs


def test_write_batch_outputs__writes_md_csv_json(tmp_path: Path) -> None:
    assessments = [
        AssessmentResult(
            deal_id="d1",
            company_name="Acme",
            category_scores={
                "Team": 4.2,
                "Market": 4.1,
                "Product": 4.0,
                "Traction": 3.9,
                "Unit Economics": 3.7,
                "Defensibility": 3.8,
                "Terms": 3.6,
            },
            risk_flags=[],
            sectors=["AI"],
            geographies=["US"],
            rationale="Solid",
            weighted_score=4.0,
            verdict="WAIT",
            attention_flag=True,
            attention_reason="Strong WAIT",
            verdict_one_liner="Compelling direction, but needs commercial proof.",
            why_not_invest_now=["Terms are stretched for stage.", "Evidence gap on traction and unit economics."],
            what_would_upgrade_to_invest=[
                "Clear paid traction plus retention milestones.",
                "Better visibility on cost structure and economics.",
            ],
        )
    ]

    output_paths = write_batch_outputs(assessments=assessments, output_dir=tmp_path, run_id="run-1")

    assert output_paths.markdown_path.exists()
    assert output_paths.csv_path.exists()
    assert output_paths.json_path.exists()
    assert output_paths.html_path is not None
    assert output_paths.html_path.exists()
    assert output_paths.markdown_path.name == "angelcopilot_batch_report.md"
    assert output_paths.csv_path.name == "angelcopilot_batch_summary.csv"
    assert output_paths.json_path.name == "angelcopilot_batch_assessments.json"

    markdown_text = output_paths.markdown_path.read_text(encoding="utf-8")
    html_text = output_paths.html_path.read_text(encoding="utf-8")

    assert "## Executive Overview" in markdown_text
    assert "## Appendix: Individual Assessments" in markdown_text
    assert "### 1. Acme (`d1`)" in markdown_text
    assert "#### Final Verdict" in markdown_text
    assert "Why not INVEST now:" in markdown_text
    assert "What would upgrade to INVEST:" in markdown_text
    assert "AngelCopilot Batch Report" in html_text
    assert "Appendix: Individual Assessments" in html_text
    assert "Final Verdict" in html_text
    assert "Why not INVEST now" in html_text
    assert "data:image/png;base64" in html_text


def test_write_batch_outputs__omits_why_not_for_invest_verdict(tmp_path: Path) -> None:
    assessments = [
        AssessmentResult(
            deal_id="d2",
            company_name="Beta",
            category_scores={
                "Team": 4.8,
                "Market": 4.6,
                "Product": 4.7,
                "Traction": 4.5,
                "Unit Economics": 4.2,
                "Defensibility": 4.4,
                "Terms": 4.1,
            },
            risk_flags=[],
            sectors=["AI"],
            geographies=["US"],
            rationale="Strong overall evidence.",
            weighted_score=4.6,
            verdict="INVEST",
            attention_flag=True,
            attention_reason="Invest threshold met.",
            verdict_one_liner="High-conviction opportunity at current evidence quality.",
            why_not_invest_now=["Not applicable."],
            what_would_upgrade_to_invest=["Not applicable."],
        )
    ]

    output_paths = write_batch_outputs(assessments=assessments, output_dir=tmp_path, run_id="run-2")
    markdown_text = output_paths.markdown_path.read_text(encoding="utf-8")
    html_text = output_paths.html_path.read_text(encoding="utf-8")

    assert "Why not INVEST now:" not in markdown_text
    assert "What would upgrade to INVEST:" not in markdown_text
    assert "Why not INVEST now:" not in html_text
    assert "What would upgrade to INVEST:" not in html_text
