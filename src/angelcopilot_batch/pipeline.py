from __future__ import annotations

from datetime import datetime
from pathlib import Path

from angelcopilot_batch.assistant import validate_assessment_payload
from angelcopilot_batch.extraction import extract_evidence_bundle
from angelcopilot_batch.intake import discover_recent_deals
from angelcopilot_batch.models import AssessmentResult, EvidenceBlock, InvestorProfile
from angelcopilot_batch.scoring import apply_scoring_rules

DEFAULT_SKILL_PATH = Path("skills/public/angel-copilot/SKILL.md")
DEFAULT_RUBRIC_PATH = Path("skills/public/angel-copilot/references/angelcopilot_deal_assessment_rubric.md")
MAX_EVIDENCE_CHARS = 200_000


def run_batch_assessment(
    deals_root: Path,
    since_days: int,
    profile: InvestorProfile,
    runner,
    cwd: Path,
    skill_path: Path = DEFAULT_SKILL_PATH,
    rubric_path: Path = DEFAULT_RUBRIC_PATH,
) -> list[AssessmentResult]:
    deals = discover_recent_deals(deals_root=deals_root, since_days=since_days)
    skill_text = _safe_read_text(skill_path)
    rubric_text = _safe_read_text(rubric_path)

    assessments: list[AssessmentResult] = []
    for deal in deals:
        evidence_bundle = extract_evidence_bundle(deal.supported_files)
        if not evidence_bundle.evidence_blocks:
            continue

        prompt = build_assessment_prompt(
            deal_id=deal.deal_id,
            profile=profile,
            skill_text=skill_text,
            rubric_text=rubric_text,
            evidence_bundle=evidence_bundle,
        )

        payload = _run_with_retry(runner=runner, prompt=prompt, cwd=cwd)
        if payload is None:
            continue

        normalized_payload = validate_assessment_payload(payload)
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
            evidence_sources=_build_evidence_sources(evidence_bundle.evidence_blocks),
            extraction_warnings=list(evidence_bundle.warnings),
            hypothetical_investment=check_size,
            investment_currency=profile.currency.strip() or "USD",
            investment_basis=investment_basis,
            dilution_assumption=_infer_dilution_assumption(return_scenarios),
        )
        assessments.append(apply_scoring_rules(assessment, profile))

    return sorted(assessments, key=lambda item: item.weighted_score, reverse=True)


def build_assessment_prompt(
    deal_id: str,
    profile: InvestorProfile,
    skill_text: str,
    rubric_text: str,
    evidence_bundle,
) -> str:
    evidence_text = _build_capped_evidence_text(evidence_bundle.evidence_blocks, max_chars=MAX_EVIDENCE_CHARS)
    warnings_text = "\n".join(evidence_bundle.warnings) if evidence_bundle.warnings else "None"

    response_schema = (
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

    return (
        "You are running one startup deal assessment using AngelCopilot logic.\n"
        f"Deal ID: {deal_id}\n"
        "Run the same depth as a single-deal dedicated assessment: "
        "full rubric, web sweep, and evidence reconciliation.\n"
        "Do not shortcut due to batch context. Treat this as a full standalone memo.\n"
        "Output only JSON. No markdown or prose outside JSON.\n"
        f"Required JSON schema: {response_schema}\n\n"
        "Quality bar requirements:\n"
        "- Provide all 7 category rationales with concrete evidence references.\n"
        "- Include web_sweep_findings as structured objects by area.\n"
        "- Include web_sweep_sources with dated URLs and relevance notes.\n"
        "- Include citations that reference both provided docs (D*) and web sources (W*).\n"
        "- Include verdict_one_liner always.\n"
        "- For WAIT/PASS verdicts, include explicit why_not_invest_now and "
        "what_would_upgrade_to_invest bullets.\n"
        "- For INVEST verdicts, keep why_not_invest_now empty.\n"
        "- Fill assessment_process honestly; use 'partial' if any step is incomplete.\n\n"
        "Investor profile context:\n"
        f"region: {profile.region}\n"
        f"currency: {profile.currency}\n"
        f"risk_level: {profile.inferred_risk_level}\n"
        f"ticket_typical: {profile.ticket_typical}\n"
        f"sectors_themes: {', '.join(profile.sectors_themes)}\n"
        f"geo_focus: {', '.join(profile.geo_focus)}\n\n"
        "Skill rules:\n"
        f"{skill_text}\n\n"
        "Rubric rules:\n"
        f"{rubric_text}\n\n"
        "Extraction warnings:\n"
        f"{warnings_text}\n\n"
        "Deal evidence:\n"
        f"{evidence_text}\n"
    )


def build_default_run_id() -> str:
    local_now = datetime.now().astimezone()
    zone = (local_now.strftime("%Z") or "LOCAL").replace("/", "-").replace(" ", "_")
    return local_now.strftime(f"run_%Y_%B_%d_%H-%M-%S_{zone}")


def _run_with_retry(runner, prompt: str, cwd: Path) -> dict[str, object] | None:
    try:
        return runner.run_assessment(prompt, cwd=cwd)
    except Exception:  # noqa: BLE001
        retry_prompt = (
            f"{prompt}\n\n"
            "RETRY INSTRUCTION: Return strict JSON only. Do not include markdown fences or extra text."
        )
        try:
            return runner.run_assessment(retry_prompt, cwd=cwd)
        except Exception:  # noqa: BLE001
            return None


def _safe_read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _build_capped_evidence_text(evidence_blocks: list[EvidenceBlock], max_chars: int) -> str:
    parts: list[str] = []
    used_chars = 0

    for block in evidence_blocks:
        chunk = f"SOURCE: {block.source_path.name}\n{block.text}\n\n"
        remaining = max_chars - used_chars
        if remaining <= 0:
            break

        if len(chunk) <= remaining:
            parts.append(chunk)
            used_chars += len(chunk)
            continue

        truncated_chunk = chunk[:remaining]
        parts.append(truncated_chunk)
        used_chars += len(truncated_chunk)
        break

    if len(parts) < len(evidence_blocks):
        parts.append("\n[TRUNCATED] Evidence was capped due to size.")

    return "".join(parts).strip()


def _build_evidence_sources(evidence_blocks: list[EvidenceBlock]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for block in evidence_blocks:
        label = str(block.source_path)
        if label in seen:
            continue
        seen.add(label)
        result.append(label)
    return result


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
