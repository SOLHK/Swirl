# Native Snell v4

Swirl implements Snell v4 inside its Rust runtime. Imported nodes must declare
`version = 4`; undeclared versions, v1–v3, v5, v6, QUIC, reuse and external obfs
options fail closed. A v5 server's documented v4 compatibility does not make a
v5 client configuration supported. Ordinary TCP carries both stream traffic and
the optional UDP relay. No server fixture, external proxy process or downloaded
runtime is included in the product.

TCP uses the existing resolver, connection deadline, physical-interface binding
and private-acceptance socket admission. UDP uses a dedicated bounded carrier
through the same dialer; its datagram boundaries remain AEAD record boundaries.
The encrypted payload maximum is 16,383 bytes, including the UDP address header.
Oversized datagrams fail rather than truncate. Cancelling a partially sent UDP
datagram retires its carrier; partial receives retain their bytes and original
five-second frame deadline. TCP reads expose bytes only after validating the
peer status and AEAD tags. The peer may defer its status until target data arrives,
so opening the socket is not authentication or real-connectivity evidence.
Non-reuse peers may end at a complete authenticated-record boundary; partial
salt, header or payload closure remains an error.

The AEAD layer uses ring AES-128-GCM and RustCrypto Argon2id rather than custom
cryptography. Nonce exhaustion fails closed. A process-local, key-scoped response
salt window rejects replays for ten minutes, registers only authenticated headers
and fails closed at 65,536 unexpired entries. It stores digests, not credentials.
This has the same bounded retention policy as the existing classic Shadowsocks
implementation; it is not a claim of indefinite replay retention.

## Sources and independent evidence

- [Surge's vendor documentation](https://kb.nssurge.com/surge-knowledge-base/release-notes/snell)
  defines the server releases and v4/v5 compatibility boundary.
- Wire facts were cross-checked with
  [winmin/snell-client at ada74659](https://github.com/winmin/snell-client/tree/ada7465923484eda4d078a3d3e67daeff7aa2fa7).
  That reference declares MIT in Cargo metadata but contains no license file;
  its source was not incorporated. Swirl's codec was written for its own stream,
  cancellation and egress contracts.
- [OpenSnell at 49a61f2f](https://github.com/missuo/opensnell/tree/49a61f2f6cd94834a0e6256f30ceafa78127219c)
  was used as an independent local server process. It is GPL-3.0; no source or
  binary from it is incorporated into Swirl or its distribution.
- The official Snell 4.1.1 Linux-amd64 archive and executable hashes are pinned in
  `tools/tests/snell-peer-lock.json`. `fetch_snell_peer.py` downloads it only for
  testing; `test_snell_official.py` starts and retires an owned-loopback server.
  The client example exercises the generic native outbound entry point, a
  37,000-byte stream in both directions and its clean EOF, and 1,200/16,000-byte UDP
  datagrams. The UDP carrier must remain usable after Swirl rejects empty and
  oversized outgoing datagrams locally. A wrong PSK must never reach the origin.
  Vendor binaries are test fixtures and are not redistributed in product packages.
- RustCrypto Argon2 and its transitive dependency license notices are recorded in
  `core/DEPENDENCIES.json` and collected by the existing packaging notice pipeline.

Unit tests separately cover fragmented padded frames, authentication failure,
cross-connection replay, cancellation, original deadlines, nonce exhaustion and
malformed UDP replies. A synthetic peer is not evidence of public-provider
connectivity, Qt product acceptance or TUN takeover. Only the CI receipt from an
actual official-server run establishes that official interoperability check;
writing the fixture does not establish a passing result.
