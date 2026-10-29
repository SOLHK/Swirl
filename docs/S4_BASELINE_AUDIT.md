# S4 initial audit and baseline

Recorded 2026-10-23/24 Asia/Shanghai. This is a starting point, not completed S4 acceptance.

## Source identity

- Frozen S3 remote and local HEAD: `9f8af5754d2a932f7b967eea0e64cbc75717e6be` (verified using GitHub API and `git ls-remote`).
- S3 executable/test source: `3c1fdf29cdb847c59680778efd74eb73a727a7fc`; the later commit contains handoff documentation only.
- UI source remains `7056dea1c920cee57208c1aae54b3550a850f758`; subscription integration remains `384dfe7d15a6f37e206f6db0e4768fa07d4f717d`. Both are integrated ancestors. The source inventory and retained failures are in `docs/handoffs/s3-*.json`.
- New independent branch: `work/swirl-s4-final-completion-20261023`. No main/test/source branch is modified. Existing draft PR 28 is an earlier Activity branch, not a new integration base.
- Actual handoffs exist at `docs/S3_MAX_HANDOFF_20261023.md` and `docs/handoffs/S3_MAX_TO_ULTRA.md`; neither required reconstruction from guesses.

## Verified starting state and outstanding work

S3 already integrated the Rust import ABI, transactional DPAPI persistence, cancellation/revision guards, periodic subscription refresh, node identity, atomic runtime configuration, loader identity and QUIC shutdown fix. These are reused rather than reimplemented. Historical S3 counts (680 Rust tests, 28 Qt suites, controlled peers) are not S4 test results.

Outstanding evidence-backed issues:

1. VMess strict target half-close: two retained methods, five failed assertions. Investigate independent official-client and target EOF behavior; preserve original assertions.
2. Public Shadowsocks HTTPS: HTTP 204 succeeds but strict TLS close fails; same-address direct control also fails. HTTP completion and authenticated closure remain separate results.
3. Candidate portable package includes an unlisted `Swirl-diagnostics.txt` written by UI smoke after manifest generation. Final staging must exclude runtime diagnostics and recheck exact inventory and hashes after smoke.
4. sing-box TUIC/HY2 projection gaps: protocol allowlist and nested TLS/obfs options require lossless Rust-owned mapping and actual peer fixtures.
5. Common Rust has an existing `swirl-platform` adapter for host-file discovery; extend boundary checks and actually run applicable target checks. Non-Windows UI/key storage/tunnel implementations are outside this Windows delivery stage.
6. UI pooled node latency state needs identity-aware verification. Large subscription operations and first-use long frames need measurement; current evidence does not establish a navigation memory leak.

## Same-machine native motion baseline

Existing S3 executable, Qt 6.10.3, Windows D3D11, DPR 1.5, display refresh 240 Hz. Raw local evidence: `D:/Codex/outputs/s4/ui-baseline/motion.json`.

| Metric | Baseline |
|---|---:|
| Motion correctness failures | 0 |
| Median frame interval | 4.1275 ms |
| P95 frame interval | 5.5319 ms |
| P99 frame interval | 62.7856 ms |
| Frames over 50 ms | 8 / 470 |
| Warm P95 frame interval | 4.9591 ms |
| Working set at motion measurement | 397,901,824 bytes |
| Repeated-navigation working-set growth | 311,296 bytes |
| Idle frames during harness window | 1 |
| Cached pages after visiting all routes | 16 |

Frame interval is not input-response latency, cold-start latency or animation duration. This sample is not a long-duration leak test or an idle-CPU percentage measurement. Additional startup, 100/500/1000/2000-node, response and memory comparisons must be reported separately.

Initial DPI harness requested scale 1 but observed native DPR 1.5, so its scale assertion failed. Preserve that failure and correct the harness environment before claiming 100% coverage. Window geometry must not be changed to satisfy the test.

## Validation environment

Local compiler: Rust 1.99.1 Windows GNU; Qt 6.10.3 MinGW. Isolated S4 Qt test build was configured successfully. Production CI uses Windows MSVC and fixed Qt 6.11.3; these are distinct environments. No installer has been produced for S4 at this checkpoint.

GitHub HTTPS required the already configured local proxy for command-line Git; only a per-command `http.proxy` option was used. No system networking settings were changed.
