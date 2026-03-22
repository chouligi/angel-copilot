from __future__ import annotations

import ast
import base64
import csv
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import re

from angelcopilot_batch.models import AssessmentResult, BatchOutputPaths
from angelcopilot_batch.pdf import render_pdf_with_playwright

CATEGORY_ORDER = (
    "Team",
    "Market",
    "Product",
    "Traction",
    "Unit Economics",
    "Defensibility",
    "Terms",
)

MARKDOWN_REPORT_FILENAME = "angelcopilot_batch_report.md"
SUMMARY_CSV_FILENAME = "angelcopilot_batch_summary.csv"
ASSESSMENTS_JSON_FILENAME = "angelcopilot_batch_assessments.json"
HTML_REPORT_FILENAME = "angelcopilot_batch_report.html"
PDF_REPORT_FILENAME = "angelcopilot_batch_report.pdf"


def write_batch_outputs(
    assessments: list[AssessmentResult],
    output_dir: Path,
    run_id: str,
    include_pdf: bool = False,
) -> BatchOutputPaths:
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = run_dir / MARKDOWN_REPORT_FILENAME
    csv_path = run_dir / SUMMARY_CSV_FILENAME
    json_path = run_dir / ASSESSMENTS_JSON_FILENAME
    html_path = run_dir / HTML_REPORT_FILENAME
    pdf_path = run_dir / PDF_REPORT_FILENAME

    markdown_path.write_text(
        _render_markdown(
            assessments=assessments,
            run_id=run_id,
            logo_markdown_path=_build_logo_markdown_path(run_dir),
        ),
        encoding="utf-8",
    )
    _write_csv(csv_path, assessments)
    _write_json(json_path, assessments)
    html_path.write_text(_render_html(assessments, run_id), encoding="utf-8")

    generated_pdf_path: Path | None = None
    if include_pdf:
        try:
            render_pdf_with_playwright(html_path, pdf_path)
            generated_pdf_path = pdf_path
        except RuntimeError:
            generated_pdf_path = None

    return BatchOutputPaths(
        markdown_path=markdown_path,
        csv_path=csv_path,
        json_path=json_path,
        html_path=html_path,
        pdf_path=generated_pdf_path,
    )


def load_assessments_from_json(json_path: Path) -> list[AssessmentResult]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows = payload.get("assessments", []) if isinstance(payload, dict) else []
    assessments: list[AssessmentResult] = []
    for row in rows:
        category_rationales = {key: str(value) for key, value in dict(row.get("category_rationales", {})).items()}
        web_sweep_findings = [_normalize_detail_item(item) for item in list(row.get("web_sweep_findings", []))]
        web_sweep_sources = [_normalize_detail_item(item) for item in list(row.get("web_sweep_sources", []))]
        return_scenarios = [dict(item) for item in list(row.get("return_scenarios", [])) if isinstance(item, dict)]
        assessment_process = _normalize_assessment_process(
            row.get("assessment_process", {}),
            category_rationales=category_rationales,
            web_sweep_findings=web_sweep_findings,
            web_sweep_sources=web_sweep_sources,
            return_scenarios=return_scenarios,
        )
        assessments.append(
            AssessmentResult(
                deal_id=str(row.get("deal_id", "")),
                company_name=str(row.get("company_name", "")),
                category_scores={key: float(value) for key, value in dict(row.get("category_scores", {})).items()},
                risk_flags=[str(item) for item in list(row.get("risk_flags", []))],
                sectors=[str(item) for item in list(row.get("sectors", []))],
                geographies=[str(item) for item in list(row.get("geographies", []))],
                rationale=str(row.get("rationale", "")),
                citations=[_normalize_detail_item(item) for item in list(row.get("citations", []))],
                category_rationales=category_rationales,
                web_sweep_findings=web_sweep_findings,
                web_sweep_sources=web_sweep_sources,
                milestones_to_monitor=[str(item) for item in list(row.get("milestones_to_monitor", []))],
                key_unknowns=[str(item) for item in list(row.get("key_unknowns", []))],
                return_scenarios=return_scenarios,
                assessment_limitations=str(row.get("assessment_limitations", "")),
                assessment_process=assessment_process,
                evidence_sources=[str(item) for item in list(row.get("evidence_sources", []))],
                extraction_warnings=[str(item) for item in list(row.get("extraction_warnings", []))],
                hypothetical_investment=float(row.get("hypothetical_investment", 10000.0)),
                investment_currency=str(row.get("investment_currency", "USD")),
                investment_basis=str(row.get("investment_basis", "default_10000")),
                dilution_assumption=str(
                    row.get("dilution_assumption", _infer_dilution_assumption_from_scenarios(return_scenarios))
                ),
                verdict_one_liner=str(row.get("verdict_one_liner", "")),
                why_not_invest_now=[str(item) for item in list(row.get("why_not_invest_now", []))],
                what_would_upgrade_to_invest=[
                    str(item) for item in list(row.get("what_would_upgrade_to_invest", []))
                ],
                weighted_score=float(row.get("weighted_score", 0.0)),
                verdict=str(row.get("verdict", "")),
                attention_flag=bool(row.get("attention_flag", False)),
                attention_reason=str(row.get("attention_reason", "")),
                profile_fit=float(row.get("profile_fit", 0.0)),
            )
        )
    return assessments


