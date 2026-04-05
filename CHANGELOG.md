# Changelog

All notable changes to this project are documented in this file.

## v0.1.0 - 2026-03-28

### Added

- Local batch/dealflow triage support via `angelcopilot_batch` CLI:
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

