# Changelog

All notable changes to this project are documented in this file.

## v0.2.0 - Unreleased

### Changed

- Reports label the highlight as Priority follow-up and explain that medium-priority PURSUE still merits diligence.
- Batch reports rank by recommendation, then follow-up priority, evidence strength and score, so medium-priority opportunities no longer precede high-priority opportunities with the same recommendation.
- HTML and PDF table headers wrap within adjusted column widths; report title and logo spacing also accommodates narrow layouts.

- A version 4 INVEST now requires an explicit positive cheque amount. Zero-amount recommendations downgrade to WAIT and cannot fall back to the investor's typical ticket.
- Assessments now give one action recommendation: INVEST / PURSUE / WAIT / PASS. INVEST means a supported cheque now; PURSUE means prioritize diligence; WAIT means defer active work until a stated trigger; PASS means stop at current terms or for this investor.
- Schema version 4 removes the screening/commitment mode split and the separate verdicts. Saved version 1/2/3 assessments remain readable with their original meanings.
- Assessments open with a factual Company Overview, followed by a Decision Brief with a prominent weighted score, coverage, recommendation, attention and readiness. New weighted scores renormalize over scored factors and show excluded-factor coverage; unknowns are not treated as zero.
- New assessments give stage-appropriate provisional ratings across factors when the business model supports a judgment; ordinary missing pitch materials are shown as Low evidence strength rather than an automatic score penalty. PURSUE now requires at least 3.5 / 5 plus a deal-specific diligence case; a qualifying score alone does not trigger pursuit or investment.
- Conversational, Markdown, HTML and PDF reports share the same section order and Evidence strength definitions; evidence strength is distinct from factor quality.
- Missing evidence leaves unassessable factors unscored rather than assigning poor scores. Diligence distinguishes material blockers, accepted venture risks and future milestones.
- Attention highlights INVEST and high-priority PURSUE opportunities; archived version 2 WAIT assessments retain the documented score/profile-fit attention heuristic.
- Supported valuation, dilution and syndicate-cost ranges show the equity exit needed for a target net multiple without requiring cheque sizing or invented probabilities.
- Batch assessments use the same four-action recommendation; report regeneration preserves source versions and historical recommendations.
- Consolidated the earlier unpublished report simplification and runtime-model changes since v0.1.2.

### Added

- Fictional reports and examples updated to explain the unified action model and report formats.
- Documentation and fictional report examples define INVEST / PURSUE / WAIT / PASS consistently and preserve versions 1–3 as historical formats.
- Skill package version metadata aligned with the Python distribution version.

## v0.1.0 - 2026-03-28

### Added

- Local batch/dealflow triage support via `angelcopilot` CLI:
  - `batch validate` for intake preview
  - `batch run` for multi-deal scoring
  - `batch report` for artifact regeneration from saved JSON
  - comparative output artifacts in `md` / `csv` / `json` / `html` / `pdf`
- Batch workflow controls:
  - layout modes (`syndicates`, `flat`)
  - intake filtering (`smart`, `rules`)
  - concurrent execution via `--parallelism`
  - profile-aware scoring via `.angelcopilot/profile.md`
- Public-release README overhaul with clearer product framing and workflow ladder:
  - Quick Deal Memo
  - Personalized Deal Assessment
  - Dealflow Triage
- Skill packaging sync scripts:
  - `scripts/build_skill_package.sh`
  - `scripts/verify_skill_package.sh`
- Demo/docs scaffolding:
  - `docs/assets/`
  - `examples/sample-deal/`
  - `examples/sample-output/`
- Release hygiene files:
  - `CONTRIBUTING.md`
  - `ROADMAP.md`
  - GitHub issue and pull request templates

### Improved

- Launch readiness and discoverability guidance (release checklist and clearer quickstart story).
- Reproducible sample flows using synthetic data for both single-deal and batch workflows.
- README now makes first-run usage lighter while keeping profile personalization visible.
- Batch progress logging clarity (preparation vs assessment-start events).
- Test stability for time-window fixture discovery (fixture mtimes refreshed during tests).
