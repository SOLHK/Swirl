# U1 read-only Core observation integration

## Scope and provenance

This is a selective integration onto `aa5f7d10e5b43b4e6168171d3b4d306308727210`.
The initial remote snapshot is `U1-source-snapshot.json`. The following five
source commits are not ancestors of that baseline and have no identical stable
patch IDs in its non-merge history. They are independent Windows diagnostic
tools, not implementations of a proxy engine.

| Source branch | Full source commit | Function selected | Treatment |
| --- | --- | --- | --- |
| `work/core-completion-20261017` | `70a18d58f2aafa41072fb422bfd0e4d6d342fb2f` | Observe Swirl-owned TCP sockets and possible local Mihomo chains during bounded HTTPS requests | Retain manual `Test-SwirlMihomoPath.ps1` and wrapper; pass optional expected source SHA to the identity check. It observes existing processes and never starts/stops/downloads Mihomo. |
| `work/core-completion-20261017` | `75bc81d5ae6fb4b7955b06ebd410f7267c628ac8` | Privacy-minimal Core report, passive connection sampling, loopback IPv4/IPv6 fixture | Retain monitor, configuration and private-loopback checker. Exclude the separate NSIS installer, its build script, background launcher and registry-autostart/stop helpers. |
| `work/core-completion-20261017` | `00b9f50973fc14dc4c912c694c344d064e790a20` | Passive samples between explicitly requested active checks | Retain counters, sampling interval and reporting. Default is one manually invoked cycle; continuous sampling requires `-Continuous`. |
| `work/core-completion-20261017` | `83e36ee40399c4f14f7b6257d744709c47e1ee1c` | Hash hidden files and preserve probe reason codes | Preserve stream-based SHA-256 and bounded diagnostic states. Share package validation with executable fixture tests. |
| `work/core-completion-20261017` | `f87b6f98eb7018c4a5e86f281fe707764565ce58` | Reject 32-bit process inspection | Retain checks requiring 64-bit PowerShell. Installer changes are excluded because no monitor installer is delivered by U1. |

The older identity checker from
`2c2992e35c203ea242485dc919955234de764c3c` was already in the baseline. Its
existing file is updated; a second checker/database is not introduced.

Stable source patch IDs, respectively:

```text
70a18d58f2aafa41072fb422bfd0e4d6d342fb2f  0b60d2fa8cc2daea87cf7560817d1fe38ae4d363
75bc81d5ae6fb4b7955b06ebd410f7267c628ac8  13c55dd4a2827551e6c419a0103888b167619524
00b9f50973fc14dc4c912c694c344d064e790a20  36852ad20cf5093ffff5647765ca35cf42dc0eaf
83e36ee40399c4f14f7b6257d744709c47e1ee1c  64ca139781c5c2395f96eb18e8812aba22ea804b
f87b6f98eb7018c4a5e86f281fe707764565ce58  ae88d5996c767e868d955ce6a9f3b37df4ffc921
```

The integration intentionally changes behavior, so its patch ID is not expected
to equal those source commits. Commit trailers identify the sources; selective
diff review, rather than an identical-patch claim, establishes coverage.

## R1 identity compatibility

Current product staging (`scripts/Stage-WindowsRustProduct.ps1`) writes
`package-manifest.json` and `swirl-rust-build.json`. It does not write the old
`PRODUCT.json`/`BUILD.txt` pair. The old checker therefore blocked on a valid R1
package. `tools/SwirlCoreIdentity.ps1` now validates either format:

- Current packages require both files, identical source SHA/build ID/ABI/target,
  unique safe manifest paths, and correct hashes for the executable, Rust DLL,
  Rust metadata, and both packaged China MRS files.
- Historical packages require the original explicit Rust-only declaration,
  source SHA, enabled build flag and matching executable/DLL hashes. Reports
  identify this as `legacy-product-preview`; they do not claim R1 build pairing
  or verified rule assets.
- Any mixture of old/new metadata, incomplete pair, mismatching expected SHA,
  duplicate/path-traversal entry, or altered file is rejected. A new incomplete
  package cannot silently fall back to an old manifest.
- Live inspection additionally checks the listener owner, the loaded DLL path,
  unexpected proxy-core modules, files replaced after process start and a real
  local SOCKS5 greeting. No DLL is loaded by the metadata checker.

These checks establish local package consistency. They are not a signature or
publisher-authenticity check, and the report explicitly says so.

## Manual use

From a **64-bit Windows PowerShell** session:

```powershell
# Local identity and SOCKS greeting only: no public request.
./tools/Test-SwirlCoreOffline.ps1 -Port 7898 -ExpectedSourceSha <full-tested-SHA>

# One passive snapshot: writes its own local report only.
./tools/Monitor-SwirlCore.ps1 -PassiveOnly

# One bounded public observation through an already running, verified listener.
./tools/Monitor-SwirlCore.ps1 -ExpectedSourceSha <full-tested-SHA>

# Optional continuous manual invocation; does not install autostart.
./tools/Monitor-SwirlCore.ps1 -Continuous -ExpectedSourceSha <full-tested-SHA>
```

The default output directory is `%LOCALAPPDATA%/SwirlCoreMonitor`; it can be
changed with `-DataDirectory`. Only the monitor's own reports and configuration
are written there. No system proxy, registry autostart, DNS, routing table,
scheduled task, service or firewall configuration is modified. A public check
uses a fixed HTTPS target and the existing Swirl listener; it does not import
credentials or enable a proxy. The monitor has not been started by this task.

