# Native Windows TUN: implementation and evidence

## Baseline and isolation

Work branch: `work/native-tun-windows-20261030`.
Audited baseline: `4ad8a23b7fd59f0f8c09f1e3547548b16baaf4e9` (`main`).
At checkout, `test` was `9d35542e092474056f6c154af351dbd84bf7fff4`,
one merge commit behind main. The latest `work/swirl-0219-clear-glass-20261029`
head (`6941ea37d5fe8dac128f38eca273d72aadbee1e0`) was already an ancestor
of main. The requested TUN branch did not previously exist.

This change does not edit Qt/QML, visuals, fonts, icons, or the parallel UI
branches. It does not promote test/main or authorize a release. The older
promotion instructions in AGENTS.md describe a different candidate.

## Stage A: findings from implementation

| Existing component | Source evidence | Reuse / missing functionality |
| --- | --- | --- |
| V2 runtime | `crates/swirl-core/src/v2.rs` | Immutable routing snapshots, prepare/activate/finish/rollback transactions, admission, node revocation and session records already exist. Incoming TCP is currently coupled to the HTTP/SOCKS handshake. Extract one common flow dispatcher. |
| Native TCP/UDP protocols | `crates/swirl-protocol/src/`, `swirl-core/src/socks5_udp.rs` | Native stream and datagram outbounds already exist. Reuse their authentication, transports and bounded UDP associations. No local SOCKS hop and no second protocol engine. |
| Rules and policy | `crates/swirl-routing/src/{v2,mrs}.rs`, `swirl-core/src/policy_v2.rs` | MRS domain/IP classification, service policies, rule tiers, fallback policy and explicit reject already exist. Evaluate once at flow admission. |
| DNS | `crates/swirl-dns/src/{lib,wire,dot,doh}.rs` | A/AAAA, bounded resolver concurrency, TTL/negative/failure caches, hosts, verified DoT/DoH and policy-selected encrypted query transport exist. Incoming DNS service and a reliable IP-to-domain identity do not exist. |
| Platform | `crates/swirl-platform/src/lib.rs` | Only the system hosts-file path exists. No Wintun, Windows network transaction or crash recovery backend exists. |
| C ABI | `crates/swirl-api/src/{lib,control_v2}.rs`, `include/swirl_api.h` | Versioned bounded JSON command ABI exists. TUN capability is explicitly false. Extend the control boundary without changing the existing UI. |
| Qt bridge | `src/Swirl.Quick/engine/{RustCoreEngine,EngineController}.cpp` | Both explicitly reject TUN at the audited baseline. Do not turn that UI control on before backend integration and acceptance. |
| Outbound network path | `swirl-protocol/src/dial.rs`, `swirl-transport/src/{udp,quic}.rs` | Direct sockets currently follow the system routing table. Full-tunnel routing therefore needs physical-interface binding for every TCP/UDP/DNS/QUIC socket, not only an exclusion for one proxy server. |

## Module boundaries

`swirl-tun` owns L3 packet admission, bounded smoltcp TCP sockets, UDP packet
adaptation, packet/flow queues and cancellation. smoltcp owns the TCP protocol
state machine, retransmission, windows and checksums. Wintun supplies IP packets;
it is not a TCP stream.

`swirl-core::v2::FlowDispatcher` owns the existing routing, DNS selection, native
protocol dialing, session bookkeeping, statistics and revocation rules. Both
the system proxy and TUN enter that dispatcher. A failed proxy path never changes
into DIRECT.

`swirl-dns` owns DNS wire validation and the bounded fake-address mapping. A
fake address must identify exactly one canonical name for its entire lifetime;
an expired or unknown fake address fails closed. A public address cannot safely
be reverse-mapped to a unique domain because multiple names can share it.

`swirl-platform` owns the small Windows FFI boundary, verified absolute driver
loading and typed network state transactions. Route/DNS mutation is confined to
an explicitly invoked privileged helper, with a durable pre-change journal and
ownership checks during recovery. The GUI remains unelevated.

## Dependency decision and risks

- Evaluate Wintun 0.14.1 and the MIT `wintun` Rust binding; verify the exact
  version, integrity and third-party notices before shipping a driver.
- Reuse smoltcp rather than implement a TCP/IP stack. Its exact locked version,
  features, MSRV and license must be recorded with the implementation.
- Do not directly adopt `netstack-smoltcp` 0.2.4: source inspection found
  unbounded internal channels, per-SYN allocations without tuple deduplication,
  and an invalid-UDP path which can terminate the stream. A bounded Swirl
  adapter over smoltcp avoids importing those semantics.
- System DNS inside an active tunnel can recurse into that same tunnel. Strict
  native TUN requires explicit encrypted DNS servers with numeric bootstrap
  addresses and interface-pinned network egress. Missing prerequisites fail
  validation instead of silently using the OS resolver.
- Intercepting UDP/TCP 53 is not a complete Windows DNS leak firewall. WFP,
  multihomed Windows DNS and application-owned encrypted DNS require separate
  acceptance. Do not advertise leak prevention merely because the packet DNS
  service works.
- Route rollback must compare current values with the values installed by this
  session. Never overwrite changes made by a user or another VPN after startup.
- The build host is Linux. Cross-compilation and mocked Windows transactions
  are not Windows 11 TUN, network-switch, sleep/wake or application acceptance.

## Implementation order and evidence policy

1. A: inspect the current implementation and record boundaries (this document).
2. B: add bounded TCP/UDP packet adapter, Wintun lifecycle and native flow entry.
3. C: connect dual-stack DNS identity, native outbounds and flow lifecycle.
4. D: add interface-pinned egress, ownership-aware network transaction/helper,
   then verify recovery and networking changes in disposable Windows only.
5. E: expose versioned control/diagnostics, run portable and Windows builds,
   record exact test source and unresolved real-machine acceptance.

Each stage is a separate commit. A stage is only accepted to the extent supported
by its evidence. No changes to the current development host's routes, DNS,
system proxy or driver installation are permitted or required for local tests.

## Acceptance record

At the architecture commit, no TUN data-plane tests or real Windows TUN tests
have run. Later commits will append commands, outcomes and explicit limits here.
Successful Actions builds alone will not change real Windows items to passed.
