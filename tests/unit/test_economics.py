from copy import deepcopy
import json
import pytest
from angelcopilot.economics import calculate_returns, validate_scenarios
from angelcopilot.pipeline import _response_schema_template


def sample():
    p=json.loads(_response_schema_template())
    return p['return_assumptions'],p['return_scenarios']


def test_net_cash_math_uses_exact_inputs_and_distinguishes_losses():
    assumptions,scenarios=sample()
    rows,summary=calculate_returns(assumptions,scenarios,2000,'EUR')
    # 4% deducted: 1920 deployed; 45% dilution: 0.0000528 stake.
    # Base gross: 200m * stake = 10560. Carry on profit = (10560-1920)*20%.
    base=next(r for r in rows if r['kind']=='base')
    assert summary['deployed_capital']==1920
    assert summary['entry_ownership']==pytest.approx(.000096)
    assert base['ownership_at_exit']==pytest.approx(.0000528)
    assert base['net_proceeds']==pytest.approx(8832)
    assert base['annualized_return']==pytest.approx((8832/2000)**(1/8)-1)
    assert summary['total_loss_probability']==.4
    assert summary['capital_loss_probability']==pytest.approx(.6)
    assert summary['expected_net_proceeds']==pytest.approx(sum(r['net_proceeds']*r['probability'] for r in rows))


def test_fee_added_keeps_recommended_outlay_all_in():
    a,s=sample();a.update(fee_rate=.05,fee_treatment='added')
    _,summary=calculate_returns(a,s,2100,'EUR')
    assert summary['total_outlay']==2100 and summary['deployed_capital']==2000


def test_foreign_currency_never_silently_assumes_parity():
    a,s=sample();a['valuation_currency']='USD';a.pop('fx_rate')
    _,summary=calculate_returns(a,s,2000,'EUR')
    assert summary['status']=='unavailable'
    a['fx_rate']=1.1
    rows,summary=calculate_returns(a,s,2000,'EUR')
    assert summary['status']=='available'
    assert summary['entry_ownership']==pytest.approx(1920*1.1/20000000)


@pytest.mark.parametrize('bad', [float('nan'),float('inf'),-1,True])
def test_invalid_numbers_do_not_create_net_returns(bad):
    a,s=sample();a['dilution_rate']=bad
    _,summary=calculate_returns(a,s,2000,'EUR')
    assert summary['status']=='unavailable'


def test_probability_sum_and_zero_loss_case_are_required():
    a,s=sample();s[0]['probability']=.1
    with pytest.raises(ValueError,match='sum'):validate_scenarios(s,modern=True)
    a,s=sample();s[0]['exit_value']=100
    with pytest.raises(ValueError,match='total-loss'):validate_scenarios(s,modern=True)


def test_different_outcome_horizons_and_dilution_are_computed():
    a,s=sample();s[2].update(years=12,dilution_rate=.6)
    rows,_=calculate_returns(a,s,2000,'EUR')
    assert rows[2]['ownership_at_exit']==pytest.approx(.000096*.4)
    assert rows[2]['annualized_return']==pytest.approx(rows[2]['net_multiple']**(1/12)-1)
