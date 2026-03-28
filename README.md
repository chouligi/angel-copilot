![Angel Copilot logo](./logo_Dec_25_bigger.png)

# Angel Copilot Skill for AI Agent Tools

Angel Copilot is a skill for AI agent tools (e.g., Claude Code, Codex, etc.) that helps users build an investor profile, plan allocations, and assess startup deals using a structured rubric and web-sweep process.

This repository now includes two usage modes:
- Lite mode: skill-only, conversational/manual assessments.
- Batch mode: local Python CLI for weekly multi-deal processing (`md/csv/json/pdf` outputs).

## Use in the Claude UI (upload)

Upload the packaged `angel-copilot.skill` file from the repo root.

## Use in Claude Code (local skill)

1) Clone this repo.
2) In Claude Code, add a local skill and point it to:

```
skills/public/angel-copilot
```

If your Claude Code setup expects skills to live in a specific directory, you can also copy the folder there.

## Use in Codex (local skill)

Copy the skill folder to your Codex skills directory, typically:

```
~/.codex/skills/angel-copilot
```

## Batch mode (local CLI)

### Install

```bash
python3 -m pip install -e .
```

Or with requirements files:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

### Install assistant CLI(s) used by batch mode

Batch mode calls a local assistant binary (`codex` or `claude`), so it must be installed and available in your shell `PATH`.

Codex CLI:

```bash
npm install -g @openai/codex
which codex
codex --version
codex --login
```

Claude Code CLI:

```bash
which claude
claude --version
```

If `which codex` or `which claude` returns nothing, the binary is not in `PATH`.

For `zsh`, add the install directory to `~/.zshrc`, then reload:

```bash
echo 'export PATH="/path/to/cli/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Example for `nvm` users:

```bash
echo 'export PATH="$HOME/.nvm/versions/node/v20.19.6/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Then run one setup command for PDF support:

```bash
angelcopilot setup
```

If `angelcopilot` is not found in your shell, run:

```bash
python3 -m angelcopilot_batch.cli setup
```

If you are running directly from the repo and still see `ModuleNotFoundError`, use:

```bash
PYTHONPATH=src python3 -m angelcopilot_batch.cli setup
```

The same pattern applies to other commands:

```bash
python3 -m angelcopilot_batch.cli batch validate ...
python3 -m angelcopilot_batch.cli batch run ...
```

### Optional local profile

Create a local investor profile file in the repo at:

`.angelcopilot/profile.md`

Batch mode reads this file by default via `--profile .angelcopilot/profile.md`.

You can create it in two ways.

1) Use the AngelCopilot skill onboarding flow
- In Codex/Claude with the skill loaded, run:
  - `Create or load my investor profile`
  - `Start onboarding`
- Answer the questions.
- Ask:
  - `Save my profile`
- Copy the returned profile block into `.angelcopilot/profile.md`.

2) Create it manually
- Copy the template:

```bash
mkdir -p .angelcopilot
cp examples/profile.local.template.md .angelcopilot/profile.md
```

- Then edit `.angelcopilot/profile.md` with your values.

Minimal example:

```text
region: Greece
currency: EUR
inferred_risk_level: High
ticket_typical: 25000
sectors_themes: AI, DevTools, B2B SaaS
geo_focus: Europe, US
```

Template file: `examples/profile.local.template.md`

Also accepted for convenience:
- `themes:` as an alias for `sectors_themes:`
- separators `,` `/` `&` `;` for list fields like sectors and geographies

### Validate weekly intake folder

```bash
angelcopilot batch validate --deals-root /path/to/deals --since-days 7 --layout syndicates
```

### Run weekly batch assessment

```bash
angelcopilot batch run \
  --deals-root /path/to/deals \
  --since-days 7 \
  --assistant codex \
  --parallelism 3 \
  --intake-filter smart \
  --layout syndicates \
  --skill-path ~/.codex/skills/angel-copilot/SKILL.md \
  --profile .angelcopilot/profile.md \
  --out outputs
```

