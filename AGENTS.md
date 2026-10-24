# Current UI V2 staged work (2026-10-24)

- Continue only in `D:/Codex/work/Swirl-ui-v2-20261024`, branch `work/swirl-ui-v2-20261024`, based on `4c8c9e076976e5cfb62f103daecdf2afc121eeb3` (0.2.3). Older branch instructions below are historical. Preserve main/test and all other windows; no force pushes.
- Stage 1 audit and stage 2 design/confirmation are complete. The user explicitly answered “确认这套架构” in this chat. Read `docs/UI_V2_HANDOFF.md` and `docs/UI_V2_STAGE2_ARCHITECTURE.md` plus its UI/routing/API contracts; next is stage 3 node-library implementation without asking for the same architecture approval again. No V2 product behavior or installer has shipped. Keep each stage focused and report commits, evidence, next steps and the requested model-switch reminder. Never switch models autonomously.
- The user explicitly resolved the radius discrepancy: set both window and sidebar corners to 14dp during implementation. Preserve window dimensions and sidebar structure. This supersedes the old frozen radius requirement, but does not authorize removing effects, animations or functionality. Run focused geometry checks for this change.
- Subscription auto-refresh must manage source nodes without silently applying foreign DNS/rules/groups. Nodes are a resource library; row selection/details must not choose or connect a runtime exit. Policy selection belongs to the strategy page.
- Implement the stage 2 contracts for five-tier Rust routing, stable `policy:default`/UUID identities, source-only refresh, explicit one-use full-config approval, a single in-flight configuration transaction with durable receipt and admission gating, and truthful TUN/process capability reporting. Keep schema-1 behavior until migration review. Reuse parser/model/probe/policy/motion foundations; all cases in `docs/contracts/ui-v2-acceptance-cases.json` are planned, not passed tests.
- Mandatory skill paths: existing Hallmark at `C:/Users/sysfr/.agents/skills/hallmark/SKILL.md`, project `.agents/skills/ui-ux-pro-max/SKILL.md`, installed Motion at `D:/Codex/skills/motion-design/SKILL.md`, and Qt QML at `C:/Users/sysfr/.codex/skills/qt-qml/SKILL.md`. Read `docs/UI_V2_SKILLS.md`; do not duplicate installations or introduce web UI frameworks.
- The 0.2.3 diagnostic package is historical baseline evidence, not V2 delivery. Actual private-node/Codex failures remain unresolved. Do not redownload private sources or mutate this machine's proxy/TUN/routes/DNS. Use isolated tests and exact-source package identity; do not reconfigure another worktree's CMake cache.

# v0.2.3 REALITY wire compatibility follow-up (2026-10-24; historical)

- Version 0.2.2 recovered actual cached subscription nodes but did not prove private-node networking. Version 0.2.3 fixes a separately reproduced production REALITY authenticated-client version error: use the inspected and independently tested protocol baseline 26.10.17 rather than Swirl's application version. Keep server version/time/key/SNI/UUID checks and certificate acceptance strict.
- Reuse the existing hash-pinned official Xray test peer for focused production import/authentication tests, independently of Windows packaging. Never ship that peer as the product core. Reuse encrypted cached private responses for the next isolated two-node comparison; do not repeat consumed source downloads or change this machine's proxy/TUN/routes/DNS/Codex processes.
- A controlled independent-peer pass is not proof that the supplied subscription's actual nodes or Codex services work. Retain failed actual-provider evidence and label the installer diagnostic until private networking is confirmed.

# v0.2.2 actual subscription regression follow-up (2026-10-24)

- The user retested 0.2.0 and explicitly reported that the failures persist across client formats. 0.2.1 only optimized the build graph; it is not a claimed subscription fix. Continue on independent `work/swirl-019-subscription-regression-20261024`, preserve main/test/other windows, and deliver the next actual repair as 0.2.2.
- Automatic import must reuse the existing manual nodes-only trust boundary when a foreign full profile cannot execute. Strict full-profile projection remains unchanged. A reduced result contains only validated canonical node candidates plus the current Swirl DNS/rules/groups. Foreign global settings, scripts, rewrites, MITM, file declarations, listeners and TUN are refused execution/application and retained only as bounded encrypted inert source data, with a persistent explanation. They must never be fetched, evaluated, used as host settings or replayed into the runtime. This explicit restricted data mapping supersedes the older whole-document capability allowlist that rejected otherwise usable nodes.
- Node authentication, TLS/REALITY, protocols, transport options, unknown node security fields and actual runtime eligibility remain strict. Empty inactive TCP URI host/path/serviceName placeholders are absent-equivalent; nonempty/whitespace values, unknown extensions and conflicting aliases are not silently discarded. Retain exact source URIs and encrypted provenance.
- The user authorized one read-only download of each of the two existing saved sources; both returned 200 and were cached with current-user DPAPI. That authorization has been consumed. The user separately supplied a test source and explicitly authorized testing it; use bounded download/import/isolated-node checks without changing the active system proxy or other apps. Never put private addresses, tokens, credentials or decrypted content in source, chat, public CI or deliverables.
- Validate this repair against actual encrypted cached responses before packaging, in addition to synthetic security and transaction tests. Recognition, imported nodes, runtime eligibility and successful actual outbound traffic remain separate claims. Preserve the successful 0.2.1 build graph/cache changes and do not rerun DPI/UI matrices for these importer changes.

# v0.1.9 automatic subscription and network repair (2026-10-24; historical)

- The latest user asks for automatic subscription import: remove full-profile/node-only choices from the subscription page; recognize downloaded content, apply compatible complete profiles, preserve valid nodes with visible warnings only after a whole-document safety audit. Scripts, local files, extra listeners, system mutations and TLS validation bypass remain prohibited.
- The next installer is 0.1.9. Increment PRODUCT_VERSION.txt for each subsequent delivered update; application, installer and artifact metadata must agree.
- Keep the already verified node-only forwarding for Surge, Loon and Quantumult X. Real Codex/browser/provider acceptance remains assigned to the user.

# v0.1.8 network and subscription repair (2026-10-24)

- Work on independent `work/swirl-018-network-compat-20261024`, based on the latest fetched v0.1.8 `fad05a72070b5770708cf64af57936bc9f0e64a1`. Do not change main, test or other windows' branches; never force-push.
- Preserve working V2Ray/VMess import and forwarding. Optional TCP acceleration may fall back to ordinary TCP only without changing authentication, transport, TLS or unknown-field validation.
- Browser Google/YouTube, actual Codex services/workspace/login/chat, real provider measurements and system-proxy versus TUN comparison are assigned to the user. Controlled loopback/independent-peer automation is separate evidence. DPI visual acceptance is also manual.
- Preserve this machine's working proxy/TUN/routes/DNS and Codex sessions. Use read-only existing logs; never export account credentials or private subscriptions. Mutating system-proxy recovery tests run only on disposable CI runners.
- Retain Cargo/Ninja caches and exact EXE/DLL/source identity. Deliver independently verified stages with necessary security/network tests and clearly label unverified acceptance. Do not develop a native format ahead of subscription/network stability.

# v0.1.7 subscription and networking repair (2026-10-24; historical)

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
