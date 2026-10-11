from __future__ import annotations

from copy import deepcopy


_SUMMARY = (
    "All figures and claims in this synthetic fixture are illustrative, designed only to exercise assessment "
    "validation, score calculation and report generation. They do not represent verified company facts, "
    "demonstrate actual customer demand, or support a real investment decision; replace them with deal-specific "
    "evidence before relying on any assessment."
)


def as_v4(payload: dict[str, object]) -> dict[str, object]:
    """Upgrade a legacy-shaped test payload to the current assessment contract."""
    result = deepcopy(payload)
    scores = result.get("category_scores", {})
    categories = ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")
    result["schema_version"] = 4
    result["economic_ranges"] = {}
    result["category_confidence"] = {
        key: "medium" if isinstance(scores, dict) and scores.get(key) is not None else "unknown"
        for key in categories
    }
    rationales = result.get("category_rationales", {})
    result["category_drivers"] = {
        key: (str(rationales.get(key, "Synthetic fixture factor."))[:150])
        for key in categories
    }
    company = str(result.get("company_name", "Synthetic company"))
    result["deal_snapshot"] = {
        "company_summary": f"{company} is a fictional business included to exercise the assessment pipeline; its product, buyer and traction are synthetic.",
        "product": "Synthetic fixture product.",
        "customer": "Synthetic fixture customer.",
        "stage": "Synthetic early stage.",
        "instrument": "Unknown.",
        "terms": "Unknown.",
        "market_timing": "Unknown.",
    }
    result["decision"] = {
        "verdict": "WAIT",
        "priority": "medium",
        "reason": "Synthetic fixture; no real investment judgment is intended.",
        "assessment_summary": {key: _SUMMARY for key in (
            "investment_case", "supporting_evidence", "counterarguments", "decision_logic"
        )},
        "economics": "unknown",
        "evidence": "incomplete",
        "fit": "unknown",
        "suggested_amount": 0,
        "sizing_reason": "No cheque in synthetic fixture.",
        "next_action": "Do not act on synthetic data.",
        "minimum_ticket": 0,
    }
    result["diligence_issues"] = []
    result["questions"] = []
    result["return_assumptions"] = {}
    result["return_scenarios"] = []
    process = result.get("assessment_process", {})
    result["assessment_process"] = {
        "used_full_rubric": bool(process.get("used_full_rubric", False)),
        "performed_web_sweep": bool(process.get("performed_web_sweep", False)),
        "reconciled_docs_with_web": bool(process.get("reconciled_docs_with_web", False)),
        "built_return_model": False,
        "notes": "Synthetic fixture only; no live company assessment was performed.",
    }
    result.setdefault("risk_flags", [])
    result.setdefault("sectors", [])
    result.setdefault("geographies", [])
    result.setdefault("rationale", "Synthetic fixture only.")
    result.setdefault("citations", [])
    result.setdefault("web_sweep_sources", [])
    result.setdefault("assessment_limitations", "Synthetic fixture only.")
    return result
