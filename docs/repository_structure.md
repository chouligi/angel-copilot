# Repository Structure

This repository follows a conventional Python open-source layout:

- `src/angelcopilot_batch/`: installable package code (CLI + batch pipeline).
- `tests/unit/`: fast unit tests for modules and helpers.
- `tests/integration/`: pipeline/CLI regression and end-to-end style tests.
- `tests/fixtures/`: synthetic fixture data used by tests.
- `docs/`: user-facing docs and screenshots/assets.
- `examples/`: sample profile, sample deal inputs, and sample outputs.
- `scripts/`: maintenance scripts (for example skill packaging helpers).
- `skills/public/angel-copilot/`: source of truth for skill content.
- `.github/`: issue/PR templates and CI workflows.

## Notes

- Package code uses the `src/` layout (best practice for import isolation during development/tests).
- Build artifacts (`*.egg-info`, `build/`, `dist/`) are intentionally excluded from version control.
- Runtime/local state (`outputs/`, `.angelcopilot/`, local helper scripts) is ignored by git.
