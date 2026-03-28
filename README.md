![Angel Copilot logo](./logo_Dec_25_bigger.png)

# Angel Copilot

Angel Copilot is an open-source AI workflow for angel investors. It helps you evaluate a single startup quickly or screen multiple deals at once and generate a ranked dealflow report.

It supports two core workflows: Quick Deal Memo and Dealflow Triage. Both can run with or without an investor profile, but we recommend creating your investor profile first for best results. Outputs are designed for decision support, with structured Markdown memos for single deals and comparative PDF reports for multi-deal prioritization.

## Why Angel Copilot

Assessing startup deals is hard. Even experienced angels benefit from a structured thinking partner that can challenge assumptions, surface risks, and help turn messy materials into a clearer investment view.

And when dealflow gets large, reviewing every company deeply can become a full-time job. Angel Copilot helps you move from ad-hoc assessment to focused triage, so you can spend more time on the deals most worth your attention.

## Start here

Pick the path that matches your goal:

- Quick Deal Memo (fastest): upload/import `angel-copilot.skill`, then run the single-deal prompt in "Try it on a sample deal in 5 minutes."
- Dealflow Triage (advanced): complete "Dealflow Triage dependencies (local CLI)" in Installation, then run `batch validate` and `batch run` on your deal folders.
- Recommended first step for either path: create your investor profile in "Recommended first step: create your investor profile."

## Who this is for

- Angel investors who want a repeatable way to evaluate startup opportunities.
- Solo fund managers, scouts and angel syndicate leads screening many opportunities each week.
- Founders and startup professionals transitioning into angel investing who want a disciplined memo process.

## Core capabilities

- Investor-profile-aware deal assessment using a structured 7-factor rubric.
- Web-sweep + document reconciliation before scoring.
- Return-scenario modeling with explicit dilution assumptions.
- Batch intake, scoring, and comparative reporting across multiple deals.
- Structured investment memos in Markdown format for single-deal review.
- Comparative `csv` / `json` / `html` / `pdf` outputs for batch triage.

## How to use Angel Copilot

### 1) Quick Deal Memo

Best for evaluating one startup quickly.

- Lowest-friction workflow.
- Usually one deal at a time.
- Works with or without a profile; best results come from profile-based personalization.
- Produces a structured investment memo in Markdown format.
- Good first workflow for new users and ad-hoc diligence.

### 2) Dealflow Triage

Best for screening multiple startups and deciding where to focus.

- Advanced workflow for batch intake and comparative review.
- Compares opportunities across the same run window.
- Helps rank which deals deserve follow-up attention first.
- Produces a polished comparative PDF report as the batch artifact.

## Screenshot / demo placeholders

Add launch visuals in [`docs/assets`](docs/assets):

- `quick-deal-memo.png`: single-deal memo screenshot.
- `dealflow-triage-report.png`: comparative report screenshot.

See [`docs/assets/README.md`](docs/assets/README.md) for expected dimensions and naming.

## Try it on a sample deal in 5 minutes

Use the synthetic sample and fixture data in this repository. No real company data is required.

### A) Quick single-deal memo (skill flow)

1. Load Angel Copilot as a local skill in Codex or Claude Code.
2. After installing the local skill, ask Angel Copilot to assess the synthetic sample deal folder.
3. Use this prompt and point to your installed `SKILL.md` and the synthetic sample folder:

```text
[$angel-copilot](<path-to-installed-skill-md>) assess the deal in <absolute-path-to-repo>/examples/sample-deal
```

Example installed skill path (Codex local skill install):

```text
~/.codex/skills/angel-copilot/SKILL.md
```

Expected output:
- A structured deal assessment memo in the chat response.
- You can save a copy at `examples/sample-output/quick-deal-memo/` (see placeholder there).

### B) Dealflow triage (batch flow)

This workflow validates a batch of startup folders, scores them consistently, and generates a comparative report with ranked attention priorities.

Use synthetic fixtures first (demo):

```bash
uv run python -m angelcopilot_batch.cli batch validate \
  --deals-root tests/fixtures/deals \
  --layout flat \
  --since-days 3650 \
  --intake-filter rules
```

Then run a small comparative batch:

```bash
uv run python -m angelcopilot_batch.cli batch run \
  --deals-root tests/fixtures/deals \
  --layout flat \
  --since-days 3650 \
  --assistant codex \
  --skill-path <path-to-installed-skill-md> \
  --profile .angelcopilot/profile.md \
  --out outputs \
  --parallelism 2 \
  --intake-filter rules
```

Example `--skill-path` value:

```text
~/.codex/skills/angel-copilot/SKILL.md
```

If `.angelcopilot/profile.md` does not exist yet, create it first (see "Recommended first step: create your investor profile" below).

Expected output folder:
- `outputs/run_<timestamp>/`
- Includes `angelcopilot_batch_report.md`, `angelcopilot_batch_summary.csv`, `angelcopilot_batch_assessments.json`, `angelcopilot_batch_report.html`
- PDF generation is enabled by default; use `--no-pdf` to disable.

If PDF is missing, run setup once:

```bash
uv run python -m angelcopilot_batch.cli setup
```

Run Dealflow Triage on your own deal folders:

```bash
uv run python -m angelcopilot_batch.cli batch validate \
  --deals-root /path/to/deals-root \
  --layout syndicates \
  --since-days 7 \
  --intake-filter smart
```

