from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from angelcopilot_batch.assistant import validate_assessment_payload
from angelcopilot_batch.intake import discover_recent_deals
from angelcopilot_batch.models import AssessmentResult, InvestorProfile
from angelcopilot_batch.preparation import cleanup_prepared_workspace, prepare_deal_workspace
from angelcopilot_batch.scoring import apply_scoring_rules

DEFAULT_RUNTIME_SKILL_PATH = Path.home() / ".codex" / "skills" / "angel-copilot" / "SKILL.md"
EXECUTION_MODE_SKILL_NATIVE = "skill_native"
ProgressCallback = Callable[[str, dict[str, object]], None]


def run_batch_assessment(
    deals_root: Path,
    since_days: int,
    profile: InvestorProfile,
    runner,
    cwd: Path,
    profile_path: Path | None = None,
    execution_mode: str = EXECUTION_MODE_SKILL_NATIVE,
    runtime_skill_path: Path = DEFAULT_RUNTIME_SKILL_PATH,
    top_level_containers: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> list[AssessmentResult]:
    if execution_mode != EXECUTION_MODE_SKILL_NATIVE:
        raise ValueError(f"Unsupported execution mode: {execution_mode}")

    deals = discover_recent_deals(
        deals_root=deals_root,
        since_days=since_days,
        top_level_containers=top_level_containers,
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

    assessments: list[AssessmentResult] = []
    for index, deal in enumerate(deals, start=1):
        _emit_progress(
            progress_callback,
            "deal_started",
            {
                "deal_id": deal.deal_id,
                "deal_path": str(deal.path),
                "index": index,
                "total": len(deals),
                "supported_files": len(deal.supported_files),
            },
        )
        prepared_workspace = prepare_deal_workspace(
            deal_path=deal.path,
            supported_files=deal.supported_files,
            deal_id=deal.deal_id,
        )
        if not prepared_workspace.files_used:
            _emit_progress(
                progress_callback,
                "deal_skipped",
                {
                    "deal_id": deal.deal_id,
                    "index": index,
                    "total": len(deals),
                    "reason": "no_prepared_files",
                },
            )
            cleanup_prepared_workspace(prepared_workspace)
            continue
        prompt = build_skill_native_prompt(
            deal_id=deal.deal_id,
            deal_path=prepared_workspace.workspace_path / "docs",
            profile_path=resolved_profile_path,
            runtime_skill_path=resolved_runtime_skill_path,
        )

        payload, error_message = _run_with_retry(runner=runner, prompt=prompt, cwd=cwd)
        if payload is None:
            _emit_progress(
                progress_callback,
                "deal_failed",
                {
                    "deal_id": deal.deal_id,
                    "index": index,
                    "total": len(deals),
                    "reason": "assistant_failed",
                    "error": error_message or "",
                },
            )
            cleanup_prepared_workspace(prepared_workspace)
            continue

        try:
            normalized_payload = validate_assessment_payload(payload)
        except Exception as exc:  # noqa: BLE001
            _emit_progress(
                progress_callback,
                "deal_failed",
                {
                    "deal_id": deal.deal_id,
                    "index": index,
                    "total": len(deals),
                    "reason": "payload_validation_failed",
                    "error": str(exc),
                },
            )
            cleanup_prepared_workspace(prepared_workspace)
            continue
        return_scenarios = [
            dict(item) for item in list(normalized_payload.get("return_scenarios", [])) if isinstance(item, dict)
        ]
        check_size = float(profile.ticket_typical) if profile.ticket_typical > 0 else 10000.0
        investment_basis = "profile_ticket_typical" if profile.ticket_typical > 0 else "default_10000"

        assessment = AssessmentResult(
            deal_id=str(normalized_payload["deal_id"] or deal.deal_id),
            company_name=str(normalized_payload["company_name"]),
            category_scores={
                key: float(value) for key, value in dict(normalized_payload["category_scores"]).items()
            },
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
            milestones_to_monitor=[
                str(item) for item in list(normalized_payload.get("milestones_to_monitor", []))
            ],
            key_unknowns=[str(item) for item in list(normalized_payload.get("key_unknowns", []))],
            return_scenarios=return_scenarios,
            assessment_limitations=str(normalized_payload.get("assessment_limitations", "")),
            assessment_process=_build_all_yes_process(),
            verdict_one_liner=str(normalized_payload.get("verdict_one_liner", "")),
            why_not_invest_now=[str(item) for item in list(normalized_payload.get("why_not_invest_now", []))],
            what_would_upgrade_to_invest=[
                str(item) for item in list(normalized_payload.get("what_would_upgrade_to_invest", []))
            ],
            evidence_sources=list(prepared_workspace.files_used),
            extraction_warnings=list(prepared_workspace.warnings),
            hypothetical_investment=check_size,
            investment_currency=profile.currency.strip() or "USD",
            investment_basis=investment_basis,
            dilution_assumption=_infer_dilution_assumption(return_scenarios),
        )
        scored = apply_scoring_rules(assessment, profile)
        assessments.append(scored)
        cleanup_prepared_workspace(prepared_workspace)
        _emit_progress(
            progress_callback,
            "deal_completed",
            {
                "deal_id": scored.deal_id,
                "company_name": scored.company_name,
                "index": index,
                "total": len(deals),
                "files_used": len(prepared_workspace.files_used),
                "weighted_score": scored.weighted_score,
                "verdict": scored.verdict,
                "attention_flag": scored.attention_flag,
            },
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


def build_skill_native_prompt(
    deal_id: str,
    deal_path: Path,
    profile_path: Path,
    runtime_skill_path: Path = DEFAULT_RUNTIME_SKILL_PATH,
) -> str:
    response_schema = _response_schema_template()
    return (
        f"Deal ID: {deal_id}\n"
        f"[$angel-copilot]({runtime_skill_path}) assess the deal in {deal_path}\n"
        f"Use investor profile from {profile_path}.\n"
        "Run the skill workflow as a standalone single-deal assessment.\n"
        "Do not re-implement or summarize the skill rules in a custom rubric.\n"
        "Read files directly from the deal folder path provided.\n"
        "After completing the assessment, output strict JSON only.\n"
        f"Required JSON schema: {response_schema}\n"
        f"If the assessed company name differs from folder name, keep deal_id as '{deal_id}'.\n"
        "No markdown fences and no extra prose outside JSON.\n"
    )


def _response_schema_template() -> str:
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
        '"assessment_process":{"single_deal_equivalent":"yes|partial|no","used_full_rubric":true,'
        '"performed_web_sweep":true,"reconciled_docs_with_web":true,'
        '"built_three_case_return_model":true,"notes":"..."}}'
    )


def build_default_run_id() -> str:
    local_now = datetime.now().astimezone()
    zone = (local_now.strftime("%Z") or "LOCAL").replace("/", "-").replace(" ", "_")
    return local_now.strftime(f"run_%Y_%B_%d_%H-%M-%S_{zone}")


def _run_with_retry(runner, prompt: str, cwd: Path) -> tuple[dict[str, object] | None, str | None]:
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
    return {
        "single_deal_equivalent": "yes",
        "used_full_rubric": True,
        "performed_web_sweep": True,
        "reconciled_docs_with_web": True,
        "built_three_case_return_model": True,
    }


def _infer_dilution_assumption(return_scenarios: list[dict[str, object]]) -> str:
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
    if progress_callback is None:
        return
    progress_callback(event, payload)


def _parse_bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "included"}:
            return True
        if normalized in {"false", "no", "excluded"}:
            return False
    return None
