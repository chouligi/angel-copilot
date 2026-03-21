from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from angelcopilot_batch.assistant import build_assistant_runner
from angelcopilot_batch.intake import discover_recent_deals
from angelcopilot_batch.pipeline import build_default_run_id, run_batch_assessment
from angelcopilot_batch.profile import load_investor_profile
from angelcopilot_batch.reporting import (
    ASSESSMENTS_JSON_FILENAME,
    load_assessments_from_json,
    write_batch_outputs,
)
from angelcopilot_batch.scoring import apply_scoring_rules


def main(argv: list[str] | None = None) -> int:
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
    deals_root = Path(args.deals_root).expanduser().resolve()
    output_dir = Path(args.out).expanduser().resolve()
    profile_path = Path(args.profile).expanduser().resolve()

    profile = load_investor_profile(profile_path)
    runner = build_assistant_runner(args.assistant)

    assessments = run_batch_assessment(
        deals_root=deals_root,
        since_days=args.since_days,
        profile=profile,
        runner=runner,
        cwd=Path.cwd(),
    )

    run_id = args.run_id or build_default_run_id()
    output_paths = write_batch_outputs(
        assessments=assessments,
        output_dir=output_dir,
        run_id=run_id,
        include_pdf=args.pdf,
    )

    print(f"Deals scored: {len(assessments)}")
    print(f"Markdown report: {output_paths.markdown_path}")
    print(f"CSV report: {output_paths.csv_path}")
    print(f"JSON report: {output_paths.json_path}")
    if output_paths.pdf_path:
        print(f"PDF report: {output_paths.pdf_path}")
    else:
        print("PDF report: not generated (Playwright not available)")

    return 0


def _validate_batch(args: argparse.Namespace) -> int:
    deals_root = Path(args.deals_root).expanduser().resolve()
    deals = discover_recent_deals(deals_root=deals_root, since_days=args.since_days)

    print(f"Detected deals: {len(deals)}")
    for deal in deals:
        print(f"- {deal.deal_id}: {len(deal.supported_files)} supported files")

    return 0


def _rerender_report(args: argparse.Namespace) -> int:
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
    parser = argparse.ArgumentParser(description="AngelCopilot batch runner")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Install local browser dependency for PDF generation")

    batch_parser = subparsers.add_parser("batch", help="Batch commands")
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command")

    run_parser = batch_subparsers.add_parser("run", help="Run weekly batch assessments")
    run_parser.add_argument("--deals-root", required=True)
    run_parser.add_argument("--since-days", type=int, default=7)
    run_parser.add_argument("--assistant", choices=["codex", "claude"], default="codex")
    run_parser.add_argument("--profile", default=".angelcopilot/profile.md")
    run_parser.add_argument("--out", default="outputs")
    run_parser.add_argument("--run-id", default="")
    run_parser.add_argument("--pdf", action="store_true", default=True)

    validate_parser = batch_subparsers.add_parser("validate", help="Validate intake folders")
    validate_parser.add_argument("--deals-root", required=True)
    validate_parser.add_argument("--since-days", type=int, default=7)

    report_parser = batch_subparsers.add_parser("report", help="Rebuild reports from JSON")
    report_parser.add_argument("--run-id", required=True)
    report_parser.add_argument("--target-run-id", default="")
    report_parser.add_argument("--out", default="outputs")
    report_parser.add_argument("--formats", default="md,csv,json,pdf")
    report_parser.add_argument("--recompute-scoring", action="store_true")
    report_parser.add_argument("--profile", default=".angelcopilot/profile.md")

    return parser


def _run_setup(args: argparse.Namespace) -> int:
    del args
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("Chromium installed for Playwright PDF rendering.")
    return 0


def _resolve_report_json_path(run_dir: Path) -> Path:
    preferred = run_dir / ASSESSMENTS_JSON_FILENAME
    if preferred.exists():
        return preferred

    legacy = run_dir / "report.json"
    if legacy.exists():
        return legacy

    return preferred


def _infer_dilution_assumption(return_scenarios: list[dict[str, object]]) -> str:
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
