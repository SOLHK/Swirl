# Explicit physical-interface subscription downloads

Version: 0.2.35 candidate. This page contains no private URLs, response bodies,
node addresses or credentials.

## Problem and evidence

The reported failure included an HTTP 403 before parsing. Independent requests
using different HTTP clients and TLS implementations also received that refusal
while traversing the existing third-party TUN. Merely disabling a client's HTTP
proxy did not bypass that TUN. A public HTTPS control confirmed that pinning one
socket to an active physical adapter used a different network exit without
changing host routes, DNS settings, the proxy or the TUN.

The owner then authorized exactly one fresh request to the original subscription.
It returned HTTP 200 and 30,032 bytes over verified TLS with the socket pinned to
that adapter: one GET, no retry and no redirect. The body was immediately stored
with local DPAPI protection. This was an independent diagnostic request, not a
claim that the subsequently implemented product path had already passed.

The rebuilt Qt importer parsed that body offline: 90 records, two coalesced by
the existing semantic identity rule, 88 nodes saved and reloaded from a separate
DPAPI store, and 88 candidates mapped through the paired Rust library. None were
incomplete. This check sent no network request and does not establish that those
nodes can connect or that the full foreign configuration can execute.

## Product behavior

- Each source has a persisted `downloadRoute` of `system` or `physical`. Existing
  sources default to `system`; editing through an older call preserves an
  existing explicit choice. Invalid types and values fail at the store boundary.
- Windows exposes the physical choice as a source setting with a clear notice
  that it bypasses the system proxy and VPN/TUN for that subscription download.
  It is never selected automatically after a 403. Non-Windows UI identifies the
  choice as unavailable and requires the user to select the supported route.
- Qt retains HTTPS, normal certificate validation, original signed URL bytes,
  the existing same-origin redirect policy, response-size cap and total deadline.
  Physical mode requires HTTPS. The default system/PAC path remains available.
- The native Rust bridge uses an ephemeral loopback CONNECT listener with random
  authentication and a single fixed host/port. It selects active hardware
  adapters with a default gateway, pins both DNS and outbound sockets, and uses
  that adapter's configured DNS servers. It rejects private/fake-IP destination
  answers and never falls back to a different download route.
- The bridge is limited to eight active leases, four concurrent clients per
  lease, sixteen accepted clients per lease and a thirty-second lifetime.
  Cancellation, completion, timeout and service destruction revoke the lease
  and its child tasks. No external core, downloader binary or interpreter is
  part of this runtime path.
- Only the source's download preference changes. Saving it does not enable
  subscription updates, change selected nodes or apply a network policy.

## Reference approach

Primary GitHub sources informed the design; no upstream implementation was
copied:

- [Microsoft IP_UNICAST_IF documentation](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/WinSock/ipproto-ip-socket-options.md)
- [Microsoft adapter enumeration documentation](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/iphlpapi/nf-iphlpapi-getadaptersaddresses.md)
- [Tokio TCP socket API](https://github.com/tokio-rs/tokio/blob/master/tokio/src/net/tcp/socket.rs)

## Validation boundaries

Controlled checks exercise authenticated CONNECT, fixed-target rejection,
two-way relay and half-close, cancellation and native expiry, DNS transaction
validation, DNS TCP framing, Qt certificate rejection, HTTP 403 without a route
fallback, redirects, negotiation, late startup cleanup, strict persisted route
decoding and source review/adoption. Final execution counts and source identity
belong in the delivery receipt and exact-commit CI results.

The candidate was built with all related Qt targets paired to native build ID
`3541f0ab7d081d3f5f90ea3335be11da4d2fd85213cef6eb0899fe3baa803a56`.
The complete import suite passed 84 cases, the network-policy suite passed 16,
catalog transactions passed 46, and the node UI CTest passed. Five additional
critical CTests (LAN control, policy configuration, downloads, formats and import
boundaries) passed. The workspace ran 1,159 passing Rust tests with three
privileged cases left for CI; the final site-local-address correction separately
re-ran all twelve native route tests successfully.

A fixed public Cloudflare GET then traversed the real `NodeImportService`,
paired FFI bridge, physical sockets and Qt's normal TLS validation: HTTP 200,
Qt error zero, one request, 2,012 ms. Its non-subscription response was rejected
without applying configuration. An independent Qt TLS control through that
bridge also passed. The separate IANA example-site control failed issuer-chain
validation (Qt error 6 / SSL enum 11); that failure remains recorded. No
certificate exception, alternate trust policy or route fallback was added.

These are local candidate results based on parent `a2dd8d0` plus the recorded
changes, not exact-commit CI results for a later push.

The separately frozen one-hour controlled TLS/SSE workload uses the earlier
`f4efe047858c9470b64071aeb620809316e75db7` runtime. It cannot certify this new
download bridge, real providers, physical TUN routing, Codex Desktop or a
performance ratio against another client. Real subscription refreshes and node
tests remain subject to the owner's explicit testing window.
