# Swirl unified test build: real nodes, imports, subscriptions and motion

The unified build combines phase-two real-node code with motion commit
`35e79781f8aaab51d55b528f28a156d9dcba81ea`. It preserves real empty states and
does not restore the old demonstration statistics.

## Import and updates

- The node page's **一键导入** accepts clipboard text, local `.yaml/.yml/.json`
  files, pasted Clash configurations, individual Clash node objects, and an
  HTTPS URL for a one-time download. Only the `proxies` node list is imported.
- The existing subscriptions page saves an encrypted HTTPS URL, display name,
  enabled state and update interval. Intervals are six hours, twelve hours,
  daily and weekly. Updates run while Swirl is running, including when minimized.
  Due subscriptions update on startup; this does not install a Windows service.
- **更新全部**, per-source refresh, editing and removal are real operations.
  Removing a subscription retains its downloaded nodes as manual nodes.
- Full configurations' global settings, rules, providers and TUN/DNS/listener
  settings are not applied. This is node import, not unrestricted configuration
  execution. A provider-only file without an actual `proxies` list is rejected.
- Empty, malformed, oversized or failed downloads preserve the previous nodes.
  Source replacement is atomic. Matching source/name/protocol retain node IDs;
  removed active nodes disconnect. Changed active source configurations restart
  the owned engine with the selected ID. An explicit stop during an update is
  respected and cannot be undone by the delayed response.

## Protocol support

The registry follows the outbound transports in the pinned **Mihomo v1.19.32**:

`socks5`, `ss`, `trojan`, `http`, `ssr`, `vmess`, `vless`, `snell`, `hysteria`,
`hysteria2`, `wireguard`, `tuic`, `shadowquic`, `gost-relay`, `ssh`, `mieru`,
`anytls`, `sudoku`, `masque`, `trusttunnel`, `openvpn`, `tailscale`, `zerotier`,
`easytier`.

`direct`, `dns`, `reject` and `rematch` are routing actions, not remote nodes.
Swirl does not implement these protocols' network handshakes. Mihomo receives
the preserved protocol options and performs the actual protocol validation and
transport. Support is bounded by the capabilities of the packaged Windows engine.

The manual form supports common credentials and private JSON extension options;
complex transports should be imported from a valid Clash/Mihomo node object.
Existing private options are never prefilled into the UI. Blank fields retain
existing credentials. JSON extension keys merge into existing private options.
Use import to replace an entire complex node configuration.

## Security and bounds

- Existing SHA-256/version verification, API authentication, exclusive loopback
  ports, Windows Job ownership, deadlines and process cleanup remain enabled.
- Node credentials, extension options and token-bearing URLs share the existing
  atomic Windows DPAPI store. Schema-one files without subscriptions/options
  remain compatible. There is no plaintext fallback.
- Public QML DTOs contain redacted node/source summaries. Network errors and YAML
  exceptions do not include server responses, input text, passwords or URL tokens.
  The form clears submitted/closed credential fields.
- TLS verification is mandatory. Unsafe certificate bypass, local file references,
  executable/script fields, chosen host interfaces/routes and extra listeners are
  rejected. Inline certificates/keys are supported. EasyTier listeners are disabled.
- Download redirects are bounded to five, HTTPS downgrade is rejected, TLS checks
  remain enabled, and HTTP is accepted only for literal loopback test endpoints.
- Input is limited to 4 MiB, 2,000 nodes, bounded nesting/expansion and 256 KiB of
  private options per node. The encrypted store retains its existing 1 MiB bound;
  exceeding it fails atomically. At most 32 subscriptions are saved.
- Downloads use a 15-second transfer timeout and 30-second overall deadline;
  automatic failures retry no more often than every 15 minutes. Parsing runs in
  a worker; the Qt UI thread commits only a complete validated result.
- Neither Windows proxy/DNS/routes nor a system TUN are enabled by this feature.

## Window and branding

The native DWM border remains disabled because Qt owns the antialiased HDR
outline. A one-physical-pixel theme-aware Qt outline makes overlapping pale
windows distinguishable without changing their radius or layout. Runtime Windows
icons are rasterized directly from the existing knot SVG; executable and installer
icons continue to use the canonical SVG-derived ICO. No SVG artwork is changed.
Already pinned shortcuts to older installations can retain Windows' old cached
icon; installing this build updates Swirl's installed shortcuts but does not
delete unrelated shortcuts or reset the user's global icon cache.

## Validation scope

`SwirlImportTests` checks all 24 protocol registrations and encrypted persistence,
YAML anchors/transport/TLS preservation, malformed and unsafe input, real source
downloads, stable selection, automatic scheduling, stale-on-error behavior and a
real controlled SOCKS5 chain with active-source A-to-B replacement.

`SwirlNodeTests` checks real HTTP/HTTPS forwarding, explicit selected exits,
switching, failures and cleanup. Additional samples use the packaged Mihomo for
configuration/start checks of HTTP, VMess, VLESS, SSR, Snell, Hysteria/Hysteria2,
TUIC, AnyTLS, SSH, gost-relay, Mieru, ShadowQUIC and TrustTunnel. These configuration
checks do not prove their remote handshakes. No real remote subscription or node
credentials have been supplied to these automated tests.

`Swirl --node-self-test` also exercises one-click import through QML and a real
request through the imported node. Motion, all pages, capture, engine lifecycle,
native window composition and GPU FP16 tests are retained. Native capture rejects
Windows secure-desktop interruptions rather than treating unrelated screenshots
as Swirl evidence. Exact results are recorded in the delivery report.

Sources: [pinned Mihomo parser](https://github.com/MetaCubeX/mihomo/blob/v1.19.32/adapter/parser.go),
[Mihomo proxies](https://wiki.metacubex.one/en/config/proxies/),
[fkYAML v0.5.0](https://github.com/fktn-k/fkYAML/releases/tag/v0.5.0).
