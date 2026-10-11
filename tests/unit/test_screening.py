from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import csv
import json

import pytest

from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.contract import assessment_response_schema
from angelcopilot.economics import calculate_returns, calculate_screening_sensitivity
from angelcopilot.models import AssessmentResult, InvestorProfile
from angelcopilot.reporting import write_batch_outputs, load_assessments_from_json
from angelcopilot.scoring import apply_scoring_rules, assessment_sort_key
from test_scoring import modern, investor


def revised(index=0, *, mode='screening', recommendation='PURSUE', priority='high'):
    a = modern(index)
    issues = [{**i, 'resolution_type': 'document' if i['status'] == 'blocker' else 'monitor',
               'resolution_horizon': 'During initial diligence' if i['status'] == 'blocker' else 'Quarterly investor reporting'}
              for i in a.diligence_issues]
    return replace(a, schema_version=3, assessment_mode=mode, diligence_issues=issues,
                   screening={'recommendation': recommendation, 'priority': priority,
                              'reason': 'Clear buyer pain and promising early use justify focused follow-up at this price.',
                              'next_action': 'Arrange a founder meeting and request the delivered-cost schedule.'})


def ranges(**overrides):
    data = dict(currency='USD', entry_valuation_min=8_000_000, entry_valuation_max=12_000_000,
                dilution_min=.3, dilution_max=.6, fee_rate_min=.02, fee_rate_max=.06,
                carry_rate_min=.15, carry_rate_max=.2, fee_treatment='deducted',
                carry_basis='deployed_capital', target_net_multiple=10,
                rationale='Entry and cost terms are reported ranges; dilution and target multiple are illustrative stress assumptions.')
    data.update(overrides)
    return data


def test_screening_can_pursue_with_missing_scores_model_and_profile():
    a = revised(1)
    a.category_scores['Unit Economics'] = None
    a.category_confidence['Unit Economics'] = 'unknown'
    result = apply_scoring_rules(a, InvestorProfile())
    assert result.pursuit_recommendation == 'PURSUE'
    assert result.attention_flag is True
    assert result.weighted_score is not None and result.score_coverage < 1
    assert result.commitment_readiness == 'Diligence required'
    assert result.verdict == 'WAIT' and result.recommended_investment == 0
    assert result.next_action == a.screening['next_action']


def test_screening_does_not_authorize_cheque_even_with_complete_diligence():
    result = apply_scoring_rules(revised(), investor())
    assert result.pursuit_recommendation == 'PURSUE' and result.attention_flag
    assert result.verdict == 'WAIT' and result.recommended_investment == 0
    assert result.commitment_readiness == 'Cannot assess readiness'


def test_zero_amount_invest_is_downgraded_during_v4_validation():
    payload = modern().to_json_dict()
    payload['schema_version'] = 4
    payload['deal_snapshot']['company_summary'] = 'A fictional company serving a defined business workflow.'
    payload['economic_ranges'] = ranges()
    payload['decision'].update(verdict='INVEST', priority='high', suggested_amount=0)
    for issue in payload['diligence_issues']:
        issue.update(resolution_type='document', resolution_horizon='During initial diligence')

    validated = validate_assessment_payload(payload)

    assert validated['decision']['verdict'] == 'WAIT'
    assert validated['decision']['suggested_amount'] == 0
    assert 'positive proposed amount' in validated['decision']['next_action']
    assert any('proposed cheque amount was zero' in warning for warning in validated['assessment_quality_warnings'])


def test_zero_amount_v4_invest_cannot_fall_back_to_profile_ticket():
    a = modern()
    a.schema_version = 4
    a.decision.update(verdict='INVEST', priority='high', suggested_amount=0)
    a.economic_ranges = ranges()

    result = apply_scoring_rules(a, investor())

    assert result.verdict == 'WAIT'
    assert result.recommended_investment == 0
    assert result.hypothetical_investment == 0
    assert 'positive proposed amount' in result.decision['reason']


@pytest.mark.parametrize('recommendation,priority,attention', [
    ('PURSUE', 'high', True), ('PURSUE', 'medium', False), ('CONSIDER', 'medium', False), ('PASS', 'low', False)])
def test_attention_means_follow_up_priority(recommendation, priority, attention):
    result = apply_scoring_rules(revised(recommendation=recommendation, priority=priority), investor())
    assert result.attention_flag is attention
    assert result.pursuit_recommendation == recommendation


def test_hard_risk_suppresses_attention_without_inventing_company_weakness():
    a = revised(); a.risk_flags = ['hard: unresolved integrity allegation']
    result = apply_scoring_rules(a, investor())
    assert result.attention_flag is False
    assert result.category_scores == a.category_scores


