"""Core batch orchestration from deal discovery to scored assessments."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, fields
from datetime import datetime
import json
from pathlib import Path

from angelcopilot.assistant import validate_assessment_payload
from angelcopilot.intake import discover_recent_deals
from angelcopilot.models import AssessmentResult, DealInput, InvestorProfile
from angelcopilot.preparation import (
    PreparedDealWorkspace,
    cleanup_prepared_workspace,
    prepare_deal_workspace,
)
from angelcopilot.scoring import apply_scoring_rules

_REPO_SKILL = Path(__file__).resolve().parents[2] / "skills/public/angel-copilot/SKILL.md"
DEFAULT_RUNTIME_SKILL_PATH = _REPO_SKILL if _REPO_SKILL.is_file() else Path.home() / ".codex/skills/angel-copilot/SKILL.md"
EXECUTION_MODE_SKILL_NATIVE = "skill_native"
ProgressCallback = Callable[[str, dict[str, object]], None]


@dataclass
class PreparedDealTask:
    """Prepared per-deal execution payload for worker processing."""

    deal: DealInput
    index: int
    total: int
    workspace: PreparedDealWorkspace
    prompt: str


def run_batch_assessment(
    deals_root: Path,
    since_days: int | None,
    profile: InvestorProfile,
    runner,
    cwd: Path,
    profile_path: Path | None = None,
    execution_mode: str = EXECUTION_MODE_SKILL_NATIVE,
    runtime_skill_path: Path = DEFAULT_RUNTIME_SKILL_PATH,
    top_level_containers: bool = False,
    intake_filter: str = "smart",
    folder_classifier=None,
    progress_callback: ProgressCallback | None = None,
    parallelism: int = 1,
) -> list[AssessmentResult]:
    """Run end-to-end batch assessment and return scored, sorted results.

    Args:
        deals_root: Root directory with discovered deal folders/files.
        since_days: Intake lookback window in days; ``None`` includes all deals.
        profile: Investor profile used for fit and scoring.
        runner: Assistant runner implementing ``run_assessment``.
        cwd: Working directory for assistant commands.
        profile_path: Profile file path passed to the skill prompt.
        execution_mode: Execution mode selector (currently skill-native only).
        runtime_skill_path: Path to runtime ``SKILL.md``.
        top_level_containers: Whether top-level folders are containers.
        intake_filter: Intake filtering mode.
        folder_classifier: Optional intake classifier.
        progress_callback: Optional progress event sink.
        parallelism: Number of concurrent deal workers.

    Returns:
        Scored assessments sorted by descending weighted score.
    """

    if execution_mode != EXECUTION_MODE_SKILL_NATIVE:
        raise ValueError(f"Unsupported execution mode: {execution_mode}")
    if parallelism < 1:
        raise ValueError("parallelism must be >= 1")

    _emit_progress(
        progress_callback,
        "deal_discovery_started",
        {
            "deals_root": str(deals_root),
            "since_days": since_days,
            "intake_filter": intake_filter,
            "top_level_containers": top_level_containers,
        },
    )
    deals = discover_recent_deals(
        deals_root=deals_root,
        since_days=since_days,
        top_level_containers=top_level_containers,
        intake_filter=intake_filter,
        folder_classifier=folder_classifier,
        classifier_cache_path=cwd / ".angelcopilot" / "intake_classifier_cache.json",
    )
    _emit_progress(
        progress_callback,
        "deal_discovery_completed",
        {
            "deals_root": str(deals_root),
            "since_days": since_days,
            "total_deals": len(deals),
            "intake_filter": intake_filter,
            "top_level_containers": top_level_containers,
        },
    )
    resolved_profile_path = (
        profile_path.expanduser().resolve() if profile_path is not None else Path(".angelcopilot/profile.md").resolve()
    )
    resolved_runtime_skill_path = runtime_skill_path.expanduser().resolve()
    _emit_progress(
        progress_callback,
        "batch_started",
        {
            "deals_root": str(deals_root),
            "since_days": since_days,
            "total_deals": len(deals),
            "execution_mode": execution_mode,
            "parallelism": parallelism,
        },
    )

    prepared_tasks = _prepare_deal_tasks(
        deals=deals,
        profile_path=resolved_profile_path,
        runtime_skill_path=resolved_runtime_skill_path,
        progress_callback=progress_callback,
    )
    assessments = _run_deal_assessments(
        prepared_tasks=prepared_tasks,
        profile=profile,
        runner=runner,
        cwd=cwd,
        progress_callback=progress_callback,
        parallelism=parallelism,
    )
    if prepared_tasks and not assessments:
        raise RuntimeError(
            f"No assessments completed successfully for {len(prepared_tasks)} prepared deal(s). "
            "See preceding deal_failed logs for assistant or payload errors."
        )

    sorted_assessments = sorted(assessments, key=lambda item: ({"INVEST": 0, "WAIT": 1, "PASS": 2}.get(item.verdict, 3), -(item.weighted_score or 0)))
    _emit_progress(
        progress_callback,
        "batch_completed",
        {
            "total_deals": len(deals),
            "scored_deals": len(sorted_assessments),
            "attention_deals": sum(1 for item in sorted_assessments if item.attention_flag),
        },
    )
    return sorted_assessments


def _run_deal_assessments(
    prepared_tasks: list[PreparedDealTask],
    profile: InvestorProfile,
    runner,
    cwd: Path,
    progress_callback: ProgressCallback | None,
    parallelism: int,
) -> list[AssessmentResult]:
    """Execute prepared deals sequentially or via thread pool workers.
    
    Args:
        prepared_tasks: Value for ``prepared_tasks``.
        profile: Value for ``profile``.
        runner: Value for ``runner``.
        cwd: Value for ``cwd``.
        progress_callback: Value for ``progress_callback``.
        parallelism: Value for ``parallelism``.
    
    Returns:
        list[AssessmentResult]: Value returned by this function.
    """

    assessments: list[AssessmentResult] = []
    if parallelism == 1 or len(prepared_tasks) <= 1:
        for prepared_task in prepared_tasks:
            scored = _assess_prepared_deal(
                prepared_task=prepared_task,
                profile=profile,
                runner=runner,
                cwd=cwd,
                progress_callback=progress_callback,
            )
            if scored is not None:
                assessments.append(scored)
        return assessments

    max_workers = min(parallelism, len(prepared_tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _assess_prepared_deal,
                prepared_task=prepared_task,
                profile=profile,
                runner=runner,
                cwd=cwd,
                progress_callback=progress_callback,
            ): prepared_task
            for prepared_task in prepared_tasks
        }
        for future in as_completed(futures):
            prepared_task = futures[future]
            try:
                scored = future.result()
            except Exception as exc:  # noqa: BLE001
                _emit_progress(
                    progress_callback,
                    "deal_failed",
                    {
                        "deal_id": prepared_task.deal.deal_id,
                        "index": prepared_task.index,
                        "total": prepared_task.total,
                        "reason": "worker_failed",
                        "error": str(exc),
                    },
                )
                continue
            if scored is not None:
                assessments.append(scored)
    return assessments


def _prepare_deal_tasks(
    deals: list[DealInput],
    profile_path: Path,
    runtime_skill_path: Path,
    progress_callback: ProgressCallback | None,
) -> list[PreparedDealTask]:
    """Prepare isolated workspaces and prompts for each discovered deal.
    
    Args:
        deals: Value for ``deals``.
        profile_path: Value for ``profile_path``.
        runtime_skill_path: Value for ``runtime_skill_path``.
        progress_callback: Value for ``progress_callback``.
    
    Returns:
        list[PreparedDealTask]: Value returned by this function.
    """

    prepared_tasks: list[PreparedDealTask] = []
    total = len(deals)
    for index, deal in enumerate(deals, start=1):
        _emit_progress(
            progress_callback,
            "deal_started",
            {
                "deal_id": deal.deal_id,
                "deal_path": str(deal.path),
                "index": index,
                "total": total,
                "supported_files": len(deal.supported_files),
            },
        )
        workspace = prepare_deal_workspace(
            deal_path=deal.path,
            supported_files=deal.supported_files,
            deal_id=deal.deal_id,
        )
        if not workspace.files_used:
            _emit_progress(
                progress_callback,
                "deal_skipped",
                {
                    "deal_id": deal.deal_id,
                    "index": index,
                    "total": total,
                    "reason": "no_prepared_files",
                },
            )
            cleanup_prepared_workspace(workspace)
            continue

        prompt = build_skill_native_prompt(
            deal_id=deal.deal_id,
            deal_path=workspace.workspace_path / "docs",
            profile_path=profile_path,
            runtime_skill_path=runtime_skill_path,
        )
        prepared_tasks.append(
            PreparedDealTask(
                deal=deal,
                index=index,
                total=total,
                workspace=workspace,
                prompt=prompt,
            )
        )
        _emit_progress(
            progress_callback,
            "deal_prepared",
            {
                "deal_id": deal.deal_id,
                "index": index,
                "total": total,
                "files_used": len(workspace.files_used),
                "warnings": len(workspace.warnings),
            },
        )
    return prepared_tasks


def _assess_prepared_deal(
    prepared_task: PreparedDealTask,
    profile: InvestorProfile,
    runner,
    cwd: Path,
    progress_callback: ProgressCallback | None,
) -> AssessmentResult | None:
    """Execute one prepared deal assessment and return scored output.
    
    Args:
        prepared_task: Value for ``prepared_task``.
        profile: Value for ``profile``.
        runner: Value for ``runner``.
        cwd: Value for ``cwd``.
        progress_callback: Value for ``progress_callback``.
    
    Returns:
        AssessmentResult | None: Value returned by this function.
    """

    deal = prepared_task.deal
    prepared_workspace = prepared_task.workspace
    try:
        _emit_progress(
            progress_callback,
            "deal_assessment_started",
            {
                "deal_id": deal.deal_id,
                "index": prepared_task.index,
                "total": prepared_task.total,
            },
        )
        payload, error_message = _run_with_retry(runner=runner, prompt=prepared_task.prompt, cwd=cwd)
        if payload is None:
            _emit_progress(
                progress_callback,
                "deal_failed",
                {
                    "deal_id": deal.deal_id,
                    "index": prepared_task.index,
                    "total": prepared_task.total,
                    "reason": "assistant_failed",
                    "error": error_message or "",
                },
            )
            return None

        try:
            normalized_payload = validate_assessment_payload(payload)
        except Exception as exc:  # noqa: BLE001
            _emit_progress(
                progress_callback,
                "deal_failed",
                {
                    "deal_id": deal.deal_id,
                    "index": prepared_task.index,
                    "total": prepared_task.total,
                    "reason": "payload_validation_failed",
                    "error": str(exc),
                },
            )
            return None

        try:
            scored = _build_scored_assessment(
                deal_id=deal.deal_id,
                normalized_payload=normalized_payload,
                profile=profile,
                evidence_sources=prepared_workspace.files_used,
                extraction_warnings=prepared_workspace.warnings,
            )
        except Exception as exc:  # noqa: BLE001
            _emit_progress(progress_callback, "deal_failed", {"deal_id": deal.deal_id,
                "index": prepared_task.index, "total": prepared_task.total,
                "reason": "scoring_failed", "error": str(exc)})
            return None
        _emit_progress(
            progress_callback,
            "deal_completed",
            {
                "deal_id": scored.deal_id,
                "company_name": scored.company_name,
                "index": prepared_task.index,
                "total": prepared_task.total,
                "files_used": len(prepared_workspace.files_used),
                "weighted_score": scored.weighted_score,
                "verdict": scored.verdict,
                "attention_flag": scored.attention_flag,
            },
        )
        return scored
    finally:
        cleanup_prepared_workspace(prepared_workspace)


def _build_scored_assessment(
    deal_id: str,
    normalized_payload: dict[str, object],
    profile: InvestorProfile,
    evidence_sources: list[str],
    extraction_warnings: list[str],
) -> AssessmentResult:
    """Construct normalized `AssessmentResult` and apply scoring rules.
    
    Args:
        deal_id: Value for ``deal_id``.
        normalized_payload: Value for ``normalized_payload``.
        profile: Value for ``profile``.
        evidence_sources: Value for ``evidence_sources``.
        extraction_warnings: Value for ``extraction_warnings``.
    
    Returns:
        AssessmentResult: Value returned by this function.
    """

    allowed = {f.name for f in fields(AssessmentResult)}
    data = {k: v for k, v in normalized_payload.items() if k in allowed}
    data.setdefault("deal_id", deal_id)
    for key, default in {"risk_flags": [], "sectors": [], "geographies": [], "rationale": ""}.items():
        data.setdefault(key, default)
    data.update(evidence_sources=list(evidence_sources), extraction_warnings=list(extraction_warnings))
    return apply_scoring_rules(AssessmentResult(**data), profile)


def build_skill_native_prompt(
    deal_id: str,
    deal_path: Path,
    profile_path: Path,
    runtime_skill_path: Path = DEFAULT_RUNTIME_SKILL_PATH,
) -> str:
    """Build the native skill invocation prompt with strict JSON schema contract.

    Args:
        deal_id: Stable deal identifier.
        deal_path: Prepared deal docs path consumed by the skill.
        profile_path: Investor profile path for personalization.
        runtime_skill_path: Path to installed runtime ``SKILL.md``.

    Returns:
        Prompt text passed to the assistant CLI.
    """

    response_schema = _response_schema_template()
    return (
        f"Deal ID: {deal_id}\n"
        f"[$angel-copilot]({runtime_skill_path}) assess the deal in {deal_path}\n"
        f"Use investor profile from {profile_path}.\n"
        "Run the skill workflow as a standalone single-deal assessment.\n"
        "Do not re-implement or summarize the skill rules in a custom rubric.\n"
        "Read files directly from the deal folder path provided.\n"
        "Use schema_version 2. Give a personal actionable judgment at reviewed terms; never map the score to a verdict.\n"
        "INVEST means a normal cheque now; WAIT and PASS mean no cheque recommended. Do not display a numeric zero-cheque amount. No exploratory/starter cheque language.\n"
        "Use only the investor profile's normal ticket range. Do not source cheque sizes from rubric defaults; if the profile has no complete range, do not recommend or model a cheque.\n"
        "Keep category drivers <=25 words and category notes about 40-70 words.\n"
        "Rank up to five diligence issues and up to three primary founder questions by decision impact.\n"
        "Each ask must link to an issue and request evidence when assurance would not verify the claim.\n"
        "Route optional asks to founder, syndicate_lead, counsel or customer. Three is a ceiling, not a quota.\n"
        "Model no follow-ons with explicit fees, carry, FX, post-money ownership and dilution.\n"
        "Use loss/bear/base/upside scenarios with fractional probabilities summing to 1. Leave assumptions and scenarios empty if unknowable.\n"
        "Return-assumption currency must equal the profile currency (default EUR); FX must be explicit across currencies.\n"
        "Report missing scores as null and missing process work honestly. Do not invent executed contracts or verification.\n"
        "After completing the assessment, output strict JSON only.\n"
        f"Required JSON schema: {response_schema}\n"
        f"If the assessed company name differs from folder name, keep deal_id as '{deal_id}'.\n"
        "No markdown fences and no extra prose outside JSON.\n"
    )


def _response_schema_template() -> str:
    """Return the expected JSON schema example used in assistant prompts.
    
    Args:
        None.
    
    Returns:
        str: Value returned by this function.
    """

    example = {
        "schema_version": 2, "deal_id": "...", "company_name": "...",
        "category_scores": {k: None for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "category_rationales": {k: "Evidence and judgment; identify score ceiling." for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "category_drivers": {k: "Short decision driver" for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "category_confidence": {k: "unknown" for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "deal_snapshot": {"product": "...", "customer": "...", "stage": "...", "instrument": "...", "terms": "...", "market_timing": "..."},
        "decision": {"verdict": "WAIT", "reason": "...", "assessment_summary": {"investment_case": "...", "supporting_evidence": "...", "counterarguments": "...", "decision_logic": "..."}, "economics": "unknown", "evidence": "incomplete", "fit": "unknown", "suggested_amount": 0,
                     "sizing_reason": "No allocation until material evidence is resolved", "next_action": "...", "minimum_ticket": 0},
        "diligence_issues": [{"id": "I1", "priority": 1, "status": "blocker", "evidence_state": "unknown", "title": "...", "finding": "...", "decision_impact": "...", "evidence_needed": "...", "reconsideration_condition": "...", "source_ids": ["D1"]}],
        "questions": [{"question": "...", "priority": 1, "audience": "founder", "optional": False, "issue_id": "I1", "evidence_requested": "..."}],
        "return_assumptions": {"currency": "EUR", "valuation_currency": "EUR", "fx_rate": 1, "entry_valuation": 20000000,
                               "entry_valuation_basis": "post_money", "exit_value_basis": "distributable_equity", "fee_rate": .04, "fee_treatment": "deducted",
                               "carry_rate": .20, "carry_basis": "deployed_capital", "dilution_rate": .45, "follow_on": False, "years": 8,
                               "ownership_note": "SAFE cap-based ownership is illustrative; verify conversion and senior claims", "exclusions": "Taxes and future additional expenses excluded"},
        "return_scenarios": [{"kind": k, "scenario": k.title(), "exit_value": v, "probability": prob, "rationale": "Company-specific outcome assumptions"}
                             for k, v, prob in [("loss", 0, .4), ("bear", 5000000, .2), ("base", 200000000, .3), ("upside", 1000000000, .1)]],
        "risk_flags": [], "sectors": [], "geographies": [], "rationale": "",
        "citations": [{"id": "D1", "source": "...", "date": "YYYY-MM-DD", "note": "..."}],
        "web_sweep_sources": [{"id": "W1", "source": "...", "date": "YYYY-MM-DD", "date_accessed": "YYYY-MM-DD", "url": "https://...", "note": "..."}],
        "assessment_limitations": "...",
        "assessment_process": {"used_full_rubric": True, "performed_web_sweep": True, "reconciled_docs_with_web": True, "built_return_model": True, "notes": "Actual completion only"},
    }
    return json.dumps(example)


def build_default_run_id() -> str:
    """Build a timestamped run id suitable for output folder names.
    
    Returns:
        Run identifier in local timezone.
    
    Args:
        None.
    """

    local_now = datetime.now().astimezone()
    zone = (local_now.strftime("%Z") or "LOCAL").replace("/", "-").replace(" ", "_")
    return local_now.strftime(f"run_%Y_%B_%d_%H-%M-%S_{zone}")


def _run_with_retry(runner, prompt: str, cwd: Path) -> tuple[dict[str, object] | None, str | None]:
    """Run assistant once with a strict-JSON retry fallback on failure.
    
    Args:
        runner: Value for ``runner``.
        prompt: Value for ``prompt``.
        cwd: Value for ``cwd``.
    
    Returns:
        tuple[dict[str, object] | None, str | None]: Value returned by this function.
    """

    first_error: str | None = None
    try:
        return runner.run_assessment(prompt, cwd=cwd), None
    except Exception as exc:  # noqa: BLE001
        first_error = str(exc)
        retry_prompt = (
            f"{prompt}\n\n"
            "RETRY INSTRUCTION: Return strict JSON only. Do not include markdown fences or extra text."
        )
        try:
            return runner.run_assessment(retry_prompt, cwd=cwd), None
        except Exception as retry_exc:  # noqa: BLE001
            second_error = str(retry_exc)
            return None, f"first_attempt={first_error}; retry_attempt={second_error}"


def _infer_dilution_assumption(return_scenarios: list[dict[str, object]]) -> str:
    """Infer dilution inclusion summary from return-scenario fields.
    
    Args:
        return_scenarios: Value for ``return_scenarios``.
    
    Returns:
        str: Value returned by this function.
    """

    observed: list[bool] = []
    for scenario in return_scenarios:
        if "includes_dilution" in scenario:
            value = scenario["includes_dilution"]
        elif "dilution_included" in scenario:
            value = scenario["dilution_included"]
        else:
            continue

        parsed = _parse_bool_or_none(value)
        if parsed is not None:
            observed.append(parsed)

    if not observed:
        return "Not recorded; do not infer dilution from narrative."
    if all(observed):
        return "Included."
    if not any(observed):
        return "Excluded."
    return "Mixed by scenario."


def _emit_progress(
    progress_callback: ProgressCallback | None,
    event: str,
    payload: dict[str, object],
) -> None:
    """Emit pipeline progress event when callback is configured.
    
    Args:
        progress_callback: Value for ``progress_callback``.
        event: Value for ``event``.
        payload: Value for ``payload``.
    
    Returns:
        None.
    """

    if progress_callback is None:
        return
    progress_callback(event, payload)


def _parse_bool_or_none(value: object) -> bool | None:
    """Parse bool or none.
    
    Args:
        value: Value for ``value``.
    
    Returns:
        bool | None: Value returned by this function.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "included"}:
            return True
        if normalized in {"false", "no", "excluded"}:
            return False
    return None
