# S4 protocol closure investigation

Recorded 2026-10-24 Asia/Shanghai. **The two strict network acceptance failures
remain open.** The investigation adds evidence to distinguish timer-driven
socket cleanup from a successful half-close; it does not weaken the tests or
change the runtime to manufacture EOF.

## Source and environment

- Branch: `work/swirl-s4-final-completion-20261023`, base
  `9f8af5754d2a932f7b967eea0e64cbc75717e6be`.
- Windows 11, Rust 1.99.1 GNU, isolated build
  `D:/Codex/build-swirl-s4-closure-20261024`; environment setup
  `D:/Codex/tmp/s4-env.ps1` and pinned peers from the existing S3 cache.
- The VMess production module and original `test_vmess_xray.py` remain unchanged
  from the base. Other agents were integrating separate S4 files concurrently;
  these local binary hashes and relevant-source hashes are evidence for this
  investigation, not a claim that the final integrated SHA was tested.
- Pinned Xray v26.10.21 / `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`, executable
  SHA256 `c77a00eb84fb93ae044c2d771a1cabcc033b81e487253fbc35b12df6879c1e15`.
  The cached release manifest ties it to archive SHA256
  `fc58c39ee2f2717b4c54d28d374362389e5319b20ae44aea76ea45a5243ec827`.
  The official control client and server use the **same executable** in separate
  isolated test roles. Neither enters the Swirl runtime or delivery package.
- No private inputs, system proxy/TUN/routes/DNS changes, Clash termination or
  installed-product replacement occurred. Raw public test sockets do not use
  environment proxy settings; this does not prove the host lacks transparent
  forwarding.

## VMess: bytes and EOF are independent evidence

The unchanged strict suite still fails **2 methods / 5 assertions**. It transfers
4 MiB + 17 bytes with the correct hash, but clean authenticated closure fails.
Ordinary completed-response tests pass **13/13**, including 64 MiB, concurrent
sessions, reconnect, TLS certificate failures and supported imports.

The new `diagnose_vmess_close.py` sends the same 4 MiB + 17 byte pattern through
either the native runtime or the official client's loopback SOCKS listener.
The independent origin first echoes the complete payload, then waits for upload
EOF. Only after EOF does it send a 32-byte SHA256 receipt. The client must receive
that receipt and a clean close. A successful echo or a target EOF occurring
during connection teardown cannot satisfy this stronger diagnostic.

| Path | Echo bytes/hash | Post-EOF receipt | Strict result |
|---|---|---|---|
| Direct socket → origin | Complete | Verified | PASS |
| Swirl → pinned Xray → origin: TCP / TLS / WS / WSS | Complete in all 4 | Missing in all 4 | FAIL, 0/4 |
| Same-version official Xray client → pinned Xray → origin: TCP / TLS / WS / WSS | Complete in all 4 | Missing in all 4 | FAIL, 0/4 |

Server logs record `context canceled` after roughly one second once upload
finishes. The origin may then see TCP EOF, but its post-EOF response does not
reach either client. The initial echo-only diagnostic is retained in the raw
evidence directory because it demonstrated why merely counting target EOF can
be misleading: timer cancellation can produce that event.

The pinned [freedom outbound source](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/freedom/freedom.go)
finishes its upload copier without calling target `CloseWrite`; it waits for
the response/cancellation before full connection cleanup. The
[VMess inbound](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/vmess/inbound/inbound.go)
sets a downlink-only timer after request completion. Source and the two-client
experiment agree that this pinned server path lacks the required target
half-close contract. This is bounded attribution of these fixtures, not proof
that every Swirl protocol path is defect-free.

No production workaround is justified by these results. Accepting a bare FIN,
forcing an early WS close, extending the original deadline or treating a full
echo as authenticated EOF would disguise the missing contract. Future work
requires an independently identified server implementation/version that provides
target half-close and authenticated completion, followed by the unchanged
strict tests on every required desktop platform. The original failed test and
its CI requirement remain active.

## Public Shadowsocks TLS close

The original public test remains **FAILED** at node A / CONNECT / origin-close.
The preceding HTTP request passes; HTTPS verifies the certificate and receives
HTTP 204, then strict unwrap raises `SSLEOFError`. Remaining SOCKS5/node-switch
requests are not executed after the first failure and are not counted as passes.

The direct diagnostic reuses the proxy peer's exact chosen IP
`120.232.233.162`, SNI `www.gstatic.com`, TLS 1.3, HTTP/1.1 and request policy.
Both connections verify the same leaf certificate SHA256
`2f8e8a520600f81073f18b6a06056c162f1e21f97f52e98425750fc031349c43`, return 204,
and fail with `SSLEOFError` at origin-close. Certificate fingerprints and an
explicit `matches_proxy_certificate` field are now recorded. They contain only
public certificate hashes.

The loopback TLS controls pass **3/3**: proper close_notify succeeds, truncation
after 204 fails, and an untrusted certificate fails before HTTP. This supports
source/path-dependent truncation as the public-case explanation. It does not
turn the public gate green or prove the absence of all relay defects. A
controlled public origin and independent device/network acceptance remain
unverified; no hosted origin was available in this task. Cleanup confirms native
stop, process exit and listener release.

## Commands and results

Environment: current repository `tools/tests` on `PYTHONPATH`; native binaries
from `D:/Codex/build-swirl-s4-closure-20261024/debug`, pinned peer paths from
`D:/Codex/tmp/s3-native-env.ps1` with S4 evidence paths overridden.

```text
cargo build --manifest-path core/Cargo.toml --locked --offline -p swirl-core --example transport-runtime -p swirl-protocol --example transport-client -p swirl-api --bins
cargo test --manifest-path core/Cargo.toml --locked --offline -p swirl-protocol vmess
python tools/tests/test_vmess_xray.py
python tools/tests/test_vmess_xray.py --strict-half-close
python tools/tests/diagnose_vmess_close.py --output D:/Codex/outputs/s4-protocol/final-vmess-receipt.json
python -m unittest -v test_vmess_close_diagnostic
python -m unittest -v test_r1_public_proxy.PublicTlsControlTests test_r1_public_proxy.R1PublicProxyTests
```

| Check | Actual result |
|---|---|
| Native examples / API build | Exit 0; GNU `.drectve` linker warnings retained |
| Existing focused Rust VMess tests | 11 passed / 0 failed / 0 ignored; unrelated test cases filtered out |
| Ordinary independent VMess response menu | 13 passed / 0 failed / 0 skipped |
| Original strict VMess menu | 2 methods, 5 failed assertions, exit 1 |
| Post-EOF diagnostic | Direct 1 passed; Swirl 4 failed; official control 4 failed; exit 1 |
| Diagnostic classification regressions | 4 passed; truncation, missing receipt, target errors and corrupt bytes cannot be promoted |
| Controlled TLS close tests | 3 passed |
| Original public SS test | 1 failed, exit 1; same-address/same-certificate direct diagnostic also failed |

Raw logs/reports are retained at `D:/Codex/outputs/s4-protocol`. The committed
[evidence index](evidence/S4_PROTOCOL_CLOSURE_20261024.json) records hashes and
compact actual results. Cross-platform execution, final source identity and L5
acceptance are separate outstanding gates.