@pytest.mark.parametrize('gate', ['fatal', 'economics', 'fit'])
def test_material_objections_override_positive_pursuit(gate):
    a = revised()
    if gate == 'fatal': a.diligence_issues[0]['status'] = 'fatal'
    elif gate == 'economics': a.decision['economics'] = 'unattractive'
    else: a.decision['fit'] = 'incompatible'
    result = apply_scoring_rules(a, investor())
    assert result.pursuit_recommendation == 'PASS' and result.pursuit_priority == 'low'
    assert not result.attention_flag and result.recommended_investment == 0
    assert result.commitment_readiness != 'Ready to commit'


def test_transition_attention_restores_strong_wait_threshold():
    a = modern(1)
    a.category_scores = {key: 4 for key in a.category_scores}
    result = apply_scoring_rules(a, investor(sectors_themes=['B2B Software'], geo_focus=['Europe']))
    assert result.verdict == 'WAIT' and result.attention_flag is True
    assert result.pursuit_recommendation == ''  # No invented archived judgment.
    a.risk_flags = ['hard: unresolved risk']
    assert not apply_scoring_rules(a, investor(sectors_themes=['B2B Software'], geo_focus=['Europe'])).attention_flag


def test_unknown_evidence_is_unscored_and_does_not_mutate_payload():
    a = revised(); payload = a.to_json_dict()
    payload['category_confidence']['Unit Economics'] = 'unknown'
    before = deepcopy(payload)
    normalized = validate_assessment_payload(payload)
    assert normalized['category_scores']['Unit Economics'] is None
    assert normalized['screening']['recommendation'] == 'PURSUE'
    assert payload == before


def test_nonstandard_evidence_strength_is_rejected():
    payload = revised().to_json_dict(); payload['category_confidence']['Team'] = 'medium-low'
    with pytest.raises(ValueError, match='Evidence strength'): validate_assessment_payload(payload)


def test_monitoring_risk_is_not_a_blocker():
    payload = revised().to_json_dict(); payload['diligence_issues'][0]['status'] = 'blocker'
    with pytest.raises(ValueError, match='monitoring'): validate_assessment_payload(payload)


def test_complete_diligence_can_support_commitment_with_residual_venture_risk():
    a = revised(mode='commitment')
    a.diligence_issues[0]['resolution_type'] = 'business_milestone'
    a.diligence_issues[0]['resolution_horizon'] = 'Over the next financing cycle'
    result = apply_scoring_rules(a, investor())
    assert result.verdict == 'INVEST' and result.commitment_readiness == 'Ready to commit'
    assert result.recommended_investment == 2000


def test_justified_sizing_can_depart_from_typical_within_profile_range():
    a = revised(mode='commitment')
    a.decision.update(suggested_amount=3500, minimum_ticket=3000,
                      sizing_reason='A EUR 3,500 cheque meets the minimum and remains within the saved range and budget.')
    result = apply_scoring_rules(a, investor())
    assert result.verdict == 'INVEST' and result.recommended_investment == 3500
    assert result.hypothetical_investment == 3500 and result.sizing_reason == a.decision['sizing_reason']


def test_subscription_minimum_can_raise_default_cheque_within_range():
    a = revised(mode='commitment'); a.decision.update(suggested_amount=0, minimum_ticket=3000)
    result = apply_scoring_rules(a, investor())
    assert result.verdict == 'INVEST' and result.recommended_investment == 3000
    assert 'subscription minimum' in result.sizing_reason


@pytest.mark.parametrize('amount', [1000, 6000])
def test_commitment_rejects_out_of_range_sizing(amount):
    a = revised(mode='commitment'); a.decision['suggested_amount'] = amount
    result = apply_scoring_rules(a, investor())
    assert result.verdict == 'WAIT' and result.recommended_investment == 0


def test_commitment_cannot_override_pass_screening():
    result = apply_scoring_rules(revised(mode='commitment', recommendation='PASS', priority='low'), investor())
    assert result.verdict != 'INVEST' and result.recommended_investment == 0


def test_missing_low_weight_score_does_not_itself_block_completed_diligence():
    a = revised(mode='commitment'); a.category_scores['Defensibility'] = None
    a.category_confidence['Defensibility'] = 'unknown'
    result = apply_scoring_rules(a, investor())
    assert result.weighted_score is not None and result.score_coverage == pytest.approx(.9)
    assert result.verdict == 'INVEST'  # Sufficient material evidence is separate from all seven numeric scores.


