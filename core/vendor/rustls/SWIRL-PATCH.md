# Swirl rustls 0.23.46 patch

This directory vendors the existing locked rustls dependency, not a proxy core.
TLS cryptography, key agreement, record protection, transcript handling and
certificate/proof verification remain in rustls and its configured providers.

## Provenance and licenses

- Package: `rustls 0.23.46`, from the public crates.io archive.
- Archive: <https://static.crates.io/crates/rustls/rustls-0.23.46.crate>
- Original archive SHA-256:
  `48e13bd8c0e9365c43cfa5c9e8f9ad49d3c8444926c9aac819e0e4dc503c8fdf`.
- Upstream repository: <https://github.com/rustls/rustls>.
- Archive source revision: `f04804fa13341a9b1dc02b5d1dd8a746f2c4b7fb`,
  repository subdirectory `rustls` (from `.cargo_vcs_info.json`).
- Upstream license expression: `Apache-2.0 OR ISC OR MIT`.
  `LICENSE-APACHE`, `LICENSE-ISC` and `LICENSE-MIT` are retained unchanged.
- All archive files are retained except `.cargo_vcs_info.json`, whose provenance
  is recorded here. Cargo's local `.cargo-ok` extraction marker is not included.
  The upstream `.rustfmt.toml` is also retained from that exact revision so
  formatting checks preserve the original library source.
- Swirl's changes are available under the same license expression.

## Local changes

`src/client/customize.rs` adds one opt-in `ClientHelloCustomizer` callback. The
callback receives and returns a complete handshake message (four-byte handshake
header, without the TLS record header). `ClientConfig.client_hello_customizer`
defaults to `None`; unconfigured clients follow the upstream path unchanged.

Modified upstream files are `src/lib.rs`, `src/client/builder.rs`,
`src/client/client_conn.rs`, `src/client/common.rs`, `src/client/hs.rs` and
`src/client/tls13.rs`. Each contains a notice identifying this modification.
No other upstream implementation or license file is changed.

The callback runs only for the initial TLS 1.3 stream ClientHello, before both
transcript hashing and transmission. Actual TLS 1.2 configuration, resumption,
early data, real ECH configuration, QUIC and HelloRetryRequest fail explicitly.
A browser profile may advertise historical TLS 1.2 offers; this does not enable
TLS 1.2 negotiation in this path.

Validation bounds the message to 16 KiB and 64 extensions, rejects duplicates,
and preserves the generated random, session ID, actual key-share bytes, SNI,
ALPN, OCSP and certificate-decompression capabilities. Only bounded GREASE and
explicit browser-offer extension forms are permitted. GREASE ECH is allowed in
a fixed opaque outer form; this is not real encrypted ClientHello support.
Signature offers can differ for REALITY's separate pinned Ed25519 proof, which
is still verified by Swirl's REALITY certificate verifier. This API must not be
used to claim general public-PKI browser equivalence.

The returned bytes are parsed for negotiated-state metadata but retained
verbatim for the wire and transcript. Sent-extension and cipher metadata reflect
the actual replacement. The adapter does not rewrite socket traffic. A server
negotiating a newly advertised extension unsupported by rustls (such as ALPS)
is rejected with `CustomClientHelloExtensionNegotiationUnsupported` rather than
silently accepted.

The Chrome profile belongs to Swirl's transport crate, outside this dependency.
Brotli certificate decompression uses rustls's existing, explicitly enabled
`brotli` feature; the callback cannot add a compression capability the original
configuration did not offer.

## Validation and maintenance

`crates/swirl-transport/tests/client_hello_customizer.rs` tests the actual rustls
connection boundary: exact emitted bytes, unsupported contexts, malformed
callback output, preserved authentication/key material, HelloRetryRequest and
Brotli decompression. Full REALITY/Vision peer tests and the independently pinned
uTLS ClientHello comparison remain application-level acceptance gates.

When upgrading rustls, begin with the complete new upstream release, review its
security changes, then reapply only these local changes. Recheck placement before
transcript handling, encoded-versus-parsed ownership, handshake-state metadata,
ECH handling and extension negotiation. Run the focused tests and all native,
peer, cross-platform and product-chain gates before updating the recorded
version and provenance. Do not let this patch freeze security updates.
