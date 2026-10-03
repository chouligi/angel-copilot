"""Render a decision-first memo and a separate evidence appendix from shared blocks."""
from __future__ import annotations

import ast
import base64
import csv
from dataclasses import fields
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.parse import quote

from angelcopilot.models import AssessmentResult, BatchOutputPaths, InvestorProfile
from angelcopilot.scoring import CATEGORY_WEIGHTS, apply_scoring_rules
from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.pdf import render_pdf_with_playwright

CATEGORY_ORDER = tuple(CATEGORY_WEIGHTS)
MARKDOWN_REPORT_FILENAME = "angelcopilot_batch_report.md"
SUMMARY_CSV_FILENAME = "angelcopilot_batch_summary.csv"
ASSESSMENTS_JSON_FILENAME = "angelcopilot_batch_assessments.json"
HTML_REPORT_FILENAME = "angelcopilot_batch_report.html"
PDF_REPORT_FILENAME = "angelcopilot_batch_report.pdf"
DISCLAIMER = "This is for educational purposes and not financial, legal, or tax advice."


def _prepared(a: AssessmentResult) -> AssessmentResult:
    if a.schema_version == 2:
        validate_assessment_payload(a.to_json_dict())
    known = {f.name for f in fields(InvestorProfile)}
    constraints = {k: v for k, v in a.investor_constraints.items() if k in known}
    if not constraints:
        constraints = {"currency": a.investment_currency}
    return apply_scoring_rules(a, InvestorProfile(**constraints))


