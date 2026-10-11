"""Validate the versioned assessment contract without manufacturing evidence."""

from __future__ import annotations

from angelcopilot.economics import calculate_returns, number, validate_scenarios

CATEGORIES = ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")


def assessment_response_schema() -> dict[str, object]:
    """JSON Schema for the current version 4 response structure.

    Semantic constraints that JSON Schema cannot express portably (such as
    probability sums and word counts) remain enforced by ``validate_modern``.
    """
    categories = list(CATEGORIES)
    text = {"type": "string"}

    def obj(properties: dict[str, object]) -> dict[str, object]:
        return {
            "type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False,
        }

    text_list = {"type": "array", "items": text}
    source_fields = {key: {"anyOf": [text, {"type": "null"}]} for key in ("id", "source", "date", "date_accessed", "url", "note")}
    source = {"anyOf": [text, obj(source_fields)]}
    issue = obj({
        "id": text,
        "priority": {"type": "number", "minimum": 1, "maximum": 5},
        "status": {"type": "string", "enum": ["fatal", "blocker", "risk", "resolved"]},
        "evidence_state": {"type": "string", "enum": ["verified", "reported", "unknown", "conflicting"]},
        "title": text,
        "finding": text,
        "decision_impact": text,
        "evidence_needed": text,
        "reconsideration_condition": text,
        "source_ids": text_list,
    })
    issue["properties"].update({"resolution_type": {"type": "string", "enum": ["document", "call", "business_milestone", "monitor"]}, "resolution_horizon": text})
    issue["required"].extend(["resolution_type", "resolution_horizon"])
    question = obj({
        "question": text,
        "priority": {"type": "number", "minimum": 1, "maximum": 100},
        "audience": {"type": "string", "enum": ["founder", "syndicate_lead", "counsel", "customer"]},
        "optional": {"type": "boolean"},
        "issue_id": text,
        "evidence_requested": text,
    })
    summary = obj({key: text for key in ("investment_case", "supporting_evidence", "counterarguments", "decision_logic")})
    decision = obj({
        "verdict": {"type": "string", "enum": ["INVEST", "PURSUE", "WAIT", "PASS"]},
        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": text,
        "assessment_summary": summary,
        "economics": {"type": "string", "enum": ["attractive", "unattractive", "unknown"]},
        "evidence": {"type": "string", "enum": ["sufficient", "incomplete"]},
        "fit": {"type": "string", "enum": ["compatible", "incompatible", "unknown"]},
        "suggested_amount": {"type": "number", "minimum": 0},
        "sizing_reason": text,
        "next_action": text,
        "minimum_ticket": {"type": "number", "minimum": 0},
    })
    assumption_values = {
        "currency": text,
        "valuation_currency": text,
        "fx_rate": {"type": "number", "minimum": 0.000001},
        "entry_valuation": {"type": "number", "minimum": 0.01},
        "entry_valuation_basis": {"type": "string", "enum": ["post_money"]},
        "exit_value_basis": {"type": "string", "enum": ["distributable_equity"]},
        "fee_rate": {"type": "number", "minimum": 0, "maximum": 0.9999},
        "fee_treatment": {"type": "string", "enum": ["deducted", "added"]},
        "carry_rate": {"type": "number", "minimum": 0, "maximum": 1},
        "carry_basis": {"type": "string", "enum": ["deployed_capital", "total_outlay"]},
        "dilution_rate": {"type": "number", "minimum": 0, "maximum": 1},
        "follow_on": {"type": "boolean", "enum": [False]},
        "years": {"type": "number", "minimum": 1},
        "ownership_note": text,
        "exclusions": text,
    }
    assumptions = {"anyOf": [obj(assumption_values), obj({})]}
    process = obj({
        "used_full_rubric": {"type": "boolean"},
        "performed_web_sweep": {"type": "boolean"},
        "reconciled_docs_with_web": {"type": "boolean"},
        "built_return_model": {"type": "boolean"},
        "notes": text,
    })
    properties = {
        "schema_version": {"type": "integer", "enum": [4]},
        "economic_ranges": {"anyOf": [obj({}), obj({
            "currency": text,
            **{key: {"type": "number", "minimum": 0.01} for key in ("entry_valuation_min", "entry_valuation_max")},
            "target_net_multiple": {"type": "number", "minimum": 1.01},
            **{key: {"type": "number", "minimum": 0, "maximum": 0.99} for key in ("dilution_min", "dilution_max", "fee_rate_min", "fee_rate_max", "carry_rate_min", "carry_rate_max")},
            "fee_treatment": {"type": "string", "enum": ["deducted", "added"]},
            "carry_basis": {"type": "string", "enum": ["deployed_capital", "total_outlay"]},
            "rationale": text,
        })]},
        "deal_id": text,
        "company_name": text,
        "category_scores": obj({key: {"anyOf": [
            {"type": "number", "minimum": 0, "maximum": 5}, {"type": "null"}
        ]} for key in categories}),
        "category_rationales": obj({key: text for key in categories}),
        "category_drivers": obj({key: text for key in categories}),
        "category_confidence": obj({key: {"type": "string", "enum": ["high", "medium", "low", "unknown"]} for key in categories}),
        "deal_snapshot": obj({key: text for key in ("company_summary", "product", "customer", "stage", "instrument", "terms", "market_timing")}),
        "decision": decision,
        "diligence_issues": {"type": "array", "maxItems": 5, "items": issue},
        "questions": {"type": "array", "items": question},
        "return_assumptions": assumptions,
        "return_scenarios": {"type": "array", "items": obj({
            "kind": {"type": "string", "enum": ["loss", "bear", "base", "upside"]},
            "scenario": text,
            "exit_value": {"type": "number", "minimum": 0},
            "probability": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": text,
        })},
        "risk_flags": text_list,
        "sectors": text_list,
        "geographies": text_list,
        "rationale": text,
        "citations": {"type": "array", "items": source},
        "web_sweep_sources": {"type": "array", "items": source},
        "assessment_limitations": text,
        "assessment_process": process,
        "evidence_sources": text_list,
        "extraction_warnings": text_list,
    }
    return obj(properties)


