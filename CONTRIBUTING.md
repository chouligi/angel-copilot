# Contributing

Thanks for contributing to Angel Copilot.

## Scope

This repository combines:

- Skill content (`skills/public/angel-copilot`)
- Batch CLI pipeline (`src/angelcopilot_batch`)
- Packaging/docs for public use

Contributions are welcome across all three areas.

## Development setup

Recommended:

```bash
uv sync
```

Fallback:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-dev.txt
python3 -m pip install -e .
```

## Run tests

```bash
uv run pytest -q
```

Targeted suites:

```bash
uv run pytest -q tests/unit
uv run pytest -q tests/integration
```

## Repository layout

See [`docs/repository_structure.md`](docs/repository_structure.md) for the canonical folder structure.

## Docs and examples

- Keep README claims aligned with actual CLI behavior.
- Use synthetic/fake data for examples and screenshots.
- Do not commit private decks, LPAs, or sensitive deal docs.

## Skill packaging sync

`skills/public/angel-copilot/` is the source of truth.

When skill files change:

```bash
./scripts/build_skill_package.sh
./scripts/verify_skill_package.sh
```

Commit `angel-copilot.skill` only when verify passes.

## Pull requests

- Keep PRs focused and small where possible.
- Include a short rationale and test/verification notes.
- If behavior changes, update docs and examples in the same PR.

Use the repository PR template when opening a pull request.
