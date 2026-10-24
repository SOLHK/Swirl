# v0.1.7 subscription and networking repair (2026-10-24)

- Work on independent `work/swirl-017-subscription-network-20261024`, based on remote S4 `ca7015679aef49702a40302de55d83e367ed9e95`. Do not update S4, S3, main, test or parallel branches.
- The current user authorizes subscription/node content and dialog layout repairs; preserve sidebar width, sidebar/frame radii and overall window geometry. Keep all existing motion and interactions.
- Retain persistent subscription ownership, transactional updates and manual nodes. Unknown legacy ownership requires explicit cleanup/reassignment; never infer that unowned nodes are safe to delete.
- Run portable dependency/target checks, Rust/C++/QML regression and Windows packaging. Distinguish controlled peers, public traffic and private-provider/Codex account acceptance.
- Preserve existing local Clash/system proxy/TUN/routes/DNS and private data. Network setting mutation tests run only on disposable CI runners. Do not upload private logs, URLs or node credentials.

# Current S4 integration contract (2026-10-24)

- Active work is `work/swirl-s4-final-completion-20261023`, based on frozen S3 `9f8af5754d2a932f7b967eea0e64cbc75717e6be`. The S3 instructions below are historical; do not modify S3, main, test or parallel branches.
- Read `docs/S4_BASELINE_AUDIT.md` and `docs/S4_CROSS_PLATFORM.md`. Keep protocol, subscription semantics, DNS, routing and measurement in portable Rust. Windows, Apple, Android and HarmonyOS SDK calls belong only in separate platform adapters; no Qt or WinTUN dependency in common Rust crates.
- Preserve the existing window/sidebar geometry, contours, clipping and sizing policy exactly. Content refinements must retain functions and interruptible motion. Measure before and after on the same machine.
- Before each commit run the portable dependency guard and applicable target checks. Distinguish native tests, cross-compilation, system permissions and device acceptance. OpenHarmony target compilation is not HarmonyOS NEXT VPN acceptance; Android VPN APIs are not a substitute.
- Commit and push verified stages promptly to S4 without force. Final product gates and package identity must use one integrated SHA. Preserve failed and skipped evidence; do not lower strict network assertions.
- Existing local Clash/system proxy/TUN/routes/DNS and private subscriptions remain untouched. Use isolated data and controlled peers. The user performs final private-provider acceptance after development.

# Historical S3 integration contract (2026-10-23)

- Work on `work/swirl-s3-max-ultra-20261023`, based on the user-approved `work/ui-window-node-performance-20261023` (`7056dea1c920cee57208c1aae54b3550a850f758`). Do not reset, force-push, or modify main/test/other development branches.
- Read `docs/handoffs/S3_MAX_TO_ULTRA.md` before continuing. Earlier branch/version/compatibility instructions below are historical and do not override this contract.
- Preserve the current window and sidebar contours, geometry, clipping, antialiasing, glass and interaction infrastructure. Run `python tools/Verify-S3UiBaseline.py`; do not replace QML with old subscription-branch files.
- Rust Core is the sole product proxy runtime. Do not restore Mihomo or the former C++ proxy engine. Parsing another application's subscription format does not authorize bundling its core.
- The user currently relies on Clash for this conversation. Local tests must not stop it or change system proxy, TUN, routes or DNS. Keep system-proxy mutation tests on disposable CI runners. Use isolated test storage and loopback peers; do not request or upload private subscriptions.
- Preserve strict protocol/TLS closure failures. L1 recognition, L2 conversion, L3 startup, L4 independent-peer transfer and L5 user acceptance are separate claims.

# UI/UX Guidance

## UI update delivery requirements (2026-10-23)

- Continue the accepted `0b15f77` UI on `work/ui-liquid-glass-unification-20261023`, preserving the latest sidebar material, shadow and interactions.
- The next UI update is 0.1.3; increment the patch version for every subsequent delivered update (0.1.4, 0.1.5, ...). Update `src/Swirl.Quick/PRODUCT_VERSION.txt` before building so application and installer versions agree.
- After validating each completed UI update, commit and push it to GitHub on the UI branch. Report the commit and any unverified acceptance items. Do not update `main` without explicit authorization.
- Buttons and related controls use the sidebar selection's flat neutral rounded style. Do not add raised button shadows or 3D gradients; preserve interaction feedback and motion.

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
