"""Render a format-only retrospective of the 2026-07-22 assessment."""
from copy import deepcopy
import json
from pathlib import Path
import re

from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.models import AssessmentResult
from angelcopilot.profile import load_investor_profile
from angelcopilot.reporting import write_batch_outputs
from angelcopilot.scoring import apply_scoring_rules

SOURCE = Path("outputs/run_2026_July_22/angelcopilot_batch_assessments.json")
OUT = Path("examples/sample-output/stronghold-retrospective")
USD_PER_EUR = 1.1408


def _eur_text(text: str) -> str:
    """Convert source USD amounts to retrospective-date EUR equivalents."""
    pattern = re.compile(r"\$(?P<amount>[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?P<scale>million|billion|m|bn|b)?\b", re.I)
    def convert(match):
        amount = float(match.group("amount").replace(",", ""))
        scale = (match.group("scale") or "").lower()
        multiplier = 1_000_000_000 if scale in {"billion", "bn", "b"} else (1_000_000 if scale in {"million", "m"} else 1)
        converted = amount * multiplier / USD_PER_EUR
        if multiplier == 1:
            return f"EUR {converted:,.0f}"
        unit = "billion" if multiplier == 1_000_000_000 else "million"
        return f"EUR {converted / multiplier:,.1f} {unit}"
    return pattern.sub(convert, text)


def _convert_usd_to_eur(value):
    if isinstance(value, str):
        return _eur_text(value)
    if isinstance(value, list):
        return [_convert_usd_to_eur(item) for item in value]
    if isinstance(value, dict):
        return {key: _convert_usd_to_eur(item) for key, item in value.items()}
    return value


