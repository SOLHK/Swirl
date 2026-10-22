# UI/UX Guidance

## User development requirements (2026-10-17)

- Before implementation, look for mature open-source approaches on GitHub and
  record the relevant primary references. Learn from their design and observable
  behavior; independently implement Swirl changes without copying their code.
- Check the task's premises, missing information and reasoning before acting.
  Separate verified facts, hypotheses and judgments; explain disagreements and
  material costs or risks with evidence. Ask when the actual goal is uncertain.
- Use the smallest direct change that fulfills the request. Do not add unrelated
  features, configuration options or extension frameworks.
- On the user's Windows computer, keep generated/downloaded files, skills,
  checkouts and build tools in `D:\Codex`. Do not write to `C:` unless a required
  component cannot run elsewhere and the user has explicitly approved it. A
  cloud Linux workspace cannot access that drive; disclose this limitation and
  never claim a GitHub push also saved files to the user's D drive.

## Current development handoff

Read `docs/CONTINUE_DEVELOPMENT.md` and `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md` before continuing the Rust migration. Preserve the existing UI; implement native forwarding in Rust without disguising an external core as native. The user's 2026-10-17 handoff supersedes the older `test` instruction: after each completed and validated stage, commit and push to `work/core-completion-20261017`. Never update `main` without explicit user authorization. Reuse the configured Swirl Core Automation App; do not reconfigure the App or change Secrets. Private subscription links, credentials and decrypted configurations must never enter source commits, public CI, logs or conversion services. The user has authorized testing the existing encrypted archive in the private Swirl-Private-Tests repository: decrypt only in memory in that private workflow, preserve only whitelisted reports, and do not refresh subscription URLs without a new open-window instruction. The historical Mihomo architecture below describes the retained compatibility build, not permission to use it as fallback in Rust mode.

For UI/UX design, interaction, accessibility, or visual refinement, consult `.agents/skills/ui-ux-pro-max/SKILL.md` and its local resources when relevant. Treat the skill as guidance and follow existing project constraints first. Preserve Swirl’s refined, minimal macOS 27 visual direction and its C++23, Qt 6 Quick/QML, and Mihomo architecture; do not add unrelated frameworks such as React, Vue, or Tailwind.
