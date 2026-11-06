# Private subscription QA: current gate and historical fixtures

`SwirlPrivateSubscriptionAcceptance` is a Windows-only QA target under
`SWIRL_BUILD_CORE_TESTS`. It is excluded from the product package and does not
change the production downloader, system proxy, DNS, routes or TUN settings.

The default invocation refuses networking. `--self-test` uses synthetic data
and loopback fixtures only; `--offline-body` decrypts a local response and checks
the actual importer and an independent encrypted NodeStore round trip.

## Current 0.2.40 live boundary

`--live` unconditionally returns `AuthenticatedBillingAndWireGuardRequired`
before reading a private manifest, creating an output directory or starting a
network runtime. A fresh authorization window does not bypass this refusal.
`PrivateSubscriptionBudget.py` also remains offline-only: neither a parsed
`subscription-userinfo` header nor a successful reservation is a live grant.

The persistent ledger can store a separate TCP byte quota and a receive-buffer
reservation for every allowed connection attempt. Failed durable writes poison
the session until it closes and reloads actual disk state under the exclusive
lock. Existing baselines, local counts and outstanding reservations survive a
schema-1 to schema-2 upgrade. Official account growth and local socket bytes
remain separate; account growth can include other clients.

The optional Rust `private-acceptance` build provides one process-wide TCP
quota, an immutable deadline of at most 8000 ms, cancellation during connect,
and shutdown of registered idle sockets. Pending-connect cancellation still
requires its future to be polled; a stalled runtime requires an external
supervisor to terminate and await the dedicated process. Guarded UDP, OS resolver lookups and
the separate physical-download path fail closed. A parent must reserve the
full byte limit plus 1 MiB for each permitted connection attempt before launch.
Socket reads/writes include TLS and protocol framing, but do not measure IP
headers, retransmissions or unread kernel data. These controls do not establish
complete wire accounting or provider billing.

Live execution still requires a fresh authenticated provider snapshot, one
stable ledger, a protected dedicated process, demonstrated coverage of every
egress path, and confirmed process/task exit before provider reconciliation
and settlement. The original Windows private ledger and DPAPI inputs must
remain in their controlled environment; a new empty ledger is not a substitute.
Never unblock the legacy command with a boolean or by removing its early return.

The cumulative policy remains decimal 2/5/10/15/20 GB with at least 80 GB kept
available. The first live round must contain at most 12 executable nodes, at
most three concurrent attempts and an eight-second deadline per attempt.
Prefer HTTPS 204 and cap ordinary GET bodies at 64 KiB. These are required
admission conditions, not evidence that live execution has occurred.

## Historical capture harness (unreachable from `--live`)

The legacy path expected a local DPAPI manifest, UTC start/end times for a
window of at most ten minutes, and a fresh absolute private output directory
outside a Git repository. Its manifest expected six sources. URLs and
credentials were never CLI arguments or public report fields. This old path
has thirty-second source deadlines and can traverse every imported node, so
it does not meet the current bounded live-round contract. Its existence is
neither authorization nor a ready execution path. The following descriptions
and historical checks concern that earlier harness and its retained fixtures.

Each source uses a separate Qt HTTPS client through native `start_once` with
normal certificate verification, at most thirty seconds and four MiB. Redirects
and format-negotiation retries are not followed. This dedicated QA downloader
differs from the production downloader's normal negotiation behavior. A missing
single-use operation fails closed instead of selecting ordinary `start`.

Qt 6.12 may replay an idempotent GET after an unexpected EOF. Even its public
custom-request API remaps a custom GET back to the GET operation. Consequently,
one API call is not evidence of one request. The native single-use tunnel
permit is consumed atomically after authentication and exact-target validation,
before DNS/origin access; subsequent reconnects cannot reach another origin
connection. Authentication challenges do not consume that permit.

Original URLs, response headers/bodies, source stores and detailed node results
are stored only with user-bound DPAPI. Public results contain source/node
ordinals, fixed classifications, HTTP/Qt codes, counts and numeric timings.
Existing source files are never overwritten. Imported records are semantically
deduplicated by the existing store, with both pre/post counts reported.

Node probes reuse `NodeTestService` with no more than three active nodes. Each
new group checks both the UTC deadline and a monotonic budget; expiry cancels
downloads/probes and reports untested nodes. Probes retain the existing HEAD
and 2xx-success semantics. The fixed public probe path was independently
verified to accept HEAD; a GET-only trace endpoint had returned 404 for HEAD
and was rejected for this purpose.

Source downloads use physical interfaces. Node probes use the current network
routes with isolated node options; they do not prove an independent physical
egress, UDP/QUIC, full foreign configuration execution, physical TUN, Codex
Desktop or real-node throughput acceptance. HTTP-header time is not RTT.

## Historical executed checks (not current-source live acceptance)

- Actual native RED/GREEN followed by **15/15** route tests, including wrong
  authentication/target before the permit, concurrent claims and the real ABI.
- Full Rust workspace: **1,162 passed, zero failed, three privileged cases
  reserved for CI**.
- **21/21** QA self-checks: encrypted receipts and reload; strict wire GET/query
  bytes; no body; no redirect; TLS rejection; size/deadline/timeout bounds; an
  origin that closes after a complete GET; and a real NodeTestService/Rust
  loopback probe checking HEAD, target path, 204 and worker release. In the EOF
  case Qt tried three connections, while the gate admitted one upstream and
  the origin received exactly one GET. The native tests independently verify
  the real atomic admission rule; the loopback gate is not a production bypass.
- A frozen real body again parsed 90 records and saved/reloaded 88 nodes after
  existing semantic deduplication, without network requests.
- Default invocation and an expired window both refused networking. The expired
  invocation did not create its proposed output directory.
- A fixed public HEAD through the real Qt client, native single-use route and
  normal TLS verification returned HTTP 200 / Qt zero, with no SSL errors and
  successful route cleanup. This was not a private subscription request.

The original system-proxy stop negative control also ran against exact old
controller blobs: all six regression cases failed after successful compilation,
then all passed after restoring/rebuilding current source. Byte hashes were
checked. The runner now also locates the Windows Ninja executable layout;
compile errors, absent cases and failure to restore still fail the gate.
