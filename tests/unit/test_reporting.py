from dataclasses import replace
import json
from pathlib import Path
import pytest
from angelcopilot.models import AssessmentResult
from angelcopilot.reporting import load_assessments_from_json,write_batch_outputs
from test_scoring import modern


def test_export_roundtrip_retains_decision_constraints_and_process(tmp_path):
    a=modern(1)
    a.assessment_process['performed_web_sweep']=False
    result=write_batch_outputs([a],tmp_path,'run')
    loaded=load_assessments_from_json(result.json_path)
    assert loaded[0].verdict=='WAIT' and loaded[0].recommended_investment==0
    assert loaded[0].assessment_process['performed_web_sweep'] is False
    second=write_batch_outputs(loaded,tmp_path,'rebuilt')
    assert json.loads(result.json_path.read_text())['assessments']==json.loads(second.json_path.read_text())['assessments']


def test_three_primary_questions_and_optional_audience_routing(tmp_path):
    result=write_batch_outputs([modern(1)],tmp_path,'run')
    text=result.markdown_path.read_text()
    main=text.split('## Evidence Appendix')[0]
    assert 'customer-by-customer bridge' in main and 'fully loaded economics' in main
    assert 'Investment Case and Decision' in main and 'FieldSense addresses expensive industrial downtime' in main
    assert 'Return analysis unavailable' in main
    assert '#### Deal Economics' not in main
    assert 'WAIT · No cheque recommended' in main
    assert 'EUR 0' not in main
    import csv
    with result.csv_path.open() as handle:
        row=next(csv.DictReader(handle))
    assert row['recommended_investment']==''
    assert 'What fee and carry basis' not in main
    assert 'What fee and carry basis' in text.split('## Evidence Appendix')[1]
    html=result.html_path.read_text()
    assert "<col style='width:19%'>" in html and 'Decision-Critical Diligence' in html
    assert 'src-fictional_fieldsense-D1' in html


def test_wait_with_available_return_model_still_has_no_recommended_amount(tmp_path):
    from angelcopilot.scoring import apply_scoring_rules
    from test_scoring import investor
    a=apply_scoring_rules(modern(),investor())
    a=replace(a,verdict='WAIT',recommended_investment=0,
              decision={**a.decision,'proposed_verdict':'WAIT','verdict':'WAIT','suggested_amount':0})
    result=write_batch_outputs([a],tmp_path,'run')
    text=result.markdown_path.read_text()
    main=text.split('## Evidence Appendix')[0]
    assert '| WAIT | No cheque |' in main
    assert 'recommended allocation: No cheque recommended' in main
    assert 'recommended allocation: EUR 0' not in main


def test_four_primary_questions_are_rejected(tmp_path):
    a=modern(1);a.questions.append(dict(a.questions[0],priority=5))
    with pytest.raises(ValueError,match='three'):write_batch_outputs([a],tmp_path,'run')


def test_requested_pdf_failure_is_not_silently_success(tmp_path,monkeypatch):
    def fail(*args):raise RuntimeError('Browser unavailable')
    monkeypatch.setattr('angelcopilot.reporting.render_pdf_with_playwright',fail)
    with pytest.raises(RuntimeError,match='Browser unavailable'):write_batch_outputs([modern()],tmp_path,'run',include_pdf=True)


def test_legacy_questions_stay_unranked_and_long_urls_use_named_links(tmp_path):
    a=AssessmentResult('d1','Archive',{'Team':4},[],[],[],'Old text',verdict='INVEST',founder_questions=['Old question'],
                       citations=[{'id':'W1','source':'Named source','url':'https://example.com/'+('long/'*80),'date':'2026-01-01'}])
    result=write_batch_outputs([a],tmp_path,'run')
    md=result.markdown_path.read_text();html=result.html_path.read_text()
    assert 'Old question' not in md.split('## Evidence Appendix')[0]
    assert 'Historical Questions — Unranked' in md
    assert "href='https://example.com/" in html
    assert '>Named source</a>' in html
    assert load_assessments_from_json(result.json_path)[0].recommended_investment==0


def test_sources_escape_untrusted_html_and_unsafe_urls(tmp_path):
    a=modern();a.citations.append({'id':'D2','source':'<script>bad()</script>','url':'javascript:alert(1)'})
    result=write_batch_outputs([a],tmp_path,'run')
    text=result.html_path.read_text()
    assert '<script>bad()' not in text and "href='javascript:" not in text


def test_markdown_escapes_untrusted_content_and_closes_link_delimiters(tmp_path):
    a=modern();a.company_name='Company [x](javascript:alert(1))'
    a.category_rationales['Team']='**bold** <script>alert(1)</script>'
    a.citations.append({'id':'D2','source':'Source','url':'https://example.com/path_(x)'})
    result=write_batch_outputs([a],tmp_path,'run')
    md=result.markdown_path.read_text()
    assert '<script>' not in md
    assert r'\[x\]' in md and r'\*\*bold\*\*' in md
    assert 'https://example.com/path_%28x%29' in md


def test_optional_collections_are_validated(tmp_path):
    a=modern();a.risk_flags=None
    with pytest.raises(ValueError,match='risk_flags'):write_batch_outputs([a],tmp_path,'run')


def test_pipe_in_table_cell_is_escaped_exactly_once():
    from angelcopilot.reporting import _md_cell
    assert _md_cell('A | B') == r'A \| B'


def test_risk_flag_items_must_be_text(tmp_path):
    a=modern();a.risk_flags=[{}]
    with pytest.raises(ValueError,match='risk_flags'):write_batch_outputs([a],tmp_path,'run')
