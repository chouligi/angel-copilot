from __future__ import annotations
from copy import deepcopy
from dataclasses import fields
import importlib.util
from pathlib import Path
import pytest
from angelcopilot.models import AssessmentResult, InvestorProfile
from angelcopilot.scoring import apply_scoring_rules
from angelcopilot.assistant import validate_assessment_payload

_spec = importlib.util.spec_from_file_location('report_demo', Path(__file__).parents[2] / 'scripts/build_revised_report_demo.py')
_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_demo)


def modern(index=0):
    data = validate_assessment_payload(deepcopy(_demo.demo_payloads()[index]))
    allowed = {f.name for f in fields(AssessmentResult)}
    return AssessmentResult(**{k:v for k,v in data.items() if k in allowed})


def investor(**overrides):
    data = dict(currency='EUR', ticket_min=2000, ticket_typical=2000, ticket_max=5000)
    data.update(overrides)
    return InvestorProfile(**data)


def test_decision_is_not_a_score_threshold():
    invest = modern()
    invest.category_scores = {k: 3.7 for k in invest.category_scores}
    result = apply_scoring_rules(invest, investor())
    assert result.verdict == 'INVEST' and result.recommended_investment == 2000
    assert result.weighted_score == 3.7
    high_score_wait = modern(1)
    high_score_wait.category_scores = {k: 4.5 for k in high_score_wait.category_scores}
    wait = apply_scoring_rules(high_score_wait, investor())
    assert wait.weighted_score == 4.5
    assert wait.verdict == 'WAIT' and wait.recommended_investment == 0


def test_fatal_issue_overrules_high_score():
    a = modern()
    a.category_scores = {k:5 for k in a.category_scores}
    a.diligence_issues[0]['status'] = 'fatal'
    r = apply_scoring_rules(a, investor())
    assert r.verdict == 'PASS' and r.recommended_investment == 0


@pytest.mark.parametrize('field,value', [('evidence','incomplete'),('economics','unknown'),('fit','unknown')])
def test_invest_requires_explicit_gates(field,value):
    a=modern();a.decision[field]=value
    r=apply_scoring_rules(a,investor())
    assert r.verdict=='WAIT' and r.recommended_investment==0


@pytest.mark.parametrize('amount', [500, 1999, 5001])
def test_payload_cheque_amount_does_not_override_profile(amount):
    a=modern();a.decision['suggested_amount']=amount
    r=apply_scoring_rules(a,investor())
    assert r.verdict=='INVEST' and r.recommended_investment==2000


def test_cheque_size_comes_from_profile_not_deal_payload():
    a=modern()
    a.decision['suggested_amount']=3500
    a.decision['model_amount']=4500
    r=apply_scoring_rules(a,investor())
    assert r.verdict=='INVEST'
    assert r.recommended_investment==2000
    assert r.hypothetical_investment==2000
    assert r.investment_basis=='profile_ticket_typical'


def test_ticket_limits_must_come_from_profile():
    result=apply_scoring_rules(modern(),InvestorProfile(currency='EUR'))
    assert result.verdict=='WAIT' and result.hypothetical_investment==0
    assert result.return_summary['status']=='unavailable'
    assert 'complete cheque range' in result.return_summary['reason']


def test_budget_and_hurdle_are_explicit_constraints():
    a=modern()
    assert apply_scoring_rules(a,investor(remaining_angel_budget=1000)).verdict=='WAIT'
    assert apply_scoring_rules(a,investor(return_hurdle=.8)).verdict=='PASS'
    assert apply_scoring_rules(a,investor()).verdict=='INVEST'


def test_missing_score_is_not_zero_or_comparable_aggregate():
    a=modern();a.category_scores['Team']=None
    r=apply_scoring_rules(a,investor())
    assert r.weighted_score is None and r.score_coverage==pytest.approx(.75)
    assert r.verdict=='WAIT'


def test_weight_overrides_change_summary_not_verdict():
    a=modern();a.category_scores['Team']=1
    base=apply_scoring_rules(a,investor())
    custom=apply_scoring_rules(a,investor(evaluation_weight_overrides={'Team':.5}))
    assert custom.weighted_score<base.weighted_score
    assert sum(custom.effective_weights.values())==pytest.approx(1)
    assert custom.verdict==base.verdict=='INVEST'


def test_legacy_score_and_hard_flags_do_not_authorize_investment():
    a=modern();a.schema_version=1;a.decision={};a.verdict='INVEST';a.risk_flags=['hard:regulatory_blocker']
    r=apply_scoring_rules(a,investor())
    assert r.verdict=='WAIT' and r.recommended_investment==0 and not r.attention_flag
    assert r.decision['original_verdict']=='INVEST'


def test_process_flags_are_preserved_and_do_not_become_all_yes():
    a=modern();r=apply_scoring_rules(a,investor())
    assert r.assessment_process['performed_web_sweep'] is False


def test_assessment_summary_is_structured_and_sufficiently_substantive():
    payload=deepcopy(_demo.demo_payloads()[0])
    payload['decision'].pop('assessment_summary')
    with pytest.raises(ValueError,match='assessment_summary'):
        validate_assessment_payload(payload)
    payload=deepcopy(_demo.demo_payloads()[0]);payload['decision']['assessment_summary']['decision_logic']='brief answer only'
    with pytest.raises(ValueError,match='25–80 words'):
        validate_assessment_payload(payload)


def test_no_return_case_means_no_invest():
    a=modern();a.return_assumptions={};a.return_scenarios=[]
    r=apply_scoring_rules(a,investor())
    assert r.verdict=='WAIT' and r.return_summary['status']=='unavailable'


def test_gated_decision_regeneration_is_idempotent_and_preserves_proposal():
    a=modern();a.diligence_issues[0]['status']='blocker'
    first=apply_scoring_rules(a,investor())
    second=apply_scoring_rules(first,investor())
    assert first.verdict==second.verdict=='WAIT'
    assert first.next_action==second.next_action
    assert first.decision['proposed_verdict']=='INVEST'
    assert first.decision['proposed_amount']==2000
    assert second.decision['suggested_amount']==0