def text_field(obj: dict, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be nonempty text")
    return value.strip()


def validate_modern(payload: dict[str, object]) -> dict[str, object]:
    """Version 2 uses structured decisions, evidence issues and targeted asks."""
    result = dict(payload)
    result["category_confidence"] = dict(payload.get("category_confidence", {})) if isinstance(payload.get("category_confidence"), dict) else {}
    raw_warnings = payload.get("assessment_quality_warnings", [])
    quality_warnings: list[str] = [warning for warning in raw_warnings if isinstance(warning, str)] if isinstance(raw_warnings, list) else []
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
                 "deal_snapshot", "decision", "assessment_process"):
        if not isinstance(payload.get(name), dict):
            raise ValueError(f"{name} must be an object")
    for name in ("diligence_issues", "questions"):
        if not isinstance(payload.get(name), list) or any(not isinstance(row, dict) for row in payload[name]):
            raise ValueError(f"{name} must be a list of objects")
    return_model_shape_invalid = False
    if not isinstance(payload.get("return_assumptions"), dict):
        result["return_assumptions"] = {}
        return_model_shape_invalid = True
        quality_warnings.append("Return assumptions were malformed; the return model was omitted.")
    if not isinstance(payload.get("return_scenarios"), list) or any(
        not isinstance(row, dict) for row in payload["return_scenarios"]
    ):
        result["return_scenarios"] = []
        return_model_shape_invalid = True
        quality_warnings.append("Return scenarios were malformed; the return model was omitted.")
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
            quality_warnings.append(f"{key} driver exceeds the preferred 25-word limit.")
        if payload["category_confidence"].get(key) not in {"high", "medium", "low", "unknown"}:
            if payload.get("schema_version") in {3, 4}:
                raise ValueError(f"{key} Evidence strength must be high/medium/low/unknown")
            result["category_confidence"][key] = "unknown"
            quality_warnings.append(f"{key} Evidence strength was unrecognized and is shown as unknown.")
    for key in ("product", "customer", "stage", "instrument", "terms", "market_timing"):
        text_field(payload["deal_snapshot"], key)
    # Older saved assessments predate this field; fresh model responses require it.
    if "company_summary" in payload["deal_snapshot"]:
        text_field(payload["deal_snapshot"], "company_summary")
    decision = dict(payload["decision"])
    result["decision"] = decision
    if return_model_shape_invalid and decision.get("verdict") == "INVEST":
        decision["verdict"] = "WAIT"
        decision["suggested_amount"] = 0
        decision["reason"] = "No cheque recommended because the return model could not be read; review the assumptions."
        quality_warnings.append("INVEST was downgraded to WAIT because no valid return model was available.")
    verdicts = {"INVEST", "WAIT", "PASS"} if payload.get("schema_version") == 3 else {"INVEST", "PURSUE", "WAIT", "PASS"}
    choices = {
        "verdict": (verdicts, "WAIT"),
        "economics": ({"attractive", "unattractive", "unknown"}, "unknown"),
        "evidence": ({"sufficient", "incomplete"}, "incomplete"),
        "fit": ({"compatible", "incompatible", "unknown"}, "unknown"),
    }
    for key, (allowed, fallback) in choices.items():
        if decision.get(key) not in allowed:
            decision[key] = fallback
            quality_warnings.append(f"Decision field {key} was unrecognized; conservative value {fallback} was used.")
            if key == "verdict":
                decision["reason"] = "No cheque recommended because the supplied verdict could not be read; review this assessment."
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
        word_counts.append(count)
    if not 140 <= sum(word_counts) <= 260:
        quality_warnings.append(
            f"Assessment summary has {sum(word_counts)} words; preferred total is 140–260. Report generated anyway."
        )
    for key, count in zip(summary_parts, word_counts):
        if not 25 <= count <= 80:
            quality_warnings.append(
                f"Assessment summary section {key} has {count} words; preferred range is 25–80."
            )
    raw_suggested = decision.get("suggested_amount", 0)
    if decision["verdict"] != "INVEST":
        if raw_suggested != 0:
            quality_warnings.append("A nonzero or malformed cheque suggestion was reset to zero for a non-INVEST decision.")
        decision["suggested_amount"] = 0
    else:
        try:
            decision["suggested_amount"] = number(raw_suggested, "suggested_amount")
        except ValueError:
            decision["verdict"] = "WAIT"
            decision["suggested_amount"] = 0
            decision["reason"] = "No cheque recommended because the proposed amount could not be read; review before acting."
            quality_warnings.append("Unparseable cheque amount downgraded INVEST to WAIT and zero cheque.")
        if payload.get("schema_version") == 4 and decision["verdict"] == "INVEST" and decision["suggested_amount"] <= 0:
            decision["verdict"] = "WAIT"
            decision["suggested_amount"] = 0
            decision["reason"] = "No cheque recommended because INVEST requires a positive proposed amount; confirm the intended cheque before reconsidering."
            decision["next_action"] = decision["reason"]
            quality_warnings.append("INVEST was downgraded to WAIT because the proposed cheque amount was zero.")
    issues = [dict(issue) for issue in payload["diligence_issues"]]
    result["diligence_issues"] = issues
    if len(issues) > 5:
        issues = issues[:5]
        result["diligence_issues"] = issues
        quality_warnings.append("More than five diligence issues were supplied; only the first five are included.")
    ids: set[str] = set()
    for issue in issues:
        issue_id = text_field(issue, "id")
        if issue_id in ids:
            raise ValueError("Diligence issue IDs must be unique")
        ids.add(issue_id)
        priority = number(issue.get("priority"), "issue priority", minimum=1, maximum=5)
        if not priority.is_integer():
            raise ValueError("Issue priority must be an integer")
        if issue.get("status") not in {"fatal", "blocker", "risk", "resolved"}:
            issue["status"] = "blocker"
            quality_warnings.append(f"Issue {issue_id} had an unrecognized status and is conservatively marked blocker.")
        if issue.get("evidence_state") not in {"verified", "reported", "unknown", "conflicting"}:
            issue["evidence_state"] = "unknown"
            quality_warnings.append(f"Issue {issue_id} had an unrecognized evidence state and is shown as unknown.")
        for key in ("title", "finding", "decision_impact"):
            text_field(issue, key)
        if issue["status"] == "blocker":
            for key, fallback in (
                ("evidence_needed", "Request evidence needed to resolve this issue."),
                ("reconsideration_condition", "Reassess after the requested evidence is reviewed."),
            ):
                if not isinstance(issue.get(key), str) or not issue[key].strip():
                    issue[key] = fallback
                    quality_warnings.append(f"Issue {issue_id} omitted {key}; a generic follow-up was inserted.")
    questions = [dict(question) for question in payload["questions"]]
    result["questions"] = questions
    primary = []
    kept_questions = []
    for question in questions:
        ask = text_field(question, "question")
        if len(ask.split()) > 45:
            quality_warnings.append(f"Question linked to issue {question.get('issue_id')} exceeds the preferred 45-word limit.")
        audience = question.get("audience")
        if audience not in {"founder", "syndicate_lead", "counsel", "customer"}:
            question["audience"] = "syndicate_lead"
            question["optional"] = True
            quality_warnings.append("A question had an unrecognized audience and was routed as an optional syndicate-lead follow-up.")
        if question.get("issue_id") not in ids:
            quality_warnings.append("A question without a valid linked diligence issue was omitted.")
            continue
        number(question.get("priority"), "question priority", minimum=1, maximum=100)
        if not isinstance(question.get("optional"), bool):
            question["optional"] = True
            quality_warnings.append("A question with an invalid optional flag was treated as an optional follow-up.")
        text_field(question, "evidence_requested")
        kept_questions.append(question)
        if not question["optional"]:
            if question["audience"] != "founder":
                question["optional"] = True
                quality_warnings.append("A non-founder question was moved out of the primary founder outreach block.")
            else:
                primary.append(question)
    if len(primary) > 3:
        primary.sort(key=lambda question: number(question["priority"], "question priority", minimum=1, maximum=100))
        for question in primary[3:]:
            question["optional"] = True
        quality_warnings.append("More than three primary founder questions were supplied; lower-priority asks were moved to optional follow-ups.")
    result["questions"] = kept_questions
    scenarios = result.get("return_scenarios", payload.get("return_scenarios", []))
    try:
        validate_scenarios(scenarios, modern=True)
        if scenarios:
            assumptions = result.get("return_assumptions", payload.get("return_assumptions"))
            _, return_summary = calculate_returns(assumptions, scenarios, 1, str(assumptions.get("currency", "")))
            if return_summary["status"] != "available":
                raise ValueError(str(return_summary["reason"]))
        elif result.get("return_assumptions", payload.get("return_assumptions")):
            raise ValueError("assumptions were supplied without scenarios")
    except (TypeError, ValueError) as exc:
        result["return_scenarios"] = []
        result["return_assumptions"] = {}
        quality_warnings.append(f"Return model could not be validated and was omitted: {exc}")
        if decision["verdict"] == "INVEST":
            decision["verdict"] = "WAIT"
            decision["suggested_amount"] = 0
            decision["reason"] = "No cheque recommended because the return model could not be validated; review the assumptions."
            quality_warnings.append("INVEST was downgraded to WAIT because no valid return model was available.")
    result["assessment_quality_warnings"] = list(dict.fromkeys(quality_warnings))
    if payload.get("schema_version") == 3:
        validate_screening(result)
    elif payload.get("schema_version") == 4:
        validate_unified(result)
    return result


