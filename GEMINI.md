# Gemini / Gemini 4 Carbon — Swirl engineering instructions

Repository: `SOLHK/Swirl`. Target branch for work is `test`; **never modify `main` or create a Release without explicit owner approval**.

Before every coding/CI task, read and obey:
1. [AGENTS.md](AGENTS.md) — active architecture, security and branch rules.
2. [docs/ENGINEERING_CHANGE_POLICY.md](docs/ENGINEERING_CHANGE_POLICY.md) — maintainability, PR size, justified testing and CI-cost policy.
3. Relevant existing architecture/build documents and the exact current PR/HEAD logs.

## Non-negotiable development behavior

- **Act on the requested issue, do not merely analyze it.** Prove the root cause with the current source/logs and fix it in the smallest complete change; avoid unrelated refactors.
- Do **not** create speculative defensive layers, duplicate code paths, fake fallbacks, repeated diagnostics, expansive regression matrices or CI jobs just to make the change appear thorough. Safety-critical defenses are necessary and must be retained.
- Prefer a single authoritative implementation, keep Rust Core as the only native network runtime, and preserve UI behavior/data/migrations.
- Before slow/full CI, do targeted syntax/compile/tests for the affected scope; separate inner-loop feedback from PR integration and final product acceptance. Never skip required security or final delivery checks.
- Do **not** suppress QML/VME warnings, weaken tests, change thresholds/deadlines, silently disable checks, fabricate evidence, or reuse CI success from another SHA.
- Default PR-size review trigger: **more than 20 production source files OR more than 1000 manually authored changed source lines**. Split unrelated changes; a necessary atomic exception requires a written rationale and owner approval. Not a reason to delete meaningful tests or compress code.
- Any change to required CI gates needs explicit owner authorization and verified equivalent coverage. Documentation/PR checkboxes are guidance, **not GitHub-enforced branch-protection rules**.
- Work on a development branch and create a PR targeting `test`; report the latest check results accurately. Never claim production test completion on the strength of a loopback/mock fixture alone.

## Current debugging pointer (not a standing assumption)

At writing, Swirl 0.2.45 PR #62 had a Preview failure in run `44096965107`, step `Exercise the production Release routes with normal animation`: `rapid full-motion smoke failed: Native smoke exited 2`, with a QML/runtime warning check. **Check current HEAD and fresh CI** before relying on this historical pointer. Investigate the actual diagnostic artifact and fix the root cause; do not suppress warnings or remove the 61-route smoke requirement.

Deliver real code/CI changes when asked, with a measured before/after impact, risks and exact commit/PR details.