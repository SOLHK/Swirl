# Swirl 0.1.9 automatic subscription import

The subscription page no longer asks for full-profile versus node-only mode.
Legacy persisted scope values remain readable for snapshot compatibility but
cannot override the downloaded content during a subscription refresh. Format
preferences negotiate a response with the server; recognition uses its actual
contents, never the provider name, URL suffix or preference.

Portable Rust owns DNS, rule and group translation. Ordinary node documents
keep the existing Swirl network policy. Compatible profiles apply atomically
with source-owned node IDs. A recognized unsupported feature may keep the
valid nodes and current policy only after a separate whole-document safety
audit. An earlier compatibility error cannot hide a later script, file
reference, extra listener or host network operation. Unknown capabilities are
closed by default.

Reduced-scope imports have a persistent warning and encrypted inert original
configuration. No retained original is ever executed. Each subscription's
result is removed with that subscription, in the same atomic node-store write.
Manual nodes, other subscriptions and unowned historical data remain separate.

Managed update headers are validated and preserved as metadata. They do not
replace Swirl's explicit subscription URL or update interval, and never cause
extra downloads. The card explains this boundary. Client-only settings are
validated and preserved without modifying Swirl's UI, log or test settings.

Trojan subscription requests to skip certificate validation are strengthened
to validation enabled, with the original encrypted and a visible notice.
Runtime or manually supplied bypass requests remain prohibited. A valid
certificate is still required; this does not make self-signed, expired or
wrong-name providers usable. See V019_TROJAN_SECURE_IMPORT.md.

Codex's fresh-child launcher now supplies an explicit Chromium proxy switch in
addition to native child environment settings. Actual forwarding failures are
recorded once per connection using fixed error and phase vocabularies and
opaque node references. No account tokens, targets or arbitrary error strings
are copied into these events. See V019_CODEX_PROXY_CHAIN_20261024.md.

The user's failure3 bundle identifies the tested source as a28258e/0.1.8.
It records owned system-proxy states during the relevant period, and a stopped
engine at export time. The latter cannot establish the earlier failure-time
state. Five new node failures were origin TLS timeouts. Real Codex workspace,
login/chat, provider tests and browser acceptance remain with the user.

Every subsequent delivered update increments PRODUCT_VERSION.txt. It drives
the application, installer, build report and artifact label; an incremental
CMake build also watches this input. The next package is 0.1.9.

The previous a28258e candidate completed its Windows job in 12m36s and its
build/package script in 640.284s. The following f4fa1a5 run passed but missed
the compiler cache: the hosted image changed from 20261022.344.1 to
20261012.333.1 even though recorded MSVC/SDK/Rust versions agreed. The cache
key now uses actual compiler/linker/CMake binary hashes and versions, SDK and
workspace paths instead of the broad image label. Ninja and Cargo dependency
checks remain enabled. This is a cache-key correction, not a claimed measured
cache speedup; each delivery includes its actual timing evidence.

Automated checks use controlled loopback peers and disposable system-proxy
recovery on CI. They do not establish actual provider quality or real Codex
account success. TUN remains unavailable in the current Rust product. The
native format remains deferred until compatibility/network acceptance.

## Initial local checks before the first committed CI

Qt 6.10.3 / MinGW local regression: Core 91 passed, 0 failed, 10 designated
fixture-dependent skips; Import 54 passed, 0 failed, 0 skipped; Subscription
Formats 7 passed, 0 failed, 0 skipped, including 17 download/persist/map formats.
New critical automatic import/native fallback/managed INI/QX/forwarding-log
methods and Trojan certificate tests have no skips. Earlier failed runs are
retained locally; old manual-mode assertions were updated only where the
latest automatic-import requirement replaced that behavior. Script, file,
MITM, listener, busy and persistence-failure rejection checks remain strict.

Portable subscription tests passed 139 cases with the final classifier's five
focused cases rechecked; the profile ABI's three cases passed. Rust Clippy,
format, portable dependency, source/input-cache guard and offline privacy
checks passed. Independent VMess transport and launcher evidence is described
in the P0 note. These local checks do not replace the final committed
CI, disposable proxy recovery and exact-source installer verification.

## Windows CI exposed a real probe-allocation defect

The first 0.1.9 commit, 1c2e362, passed Rust CI but failed Windows run
40089664045 before production staging. The queue recovery test measured 19/24
successful controlled nodes; five failed in local listener allocation, before
any request reached an upstream. The other 12 CTest suites passed. No installer
was produced or delivered from that run; compiler-cache output is not a pass.

NodeTestService unnecessarily required UDP availability on the same temporary
TCP port, although the Rust runtime binds only a TCP listener. The replacement
lets Rust atomically bind loopback port zero for isolated probe workers. This
also removes the Qt-reserve/close/Rust-rebind window. An internal C++ capability
defaults off and cannot come from a subscription or saved settings; ordinary
application port-zero requests remain invalid. The adapter publishes only the
strictly validated actual bound port, retaining the original zero request for
worker reconfiguration so the existing listener is reused.

Windows UDP exclusions are a plausible trigger for the old extra check, but
the failed CI did not record its OS error code. This defect cannot explain all
of the user's old failed nodes: the new failure3 report records origin TLS
timeouts instead. No expected success count, TLS policy or request assertion
was lowered to make the queue pass.

The atomic-listener follow-up passed its new real-listener/GET/HEAD/selection
test without skips; the unchanged 24/24 recovery and cancellation case passed
three consecutive runs. The complete local Core suite passed 92 cases, with
0 failures and the same 10 designated fixture-dependent skips (42.477s).
The earlier Import and Format results remain valid for unchanged parsing
logic; final exact-source Windows CI reruns the required suite set before
an installer can be delivered.