def validate_screening(result: dict[str, object]) -> None:
    """Validate pursuit independently of commitment and avoid invented quality."""
    if result.get("assessment_mode") not in {"screening", "commitment"}:
        raise ValueError("assessment_mode must be screening or commitment")
    screening = result.get("screening")
    if not isinstance(screening, dict):
        raise ValueError("screening must be an object")
    if screening.get("recommendation") not in {"PURSUE", "CONSIDER", "PASS"}:
        raise ValueError("screening.recommendation must be PURSUE/CONSIDER/PASS")
    if screening.get("priority") not in {"high", "medium", "low"}:
        raise ValueError("screening.priority must be high/medium/low")
    for key in ("reason", "next_action"):
        text_field(screening, key)
    allowed_priorities = {"PURSUE": {"high", "medium"}, "CONSIDER": {"medium", "low"}, "PASS": {"low"}}
    if screening["priority"] not in allowed_priorities[screening["recommendation"]]:
        raise ValueError("Pursuit priority must match recommendation: PURSUE high/medium; CONSIDER medium/low; PASS low")
    for key in CATEGORIES:
        if result["category_confidence"][key] == "unknown":
            result["category_scores"][key] = None
    for issue in result["diligence_issues"]:
        if issue.get("resolution_type") not in {"document", "call", "business_milestone", "monitor"}:
            raise ValueError("Every issue needs a valid resolution_type")
        text_field(issue, "resolution_horizon")
        if issue["status"] == "blocker" and issue["resolution_type"] == "monitor":
            raise ValueError("An accepted monitoring risk cannot be a commitment blocker")
    ranges = result.get("economic_ranges")
    if not isinstance(ranges, dict):
        raise ValueError("economic_ranges must be an object; use {} when unsupported")
    if ranges:
        from angelcopilot.economics import calculate_screening_sensitivity
        calculate_screening_sensitivity(ranges)  # Validate before rendering or scoring.


