# UI/UX Guidance

## Current development handoff

Read `docs/CONTINUE_DEVELOPMENT.md` and `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md` before continuing the Rust migration. Preserve the existing UI; implement native forwarding in Rust without disguising an external core as native. The user's 2026-10-17 handoff supersedes the older `test` instruction: after each completed and validated stage, commit and push to `work/core-completion-20261017`. Never update `main` without explicit user authorization. Reuse the configured Swirl Core Automation App; do not reconfigure the App or change Secrets. Private subscription links, credentials and decrypted configurations must stay outside Git and external services. The historical Mihomo architecture below describes the retained compatibility build, not permission to use it as fallback in Rust mode.

For UI/UX design, interaction, accessibility, or visual refinement, consult `.agents/skills/ui-ux-pro-max/SKILL.md` and its local resources when relevant. Treat the skill as guidance and follow existing project constraints first. Preserve Swirl’s refined, minimal macOS 27 visual direction and its C++23, Qt 6 Quick/QML, and Mihomo architecture; do not add unrelated frameworks such as React, Vue, or Tailwind.
