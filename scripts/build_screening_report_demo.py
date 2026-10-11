#!/usr/bin/env python3
"""Build fictional version 4 action-recommendation reports without live research."""
from __future__ import annotations

import argparse
from dataclasses import fields
from pathlib import Path

from build_revised_report_demo import demo_payloads
from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.models import AssessmentResult, InvestorProfile
from angelcopilot.scoring import apply_scoring_rules
from angelcopilot.reporting import write_batch_outputs


def unified_action_demo_payloads() -> list[dict]:
    payloads = demo_payloads()
    choices = [('PURSUE', 'high'), ('WAIT', 'medium'), ('PASS', 'low')]
    for data, (recommendation, priority) in zip(payloads, choices):
        data['deal_snapshot']['company_summary'] = (
            'SidecarData provides prospect-data enrichment software for small B2B sales teams. Its workflow helps those teams enrich sales prospect records. The fictional customer schedule describes early paid accounts and known delivery costs. Established datasets and bundled CRM tools serve the same buyers; the packet does not specify the pricing model. [D1]' if data['deal_id'] == 'fictional_sidecardata' else
            'FieldSense develops edge sensors for plant reliability teams to support industrial machine maintenance and reduce downtime. The fictional packet describes a prototype and paid-pilot interest, but does not establish repeat production orders or independently verified detection performance. The ongoing revenue model is not specified. [D1]' if data['deal_id'] == 'fictional_fieldsense' else
            f"{data['company_name']} provides software that automates invoice exceptions and approvals for finance teams at mid-sized logistics businesses. It integrates with customer workflows to reduce manual exception handling and improve cash collection. The fictional packet describes a working integration and recurring customer revenue; renewal history is limited to one cycle. The precise subscription pricing is not specified. [D1]")
        data['schema_version'] = 4
        data['decision'].update(verdict=recommendation, priority=priority,
                                reason='Specific buyer pain and early use justify focused diligence at this price.' if recommendation == 'PURSUE' else
                                'Wait for a repeat customer order and confirmed delivery-cost schedule before prioritizing diligence.' if recommendation == 'WAIT' else
                                'The current price leaves insufficient net upside relative to the business risks.',
                                next_action='Arrange a founder meeting and request customer references.' if recommendation == 'PURSUE' else
                                'Reopen after a repeat order and a delivered unit-cost schedule are available.' if recommendation == 'WAIT' else
                                'Stop work at the current terms; reconsider only if price changes materially.',
                                suggested_amount=0,
                                sizing_reason='No cheque recommended for this action.')
        data['decision']['assessment_summary']['decision_logic'] = (
            'The recommendation reflects whether a concrete next step is worth taking at the current price. Focus on the highest-impact customer and delivery questions. PURSUE means diligence now; WAIT means reopen only after its stated trigger.' if recommendation != 'PASS' else
            'The disclosed price and costs leave too little plausible upside for this investor. Further verification of ordinary operating claims would not resolve the pricing objection. Decline the current opportunity and reconsider only if the economics materially change.')
        data['decision']['assessment_summary']['supporting_evidence'] = data['decision']['assessment_summary']['supporting_evidence'].replace('These facts support a normal minimum cheque in this illustration', 'These facts support focused follow-up in this illustration')
        data['category_rationales']['Defensibility'] = data['category_rationales']['Defensibility'].replace('lower confidence', 'lower evidence strength')
        data['economic_ranges'] = {} if recommendation == 'WAIT' else {
            'currency': 'EUR', 'entry_valuation_min': 12_000_000, 'entry_valuation_max': 14_000_000,
            'dilution_min': .3, 'dilution_max': .6, 'fee_rate_min': .04, 'fee_rate_max': .06,
            'carry_rate_min': .2, 'carry_rate_max': .2, 'fee_treatment': 'deducted',
            'carry_basis': 'deployed_capital', 'target_net_multiple': 10,
            'rationale': 'All figures are fictional. Entry and syndicate costs illustrate supplied terms; dilution is a stress range. Ten times net cash is an illustrative target, not a personal hurdle or forecast.'}
        data['return_assumptions'] = {}
        data['return_scenarios'] = []
        data['assessment_process']['built_return_model'] = False
        data['assessment_process']['notes'] = 'Fictional unified action and range-sensitivity demonstration only. No live research or verification.'
        for issue in data['diligence_issues']:
            issue['decision_impact'] = issue['decision_impact'].replace('Residual loss risk limits ticket size; it is not an unresolved prerequisite for this illustrative INVEST.', 'Short history limits certainty but is ordinary stage-appropriate venture risk; it does not block focused pursuit.')
            issue.update(resolution_type='document' if issue['status']=='blocker' else 'monitor',
                         resolution_horizon='During initial diligence' if issue['status']=='blocker' else 'Quarterly monitoring')
        for category, confidence in data['category_confidence'].items():
            if confidence == 'unknown': data['category_scores'][category] = None
    return payloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('examples/sample-output'))
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args()
    profile = InvestorProfile(currency='EUR')  # Screening works without a personal cheque range.
    allowed = {field.name for field in fields(AssessmentResult)}
    assessments = []
    for payload in unified_action_demo_payloads():
        normalized = validate_assessment_payload(payload)
        a = AssessmentResult(**{key: value for key, value in normalized.items() if key in allowed})
        assessments.append(apply_scoring_rules(a, profile))
    paths = write_batch_outputs(assessments, args.output_dir, 'unified-action-assessment', include_pdf=args.pdf)
    print(paths.markdown_path)
    print(paths.html_path)
    if paths.pdf_path: print(paths.pdf_path)


if __name__ == '__main__':
    main()