def validate_unified(result: dict[str, object]) -> None:
    """Validate the single-action version 4 recommendation."""
    decision = result.get("decision")
    if not isinstance(decision, dict) or decision.get("verdict") not in {"INVEST", "PURSUE", "WAIT", "PASS"}:
        raise ValueError("decision.verdict must be INVEST/PURSUE/WAIT/PASS")
    if decision["verdict"] != "INVEST" and decision.get("suggested_amount", 0) != 0:
        raise ValueError("Only an INVEST recommendation may include a cheque amount")
    if decision["verdict"] == "INVEST" and number(decision.get("suggested_amount", 0), "suggested_amount") <= 0:
        raise ValueError("INVEST requires a positive suggested_amount")
    if decision.get("priority") not in {"high", "medium", "low"}:
        raise ValueError("decision.priority must be high/medium/low")
    allowed_priorities = {
        "INVEST": {"high"}, "PURSUE": {"high", "medium"},
        "WAIT": {"high", "medium", "low"}, "PASS": {"low"},
    }
    if decision["priority"] not in allowed_priorities[decision["verdict"]]:
        raise ValueError("Recommendation priority must match INVEST/high, PURSUE/high-or-medium, WAIT/any, or PASS/low")
    for key in CATEGORIES:
        if result["category_confidence"][key] == "unknown":
            result["category_scores"][key] = None
    for issue in result["diligence_issues"]:
        if issue.get("resolution_type") not in {"document", "call", "business_milestone", "monitor"}:
            raise ValueError("Every issue needs a valid resolution_type")
        text_field(issue, "resolution_horizon")
        if issue["status"] == "blocker" and issue["resolution_type"] == "monitor":
            raise ValueError("An accepted monitoring risk cannot be a commitment blocker")
    ranges = result.get("economic_ranges")
    if not isinstance(ranges, dict):
        raise ValueError("economic_ranges must be an object; use {} when unsupported")
    if ranges:
        from angelcopilot.economics import calculate_screening_sensitivity
        calculate_screening_sensitivity(ranges)
