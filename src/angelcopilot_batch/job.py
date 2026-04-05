"""High-level batch job entrypoint with progress logging and output writing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from angelcopilot_batch.assistant import build_assistant_runner, build_intake_classifier
from angelcopilot_batch.models import AssessmentResult, BatchOutputPaths
from angelcopilot_batch.pipeline import (
    EXECUTION_MODE_SKILL_NATIVE,
    DEFAULT_RUNTIME_SKILL_PATH,
    build_default_run_id,
    run_batch_assessment,
)
from angelcopilot_batch.profile import load_investor_profile
from angelcopilot_batch.reporting import write_batch_outputs

LogFn = Callable[[str], None]


@dataclass
class BatchRunResult:
    """Result object returned by `run_batch_job`."""

    run_id: str
    assessments: list[AssessmentResult]
    output_paths: BatchOutputPaths


def run_batch_job(
    deals_root: str | Path,
    since_days: int | None = None,
    assistant: str = "codex",
    profile_path: str | Path = ".angelcopilot/profile.md",
    out: str | Path = "outputs",
    skill_path: str | Path = DEFAULT_RUNTIME_SKILL_PATH,
    top_level_containers: bool = True,
    intake_filter: str = "smart",
    include_pdf: bool = True,
    parallelism: int = 1,
    run_id: str | None = None,
    cwd: str | Path | None = None,
    logger: LogFn | None = None,
    runner=None,
) -> BatchRunResult:
    """Run a full batch assessment job and write all configured artifacts.

    Args:
        deals_root: Root path containing deal folders/files.
        since_days: Intake lookback window in days; ``None`` includes all deals.
        assistant: Assistant backend name (``codex`` or ``claude``).
        profile_path: Path to investor profile markdown file.
        out: Output directory for run artifacts.
        skill_path: Runtime ``SKILL.md`` path used for skill-native prompts.
        top_level_containers: Whether top-level folders are containers.
        intake_filter: Intake mode (``smart`` or ``rules``).
        include_pdf: Whether to generate PDF artifacts.
        parallelism: Number of concurrent deal assessments.
        run_id: Optional explicit run id; auto-generated when omitted.
        cwd: Optional working directory for assistant command execution.
        logger: Optional log sink.
        runner: Optional injected assistant runner implementation.

    Returns:
        Batch run result containing run id, assessments, and output paths.
    """

    resolved_deals_root = Path(deals_root).expanduser().resolve()
    resolved_profile_path = Path(profile_path).expanduser().resolve()
    resolved_output_dir = Path(out).expanduser().resolve()
    resolved_skill_path = Path(skill_path).expanduser().resolve()
    resolved_cwd = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd()

    profile = load_investor_profile(resolved_profile_path)
    effective_runner = runner or build_assistant_runner(assistant)
    intake_classifier = None
    if intake_filter == "smart":
        try:
            intake_classifier = build_intake_classifier(assistant, cwd=resolved_cwd)
        except RuntimeError:
            intake_classifier = None
    log = logger or _default_logger

    assessments = run_batch_assessment(
        deals_root=resolved_deals_root,
        since_days=since_days,
        profile=profile,
        runner=effective_runner,
        cwd=resolved_cwd,
        profile_path=resolved_profile_path,
        execution_mode=EXECUTION_MODE_SKILL_NATIVE,
        runtime_skill_path=resolved_skill_path,
        top_level_containers=top_level_containers,
        intake_filter=intake_filter,
        folder_classifier=intake_classifier,
        progress_callback=_build_progress_callback(log),
        parallelism=parallelism,
    )

    effective_run_id = run_id or build_default_run_id()
    output_paths = write_batch_outputs(
        assessments=assessments,
        output_dir=resolved_output_dir,
        run_id=effective_run_id,
        include_pdf=include_pdf,
    )
    log(f"[{_timestamp()}] batch completed: scored={len(assessments)} run_id={effective_run_id}")
    log(f"[{_timestamp()}] markdown: {output_paths.markdown_path}")
    log(f"[{_timestamp()}] csv: {output_paths.csv_path}")
    log(f"[{_timestamp()}] json: {output_paths.json_path}")
    if output_paths.pdf_path:
        log(f"[{_timestamp()}] pdf: {output_paths.pdf_path}")
    else:
        log(f"[{_timestamp()}] pdf: not generated")

    return BatchRunResult(
        run_id=effective_run_id,
        assessments=assessments,
        output_paths=output_paths,
    )


def _build_progress_callback(logger: LogFn) -> Callable[[str, dict[str, object]], None]:
    """Map internal progress events to user-facing log lines.
    
    Args:
        logger: Value for ``logger``.
    
    Returns:
        Callable[[str, dict[str, object]], None]: Value returned by this function.
    """

    def _callback(event: str, payload: dict[str, object]) -> None:
        """Callback.
        
        Args:
            event: Value for ``event``.
            payload: Value for ``payload``.
        
        Returns:
            None.
        """
        prefix = f"[{_timestamp()}]"
        if event == "deal_discovery_started":
            since_days = payload.get("since_days")
            since_label = since_days if since_days is not None else "all"
            layout = "syndicates" if payload.get("top_level_containers") else "flat"
            logger(
                f"{prefix} discovering deals: root={payload.get('deals_root')} "
                f"layout={layout} since_days={since_label} intake={payload.get('intake_filter')}"
            )
            return
        if event == "deal_discovery_completed":
            since_days = payload.get("since_days")
            since_label = since_days if since_days is not None else "all"
            logger(
                f"{prefix} discovery complete: deals={payload.get('total_deals', 0)} "
                f"since_days={since_label}"
            )
            return
        if event == "batch_started":
            since_days = payload.get("since_days")
            since_label = since_days if since_days is not None else "all"
            logger(
                f"{prefix} batch started: deals={payload.get('total_deals', 0)} "
                f"since_days={since_label} mode={payload.get('execution_mode')}"
            )
            return
        if event == "deal_started":
            logger(
                f"{prefix} [{payload.get('index')}/{payload.get('total')}] "
                f"preparing deal '{payload.get('deal_id')}' (files={payload.get('supported_files')})"
            )
            return
        if event == "deal_prepared":
            logger(
                f"{prefix} [{payload.get('index')}/{payload.get('total')}] "
                f"prepared deal '{payload.get('deal_id')}' "
                f"(files_used={payload.get('files_used')}, warnings={payload.get('warnings')})"
            )
            return
        if event == "deal_assessment_started":
            logger(
                f"{prefix} [{payload.get('index')}/{payload.get('total')}] "
                f"assessment started for '{payload.get('deal_id')}'"
            )
            return
        if event == "deal_completed":
            logger(
                f"{prefix} [{payload.get('index')}/{payload.get('total')}] "
                f"done '{payload.get('deal_id')}' score={float(payload.get('weighted_score', 0.0)):.2f} "
                f"verdict={payload.get('verdict')}"
            )
            return
        if event == "deal_skipped":
            logger(
                f"{prefix} [{payload.get('index')}/{payload.get('total')}] "
                f"skipped '{payload.get('deal_id')}': {payload.get('reason')}"
            )
            return
        if event == "deal_failed":
            logger(
                f"{prefix} [{payload.get('index')}/{payload.get('total')}] "
                f"failed '{payload.get('deal_id')}': {payload.get('reason')} | {payload.get('error', '')}"
            )
            return
        if event == "batch_completed":
            logger(
                f"{prefix} batch summary: scored={payload.get('scored_deals')} "
                f"attention={payload.get('attention_deals')} total={payload.get('total_deals')}"
            )

    return _callback


def _timestamp() -> str:
    """Return local wall-clock timestamp for log prefixes.
    
    Args:
        None.
    
    Returns:
        str: Value returned by this function.
    """

    return datetime.now().astimezone().strftime("%H:%M:%S")


def _default_logger(message: str) -> None:
    """Default logger implementation used when no logger is injected.
    
    Args:
        message: Value for ``message``.
    
    Returns:
        None.
    """

    print(message, flush=True)
