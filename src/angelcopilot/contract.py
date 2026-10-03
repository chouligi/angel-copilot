"""Validate the versioned assessment contract without manufacturing evidence."""

from __future__ import annotations

from angelcopilot.economics import calculate_returns, number, validate_scenarios

CATEGORIES = ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")


def text_field(obj: dict, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be nonempty text")
    return value.strip()


def choice(obj: dict, key: str, choices: set[str]) -> str:
    value = obj.get(key)
    if value not in choices:
        raise ValueError(f"{key} must be one of {sorted(choices)}")
    return str(value)


def validate_modern(payload: dict[str, object]) -> dict[str, object]:
    """Version 2 uses structured decisions, evidence issues and targeted asks."""
    result = dict(payload)
    for name in ("risk_flags", "sectors", "geographies", "evidence_sources", "extraction_warnings"):
        value = payload.get(name, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"{name} must be a list of text items")
        result[name] = value
    for name in ("web_sweep_sources", "citations"):
        value = payload.get(name, [])
        if not isinstance(value, list) or any(not isinstance(item, (str, dict)) for item in value):
            raise ValueError(f"{name} must be a list of text items or source objects")
        result[name] = value
    for name in ("assessment_limitations", "rationale"):
        if name in payload and not isinstance(payload[name], str):
            raise ValueError(f"{name} must be text")
    for name in ("category_scores", "category_rationales", "category_drivers", "category_confidence",
                 "deal_snapshot", "decision", "return_assumptions", "assessment_process"):
        if not isinstance(payload.get(name), dict):
            raise ValueError(f"{name} must be an object")
    for name in ("diligence_issues", "questions", "return_scenarios"):
        if not isinstance(payload.get(name), list) or any(not isinstance(row, dict) for row in payload[name]):
            raise ValueError(f"{name} must be a list of objects")
    result["category_scores"] = {
        key: None if payload["category_scores"].get(key) is None else number(payload["category_scores"][key], key, maximum=5)
        for key in CATEGORIES
    }
    for key in CATEGORIES:
        if key not in payload["category_scores"]:
            raise ValueError(f"Missing category score: {key}; use null for unknown")
        text_field(payload["category_rationales"], key)
        driver = text_field(payload["category_drivers"], key)
        if len(driver.split()) > 25:
            raise ValueError(f"{key} driver exceeds 25 words")
        choice(payload["category_confidence"], key, {"high", "medium", "low", "unknown"})
    for key in ("product", "customer", "stage", "instrument", "terms", "market_timing"):
        text_field(payload["deal_snapshot"], key)
    decision = payload["decision"]
    choice(decision, "verdict", {"INVEST", "WAIT", "PASS"})
    choice(decision, "economics", {"attractive", "unattractive", "unknown"})
    choice(decision, "evidence", {"sufficient", "incomplete"})
    choice(decision, "fit", {"compatible", "incompatible", "unknown"})
    for key in ("reason", "next_action", "sizing_reason"):
        text_field(decision, key)
    summary = decision.get("assessment_summary")
    if not isinstance(summary, dict):
        raise ValueError("decision.assessment_summary must be a structured object")
    summary_parts = ("investment_case", "supporting_evidence", "counterarguments", "decision_logic")
    if set(summary) != set(summary_parts):
        raise ValueError(f"decision.assessment_summary must contain exactly {list(summary_parts)}")
    word_counts = []
    for key in summary_parts:
        part = text_field(summary, key)
        count = len(part.split())
        if not 25 <= count <= 80:
            raise ValueError(f"decision.assessment_summary.{key} must contain 25–80 words")
        word_counts.append(count)
    if not 140 <= sum(word_counts) <= 260:
        raise ValueError("decision.assessment_summary must contain 140–260 words in total")
    suggested = number(decision.get("suggested_amount", 0), "suggested_amount")
    if decision["verdict"] != "INVEST" and suggested != 0:
        raise ValueError("WAIT and PASS must recommend zero now")
    issues = payload["diligence_issues"]
    if len(issues) > 5:
        raise ValueError("Keep at most five decision-critical diligence issues")
    ids: set[str] = set()
    for issue in issues:
        issue_id = text_field(issue, "id")
        if issue_id in ids:
            raise ValueError("Diligence issue IDs must be unique")
        ids.add(issue_id)
        priority = number(issue.get("priority"), "issue priority", minimum=1, maximum=5)
        if not priority.is_integer():
            raise ValueError("Issue priority must be an integer")
        choice(issue, "status", {"fatal", "blocker", "risk", "resolved"})
        choice(issue, "evidence_state", {"verified", "reported", "unknown", "conflicting"})
        for key in ("title", "finding", "decision_impact"):
            text_field(issue, key)
        if issue["status"] == "blocker":
            for key in ("evidence_needed", "reconsideration_condition"):
                text_field(issue, key)
    primary = []
    for question in payload["questions"]:
        ask = text_field(question, "question")
        if len(ask.split()) > 45:
            raise ValueError("Keep each question to one focused request, at most 45 words")
        audience = choice(question, "audience", {"founder", "syndicate_lead", "counsel", "customer"})
        if question.get("issue_id") not in ids:
            raise ValueError("Each question must link to an existing diligence issue")
        number(question.get("priority"), "question priority", minimum=1, maximum=100)
        if not isinstance(question.get("optional"), bool):
            raise ValueError("Question optional must be a boolean")
        text_field(question, "evidence_requested")
        if not question["optional"]:
            if audience != "founder":
                raise ValueError("Only founder questions may appear in the primary outreach block")
            primary.append(question)
    if len(primary) > 3:
        raise ValueError("At most three primary founder questions; three is a ceiling, not a quota")
    scenarios = payload["return_scenarios"]
    validate_scenarios(scenarios, modern=True)
    if scenarios:
        assumptions = payload["return_assumptions"]
        _, summary = calculate_returns(assumptions, scenarios, 1, str(assumptions.get("currency", "")))
        if summary["status"] != "available":
            raise ValueError(f"Invalid return assumptions: {summary['reason']}")
    elif payload["return_assumptions"]:
        raise ValueError("Supply scenarios with assumptions, or leave both empty when the model is unavailable")
    return result
