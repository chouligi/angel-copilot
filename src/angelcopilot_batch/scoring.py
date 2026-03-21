from __future__ import annotations

from dataclasses import replace
import re

from angelcopilot_batch.models import AssessmentResult, InvestorProfile

CATEGORY_WEIGHTS = {
    "Team": 0.25,
    "Market": 0.20,
    "Product": 0.15,
    "Traction": 0.15,
    "Unit Economics": 0.10,
    "Defensibility": 0.10,
    "Terms": 0.05,
}


def apply_scoring_rules(assessment: AssessmentResult, profile: InvestorProfile) -> AssessmentResult:
    weighted_score = _compute_weighted_score(assessment.category_scores)
    verdict = _map_verdict(weighted_score)
    profile_fit = _compute_profile_fit(assessment, profile)

    has_hard_risk = any(_is_hard_risk(flag) for flag in assessment.risk_flags)
    if has_hard_risk:
        attention_flag = False
        attention_reason = "Blocked by hard-risk gate."
    else:
        attention_flag, attention_reason = _evaluate_attention(verdict, weighted_score, profile_fit)

    return replace(
        assessment,
        weighted_score=weighted_score,
        verdict=verdict,
        attention_flag=attention_flag,
        attention_reason=attention_reason,
        profile_fit=profile_fit,
    )


def _compute_weighted_score(category_scores: dict[str, float]) -> float:
    total = 0.0
    for category, weight in CATEGORY_WEIGHTS.items():
        total += float(category_scores.get(category, 0.0)) * weight
    return round(total, 3)


def _map_verdict(weighted_score: float) -> str:
    if weighted_score >= 4.2:
        return "INVEST"
    if weighted_score >= 3.5:
        return "WAIT"
    return "PASS"


def _compute_profile_fit(assessment: AssessmentResult, profile: InvestorProfile) -> float:
    criteria: list[float] = []

    if profile.sectors_themes:
        criteria.append(1.0 if _matches_any(assessment.sectors, profile.sectors_themes) else 0.0)

    if profile.geo_focus:
        criteria.append(1.0 if _matches_any(assessment.geographies, profile.geo_focus) else 0.0)

    if not criteria:
        return 0.5

    return round(sum(criteria) / len(criteria), 3)


def _evaluate_attention(verdict: str, weighted_score: float, profile_fit: float) -> tuple[bool, str]:
    if verdict == "INVEST":
        return True, "INVEST verdict and risk gates passed."

    if verdict == "WAIT" and weighted_score >= 3.9 and profile_fit >= 0.5:
        return True, "Strong WAIT matched profile and crossed 3.9 threshold."

    return False, "Below attention threshold."


def _matches_any(values: list[str], preferences: list[str]) -> bool:
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
    normalized = flag.strip().lower()
    return normalized.startswith("hard:") or "hard-risk" in normalized or "hard risk" in normalized


def _normalize_match_text(value: str) -> str:
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
