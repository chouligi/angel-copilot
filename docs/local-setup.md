# Local Setup and Workflows

This page covers using Angel Copilot from the open-source repository.

If you want the fastest no-setup path, use the [AngelCopilot GPT](https://chatgpt.com/g/g-69011b259dd88191860f2327c0cf19c7-angelcopilot).

## Choose your path

- Single-deal workflow: import `angel-copilot.skill` into a skill-enabled assistant
- Batch workflow: install the local CLI and run Dealflow Triage on your deal folders

## Recommended first step: create your investor profile

You can use Angel Copilot without a profile, but the output is usually stronger when it knows your geography, currency, check size, risk tolerance, follow-on strategy, and portfolio context.

In your assistant chat with the skill loaded:

1. `Create or update my investor profile`
2. `Start onboarding`
3. `Save my profile`

Save the profile block to:

```text
.angelcopilot/profile.md
```

Optional local template:

```bash
mkdir -p .angelcopilot
cp examples/profile.local.template.md .angelcopilot/profile.md
```

## Single-deal assessment memo

Use this path when you want a memo for one startup.

### Packaged `.skill`

If you prefer a simple upload/import flow, use the packaged file in the repo root:

- `angel-copilot.skill`

You can upload or import that file in skill-enabled UIs.

### Local skill usage

Use this prompt and point it to your installed `SKILL.md` and the sample deal folder:

```text
[$angel-copilot](<path-to-installed-skill-md>) assess the deal in <absolute-path-to-repo>/examples/sample-deal
```

Example installed skill path for Codex:

```text
~/.codex/skills/angel-copilot/SKILL.md
```

Profile behavior:

- If `.angelcopilot/profile.md` exists, Angel Copilot loads it at assessment start
- If the profile is missing, it runs a generic assessment and states that clearly

Expected output:

- A written deal memo in the chat response
- Optional saved output under `examples/sample-output/quick-deal-memo/`
- Memo header: `Deal Assessment Memo`

## Dealflow Triage

Use this path when you want to validate and rank multiple startup opportunities.

### Install dependencies

1. Install Python dependencies.

Recommended:

```bash
uv sync
```

Fallback:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

2. Ensure one assistant CLI is available in your shell:

```bash
codex --version
# or
claude --version
```

3. Install the PDF rendering dependency once:

```bash
uv run python -m angelcopilot_batch.cli setup
```

### Validate the synthetic fixtures

```bash
uv run python -m angelcopilot_batch.cli batch validate \
  --deals-root tests/fixtures/deals \
  --layout flat \
  --intake-filter rules
```

### Run a sample comparative batch

```bash
uv run python -m angelcopilot_batch.cli batch run \
  --deals-root tests/fixtures/deals \
  --layout flat \
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

If `.angelcopilot/profile.md` does not exist yet, create it first.

Expected output folder:

- `outputs/run_<timestamp>/`
- Includes `angelcopilot_batch_report.md`, `angelcopilot_batch_summary.csv`, `angelcopilot_batch_assessments.json`, `angelcopilot_batch_report.html`
- The report header is `AngelCopilot Dealflow Triage Report`
- PDF generation is enabled by default; use `--no-pdf` to disable

### Run on your own deal folders

Tip: omit `--since-days` if you want to include all deals in `--deals-root`.

Layout quick guide:

- `--layout syndicates`: top-level folders are source folders that contain deal folders
- `--layout flat`: top-level folders or files under `--deals-root` are treated as deals directly

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

### How deal discovery works

1. Point `--deals-root` to a local folder containing startup documents.
2. Choose `--layout`.
3. Angel Copilot scans supported files: `.txt`, `.md`, `.pdf`, `.docx`, `.zip`.
4. It computes the latest activity timestamp for each detected deal.
5. If you pass `--since-days`, it keeps only recent deals.
6. `batch validate` shows what was detected; `batch run` scores those deals.

Directory examples:

```text
# --layout syndicates
/deals-root/
  SourceA/
    startup-a/
      deck.pdf
      memo.md
  PersonalCRM/
    startup-b/
      one-pager.docx
```

```text
# --layout flat
/deals-root/
  startup-a/
    deck.pdf
  startup-b/
    memo.md
```

## Local skill folders

### Claude Code local skill

If you run Claude Code with a local filesystem skill path, add:

```text
skills/public/angel-copilot
```

### Codex local skill

If you run Codex with a local filesystem skill path, copy the skill folder into:

```text
~/.codex/skills/angel-copilot
```

## CLI runtime notes

- Recommended path: use `uv run` so you do not need to manage Python path details manually
- Alternative path:

```bash
python3 -m pip install -e .
python3 -m angelcopilot_batch.cli --help
```

- Fallback path if you see `ModuleNotFoundError`:

```bash
PYTHONPATH=src python3 -m angelcopilot_batch.cli --help
```

## Maintainer note

`skills/public/angel-copilot/` is the source of truth for skill content.

If you change the skill files, rebuild and verify the packaged `.skill` file:

```bash
./scripts/build_skill_package.sh
./scripts/verify_skill_package.sh
```
