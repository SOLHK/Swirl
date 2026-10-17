# UI/UX Guidance

## Current development handoff

Read `docs/CONTINUE_DEVELOPMENT.md` and `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md` before continuing the Rust migration. Preserve the existing UI; implement native forwarding in Rust without disguising an external core as native. After each completed and validated stage, commit and push to `test`. Never update `main` without explicit user authorization. Private subscription links, credentials and decrypted configurations must stay outside Git and external services. The historical Mihomo architecture below describes the retained compatibility build, not permission to use it as fallback in Rust mode.

For UI/UX design, interaction, accessibility, or visual refinement, consult `.agents/skills/ui-ux-pro-max/SKILL.md` and its local resources when relevant. Treat the skill as guidance and follow existing project constraints first. Preserve Swirl’s refined, minimal macOS 27 visual direction and its C++23, Qt 6 Quick/QML, and Mihomo architecture; do not add unrelated frameworks such as React, Vue, or Tailwind.
