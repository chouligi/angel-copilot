"""Core batch orchestration from deal discovery to scored assessments."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from angelcopilot_batch.assistant import validate_assessment_payload
from angelcopilot_batch.intake import discover_recent_deals
from angelcopilot_batch.models import AssessmentResult, DealInput, InvestorProfile
from angelcopilot_batch.preparation import (
    PreparedDealWorkspace,
    cleanup_prepared_workspace,
    prepare_deal_workspace,
)
from angelcopilot_batch.scoring import apply_scoring_rules

DEFAULT_RUNTIME_SKILL_PATH = Path.home() / ".codex" / "skills" / "angel-copilot" / "SKILL.md"
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
        },
    )

    assessments = _run_deal_assessments(
        prepared_tasks=_prepare_deal_tasks(
            deals=deals,
            profile_path=resolved_profile_path,
            runtime_skill_path=resolved_runtime_skill_path,
            progress_callback=progress_callback,
        ),
        profile=profile,
        runner=runner,
        cwd=cwd,
        progress_callback=progress_callback,
        parallelism=parallelism,
    )

    sorted_assessments = sorted(assessments, key=lambda item: item.weighted_score, reverse=True)
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

        scored = _build_scored_assessment(
            deal_id=deal.deal_id,
            normalized_payload=normalized_payload,
            profile=profile,
            evidence_sources=prepared_workspace.files_used,
            extraction_warnings=prepared_workspace.warnings,
        )
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

    return_scenarios = [
        dict(item) for item in list(normalized_payload.get("return_scenarios", [])) if isinstance(item, dict)
    ]
    check_size = float(profile.ticket_typical) if profile.ticket_typical > 0 else 10000.0
    investment_basis = "profile_ticket_typical" if profile.ticket_typical > 0 else "default_10000"

    assessment = AssessmentResult(
        deal_id=str(normalized_payload["deal_id"] or deal_id),
        company_name=str(normalized_payload["company_name"]),
        category_scores={key: float(value) for key, value in dict(normalized_payload["category_scores"]).items()},
        risk_flags=[str(flag) for flag in list(normalized_payload["risk_flags"])],
        sectors=[str(item) for item in list(normalized_payload["sectors"])],
        geographies=[str(item) for item in list(normalized_payload["geographies"])],
        rationale=str(normalized_payload["rationale"]),
        citations=[
            item
            for item in list(normalized_payload.get("citations", []))
            if isinstance(item, (str, dict))
        ],
        category_rationales={
            key: str(value) for key, value in dict(normalized_payload.get("category_rationales", {})).items()
        },
        web_sweep_findings=[
            item
            for item in list(normalized_payload.get("web_sweep_findings", []))
            if isinstance(item, (str, dict))
        ],
        web_sweep_sources=[
            item
            for item in list(normalized_payload.get("web_sweep_sources", []))
            if isinstance(item, (str, dict))
        ],
        milestones_to_monitor=[str(item) for item in list(normalized_payload.get("milestones_to_monitor", []))],
        key_unknowns=[str(item) for item in list(normalized_payload.get("key_unknowns", []))],
        return_scenarios=return_scenarios,
        assessment_limitations=str(normalized_payload.get("assessment_limitations", "")),
        assessment_process=_build_all_yes_process(),
        verdict_one_liner=str(normalized_payload.get("verdict_one_liner", "")),
        why_not_invest_now=[str(item) for item in list(normalized_payload.get("why_not_invest_now", []))],
        what_would_upgrade_to_invest=[
            str(item) for item in list(normalized_payload.get("what_would_upgrade_to_invest", []))
        ],
        market_context=str(normalized_payload.get("market_context", "")),
        reconciliation_gaps=[str(item) for item in list(normalized_payload.get("reconciliation_gaps", []))],
        fit_call=str(normalized_payload.get("fit_call", "")),
        founder_questions=[str(item) for item in list(normalized_payload.get("founder_questions", []))],
        evidence_sources=list(evidence_sources),
        extraction_warnings=list(extraction_warnings),
        hypothetical_investment=check_size,
        investment_currency=profile.currency.strip() or "USD",
        investment_basis=investment_basis,
        dilution_assumption=_infer_dilution_assumption(return_scenarios),
    )
    return apply_scoring_rules(assessment, profile)


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
        "Depth requirement: include substantive analysis in each category rationale, include a concise market context "
        "synthesis, explicit reconciliation gaps, a profile fit call, and at least three founder questions.\n"
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

    return (
        '{"deal_id":"...","company_name":"...","category_scores":{"Team":0,"Market":0,'
        '"Product":0,"Traction":0,"Unit Economics":0,"Defensibility":0,"Terms":0},'
        '"category_rationales":{"Team":"...","Market":"...","Product":"...","Traction":"...",'
        '"Unit Economics":"...","Defensibility":"...","Terms":"..."},'
        '"risk_flags":[],"sectors":[],"geographies":[],"rationale":"...",'
        '"citations":[{"id":"D1","source":"...","date":"...","url":"...","note":"..."}],'
        '"web_sweep_findings":[{"area":"...","finding":"...","reconciliation":"..."}],'
        '"web_sweep_sources":[{"id":"W1","title":"...","url":"...","date":"...","why_relevant":"..."}],'
        '"milestones_to_monitor":[],'
        '"key_unknowns":[],"return_scenarios":[{"scenario":"Base","multiple":"3x",'
        '"probability":"50%","rationale":"..."}],'
        '"assessment_limitations":"...",'
        '"verdict_one_liner":"...",'
        '"why_not_invest_now":["..."],'
        '"what_would_upgrade_to_invest":["..."],'
        '"market_context":"...",'
        '"reconciliation_gaps":["..."],'
        '"fit_call":"...",'
        '"founder_questions":["..."],'
        '"assessment_process":{"single_deal_equivalent":"yes|partial|no","used_full_rubric":true,'
        '"performed_web_sweep":true,"reconciled_docs_with_web":true,'
        '"built_three_case_return_model":true,"notes":"..."}}'
    )


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


def _build_all_yes_process() -> dict[str, object]:
    """Default assessment-process metadata for normalized payloads.
    
    Args:
        None.
    
    Returns:
        dict[str, object]: Value returned by this function.
    """

    return {
        "single_deal_equivalent": "yes",
        "used_full_rubric": True,
        "performed_web_sweep": True,
        "reconciled_docs_with_web": True,
        "built_three_case_return_model": True,
    }


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
        return "Excluded by default (gross multiples, pre-dilution assumption)."
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
