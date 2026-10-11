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
from angelcopilot.scoring import apply_scoring_rules, assessment_sort_key

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
        Assessments ranked by recommended action, evidence strength and score.
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

    sorted_assessments = sorted(assessments, key=assessment_sort_key)
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
                "recommendation": scored.verdict,
                "priority": scored.pursuit_priority,
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
        "Write deal_snapshot.company_summary as one plain-language paragraph explaining what the company does: the product, customer, problem, how it works, revenue model and current product status where supported by the documents. Attribute reported claims and cite sources. State material gaps without inventing details; keep investment judgments in assessment_summary.\n"
        "Use schema_version 4 and give exactly one action recommendation in decision.verdict: INVEST, PURSUE, WAIT or PASS. INVEST means a normal cheque now after all commitment checks pass. PURSUE means prioritize diligence now but no cheque yet; it requires a weighted score of at least 3.5/5 and a specific reason to spend diligence time. WAIT means do not prioritize diligence now; name the evidence, milestone or event that would justify reopening. PASS means stop work at these terms or for this investor. Do not use WAIT as a synonym for incomplete diligence when the deal is worth pursuing.\n"
        "Set decision.priority to high for INVEST, high or medium for PURSUE, any level for WAIT, and low for PASS.\n"
        "INVEST requires sufficient stage-appropriate evidence, attractive net economics supported by a return summary or sensitivity, compatible investor constraints, and a justified cheque within the profile's permitted range, subscription minimum and known budget. Apply any configured base-case return hurdle. Fatal issues, unattractive economics or incompatible fit mean PASS. Resolve investment-critical blockers and hard risks before INVEST; if the opportunity merits resolving them, recommend PURSUE. Missing private evidence, a personal cheque range or a probability return model does not automatically lower the score or make a deal WAIT. Distinguish verification work, accepted venture risk and future business milestones; every issue needs resolution_type and resolution_horizon. Ordinary unsigned investor subscription paperwork is not itself a blocker.\n"
        "Score all seven factors provisionally when the available evidence, stage and business model give a reasonable basis. Early deal materials are expected to be incomplete: do not leave a score null solely because diligence metrics are absent, and do not assign an arbitrary low score for missing disclosure. Use the business model and stage-appropriate signals, state assumptions and what could change the rating, and set evidence strength low when support is mostly reported or incomplete. Lower a score only for a substantive risk supported by evidence or the business model. Reserve evidence strength unknown and a null score for the rare case with no responsible basis for any provisional judgment. Evidence strength is separate from company quality.\n"
        "The JSON template's example values are structural placeholders, not assessment defaults. Replace its null score placeholders with provisional numeric judgments wherever the factor can be assessed from the stage, business model or available evidence.\n"
        "Use economic_ranges for exit-value sensitivities without a cheque or probabilities when supportable; use {} when unsupported. Distinguish reported terms from assumptions. Do not add a conditional investment view.\n"
        "For INVEST, provide a positive cheque amount within the complete investor profile range. For PURSUE, WAIT and PASS, suggested_amount must be numeric 0 and no cheque is recommended. Do not display a numeric zero-cheque amount. No exploratory/starter cheque language. Explain justified departures from the typical ticket within the permitted range.\n"
        "Keep category drivers <=25 words and category notes about 40-70 words.\n"
        "Rank up to five diligence issues and up to three primary founder questions by decision impact.\n"
        "Each ask must link to an issue and request evidence when assurance would not verify the claim.\n"
        "Route optional asks to founder, syndicate_lead, counsel or customer. Three is a ceiling, not a quota.\n"
        "Model no follow-ons with explicit fees, carry, FX, post-money ownership and dilution.\n"
        "Use loss/bear/base/upside scenarios with fractional probabilities summing to 1. Leave assumptions and scenarios empty if unknowable.\n"
        "Return-assumption currency must equal the profile currency (default EUR); FX must be explicit across currencies.\n"
        "Report a null score only for a genuinely unassessable factor, and explain the reason. Report missing process work honestly. Do not invent executed contracts or verification.\n"
        "Decision enum contract: decision.economics must be exactly one of `attractive`, `unattractive`, `unknown`; "
        "decision.fit must be exactly one of `compatible`, `incompatible`, `unknown`; "
        "decision.evidence must be exactly `sufficient` or `incomplete`. These fields are classifications, "
        "not prose. Never put a sentence or a category name in these fields.\n"
        "decision.suggested_amount must be a JSON number, never text. For PURSUE, WAIT or PASS it must be numeric 0; "
        "for INVEST it must be a positive number within the profile's allowed ticket range.\n"
        "Each diligence issue status must be exactly fatal/blocker/risk/resolved and evidence_state must be "
        "exactly verified/reported/unknown/conflicting. Do not use other synonyms.\n"
        "The four decision.assessment_summary fields must each contain 25–80 words and total 140–260 words.\n"
        "return_assumptions must always be a JSON object. Use {} when return scenarios cannot be modeled; "
        "never use a string, array, or null for it. If assumptions are provided, return_scenarios must also be provided.\n"
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
        "schema_version": 4,
        "economic_ranges": {}, "deal_id": "...", "company_name": "...",
        "category_scores": {k: None for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "category_rationales": {k: "Evidence and judgment; identify score ceiling." for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "category_drivers": {k: "Short decision driver" for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "category_confidence": {k: "unknown" for k in ("Team", "Market", "Product", "Traction", "Unit Economics", "Defensibility", "Terms")},
        "deal_snapshot": {"company_summary": "...", "product": "...", "customer": "...", "stage": "...", "instrument": "...", "terms": "...", "market_timing": "..."},
        "decision": {"verdict": "WAIT", "priority": "medium", "reason": "...", "assessment_summary": {"investment_case": "...", "supporting_evidence": "...", "counterarguments": "...", "decision_logic": "..."}, "economics": "unknown", "evidence": "incomplete", "fit": "unknown", "suggested_amount": 0,
                     "sizing_reason": "No allocation until material evidence is resolved", "next_action": "...", "minimum_ticket": 0},
        "diligence_issues": [{"id": "I1", "priority": 1, "status": "blocker", "evidence_state": "unknown", "title": "...", "finding": "...", "decision_impact": "...", "evidence_needed": "...", "reconsideration_condition": "...", "source_ids": ["D1"], "resolution_type": "document", "resolution_horizon": "During initial diligence"}],
        "questions": [{"question": "...", "priority": 1, "audience": "founder", "optional": False, "issue_id": "I1", "evidence_requested": "..."}],
        "return_assumptions": {"currency": "EUR", "valuation_currency": "EUR", "fx_rate": 1, "entry_valuation": 20000000,
                               "entry_valuation_basis": "post_money", "exit_value_basis": "distributable_equity", "fee_rate": .04, "fee_treatment": "deducted",
                               "carry_rate": .20, "carry_basis": "deployed_capital", "dilution_rate": .45, "follow_on": False, "years": 8,
                               "ownership_note": "SAFE cap-based ownership is illustrative; verify conversion and senior claims", "exclusions": "Taxes and future additional expenses excluded"},
        "return_scenarios": [{"kind": k, "scenario": k.title(), "exit_value": v, "probability": prob, "rationale": "Company-specific outcome assumptions"}
                             for k, v, prob in [("loss", 0, .4), ("bear", 5000000, .2), ("base", 200000000, .3), ("upside", 1000000000, .1)]],
        "risk_flags": [], "sectors": [], "geographies": [], "rationale": "",
        "citations": [{"id": "D1", "source": "...", "date": "YYYY-MM-DD", "date_accessed": None, "url": None, "note": "..."}],
        "web_sweep_sources": [{"id": "W1", "source": "...", "date": "YYYY-MM-DD", "date_accessed": "YYYY-MM-DD", "url": "https://...", "note": "..."}],
        "evidence_sources": [], "extraction_warnings": [],
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
    """Run assistant up to three times, feeding each failure into the next prompt.
    
    Args:
        runner: Value for ``runner``.
        prompt: Value for ``prompt``.
        cwd: Value for ``cwd``.
    
    Returns:
        tuple[dict[str, object] | None, str | None]: Value returned by this function.
    """

    errors: list[str] = []
    current_prompt = prompt
    for attempt in range(1, 4):
        try:
            payload = runner.run_assessment(current_prompt, cwd=cwd)
            if payload.get("schema_version") != 4:
                raise ValueError(f"New assessments must use schema_version 4; received {payload.get('schema_version')}")
            return payload, None
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            errors.append(error)
            if attempt < 3:
                prior_errors = "\n".join(f"- {item}" for item in errors)
                current_prompt = (
                    f"{prompt}\n\n"
                    f"RETRY {attempt}/2 VALIDATION FEEDBACK. All prior validation errors must be fixed together:\n"
                    f"{prior_errors}\n"
                    "Recheck the entire response against the schema, not only the latest error. In particular, "
                    "decision.economics is one of attractive/unattractive/unknown; decision.fit is one of "
                    "compatible/incompatible/unknown; decision.evidence is sufficient/incomplete; suggested_amount "
                    "is numeric and exactly 0 for WAIT/PASS; issue status and evidence_state must use their listed "
                    "enums; summary word limits still apply; return_assumptions is always an object (use {} when "
                    "unavailable). Do not include markdown fences or extra text."
                )

    return None, "; ".join(
        f"attempt_{index}={error}" for index, error in enumerate(errors, start=1)
    )


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
