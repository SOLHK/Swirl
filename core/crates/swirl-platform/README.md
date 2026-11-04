# Windows native TUN platform boundary

The portable network core still forbids unsafe Rust. This crate uses `deny(unsafe_code)` with narrowly scoped exceptions for loading a verified Wintun DLL, locating the Windows system directory, setting/readchecking physical-interface socket options, and registering/cancelling IP Helper notifications. No platform module loads a driver or changes network state merely by being imported.

## Packet device

`wintun_device::WintunDevice` wraps Wintun 0.14.1 through the MIT-licensed `wintun` 0.5.1 binding. `create` accepts an absolute local DLL path, its expected SHA-256, an adapter name/GUID, and a bounded power-of-two ring capacity. The expected hash must also equal the compiled-in official DLL hash for the target architecture. A file handle disallows concurrent writes/deletion, and dependent DLL loading is restricted to System32. The installed driver directory must be protected from unprivileged modification.

The device exposes complete L3 packets through `receive_blocking`, `try_receive` and `send`. Receive buffers can be reused; received Wintun ring slots are released before any async work. A send-ring-full error is `WouldBlock`. `shutdown` wakes the dedicated reader before its thread is joined. The owning helper must recover network changes before dropping the device. Existing adapters are not adopted or deleted by name.

The driver is not bundled by this crate. The official prebuilt-binary license is retained in `licenses/WINTUN-0.14.1.txt`. Distribution must keep the DLL unmodified and accompany software using only its documented API. Building the GPL driver source and distributing the official signed DLL are different licensing paths.

Official archive: <https://www.wintun.net/builds/wintun-0.14.1.zip>

Archive SHA-256: `07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51`.

## Network transaction

`network_transaction::Journal::prepare` snapshots typed resources for one `InterfaceIdentity { index, guid }`. Index alone is insufficient because Windows recycles interface indexes. Supported resources are interface MTU per IP family, unicast addresses, routes, per-interface DNS, and two narrowly scoped physical-interface DNS firewall rules.

`FileJournalStore` takes an OS file lock, stores a versioned bounded journal, flushes it, and atomically replaces the previous record. A new session cannot overwrite an existing journal. Each write is marked `Applying` durably before the OS operation and `Applied` only after readback. Recovery handles a crash between the OS write and the marker, restoring only a current value equal to the session's recorded value. Unattempted changes and restored resources never reclaim ownership. A disk failure during rollback does not prevent attempts to restore other independent resources. Later administrator/VPN edits are retained and reported as conflicts.

The helper uses `windows_network::secure_state_directory` to obtain the fixed Windows CommonApplicationData/Swirl/NativeTun directory. It obtains the location through Windows, creates directories with protected ACLs at creation time, grants data access only to Administrators/SYSTEM, and restricts implicit owner rights on inherited files. Existing untrusted ACLs, reparse points and unexpected nested directories are rejected. A journal does not confer privilege or authenticate an untrusted IPC caller. System calls/NetTCPIP do not provide atomic compare-and-swap with arbitrary third-party administrators; the backend compares immediately before a change and verifies readback, while the process/file lock serializes Swirl owners.

Compose start changes in this order:

1. `dns_guard_resources` for **all** known physical adapter aliases, including disconnected adapters.
2. `Resource::Mtu { ipv6: false/true }`, using the packet stack's configured MTU.
3. `capture_resources` for virtual addresses, virtual DNS and IPv4/IPv6 split default routes.

The helper must pin all core outbound TCP/UDP/QUIC/DNS sockets to their physical interfaces before adding capture routes. `pin_outbound_socket` sets `IP_UNICAST_IF` or `IPV6_UNICAST_IF` and checks readback. IPv4 sets network byte order but reads host byte order; IPv6 uses host byte order for both operations.

## Actual Windows backend

`windows_network::WindowsNetworkBackend` uses fixed PowerShell scripts with typed JSON stdin and a 30-second operation deadline. It locates the system PowerShell executable through Windows, imports modules only from the system module directory, runs without profiles, and never interpolates user input into executable script text. Mutation checks that the current process is already elevated; it never elevates a GUI or launches an interactive approval.

Routes, addresses, DNS and MTU are confined to the owned non-hardware TUN interface. The physical default routes and physical-interface DNS configuration remain intact. DNS firewall rules block outbound TCP and UDP remote port 53 only on the known hardware interfaces. This closes the LAN-DNS path that more-specific routes would otherwise exempt from `/1` TUN capture. Rule names contain both TUN GUID and session-owner nonce; metadata, scope, protocol, ports, aliases, profile, enabled state and application/security filters are checked before removing them. Existing same-name rules are not adopted. Firewall profiles must be enabled and permit local firewall rules. Encrypted resolver connections on 443/853 are unaffected by these port-53 guards. Capture-recovery conflicts retain the DNS guards for explicit recovery.

`windows_network::snapshot` returns adapters and default/split-default routes. Physical-egress selection rejects existing VPN or non-physical default routes. It does not claim to discover arbitrary third-party WFP per-application VPN policies.

`NetworkChangeWatcher` subscribes to interface, route and unicast address notifications for both families. Its callbacks only set a coalesced atomic flag for changes outside the owned TUN index. The lifecycle task can check that flag without repeatedly launching PowerShell. Closing the watcher cancels registrations before releasing callback state. A cancellation failure retains the small context until helper process exit to avoid freeing memory still referenced by Windows.

## Verification boundaries

Portable tests cover durable sequencing, torn-write recovery states, partial OS failure, disk-full rollback, dual-stack resource plans, MTU restoration, firewall ownership, concurrent file locks and third-party mutation preservation. Windows tests additionally parse the fixed scripts without running their network mutations, reject untrusted driver configurations before loading them, perform IPv4/IPv6 socket-option loopback roundtrips, and register/cancel change notifications without altering network state.

Cross-compilation checks Windows types and API use; it does not run a driver. Real Wintun packet I/O, actual route/firewall/DNS operations, Wi-Fi switching, sleep/wake, crash recovery and packaging need a disposable Windows environment. An added hardware interface not present in the initial DNS guard requires a new guarded session. A host firewall policy changed after startup also requires liveness monitoring. Automatic UAC/service installation and authenticated least-privilege IPC remain integration work; callers must not treat this library as a security boundary by itself.

Primary references:

- <https://www.wintun.net/>
- <https://docs.rs/wintun/0.5.1/wintun/>
- <https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-ip-socket-options>
- <https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-ipv6-socket-options>
- <https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule>
- <https://learn.microsoft.com/en-us/powershell/module/dnsclient/set-dnsclientserveraddress>
