"""Summarize seven factors and enforce actionable investment decision gates."""

from __future__ import annotations
from dataclasses import asdict, replace
import re
from angelcopilot.economics import calculate_returns, calculate_screening_sensitivity, number
from angelcopilot.models import AssessmentResult, InvestorProfile

CATEGORY_WEIGHTS = {"Team": .25, "Market": .20, "Product": .15, "Traction": .15,
                    "Unit Economics": .10, "Defensibility": .10, "Terms": .05}
PURSUIT_SCORE_FLOOR = 3.5


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
    revised = assessment.schema_version == 3
    unified = assessment.schema_version == 4
    current = revised or unified
    weights = effective_weights(profile.evaluation_weight_overrides)
    scores = {key: None if assessment.category_scores.get(key) is None else
              number(assessment.category_scores[key], key, maximum=5) for key in weights}
    if current:
        scores = {k: None if assessment.category_confidence.get(k) == "unknown" else value for k, value in scores.items()}
    coverage = sum(weights[k] for k in weights if scores[k] is not None)
    weighted_total = sum(scores[k] * weights[k] for k in weights if scores[k] is not None)
    # New assessments report the weighted average of assessable factors and disclose
    # coverage separately. Unknown factors are excluded, never treated as zero.
    # Preserve the historical all-or-nothing aggregate for archived v1/v2 rows.
    score = (round(weighted_total / coverage, 3) if current and coverage > 0 else
             round(weighted_total, 3) if coverage > .999999 else None)
    decision = dict(assessment.decision)
    modern = assessment.schema_version in {2, 3, 4}
    mode = assessment.assessment_mode if revised else ("unified" if unified else "commitment")
    verdict = str(decision.get("proposed_verdict", decision.get("verdict", "WAIT"))).upper() if modern else "WAIT"
    reason = str(decision.get("proposed_reason", decision.get("reason", "Recommendation requires a current assessment of evidence and net economics.")))
    warnings: list[str] = []
    invalid_unified_investment_amount = (
        unified and verdict == "INVEST" and
        number(decision.get("suggested_amount", 0), "suggested_amount") <= 0
    )
    if invalid_unified_investment_amount:
        verdict = "WAIT"
        reason = "No cheque recommended because INVEST requires a positive proposed amount; confirm the intended cheque before reconsidering."
        decision["next_action"] = reason
        warnings.append("INVEST was downgraded to WAIT because the proposed cheque amount was zero.")
    minimum = number(profile.ticket_min, "ticket_min", minimum=.01) if profile.ticket_min is not None else None
    maximum = number(profile.ticket_max, "ticket_max", minimum=minimum or .01) if profile.ticket_max is not None else None
    typical = float(profile.ticket_typical) if profile.ticket_typical > 0 else (minimum or 0.0)
    configured_amount = typical if minimum is not None and maximum is not None else 0.0
    # A deal payload may propose a cheque, but cheque sizing is investor-specific.
    # Archives retain typical-only sizing; current assessments allow justified sizing within the saved range.
    amount = configured_amount
    sizing = ("Investor profile typical ticket." if profile.ticket_typical else
              "Investor profile minimum ticket; no typical amount is configured.")
    suggested = decision.get("proposed_amount", decision.get("suggested_amount", 0))
    if invalid_unified_investment_amount:
        amount = 0.0
        sizing = "No cheque; INVEST did not include a positive proposed amount."
    elif current and minimum is not None and maximum is not None:
        proposed = number(suggested, "suggested_amount")
        if proposed > 0:
            amount = proposed
            sizing = str(decision.get("sizing_reason", ""))
        else:
            deal_minimum = number(decision.get("minimum_ticket", 0), "minimum_ticket")
            amount = max(minimum, typical, deal_minimum)
            if profile.remaining_angel_budget is not None:
                amount = min(amount, profile.remaining_angel_budget)
            if amount != typical:
                sizing = "Adjusted within the allowed range for the subscription minimum and known remaining budget."
    sensitivity = calculate_screening_sensitivity(assessment.economic_ranges) if current else {"status": "unavailable"}
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
        if unified:
            decision["next_action"] = message
        warnings.append(message)

    if verdict not in ({"INVEST", "PURSUE", "WAIT", "PASS"} if unified else {"INVEST", "WAIT", "PASS"}):
        gate("WAIT", "No valid investment judgment was supplied.")
    if any(row.get("status") == "fatal" for row in issues):
        gate("PASS", "Deal-breaking issue: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "fatal"))
    elif verdict != "PASS":
        if modern and decision.get("economics") == "unattractive":
            gate("PASS", "Net risk/reward is unattractive at the current terms.")
        elif modern and decision.get("fit") == "incompatible":
            gate("PASS", "The opportunity conflicts with stated investor constraints.")
        elif verdict == "INVEST" and any(row.get("status") == "blocker" for row in issues):
            gate("WAIT", "Resolve before investing: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "blocker"))
        elif verdict == "INVEST" and hard_risk:
            gate("WAIT", "An unresolved hard-risk flag blocks an investment; establish its facts and fixability.")
    if revised and mode == "screening":
        verdict = "PASS" if verdict == "PASS" else "WAIT"
        reason = "Commitment has not been assessed; this is a pursuit screening."
    if revised and assessment.screening.get("recommendation") == "PASS" and verdict == "INVEST":
        gate("WAIT", "A PASS screening cannot support commitment; reconcile the investment judgment.")
    if verdict == "INVEST":
        if minimum is None or maximum is None:
            gate("WAIT", "The investor profile does not define a complete normal cheque range.")
        elif decision.get("evidence") != "sufficient" or (not revised and coverage < .999999):
            gate("WAIT", "Material evidence is incomplete; a normal cheque is not justified yet.")
        elif decision.get("economics") != "attractive" or (summary.get("status") != "available" and sensitivity.get("status") != "available"):
            gate("WAIT", "A credible net return case is not available at the reviewed terms.")
        elif decision.get("fit") != "compatible":
            gate("WAIT", "Confirm suitability for the stated investor constraints before investing.")
        elif not minimum <= amount <= maximum:
            gate("WAIT", "The proposed cheque falls outside the investor's normal ticket range.")
        elif number(decision.get("minimum_ticket", 0), "minimum_ticket") > amount:
            gate("WAIT", "The all-in proposed cheque does not meet the deal's minimum subscription.")
        elif profile.remaining_angel_budget is not None and amount > profile.remaining_angel_budget:
            gate("WAIT", "The normal cheque exceeds the known remaining angel budget.")
        elif amount != typical and not sizing.strip():
            gate("WAIT", "Explain why the proposed cheque differs from the normal ticket.")
        elif profile.return_hurdle is not None:
            base = next((row for row in scenarios if row.get("kind") == "base"), None)
            if summary.get("status") != "available" or base is None:
                gate("WAIT", "A base-case net model is needed to compare the configured personal hurdle.")
            elif float(base["annualized_return"]) < profile.return_hurdle:
                gate("PASS", "Base-case net annualized return is below the configured personal hurdle at current terms.")
    if not modern:
        warnings.append("Legacy assessment: no structured decision gates or question priorities were recorded. Re-assess to make a current recommendation.")
        decision["original_verdict"] = assessment.decision.get("original_verdict", assessment.verdict or "Not recorded")
    recommended = amount if verdict == "INVEST" else 0.0
    next_action = str(decision.get("proposed_next_action", decision.get("next_action", "Re-assess using the current framework.")))
    screening = dict(assessment.screening) if revised else {}
    pursuit = str(screening.get("recommendation", "")) if revised else (verdict if unified else "")
    priority = str(screening.get("priority", "")) if revised else (str(decision.get("priority", "")) if unified else "")
    pursuit_reason = str(screening.get("reason", "")) if revised else (reason if unified else "")
    if revised and ((mode == "commitment" and verdict == "PASS") or any(row.get("status") == "fatal" for row in issues) or decision.get("economics") == "unattractive" or decision.get("fit") == "incompatible"):
        pursuit, priority = "PASS", "low"
        pursuit_reason = reason if mode == "commitment" else (
            "Deal-breaking issue: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "fatal") if any(row.get("status") == "fatal" for row in issues) else
            "The current terms have unattractive net economics." if decision.get("economics") == "unattractive" else
            "The opportunity conflicts with stated investor constraints.")
        next_action = "Decline the current opportunity; reconsider only if the stated objection changes."
    elif revised:
        next_action = str(screening["next_action"])
    if unified and (verdict == "PASS" or any(row.get("status") == "fatal" for row in issues) or
                    decision.get("economics") == "unattractive" or decision.get("fit") == "incompatible"):
        verdict = pursuit = "PASS"
        priority = "low"
        if any(row.get("status") == "fatal" for row in issues):
            reason = "Deal-breaking issue: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "fatal")
        elif decision.get("economics") == "unattractive":
            reason = "Net risk/reward is unattractive at the current terms."
        elif decision.get("fit") == "incompatible":
            reason = "The opportunity conflicts with stated investor constraints."
        pursuit_reason = reason
        next_action = "Stop work at the current terms; reconsider only if the stated objection changes."
        decision["verdict"] = verdict
        decision["reason"] = reason
        decision["next_action"] = next_action
    if revised and pursuit == "PURSUE" and (score is None or score < PURSUIT_SCORE_FLOOR):
        score_text = "no assessable weighted score" if score is None else f"{score:.1f} / 5"
        original_reason = pursuit_reason.split(". ", 1)[0].strip()
        pursuit = "CONSIDER"
        priority = "medium" if priority in {"high", "medium"} else "low"
        pursuit_reason = (
            f"Score {score_text} is below the {PURSUIT_SCORE_FLOOR:.1f} PURSUE minimum. "
            f"Consider targeted follow-up only: {original_reason}"
        )
        summary = decision.get("assessment_summary")
        if isinstance(summary, dict):
            summary = dict(summary)
            logic = str(summary.get("decision_logic", ""))
            logic = logic.replace("PURSUE", "CONSIDER").replace("Pursue", "Consider").replace("pursue", "consider")
            summary["decision_logic"] = (
                f"The {PURSUIT_SCORE_FLOOR:.1f} / 5 minimum for PURSUE is not met ({score_text}); classify as CONSIDER. "
                f"{logic}"
            ).strip()
            decision["assessment_summary"] = summary
    if revised:
        screening.update(recommendation=pursuit, priority=priority, reason=pursuit_reason, next_action=next_action)
    if unified and verdict == "PURSUE" and (score is None or score < PURSUIT_SCORE_FLOOR):
        verdict = pursuit = "WAIT"
        priority = "low"
        trigger = next((str(row.get("reconsideration_condition", "")).strip() for row in sorted(issues, key=lambda row: row.get("priority", 99))
                        if str(row.get("reconsideration_condition", "")).strip()), "New evidence that materially changes the factor assessment")
        reason = pursuit_reason = (
            f"Score {score:.1f} / 5 is below the {PURSUIT_SCORE_FLOOR:.1f} PURSUE minimum; wait for a material change before prioritizing diligence."
            if score is not None else
            f"No weighted score can be calculated, so the {PURSUIT_SCORE_FLOOR:.1f} PURSUE minimum is not met; wait for a material change before prioritizing diligence."
        )
        decision["verdict"] = verdict
        decision["reason"] = reason
        decision["next_action"] = "Revisit when: " + trigger
        summary = decision.get("assessment_summary")
        if isinstance(summary, dict):
            summary = dict(summary)
            previous = str(summary.get("decision_logic", ""))
            summary["decision_logic"] = (
                f"The {PURSUIT_SCORE_FLOOR:.1f} / 5 minimum for PURSUE is not met; recommend WAIT until this trigger: {trigger}. "
                f"{previous.replace('PURSUE', 'WAIT').replace('Pursue', 'Wait').replace('pursue', 'wait')}"
            ).strip()
            decision["assessment_summary"] = summary
        next_action = decision["next_action"]
    readiness = "Ready to commit" if verdict == "INVEST" else (
        "Cannot assess readiness" if pursuit == "PASS" or verdict == "PASS" else
        "Diligence required" if any(row.get("status") == "blocker" for row in issues) or decision.get("evidence") == "incomplete" else "Cannot assess readiness")
    readiness_reason = reason
    if revised and mode == "screening":
        if pursuit == "PASS":
            readiness_reason = "Opportunity declined: " + pursuit_reason
        elif any(row.get("status") == "blocker" for row in issues):
            readiness_reason = "Verify before committing: " + "; ".join(str(row.get("title")) for row in issues if row.get("status") == "blocker")
        elif decision.get("evidence") == "incomplete":
            readiness_reason = "Material evidence needs verification; commitment has not been assessed."

    fit_score = _compute_profile_fit(assessment, profile)
    eligible_attention = modern and verdict != "PASS" and not hard_risk and not any(row.get("status") == "fatal" for row in issues) and decision.get("fit") != "incompatible"
    attention = eligible_attention and (pursuit == "PURSUE" and priority == "high" if revised else
        (verdict == "INVEST" or (verdict == "PURSUE" and priority == "high")) if unified else
        verdict == "INVEST" or (verdict == "WAIT" and score is not None and score >= 3.9 and fit_score >= .5))
    attention_reason = ("High-priority PURSUE; " + pursuit_reason if revised else
        "INVEST recommendation." if unified and verdict == "INVEST" else "High-priority PURSUE recommendation." if unified else
        "Ready to commit." if verdict == "INVEST" else "Strong WAIT: score >= 3.9 and profile fit >= 0.5.") if attention else (
        "Archived record: pursuit priority was not assessed." if not modern else
        "Priority follow-up excluded: the opportunity is declined, has an unresolved hard risk or conflicts with investor constraints." if not eligible_attention else
        "Worth pursuing; medium-priority follow-up." if pursuit == "PURSUE" and priority == "medium" else
        "Monitor the stated trigger before further diligence." if verdict == "WAIT" else
        "Follow the stated next action at the assigned priority.")
    if revised:
        decision.update({"proposed_verdict": decision.get("proposed_verdict", decision.get("verdict", verdict)),
                         "proposed_amount": decision.get("proposed_amount", suggested),
                         "proposed_reason": decision.get("proposed_reason", decision.get("reason", reason)),
                         "proposed_next_action": decision.get("proposed_next_action", decision.get("next_action", next_action))})
    decision.update({"verdict": verdict, "reason": reason, "suggested_amount": recommended, "model_amount": amount,
                     "next_action": next_action,
                     "judgment_basis": "Base-case annualized hurdle comparison plus investment judgment" if profile.return_hurdle is not None else "Qualitative investment judgment; no personal return hurdle supplied",
                     "return_hurdle": profile.return_hurdle})
    if unified:
        decision["priority"] = priority
    return replace(assessment, category_scores=scores, weighted_score=score, score_coverage=coverage,
                   effective_weights=weights, decision=decision, verdict=verdict, decision_reason=reason,
                   verdict_one_liner=reason, recommended_investment=recommended, hypothetical_investment=amount,
                   investment_currency=currency, investment_basis="profile_ticket_typical" if profile.ticket_typical else ("profile_ticket_minimum" if minimum is not None else "no_profile_ticket_configured"),
                   next_action=next_action, sizing_reason=sizing, return_scenarios=scenarios, return_summary=summary,
                   investor_constraints=asdict(profile),
                   dilution_assumption="Explicitly included; no follow-ons." if summary.get("status") == "available" else "Not recorded or model unavailable.",
                   decision_warnings=warnings, profile_fit=fit_score,
                   assessment_mode=mode, screening=screening, pursuit_recommendation=pursuit,
                   pursuit_priority=priority, pursuit_reason=pursuit_reason,
                   commitment_readiness=readiness, readiness_reason=readiness_reason,
                   economic_sensitivity=sensitivity,
                   attention_flag=bool(attention), attention_reason=attention_reason)


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


def assessment_sort_key(assessment: AssessmentResult) -> tuple:
    """Rank by action, follow-up priority, evidence strength, then score."""
    if assessment.schema_version == 4:
        strength = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        evidence = sum(strength.get(v, 0) for v in assessment.category_confidence.values()) / 7
        return ({"INVEST": 0, "PURSUE": 1, "WAIT": 2, "PASS": 3}.get(assessment.verdict, 4),
                {"high": 0, "medium": 1, "low": 2}.get(str(assessment.decision.get("priority", assessment.pursuit_priority)), 3),
                -evidence, -(assessment.weighted_score or 0), assessment.company_name)
    if assessment.schema_version == 3:
        strength = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        evidence = sum(strength.get(v, 0) for v in assessment.category_confidence.values()) / 7
        return ({"PURSUE": 0, "CONSIDER": 1, "PASS": 2}.get(assessment.pursuit_recommendation, 3),
                {"high": 0, "medium": 1, "low": 2}.get(assessment.pursuit_priority, 3),
                -evidence, -(assessment.weighted_score or 0), assessment.company_name)
    return (3, {"INVEST": 0, "WAIT": 1, "PASS": 2}.get(assessment.verdict, 3), 0,
            -(assessment.weighted_score or 0), assessment.company_name)