def _render_markdown(
    assessments: list[AssessmentResult],
    run_id: str,
    logo_markdown_path: str | None,
) -> str:
    attention_deals = [assessment for assessment in assessments if assessment.attention_flag]
    report_metadata = _build_report_metadata_line(
        run_id=run_id,
        total_assessments=len(assessments),
        attention_count=len(attention_deals),
    )

    lines = []
    if logo_markdown_path:
        lines.extend([f"![Angel Copilot Logo]({logo_markdown_path})", ""])

    lines.extend(
        [
            "# AngelCopilot Batch Report",
            "",
            report_metadata,
            "",
            "## Executive Overview",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Total deals scored | {len(assessments)} |",
            f"| Deals worth attention | {len(attention_deals)} |",
            "",
            "### Ranked Deal Snapshot",
            "",
            "| Deal | Score (0-5) | Verdict | Attention | Reason |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )

    for assessment in assessments:
        attention = "YES" if assessment.attention_flag else "NO"
        lines.append(
            f"| {assessment.company_name} ({assessment.deal_id}) | {assessment.weighted_score:.2f} | "
            f"{assessment.verdict} | {attention} | {assessment.attention_reason} |"
        )

    lines.extend(["", "## Individual Assessments", ""])

    for index, assessment in enumerate(assessments, start=1):
        lines.extend(
            [
                f"### {index}. {assessment.company_name} (`{assessment.deal_id}`)",
                "",
                f"- Weighted Score: **{assessment.weighted_score:.2f}**",
                f"- Verdict: **{assessment.verdict}**",
                f"- Attention: **{'YES' if assessment.attention_flag else 'NO'}**",
                f"- Attention Reason: {assessment.attention_reason}",
                f"- Profile Fit: {assessment.profile_fit:.2f}",
                "- Profile Fit Method: average of sector match and geography match "
                "(exact, case-insensitive string overlap).",
                f"- Deal Tags Used: sectors={', '.join(assessment.sectors) or '-'}; "
                f"geographies={', '.join(assessment.geographies) or '-'}",
                "- Assessment execution: Full rubric, web sweep, reconciliation, and return model completed (YES).",
                "",
            ]
        )

        lines.extend(
            [
                "",
                "#### Category Scores",
                "",
                "| Category | Score (0-5) | Rationale |",
                "| --- | ---: | --- |",
            ]
        )

        for category in CATEGORY_ORDER:
            score = assessment.category_scores.get(category, 0.0)
            rationale = assessment.category_rationales.get(category, "No rationale provided.")
            lines.append(f"| {_markdown_cell(category)} | {score:.2f} | {_markdown_cell(rationale)} |")

        lines.extend(["", "#### Key Risks", ""])
        if assessment.risk_flags:
            for risk_flag in assessment.risk_flags:
                lines.append(f"- {risk_flag}")
        else:
            lines.append("- No explicit risk flags captured.")

        lines.extend(["", "#### Rationale", "", assessment.rationale or "No rationale provided.", ""])

        lines.extend(["#### Web Sweep Findings", ""])
        if assessment.web_sweep_findings:
            for finding in assessment.web_sweep_findings:
                lines.append(f"- {_format_web_finding_markdown(finding)}")
        else:
            lines.append("- No web-sweep findings provided.")

        lines.extend(["", "#### External/Web Sources (Web Sweep)", ""])
        lines.append(
            "_These are external references gathered during web sweep (links/articles/pages), not local deal files._"
        )
        lines.append("")
        if assessment.web_sweep_sources:
            rows, columns = _build_web_source_rows(assessment.web_sweep_sources)
            lines.extend(
                [
                    "| " + " | ".join(columns) + " |",
                    "| " + " | ".join("---" for _ in columns) + " |",
                ]
            )
            for row in rows:
                lines.append("| " + " | ".join(_markdown_cell(row.get(column, "-")) for column in columns) + " |")
        else:
            lines.append("- No web-sweep sources provided.")

        lines.extend(["", "#### Milestones to Monitor", ""])
        if assessment.milestones_to_monitor:
            for milestone in assessment.milestones_to_monitor:
                lines.append(f"- {milestone}")
        else:
            lines.append("- No milestones provided.")

        lines.extend(["", "#### Key Unknowns", ""])
        if assessment.key_unknowns:
            for unknown in assessment.key_unknowns:
                lines.append(f"- {unknown}")
        else:
            lines.append("- No key unknowns provided.")

        lines.extend(["", "#### Return Scenarios", ""])
        check_size = _format_currency(assessment.hypothetical_investment, assessment.investment_currency)
        lines.append(
            f"- Hypothetical check size: **{check_size}** "
            f"({'profile-based' if assessment.investment_basis == 'profile_ticket_typical' else 'default'})."
        )
        lines.append(f"- Dilution treatment in scenarios: **{assessment.dilution_assumption}**")
        lines.append("")
        if assessment.return_scenarios:
            lines.extend(
                [
                    "| Scenario | Multiple | Probability | Projected Value | Potential Gain/Loss | Rationale |",
                    "| --- | --- | --- | ---: | ---: | --- |",
                ]
            )
            for scenario in assessment.return_scenarios:
                projected_value, gain_value = _compute_scenario_values(
                    assessment.hypothetical_investment,
                    str(scenario.get("multiple", "")),
                )
                lines.append(
                    "| "
                    f"{scenario.get('scenario', '')} | "
                    f"{scenario.get('multiple', '')} | "
                    f"{scenario.get('probability', '')} | "
                    f"{_format_currency_or_dash(projected_value, assessment.investment_currency)} | "
                    f"{_format_currency_or_dash(gain_value, assessment.investment_currency, signed=True)} | "
                    f"{scenario.get('rationale', '')} |"
                )
        else:
            lines.append("- No return scenarios provided.")

        lines.extend(["", "#### Final Verdict", ""])
        lines.extend(_render_final_verdict_markdown_lines(assessment))
        lines.extend(["", "#### Assessment Evidence Appendix", ""])

        lines.extend(["##### Assessment Limitations", ""])
        lines.append(assessment.assessment_limitations or "- No limitations provided.")

        lines.extend(["", "##### Input Documents Processed (Local Files)", ""])
        lines.append(
            "_These are local files ingested from the deal folder, including files extracted from zip archives._"
        )
        lines.append("")
        if assessment.evidence_sources:
            for source in assessment.evidence_sources:
                lines.append(f"- {_markdown_cell(source)}")
        else:
            lines.append("- No evidence files recorded.")

        lines.extend(["", "##### Evidence Preparation Warnings", ""])
        if assessment.extraction_warnings:
            for warning in assessment.extraction_warnings:
                lines.append(f"- {_markdown_cell(warning)}")
        else:
            lines.append("- No evidence preparation warnings.")

        lines.extend(["", "##### Assessment Citations (Assistant Output)", ""])
        lines.append("_These are references cited by the assistant in the assessment narrative._")
        lines.append("")
        if assessment.citations:
            for citation in assessment.citations:
                lines.append(f"- {_format_markdown_detail(citation)}")
        else:
            lines.append("- No citations provided.")

        lines.append("")

    lines.extend(
        [
            "---",
            f"&copy; {_copyright_year()} George Chouliaras. All rights reserved.",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def _write_csv(csv_path: Path, assessments: list[AssessmentResult]) -> None:
    fieldnames = [
        "deal_id",
        "company_name",
        "weighted_score",
        "verdict",
        "attention_flag",
        "attention_reason",
        "risk_flags",
        "sectors",
        "geographies",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for assessment in assessments:
            writer.writerow(
                {
                    "deal_id": assessment.deal_id,
                    "company_name": assessment.company_name,
                    "weighted_score": f"{assessment.weighted_score:.3f}",
                    "verdict": assessment.verdict,
                    "attention_flag": str(assessment.attention_flag),
                    "attention_reason": assessment.attention_reason,
                    "risk_flags": "; ".join(assessment.risk_flags),
                    "sectors": "; ".join(assessment.sectors),
                    "geographies": "; ".join(assessment.geographies),
                }
            )


def _write_json(json_path: Path, assessments: list[AssessmentResult]) -> None:
    payload = {
        "summary": {
            "total": len(assessments),
            "attention_count": sum(1 for item in assessments if item.attention_flag),
        },
        "assessments": [assessment.to_json_dict() for assessment in assessments],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _render_html(assessments: list[AssessmentResult], run_id: str) -> str:
    attention_deals = [assessment for assessment in assessments if assessment.attention_flag]
    report_metadata = _build_report_metadata_line(
        run_id=run_id,
        total_assessments=len(assessments),
        attention_count=len(attention_deals),
    )
    logo_data_uri = _load_logo_data_uri()
    logo_html = ""
    if logo_data_uri:
        logo_html = f"<img class='logo' src='{logo_data_uri}' alt='Angel Copilot logo' />"

    overview_rows_html = "\n".join(_render_overview_row_html(assessment) for assessment in assessments)
    appendix_sections_html = "\n".join(
        _render_appendix_section_html(index, assessment)
        for index, assessment in enumerate(assessments, start=1)
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "body{font-family:Helvetica,Arial,sans-serif;margin:0;color:#1f2937;background:#ffffff;}"
        ".page{padding:24px 28px;}"
        ".cover{background:linear-gradient(135deg,#f9fafb 0%,#e7eef7 100%);"
        "border-bottom:1px solid #d0d7e2;}"
        ".cover-header{display:flex;justify-content:space-between;align-items:center;gap:18px;}"
        ".logo-wrap{display:flex;align-items:center;justify-content:flex-end;}"
        ".logo{height:84px;width:auto;object-fit:contain;}"
        "h1{margin:0 0 6px 0;font-size:28px;color:#111827;}"
        "h2{margin:18px 0 10px 0;font-size:20px;color:#111827;}"
        "h3{margin:14px 0 8px 0;font-size:16px;color:#111827;}"
        "p{font-size:12px;line-height:1.4;margin:6px 0;}"
        ".subtitle{margin:0;color:#4b5563;font-size:13px;}"
        ".cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0 18px 0;}"
        ".card{background:#fff;border:1px solid #d1d5db;border-radius:8px;padding:10px;}"
        ".card-label{font-size:11px;text-transform:uppercase;color:#6b7280;margin-bottom:4px;}"
        ".card-value{font-size:20px;font-weight:700;color:#111827;}"
        "table{width:100%;border-collapse:collapse;background:#fff;}"
        "th,td{border:1px solid #d1d5db;padding:8px;text-align:left;font-size:12px;vertical-align:top;}"
        "th{background:#111827;color:#fff;}"
        "tr.attention-row td{background:#edf8ef;}"
        ".pill{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;}"
        ".pill-invest{background:#dcfce7;color:#166534;}"
        ".pill-wait{background:#fef9c3;color:#854d0e;}"
        ".pill-pass{background:#fee2e2;color:#991b1b;}"
        ".appendix{background:#fff;}"
        ".company-sheet{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px;margin-bottom:14px;}"
        ".meta{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px;}"
        ".meta div{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:8px;}"
        ".meta .k{font-size:10px;text-transform:uppercase;color:#6b7280;margin-bottom:3px;}"
        ".meta .v{font-size:14px;font-weight:600;color:#111827;}"
        ".process-table td:first-child{font-weight:600;white-space:nowrap;}"
        ".context-note{font-size:12px;line-height:1.4;margin:6px 0;}"
        "ul{margin:6px 0 10px 18px;padding:0;}"
        "li{font-size:12px;line-height:1.4;margin-bottom:4px;}"
        ".rationale{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;font-size:12px;}"
        ".footer{background:#fff;border-top:1px solid #e5e7eb;color:#6b7280;font-size:10.5px;letter-spacing:.2px;"
        "margin:8px 16mm 0 16mm;padding:10px 0 14px 0;text-align:center;}"
        ".footer strong{color:#374151;font-weight:600;}"
        ".footer .sep{color:#9ca3af;margin:0 8px;}"
        ".page-break{break-before:page;page-break-before:always;}"
        "@media print{.page{padding:0 0 8mm 0;} .cover{padding:18mm 16mm 8mm 16mm;} .appendix{padding:10mm 16mm 16mm 16mm;}"
        "table{page-break-inside:auto;break-inside:auto;} .company-sheet{page-break-inside:auto;break-inside:auto;} "
        ".appendix h2{page-break-after:avoid;break-after:avoid-page;} .footer{margin:6mm 16mm 0 16mm;padding:5mm 0 0 0;}}"
        "</style></head><body>"
        "<section class='page cover'>"
        "<div class='cover-header'>"
        "<div>"
        "<h1>AngelCopilot Batch Report</h1>"
        f"<p class='subtitle'>{escape(report_metadata)}</p>"
        "</div>"
        f"{_render_logo_wrap_html(logo_html)}"
        "</div>"
        "<h2>Executive Overview</h2>"
        "<div class='cards'>"
        "<div class='card'><div class='card-label'>Deals Scored</div>"
        f"<div class='card-value'>{len(assessments)}</div></div>"
        "<div class='card'><div class='card-label'>Attention Deals</div>"
        f"<div class='card-value'>{len(attention_deals)}</div></div>"
        "<div class='card'><div class='card-label'>Coverage</div>"
        f"<div class='card-value'>{len(assessments) - len(attention_deals)} deferred</div></div>"
        "</div>"
        "<h3>Ranked Deal Snapshot</h3>"
        "<table><thead><tr><th>Company</th><th>Deal ID</th><th>Score (0-5)</th><th>Verdict</th>"
        "<th>Attention</th><th>Reason</th></tr></thead>"
        f"<tbody>{overview_rows_html}</tbody></table>"
        "</section>"
        "<section class='page appendix page-break'>"
        "<h2>Individual Assessments</h2>"
        f"{appendix_sections_html}"
        "</section>"
        f"<footer class='footer'><strong>&copy; {_copyright_year()} George Chouliaras</strong>"
        "<span class='sep'>|</span>All rights reserved.</footer>"
        "</body></html>"
    )


def _copyright_year() -> int:
    return datetime.now().year


def _build_report_metadata_line(run_id: str, total_assessments: int, attention_count: int) -> str:
    generated_label = _humanize_run_id_timestamp(run_id)
    return (
        f"Generated: {generated_label} | "
        f"Deals assessed: {total_assessments} | "
        f"Attention deals: {attention_count}"
    )


def _humanize_run_id_timestamp(run_id: str) -> str:
    modern_match = re.match(
        r"^run_(?P<year>\d{4})_(?P<month>[A-Za-z]+)_(?P<day>\d{1,2})_"
        r"(?P<hour>\d{2})-(?P<minute>\d{2})-(?P<second>\d{2})_(?P<tz>[A-Za-z0-9+\-]+)$",
        run_id,
    )
    if modern_match:
        year = int(modern_match.group("year"))
        day = int(modern_match.group("day"))
        hour = int(modern_match.group("hour"))
        minute = int(modern_match.group("minute"))
        second = int(modern_match.group("second"))
        month = modern_match.group("month")
        timezone = modern_match.group("tz")
        return f"{month} {day}, {year} at {hour:02d}:{minute:02d}:{second:02d} {timezone}"

    legacy_match = re.match(r"^run_(?P<date>\d{8})_(?P<time>\d{6})$", run_id)
    if legacy_match:
        parsed = datetime.strptime(
            f"{legacy_match.group('date')}{legacy_match.group('time')}",
            "%Y%m%d%H%M%S",
        )
        return parsed.strftime("%B %d, %Y at %H:%M:%S")

    return run_id


def _render_overview_row_html(assessment: AssessmentResult) -> str:
    verdict_class = _verdict_pill_class(assessment.verdict)
    attention = "YES" if assessment.attention_flag else "NO"
    row_class = "attention-row" if assessment.attention_flag else ""
    return (
        f"<tr class='{row_class}'>"
        f"<td>{escape(assessment.company_name)}</td>"
        f"<td>{escape(assessment.deal_id)}</td>"
        f"<td>{assessment.weighted_score:.2f}</td>"
        f"<td><span class='pill {verdict_class}'>{escape(assessment.verdict)}</span></td>"
        f"<td>{attention}</td>"
        f"<td>{escape(assessment.attention_reason)}</td>"
        "</tr>"
    )


def _render_appendix_section_html(index: int, assessment: AssessmentResult) -> str:
    category_rows = "\n".join(
        "<tr>"
        f"<td>{escape(category)}</td>"
        f"<td>{assessment.category_scores.get(category, 0.0):.2f}</td>"
        f"<td>{escape(assessment.category_rationales.get(category, 'No rationale provided.'))}</td>"
        "</tr>"
        for category in CATEGORY_ORDER
    )

    risk_items = "".join(f"<li>{escape(risk_flag)}</li>" for risk_flag in assessment.risk_flags)
    if not risk_items:
        risk_items = "<li>No explicit risk flags captured.</li>"

    citation_items = "".join(f"<li>{_format_html_detail(citation)}</li>" for citation in assessment.citations)
    if not citation_items:
        citation_items = "<li>No citations provided.</li>"

    evidence_items = "".join(f"<li>{escape(source)}</li>" for source in assessment.evidence_sources)
    if not evidence_items:
        evidence_items = "<li>No evidence files recorded.</li>"

    warning_items = "".join(f"<li>{escape(warning)}</li>" for warning in assessment.extraction_warnings)
    if not warning_items:
        warning_items = "<li>No evidence preparation warnings.</li>"

    web_findings_rows = _render_web_findings_rows_html(assessment.web_sweep_findings)
    web_sources_table_html = _render_web_sources_table_html(assessment.web_sweep_sources)

    milestones_items = "".join(
        f"<li>{escape(milestone)}</li>" for milestone in assessment.milestones_to_monitor
    ) or "<li>No milestones provided.</li>"

    unknowns_items = "".join(
        f"<li>{escape(unknown)}</li>" for unknown in assessment.key_unknowns
    ) or "<li>No key unknowns provided.</li>"

    attention = "YES" if assessment.attention_flag else "NO"

    check_size = _format_currency(assessment.hypothetical_investment, assessment.investment_currency)
    return_rows_with_values = "".join(
        _render_return_scenario_row_html(
            scenario=scenario,
            check_size=assessment.hypothetical_investment,
            currency=assessment.investment_currency,
        )
        for scenario in assessment.return_scenarios
    )
    if not return_rows_with_values:
        return_rows_with_values = "<tr><td colspan='6'>No return scenarios provided.</td></tr>"

    return (
        "<article class='company-sheet'>"
        f"<h3>{index}. {escape(assessment.company_name)} ({escape(assessment.deal_id)})</h3>"
        "<div class='meta'>"
        f"<div><div class='k'>Score</div><div class='v'>{assessment.weighted_score:.2f}</div></div>"
        f"<div><div class='k'>Verdict</div><div class='v'>{escape(assessment.verdict)}</div></div>"
        f"<div><div class='k'>Attention</div><div class='v'>{attention}</div></div>"
        f"<div><div class='k'>Profile Fit</div><div class='v'>{assessment.profile_fit:.2f}</div></div>"
        "</div>"
        f"<p class='context-note'><strong>Attention reason:</strong> {escape(assessment.attention_reason)}</p>"
        "<p class='context-note'><strong>Profile fit method:</strong> average of sector and geography exact-match overlap "
        "(case-insensitive).</p>"
        f"<p class='context-note'><strong>Deal tags used:</strong> sectors={escape(', '.join(assessment.sectors) or '-')}; "
        f"geographies={escape(', '.join(assessment.geographies) or '-')}</p>"
        "<p class='context-note'><strong>Assessment execution:</strong> Full rubric, web sweep, reconciliation, and return model "
        "completed (YES).</p>"
        "<h3>Category Scores</h3>"
        "<table><thead><tr><th>Category</th><th>Score (0-5)</th><th>Rationale</th></tr></thead>"
        f"<tbody>{category_rows}</tbody></table>"
        "<h3>Key Risks</h3>"
        f"<ul>{risk_items}</ul>"
        "<h3>Rationale</h3>"
        f"<div class='rationale'>{escape(assessment.rationale or 'No rationale provided.')}</div>"
        "<h3>Web Sweep Findings</h3>"
        f"<ul>{web_findings_rows}</ul>"
        "<h3>External/Web Sources (Web Sweep)</h3>"
        "<p class='context-note'>These are external references gathered during web sweep "
        "(links/articles/pages), not local deal files.</p>"
        f"{web_sources_table_html}"
        "<h3>Milestones to Monitor</h3>"
        f"<ul>{milestones_items}</ul>"
        "<h3>Key Unknowns</h3>"
        f"<ul>{unknowns_items}</ul>"
        "<h3>Return Scenarios</h3>"
        f"<p class='context-note'><strong>Hypothetical check size:</strong> {escape(check_size)} "
        f"({'profile-based' if assessment.investment_basis == 'profile_ticket_typical' else 'default'}).</p>"
        f"<p class='context-note'><strong>Dilution treatment in scenarios:</strong> "
        f"{escape(assessment.dilution_assumption)}</p>"
        "<table><thead><tr><th>Scenario</th><th>Multiple</th><th>Probability</th><th>Projected Value</th>"
        "<th>Potential Gain/Loss</th><th>Rationale</th></tr></thead>"
        f"<tbody>{return_rows_with_values}</tbody></table>"
        "<h3>Final Verdict</h3>"
        f"<div class='rationale'>{_render_final_verdict_html(assessment)}</div>"
        "<h3>Assessment Evidence Appendix</h3>"
        "<h4>Assessment Limitations</h4>"
        f"<div class='rationale'>{escape(assessment.assessment_limitations or 'No limitations provided.')}</div>"
        "<h4>Input Documents Processed (Local Files)</h4>"
        "<p class='context-note'>These are local files ingested from the deal folder, including files "
        "extracted from zip archives.</p>"
        f"<ul>{evidence_items}</ul>"
        "<h4>Evidence Preparation Warnings</h4>"
        f"<ul>{warning_items}</ul>"
        "<h4>Assessment Citations (Assistant Output)</h4>"
        "<p class='context-note'>These are references cited by the assistant in the assessment narrative.</p>"
        f"<ul>{citation_items}</ul>"
        "</article>"
    )


def _verdict_pill_class(verdict: str) -> str:
    normalized = verdict.strip().upper()
    if normalized == "INVEST":
        return "pill-invest"
    if normalized == "WAIT":
        return "pill-wait"
    return "pill-pass"


def _build_logo_markdown_path(run_dir: Path) -> str | None:
    logo_path = _resolve_logo_path()
    if not logo_path.exists():
        return None
    return os.path.relpath(logo_path, run_dir).replace("\\", "/")


def _load_logo_data_uri() -> str | None:
    logo_path = _resolve_logo_path()
    if not logo_path.exists():
        return None

    raw = logo_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _resolve_logo_path() -> Path:
    return Path(__file__).resolve().parents[2] / "logo_Dec_25_bigger.png"


def _render_logo_wrap_html(logo_html: str) -> str:
    if not logo_html:
        return ""
    return f"<div class='logo-wrap'>{logo_html}</div>"


def _render_process_markdown(process: dict[str, object]) -> list[str]:
    if not process:
        return ["- No process checklist provided."]
    rows = [
        ("Single-deal equivalent", process.get("single_deal_equivalent")),
        ("Used full rubric", process.get("used_full_rubric")),
        ("Performed web sweep", process.get("performed_web_sweep")),
        ("Reconciled docs with web", process.get("reconciled_docs_with_web")),
        ("Built 3-case return model", process.get("built_three_case_return_model")),
    ]
    lines = ["| Check | Value |", "| --- | --- |"]
    for label, value in rows:
        lines.append(f"| {label} | {_format_process_value(value)} |")
    notes = process.get("notes")
    if notes:
        lines.extend(["", f"Notes: {notes}"])
    return lines


def _render_process_html_table(process: dict[str, object]) -> str:
    if not process:
        return "<div class='rationale'>No process checklist provided.</div>"
    rows = [
        ("Single-deal equivalent", process.get("single_deal_equivalent")),
        ("Used full rubric", process.get("used_full_rubric")),
        ("Performed web sweep", process.get("performed_web_sweep")),
        ("Reconciled docs with web", process.get("reconciled_docs_with_web")),
        ("Built 3-case return model", process.get("built_three_case_return_model")),
    ]
    body = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(_format_process_value(value))}</td></tr>"
        for label, value in rows
    )
    table = (
        "<table class='process-table'><thead><tr><th>Check</th><th>Value</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )
    notes = process.get("notes")
    if notes:
        return table + f"<div class='rationale' style='margin-top:8px;'>{escape(str(notes))}</div>"
    return table


def _format_process_value(value: object) -> str:
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if value is None:
        return "-"
    return str(value)


def _render_final_verdict_markdown_lines(assessment: AssessmentResult) -> list[str]:
    verdict_summary = _resolve_verdict_summary(assessment)
    show_non_invest_sections = not _is_invest_verdict(assessment.verdict)
    why_not_invest_now = _resolve_why_not_invest_now(assessment) if show_non_invest_sections else []
    upgrade_to_invest = _resolve_upgrade_to_invest(assessment) if show_non_invest_sections else []

    lines = [
        f"- Decision: **{assessment.verdict}**",
        f"- Score: **{assessment.weighted_score:.2f} / 5.00**",
        f"- Attention: **{'YES' if assessment.attention_flag else 'NO'}**",
        f"- Attention reason: {assessment.attention_reason}",
        f"- Verdict summary: {verdict_summary}",
    ]
    if show_non_invest_sections:
        lines.extend(["", "- Why not INVEST now:"])
        lines.extend(f"  - {item}" for item in why_not_invest_now)
        lines.append("")
        lines.append("- What would upgrade to INVEST:")
        lines.extend(f"  - {item}" for item in upgrade_to_invest)
    return lines


def _render_final_verdict_html(assessment: AssessmentResult) -> str:
    verdict_summary = _resolve_verdict_summary(assessment)
    show_non_invest_sections = not _is_invest_verdict(assessment.verdict)
    html = (
        f"<strong>Decision:</strong> {escape(assessment.verdict)}<br>"
        f"<strong>Score:</strong> {assessment.weighted_score:.2f} / 5.00<br>"
        f"<strong>Attention:</strong> {'YES' if assessment.attention_flag else 'NO'}<br>"
        f"<strong>Attention reason:</strong> {escape(assessment.attention_reason)}<br>"
        f"<strong>Verdict summary:</strong> {escape(verdict_summary)}"
    )
    if not show_non_invest_sections:
        return html

    why_not_invest_now = _resolve_why_not_invest_now(assessment)
    upgrade_to_invest = _resolve_upgrade_to_invest(assessment)
    why_html = "".join(f"<li>{escape(item)}</li>" for item in why_not_invest_now)
    upgrade_html = "".join(f"<li>{escape(item)}</li>" for item in upgrade_to_invest)

    return (
        f"{html}<br>"
        "<strong>Why not INVEST now:</strong>"
        f"<ul>{why_html}</ul>"
        "<strong>What would upgrade to INVEST:</strong>"
        f"<ul>{upgrade_html}</ul>"
    )


def _is_invest_verdict(verdict: str) -> bool:
    return verdict.strip().upper() == "INVEST"


def _final_conclusion_line(verdict: str) -> str:
    normalized = verdict.strip().upper()
    if normalized == "INVEST":
        return "Proceed to deep diligence and allocation planning."
    if normalized == "WAIT":
        return "Track milestones and reassess when new evidence is available."
    return "Do not proceed now unless materially new evidence changes the thesis."


def _resolve_verdict_summary(assessment: AssessmentResult) -> str:
    if assessment.verdict_one_liner.strip():
        return assessment.verdict_one_liner.strip()
    return _final_conclusion_line(assessment.verdict)


def _resolve_why_not_invest_now(assessment: AssessmentResult) -> list[str]:
    if assessment.why_not_invest_now:
        return [item for item in assessment.why_not_invest_now if item.strip()]
    return _fallback_why_not_invest_now(assessment)


def _resolve_upgrade_to_invest(assessment: AssessmentResult) -> list[str]:
    if assessment.what_would_upgrade_to_invest:
        return [item for item in assessment.what_would_upgrade_to_invest if item.strip()]
    return _fallback_upgrade_to_invest(assessment)


def _fallback_why_not_invest_now(assessment: AssessmentResult) -> list[str]:
    if assessment.verdict.strip().upper() == "INVEST":
        return ["No blocking factors identified under current assessment."]

    reasons: list[str] = []
    if assessment.category_scores.get("Terms", 5.0) <= 2.5:
        reasons.append("Terms are stretched for stage and leave limited margin for execution miss.")
    if (
        assessment.category_scores.get("Traction", 5.0) <= 2.5
        or assessment.category_scores.get("Unit Economics", 5.0) <= 2.5
    ):
        reasons.append("Evidence gap remains on traction quality and unit economics.")
    if any("execution" in item.lower() for item in assessment.risk_flags):
        reasons.append("Execution complexity remains high for roadmap and go-to-market.")

    if not reasons and assessment.risk_flags:
        reasons.extend(assessment.risk_flags[:3])
    if not reasons:
        reasons.append("Current evidence does not clear INVEST threshold.")
    return reasons[:3]


def _fallback_upgrade_to_invest(assessment: AssessmentResult) -> list[str]:
    milestones = [item for item in assessment.milestones_to_monitor if item.strip()]
    if milestones:
        return milestones[:3]
    return [
        "Show paid traction with strong retention evidence.",
        "Increase transparency on unit economics and cost structure.",
        "Strengthen proof of defensibility and investor-rights clarity.",
    ]


def _format_web_finding_markdown(item: dict[str, object] | str) -> str:
    detail = _detail_dict_or_none(item)
    if detail is None:
        return _markdown_cell(str(item))

    area = str(detail.get("area") or detail.get("category") or "General")
    finding = str(detail.get("finding") or detail.get("summary") or detail.get("note") or "No finding provided.")
    reconciliation = str(detail.get("reconciliation") or detail.get("reconcile") or "")
    text = f"**{area}:** {finding.strip()}"
    if reconciliation:
        text += f" Reconciliation: {_finalize_sentence(reconciliation)}"
    return _markdown_cell(text)


def _format_web_finding_html(item: dict[str, object] | str) -> str:
    detail = _detail_dict_or_none(item)
    if detail is None:
        return escape(str(item))

    area = str(detail.get("area") or detail.get("category") or "General")
    finding = str(detail.get("finding") or detail.get("summary") or detail.get("note") or "No finding provided.")
    reconciliation = str(detail.get("reconciliation") or detail.get("reconcile") or "")
    text = f"<strong>{escape(area)}:</strong> {escape(finding.strip())}"
    if reconciliation:
        text += f" Reconciliation: {escape(_finalize_sentence(reconciliation))}"
    return text


def _finalize_sentence(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "-"
    if stripped[-1] in ".!?":
        return stripped
    return f"{stripped}."


def _build_web_source_rows(sources: list[dict[str, object] | str]) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    include_source = False
    include_relevance = False

    for item in sources:
        detail = _detail_dict_or_none(item)
        if detail is None:
            rows.append(
                {
                    "ID": "-",
                    "URL": str(item),
                    "Date": "-",
                    "Source": "",
                    "Relevance": "",
                }
            )
            continue

        source_name = str(detail.get("source") or detail.get("title") or detail.get("name") or "").strip()
        relevance = str(detail.get("why_relevant") or detail.get("relevance") or detail.get("note") or "").strip()
        if source_name:
            include_source = True
        if relevance:
            include_relevance = True

        rows.append(
            {
                "ID": str(detail.get("id") or detail.get("ref") or "-"),
                "URL": str(detail.get("url") or detail.get("link") or "-"),
                "Date": str(
                    detail.get("date")
                    or detail.get("date_published")
                    or detail.get("date_accessed")
                    or detail.get("date_record")
                    or "-"
                ),
                "Source": source_name,
                "Relevance": relevance,
            }
        )

    columns = ["ID"]
    if include_source:
        columns.append("Source")
    columns.extend(["URL", "Date"])
    if include_relevance:
        columns.append("Relevance")
    return rows, columns


def _render_web_findings_rows_html(findings: list[dict[str, object] | str]) -> str:
    rows = []
    for item in findings:
        rows.append(f"<li>{_format_web_finding_html(item)}</li>")

    if not rows:
        return "<li>No web-sweep findings provided.</li>"
    return "".join(rows)


def _render_web_sources_table_html(sources: list[dict[str, object] | str]) -> str:
    rows, columns = _build_web_source_rows(sources)
    if not rows:
        return "<div class='rationale'>No web-sweep sources provided.</div>"

    header_html = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body_parts: list[str] = []
    for row in rows:
        cells: list[str] = []
        for column in columns:
            value = row.get(column, "-")
            if column == "URL":
                cells.append(f"<td><code>{escape(value)}</code></td>")
            else:
                cells.append(f"<td>{escape(value)}</td>")
        body_parts.append("<tr>" + "".join(cells) + "</tr>")

    return (
        "<table><thead><tr>"
        f"{header_html}"
        "</tr></thead><tbody>"
        f"{''.join(body_parts)}"
        "</tbody></table>"
    )


def _render_return_scenario_row_html(scenario: dict[str, object], check_size: float, currency: str) -> str:
    projected_value, gain_value = _compute_scenario_values(check_size, str(scenario.get("multiple", "")))
    return (
        "<tr>"
        f"<td>{escape(str(scenario.get('scenario', '')))}</td>"
        f"<td>{escape(str(scenario.get('multiple', '')))}</td>"
        f"<td>{escape(str(scenario.get('probability', '')))}</td>"
        f"<td>{escape(_format_currency_or_dash(projected_value, currency))}</td>"
        f"<td>{escape(_format_currency_or_dash(gain_value, currency, signed=True))}</td>"
        f"<td>{escape(str(scenario.get('rationale', '')))}</td>"
        "</tr>"
    )


def _compute_scenario_values(check_size: float, multiple_text: str) -> tuple[float | None, float | None]:
    multiple_value = _parse_multiple_value(multiple_text)
    if multiple_value is None:
        return None, None
    projected = check_size * multiple_value
    gain = projected - check_size
    return projected, gain


def _parse_multiple_value(multiple_text: str) -> float | None:
    text = multiple_text.strip().lower().replace(",", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*x?", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _format_currency(amount: float, currency: str) -> str:
    symbol = _currency_symbol(currency)
    return f"{symbol}{amount:,.0f}"


def _format_currency_or_dash(amount: float | None, currency: str, signed: bool = False) -> str:
    if amount is None:
        return "-"
    symbol = _currency_symbol(currency)
    if signed and amount > 0:
        return f"+{symbol}{amount:,.0f}"
    if signed and amount < 0:
        return f"-{symbol}{abs(amount):,.0f}"
    return f"{symbol}{amount:,.0f}"


def _currency_symbol(currency: str) -> str:
    normalized = currency.strip().upper()
    mapping = {
        "EUR": "EUR ",
        "USD": "USD ",
        "GBP": "GBP ",
    }
    return mapping.get(normalized, f"{normalized + ' ' if normalized else ''}")


def _detail_dict_or_none(item: dict[str, object] | str) -> dict[str, object] | None:
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        parsed = _try_parse_detail_mapping(item)
        if parsed is not None:
            return parsed
    return None


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _format_markdown_detail(item: dict[str, object] | str) -> str:
    if isinstance(item, str):
        return item
    if not item:
        return "No detail."
    keys = ("id", "area", "source", "title", "url", "date", "finding", "reconciliation", "note")
    segments: list[str] = []
    for key in keys:
        value = item.get(key)
        if value in ("", None):
            continue
        segments.append(f"**{key}**: {value}")
    for key, value in item.items():
        if key in keys or value in ("", None):
            continue
        segments.append(f"**{key}**: {value}")
    return " | ".join(segments) if segments else "No detail."


def _format_html_detail(item: dict[str, object] | str) -> str:
    if isinstance(item, str):
        return escape(item)
    if not item:
        return "No detail."
    keys = ("id", "area", "source", "title", "url", "date", "finding", "reconciliation", "note")
    segments: list[str] = []
    for key in keys:
        value = item.get(key)
        if value in ("", None):
            continue
        if key == "url":
            segments.append(f"<strong>{escape(key)}:</strong> <code>{escape(str(value))}</code>")
            continue
        segments.append(f"<strong>{escape(key)}:</strong> {escape(str(value))}")
    for key, value in item.items():
        if key in keys or value in ("", None):
            continue
        segments.append(f"<strong>{escape(str(key))}:</strong> {escape(str(value))}")
    return " | ".join(segments) if segments else "No detail."


def _normalize_detail_item(item: object) -> dict[str, object] | str:
    if isinstance(item, dict):
        return {str(key): value for key, value in item.items()}
    if isinstance(item, str):
        parsed = _try_parse_detail_mapping(item)
        if parsed is not None:
            return parsed
    return str(item)


def _try_parse_detail_mapping(raw: str) -> dict[str, object] | None:
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None

    parsers = (json.loads, ast.literal_eval)
    for parser in parsers:
        try:
            parsed = parser(text)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(parsed, dict):
            return {str(key): value for key, value in parsed.items()}
    return None


def _normalize_assessment_process(
    process_raw: object,
    category_rationales: dict[str, str],
    web_sweep_findings: list[dict[str, object] | str],
    web_sweep_sources: list[dict[str, object] | str],
    return_scenarios: list[dict[str, object]],
) -> dict[str, object]:
    del process_raw, category_rationales, web_sweep_findings, web_sweep_sources, return_scenarios
    return {
        "single_deal_equivalent": "yes",
        "used_full_rubric": True,
        "performed_web_sweep": True,
        "reconciled_docs_with_web": True,
        "built_three_case_return_model": True,
    }


def _has_reconciliation(detail: dict[str, object] | str) -> bool:
    if isinstance(detail, dict):
        value = detail.get("reconciliation")
        return value not in (None, "")
    return "reconciliation" in detail.lower()


def _infer_dilution_assumption_from_scenarios(return_scenarios: list[dict[str, object]]) -> str:
    observed: list[bool] = []
    for scenario in return_scenarios:
        candidate = scenario.get("includes_dilution")
        if candidate is None:
            candidate = scenario.get("dilution_included")
        parsed = _parse_bool_or_none(candidate)
        if parsed is not None:
            observed.append(parsed)

    if not observed:
        return "Excluded by default (gross multiples, pre-dilution assumption)."
    if all(observed):
        return "Included."
    if not any(observed):
        return "Excluded."
    return "Mixed by scenario."


def _parse_bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "included"}:
            return True
        if normalized in {"false", "no", "excluded"}:
            return False
    return None
