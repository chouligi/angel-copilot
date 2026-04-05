from __future__ import annotations

from pathlib import Path
import re

from angelcopilot_batch.models import InvestorProfile
from angelcopilot_batch.pipeline import run_batch_assessment


class FixtureRunner:
    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del cwd
        deal_id_match = re.search(r"Deal ID: ([^\n]+)", prompt)
        deal_id = deal_id_match.group(1).strip() if deal_id_match else "unknown"

        if deal_id == "beta_ops":
            sector = ["DevTools"]
            geography = ["US"]
            score_base = 3.95
        else:
            sector = ["AI"]
            geography = ["Europe"]
            score_base = 4.25

        return {
            "deal_id": deal_id,
            "company_name": deal_id.replace("_", " ").title(),
            "category_scores": {
                "Team": score_base,
                "Market": score_base,
                "Product": score_base,
                "Traction": score_base,
                "Unit Economics": score_base,
                "Defensibility": score_base,
                "Terms": score_base,
            },
            "risk_flags": [],
            "sectors": sector,
            "geographies": geography,
            "rationale": "Fixture assessment.",
            "citations": [
                {
                    "id": "D1",
                    "source": "fixture_memo",
                    "date": "2026-01-01",
                    "url": "provided://fixture_memo",
                    "note": "Fixture source.",
                },
                {
                    "id": "W1",
                    "source": "fixture_web",
                    "date": "2026-01-02",
                    "url": "https://example.com/fixture",
                    "note": "Fixture web source.",
                },
            ],
            "category_rationales": {
                "Team": "Strong operators.",
                "Market": "Viable market.",
                "Product": "Clear product wedge.",
                "Traction": "Early but positive signal.",
                "Unit Economics": "Limited early data.",
                "Defensibility": "Execution and domain moat.",
                "Terms": "Neutral fixture terms.",
            },
            "web_sweep_findings": ["Fixture web-sweep finding."],
            "web_sweep_sources": ["https://example.com/fixture"],
            "milestones_to_monitor": ["Convert pilots to annual contracts."],
            "key_unknowns": ["Long-term retention curve."],
            "return_scenarios": [
                {"scenario": "Pessimistic", "multiple": "0.3x", "probability": "30%", "rationale": "Weak PMF"},
                {"scenario": "Base", "multiple": "3x", "probability": "50%", "rationale": "Solid execution"},
                {"scenario": "Optimistic", "multiple": "12x", "probability": "20%", "rationale": "Breakout growth"},
            ],
            "assessment_limitations": "Fixture-only synthetic context.",
            "assessment_process": {
                "single_deal_equivalent": "yes",
                "used_full_rubric": True,
                "performed_web_sweep": True,
                "reconciled_docs_with_web": True,
                "built_three_case_return_model": True,
            },
        }


def test_run_batch_assessment__processes_fixture_deals_without_prod_docs(deals_fixtures_root: Path) -> None:
    profile = InvestorProfile(sectors_themes=["AI", "DevTools"], geo_focus=["Europe", "US"])

    results = run_batch_assessment(
        deals_root=deals_fixtures_root,
        since_days=7,
        profile=profile,
        runner=FixtureRunner(),
        cwd=deals_fixtures_root,
    )

    assert len(results) == 2
    result_ids = {item.deal_id for item in results}
    assert result_ids == {"alpha_ai", "beta_ops"}
    assert any(item.attention_flag for item in results)
