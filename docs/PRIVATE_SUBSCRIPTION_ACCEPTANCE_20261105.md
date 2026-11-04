# Window-gated private subscription QA

`SwirlPrivateSubscriptionAcceptance` is a Windows-only QA target under
`SWIRL_BUILD_CORE_TESTS`. It is excluded from the product package and does not
change the production downloader, system proxy, DNS, routes or TUN settings.

The default invocation refuses networking. `--self-test` uses synthetic data
and loopback fixtures only; `--offline-body` decrypts a local response and checks
the actual importer and an independent encrypted NodeStore round trip.

The explicit live command accepts a local DPAPI manifest, UTC start/end times
for a newly authorized window of at most ten minutes, and a fresh absolute
private output directory outside a Git repository. The manifest contains six
sources; URLs and credentials are never CLI arguments or public report fields.
No live test is authorized by the existence of this tool or this document.

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

## Executed checks before live use

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
