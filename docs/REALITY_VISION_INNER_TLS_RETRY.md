# Inner TLS retry and Vision direct eligibility

Windows Qt can send a second inner ClientHello after the origin requests a new
TLS 1.3 key share. The origin accepts HTTPS, but the former Vision inspector
permanently rejected HelloRetryRequest. When the peer subsequently selected
Vision direct mode, Rust refused the handoff and Qt reported a failed request.

The inspector now retains bounded first-flight metadata and observes one retry.
It waits for both complete second-flight hellos, validates their session, random,
cipher, immutable extensions, requested key share and cookie, and requires the
early-data extension to be removed. A repeated retry, an HRR sharing a record
with trailing plaintext handshake data, or malformed compatibility CCS fails
closed independently of network read boundaries. Record offsets survive the
flight transition. Inner endpoint certificate verification, outer REALITY
authentication, encrypted-record completion and unique transport handoff
ownership remain unchanged.

HRR with PSK identities/binders remains outside direct eligibility: those opaque
updates are not interpreted or accepted by this inspector. Non-retry behavior
is unchanged. This does not add outer REALITY HRR support or imply support for
all TLS extensions, private providers, TUN or external networks.

Regression coverage includes valid group/cookie retries, every read split,
partial CCS headers, forbidden second retries, unchanged SNI/session/cipher,
early data and PSK rejection. Actual Qt/Rust/Xray product-chain acceptance and
the exact source/package identity are reported separately by the delivery run.

Protocol references: [RFC 8446 section 4.1.2](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.1.2),
[section 4.1.4](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.1.4) and
[section 5](https://www.rfc-editor.org/rfc/rfc8446.html#section-5).
