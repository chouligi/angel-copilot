from __future__ import annotations

from pathlib import Path
import re
import threading

import pytest
from angelcopilot.models import InvestorProfile
from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.pipeline import build_skill_native_prompt, run_batch_assessment
from angelcopilot.reporting import write_batch_outputs


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


class CapturingRunner:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del cwd
        self.prompts.append(prompt)
        return FakeRunner().run_assessment(prompt="", cwd=Path("."))


class FailingRunner:
    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del prompt
        del cwd
        raise RuntimeError("intentional failure")


class RepairingModernRunner:
    """Simulate a structurally malformed model response followed by a retry."""

    def __init__(self, defect: str) -> None:
        self.prompts: list[str] = []
        self.defect = defect

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del cwd
        self.prompts.append(prompt)
        payload = _modern_payload()
        if len(self.prompts) == 1:
            if self.defect == "return_assumptions":
                payload["return_assumptions"] = "not an object"
            else:
                raise AssertionError(f"Unknown synthetic defect: {self.defect}")
        return validate_assessment_payload(payload)


class CumulativeRetryRunner:
    """Exercise repeated validation repairs without a model/API call."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del cwd
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            raise ValueError("assessment_summary word count rejected")
        if len(self.prompts) == 2:
            raise ValueError("suggested_amount must be a number")
        payload = _modern_payload()
        return validate_assessment_payload(payload)


class AlwaysFailingRunner:
    """Simulate an unrecoverable generation failure and capture retry prompts."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del cwd
        self.prompts.append(prompt)
        raise RuntimeError("synthetic CLI transport failure")


class ShortSummaryMalformedRunner:
    """Return style warnings and repairable recommendation fields as raw JSON."""

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del prompt, cwd
        payload = _modern_payload()
        payload["decision"]["assessment_summary"] = {
            key: "Brief but usable summary." for key in (
                "investment_case", "supporting_evidence", "counterarguments", "decision_logic"
            )
        }
        payload["decision"]["suggested_amount"] = "not a number"
        payload["return_assumptions"] = "not an object"
        payload["category_drivers"]["Team"] = "decision driver " * 20
        payload["diligence_issues"] = [{
            "id": "I1", "priority": 1, "status": "critical", "evidence_state": "unverified",
            "title": "Evidence gap", "finding": "The claim is not supported.",
            "decision_impact": "It limits the current decision.",
        }]
        payload["questions"] = [{
            "question": "Please provide the underlying source documents and walk through every material assumption "
                         "used to prepare this forecast so that we can independently verify the reported figures, "
                         "including customer schedules, signed contracts, accounting records, calculation notes, "
                         "supporting correspondence, exclusions, adjustments, and the reconciliation to filed statements "
                         "for the last three reporting periods.",
            "priority": 1, "audience": "founder", "optional": False, "issue_id": "I1",
            "evidence_requested": "Underlying source documents and forecast bridge.",
        }]
        return payload


def _modern_payload() -> dict[str, object]:
    categories = ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")
    summary = "This synthetic assessment summary gives enough context to satisfy the versioned contract. " \
        "It describes what is known, what remains uncertain, and why the current decision follows from evidence. " \
        "The test does not contact external services and exists to verify the assessment repair boundary."
    return {
        "schema_version": 2,
        "deal_id": "deal_a",
        "company_name": "Deal A",
        "category_scores": {key: None for key in categories},
        "category_rationales": {key: "Evidence is not available in this synthetic test." for key in categories},
        "category_drivers": {key: "Insufficient evidence to support a score." for key in categories},
        "category_confidence": {key: "unknown" for key in categories},
        "deal_snapshot": {key: "Unknown" for key in ("product", "customer", "stage", "instrument", "terms", "market_timing")},
        "decision": {
            "verdict": "WAIT", "reason": "Evidence is insufficient.", "next_action": "Gather evidence.",
            "sizing_reason": "No cheque until evidence is sufficient.", "economics": "unknown",
            "evidence": "incomplete", "fit": "unknown", "suggested_amount": 0,
            "assessment_summary": {key: summary for key in (
                "investment_case", "supporting_evidence", "counterarguments", "decision_logic"
            )},
        },
        "diligence_issues": [], "questions": [], "return_assumptions": {}, "return_scenarios": [],
        "risk_flags": [], "sectors": [], "geographies": [], "rationale": "Synthetic integration fixture.",
        "citations": [], "web_sweep_sources": [], "assessment_limitations": "Synthetic test only.",
        "assessment_process": {
            "used_full_rubric": False, "performed_web_sweep": False,
            "reconciled_docs_with_web": False, "built_return_model": False,
        },
    }


