"""Command-line interface for batch run, validate, setup, and report rebuild."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

from angelcopilot_batch.intake import discover_recent_deals
from angelcopilot_batch.job import run_batch_job
from angelcopilot_batch.profile import load_investor_profile
from angelcopilot_batch.reporting import (
    ASSESSMENTS_JSON_FILENAME,
    load_assessments_from_json,
    write_batch_outputs,
)
from angelcopilot_batch.scoring import apply_scoring_rules


class _HelpFormatter(argparse.RawTextHelpFormatter):
    """Format help text with readable sections and selective defaults."""

    def _get_help_string(self, action: argparse.Action) -> str:
        """Get help string.
        
        Args:
            action: Value for ``action``.
        
        Returns:
            str: Value returned by this function.
        """
        help_text = action.help or ""
        if "%(default)" in help_text:
            return help_text
        if action.required:
            return help_text
        if action.default in {None, argparse.SUPPRESS}:
            return help_text
        if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):  # noqa: SLF001
            return help_text
        return f"{help_text} (default: %(default)s)"


LAYOUT_HELP = dedent(
    """
    How to interpret --deals-root:
      syndicates: top-level folders are group/source folders that contain deal folders
      flat: top-level folders/files are deals directly
    """
).strip()

DEALS_ROOT_HELP = dedent(
    """
    Root folder containing your deal files/folders.
    Use --layout syndicates if deals are one level below group folders,
    or --layout flat if deals are directly under this root.
    """
).strip()
INTAKE_FILTER_HELP = dedent(
    """
    Candidate deal-folder filtering mode:
      smart: assistant classifier + fallback heuristics for deciding whether a folder is a startup/deal folder
      rules: heuristics only (faster; excludes admin/legal/docs-like folders)
    """
).strip()


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args and dispatch to the selected subcommand.

    Args:
        argv: Optional CLI arguments. When omitted, uses ``sys.argv``.

    Returns:
        Process-style exit code.
    """

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "batch" and args.batch_command == "run":
        return _run_batch(args)

    if args.command == "batch" and args.batch_command == "validate":
        return _validate_batch(args)

    if args.command == "batch" and args.batch_command == "report":
        return _rerender_report(args)

    if args.command == "setup":
        return _run_setup(args)

    parser.print_help()
    return 1


def _run_batch(args: argparse.Namespace) -> int:
    """Execute `batch run` and print a compact completion summary.
    
    Args:
        args: Value for ``args``.
    
    Returns:
        int: Value returned by this function.
    """

    top_level_containers = args.layout == "syndicates"
    result = run_batch_job(
        deals_root=args.deals_root,
        since_days=args.since_days,
        assistant=args.assistant,
        profile_path=args.profile,
        out=args.out,
        skill_path=args.skill_path,
        top_level_containers=top_level_containers,
        intake_filter=args.intake_filter,
        include_pdf=args.pdf,
        parallelism=args.parallelism,
        run_id=args.run_id or None,
        cwd=Path.cwd(),
        logger=print,
    )
    print(f"Deals scored: {len(result.assessments)}")

    return 0


def _validate_batch(args: argparse.Namespace) -> int:
    """Execute `batch validate` and print discovered deal candidates.
    
    Args:
        args: Value for ``args``.
    
    Returns:
        int: Value returned by this function.
    """

    deals_root = Path(args.deals_root).expanduser().resolve()
    deals = discover_recent_deals(
        deals_root=deals_root,
        since_days=args.since_days,
        top_level_containers=(args.layout == "syndicates"),
        intake_filter=args.intake_filter,
    )

    print(f"Detected deals: {len(deals)}")
    for deal in deals:
        print(f"- {deal.deal_id}: {len(deal.supported_files)} supported files")

    return 0