```bash
uv run python -m angelcopilot_batch.cli batch run \
  --deals-root /path/to/deals-root \
  --layout syndicates \
  --since-days 7 \
  --assistant codex \
  --skill-path <path-to-installed-skill-md> \
  --profile .angelcopilot/profile.md \
  --out outputs \
  --parallelism 2 \
  --intake-filter smart
```

What this produces:
- A timestamped run folder under `outputs/`.
- A comparative markdown report and summary table (`csv`) for ranking deals.
- A comparative PDF report artifact (unless you pass `--no-pdf`).

## Recommended first step: create your investor profile

You can run Angel Copilot without a profile, but results are typically better when profile context is available.
Create your investor profile once so assessments can be tailored to your geography, currency, check size, risk tolerance, follow-on strategy, and portfolio context.

In your assistant chat with the skill loaded:

1. `Create or update my investor profile`
2. `Start onboarding`
3. `Save my profile`

Then save the profile block to:

```text
.angelcopilot/profile.md
```

Optional local template:

```bash
mkdir -p .angelcopilot
cp examples/profile.local.template.md .angelcopilot/profile.md
```

## Installation

Choose the path that matches how you want to use Angel Copilot:

- Quick Deal Memo via skill upload/import: no local Python setup required.
- Dealflow Triage via local CLI: install local dependencies and one assistant CLI (`codex` or `claude`).

### Packaged `.skill`

If you prefer a simple upload flow (no local code setup), use the packaged file:

- `angel-copilot.skill` (in the repo root)
- You can upload/import this file in skill-enabled UIs (for example, Claude UI skill upload, or other clients that support `.skill` import).

If you are only using upload/import, you can stop here.

If you are maintaining or editing the source skill files:

- Source of truth is `skills/public/angel-copilot/`.
- Rebuild the packaged file after skill edits:

```bash
./scripts/build_skill_package.sh
```

- Verify packaged file and source files are synced:

```bash
./scripts/verify_skill_package.sh
```

### Dealflow Triage dependencies (local CLI)

Use this only if you want to run batch commands such as `batch validate` and `batch run`.

1. Install Python dependencies (choose one path).

Recommended:

```bash
uv sync
```

Fallback:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

2. Ensure one assistant CLI is installed and available in your shell:

```bash
codex --version
# or
claude --version
```

3. Install PDF rendering dependency once (Playwright Chromium):

```bash
uv run python -m angelcopilot_batch.cli setup
```

### Claude Code local skill

Use this only if you run Claude Code with a local filesystem skill path.
If you already imported/uploaded `angel-copilot.skill`, you can skip this section.

1. Clone this repo (or use your existing clone).
2. In Claude Code, add this local skill folder path:

```text
skills/public/angel-copilot
```

This mode is most useful if you are editing the skill and want your local changes to be used immediately.

### Codex local skill

Use this only if you run Codex with a local filesystem skill path.
If you already imported/uploaded `angel-copilot.skill`, you can skip this section.

Copy the skill folder into Codex local skills:

```text
~/.codex/skills/angel-copilot
```

This mode is most useful if you are editing the skill and want local source changes to be used immediately.

### CLI runtime notes (for batch commands only)

This section explains how to run the local Python CLI (`angelcopilot_batch`) for Dealflow Triage.
If you only use skill upload/import flows, you can skip this.

- Recommended path: use `uv run` to execute commands without managing Python path details manually.
- Alternative path: install the package in editable mode, then call the module directly:

```bash
python3 -m pip install -e .
python3 -m angelcopilot_batch.cli --help
```

- Fallback path: if you run from source and see `ModuleNotFoundError`, set `PYTHONPATH` explicitly:

```bash
PYTHONPATH=src python3 -m angelcopilot_batch.cli --help
```

## Sample prompts

- `Create or update my investor profile`
- `Assess a startup deal`
- `What are the main risks in this deal?`
- `Compare these startup opportunities`
- `Help me prioritize which of these deals deserve attention`
- `Generate a due diligence checklist`

## Sample output

### Sample Quick Deal Memo

What to expect:
- Narrative-first single-company memo.
- Scorecard, return assumptions, return scenarios, reconciliation gaps, and founder questions.

Example location:
- [`examples/sample-output/quick-deal-memo/sample_quick_deal_memo.md`](examples/sample-output/quick-deal-memo/sample_quick_deal_memo.md)

### Sample Dealflow Triage Report

What to expect:
- Multi-deal comparative ranking output.
- Side-by-side scoring summary with attention prioritization.
- Exportable PDF artifact for review/share.

Example location:
- [`examples/sample-output/dealflow-triage/README.md`](examples/sample-output/dealflow-triage/README.md)
- Fictional batch input JSON:
  [`examples/sample-output/dealflow-triage/fictional_batch_assessments.json`](examples/sample-output/dealflow-triage/fictional_batch_assessments.json)
- Synthetic report artifact:
  [`examples/sample-output/dealflow-triage/angelcopilot_batch_report.pdf`](examples/sample-output/dealflow-triage/angelcopilot_batch_report.pdf)


## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, tests, style, and PR guidance.


## Further reading

- [User guide](https://beyondthedemoai.substack.com/p/angelcopilot-a-copilot-for-angel)
- [Build story and background](https://www.linkedin.com/pulse/how-i-built-angelcopilot-turning-custom-gpt-system-chouliaras-eqwoe/?trackingId=DViRC4F3QcaGwJSxjGoZAA%3D%3D)
