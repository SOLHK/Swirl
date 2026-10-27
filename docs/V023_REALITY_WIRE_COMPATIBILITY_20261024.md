# Swirl 0.2.3: authenticated REALITY client version

The production protocol adapter encoded `[0, 1, 0]` in the encrypted REALITY ClientHello session ID. This is a protocol implementation compatibility version, not Swirl's package version. Official servers with a minimum accepted client version reject that value before a VLESS session reaches its target. Previous low-level fixtures supplied a newer version explicitly, so they did not catch the production caller error.

The adapter now uses `[26, 10, 17]`, the independently inspected protocol baseline pinned by `tools/tests/xray_peer/lock.json`. This does not claim that all Xray features are implemented. Unsupported certificate profiles and other features still fail their existing validation. No key, certificate, timestamp, SNI, UUID, server version-bound or endpoint verification is bypassed.

Primary references inspected:

- [Pinned REALITY server implementation](https://github.com/XTLS/REALITY/tree/83f621788ca88b83179810b12baa7ae518aacb83): authenticated client version/time and server acceptance bounds.
- [Pinned Xray core](https://github.com/XTLS/Xray-core/tree/92ccc939aaf4f8965f369cf0b142e005aeaa11d5): the source baseline independently exercised by the existing full-server fixtures.
- `tools/tests/transport-peer-lock.json`: the current official release used by the repeatable candidate gate is Xray 26.10.21; its archive/binary/version/commit provenance is verified separately from the source-built oracle.

## Reproduction and validation

On this Windows host, before the change, two production-runtime positive cases against the official release rejected the tunnel. Server observations decrypted the client version as `[0,1,0]`, recorded zero authenticated sessions and no target traffic. These are actual independent server processes and verified HTTP/HTTPS origins, not mocked success.

After the change:

- Focused Chrome raw: 5/5; rustls raw: 6/6; Chrome Vision: 8/8. The final stale-clock assertion was strengthened after review and rerun in all three profiles, each passing.
- Protocol unit tests: 122 passed. Clippy with warnings denied and Rust formatting passed.
- The added candidate CLI selector was run locally with rustls: 6/6, 12.576 seconds, zero skipped. It exercises import from URI/YAML/JSON/base64 through the production Runtime, verified HTTPS, accepted minimum/exact intervals, rejected incompatible intervals, stale authenticated hello, and wrong authentication/UUID.
- The CI selector runs those six cases for rustls, Chrome and Chrome Vision. It reuses the same already downloaded hash-pinned Xray peer and Cargo debug cache as the VMess gate. It requires exact test counts and zero skipped. The source-built oracle remains a separate verification path.
- Independent review found no production blocker. It strengthened cancellable socket cleanup and required two server-decrypted ClientHellos in the stale-clock test; both changes were applied before commit.

## Actual supplied subscription: still unverified networking

The supplied source was downloaded once with the real Qt downloader and returned HTTP 200. Its response remains encrypted locally. No private URL, credential, decrypted profile or account log is included here or sent to CI.

After rebuilding the paired release ABI and Engine and relinking the isolated Qt importer, the existing encrypted response was imported into a fresh store: 59 records, 56 saved nodes, 55 eligible candidates. Current global settings remained unchanged. The same two actual Google HEAD probes still failed with `RealityAuthenticationOrHandshake`, phase `outbound_handshake`, HTTP 0. The protocol version fix alone has **not** restored the supplied nodes' actual connectivity.

The independent official Xray control also failed those actual nodes, including a bounded plain-HTTP follow-up. This does not identify which component or provider condition is responsible. It is not evidence that all supplied nodes are unusable, nor that Swirl implements every required feature.

No subscription was re-downloaded for this comparison. No active system proxy, Clash, TUN, routes, DNS, Codex process or account state was changed. Private-provider, Google/YouTube and real Codex workspace/login/chat acceptance remain explicitly unverified. The installer is a diagnostic test candidate.
