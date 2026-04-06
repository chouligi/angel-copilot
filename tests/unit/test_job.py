from __future__ import annotations

from pathlib import Path

from angelcopilot_batch.job import run_batch_job


class FakeRunner:
    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del prompt
        del cwd
        return {
            "deal_id": "deal_a",
            "company_name": "Deal A",
            "category_scores": {
                "Team": 4.4,
                "Market": 4.2,
                "Product": 4.0,
                "Traction": 3.9,
                "Unit Economics": 3.8,
                "Defensibility": 4.1,
                "Terms": 3.7,
            },
            "risk_flags": [],
            "sectors": ["AI"],
            "geographies": ["Europe"],
            "rationale": "Good",
            "citations": [
                {"id": "D1", "source": "memo.txt", "date": "2026-01-01", "url": "provided://memo.txt", "note": "n"},
                {"id": "W1", "source": "example", "date": "2026-01-02", "url": "https://example.com", "note": "n"},
            ],
            "category_rationales": {
                "Team": "Strong execution background.",
                "Market": "Large and growing market.",
                "Product": "Differentiated workflow product.",
                "Traction": "Early paid usage.",
                "Unit Economics": "Initial pricing signal only.",
                "Defensibility": "Execution speed and data loop.",
                "Terms": "Reasonable compared to peers.",
            },
            "web_sweep_findings": ["Company site and major funding coverage align on thesis."],
            "web_sweep_sources": ["https://example.com"],
            "milestones_to_monitor": ["Reach 100 paying customers."],
            "key_unknowns": ["Net dollar retention by segment."],
            "return_scenarios": [
                {"scenario": "Pessimistic", "multiple": "0.3x", "probability": "30%", "rationale": "No PMF"},
                {"scenario": "Base", "multiple": "3x", "probability": "50%", "rationale": "Moderate exit"},
                {"scenario": "Optimistic", "multiple": "12x", "probability": "20%", "rationale": "Strong scale"},
            ],
            "assessment_limitations": "Fixture data only.",
            "assessment_process": {
                "single_deal_equivalent": "yes",
                "used_full_rubric": True,
                "performed_web_sweep": True,
                "reconciled_docs_with_web": True,
                "built_three_case_return_model": True,
                "notes": "Fixture confirms end-to-end path.",
            },
        }


def test_run_batch_job__logs_progress_and_writes_outputs(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("region: EU\ncurrency: EUR\n", encoding="utf-8")

    messages: list[str] = []
    result = run_batch_job(
        deals_root=deals_root,
        since_days=7,
        assistant="codex",
        profile_path=profile_path,
        out=tmp_path / "outputs",
        top_level_containers=False,
        include_pdf=False,
        runner=FakeRunner(),
        logger=messages.append,
    )

    assert len(result.assessments) == 1
    assert result.output_paths.markdown_path.exists()
    assert not any("preparing deal" in msg for msg in messages)
    assert any("prepared deal" in msg for msg in messages)
    assert any("assessment started for 'deal_a'" in msg for msg in messages)
    assert any("done 'deal_a'" in msg for msg in messages)
    assert any("Assessing deals sequentially (parallelism=1)." in msg for msg in messages)


def test_run_batch_job__logs_parallelism_when_above_one(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("region: EU\ncurrency: EUR\n", encoding="utf-8")

    messages: list[str] = []
    run_batch_job(
        deals_root=deals_root,
        since_days=7,
        assistant="codex",
        profile_path=profile_path,
        out=tmp_path / "outputs",
        top_level_containers=False,
        include_pdf=False,
        runner=FakeRunner(),
        logger=messages.append,
        parallelism=4,
    )

    assert any("Assessing 4 deals in parallel." in msg for msg in messages)
