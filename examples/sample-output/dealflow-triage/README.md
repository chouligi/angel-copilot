# Dealflow Triage Output (Synthetic Samples)

This folder represents expected comparative output artifacts from the batch triage workflow.

## Expected generated artifacts

From `batch run`, the real artifacts are written under:

`outputs/run_<timestamp>/`

Expected files include:

- `angelcopilot_batch_report.md`
- `angelcopilot_batch_summary.csv`
- `angelcopilot_batch_assessments.json`
- `angelcopilot_batch_report.html`
- `angelcopilot_batch_report.pdf` (default enabled, unless `--no-pdf`)

## Included synthetic sample artifacts

- `fictional_batch_assessments.json`
  - Fully fictional batch input used to render the sample report.
- `angelcopilot_batch_report.md`
  - Rendered markdown comparative report from the fictional input.
- `angelcopilot_batch_summary.csv`
  - Ranked deal summary table from the fictional input.
- `angelcopilot_batch_report.pdf`
  - Synthetic comparative PDF report generated from the fictional batch JSON.

These files are synthetic demo assets only.
