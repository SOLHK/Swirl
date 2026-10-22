# Pinned Xray / REALITY loopback test peer

This directory contains **test instrumentation only**. `main.go` imports the
official, unmodified Xray `transport/internet/reality.Server`, which calls its
locked `github.com/xtls/reality` dependency. Swirl's client protocol remains Rust.
Neither Go executable is linked into, shipped with, or launched by Swirl's
product runtime.

## Source and build identity

`lock.json` fixes Xray v26.10.17 at
`92ccc939aaf4f8965f369cf0b142e005aeaa11d5`, its Git tree and the SHA-256 of its
original `go.mod` / `go.sum`. Its REALITY dependency is
`v0.0.0-20261014101318-83f621788ca8`, full upstream commit
`83f621788ca88b83179810b12baa7ae518aacb83`. The module ZIP and module-file `h1`
checksums are separately locked. Both commits were checked against their
official GitHub repositories; GitHub reported valid verified signatures.

Primary source evidence:

- [Official Xray commit](https://github.com/XTLS/Xray-core/commit/92ccc939aaf4f8965f369cf0b142e005aeaa11d5)
- [Xray go.mod](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/go.mod)
- [Xray go.sum](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/go.sum)
- [Official REALITY commit](https://github.com/XTLS/REALITY/commit/83f621788ca88b83179810b12baa7ae518aacb83)
- [Xray Server wrapper](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/transport/internet/reality/reality.go)
- [REALITY handshake and target observation](https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/tls.go)
- [REALITY transport EOF behavior](https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/conn.go)

From the repository root, with Python 3.11+, Git and Go **1.27.2**:

```text
python tools/Build-XrayPeer.py --output /absolute/path/to/xray-peer
```

The same command works on Linux, macOS and Windows. `--go` selects an explicitly
installed Go executable. `--source` may reuse an existing clean checkout, but
its official remote, exact commit/tree, all tracked files and lock hashes must
still match. The build does not download prebuilt Xray executables. It builds
the complete unmodified `./main` executable and the small Go test entry point
against the original upstream module in `-mod=readonly` mode.

`go mod verify` runs before and after compilation. Go checksum verification is
enabled, automatic toolchain replacement is disabled, and a wrong Go version,
source identity, changed module file, failed download, failed build or changed
helper source is fatal. Build output contains `xray[.exe]`,
`reality-peer[.exe]`, `build.log`, `build-manifest.json` and both `go version -m`
reports. The manifest records the Swirl checkout SHA and worktree status, source
hashes, toolchain identity, exact module identity, executable SHA-256 and failure
state. Keeping the full `build.log` in failed CI jobs is required.

Both executables are built a second time to different output paths using the
same toolchain, fixed source and build flags. Their SHA-256 values must match
the first build; comparison evidence is stored under `reproducible_rebuild`.
This checks same-platform reproducibility with compiler-cache reuse. It does
not claim identical executables across different operating systems or a fully
independent reproducible-build attestation. The complete Xray executable is an
identity-checked reference artifact. Building it does not prove full VLESS,
Vision, configuration import or product runtime interoperability.

## Single-connection JSON interface

The peer accepts one bounded JSON line on stdin:

```json
{"mode":"echo","group":"hybrid","read_chunk":4093,"write_chunk":997,"timeout_ms":8000}
```

`group` is `hybrid` (X25519MLKEM768, 4588) or `x25519` (29). Modes are `echo`,
`unclean-eof`, `stall-handshake`, `stall-data` and `observe-cancel`. Read/write
fragment sizes are 1 through 16384; the absolute peer lifetime is 100 through
20000 milliseconds. Unknown fields and values fail.

The first stdout line has `event: "ready"` and `settings` matching the Rust
`reality-client` example: loopback host/port, test SNI, freshly generated public
key, short ID and synthetic client version. Only random **test** credentials
are emitted. Private keys remain in process memory.

The second line has `event: "result"`. It records REALITY authentication, the
upstream TLS handshake-complete/verified-client-Finished state, negotiated TLS
version/group/cipher, byte counts and SHA-256 of both application directions,
TLS close flags, raw TCP EOF, camouflage application bytes and active socket
count **after cleanup**. Every successfully handled scenario exits zero;
fixture setup, unexpected I/O, invariant or deadline failures exit nonzero.
Wrong authentication is an explicit `authentication_rejected` result, with zero
application bytes. Tests must still validate all positive and negative outcomes.

The pinned REALITY-specific handshake does not populate Go's
`ConnectionState.CurveID`. A bounded read-only observer therefore parses the
selected `key_share` from the actual plaintext ServerHello written to the
socket. It cross-checks the wire TLS version and cipher against the completed
upstream state. The configured/requested group is never substituted for an
unobserved negotiated result.

## Fixture constraints and close semantics

The camouflage TLS target is another in-process **127.0.0.1** listener, using a
new Ed25519 CA and leaf certificate for every case. No system trust store is
changed. It selects only the requested TLS 1.3 key-exchange group, disables
session tickets, emits no application bytes and is subject to the same deadline.

Because this controlled target emits no post-handshake records, the fixture
initializes upstream's exported target-observation cache with the known empty
record list. This avoids its long-running background target probes. No upstream
authentication, certificate MAC, key exchange, Finished, TLS record, fallback or
close implementation is changed. This fixture does not cover arbitrary public
camouflage sites or ticket-producing target behavior.

The upstream Go TLS implementation permits raw TCP EOF at some record boundaries.
The fixture therefore separately observes EOF on the raw socket. It reports
`close_notify_received` only when the TLS reader reports EOF **without** a raw
socket EOF. For `unclean-eof`, it first verifies the client's authenticated
close, then deliberately closes the raw descriptor without calling TLS `Close`.
The Rust client must reject the missing server `close_notify`.

Accepted sockets and the upstream's outbound camouflage socket are tracked.
Cleanup closes both listeners, refuses late registrations, closes every tracked
socket and waits for fixture workers before reporting zero active connections.
No test accesses a private provider, subscription URL, cache, system proxy, TUN
device or external test destination.

All protocol implementation licenses remain in the downloaded upstream source;
the build log and source identities make their provenance explicit. This helper
contains only independently written fixture setup, instrumentation and echo I/O.
