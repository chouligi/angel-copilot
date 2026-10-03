"""Summarize seven factors and enforce actionable investment decision gates."""

from __future__ import annotations
from dataclasses import asdict, replace
import re
from angelcopilot.economics import calculate_returns, number
from angelcopilot.models import AssessmentResult, InvestorProfile

CATEGORY_WEIGHTS = {"Team": .25, "Market": .20, "Product": .15, "Traction": .15,
                    "Unit Economics": .10, "Defensibility": .10, "Terms": .05}


def effective_weights(overrides: dict[str, float]) -> dict[str, float]:
    if set(overrides) - set(CATEGORY_WEIGHTS):
        raise ValueError("Unknown weight override category")
    weights = {key: number(overrides.get(key, value), key) for key, value in CATEGORY_WEIGHTS.items()}
    total = sum(weights.values())
    if not total:
        raise ValueError("Rubric weights cannot all be zero")
    return {key: value / total for key, value in weights.items()}


def apply_scoring_rules(assessment: AssessmentResult, profile: InvestorProfile) -> AssessmentResult:
    """Scores describe quality; explicit evidence/economics/suitability determine action."""
    weights = effective_weights(profile.evaluation_weight_overrides)
    scores = {key: None if assessment.category_scores.get(key) is None else
              number(assessment.category_scores[key], key, maximum=5) for key in weights}
    coverage = sum(weights[k] for k in weights if scores[k] is not None)
    score = round(sum(scores[k] * weights[k] for k in weights if scores[k] is not None), 3) if coverage > .999999 else None
    decision = dict(assessment.decision)
    modern = assessment.schema_version == 2
    verdict = str(decision.get("proposed_verdict", decision.get("verdict", "WAIT"))).upper() if modern else "WAIT"
    reason = str(decision.get("proposed_reason", decision.get("reason", "Recommendation requires a current assessment of evidence and net economics.")))
    warnings: list[str] = []
    minimum = number(profile.ticket_min, "ticket_min", minimum=.01) if profile.ticket_min is not None else None
    maximum = number(profile.ticket_max, "ticket_max", minimum=minimum or .01) if profile.ticket_max is not None else None
    typical = float(profile.ticket_typical) if profile.ticket_typical > 0 else (minimum or 0.0)
    configured_amount = typical if minimum is not None and maximum is not None else 0.0
    # A deal payload may propose a cheque, but cheque sizing is investor-specific.
    # Use only the saved profile's typical amount (or minimum when no typical is set).
    amount = configured_amount
    sizing = ("Investor profile typical ticket." if profile.ticket_typical else
              "Investor profile minimum ticket; no typical amount is configured.")
    suggested = decision.get("proposed_amount", decision.get("suggested_amount", 0))
    currency = profile.currency.strip().upper() or "EUR"
    if amount > 0:
        scenarios, summary = calculate_returns(assessment.return_assumptions, assessment.return_scenarios, amount, currency)
    else:
        scenarios, summary = assessment.return_scenarios, {"status": "unavailable", "reason": "The investor profile has no complete cheque range; no hypothetical ticket was assumed."}
    issues = assessment.diligence_issues
    hard_risk = any(_is_hard_risk(flag) for flag in assessment.risk_flags)

    def gate(new_verdict: str, message: str) -> None:
        nonlocal verdict, reason
        verdict, reason = new_verdict, message
        warnings.append(message)

    if verdict not in {"INVEST", "WAIT", "PASS"}:
        gate("WAIT", "No valid investment judgment was supplied.")
    if any(row.get("status") == "fatal" for row in issues):
        gate("PASS", "Deal-breaking issue: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "fatal"))
    elif verdict != "PASS":
        if modern and decision.get("economics") == "unattractive":
            gate("PASS", "Net risk/reward is unattractive at the current terms.")
        elif modern and decision.get("fit") == "incompatible":
            gate("PASS", "The opportunity conflicts with stated investor constraints.")
        elif any(row.get("status") == "blocker" for row in issues):
            gate("WAIT", "Resolve before investing: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "blocker"))
        elif hard_risk:
            gate("WAIT", "An unresolved hard-risk flag blocks an investment; establish its facts and fixability.")
    if verdict == "INVEST":
        if minimum is None or maximum is None:
            gate("WAIT", "The investor profile does not define a complete normal cheque range.")
        elif decision.get("evidence") != "sufficient" or coverage < .999999:
            gate("WAIT", "Material evidence is incomplete; a normal cheque is not justified yet.")
        elif decision.get("economics") != "attractive" or summary.get("status") != "available":
            gate("WAIT", "A credible net return case is not available at the reviewed terms.")
        elif decision.get("fit") != "compatible":
            gate("WAIT", "Confirm suitability for the stated investor constraints before investing.")
        elif not minimum <= amount <= maximum:
            gate("WAIT", "The proposed cheque falls outside the investor's normal ticket range.")
        elif number(decision.get("minimum_ticket", 0), "minimum_ticket") > amount:
            gate("WAIT", "The all-in proposed cheque does not meet the deal's minimum subscription.")
        elif profile.remaining_angel_budget is not None and amount > profile.remaining_angel_budget:
            gate("WAIT", "The normal cheque exceeds the known remaining angel budget.")
        elif amount != typical and not str(decision.get("sizing_reason", "")).strip():
            gate("WAIT", "Explain why the proposed cheque differs from the normal ticket.")
        elif profile.return_hurdle is not None:
            base = next(row for row in scenarios if row.get("kind") == "base")
            if float(base["annualized_return"]) < profile.return_hurdle:
                gate("PASS", "Base-case net annualized return is below the configured personal hurdle at current terms.")
    if not modern:
        warnings.append("Legacy assessment: no structured decision gates or question priorities were recorded. Re-assess to make a current recommendation.")
        decision["original_verdict"] = assessment.decision.get("original_verdict", assessment.verdict or "Not recorded")
    recommended = amount if verdict == "INVEST" else 0.0
    next_action = str(decision.get("proposed_next_action", decision.get("next_action", "Re-assess using the current framework.")))
    if warnings and modern:
        next_action = ("Do not commit; review the stated blocking conditions." if verdict == "WAIT" else "Do not commit under the current opportunity or terms.")
    decision.update({"proposed_verdict": decision.get("proposed_verdict", decision.get("verdict", verdict)),
                     "proposed_amount": decision.get("proposed_amount", suggested),
                     "proposed_reason": decision.get("proposed_reason", decision.get("reason", reason)),
                     "proposed_next_action": decision.get("proposed_next_action", decision.get("next_action", next_action)),
                     "verdict": verdict, "reason": reason, "suggested_amount": recommended, "model_amount": amount,
                     "next_action": next_action,
                     "judgment_basis": "Base-case annualized hurdle comparison plus investment judgment" if profile.return_hurdle is not None else "Qualitative investment judgment; no personal return hurdle supplied",
                     "return_hurdle": profile.return_hurdle})
    return replace(assessment, category_scores=scores, weighted_score=score, score_coverage=coverage,
                   effective_weights=weights, decision=decision, verdict=verdict, decision_reason=reason,
                   verdict_one_liner=reason, recommended_investment=recommended, hypothetical_investment=amount,
                   investment_currency=currency, investment_basis="profile_ticket_typical" if profile.ticket_typical else ("profile_ticket_minimum" if minimum is not None else "no_profile_ticket_configured"),
                   next_action=next_action, sizing_reason=sizing, return_scenarios=scenarios, return_summary=summary,
                   investor_constraints=asdict(profile),
                   dilution_assumption="Explicitly included; no follow-ons." if summary.get("status") == "available" else "Not recorded or model unavailable.",
                   decision_warnings=warnings, profile_fit=_compute_profile_fit(assessment, profile),
                   attention_flag=verdict == "INVEST", attention_reason=reason)


def _compute_profile_fit(assessment: AssessmentResult, profile: InvestorProfile) -> float:
    criteria = []
    if profile.sectors_themes:
        criteria.append(float(_matches_any(assessment.sectors, profile.sectors_themes)))
    if profile.geo_focus:
        criteria.append(float(_matches_any(assessment.geographies, profile.geo_focus)))
    return sum(criteria) / len(criteria) if criteria else 0.0


def _matches_any(values: list[str], preferences: list[str]) -> bool:
    """Matches any.
    
    Args:
        values: Value for ``values``.
        preferences: Value for ``preferences``.
    
    Returns:
        bool: Value returned by this function.
    """
    normalized_values = [_normalize_match_text(item) for item in values if item.strip()]
    normalized_preferences = [_normalize_match_text(item) for item in preferences if item.strip()]

    for value in normalized_values:
        value_tokens = set(value.split())
        for preference in normalized_preferences:
            preference_tokens = set(preference.split())
            if not value_tokens or not preference_tokens:
                continue
            if value_tokens == preference_tokens:
                return True
            if value_tokens.issubset(preference_tokens) or preference_tokens.issubset(value_tokens):
                return True
    return False


def _is_hard_risk(flag: str) -> bool:
    """Is hard risk.
    
    Args:
        flag: Value for ``flag``.
    
    Returns:
        bool: Value returned by this function.
    """
    normalized = flag.strip().lower()
    return normalized.startswith("hard:") or "hard-risk" in normalized or "hard risk" in normalized


def _normalize_match_text(value: str) -> str:
    """Normalize match text.
    
    Args:
        value: Value for ``value``.
    
    Returns:
        str: Value returned by this function.
    """
    text = value.strip().lower()
    replacements = {
        "u.s.a.": "united states",
        "u.s.": "united states",
        "usa": "united states",
        "us": "united states",
        "eu": "europe",
        "uk": "united kingdom",
    }
    for source, target in replacements.items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
