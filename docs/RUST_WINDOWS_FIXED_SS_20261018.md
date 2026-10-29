# Fixed cached SS: Windows source-network and dual-source verification

The previous local `MissingArchiveKey` blocker is resolved **without exporting
or rotating the key**. The existing private repository Secret
`SWIRL_ARCHIVE_KEY` was used in memory by the existing Windows self-hosted runner.
The owner's earlier authorization for that runner was verified in the original
chat. All task code, cache reuse, reports and outputs remain under `D:\Codex`;
the runner's existing C-drive bookkeeping is the previously authorized exception.
No private plaintext was uploaded, and no supplier subscription was refreshed.

[Actual private run 39099020539](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39099020539)
finished **success**. Its source is private commit
`df2190a4364bfb8965fff8e8bb1070b5464d8301`; 52 synthetic helper tests passed before
the real operation. [Whitelisted evidence](evidence/RUST_WINDOWS_FIXED_SS_20261018_VERIFIED.json).

## Exact sources and local comparison

The approved local DPAPI manifest/cache was read without modification. The
current GitHub Fernet archive was decrypted only in process memory, and both
local and remote body-integrity checks were required before comparison.

- Local manifest: 18 entries / 17 distinct URLs; remote: 16 / 16.
- **All 16 remote URLs match local entries byte for byte**, including credentials,
  query order and encoding. Local ordering differs, so matching never used ordinal
  position. Serialization-only matches: zero. The two additional local entries
  do not correspond to remote entries; together they represent the one extra URL.
- Local cache: 14 bodies / 12 distinct decoded bodies. Remote: 16 bodies / seven
  distinct bodies. None of the 14 local bodies is byte-identical to a current
  remote body. Both original sources were preserved.
- All 12 locally parsed cached documents have 90 node records. Three SS source
  pairs have identical multisets of executable outbound parameters, including
  credentials and transport parameters, despite differing original documents.
  No hashes or values of those private parameters are included in the report.
- Other original node records differ, and some cannot form executable candidates
  because of insecure TLS or unsupported TCP Fast Open. Two local records remain
  unrecognized. These are explicit compatibility gaps; empty candidate sets were
  not treated as proof that credentials or protocol parameters match.

The result corrects the earlier uncertainty about URL identity. Different body
hashes alone did not mean that subscription identities or SS credentials changed.
The cause of differences between saved formats/content was not established.

## Same immutable old samples, real user Windows network

The diagnostic verified the original 2026-10-17 window ciphertext and subscription
#9 body identity, then used original node indices 1, 2 and 3. It did not substitute
current-archive or local-cache nodes. Each Python/Rust pair kept the existing
10-second total / three-second combined DNS / two-pending-TCP limits.

| Fixed sample | Python DNS / TCP | Rust DNS / TCP | Pair wall time | Strict HTTPS phase |
|---|---|---|---|---|
| 1 | 16 / 47 ms | 4 / 40 ms | 266 ms | TLS 1.3, HTTP 200, orderly close |
| 2 | 0 / 47 ms | 4 / 42 ms | 281 ms | TLS 1.3, HTTP 200, orderly close |
| 3 | 0 / 61 ms | 4 / 39 ms | 250 ms | TLS 1.3, HTTP 200, orderly close |

Each engine resolved one IPv4 / zero IPv6 addresses per sample, attempted one,
and had zero remaining. Python TCP **3/3**, native Rust TCP **3/3**. The subsequent
SS forwarding probes each passed certificate-verified origin TLS, HTTP 200,
bidirectional accounting and normal TLS/session closure. All three had
`accepted=1`, `active=0`, `failed=0`, and empty error/stage. Their independent
45-second protocol-phase budgets were satisfied (wall times 264/250/250 ms).
This is end-to-end native SS evidence, not separate timing instrumentation for
each obfs/AEAD substage, and not provider UDP or whole-GUI-config acceptance.

Native checkout was `2b2044bb43ee5da8596b9e6f99418790df666245`; it is a documentation
head. The Rust product tree is exactly implementation `cafdd62`, whose final
three-platform tested source is `b903b8b`. Actual executable hashes are recorded
and match the earlier local Release build. No new Rust build is claimed for the
documentation head.

## Environment comparison and limits

The prior hosted Linux run `39097562489`, using the same immutable ciphertext and
sample indices, resolved four IPv4 / zero IPv6 addresses per engine and timed out
on all four for every sample (Python 0/3, Rust 0/3). It never reached SS/HTTPS.
Windows success plus the different DNS address counts establishes an environment
difference; it does **not** establish that cloud IPs are blocked or that all 90
nodes work. No product timeout or protocol semantics were changed to obtain the
Windows result.

Read-only local observations found the user's existing Mihomo and Swirl processes
and an enabled system proxy. Connected IP interfaces were physical WLAN and
loopback, with the IPv4 default route on WLAN; no active TUN adapter was observed.
The test launched only the native Rust harness and independent Python sockets,
used an explicit SS outbound, and did not use the system HTTP proxy API or start
an external proxy core. No user network settings were changed. This adapter/route
observation is not a packet-capture or WFP-filter audit.

The comparison/probe reports remain in
`D:\Codex\outputs\local-secret-validation-39099020539`. There is no workflow
artifact upload step. Re-running the local workflow requires reviewing its pinned
public source SHA against the actual clean checkout; do not remove that guard or
mistake a changed documentation HEAD for a new product build.