class ThreadTrackingRunner:
    def __init__(self) -> None:
        self.thread_ids: set[int] = set()
        self.lock = threading.Lock()

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        del cwd
        deal_id_match = re.search(r"Deal ID: ([^\n]+)", prompt)
        deal_id = deal_id_match.group(1).strip() if deal_id_match else "unknown"
        with self.lock:
            self.thread_ids.add(threading.get_ident())
        return {
            "deal_id": deal_id,
            "company_name": deal_id.replace("_", " ").title(),
            "category_scores": {
                "Team": 4.1,
                "Market": 4.1,
                "Product": 4.1,
                "Traction": 4.1,
                "Unit Economics": 4.1,
                "Defensibility": 4.1,
                "Terms": 4.1,
            },
            "risk_flags": [],
            "sectors": ["AI"],
            "geographies": ["Europe"],
            "rationale": "Good",
            "citations": [],
            "category_rationales": {
                "Team": "Strong team.",
                "Market": "Large market.",
                "Product": "Useful product.",
                "Traction": "Early traction.",
                "Unit Economics": "Plausible economics.",
                "Defensibility": "Some moat.",
                "Terms": "Neutral terms.",
            },
            "web_sweep_findings": ["Finding"],
            "web_sweep_sources": ["https://example.com"],
            "milestones_to_monitor": ["Milestone"],
            "key_unknowns": ["Unknown"],
            "return_scenarios": [
                {"scenario": "Pessimistic", "multiple": "0.3x", "probability": "30%", "rationale": "Low"},
                {"scenario": "Base", "multiple": "3x", "probability": "50%", "rationale": "Medium"},
                {"scenario": "Optimistic", "multiple": "12x", "probability": "20%", "rationale": "High"},
            ],
            "assessment_limitations": "Fixture data only.",
            "assessment_process": {
                "single_deal_equivalent": "yes",
                "used_full_rubric": True,
                "performed_web_sweep": True,
                "reconciled_docs_with_web": True,
                "built_three_case_return_model": True,
            },
        }


def test_run_batch_assessment__processes_recent_deals_end_to_end(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")

    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])
    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=profile,
        runner=FakeRunner(),
        cwd=tmp_path,
    )

    assert len(results) == 1
    assert results[0].deal_id == "deal_a"
    assert results[0].weighted_score > 0


def test_run_batch_assessment__skill_native_mode_uses_skill_reference(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("region: EU\ncurrency: EUR\n", encoding="utf-8")
    runtime_skill_path = tmp_path / "SKILL.md"
    runtime_skill_path.write_text("placeholder skill", encoding="utf-8")

    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])
    runner = CapturingRunner()

    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=profile,
        runner=runner,
        cwd=tmp_path,
        profile_path=profile_path,
        runtime_skill_path=runtime_skill_path,
    )

    assert len(results) == 1
    assert runner.prompts
    prompt = runner.prompts[0]
    assert "[$angel-copilot](" in prompt
    assert str(runtime_skill_path) in prompt
    assert "assess the deal in " in prompt
    assert str(deal_folder) not in prompt
    assert str(profile_path) in prompt


def test_build_skill_native_prompt__states_modern_enum_and_object_contract(tmp_path: Path) -> None:
    prompt = build_skill_native_prompt(
        deal_id="deal_a", deal_path=tmp_path / "deal", profile_path=tmp_path / "profile.md"
    )

    assert "decision.economics must be exactly one of `attractive`, `unattractive`, `unknown`" in prompt
    assert "decision.fit must be exactly one of `compatible`, `incompatible`, `unknown`" in prompt
    assert "return_assumptions must always be a JSON object" in prompt
    assert "never use a string, array, or null for it" in prompt
    assert "decision.suggested_amount must be a JSON number" in prompt
    assert "evidence_state must be exactly verified/reported/unknown/conflicting" in prompt


def test_run_batch_assessment__normalizes_malformed_return_assumptions(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("Synthetic test evidence", encoding="utf-8")
    runner = RepairingModernRunner("return_assumptions")

    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"]),
        runner=runner,
        cwd=tmp_path,
    )

    assert len(results) == 1
    assert results[0].deal_id == "deal_a"
    assert len(runner.prompts) == 1
    assert any("Return assumptions were malformed" in warning for warning in results[0].assessment_quality_warnings)
    assert len(results[0].assessment_quality_warnings) == len(set(results[0].assessment_quality_warnings))