def build(include_pdf: bool = True):
    old = json.loads(SOURCE.read_text(encoding="utf-8"))["assessments"][0]
    scores = old["category_scores"]
    rationale = {
        "Team": "The founders combine electronic-warfare and technical credentials with defence-program experience. Several specific résumé claims and the ability to build the required engineering and production team were not independently verified.",
        "Market": "Counter-UAS demand is supported by defence priorities, but procurement is fragmented, competitive and dependent on programme timing. The company’s broad market estimate is not used as proof of obtainable sales.",
        "Product": "AURA and LUMINA address defined sensing needs and have reported field exposure. Independent detection, false-alarm, environmental and reliability results were not supplied.",
        "Traction": "RoverTech publicly confirmed a memorandum and joint development. The supplied approximately $47m combines contracts with nonbinding interest and pipeline; binding orders, invoices and collections were not reconciled.",
        "Unit Economics": "The supplied hardware bill of materials suggests a possible margin, but excludes material delivery, service, warranty, logistics and working-capital costs. Scalable delivered economics remain unproven.",
        "Defensibility": "Field data, integrations and qualification history could strengthen the position as deployments grow. A durable technical lead, company-owned IP and freedom to operate were not established in the reviewed evidence.",
        "Terms": "The supplied materials state a $20m post-money SAFE cap, approximately 4% expenses and 20% carry. Conversion, rights and final investor-level costs require document review; no follow-on investment is assumed in this review.",
    }
    drivers = {
        "Team": "Relevant defence and electronic-warfare experience; key résumé claims and production hiring need verification",
        "Market": "Strong demand tailwinds; fragmented procurement and intense competition",
        "Product": "Defined sensing products with field exposure; independent reliability results are missing",
        "Traction": "Public partnership confirmed; headline commercial interest is not reconciled to binding orders",
        "Unit Economics": "Promising preliminary hardware margin; delivered cost and working capital are unknown",
        "Defensibility": "Integration and field data may help; company-owned IP and durable advantage are unproven",
        "Terms": "Headline cap and SPV costs disclosed; conversion and investor rights need review",
    }
    raw = {
        "schema_version": 2, "deal_id": "Stronghold-retrospective-2026-07-22",
        "company_name": old["company_name"], "category_scores": scores,
        "category_rationales": rationale,
        "category_drivers": drivers,
        "category_confidence": {"Team":"medium", "Market":"medium", "Product":"medium", "Traction":"low", "Unit Economics":"low", "Defensibility":"low", "Terms":"medium"},
        "deal_snapshot": {"report_note": "RETROSPECTIVE FORMAT REVIEW — historical decision and evidence as of 2026-07-22; research was not refreshed. Evidence-strength ratings are retrospective editorial judgments because the original assessment did not record them. USD-denominated source amounts are shown as EUR equivalents at the ECB rate of EUR 1 = USD 1.1408 for 2026-07-22 (rounded); original documents use USD. The three questions below are an editorial prioritization of that record, not a current recommendation.",
            "as_of": "2026-07-22", "product": "Counter-UAS and electronic-warfare sensing systems, as described in the historical memo.",
            "customer": "Defence and government programmes; customer mix and binding order status require verification.",
            "stage": "Seed", "instrument": "SPV exposure through a Delaware series partnership into a French SAS, per supplied materials.",
            "terms": "Historical materials state a $20m post-money SAFE cap, approximately 4% expenses and 20% carry. Conversion and investor-level terms require document review.",
            "market_timing": "Defence procurement demand is relevant; programme timing, customer commitments and production conversion remain uncertain."},
        "decision": {"verdict": "WAIT", "reason": "Binding commercial commitments, independent performance evidence and fully loaded production economics are unresolved.",
            "assessment_summary": {
                "investment_case": "Stronghold targets a consequential defence need: affordable counter-UAS sensing that can operate in contested environments. The founders bring relevant electronic-warfare and technical experience, and AURA and LUMINA are specific products rather than a broad AI claim. If the systems prove reliable and procurements convert into repeat production, the company could earn a valuable position in a growing market.",
                "supporting_evidence": "The historical review found public evidence for founder credentials, product existence, AURA field exposure and RoverTech joint development. RoverTech’s announcement corroborates a memorandum and programme collaboration, which is meaningful external validation. The source memo reports approximately EUR 41.2 million of commercial interest after conversion, but the review found that figure combines contracts with LOIs, quotations, demonstrations and pipeline; it is not verified backlog. [D1] [W1] [W2]",
                "counterarguments": "The public partnership does not substantiate the memo’s five-year purchase characterization or minimum commitments. Independent results for detection, false alarms, environmental performance and reliability were absent. Preliminary hardware margin omits integration, service, warranty, logistics and working capital, leaving production funding unclear. At an approximately EUR 17.5 million post-money SAFE cap, the entry price assumes substantial commercial conversion. The historic return model lacks a distinct total-loss case. [D1] [D2] [FX1]",
                "decision_logic": "The historical WAIT reflects missing proof, not weak market relevance or founder capability. Recommend zero until enforceable commitments, independent product results and fully loaded production economics are verified. These establish demand, procurement readiness and a financeable margin path. Then reassess price, SPV costs and net returns using final legal terms and a full-loss scenario. This reflects 2026-07-22 evidence and is not a current recommendation."},
            "economics": "unknown", "evidence": "incomplete", "fit": "unknown", "suggested_amount": 0,
            "sizing_reason": "No commitment pending verification of the three decision-critical issues.",
            "next_action": "Verify binding programme commitments, independent performance results and fully loaded production economics; then reassess.",
            "minimum_ticket": 0},
        "diligence_issues": [
            {"id":"I1","priority":1,"status":"blocker","evidence_state":"conflicting","title":"Commercial interest is not verified backlog","finding":"The historical memo combines contracts, LOIs, an NDA, demonstrations, quotations and pipeline into an approximately $47m headline figure.","decision_impact":"The order value and production forecast cannot be underwritten as committed revenue.","evidence_needed":"Counterparty-level schedule linking executed agreements to enforceable quantities, price, cancellation rights, deliveries, invoices and cash collected.","reconsideration_condition":"Independent review confirms material binding minimum purchases and credible delivery timing.","source_ids":["D1","D2"]},
            {"id":"I2","priority":2,"status":"blocker","evidence_state":"unknown","title":"Independent product performance is unavailable","finding":"The historical materials make performance claims but do not provide independent detection, false-alarm, environmental and reliability results.","decision_impact":"Field performance is central to procurement, repeat deployments and product liability exposure.","evidence_needed":"Independent test results against agreed operating conditions and a customer reference.","reconsideration_condition":"A qualified third party or customer confirms performance against stated requirements.","source_ids":["D1","W1"]},
            {"id":"I3","priority":3,"status":"blocker","evidence_state":"unknown","title":"Production economics and cash needs are incomplete","finding":"The assessment identifies certification, warranty, working capital and industrialisation as material but unresolved costs.","decision_impact":"The company may require substantially more capital or deliver below the forecast margin.","evidence_needed":"Fully loaded unit-cost, production-capacity, certification, warranty and working-capital plan tied to the forecast.","reconsideration_condition":"A bottom-up plan supports positive delivered margin and a financeable path to serial production.","source_ids":["D1","D2"]}],
        "questions": [
            {"question":"Please reconcile the approximately $47m headline line by line, identifying binding minimum quantities, cancellation rights, delivery dates, invoices and cash collected.","priority":1,"audience":"founder","optional":False,"issue_id":"I1","evidence_requested":"Counterparty schedule linked to redacted executed agreements, invoices and receipts."},
            {"question":"Which independent test report supports the detection, false-alarm and reliability claims, and may we speak with the test customer?","priority":2,"audience":"founder","optional":False,"issue_id":"I2","evidence_requested":"Test report with conditions, results and customer permission for reference."},
            {"question":"Can you share the fully loaded unit economics and working-capital plan for serial production?","priority":3,"audience":"founder","optional":False,"issue_id":"I3","evidence_requested":"Costed production plan including certification, warranty, integration and working capital."}],
        "return_assumptions": {}, "return_scenarios": [],
        "citations": old.get("citations", []), "web_sweep_sources": old.get("web_sweep_sources", []),
        "assessment_process": old.get("assessment_process", {}),
        "assessment_limitations": "Retrospective layout example only. Facts and research status are preserved as of 2026-07-22; no refreshed research was performed. The historical return cases were not converted because they do not supply a distinct total-loss scenario.",
        "rationale": old.get("rationale", ""), "risk_flags": old.get("risk_flags", []),
        "sectors": old.get("sectors", []), "geographies": old.get("geographies", [])}
    raw["citations"].append({"id":"FX1","source":"Official Journal of the European Union: Euro exchange rates, 22 July 2026",
        "source_type":"Official exchange-rate reference","date":"2026-07-22",
        "url":"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:C_202603604",
        "note":"The ECB reference rate was EUR 1 = USD 1.1408; USD-denominated historical amounts in this retrospective are converted to EUR and rounded."})
    raw = _convert_usd_to_eur(raw)
    normalized = validate_assessment_payload(raw)
    allowed = {f.name for f in __import__('dataclasses').fields(AssessmentResult)}
    assessment = AssessmentResult(**{k:v for k,v in normalized.items() if k in allowed})
    profile_path = Path(".angelcopilot/profile.md")
    if not profile_path.exists():
        profile_path = Path("examples/profile.local.template.md")
    profile = load_investor_profile(profile_path)
    assessment = apply_scoring_rules(assessment, profile)
    return write_batch_outputs([assessment], OUT.parent, OUT.name, include_pdf=include_pdf)


if __name__ == "__main__":
    print(build())
