# Sample Deal Input (Synthetic)

This folder contains a fictional startup deal package for reproducible demos.

## Intended use

- Use this folder as a low-risk input for the Quick Deal Memo workflow.
- Keep content synthetic and non-sensitive.
- Expand files over time if you want richer memo outputs.

## Current files

- `syntheticco_01_alphamesh_memo.md`

## How this is used

Prompt your assistant with Angel Copilot skill and point to this directory path.

Example:

```text
[$angel-copilot](<path-to-installed-skill-md>) assess the deal in <absolute-path-to-repo>/examples/sample-deal
```

## Notes

- This folder is for single-deal workflow demos.
- For batch/dealflow triage demos, use `tests/fixtures/deals` or your own multi-deal folder.
