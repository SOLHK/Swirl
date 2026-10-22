# X1.2-B2 recovery and password-protocol completion

Observed 2026-10-22 Asia/Singapore. This phase changes only conversion and
synthetic tests, not a production connector or any private subscription.

## Verified recovery

Fresh `git ls-remote` initially returned
`4606b6df484cd0504014b9bdac6cb237a813c9b3` for
`work/xray-v2ray-json-import-20261021`.

The local older `/workspace/scratch/9ce1017ff3a8/Swirl-X12-B` directory contained
uncommitted drafts with an obsolete projection API. They were not copied over
B1. A second read-only search found the actual published B2 commit
[`4e9f6ea0411c03bba418bb46884748ba7e0ba03b`](https://github.com/SOLHK/Swirl/commit/4e9f6ea0411c03bba418bb46884748ba7e0ba03b)
on `work/xray-v2ray-json-b-20261022`. The GitHub commit API verified its parent
as `4606b6df484cd0504014b9bdac6cb237a813c9b3`.

The isolated continuation branch fast-forwarded to that exact existing commit;
its original SHA and all B1 history are preserved, without replaying B2 under
a new identity. The unrelated Qt/transport/replacement worktrees were read only.

## Completed additions

- Trojan and Shadowsocks keep all password bytes, method spelling, email,
  level, endpoint indices, stream settings and mux in the original archive.
- Official V2Ray `ivCheck` and `ota` fields are type-checked as booleans. False
  remains neutral; true is retained with an explicit unsupported diagnostic.
  No IV-check/OTA implementation is claimed for the native connector.
- Xray cipher aliases and XChaCha20 variants receive known-unsupported
  diagnostics. They are never silently changed to a supported cipher.
- Passwords above the current native 1024-byte limit remain complete in the
  source/projection and are explicitly blocked for native execution.
- Removed nonempty Trojan flow is invalid; protocol-level `level` values
  above 255 are invalid because the pinned Trojan/SS JSON structs use byte,
  despite the shared upstream internal User representation using uint32.

## References rechecked

The following exact commits and LICENSE files were fetched again. Only field
semantics were learned; no upstream implementation or runtime was incorporated.

| Project | Commit | License |
| --- | --- | --- |
| XTLS/Xray-core | `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74` | MPL-2.0 |
| v2fly/v2ray-core | `de610153d59ee0bc9222a17680061d732fa14e7b` | MIT |
| SagerNet/sing-box | `dfb80349bf5779ec0a3f834c9ec2794345bff8f0` | GPL-3.0-or-later plus stated naming restriction |

Source files: Xray `infra/conf/{trojan,shadowsocks}.go`; V2Ray
`infra/conf/v4/{trojan,shadowsocks}.go`, `proxy/shadowsocks/config.go`;
sing-box `option/{shadowsocks,vmess}.go`.

## Actual local validation

Linux x86_64, rustc 1.99.1. The host disk was full, so this session used a
separate memory-backed checkout, copied public Cargo cache and its own target
directory. No other window's source, cache or artifacts were removed.

- `cargo test -p swirl-subscription --locked --offline`: 155 passed,
  zero failures/ignored (89 unit, 11 adversarial, 18 B1, 10 B2, 27 structure).
- `cargo clippy -p swirl-subscription --all-targets --locked --offline -- -D warnings`: passed.
- `cargo check --workspace --locked --offline`: passed.
- `cargo fmt --all` applied; the stage also runs the exact check before commit.

No new native execution or network claim is made at this conversion checkpoint.
B4 handles security/transport capability, B5 produces validated native configs,
and B6 must verify the final exact SHA on Windows, Linux and macOS.
