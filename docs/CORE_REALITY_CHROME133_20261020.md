# REALITY / Vision / Chrome133 continuation — 2026-10-20

Only `work/core-completion-20261017` is authorized. The initial remote was
`85f4cb916221fb64b9c07f0cd6fd85bbc7e94883`. The first repair was pushed as
`54908e2902c28ae20e2588fa5347df9b2b3d76e9`. Concurrent font commit
`24119489f7b85fe58dea53acf3a4a6f467a6e8fa` was independently re-read, checked for
overlap and retained by fast-forward before this implementation. No force push,
main/test changes, private subscription retrieval or provider credentials are
part of this work. Frozen acceptance stays **79 items / 6 accepted / 10.83%**.

Chrome133 source was pushed as `a3b89050e141557444519c8c17f2a263e6a013fc`.
Subsequent font-only commits `ef564245f5de600757b7283437c7daf31a1e90e9` and
`4927316c74f935099a5648cefacc13ae0d1f2772` were independently fetched, inspected
for overlap and retained by fast-forward. A later Windows run exposed a real
fixture allocation failure even though a3b8905 passed; that failure and the
source repair are recorded below rather than being hidden by the earlier pass.

## Original CI failure and source identity

| Source | Rust workflow | App workflow | Observed conclusion |
|---|---|---|---|
| `169e0cad51fc18a2d6fa4f194fafd90128bf2f7b` | [39362403837](https://github.com/SOLHK/Swirl/actions/runs/39362403837) | [39362403822](https://github.com/SOLHK/Swirl/actions/runs/39362403822) | Both successful, including the Windows full application build. |
| `85f4cb916221fb64b9c07f0cd6fd85bbc7e94883` | [39363969382](https://github.com/SOLHK/Swirl/actions/runs/39363969382) | [39363969436](https://github.com/SOLHK/Swirl/actions/runs/39363969436) | Failed: TLS 1.3 origin certificate fixture lacked Authority Key Identifier under strict Python/OpenSSL validation. The affected 9-case menu had 8 successes and 1 error. |
| `54908e2902c28ae20e2588fa5347df9b2b3d76e9` | [39366092611](https://github.com/SOLHK/Swirl/actions/runs/39366092611) | [39366092691](https://github.com/SOLHK/Swirl/actions/runs/39366092691) | All successful, including the actual Qt/DPAPI/network menus and complete Windows application build. |
| `a3b89050e141557444519c8c17f2a263e6a013fc` | [39368450317](https://github.com/SOLHK/Swirl/actions/runs/39368450317) | [39368450338](https://github.com/SOLHK/Swirl/actions/runs/39368450338) | All successful: native and Chrome133 menus on all platforms, Linux public origins, Windows Qt/DPAPI and complete Swirl.exe build. |
| `ef564245f5de600757b7283437c7daf31a1e90e9` | [39368769057](https://github.com/SOLHK/Swirl/actions/runs/39368769057) | [39368768977](https://github.com/SOLHK/Swirl/actions/runs/39368768977) | App/Linux/macOS successful; Windows failed while creating a DNS fixture with WinError 10013. Later Windows protocol/Qt/application gates did not run. |

The repair gives the temporary CA proper key usage and SKI, and leaf certificates
AKI, SKI, digital-signature usage and serverAuth. The local TLS 1.3 verifier also
explicitly enables X509_STRICT, so Python 3.12 cannot conceal the newer CI check.
Certificate verification was not disabled. The original P1 failure was not a
Vision assertion that could be skipped or weakened.

Original App archives were actually downloaded: all 326 P0 / 333 P1 files
matched their Git blobs, with trigger, tested and tar commit IDs equal. The
54908e2 archive also contains 333 matching files, an empty source diff and no
untracked source. App now runs `ApplyCoreDevelopment.py --check` and read-only
format checks, asserts the trigger SHA before and after execution, and exports
that same commit. It no longer formats, commits or pushes a different tree during
validation. Missing reviewed workflow gates fail the updater check.

The App token now requests read-only contents access and no workflow-write
permission. This is a scope reduction for validation, not a change to the App
installation, repository secrets or the user's branch authorization.

Downloaded 54908e2 Linux evidence establishes HTTP 200 with the expected 22-byte
Microsoft Connect Test body and HTTPS 301 from `www.rust-lang.org`, using normal
certificate verification and authenticated TLS close. REALITY and Vision both
passed; the Vision HTTPS request recorded one Direct command in each direction,
one authenticated official Xray session and one actual public TCP connection.
Reports explicitly say `provider_connection=false` and `direct_fallback=false`.
This is public-origin evidence through a controlled official Xray server, not a
real subscription-provider connection or Windows GUI acceptance.

The downloaded Windows Qt P0/P1 artifacts each have 1/1 successful product-chain
case with zero skips. Vision's A node recorded Direct upload=1/download=1; B did
not have a successful HTTPS request and correctly recorded zero Direct commands.
The evidence includes ten HTTP paths, one verified HTTPS close, a 262180-byte
echo/half-close transfer and no origin errors. The updated Qt gate explicitly
requires those A-node Direct observations rather than only framing activity.

## Completed Chrome133 CI and a subsequent Windows allocation repair

The [a3b8905 exact-SHA audit](evidence/CORE_REALITY_CHROME133_CI_20261020.json)
records downloaded artifacts, their hashes, actual test results and source
identity. Every Rust platform and App passed 320 ordinary Rust tests and one
doctest; each passed 14 REALITY component tests, 4 Vision component tests,
4 independent uTLS oracle tests, native Runtime menus of 8/8 and 10/10, and
Chrome133 Runtime menus of 8/8 and 10/10. These protocol menus had zero failures,
errors or skips. General Python suites still report their explicit unavailable-Qt
skips; Windows later executes the applicable Qt menus with actual binaries.

The three Windows Qt Runtime artifacts (native REALITY, native Vision and
Chrome133 Vision) each passed 1/1 with no skips. Each retains ten HTTP paths,
strict verified HTTPS, a 262180-byte echo/half-close transfer, persisted DPAPI
configuration and A/B observations. Both Vision A nodes recorded upload and
download Direct commands. B's deliberately unsuccessful HTTPS request correctly
records no Direct transition. The final build log contains the actual
`build/rust-qt/Release/Swirl.exe` link output and the required file-existence
check passed. This is hosted Windows product-chain evidence, not physical GUI
or private-provider acceptance.

All four Linux public-origin artifacts also passed: native/Chrome133, with and
without Vision. HTTP returned the expected 22-byte body with status 200;
strict verified TLS 1.3 HTTPS returned status 301 with authenticated close.
Each request records an authenticated REALITY/VLESS session and an actual public
TCP connection through the official controlled Xray server. Both Vision HTTPS
paths recorded Direct in both directions. There was no DIRECT fallback.
The App source archive contains 468 files whose blobs all match a3b8905, with
equal trigger/tested/archive commit IDs and empty source diff/untracked-source
records. Its generated identity marker files are not source modifications.

The ef56424 Windows failure occurred before the certificate-negative test could
run: the DNS fixture's first TCP bind requested `127.0.0.1:52786` and returned
10013. Neither the before nor after excluded-port table included 52786. There
was no contemporaneous endpoint/PID snapshot, so the historical owner or exact
OS denial cause remains unknown. An unexcluded randomly chosen number is not
an owned free port; that source defect is directly observable and repaired.

DNS and paired Shadowsocks fixtures now request TCP port zero and retain the
actual server socket while checking known TCP/UDP exclusions and binding UDP
to the same port. Windows sockets request `SO_EXCLUSIVEADDRUSE` before bind;
`SO_REUSEADDR` is not used. Known excluded TCP candidates remain held until
selection exits, so a sequential allocator can pass an entire exclusion block
without selecting the same still-owned endpoint. These finite-set prechecks
are separate from the unchanged budget of eight actual EADDRINUSE/10048
collisions. Unknown 10013 and other failures still propagate as the original
exception, with cleanup and the protocol/address/attempt context. The related
dual-family fixture uses the same ownership and separate-budget rules.

New regression cases cover the 200-port exclusion sequence, retained descriptor
ownership, no UDP bind to excluded candidates, cleanup on all exits, port-zero
requests, real exclusive/wildcard incumbents and actual TCP/UDP data. Simulated
OS allocation sequences are distinguished from actual socket forwarding tests.
Failure-only CI diagnostics retain local TCP/UDP endpoint/state/PID snapshots;
these later snapshots do not retrospectively prove the failed port's owner.
The repair needs its own exact-SHA CI and cannot inherit a3b8905's success.

The [local repair checkpoint](evidence/CORE_LOOPBACK_PORT_OWNERSHIP_LOCAL_20261020.json)
retains source hashes, all earlier failure logs and the passed allocation,
Rust, Xray, oracle and Runtime results. Additional local complete policy/DNS
runs exposed intermittent deadlines: one CONNECT probe timeout, two DoH
timeouts, a later UDP `DnsTimeout` and a DoT recovery request returning 502.
The latter observations are not claimed fixed by the allocation change.
`DnsTimeout` alone does not distinguish the 900ms UDP endpoint deadline from
the 3s total budget, and the 502 log did not record its internal error.
Bounded unchanged diagnostic runs passed without establishing the historical
cause. The sequential policy menu passed 21/21; the final complete instrumented
DNS menu passed 43/43 with zero failures, errors or skips in 124.511 seconds.
That passing trace measured long heartbeat gaps and cgroup CPU throttling;
Python CPU and some other events advanced during the gaps. This does not prove
a whole-process freeze or explain the earlier failures, which lack complete
timing traces. All four complete DNS outcomes, source and binary hashes, and
the trace limits are preserved in the checkpoint. New exact-SHA CI remains an
independent gate. No timeout, certificate check or test assertion was relaxed.
These failures remain an open local investigation, not overwritten by a later pass.

## Implemented profile and ownership

The existing native Rust Runtime still owns sockets, cancellation, routes,
VLESS framing, Vision and shutdown. No Xray/sing-box executable or Go runtime is
linked or launched by production Swirl. Test-only official processes remain
independent peers.

`rustls`, `chrome` and `chrome_133` are the only accepted explicit fingerprints.
The two Chrome names select **Chrome133**, the `Chrome_Auto` profile in the locked
uTLS oracle, and remain distinct original strings in stored/source configuration.
They do not mean current/latest Chrome, Firefox, generic uTLS or complete browser
behavior. Missing, unknown and conflicting profiles still fail explicitly.

The opt-in rustls 0.23.46 hook runs before transcript hashing and transmission.
It retains exact encoded bytes, updates offered-extension/cipher state, and
preserves the random, SessionID, SNI, ALPN and every actual key share. Both the
offline preview and authenticated constructor share one per-connection GREASE,
ECH and extension-permutation object. Their complete first flights must agree
after inserting the authenticated SessionID. Socket-layer rewriting is not used.

The wire profile includes the pinned cipher and signature lists, GREASE,
extension permutation, X25519MLKEM768 plus an **independent** X25519 share,
supported versions/groups, ALPS offer, GREASE ECH and real Brotli decompression.
The separate classical and hybrid X25519 private owners are consumed by the
corresponding negotiated branch. REALITY's SessionID authentication uses the
standalone share when offered, matching upstream; it does not accidentally use
the hybrid component. Certificate HMAC, Ed25519 CertificateVerify and TLS Finished
remain mandatory. Failed negotiation never becomes ordinary TLS or DIRECT.

The default Chrome ALPN offer is exactly `h2,http/1.1`. Empty source ALPN remains
empty in IR and selects this documented profile default; an explicit override
must be exactly that ordered list. Unsupported ALPN is rejected, not discarded.
The native profile retains its existing custom ALPN behavior.

Actual outer negotiation is TLS 1.3 only. HRR, real ECH, resumption/0-RTT, QUIC,
unsupported selected extensions (including ALPS), Firefox and other profiles
remain explicit failures. The ALPS offer does not claim implementation of ALPS
negotiation. ClientHello compatibility is not proof of browser-identical record
timing or resistance to every fingerprinting method. Inner HTTPS TLS 1.2 remains
supported through authenticated non-Direct Vision; inner TLS 1.3 can enter Direct.

In the exact locked official REALITY server, authenticated TLS 1.3
[EncryptedExtensions](https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/handshake_messages.go)
are generated locally and have no ALPS negotiation field. Therefore this ALPS
limitation does not block that server's authenticated path, even when the
camouflage target supports ALPS. This source-level finding does not extend to
provider modifications, future versions or unauthenticated transparent traffic.

## Strict subscription and Qt adaptation

Rust Inspector and the actual Qt normalizer preserve the critical values through
URI, Base64, Clash YAML/JSON, sing-box JSON and the supported Xray JSON subset.
The Xray mapping accepts one legacy `vnext` endpoint with one user or the newer
simplified outbound settings, explicit raw/tcp, REALITY, `encryption=none`,
SNI, publicKey/password, shortId, fingerprint and optional exact Vision flow.
Equal aliases are accepted; conflicts, multiple users/endpoints, unrecognized
nested fields, active mux and TCP obfuscation are rejected. Global Xray policies
remain preserved source data, not automatically executable policies.

sing-box's enabled uTLS is accepted only with an explicit supported Chrome
profile. Disabled uTLS with a fingerprint, inferred/missing fingerprints,
unknown options or conflicting top-level aliases cannot silently change meaning.
Qt no longer writes `fingerprint=rustls` regardless of source. It preserves the
actual profile in Rust IR, checks the untouched source and refuses old inferred
Chrome defaults. NodeStore's existing generic serialization preserves parameters,
original configuration and conversion issues without a format migration.

`spiderX` is still preserved and explicitly unsupported, including an explicit
empty value. In the locked Xray source it controls crawling after unsuccessful
REALITY authentication; Swirl implements failure without that crawler. It would
be incorrect to erase the field just to raise the executable-candidate count.
The pinned Xray REALITY settings do not define an ALPN override; unknown source
fields are not silently accepted.

Qt tests extend the real importer, encrypted NodeStore save/reload and
RustCoreEngine configuration path across these formats. The dedicated Windows
Runtime test still enters through NodeImportService and EngineController, uses
DPAPI and recreates the product objects before requesting the origins. Its new
Chrome/Vision menu must pass in the exact-SHA Windows job before claiming that
product integration is verified. It passed in the a3b8905 job and downloaded
artifact described above; the local environment has no Qt SDK.

## Independent references and licenses

| Reference | Exact reviewed version | Role and license boundary |
|---|---|---|
| [Xray-core](https://github.com/XTLS/Xray-core/tree/92ccc939aaf4f8965f369cf0b142e005aeaa11d5) | v26.10.17, `92ccc939aaf4f8965f369cf0b142e005aeaa11d5` | Independent official server and field definitions; MPL-2.0; test-only. |
| [REALITY](https://github.com/XTLS/REALITY/tree/83f621788ca88b83179810b12baa7ae518aacb83) | `v0.0.0-20261014101318-83f621788ca8` | Official authentication/record behavior; retained source/license in peer build evidence. |
| [uTLS profile](https://github.com/refraction-networking/utls/blob/aa6edf4b11af82e110eea845bb2983d30138d651/u_parrots.go) | `v1.8.3-0.20260301010127-aa6edf4b11af` | Independent wire oracle using real uTLS state; BSD-3-Clause; not a production dependency. |
| [sing-box](https://github.com/SagerNet/sing-box/tree/v1.14.3) | v1.14.3, released 2026-10-09; go.mod uses metacubex/utls v1.8.7 | Configuration/design comparison; GPL-3.0-or-later; no implementation copied or linked. |
| [rustls](https://github.com/rustls/rustls/tree/f04804fa13341a9b1dc02b5d1dd8a746f2c4b7fb) | 0.23.46, same previously locked version | Maintained TLS library with six modified upstream files plus one adapter file; Apache-2.0 OR ISC OR MIT. |

The vendored rustls archive digest, revision, licenses, modification list and
upgrade procedure are in `core/vendor/rustls/SWIRL-PATCH.md`. Brotli support adds
only alloc-no-stdlib 2.0.4, alloc-stdlib 0.2.4, brotli 8.0.4 and
brotli-decompressor 5.0.3; existing locked package versions are not upgraded.
`DEPENDENCIES.json`, the collection script and the packaged browser-TLS license
bundle include the vendored dependency and all newly required notices.

## Verification and evidence boundaries

The independent oracle compares actual finalized native first flights against
real locked uTLS. It normalizes only legitimate randomness, GREASE values and
extension permutation. It checks fixed fields, ordered lists, payload families
and independence of the two X25519 public shares. The native profile is a
negative control. Nine wire mutations must fail; fresh keys, randoms, ECH and
permutations are checked across eight separate instances per browser alias.

Local results at this checkpoint: fmt/check/strict Clippy, **320 ordinary Rust
tests + 1 doctest**, all passed; the hook has 9 focused tests; the browser backend
has independent authenticated handshake and failure tests. The uTLS oracle
passed 4/4 and official REALITY component passed 14/14, all with zero skips.
Final complete Runtime menus passed **8/8 REALITY and 10/10 Vision for each of
native rustls and Chrome**, zero failures/errors/skips. Chrome covers six imported
formats, 512 KiB Direct transfer, strict verified HTTPS, route/selection behavior,
cancellation and authentication failures. Added SOCKS5 DOMAIN CONNECT performs
actual HTTP and verified HTTPS requests in both profiles and both flow modes.
The [local checkpoint](evidence/CORE_REALITY_CHROME133_LOCAL_20261020.json) retains
the actual precommit source state and hashes; it is not an exact-commit CI result.

An initial Chrome interoperability attempt failed because both controlled
camouflage targets only had Ed25519 certificates, which Chrome133 does not
offer. Actual Xray logs showed successful SessionID authentication followed by
an incompatible target handshake. The Go target now offers both ECDSA P256 and
Ed25519 through standard TLS certificate selection; the Python target selects
the compatible fixture certificate for the declared profile. Production profile
constants and all authentication/Finished/data assertions remain unchanged.

The initial local Chrome public probe stopped at `PublicDnsFailed` before public
TCP, and correctly recorded an uncommitted working tree. It is not public acceptance.
Linux CI adds separate Chrome REALITY and Chrome Vision public gates alongside
both native gates. Linux/macOS/Windows/App keep all earlier native menus and add
the oracle and Chrome menus. Windows adds actual Qt/DPAPI Chrome Vision before
the full application build. These a3b8905 gates subsequently passed as recorded
above. CI gate/shell-failure tests pass 54/54 locally.

Do not convert historical private subscription counts (59 REALITY, 55 Vision,
59 retained URIs, previously zero native candidates) into current connectivity
claims. The private file/cache on the user's Windows computer has not been read,
decrypted or refreshed here. Once exact-SHA CI finishes, use the existing local
saved subscription without refreshing it, retain credentials locally, and return
only candidate counts, supported combinations, authentication/Direct/HTTP/HTTPS
outcomes and redacted error codes. Provider selection/availability, physical
Windows GUI behavior and the frozen acceptance matrix remain separate gates.
