# Swirl Core R4 rule-routing audit checkpoint (2026-10-21)

## Baseline and branch safety

- Integration baseline inspected: `work/core-completion-20261017` at `2c2992e35c203ea242485dc919955234de764c3c`.
- The separate `work/core-buildkit-20261017` branch is divergent and 216 commits behind the integration branch; it is not a suitable R4 base.
- R4 branch: `work/core-rule-routing-20261021`, created from the integration baseline. No existing R4 branch was present in the branch listing.
- No rule-routing PR was returned by the initial GitHub PR search. Branch and file inspection is still required before future integration.

## Verified source findings

- `core/crates/swirl-routing/src/lib.rs` already implements ordered matching for DOMAIN, DOMAIN-SUFFIX, DOMAIN-KEYWORD, CIDR, source CIDR, destination port and MATCH, including a trace of the matched rule. Its tests cover suffix boundaries, first-match priority, lazy DNS resolution, IPv4/IPv6 literals and REJECT-style outbound selection.
- `core/crates/swirl-subscription/src/lib.rs` defines the Swirl IR matcher and validates outbound/rule references. The Rust routing crate currently depends only on this IR; it has no MRS loader dependency or MRS parsing module.
- `core/crates/swirl-core/src/lib.rs` invokes the Rust routing selector for actual TCP sessions and records the selected node and rule label. This is an existing real routing path, not merely a UI simulation.
- `src/Swirl.Quick/engine/RustCoreEngine.cpp` rejects `smartRouting && routingMode == "rule"` before constructing the Rust IR, even though its `routingConfiguration()` maps custom rules and built-in private destinations into Rust matchers.
- `src/Swirl.Quick/engine/SwirlProtocolRegistry.cpp` in the non-Rust build explicitly directs MRS smart routing to Mihomo. The production compile definition and build target must be checked before changing engine selection.
- Bundled assets already exist at `src/Swirl.Quick/packaging/rules/`: `cn-domain.mrs` (540,748 bytes), `cn-ip.mrs` (37,538 bytes), `manifest.json`, and `LICENSE`. The manifest pins source `MetaCubeX/meta-rules-dat` commit `83c8208bdfae92b1caaa29745f51f233b6f1847e` and SHA-256 hashes for both files. Do not redownload or duplicate them.

## MRS format and license notes

Mihomo's published rule-provider documentation says MRS currently supports domain and ipcidr behavior and identifies the MRS format as binary. The upstream provider package documents magic bytes `MRS\x01`. This is not sufficient by itself to safely parse the remaining binary structure. Do not treat the MRS files as text or implement a guessed decoder. Before adding a parser, inspect the exact upstream implementation/version and confirm license compatibility; then add corruption, truncation, wrong-behavior, version and checksum tests.

References:
- https://wiki.metacubex.one/en/config/rule-providers/
- https://pkg.go.dev/github.com/metacubex/mihomo/rules/provider

## Immediate next steps

1. Inspect exact upstream MRS v1 domain and ipcidr decoding implementation and its dependency licenses.
2. Add a bounded, fail-closed MRS reader to `swirl-routing` or a small dedicated crate; use the already bundled files and manifest hashes.
3. Add tests for valid files, hash mismatch, truncated header/body, unsupported version, domain label boundaries, IPv4 and IPv6 CIDRs.
4. Connect immutable preloaded rule sets to Rust IR/session routing without bypassing existing ordered user rules.
5. Remove the smart-routing rejection only after the complete path is configured and tests prove the behavior; never silently fall back to global proxy.
6. Run Cargo tests and the existing offline build workflow. This checkpoint itself is documentation only; no code tests are claimed as run.