@pytest.mark.parametrize('treatment,basis', [('deducted', 'deployed_capital'), ('added', 'total_outlay')])
def test_required_exit_arithmetic_matches_net_return_engine(treatment, basis):
    input_ranges = ranges(fee_treatment=treatment, carry_basis=basis)
    result = calculate_screening_sensitivity(input_ranges)
    assert result['rows'][0]['required_exit_value'] < result['rows'][-1]['required_exit_value']
    for row in result['rows']:
        assumptions = dict(currency='USD', valuation_currency='USD', fx_rate=1,
                           entry_valuation=row['entry_valuation'], entry_valuation_basis='post_money',
                           exit_value_basis='distributable_equity', fee_rate=row['fee_rate'], fee_treatment=treatment,
                           carry_rate=row['carry_rate'], carry_basis=basis, dilution_rate=row['dilution'], follow_on=False, years=8)
        scenarios = [dict(kind=k, probability=.25, exit_value=0 if k=='loss' else row['required_exit_value']) for k in ('loss','bear','base','upside')]
        calculated, summary = calculate_returns(assumptions, scenarios, 1, 'USD')
        assert summary['status'] == 'available'
        assert next(r['net_multiple'] for r in calculated if r['kind']=='base') == pytest.approx(10)


def test_economic_ranges_work_without_profile_or_probabilities():
    a = revised(1); a.economic_ranges = ranges()
    result = apply_scoring_rules(a, InvestorProfile())
    assert result.economic_sensitivity['status'] == 'available'
    assert result.return_scenarios == [] and result.hypothetical_investment == 0
    assert result.pursuit_recommendation == 'PURSUE'


def test_range_supported_commitment_still_requires_material_evidence():
    a = revised(mode='commitment'); a.return_assumptions = {}; a.return_scenarios = []
    a.economic_ranges = ranges()
    assert apply_scoring_rules(a, investor()).verdict == 'INVEST'
    a.decision['evidence'] = 'incomplete'
    assert apply_scoring_rules(a, investor()).verdict == 'WAIT'


def test_hurdle_requires_full_base_case_even_when_ranges_available():
    a = revised(mode='commitment'); a.return_assumptions = {}; a.return_scenarios = []; a.economic_ranges = ranges()
    result = apply_scoring_rules(a, investor(return_hurdle=.2))
    assert result.verdict == 'WAIT' and 'base-case' in result.decision_reason


def test_priority_and_evidence_lead_ranking_not_highest_score():
    high = apply_scoring_rules(revised(), investor())
    other = revised(recommendation='CONSIDER', priority='medium'); other.category_scores = {key: 5 for key in other.category_scores}
    other = apply_scoring_rules(other, investor())
    assert sorted([other, high], key=assessment_sort_key)[0] == high


def test_reports_share_opening_labels_attention_and_roundtrip(tmp_path, monkeypatch):
    captured = []
    def fake_pdf(html_path, pdf_path):
        captured.append(html_path.read_text()); pdf_path.write_bytes(b'PDF test placeholder')
    monkeypatch.setattr('angelcopilot.reporting.render_pdf_with_playwright', fake_pdf)
    a = revised(1); a.economic_ranges = ranges()
    summary = 'FieldSense develops sensors for plant reliability teams to support industrial machine maintenance. The supplied documents describe a prototype and pilot interest; ongoing pricing is not specified. [D1]'
    a.deal_snapshot = {**a.deal_snapshot, 'company_summary': summary}
    paths = write_batch_outputs([a], tmp_path, 'screening', include_pdf=True)
    md, html = paths.markdown_path.read_text(), paths.html_path.read_text()
    assert captured == [html]
    for report in (md, html):
        assert report.index('Company Overview') < report.index(summary.removesuffix(' [D1]')) < report.index('Decision Brief') < report.index('Investment Case and Decision')
        assert report.count(summary.removesuffix(' [D1]')) == 1
    assert md.index('**Weighted score:') < md.index('**PURSUE')
    assert html.index("class='score-summary'") < html.index('PURSUE · Priority:')
    for label in ('PURSUE', 'Attention', 'Commitment readiness', 'Evidence strength', 'Required equity exit'):
        assert label in md and label in html
    assert 'Confidence' not in md and 'Conditional investment view' not in md
    assert a.screening['next_action'] in md and a.screening['next_action'] in html
    with paths.csv_path.open() as handle: row = next(csv.DictReader(handle))
    assert row['recommendation']=='PURSUE' and row['attention_flag']=='True'
    assert row['recommended_investment']==''
    loaded = load_assessments_from_json(paths.json_path)[0]
    assert loaded.deal_snapshot['company_summary'] == summary
    again = apply_scoring_rules(loaded, InvestorProfile(**loaded.investor_constraints))
    assert (again.pursuit_recommendation, again.attention_flag, again.next_action) == (loaded.pursuit_recommendation, loaded.attention_flag, loaded.next_action)
    assert json.loads(paths.json_path.read_text())['schema_version'] == 3