The original `Start-SwirlCoreMonitor.ps1` installed a Run-key entry by default.
That behavior, its stop helper's registry edits and all installer hooks are
excluded. `Run-SwirlCoreMonitor.cmd` invokes the foreground script directly.

## What these observations do and do not prove

| Observation | Evidence provided | Still not established |
| --- | --- | --- |
| Offline checker | Package consistency, loaded DLL path, owned local listener, SOCKS5 greeting | External proxy handshake, DNS or routing correctness |
| HTTPS path observer | Responses through the listener, sampled Swirl-owned TCP sockets, observed local chain if present | Exclusion of all transparent WFP/TUN interception, QUIC/UDP socket ownership, exact rule name or DNS egress |
| Private loopback fixture | Unique local IPv4/IPv6 HTTP request arrives through the selected listener | Active route name; saved `routingMode` is only a saved preference |
| Monitor report | Timestamped aggregate observations and reported source SHA | Unified product acceptance, provider credentials, Windows manual UI acceptance |

The path observer remains inconclusive when transparent-routing indicators
exist, or TCP sampling cannot establish an outbound. A working Hysteria2/TUIC
QUIC path can consequently be inconclusive; it is not reported as a failed
protocol. The local fixture's `-SelfTest` bypasses all proxies explicitly and
does not claim a Swirl route test. No source branch's earlier test result is
promoted to a result for the U1 integration SHA.

## Other independent source differences reviewed

| Full source commit | Finding from source and history | U1 treatment |
| --- | --- | --- |
| `2b186783a704af3f4c1a91cd835997485282e2ec` | Engine/telemetry notification coalescing, stable patch ID `43c6a8b07913f1fc2eb065c0c8c60dbab4637ed9` | Parent U1 performance integration owns the selective port; this commit does not overwrite it. |
| `9e892b3746012ef8b1d983467b45cf6f336ddbe7` | Accurate full HTTPS timing label, stable patch ID `64cb1547a1d03ccc4871adc986d4d39ef68d3006` | Parent U1 performance integration owns the native measurement semantics. |
| `bbb4ea33d3a3ae596027b840af630260ba6bdbcc` | Nodes-only import and latency display mixed with version/UI changes | Nodes-only adaptation is `dbfdc0bd355383234aecb1a537accaa5b9e592ca`; it preserves D5/D6 rather than reverting to the old implementation. |
| `871cc6e93a083c8624aadae8d9f4c1fe8db6e7e8` | Old nodes-only format assertions | Relevant assertions are adapted in the same nodes-only commit, without restoring Mihomo tests/runtime. |
| `505216bc5007c9a8181c2d18490a50baa2b812c5` | `periodTraffic` helper and monthly chart test are used by the separate blue-glass Activity redesign; no current U1 consumer | Excluded with that independent visual project; not a network/accounting repair. |
| `e2254f4e321b6112dd3135989907a2664fba4928` | Independent DoH schema (`https_servers`) differs from the integrated `tls_servers[].https_path` model; stable patch ID `895936f2d8b50bafe6063274eb1e097187fba4aa` | Do not reintroduce a competing resolver model. Current DoH is implemented by `c6f4b4d0e2e9c3449ee0d21b8b2b6a043753374e`, wired by `e12b1a21f182111b16598d0f82784498bd58c080`, then extended by `95b4fbc8f58b166a93fcc10b648bef39d396c4d6` and `f81eab6e2eaf5a2d9f1f538a4ce04cde268797c0`. `git range-diff` confirms the patches are independent, not identical duplicates. |
| `564e213ce604d7b79bb2414cd3aefba5744d46eb` | Separate WinINET/native-registry diagnostic reporting; current `SystemProxySession::refresh` only exposes WinINET enabled state | Reported to parent as a separate developed-but-not-integrated diagnostic change. A future port must preserve current stronger recovery/ownership logic; this monitor-only commit does not overwrite it. |
| `49559fa5fa6ad999086afc2444ac17ed35945657`, `361053d5bed9238d8e15772bdf0b52800df64495`, `de28acb405a4863b27c065bf9232d062efc36171` | Old SystemProxy/ActivityTelemetry/Mihomo architecture mixed with independent UI work | Superseded by current SystemProxySession, unified telemetry and Rust-only runtime; do not restore obsolete engines or parallel models. |

## Regression and remaining classification

Run `tools/tests/Test-SwirlCoreIdentity.ps1` on the exact integrated SHA. It
creates local synthetic packages and exercises current/legacy success,
mixed/incomplete metadata, expected-SHA mismatch, source/build/target mismatch,
changed DLL/EXE/rules, required entries, path collisions/traversal, bounds,
hidden-file hashing and read-only script/one-cycle guards. It does not contact
the Internet or start the monitor. `core-observation.yml` runs it on Windows
PowerShell 5.1, Windows PowerShell 7 and Linux PowerShell 7, recording SHA and
PowerShell version in its artifact.

- **A — code limitation:** socket observation is TCP-only; QUIC ownership and
  active DNS/rule-name evidence need a separate observation extension. Those
  rows remain inconclusive, never fabricated passes.
- **B — developed but not integrated:** the optional monitor installer and
  autostart helpers are deliberately excluded; the separate system-proxy
  diagnostic patch is reported above.
- **C — unified regression:** source-level and local fixture checks are not the
  parent branch's final CI result. Re-run this workflow at the final U1 SHA.
- **D — real environment:** live Windows module/listener inspection, existing
  subscription/provider connectivity and observed exit routing require a real
  user-authorized Windows session. None is claimed by fixture tests.