def _rerender_report(args: argparse.Namespace) -> int:
    """Execute `batch report` to regenerate artifacts from stored JSON.
    
    Args:
        args: Value for ``args``.
    
    Returns:
        int: Value returned by this function.
    """

    output_dir = Path(args.out).expanduser().resolve()
    source_run_id = args.run_id
    target_run_id = args.target_run_id or source_run_id
    run_dir = output_dir / source_run_id
    json_path = _resolve_report_json_path(run_dir)

    if not json_path.exists():
        raise FileNotFoundError(f"Report JSON not found: {json_path}")

    assessments = load_assessments_from_json(json_path)
    if args.recompute_scoring:
        profile_path = Path(args.profile).expanduser().resolve()
        profile = load_investor_profile(profile_path)
        check_size = float(profile.ticket_typical) if profile.ticket_typical > 0 else 10000.0
        investment_basis = "profile_ticket_typical" if profile.ticket_typical > 0 else "default_10000"
        currency = profile.currency.strip() or "USD"

        refreshed: list = []
        for assessment in assessments:
            updated = replace(
                assessment,
                hypothetical_investment=check_size,
                investment_currency=currency,
                investment_basis=investment_basis,
                dilution_assumption=_infer_dilution_assumption(assessment.return_scenarios),
            )
            refreshed.append(apply_scoring_rules(updated, profile))
        assessments = refreshed

    output_paths = write_batch_outputs(
        assessments=assessments,
        output_dir=output_dir,
        run_id=target_run_id,
        include_pdf=("pdf" in args.formats),
    )

    print(f"Regenerated markdown: {output_paths.markdown_path}")
    print(f"Regenerated csv: {output_paths.csv_path}")
    print(f"Regenerated json: {output_paths.json_path}")
    if output_paths.pdf_path:
        print(f"Regenerated pdf: {output_paths.pdf_path}")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse command tree for the CLI.
    
    Args:
        None.
    
    Returns:
        argparse.ArgumentParser: Value returned by this function.
    """

    parser = argparse.ArgumentParser(
        description=dedent(
            """
            AngelCopilot batch CLI.
            Use a subcommand below, then add -h for command-specific help.
            """
        ).strip(),
        formatter_class=_HelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "setup",
        help="Install local browser dependency for PDF generation",
        description="Install Chromium via Playwright for PDF report rendering.",
        formatter_class=_HelpFormatter,
    )

    batch_parser = subparsers.add_parser(
        "batch",
        help="Batch workflows",
        description="Run, validate, or rerender AngelCopilot batch outputs.",
        formatter_class=_HelpFormatter,
        epilog=dedent(
            """
            Examples:
              uv run python -m angelcopilot_batch.cli batch validate -h
              uv run python -m angelcopilot_batch.cli batch run -h
              uv run python -m angelcopilot_batch.cli batch report -h
            """
        ).strip(),
    )
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command")

    run_parser = batch_subparsers.add_parser(
        "run",
        help="Run batch assessments",
        description="Discover recent deals, prepare documents, run assessments, and write outputs.",
        formatter_class=_HelpFormatter,
        epilog=dedent(
            """
            Examples:
              # Deals are one level under source folders (source A, personal CRM, etc.)
              uv run python -m angelcopilot_batch.cli batch run \\
                --deals-root /path/to/deals \\
                --layout syndicates \\
                --since-days 7 \\
                --assistant codex

              # Deals live directly under --deals-root
              uv run python -m angelcopilot_batch.cli batch run \\
                --deals-root /path/to/deals \\
                --layout flat \\
                --since-days 30 \\
                --assistant codex
            """
        ).strip(),
    )
    _add_common_discovery_arguments(run_parser)

    execution_group = run_parser.add_argument_group("Assessment execution")
    execution_group.add_argument(
        "--assistant",
        choices=["codex", "claude"],
        default="codex",
        help="Assistant backend used for assessments and smart intake classification.",
    )
    execution_group.add_argument(
        "--skill-path",
        default="~/.codex/skills/angel-copilot/SKILL.md",
        help="Path to AngelCopilot SKILL.md used by native skill invocation.",
    )
    execution_group.add_argument(
        "--profile",
        default=".angelcopilot/profile.md",
        help="Path to your investor profile markdown file.",
    )
    execution_group.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help="Number of deal assessments to run concurrently (2-3 is a practical start).",
    )

    output_group = run_parser.add_argument_group("Output control")
    output_group.add_argument("--out", default="outputs", help="Directory where run outputs are written.")
    output_group.add_argument("--run-id", default="", help="Optional custom run folder name.")

    run_parser.set_defaults(pdf=True)
    pdf_toggle = output_group.add_mutually_exclusive_group()
    pdf_toggle.add_argument(
        "--pdf",
        dest="pdf",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Generate PDF output (requires Playwright Chromium installed).",
    )
    pdf_toggle.add_argument(
        "--no-pdf",
        dest="pdf",
        action="store_false",
        default=argparse.SUPPRESS,
        help="Disable PDF output generation.",
    )

    validate_parser = batch_subparsers.add_parser(
        "validate",
        help="Validate intake folders",
        description="Preview which deals would be discovered before running assessments.",
        formatter_class=_HelpFormatter,
        epilog=dedent(
            """
            Examples:
              uv run python -m angelcopilot_batch.cli batch validate \\
                --deals-root /path/to/deals \\
                --layout syndicates \\
                --since-days 7 \\
                --intake-filter smart

              uv run python -m angelcopilot_batch.cli batch validate \\
                --deals-root /path/to/deals \\
                --layout flat \\
                --since-days 30 \\
                --intake-filter rules
            """
        ).strip(),
    )
    _add_common_discovery_arguments(validate_parser)

    report_parser = batch_subparsers.add_parser(
        "report",
        help="Rebuild reports from JSON",
        description="Regenerate report artifacts from an existing run's JSON without rerunning assessments.",
        formatter_class=_HelpFormatter,
        epilog=dedent(
            """
            Example:
              uv run python -m angelcopilot_batch.cli batch report \\
                --run-id run_20260329_101500 \\
                --formats md,csv,json,pdf
            """
        ).strip(),
    )
    report_group = report_parser.add_argument_group("Report source and output")
    report_group.add_argument("--run-id", required=True, help="Source run id to load existing JSON from.")
    report_group.add_argument("--target-run-id", default="", help="Optional new run id for regenerated artifacts.")
    report_group.add_argument("--out", default="outputs", help="Base output directory where runs are stored.")
    report_group.add_argument("--formats", default="md,csv,json,pdf", help="Comma-separated output formats.")
    report_group.add_argument(
        "--recompute-scoring",
        action="store_true",
        help="Reapply scoring using current profile settings before writing reports.",
    )
    report_group.add_argument(
        "--profile",
        default=".angelcopilot/profile.md",
        help="Profile used when --recompute-scoring is enabled.",
    )

    return parser


def _add_common_discovery_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared discovery-related arguments used by run and validate commands.
    
    Args:
        parser: Value for ``parser``.
    
    Returns:
        None.
    """

    discovery_group = parser.add_argument_group("Deal discovery")
    discovery_group.add_argument(
        "--deals-root",
        required=True,
        help=DEALS_ROOT_HELP,
    )
    discovery_group.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only include deals updated in the last N days. Omit to include all detected deals.",
    )
    discovery_group.add_argument(
        "--layout",
        choices=["syndicates", "flat"],
        default="syndicates",
        help=LAYOUT_HELP,
    )
    discovery_group.add_argument(
        "--intake-filter",
        choices=["smart", "rules"],
        default="smart",
        help=INTAKE_FILTER_HELP,
    )