def test_current_schema_requires_unified_action_and_resolution_fields():
    schema = assessment_response_schema()
    assert schema['properties']['schema_version']['enum'] == [4]
    assert 'economic_ranges' in schema['required']
    assert 'assessment_mode' not in schema['required']
    assert 'screening' not in schema['required']
    assert 'company_summary' in schema['properties']['deal_snapshot']['required']
    assert {'resolution_type','resolution_horizon'} <= set(schema['properties']['diligence_issues']['items']['required'])
    assert {'PURSUE', 'WAIT'} <= set(schema['properties']['decision']['properties']['verdict']['enum'])


def test_saved_assessment_without_summary_uses_recorded_description(tmp_path):
    a = modern(1)
    assert 'company_summary' not in a.deal_snapshot
    paths = write_batch_outputs([a], tmp_path, 'legacy-summary')
    for report in (paths.markdown_path.read_text(), paths.html_path.read_text()):
        assert report.index(a.deal_snapshot['product']) < report.index('Decision Brief')
        assert report.index(a.deal_snapshot['customer']) < report.index('Decision Brief')


def test_company_summary_cannot_be_blank_when_supplied():
    from dataclasses import asdict
    payload = asdict(revised())
    payload['deal_snapshot']['company_summary'] = ' '
    with pytest.raises(ValueError, match='company_summary'):
        validate_assessment_payload(payload)


def test_personal_hurdle_pass_is_reconciled_with_pursuit_and_next_action():
    result = apply_scoring_rules(revised(mode='commitment'), investor(return_hurdle=.8))
    assert result.verdict == 'PASS'
    assert result.pursuit_recommendation == 'PASS' and result.pursuit_priority == 'low'
    assert 'hurdle' in result.pursuit_reason
    assert result.next_action.startswith('Decline') and not result.attention_flag
    assert result.decision['next_action'] == result.screening['next_action'] == result.next_action
    assert result.decision['proposed_next_action'] != result.next_action
    again = apply_scoring_rules(result, investor(return_hurdle=.8))
    assert (again.pursuit_recommendation, again.pursuit_reason, again.next_action) == (result.pursuit_recommendation, result.pursuit_reason, result.next_action)


@pytest.mark.parametrize('recommendation,priority', [('PURSUE','low'),('CONSIDER','high'),('PASS','medium')])
def test_priority_combinations_match_documented_meanings(recommendation, priority):
    with pytest.raises(ValueError, match='priority'):
        validate_assessment_payload(revised(recommendation=recommendation, priority=priority).to_json_dict())


def test_batch_retry_requires_current_v4_assessment_schema(tmp_path):
    from angelcopilot.pipeline import _run_with_retry
    calls = []
    class Runner:
        def run_assessment(self, prompt, cwd):
            calls.append(prompt)
            return {'schema_version': 3 if len(calls) == 1 else 4}
    payload, error = _run_with_retry(Runner(), 'assess this opportunity', tmp_path)
    assert payload == {'schema_version': 4} and error is None and len(calls) == 2
    assert 'received 3' in calls[1]


def test_batch_job_runs_unified_assessment_without_mode_selector(tmp_path):
    from angelcopilot.job import run_batch_job
    from tests.assessment_payloads import as_v4
    deal = tmp_path/'deals'/'harborops'; deal.mkdir(parents=True)
    (deal/'memo.md').write_text('Fictional completed diligence supplied for an explicit commitment review.')
    profile = tmp_path/'profile.md'
    profile.write_text('currency: EUR\nticket_min: 2000\nticket_typical: 2000\nticket_max: 5000\n')
    calls = []
    class Runner:
        def run_assessment(self, prompt, cwd):
            calls.append(prompt)
            return as_v4(modern().to_json_dict())
    result = run_batch_job(deals_root=deal.parent, profile_path=profile, out=tmp_path/'reports',
                           intake_filter='rules', top_level_containers=False, include_pdf=False,
                           runner=Runner(), logger=lambda _: None)
    assert len(calls) == 1
    assert 'schema_version 4' in calls[0]
    assert result.assessments[0].schema_version == 4
    assert result.assessments[0].verdict == 'WAIT'
    assert 'WAIT' in result.output_paths.markdown_path.read_text()


def test_cli_rejects_removed_assessment_mode_selector():
    from angelcopilot import cli
    with pytest.raises(SystemExit):
        cli.main(['batch','run','--deals-root','/tmp/deals','--assessment-mode','commitment','--no-pdf'])
