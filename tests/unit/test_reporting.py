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
            evidence_sources=["/tmp/source/deck.pdf", "/tmp/source/archive.zip!inner/memo.txt"],
            extraction_warnings=["No supported docs found in archive: /tmp/source/empty.zip"],
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
    assert "## Individual Assessments" in markdown_text
    assert "### 1. Acme (`d1`)" in markdown_text
    assert "#### Final Verdict" in markdown_text
    assert "#### Assessment Evidence Appendix" in markdown_text
    assert "##### Input Documents Processed (Local Files)" in markdown_text
    assert "/tmp/source/archive.zip!inner/memo.txt" in markdown_text
    assert "##### Evidence Preparation Warnings" in markdown_text
    assert "#### External/Web Sources (Web Sweep)" in markdown_text
    assert "##### Assessment Citations (Assistant Output)" in markdown_text
    assert markdown_text.index("#### Final Verdict") < markdown_text.index("#### Assessment Evidence Appendix")
    assert "Why not INVEST now:" in markdown_text
    assert "What would upgrade to INVEST:" in markdown_text
    assert "AngelCopilot Dealflow Triage Report" in html_text
    assert "Individual Assessments" in html_text
    assert "Input Documents Processed (Local Files)" in html_text
    assert "Evidence Preparation Warnings" in html_text
    assert "External/Web Sources (Web Sweep)" in html_text
    assert "Assessment Citations (Assistant Output)" in html_text
    assert "Final Verdict" in html_text
    assert "Assessment Evidence Appendix" in html_text
    assert html_text.index("Final Verdict") < html_text.index("Assessment Evidence Appendix")
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


def test_write_batch_outputs__web_source_url_cells_are_wrap_safe(tmp_path: Path) -> None:
    assessments = [
        AssessmentResult(
            deal_id="d3",
            company_name="Gamma",
            category_scores={
                "Team": 4.0,
                "Market": 3.9,
                "Product": 4.1,
                "Traction": 3.8,
                "Unit Economics": 3.7,
                "Defensibility": 3.6,
                "Terms": 3.5,
            },
            risk_flags=[],
            sectors=["Infra SaaS"],
            geographies=["EU"],
            rationale="Reasonable",
            weighted_score=3.9,
            verdict="WAIT",
            attention_flag=False,
            attention_reason="Below threshold",
            web_sweep_sources=[
                {
                    "id": "W1",
                    "source": "Very Long Source Name",
                    "url": "https://example.com/this/is/a/very/long/url/that/should/not/overflow/in/pdf/"
                    "rendering/even/when/it/contains/long/unbroken/segments/and/query"
                    "?token=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "date": "2026-04-06",
                    "why_relevant": "Formatting stress test for wrap behavior.",
                }
            ],
        )
    ]

    output_paths = write_batch_outputs(assessments=assessments, output_dir=tmp_path, run_id="run-3")
    html_text = output_paths.html_path.read_text(encoding="utf-8")

    assert "class='web-sources-table'" in html_text
    assert "class='url-cell'" in html_text
    assert ".web-sources-table td.url-cell code{display:block;}" in html_text
    assert "overflow-wrap:anywhere" in html_text
    assert "table-layout:fixed" in html_text