def test_run_batch_assessment__style_and_safe_decision_fixes_do_not_block_report(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("Synthetic test evidence", encoding="utf-8")

    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"]),
        runner=ShortSummaryMalformedRunner(),
        cwd=tmp_path,
    )

    assert len(results) == 1
    assessment = results[0]
    assert assessment.decision["suggested_amount"] == 0
    assert assessment.return_summary["status"] == "unavailable"
    assert any("Return assumptions were malformed" in warning for warning in assessment.assessment_quality_warnings)
    assert assessment.diligence_issues[0]["status"] == "blocker"
    assert assessment.diligence_issues[0]["evidence_state"] == "unknown"
    assert any("preferred total is 140–260" in warning for warning in assessment.assessment_quality_warnings)
    assert any("Team driver exceeds the preferred 25-word limit" in warning for warning in assessment.assessment_quality_warnings)
    assert any("exceeds the preferred 45-word limit" in warning for warning in assessment.assessment_quality_warnings)

    outputs = write_batch_outputs([assessment], tmp_path / "report", run_id="quality-smoke")
    assert outputs.markdown_path.is_file()
    report = outputs.markdown_path.read_text(encoding="utf-8")
    assert "Assessment Quality Notes" in report
    assert "No cheque recommended" in report
    assert "Team driver exceeds the preferred 25-word limit" in report
    assert "exceeds the preferred 45-word limit" in report


def test_run_batch_assessment__retry_feedback_accumulates_prior_errors(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("Synthetic test evidence", encoding="utf-8")
    runner = CumulativeRetryRunner()

    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"]),
        runner=runner,
        cwd=tmp_path,
    )

    assert len(results) == 1
    assert len(runner.prompts) == 3
    assert "assessment_summary word count rejected" in runner.prompts[1]
    assert "assessment_summary word count rejected" in runner.prompts[2]
    assert "suggested_amount must be a number" in runner.prompts[2]


def test_run_batch_assessment__uses_both_retries_and_reports_validation_feedback(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("Synthetic test evidence", encoding="utf-8")
    runner = AlwaysFailingRunner()
    events: list[tuple[str, dict[str, object]]] = []

    with pytest.raises(RuntimeError, match="No assessments completed successfully"):
        run_batch_assessment(
            deals_root=deals_root,
            since_days=7,
            profile=InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"]),
            runner=runner,
            cwd=tmp_path,
            progress_callback=lambda event, payload: events.append((event, payload)),
        )

    assert len(runner.prompts) == 3
    assert "synthetic CLI transport failure" in runner.prompts[1]
    assert "synthetic CLI transport failure" in runner.prompts[2]
    failed_payload = next(payload for event, payload in events if event == "deal_failed")
    assert "attempt_1=synthetic CLI transport failure" in str(failed_payload["error"])
    assert "attempt_2=synthetic CLI transport failure" in str(failed_payload["error"])
    assert "attempt_3=synthetic CLI transport failure" in str(failed_payload["error"])


def test_run_batch_assessment__emits_progress_events(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")

    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])
    events: list[str] = []

    def progress(event: str, payload: dict[str, object]) -> None:
        del payload
        events.append(event)

    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=profile,
        runner=FakeRunner(),
        cwd=tmp_path,
        progress_callback=progress,
    )

    assert len(results) == 1
    assert events[0] == "deal_discovery_started"
    assert "deal_discovery_completed" in events
    assert "batch_started" in events
    assert "deal_started" in events
    assert "deal_completed" in events
    assert events[-1] == "batch_completed"


def test_run_batch_assessment__emits_deal_failed_when_runner_errors(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")

    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])
    events: list[tuple[str, dict[str, object]]] = []

    def progress(event: str, payload: dict[str, object]) -> None:
        events.append((event, payload))

    with pytest.raises(RuntimeError, match="No assessments completed successfully"):
        run_batch_assessment(
            deals_root=deals_root,
            since_days=7,
            profile=profile,
            runner=FailingRunner(),
            cwd=tmp_path,
            progress_callback=progress,
        )

    failed_events = [payload for event, payload in events if event == "deal_failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["reason"] == "assistant_failed"


def test_run_batch_assessment__parallelism_runs_deals_on_multiple_threads(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    for deal_id in ("deal_a", "deal_b"):
        deal_folder = deals_root / deal_id
        deal_folder.mkdir(parents=True)
        (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")

    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])
    runner = ThreadTrackingRunner()

    results = run_batch_assessment(
        deals_root=deals_root,
        since_days=7,
        profile=profile,
        runner=runner,
        cwd=tmp_path,
        parallelism=2,
    )

    assert len(results) == 2
    assert len(runner.thread_ids) >= 2


def test_run_batch_assessment__parallelism_less_than_one_raises(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_a"
    deal_folder.mkdir(parents=True)
    (deal_folder / "memo.txt").write_text("AI startup with traction", encoding="utf-8")

    profile = InvestorProfile(sectors_themes=["AI"], geo_focus=["Europe"])
    with pytest.raises(ValueError, match="parallelism must be >= 1"):
        run_batch_assessment(
            deals_root=deals_root,
            since_days=7,
            profile=profile,
            runner=FakeRunner(),
            cwd=tmp_path,
            parallelism=0,
        )
