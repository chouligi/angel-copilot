# Angel Copilot Claude Code Skill

Angel Copilot is a Claude Code skill that helps users build an investor profile, plan allocations, and assess startup deals using a structured rubric and web-sweep process.

## Install via Git clone

1) Clone this repo.
2) In Claude Code, add a local skill and point it to:

```
skills/public/angel-copilot
```

If your Claude Code setup expects skills to live in a specific directory, you can also copy the folder there.
If you prefer the Claude UI upload flow, use the packaged `angel-copilot.skill` file in the repo root.

## Use

Example prompts:
- Create or load my investor profile
- Start onboarding
- Suggest my investment allocation
- Assess a startup deal
- Generate a due diligence checklist
- Explain what a SAFE is and how it differs from a convertible note

## Optional: package as a .skill file

If your Claude Code environment supports `.skill` archives, package the skill folder and import it:

1) Zip the `skills/public/angel-copilot` folder.
2) Rename the zip to `angel-copilot.skill`.
3) Import the `.skill` file using your Claude Code installer.

Note: This repo already includes `angel-copilot.skill`, which can be uploaded directly in the Claude UI or imported into Claude Code.

## Further reading

- How to use AngelCopilot: https://beyondthedemoai.substack.com/p/angelcopilot-a-copilot-for-angel
- How AngelCopilot was built: https://www.linkedin.com/pulse/how-i-built-angelcopilot-turning-custom-gpt-system-chouliaras-eqwoe/?trackingId=DViRC4F3QcaGwJSxjGoZAA%3D%3D