You can switch to Claude CLI with `--assistant claude`.
Batch execution always runs in skill-native mode (one AngelCopilot skill invocation per deal).
`--parallelism` controls how many deals are assessed concurrently (default `1`).
Start with `2-3` and increase only if your machine and assistant CLI handle it reliably.
`--intake-filter smart` is the default and classifies folder candidates as deal vs admin/docs buckets.
Classification uses the selected assistant (`codex` or `claude`) on folder names; if unavailable, it falls back to rules.
Use `--intake-filter rules` to disable classifier-based filtering.
Layout modes:
- `syndicates` (default): treat top-level folders as containers; child folders are deals; standalone child `pdf/docx/zip` files are also deals.
- `flat`: treat top-level folders as deal folders.

### Run from Python with progress logging

```python
from angelcopilot_batch.job import run_batch_job

result = run_batch_job(
    deals_root="/path/to/deals",
    since_days=2,
    assistant="codex",
    parallelism=3,
    skill_path="~/.codex/skills/angel-copilot/SKILL.md",
    profile_path=".angelcopilot/profile.md",
    out="outputs",
)
```

This prints live progress like:
- batch started summary
- current deal index and name (`starting deal ...`)
- per-deal completion (`done ... score=... verdict=...`)
- failures/skips with reason
- final output paths (`md/csv/json/pdf`)

### Rebuild report artifacts for an existing run

```bash
angelcopilot batch report --run-id run_YYYY_Month_DD_HH-MM-SS_<TZ> --out outputs --formats md,csv,json,pdf
```

To write rerendered outputs into a new run folder name:

```bash
angelcopilot batch report --run-id OLD_RUN_ID --target-run-id NEW_HUMAN_READABLE_RUN_ID --out outputs
```

If you changed profile parsing/scoring logic and want old runs refreshed without rerunning assessments:

```bash
angelcopilot batch report \
  --run-id run_YYYY_Month_DD_HH-MM-SS_<TZ> \
  --out outputs \
  --recompute-scoring \
  --profile .angelcopilot/profile.md
```

Default run folder format is human-readable, for example:

`run_2026_March_21_12-33-45_CET`

Each run produces:
- `angelcopilot_batch_report.md`
- `angelcopilot_batch_summary.csv`
- `angelcopilot_batch_assessments.json`
- `angelcopilot_batch_report.html`
- `angelcopilot_batch_report.pdf` (if PDF dependencies are installed)

### Notes
- Batch mode expects one folder per deal and autodetects `txt/md/pdf/docx/zip`.
- `.zip` files are unzipped recursively during preprocessing (including nested zip files).
- Profile is local to the repo by default (`.angelcopilot/profile.md`) and excluded from git.
- Upstream document capture from deal platforms remains manual/official.
- No scraping automation is included.
- Reports include a per-deal `Files Used as Evidence` section and any `Evidence Preparation Warnings`.

## Testing without production docs

This repo includes synthetic fixture deals under:

`tests/fixtures/deals`

Use them for local development and regression testing:

```bash
pytest -q
```

The fixture dataset includes:
- Plain `txt/md` deal docs.
- A zip-only deal input (`docs_bundle.zip`) to verify auto-unzip behavior.
- No real deal data.

## Use

Example prompts:
- Create or load my investor profile
- Start onboarding
- Suggest my investment allocation
- Upload a startup's documents or information and ask "Assess a startup deal".
- Generate a due diligence checklist
- Explain what a SAFE is and how it differs from a convertible note

## Use the packaged .skill file

This repo already includes `angel-copilot.skill`.

## Further reading

- How to use AngelCopilot: https://beyondthedemoai.substack.com/p/angelcopilot-a-copilot-for-angel
- How AngelCopilot was built: https://www.linkedin.com/pulse/how-i-built-angelcopilot-turning-custom-gpt-system-chouliaras-eqwoe/?trackingId=DViRC4F3QcaGwJSxjGoZAA%3D%3D