def write_batch_outputs(assessments: list[AssessmentResult], output_dir: Path,
                        run_id: str, include_pdf: bool = False) -> BatchOutputPaths:
    # Enforce decision invariants even when called directly or rebuilding JSON.
    assessments = [_prepared(a) for a in assessments]
    assessments.sort(key=lambda a: ({"INVEST": 0, "WAIT": 1, "PASS": 2}[a.verdict], -(a.weighted_score or 0)))
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    md = run_dir / MARKDOWN_REPORT_FILENAME
    html = run_dir / HTML_REPORT_FILENAME
    csv_path = run_dir / SUMMARY_CSV_FILENAME
    json_path = run_dir / ASSESSMENTS_JSON_FILENAME
    md.write_text(_render_markdown(assessments, run_id, None), encoding="utf-8")
    html.write_text(_render_html(assessments, run_id), encoding="utf-8")
    _write_csv(csv_path, assessments)
    json_path.write_text(json.dumps({"schema_version": 2, "run_id": run_id,
                                     "assessments": [a.to_json_dict() for a in assessments]}, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    pdf = run_dir / PDF_REPORT_FILENAME if include_pdf else None
    if pdf:
        render_pdf_with_playwright(html, pdf)  # Requested PDF failures must be visible.
    return BatchOutputPaths(md, csv_path, json_path, html, pdf)


def load_assessments_from_json(json_path: Path) -> list[AssessmentResult]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows = payload.get("assessments", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Assessment artifact must contain a list of assessments")
    allowed = {f.name for f in fields(AssessmentResult)}
    assessments = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each assessment must be an object")
        data = {k: v for k, v in row.items() if k in allowed}
        for key, default in {"deal_id": "", "company_name": "", "category_scores": {}, "risk_flags": [],
                             "sectors": [], "geographies": [], "rationale": ""}.items():
            data.setdefault(key, default)
        # Preserve source metadata: a historical 'yes' is not upgraded or manufactured.
        for key in ("citations", "web_sweep_sources", "web_sweep_findings"):
            data[key] = [_detail(item) for item in data.get(key, [])]
        assessments.append(AssessmentResult(**data))
    return assessments


def _money(value: float, currency: str) -> str:
    return f"{currency} {value:,.0f}"


def _cheque_now(a: AssessmentResult) -> str:
    return _money(a.recommended_investment, a.investment_currency) if a.verdict == "INVEST" else "No cheque"


def _score(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "Not scored"


def _detail(item: object) -> object:
    if isinstance(item, str) and item.strip().startswith("{"):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(item)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, SyntaxError):
                pass
    return item


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", value)


def _sources(a: AssessmentResult) -> list[dict[str, str]]:
    result = []
    used = set()
    for index, raw in enumerate([*a.citations, *a.web_sweep_sources], 1):
        raw = _detail(raw)
        item = raw if isinstance(raw, dict) else {"source": str(raw)}
        sid = str(item.get("id") or item.get("ref") or f"S{index}")
        if sid in used:
            continue
        used.add(sid)
        url = str(item.get("url") or item.get("link") or "")
        title = str(item.get("title") or item.get("source") or item.get("name") or "Source")
        if not _http(url) and url:
            # Full input paths remain in the JSON artifact, not printed across pages.
            title = title or Path(url).name
        result.append({"id": sid, "title": title, "url": url,
                       "date": str(item.get("date_published") or item.get("date") or "Not recorded"),
                       "accessed": str(item.get("date_accessed") or "Not recorded"),
                       "type": str(item.get("source_type") or ("Public source" if _http(url) else "Supplied document / source")),
                       "note": str(item.get("why_relevant") or item.get("note") or "")})
    return result


def _http(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _memo_blocks(a: AssessmentResult) -> list[tuple[str, object]]:
    p = a.deal_snapshot
    blocks: list[tuple[str, object]] = []
    if p.get("report_note"):
        blocks.append(("note", p["report_note"]))
    if a.schema_version != 2:
        blocks.append(("note", "Archived assessment rebuilt with the new layout. Research has not been refreshed; a current recommendation and ranked questions require re-assessment."))
    decision_line = f"{a.verdict} · {_money(a.recommended_investment, a.investment_currency)} now" if a.verdict == "INVEST" else f"{a.verdict} · No cheque recommended"
    blocks += [("heading", "Decision Brief"), ("banner", decision_line),
               ("paragraph", a.decision_reason)]
    if a.schema_version == 2:
        blocks.append(("subheading", "Investment Case and Decision"))
        for key, label in [("investment_case", "Investment case"), ("supporting_evidence", "Evidence supporting the case"),
                           ("counterarguments", "Counterarguments and risks"), ("decision_logic", "Why this verdict; what could change it")]:
            blocks.append(("category", (label, a.decision["assessment_summary"][key])))
    elif a.rationale:
        blocks += [("subheading", "Historical Assessment Overview"), ("paragraph", "A concise overview was not recorded in the archived artifact; see the preserved historical analysis in the appendix.")]
    blocks.append(("paragraph", "Next action: " + a.next_action))
    summary = a.return_summary
    if summary.get("status") != "available":
        blocks.append(("category", ("Return analysis unavailable", str(summary.get("reason", "A complete net return model could not be supported.")))))
    if p:
        blocks.append(("paragraph", f"{p.get('product', '')} Customer: {p.get('customer', '')}"))
        blocks.append(("paragraph", " · ".join(str(p[k]) for k in ("stage", "instrument", "terms") if p.get(k))))
        blocks.append(("paragraph", "Market timing: " + p.get("market_timing", "Not recorded")))
        if p.get("as_of"):
            blocks.append(("note", "Evidence as of " + p["as_of"]))
    else:
        blocks.append(("paragraph", "Company and round snapshot was not recorded in this historical artifact."))
    if a.verdict == "INVEST":
        blocks.append(("paragraph", "Sizing: " + a.sizing_reason))
    blocks.append(("note", str(a.decision.get("judgment_basis", "Qualitative investment judgment"))))
    blocks.append(("heading", "Seven-Factor Assessment"))
    rows = []
    for cat in CATEGORY_ORDER:
        rows.append([cat, f"{a.effective_weights.get(cat, CATEGORY_WEIGHTS[cat]):.0%}", _score(a.category_scores.get(cat)),
                     a.category_confidence.get(cat, "unknown").title(), a.category_drivers.get(cat, "See category note below")])
    blocks.append(("table", (["Category", "Weight", "Score / 5", "Evidence strength", "Key driver"], rows, [19, 9, 15, 16, 39])))
    blocks.append(("note", "Evidence strength: High = key claims independently corroborated by authoritative evidence; Medium = some corroboration, with material gaps; Low = evidence is mostly reported, incomplete or conflicting; Unknown = evidence quality could not be assessed. Unknown is not a negative score."))
    blocks.append(("note", f"Weighted quality summary: {_score(a.weighted_score)} / 5 · Score coverage: {a.score_coverage:.0%}. Scores are descriptive; no automatic verdict thresholds."))
    if a.schema_version == 2:
        for cat in CATEGORY_ORDER:
            blocks.append(("category", (cat, a.category_rationales.get(cat, "No assessable evidence."))))
    blocks.append(("heading", "Decision-Critical Diligence"))
    if a.diligence_issues:
        for issue in sorted(a.diligence_issues, key=lambda r: float(r.get("priority", 99))):
            blocks.append(("issue", issue))
    else:
        blocks.append(("paragraph", "Decision-critical issues were not prioritized in this artifact. Re-assess before acting." if a.schema_version != 2 else "No unresolved decision-critical issues identified. See evidence limitations."))
    blocks.append(("heading", "Top Questions for the Founder"))
    primary = sorted([q for q in a.questions if q.get("audience") == "founder" and q.get("optional") is False], key=lambda q: float(q["priority"]))
    if len(primary) > 3:
        raise ValueError("Report cannot contain more than three primary founder questions")
    for index, question in enumerate(primary, 1):
        blocks.append(("question", (index, question)))
    if not primary:
        blocks.append(("paragraph", "Question priorities were not recorded. Historical questions are unranked in the appendix." if a.schema_version != 2 else "No additional founder questions needed now; do not fill a quota."))
    blocks.append(("note", "Ask only these primary questions now. A founder assurance is not verification; request the indicated evidence or a route to confirm it."))
    if summary.get("status") != "available":
        if a.schema_version == 1 and a.return_scenarios:
            blocks.append(("note", "Archived scenario multiples are retained in the JSON, but cannot be presented as verified net returns without structured fees, dilution and ownership assumptions."))
        return blocks
    blocks.append(("heading", "Deal Economics"))
    assumptions = a.return_assumptions
    allocation = _money(a.recommended_investment, a.investment_currency) if a.verdict == "INVEST" else "No cheque recommended"
    blocks.append(("paragraph", f"Hypothetical all-in outlay: {_money(a.hypothetical_investment, a.investment_currency)}; capital deployed: {_money(float(summary['deployed_capital']), a.investment_currency)}. This is a return illustration; recommended allocation: {allocation}."))
    blocks.append(("paragraph", f"Entry ownership {float(summary['entry_ownership']):.5%}; future dilution {float(summary['future_dilution']):.0%}; fee rate {float(assumptions['fee_rate']):.1%} ({assumptions['fee_treatment']}); carry {float(assumptions['carry_rate']):.0%} on gains above {str(assumptions['carry_basis']).replace('_', ' ')}. No follow-ons. FX: {assumptions.get('fx_rate', 1)} {assumptions['valuation_currency']} per {assumptions['currency']}."))
    blocks.append(("note", "Post-money entry valuation: " + _money(float(assumptions["entry_valuation"]), str(assumptions["valuation_currency"])) + ". Exit values are equity proceeds available to this holding after any assumed debt/preferences. " + str(assumptions.get("ownership_note", "Ownership is illustrative; verify conversion and the preference waterfall."))))
    rows = [[str(r.get("scenario", r["kind"].title())), f"{float(r['probability']):.0%}", _money(float(r['exit_value']), str(assumptions['valuation_currency'])),
             _money(float(r['net_proceeds']), a.investment_currency), f"{float(r['net_multiple']):.2f}x", f"{float(r['annualized_return']):.1%}", f"{float(r['ownership_at_exit']):.5%}"] for r in a.return_scenarios]
    blocks.append(("table", (["Outcome", "Prob.", "Equity exit", "Net proceeds", "Net MOIC", "Annualized", "Exit stake"], rows, [15, 7, 18, 17, 11, 13, 19])))
    for r in a.return_scenarios:
        blocks.append(("paragraph", f"{r.get('scenario', r['kind'].title())}: {r.get('rationale', '')} Holding period {r['years']:g} years; dilution {r['dilution_rate']:.0%}."))
    blocks.append(("paragraph", f"Total-loss probability {float(summary['total_loss_probability']):.0%}; loss versus cash paid {float(summary['capital_loss_probability']):.0%}. Subjective weighted net proceeds: {_money(float(summary['expected_net_proceeds']), a.investment_currency)} ({float(summary['expected_net_multiple']):.2f}x), with {float(summary['upside_share_of_expected_proceeds']):.0%} from the highest-payoff case. Probabilities are stress-test assumptions, not forecasts; weighted proceeds are not expected IRR."))
    sensitivity = summary["valuation_sensitivity"]
    exclusions = str(assumptions.get("exclusions", "Taxes and unspecified additional expenses are excluded."))
    blocks.append(("paragraph", f"At a 20% higher entry valuation, net MOIC falls to {float(sensitivity['expected_net_multiple']):.2f}x. Annualized returns assume one payment and one exit. {exclusions}"))
    if a.decision.get("return_hurdle") is not None:
        base = next(r for r in a.return_scenarios if r["kind"] == "base")
        blocks.append(("paragraph", f"Personal base-case annualized hurdle: {float(a.decision['return_hurdle']):.1%}; modeled base-case net annualized return: {float(base['annualized_return']):.1%}. This comparison is one part of the investment judgment."))
    return blocks


def _appendix_blocks(a: AssessmentResult) -> list[tuple[str, object]]:
    blocks: list[tuple[str, object]] = [("heading", "Optional Follow-ups — Ask Only If Needed")]
    for audience, label in [("founder", "Founder"), ("syndicate_lead", "Syndicate Lead"), ("counsel", "Counsel"), ("customer", "Customer / Reference")]:
        questions = sorted([q for q in a.questions if q.get("optional") and q.get("audience") == audience], key=lambda q: float(q["priority"]))
        if questions:
            blocks.append(("subheading", label))
            for i, q in enumerate(questions, 1):
                blocks.append(("question", (i, q)))
    if not any(q.get("optional") for q in a.questions):
        blocks.append(("paragraph", "No additional follow-ups recorded."))
    if a.founder_questions:
        blocks += [("subheading", "Historical Questions — Unranked"), ("note", "Retained for provenance; this is not a suggested outreach list.")]
        blocks += [("paragraph", q) for q in a.founder_questions]
    blocks.append(("heading", "Sources and Dates"))
    for item in _sources(a):
        blocks.append(("source", item))
    if not _sources(a):
        blocks.append(("paragraph", "No sources recorded."))
    blocks += [("heading", "Evidence Limitations"), ("paragraph", a.assessment_limitations or "Not recorded.")]
    blocks.append(("heading", "Actual Process Status"))
    if a.assessment_process:
        for key, value in a.assessment_process.items():
            blocks.append(("paragraph", f"{key.replace('_', ' ').title()}: {value}"))
    else:
        blocks.append(("paragraph", "Process completion was not recorded; no completion is inferred."))
    blocks += [("heading", "Documents Processed"), ("note", "Full source paths are preserved in the JSON artifact.")]
    for name in a.evidence_sources:
        blocks.append(("paragraph", " → ".join(Path(part).name for part in name.split("!"))))
    if a.extraction_warnings:
        blocks += [("heading", "Extraction Warnings")] + [("paragraph", x) for x in a.extraction_warnings]
    if a.decision_warnings:
        blocks += [("heading", "Decision Checks")] + [("paragraph", x) for x in a.decision_warnings]
    if a.schema_version != 2:
        blocks += [("heading", "Archived Analysis — Not a Current Recommendation"), ("note", f"Original verdict: {a.decision.get('original_verdict', 'Not recorded')}.")]
        for cat in CATEGORY_ORDER:
            blocks.append(("category", (cat, a.category_rationales.get(cat, "Not recorded."))))
        for heading, content in [("Original Investment Rationale", [a.rationale]), ("Original Risk Register", a.risk_flags),
                                 ("Original Unknowns", a.key_unknowns), ("Original Reconciliation", a.reconciliation_gaps),
                                 ("Original Milestones", a.milestones_to_monitor)]:
            if content:
                blocks += [("subheading", heading)] + [("paragraph", str(x)) for x in content]
    return blocks


def _html_text(value: object, a: AssessmentResult) -> str:
    text = escape(str(value))
    ids = {r["id"] for r in _sources(a)}
    return re.sub(r"\[([A-Za-z][A-Za-z0-9_-]*)\]", lambda m: f"<a class='citation' href='#src-{_slug(a.deal_id)}-{_slug(m[1])}'>[{m[1]}]</a>" if m[1] in ids else m[0], text)


def _block_html(block: tuple[str, object], a: AssessmentResult) -> str:
    kind, data = block
    t = lambda value: _html_text(value, a)
    if kind in {"heading", "subheading"}:
        tag = "h3" if kind == "heading" else "h4"
        return f"<{tag}>{t(data)}</{tag}>"
    if kind in {"paragraph", "note", "banner"}:
        return f"<p class='{kind}'>{t(data)}</p>"
    if kind == "category":
        label, text = data
        return f"<p class='category'><strong>{t(label)}.</strong> {t(text)}</p>"
    if kind == "table":
        headers, rows, widths = data
        cols = ''.join(f"<col style='width:{width}%'>" for width in widths)
        head = ''.join(f"<th>{escape(h)}</th>" for h in headers)
        body = ''.join('<tr>' + ''.join(f"<td>{t(cell)}</td>" for cell in row) + '</tr>' for row in rows)
        return f"<table><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    if kind == "issue":
        item = data
        refs = ' '.join(f"[{ref}]" for ref in item.get("source_ids", []))
        return (f"<div class='issue'><h4>{t(item['id'])} · {t(item['title'])} <span class='status'>{t(item['status'])}</span></h4>"
                f"<p>{t(item['finding'])} {t(refs)}</p><p><strong>Decision impact:</strong> {t(item['decision_impact'])}</p>"
                f"<p><strong>Evidence needed:</strong> {t(item.get('evidence_needed', 'Not required now'))}</p>"
                f"<p><strong>Reassessment trigger:</strong> {t(item.get('reconsideration_condition', 'Monitor if circumstances change'))}</p></div>")
    if kind == "question":
        index, q = data
        return f"<div class='question'><p><strong>{index}. {t(q['question'])}</strong></p><p class='note'>Evidence: {t(q['evidence_requested'])} · Linked issue {t(q['issue_id'])}</p></div>"
    if kind == "source":
        item = data
        title = f"<a href='{escape(item['url'], quote=True)}'>{escape(item['title'])}</a>" if _http(item['url']) else escape(item['title'])
        return f"<div class='source' id='src-{_slug(a.deal_id)}-{_slug(item['id'])}'><p><strong>{escape(item['id'])} · {title}</strong></p><p class='note'>{escape(item['type'])} · Source date {escape(item['date'])} · Accessed {escape(item['accessed'])}</p><p>{escape(item['note'])}</p></div>"
    raise ValueError(f"Unknown report block {kind}")


def _md_cell(value: object) -> str:
    return _md_text(value).replace('|', '\\|').replace('\\n', ' ')


def _md_text(value: object) -> str:
    """Render untrusted content as Markdown text, never as markup."""
    text = str(value).replace('\\', '\\\\')
    for char in '`*_{}[]<>#+!':
        text = text.replace(char, '\\' + char)
    return text.replace('\n', ' ')


def _block_md(block: tuple[str, object], a: AssessmentResult) -> str:
    kind, data = block
    if kind == "heading": return '#### ' + _md_text(data)
    if kind == "subheading": return '##### ' + _md_text(data)
    if kind in {"paragraph", "note"}: return _md_text(data)
    if kind == "banner": return '**' + _md_text(data) + '**'
    if kind == "category": return f"**{_md_text(data[0])}.** {_md_text(data[1])}"
    if kind == "table":
        headers, rows, _ = data
        return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |'] + ['| ' + ' | '.join(_md_cell(x) for x in row) + ' |' for row in rows])
    if kind == "issue":
        i = data
        refs = ' '.join('[' + _md_text(s) + ']' for s in i.get('source_ids', []))
        return f"**{_md_text(i['id'])} · {_md_text(i['title'])} ({_md_text(i['status'])})**\n\n{_md_text(i['finding'])} {refs}\n\nDecision impact: {_md_text(i['decision_impact'])}\n\nEvidence needed: {_md_text(i.get('evidence_needed', 'Not required now'))}\n\nReassessment trigger: {_md_text(i.get('reconsideration_condition', 'Monitor if circumstances change'))}"
    if kind == "question":
        index, q = data
        return f"{index}. **{_md_text(q['question'])}**\n\nEvidence: {_md_text(q['evidence_requested'])} · Linked issue {_md_text(q['issue_id'])}"
    if kind == "source":
        item = data
        title_text = _md_text(item['title'])
        safe_url = quote(item['url'], safe=":/?#[]@!$&'*,;=%")
        title = f"[{title_text}](<{safe_url}>)" if _http(item['url']) else title_text
        return f"<a id='src-{_slug(a.deal_id)}-{_slug(item['id'])}'></a>\n\n**{_md_text(item['id'])} · {title}**\n\n{_md_text(item['type'])} · Source date {_md_text(item['date'])} · Accessed {_md_text(item['accessed'])}\n\n{_md_text(item['note'])}"
    raise ValueError(f"Unknown report block {kind}")


def _overview(assessments: list[AssessmentResult]) -> list[list[str]]:
    return [[a.company_name, a.verdict, _cheque_now(a), a.decision_reason, a.next_action] for a in assessments]


def _render_markdown(assessments: list[AssessmentResult], run_id: str, logo_markdown_path: str | None) -> str:
    counts = ', '.join(f"{sum(a.verdict == v for a in assessments)} {v}" for v in ('INVEST', 'WAIT', 'PASS'))
    lines = ['# AngelCopilot Investment Decisions', f'Run: {run_id} · {len(assessments)} deals · {counts}', '## Executive Overview']
    if assessments:
        lines.append(_block_md(("table", (["Company", "Decision", "Cheque now", "Decisive reason", "Next action"], _overview(assessments), [])), assessments[0]))
    else: lines.append('No assessments completed in this run.')
    lines.append('## Individual Assessments')
    for i, a in enumerate(assessments, 1):
        lines.append(f'### {i}. {_md_text(a.company_name)} (`{_md_text(a.deal_id)}`)')
        lines.extend(_block_md(block, a) for block in _memo_blocks(a))
    lines.append('## Evidence Appendix')
    for a in assessments:
        lines.append('### ' + _md_text(a.company_name))
        lines.extend(_block_md(block, a) for block in _appendix_blocks(a))
    lines.append(DISCLAIMER)
    return '\n\n'.join(lines) + '\n'


CSS = """
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#203047;background:#eef1f5;margin:0;font-size:13px;line-height:1.5}
.page{background:white;max-width:1080px;margin:24px auto;padding:36px 46px;border-radius:10px;box-shadow:0 4px 24px #18243a0b}
.header{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #267b86;padding-bottom:16px;margin-bottom:20px}
.logo{width:58px;height:58px;object-fit:contain}h1{font-size:26px;line-height:1.2;margin:0 0 8px;color:#14243a}h2{font-size:22px;line-height:1.3;margin:0 0 20px}
h3{font-size:15px;color:#175e68;margin:24px 0 10px;break-after:avoid}h4{font-size:13px;margin:12px 0 5px;break-after:avoid}p{margin:7px 0;orphans:3;widows:3}
.banner{font-size:19px;font-weight:700;padding:13px 16px;border-left:4px solid #267b86;background:#eef6f5;break-inside:avoid}.note{font-size:11px;color:#59697b}.category{margin:10px 0}
table{border-collapse:collapse;table-layout:fixed;width:100%;margin:12px 0 16px;font-size:11px}th{text-align:left;padding:9px 7px;background:#203047;color:white;font-weight:600}td{padding:9px 7px;vertical-align:top;border-bottom:1px solid #dce3ea;overflow-wrap:anywhere}tr{break-inside:avoid}thead{display:table-header-group}
a{color:#175e68;text-decoration:underline;text-underline-offset:2px}.citation{font-size:10px}.issue{border-left:2px solid #d6e6e8;padding-left:14px;margin:15px 0;break-inside:avoid}.status{font-weight:400;font-size:10px;text-transform:uppercase;color:#637389}
.question,.source{break-inside:avoid;margin:10px 0 15px}.source p{margin:4px 0}.appendix{font-size:12px}nav a{display:block;margin:5px 0}.footer{margin:20px auto;max-width:1080px;padding:0 30px;font-size:11px;color:#59697b}
@page{size:A4;margin:17mm 14mm 18mm}@media print{body{background:white;font-size:10.5pt;line-height:1.4}.page{padding:0;margin:0;border-radius:0;box-shadow:none;max-width:none}.company,.appendix{break-before:page}h1{font-size:23pt}h2{font-size:19pt}h3{font-size:12pt}h4{font-size:10.5pt}.note{font-size:8.5pt}table{font-size:8pt}th,td{padding:6px 5px}.banner{font-size:14pt}.footer{break-inside:avoid}a{color:inherit}.header{margin-bottom:16px}}
"""


def _render_html(assessments: list[AssessmentResult], run_id: str) -> str:
    logo_path = Path(__file__).resolve().parents[2] / "logo_Dec_25_bigger.png"
    logo = ""
    if logo_path.exists():
        logo = "<img class='logo' alt='AngelCopilot' src='data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode() + "'>"
    parts = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><title>AngelCopilot Investment Decisions</title><style>" + CSS + "</style></head><body>",
             f"<section class='page'><div class='header'><div><h1>AngelCopilot Investment Decisions</h1><p class='note'>Run: {escape(run_id)} · {len(assessments)} deals</p></div>{logo}</div><h2>Executive Overview</h2>"]
    counts = ' · '.join(f"{sum(a.verdict == v for a in assessments)} {v}" for v in ('INVEST', 'WAIT', 'PASS'))
    parts.append(f"<p>{counts}</p>")
    if assessments:
        parts.append(_block_html(("table", (["Company", "Decision", "Cheque now", "Decisive reason", "Next action"], _overview(assessments), [19, 10, 12, 35, 24])), assessments[0]))
        parts.append("<nav><h3>Contents</h3>" + ''.join(f"<a href='#memo-{_slug(a.deal_id)}'>{escape(a.company_name)} · Decision memo</a>" for a in assessments) + "<a href='#evidence'>Evidence appendix</a></nav>")
    else:
        parts.append('<p>No assessments completed in this run.</p>')
    parts.append('</section>')
    for i, a in enumerate(assessments, 1):
        parts.append(f"<article class='page company' id='memo-{_slug(a.deal_id)}'><h2>{i}. {escape(a.company_name)}</h2>")
        parts.extend(_block_html(block, a) for block in _memo_blocks(a))
        parts.append('</article>')
    for i, a in enumerate(assessments):
        parts.append(f"<section class='page appendix' id='{'evidence' if i == 0 else 'evidence-' + _slug(a.deal_id)}'><h2>Evidence Appendix · {escape(a.company_name)}</h2>")
        parts.extend(_block_html(block, a) for block in _appendix_blocks(a))
        parts.append('</section>')
    parts.append(f"<footer class='footer'>{DISCLAIMER}</footer></body></html>")
    return ''.join(parts)


def _write_csv(path: Path, assessments: list[AssessmentResult]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['deal_id', 'company_name', 'weighted_score', 'score_coverage', 'verdict', 'recommended_investment', 'investment_currency', 'decision_reason', 'next_action'])
        writer.writeheader()
        for a in assessments:
            row = {k: getattr(a, k) for k in writer.fieldnames}
            if a.verdict != "INVEST":
                row["recommended_investment"] = ""
            writer.writerow(row)
