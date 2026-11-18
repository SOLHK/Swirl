# Native LAN / Gateway engineering audit (2026-10-31)

Base: `test` at `56948e4d6044154f1c5d91c6d817099d1c01a87f`. Native TUN PR #42 is draft at `930c3f5fc2cbcfb99de4769c44f1682f4fc2e01d`, not merged. No claim of Windows 11 real-hardware acceptance is made.

## Existing boundaries

- `swirl-core::v2` owns the loopback-only listener, policy selection, DNS, TCP/UDP native outbound and session accounting. LAN must add a separately owned listener without widening the existing loopback endpoint.
- `swirl-protocol` already parses HTTP proxy, CONNECT and SOCKS5 requests. UDP ASSOCIATE must bind the **local** address, never the remote client's address. All LAN flows must reuse the existing V2 routing and native outbound.
- `swirl-api` provides the JSON control boundary and C ABI; LAN start/stop/status require capability negotiation and real runtime state.
- Qt's existing `GatewayService`, `GatewayRouting`, `DhcpServer` and `GatewayPage` require audit against actual TUN ingress, host firewall ownership and recovery. Saving Qt settings is not proof of a running gateway.
- PR #42 adds a native TUN flow path but has a conflict with current `test` in `.github/workflows/build-qt-quick-ui.yml`. It must be integrated in a separate branch, not merged or silently treated as a released dependency.

## Security gates

Default listener remains `127.0.0.1`. Explicit LAN activation must require a specific private interface, nonempty restricted CIDR allowlist, mandatory credentials, bounded sessions and authentication failures, narrowly scoped Windows firewall rules and owned-rule cleanup. HTTP Basic and SOCKS5 password authentication are not encrypted transports. Never expose the service to a public interface or bind all interfaces by default. The LAN listener must reject localhost, link-local, metadata and host-management destinations, including DNS-rebinding results, before opening an outbound connection.

Gateway remains disabled until there is packet-level evidence of LAN ingress into the Rust dispatcher, correct return translation, DNS/Fake-IP, loop prevention, dedicated LAN/WAN topology, fail-closed IPv6 behavior and transactionally restored Windows network state. Windows Server CI is not Windows 11 physical-device acceptance.

## Test evidence status

Source and dependency boundaries reviewed; no Rust or Qt compiler is available in the current isolated execution environment. Cargo fmt/check/clippy, unit tests, Windows network and independent client tests remain **not run** for this audit commit. No merge into `test` or `main` is authorized before those gates pass.
