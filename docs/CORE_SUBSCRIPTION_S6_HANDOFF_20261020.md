# Swirl Core S6 — Windows SS fixture recovery, exact-source CI pending

## S7 continuation prepared after S6 peer gate

At source `598a8a77400236e6f817a1e4782f1c4f0da4bbd0`, Windows Rust
fmt/check/Clippy/test/Release, independent protocol peers and the native
subscription-to-target step succeeded in
[Rust run 39297859906](https://github.com/SOLHK/Swirl/actions/runs/39297859906).
[App run 39297859893](https://github.com/SOLHK/Swirl/actions/runs/39297859893)
and portable Linux/macOS Rust jobs completed successfully. The Windows Qt
product and complete application gates were still in progress at this note;
their terminal results and raw logs must be fetched separately.

S7 adds real Qt product-route assertions for DOMAIN-SUFFIX, DOMAIN-KEYWORD and
DST-PORT, preserving the existing A/B switch, NodeStore/DPAPI restoration,
ordered DIRECT/REJECT/MATCH, verified HTTPS and authenticated close assertions.
Local Windows Qt/Rust execution passed across four proxy protocols with the
source-file hashes and raw synthetic evidence saved in
[`s7-local`](evidence/subscription-product-chain/s7-local/). No private
subscription or credentials were used. Formal acceptance remains
**79 / 6 / 10.83%** until the exact committed SHA finishes CI.

Development branch: `work/core-completion-20261017`. This is a bounded
checkpoint for continuation, **not** a statement that the product's entire
subscription-to-internet flow has been accepted.

## Current remote and source baseline
- S1: `292df3ba9763414947ec9b5dffa7886c45a00879` — strict subscription boundaries.
- S2: `593e7cddc360cf7f51d9fdc988e6cf8fd99aea96` — selected real exits and independent HTTP/HTTPS origin matrix; Windows DPAPI wrapper added.
- S3: `41555465b72fd59d42bc473f0d097c93e210c240` — reject unsupported nodes in DIRECT mode, protect SNI aliases.
- S4: `a066f7d4c8acb96f5d6a46cee5700b2590328b64` — fixture socket ownership, TLS close tests.
- S5: `0416fe09fce4f4d5599c5a859842331f7783ebb3` — TLS proxy-path close and App Inspector; Rust CI 39291365493, App CI 39291365689.
- GitHub HEAD on S6 assembly is concurrent and must be re-fetched; do not assume that a chat-visible local source remains available after interruption.

## Exact known CI status before S6
- S5 `39291365493`: Linux portable Rust **success**, macOS portable Rust **success**. Windows Rust fmt/check/clippy/test/release all succeeded but Windows independent policy peer failed. Windows selected-node Qt/DPAPI, full native app build and later peer steps were **skipped**.
- S5 `39291365689`: App/Core validation **success**, including actual Inspector subscription peer step.
- Do not count prior S4 or local synthetic proxy results as Windows Qt/DPAPI application acceptance at S5/S6.

## Cause and scoped S6 correction
The independent `SsPolicyPeer` in `tools/tests/test_policy_groups.py`
obtained TCP port zero repeatedly and checked whether that OS-selected port was
also eligible for UDP. Windows repeatedly returned candidates inside a UDP
exclusion range, exhausting eight bounded attempts despite eligible ports
existing elsewhere. It was not justified to treat permission code 10013 as
a retryable address collision.

S6 now selects from the existing `windows_candidates(False)` TCP/UDP
intersection before either bind; shuffles with `SystemRandom` and bounds
attempts to eight. Both real sockets are held as a pair. A TCP or UDP
EADDRINUSE/WinError 10048 can retry; an unknown access denial, WinError 10013,
resource exhaustion, or a table-query failure propagates unchanged.
Pre-bind `SO_EXCLUSIVEADDRUSE` is applied separately to both Windows sockets.
Non-Windows port-zero behavior remains unchanged.

New and adapted unit cases cover candidate-only addresses, eight distinct
retryable collisions, immediate access failure, real socket ownership and
pre-bind option ordering. No vendor subscription, credentials or font binaries
are involved in CI.

## Next strict gates
1. Fetch exact S6 HEAD and jobs. Run `cargo fmt --all -- --check`, `cargo check --workspace --locked`, `cargo clippy --workspace --all-targets --locked -- -D warnings`, `cargo test --workspace --locked`, `cargo build --workspace --release --locked` in `core`.
2. Require Linux, macOS, Windows independent peer and raw-subscription-to-target suites. Specifically verify S6 Windows policy fixture finishes; do not weaken collision/error assertions.
3. Require Windows Qt NodeImporter → encrypted NodeStore/DPAPI → EngineController node A/B selection → Rust Core → independent proxy A/B → real HTTP/HTTPS origin, including authenticated TLS closure, DIRECT/REJECT routing, session pinning and failed-node no-fallback.
4. Require complete Windows `Swirl.exe` build **after** product tests, and App/Core validation on the same exact executable commit.
5. Save raw job logs, source SHA, run URLs, failures/skips and precise scope in `docs/CONTINUE_DEVELOPMENT.md`, `docs/SELF_DEVELOPMENT_PROGRESS.md`, and this handoff. Retry with small new commits if failing. Never force push or edit `main`, `test`, fonts or unrelated UI.
6. User-provided private subscription was inspected separately: 59 VLESS/REALITY entries, 55 requiring Vision. The production async REALITY/Vision path, DirectReady and TLS/socket ownership transfer remain unaccepted. Import/parameter retention may be tested privately, but no node may silently downgrade to TLS/TCP/DIRECT. Never put the URL or token into public CI/logs.
7. Formal baseline remains **79 / 6 / 10.83%** until a complete frozen acceptance item is evidenced.

## Important execution limitation
This checkpoint's new S6 patch was assembled through the connected GitHub API
from reviewed remote source after a lost transient local worktree. The previous
local user's screenshot mentioned S6 22/22; that claim is historical and is **not
a rerun of this exact new blob**. Exact-source CI must supply its own evidence.
