#!/usr/bin/env python3
"""Build clearly fictional v2 decision examples; never run live deal research."""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import fields
import json
from pathlib import Path

from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.models import AssessmentResult
from angelcopilot.profile import load_investor_profile
from angelcopilot.pipeline import _response_schema_template
from angelcopilot.reporting import write_batch_outputs
from angelcopilot.scoring import apply_scoring_rules


def demo_payloads() -> list[dict]:
    """Three investment outcomes at the same normal cheque; all facts are invented."""
    base = json.loads(_response_schema_template())
    base.update(deal_id="fictional_meridianops", company_name="Fictional MeridianOps", risk_flags=[], sectors=["B2B Software"], geographies=["Europe"])
    base["deal_snapshot"] = {
        "product": "Software that automates invoice exceptions and approvals.", "customer": "Finance teams at mid-sized logistics businesses.",
        "stage": "Seed", "instrument": "Post-money SAFE", "terms": "EUR 12m cap; modeled expenses 4%, carry 20%.",
        "market_timing": "Customers seek faster cash collection and fewer manual exceptions; established workflow vendors remain competitors.",
        "as_of": "2026-10-03 (fictional)", "report_note": "Entirely fictional demonstration. Companies, metrics, sources and probabilities are invented; this is not a live investment recommendation."}
    notes = {
        "Team": (4.1, "medium", "Relevant operators; delivery capacity remains concentrated", "The fictional founders have finance-software and logistics experience, with two customer references supporting implementation delivery. The planned hiring covers customer success and integrations. Founder-led selling and dependence on one technical lead prevent a higher score; this is acceptable residual execution risk for the illustrated seed stage. [D1]"),
        "Market": (4.0, "medium", "Clear buyer pain; workflow suites remain competitors", "Customer interviews identify cash-collection friction and manual exception handling as funded problems. The accessible wedge is finance teams in logistics, rather than all global accounts-payable spend. Existing suites can add similar features, so distribution and measurable time savings matter more than a broad market-size headline. [D1]"),
        "Product": (4.0, "medium", "Working integrations and measured customer time savings", "The invented reference packet includes a working integration and workflow logs supporting a reduction in exception-handling time. Product value is specific and deployment is manageable. The assessment does not assume that the same results hold across every ERP or customer size; broader implementation repeatability remains a limitation. [D1]"),
        "Traction": (3.8, "medium", "Recurring revenue supported; renewal history remains short", "An invented customer-level schedule supports EUR 600,000 of recurring revenue and reconciles contracted and live accounts. Collections and customer references support current adoption. Only one renewal cycle has occurred, so the assessment does not claim mature retention, durable expansion or a repeatable high-growth acquisition engine. [D1]"),
        "Unit Economics": (3.7, "medium", "Positive delivery contribution; acquisition scaling unproven", "The fictional cost schedule includes hosting, integration work and customer support and supports positive contribution margins. Sales are still founder-led, making a stable scaled CAC or LTV estimate premature. This factor is assessed against seed-stage delivery economics rather than fabricated mature SaaS ratios; the current cost burden is understood. [D1]"),
        "Defensibility": (3.4, "low", "Embedded workflows plausible; data advantage not proven", "ERP integrations and embedded approval processes could create switching friction. A proprietary-data advantage is not independently established, and adjacent vendors can replicate feature-level workflows. This is a plausible evolving moat rather than a demonstrated category monopoly; the lower confidence remains visible rather than being hidden in an aggregate score. [D1]"),
        "Terms": (4.0, "medium", "Transparent costs; valuation leaves illustrative upside", "The invented executed SAFE and cap table establish cap-based conversion, no senior preference leakage and a EUR 12m post-money entry basis for this fictional case. Reviewed manager terms establish the fee/carry basis. These are stipulated completed underwriting facts, not conditions left until after committing. The cheque needs no later participation. [D1]"),
    }
    for field, idx in [("category_scores", 0), ("category_confidence", 1), ("category_drivers", 2), ("category_rationales", 3)]:
        base[field] = {k: row[idx] for k, row in notes.items()}
    base["decision"] = {"verdict": "INVEST", "reason": "Reviewed evidence, suitable economics and investor fit support the normal minimum cheque.",
                        "assessment_summary": {
                            "investment_case": "MeridianOps sells software that removes a costly, recurring invoice-approval burden for mid-sized logistics finance teams. It has a clear buyer, integrates into existing finance workflows and can show customer time savings. The potential is a focused vertical workflow business with room to expand account value.",
                            "supporting_evidence": "The fictional diligence packet includes recurring customer revenue, measured time savings, a functioning product, positive delivery contribution and reviewed entry terms. The team has relevant operating experience. These facts support a normal minimum cheque in this illustration; the packet and all sources are invented for report testing.",
                            "counterarguments": "Retention evidence covers only one renewal cycle, so durable usage and expansion are not established. Sales remain founder-led, acquisition efficiency is unproven at scale, and ERP vendors or adjacent workflow suites could reproduce features. The evidence supports early product value but not a proven category moat or repeatable high-growth engine.",
                            "decision_logic": "INVEST is justified here because the included evidence is sufficient, the net return model is attractive under the stated assumptions, investor fit is compatible and the cheque stays at the normal minimum. The case weakens if churn rises, expansion fails to repeat or delivery costs increase. Monitor cohorts; do not rely on a later follow-on to rescue returns."},
                        "economics": "attractive", "evidence": "sufficient", "fit": "compatible", "suggested_amount": 2000,
                        "sizing_reason": "Use the EUR 2,000 typical ticket; short operating history does not justify increasing concentration.",
                        "next_action": "Commit the normal cheque on the reviewed terms; monitor retention through regular reporting.", "minimum_ticket": 2000}
    base["diligence_issues"] = [
        {"id": "I1", "priority": 1, "status": "risk", "evidence_state": "verified", "title": "Retention history is short",
         "finding": "The fictional packet supports one renewal cycle, not multi-year cohort durability.", "decision_impact": "Residual loss risk limits ticket size; it is not an unresolved prerequisite for this illustrative INVEST.",
         "evidence_needed": "Regular cohort reporting as the business ages.", "reconsideration_condition": "Reassess conviction if churn rises materially.", "source_ids": ["D1"]},
        {"id": "I2", "priority": 2, "status": "risk", "evidence_state": "reported", "title": "Feature replication remains possible",
         "finding": "Integration depth is promising; a durable data moat is not proven.", "decision_impact": "Keep modest conviction on upside exits and monitor competitive wins.",
         "evidence_needed": "Future win/loss reporting.", "reconsideration_condition": "Material competitive price compression would weaken the thesis.", "source_ids": ["D1"]},
    ]
    base["questions"] = [
        {"question": "Which retention metric will you include in your regular investor updates?", "priority": 1, "audience": "founder", "optional": False, "issue_id": "I1", "evidence_requested": "A sample cohort-report format; this is a monitoring question, not a condition of commitment."},
        {"question": "Can a reference customer describe the integration work required to switch vendors?", "priority": 2, "audience": "customer", "optional": True, "issue_id": "I2", "evidence_requested": "Customer explanation of workflow dependence; ask only if additional moat detail is needed."},
    ]
    base["return_assumptions"].update(currency="EUR", valuation_currency="EUR", entry_valuation=12000000, fx_rate=1,
        ownership_note="In this invented completed-diligence case, reviewed conversion and cap-table terms establish cap-based ownership and no senior preference leakage; exit values represent equity available to that holding.",
        exclusions="Taxes, unlisted later expenses and interim distributions excluded. All valuations are invented.")
    base["return_scenarios"] = [
        {"kind": "loss", "scenario": "Total loss", "exit_value": 0, "probability": .40, "rationale": "Financing or adoption fails; the entire cheque is lost."},
        {"kind": "bear", "scenario": "Partial recovery", "exit_value": 10000000, "probability": .20, "rationale": "Product adoption stalls around EUR 1m recurring revenue; a distressed sale at roughly 10x recurring revenue leaves EUR 10m distributable equity. This is a subjective partial-recovery stress case, not a forecast."},
        {"kind": "base", "scenario": "Base", "exit_value": 120000000, "probability": .30, "rationale": "Invented path: recurring revenue reaches EUR 15m over eight years (about 50% annual growth from EUR 0.6m), with sustainable delivery margins; an 8x recurring-revenue strategic sale yields EUR 120m distributable equity. Assumes no senior preference leakage."},
        {"kind": "upside", "scenario": "Upside", "exit_value": 500000000, "probability": .10, "rationale": "Invented path: strong international expansion reaches EUR 50m recurring revenue over eight years (about 74% annual growth), with scalable margins; a 10x recurring-revenue strategic sale yields EUR 500m distributable equity. This demanding outcome is given only 10% subjective weight."},
    ]
    base["citations"] = [{"id": "D1", "source": "Invented diligence packet", "source_type": "Fictional supplied document", "date": "2026-10-03", "note": "All operating, reference and term evidence in this example is invented."}]
    base["web_sweep_sources"] = []
    base["assessment_process"] = {"used_full_rubric": True, "performed_web_sweep": False, "reconciled_docs_with_web": False, "built_return_model": True,
                                  "notes": "Synthetic layout demonstration only; no public research or actual company verification performed."}
    base["assessment_limitations"] = "Entirely fictional. Only deterministic return calculation and report mechanics are exercised. It cannot be used to justify a live cheque."
    wait = deepcopy(base)
    wait.update(deal_id="fictional_fieldsense", company_name="Fictional FieldSense")
    wait["deal_snapshot"].update(product="Edge sensors for industrial machine maintenance.", customer="Plant reliability teams.", terms="EUR 20m post-money SAFE cap; fee/carry basis not available.", market_timing="Factory downtime creates measurable maintenance budgets, but sensor suppliers and machine OEMs already compete for those buyers.")
    wait["decision"].update(verdict="WAIT", reason="Pilot revenue, product reliability and delivered unit economics remain unverified.",
                            assessment_summary={
                                "investment_case":"FieldSense addresses expensive industrial downtime with edge sensors intended to identify machine-maintenance needs. Reliability teams have a relevant budget, and a coherent prototype plus customer trial interest provide a credible starting point. If the product proves dependable and economic in serial production, it could become a useful recurring maintenance tool.",
                                "supporting_evidence":"The fictional packet supports prototype existence and paid-pilot interest, and the founding team has relevant industrial experience. These are early signals, not evidence of repeatable production sales. The evidence is deliberately separated by source quality: the claimed revenue description conflicts with the supplied cancellable-trial schedule, and reliability remains company-reported.",
                                "counterarguments":"The reported pilots do not yet establish binding repeat orders. Independent field-reliability results are missing, while the unit-cost schedule excludes calibration, support, warranty and working capital. Incumbent sensor vendors and machine OEMs compete for the same maintenance budget. The headline valuation therefore cannot yet be supported by verified revenue or delivered margins.",
                                "decision_logic":"WAIT is appropriate because three linked facts could materially change both the commercial case and downside: signed recurring orders, customer-side performance evidence and fully loaded serial-unit economics. Until then the return model and Terms factor remain unavailable, so the normal cheque is zero. Reassess after those documents are independently checked; founder assurances alone do not clear the blockers."},
                            economics="unknown", evidence="incomplete", suggested_amount=0,
                            sizing_reason="No commitment while investment-critical gaps remain.", next_action="Request the three decision-changing items below; reconsider only after verification.")
    wait["diligence_issues"] = [
        {"id": "I1", "priority": 1, "status": "blocker", "evidence_state": "conflicting", "title": "Pilot versus binding revenue",
         "finding": "The invented memo labels pilots as recurring revenue; the supplied schedule labels them cancellable trials.", "decision_impact": "The current price cannot be underwritten from trial revenue.",
         "evidence_needed": "Customer-by-customer recurring revenue schedule and executed agreements.", "reconsideration_condition": "Verified paid recurring contracts support the stated operating plan.", "source_ids": ["D1"]},
        {"id": "I2", "priority": 2, "status": "blocker", "evidence_state": "reported", "title": "Unverified field reliability",
         "finding": "Detection performance is claimed by the company but not supported by customer test results.", "decision_impact": "Repeat production orders depend on dependable field performance.",
         "evidence_needed": "Independent test report or a route to confirm results with a pilot customer.", "reconsideration_condition": "Customer-side evidence supports the defined operating requirements.", "source_ids": ["D1"]},
        {"id": "I3", "priority": 3, "status": "blocker", "evidence_state": "unknown", "title": "Delivery economics incomplete",
         "finding": "Unit cost excludes calibration, warranty, support and working capital.", "decision_impact": "Revenue growth may require unattractive capital consumption.",
         "evidence_needed": "All-in unit-cost and production working-capital schedule.", "reconsideration_condition": "Early deliveries support contribution margin after full delivery costs.", "source_ids": ["D1"]},
    ]
    wait["questions"] = [
        {"question": "Can you share a customer-by-customer bridge from pilots to contracted recurring revenue?", "priority": 1, "audience": "founder", "optional": False, "issue_id": "I1", "evidence_requested": "Revenue schedule linked to redacted executed customer agreements."},
        {"question": "Which independent field-test report supports the reliability claim?", "priority": 2, "audience": "founder", "optional": False, "issue_id": "I2", "evidence_requested": "Test report or an introduction to the pilot customer to confirm performance."},
        {"question": "Can you share the fully loaded economics of one serial-production unit?", "priority": 3, "audience": "founder", "optional": False, "issue_id": "I3", "evidence_requested": "Unit-cost schedule including calibration, support, warranty and working capital."},
        {"question": "What fee and carry basis applies to the all-in commitment?", "priority": 4, "audience": "syndicate_lead", "optional": True, "issue_id": "I3", "evidence_requested": "Final cost schedule from the manager; clarify before any later INVEST recommendation."},
    ]
    wait_notes = {
        "Team": (4.2, "medium", "Industrial experience; serial delivery leadership incomplete", "The invented founders have industrial-sensing and machine-maintenance experience, with a credible prototype-delivery record. Manufacturing leadership remains a hiring need. Relevant domain knowledge supports the score, but it cannot verify the commercial or performance claims addressed by the separate blockers. [D1]"),
        "Market": (4.1, "medium", "Funded downtime problem; incumbent suppliers compete", "Industrial downtime is a clear and expensive customer problem. Reliability teams control relevant budgets, creating an accessible wedge. Existing sensor vendors and machine OEMs compete for that budget, so a large manufacturing market does not by itself establish adoption or distribution advantage. [D1]"),
        "Product": (3.4, "low", "Coherent prototype; independent reliability evidence absent", "A coherent sensor prototype exists in the invented packet, but company performance claims lack independent field evidence. The score recognizes specific product design while withholding stronger performance judgment. Reliability verification is an investment blocker rather than a post-cheque learning exercise. [D1]"),
        "Traction": (2.8, "low", "Pilot interest established; recurring orders not verified", "Customer trial interest is supported in the fictional schedule, but the memo's recurring-revenue description conflicts with cancellable-pilot terms. The score reflects the weaker confirmed commercial status. Executed recurring contracts must reconcile that difference before the current price can be underwritten. [D1]"),
        "Unit Economics": (None, "unknown", "Full delivery cost and working capital unknown", "The invented packet lacks calibration, support, warranty and production working-capital costs. A bill of materials cannot establish delivered margin, and the missing cost bridge prevents a defensible score. This is explicitly unscored rather than represented by an arbitrary low rating. [D1]"),
        "Defensibility": (3.1, "low", "Integration potential; proprietary advantage not demonstrated", "Machine integration could create workflow dependence and improve the product over time. The fictional evidence does not establish proprietary data rights, a patent advantage or superior customer access. Potential moat mechanisms therefore remain modest and low confidence rather than an assumed durable monopoly. [D1]"),
        "Terms": (None, "unknown", "Headline cap known; security economics incomplete", "A EUR 20m headline post-money cap is supplied, but conversion and investor-specific costs are incomplete. Without a reviewed instrument and manager cost schedule, the net economic exposure cannot be evaluated. This factor remains unscored and the return model unavailable; questions on manager economics are routed to the manager. [D1]"),
    }
    for field, idx in [("category_scores", 0), ("category_confidence", 1), ("category_drivers", 2), ("category_rationales", 3)]:
        wait[field] = {k: row[idx] for k, row in wait_notes.items()}
    wait["return_assumptions"], wait["return_scenarios"] = {}, []
    wait["assessment_process"]["built_return_model"] = False
    passed = deepcopy(base)
    passed.update(deal_id="fictional_sidecardata", company_name="Fictional SidecarData")
    passed["decision"].update(verdict="PASS", reason="The current entry price leaves an unattractive net return case.",
                              assessment_summary={
                                  "investment_case":"SidecarData provides a useful prospect-data enrichment workflow to small B2B sales teams. The fictional customer schedule supports early paid accounts, and known delivery costs allow a positive contribution margin. The product addresses an existing budget and the team has shipped data products, so the underlying business has credible strengths.",
                                  "supporting_evidence":"The invented packet contains paid recurring accounts, collected revenue, useful product performance and a cost schedule covering hosting, licensing and support. It supports a functioning early business with positive delivery economics. Acquisition remains founder-led, however, and customer expansion is modest; these facts support a viable company, not a category-leading growth outcome.",
                                  "counterarguments":"Prospecting data is crowded by established providers and CRM bundles, which constrain differentiation and pricing. Proprietary coverage and durable data rights are not established. More decisively, the EUR 60m post-money entry cap plus disclosed expenses and carry consumes most of the modeled base-case value; the return depends on a substantially larger exit over a long hold.",
                                  "decision_logic":"PASS follows from unattractive net economics at the current price, despite real product and customer strengths. Additional founder answers do not address the central issue. Reopen only if materially lower entry terms improve the net base case and downside balance. A price change can alter the decision; better storytelling or modest traction alone would not."},
                              economics="unattractive", suggested_amount=0,
                              sizing_reason="No allocation under the current terms.", next_action="Decline the current opportunity; revisit only after materially different pricing.")
    passed["deal_snapshot"].update(product="Data-enrichment software for sales teams.", customer="Small B2B sales teams.", terms="EUR 60m post-money SAFE cap; expenses 4%, carry 20%.", market_timing="Sales teams buy prospect data, but established datasets and bundled CRM tooling constrain pricing power.")
    passed["return_assumptions"]["entry_valuation"] = 60000000
    passed["diligence_issues"] = [{"id": "I1", "priority": 1, "status": "risk", "evidence_state": "verified", "title": "Entry price consumes upside",
                                  "finding": "The fictional entry cap requires a very large exit merely to create a modest base-case return.", "decision_impact": "The current net risk/reward does not justify the opportunity.",
                                  "evidence_needed": "Materially revised terms, not additional founder questionnaires.", "reconsideration_condition": "Reopen only if a lower price changes the modeled outcomes.", "source_ids": ["D1"]}]
    passed["questions"] = []
    pass_notes = {
        "Team": (3.7, "medium", "Capable operators; repeat scaling not established", "The fictional operators have shipped data products and recruited an initial technical team. Customer acquisition beyond founder-led sales remains limited. Team quality is serviceable and does not cause the PASS; the important distinction is that capable people do not automatically make an expensive security attractive. [D1]"),
        "Market": (3.5, "medium", "Existing spend; crowded data category limits pricing", "Prospecting data has established buyers and budget, with demand supported by the invented customer interviews. Mature datasets and bundled CRM tools restrict differentiation and price. The accessible market is credible, but the category is neither uniquely open nor supported by unlimited customer willingness to pay. [D1]"),
        "Product": (3.8, "medium", "Useful enrichment workflow; performance reasonably supported", "The invented packet supports a functioning enrichment workflow and useful accuracy against defined customer requirements. Integrations fit existing sales processes. Product utility is a genuine strength in this illustration; it does not establish the large future equity value required by the current entry price. [D1]"),
        "Traction": (3.4, "medium", "Early recurring accounts; expansion modest", "Recurring paid accounts and collections are supported in the fictional customer schedule. Growth and expansion are modest rather than category-leading. This supports a functioning early business, while leaving the larger outcomes used in the stress tests explicitly contingent on a demanding future operating path. [D1]"),
        "Unit Economics": (3.6, "medium", "Delivery margin positive; paid acquisition not scaled", "Known hosting, licensing and support costs permit a positive delivery contribution in the invented accounts. Paid acquisition has not reached stable scale. The available economics are plausible for stage, without fabricated LTV precision or a claim that every channel can be scaled profitably. [D1]"),
        "Defensibility": (2.8, "low", "Data overlap and bundling weaken durable advantage", "Customers can buy overlapping data from established providers, while workflow bundling makes switching between enrichment suppliers feasible. Proprietary coverage may help individual accounts, but the invented evidence does not establish durable data exclusivity or a compounding network effect. [D1]"),
        "Terms": (1.5, "medium", "High entry price leaves weak net base outcome", "The invented executed terms are clear enough to model: EUR 60m post-money entry plus disclosed costs and carry. Their transparency does not rescue their attractiveness. Against the stated operating paths, the net base payoff is modest over eight years and highly exposed to downside, so current pricing defeats the opportunity. [D1]"),
    }
    for field, idx in [("category_scores", 0), ("category_confidence", 1), ("category_drivers", 2), ("category_rationales", 3)]:
        passed[field] = {k: row[idx] for k, row in pass_notes.items()}
    return [base, wait, passed]


def build(output: Path, include_pdf: bool = True):
    stored_profile = Path(".angelcopilot/profile.md")
    if not stored_profile.exists():
        stored_profile = Path("examples/profile.local.template.md")
    profile = load_investor_profile(stored_profile)
    assessments = []
    raw = demo_payloads()
    allowed = {f.name for f in fields(AssessmentResult)}
    for payload in raw:
        data = validate_assessment_payload(payload)
        assessments.append(apply_scoring_rules(AssessmentResult(**{k: v for k, v in data.items() if k in allowed}), profile))
    paths = write_batch_outputs(assessments, output.parent, output.name, include_pdf=include_pdf)
    (output / "demo_payloads.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('examples/sample-output/revised-assessment'))
    parser.add_argument('--no-pdf', action='store_true')
    args = parser.parse_args()
    print(build(args.out, not args.no_pdf))
