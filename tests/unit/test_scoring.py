from __future__ import annotations

from angelcopilot_batch.models import AssessmentResult, InvestorProfile
from angelcopilot_batch.scoring import apply_scoring_rules


def test_apply_scoring_rules__marks_invest_when_weighted_score_is_high() -> None:
    assessment = AssessmentResult(
        deal_id="deal-1",
        company_name="Alpha AI",
        category_scores={
            "Team": 4.7,
            "Market": 4.5,
            "Product": 4.3,
            "Traction": 4.1,
            "Unit Economics": 3.9,
            "Defensibility": 4.0,
            "Terms": 3.8,
        },
        risk_flags=[],
        sectors=["AI"],
        geographies=["Europe"],
        rationale="Strong deal",
    )
    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])

    scored = apply_scoring_rules(assessment, profile)

    assert scored.weighted_score >= 4.2
    assert scored.verdict == "INVEST"
    assert scored.attention_flag is True


def test_apply_scoring_rules__marks_strong_wait_for_attention() -> None:
    assessment = AssessmentResult(
        deal_id="deal-2",
        company_name="Beta Tools",
        category_scores={
            "Team": 4.2,
            "Market": 4.1,
            "Product": 4.0,
            "Traction": 3.8,
            "Unit Economics": 3.7,
            "Defensibility": 3.9,
            "Terms": 3.5,
        },
        risk_flags=[],
        sectors=["DevTools"],
        geographies=["US"],
        rationale="Promising but early",
    )
    profile = InvestorProfile(sectors_themes=["DevTools"], geo_focus=["US"])

    scored = apply_scoring_rules(assessment, profile)

    assert scored.verdict == "WAIT"
    assert 3.9 <= scored.weighted_score < 4.2
    assert scored.attention_flag is True


def test_apply_scoring_rules__blocks_attention_when_hard_risk_exists() -> None:
    assessment = AssessmentResult(
        deal_id="deal-3",
        company_name="Gamma Health",
        category_scores={
            "Team": 4.6,
            "Market": 4.5,
            "Product": 4.4,
            "Traction": 4.3,
            "Unit Economics": 4.2,
            "Defensibility": 4.1,
            "Terms": 4.0,
        },
        risk_flags=["hard:regulatory_blocker"],
        sectors=["Health"],
        geographies=["Europe"],
        rationale="Strong but blocked",
    )
    profile = InvestorProfile(sectors_themes=["Health"], geo_focus=["Europe"])

    scored = apply_scoring_rules(assessment, profile)

    assert scored.verdict == "INVEST"
    assert scored.attention_flag is False
    assert "hard-risk" in scored.attention_reason.lower()


def test_apply_scoring_rules__profile_fit_matches_fuzzy_sector_and_geo_terms() -> None:
    assessment = AssessmentResult(
        deal_id="deal-4",
        company_name="Delta AI",
        category_scores={
            "Team": 4.1,
            "Market": 4.0,
            "Product": 4.0,
            "Traction": 3.9,
            "Unit Economics": 3.8,
            "Defensibility": 3.9,
            "Terms": 3.7,
        },
        risk_flags=[],
        sectors=["Frontier AI", "Developer Tooling"],
        geographies=["United States (HQ/formation signals)"],
        rationale="Good fit test",
    )
    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["US"])

    scored = apply_scoring_rules(assessment, profile)

    assert scored.profile_fit == 1.0