def _run_setup(args: argparse.Namespace) -> int:
    """Install Playwright Chromium used by PDF rendering.
    
    Args:
        args: Value for ``args``.
    
    Returns:
        int: Value returned by this function.
    """

    del args
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("Chromium installed for Playwright PDF rendering.")
    return 0


def _resolve_report_json_path(run_dir: Path) -> Path:
    """Resolve report JSON path, supporting current and legacy filenames.
    
    Args:
        run_dir: Value for ``run_dir``.
    
    Returns:
        Path: Value returned by this function.
    """

    preferred = run_dir / ASSESSMENTS_JSON_FILENAME
    if preferred.exists():
        return preferred

    legacy = run_dir / "report.json"
    if legacy.exists():
        return legacy

    return preferred


def _infer_dilution_assumption(return_scenarios: list[dict[str, object]]) -> str:
    """Infer dilution inclusion summary from report scenario payloads.
    
    Args:
        return_scenarios: Value for ``return_scenarios``.
    
    Returns:
        str: Value returned by this function.
    """

    observed: list[bool] = []
    for scenario in return_scenarios:
        candidate = scenario.get("includes_dilution")
        if candidate is None:
            candidate = scenario.get("dilution_included")
        parsed = _parse_bool_or_none(candidate)
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


if __name__ == "__main__":
    raise SystemExit(main())
