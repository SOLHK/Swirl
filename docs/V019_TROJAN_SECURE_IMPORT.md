# Trojan subscription policy in v0.1.9

The supplied screenshots show that the provider sets `skip-cert-verify=true`
on Trojan nodes. The previous importer rejected the entire subscription at
the first such node, before a TLS connection could be attempted.

Swirl now makes a restricted, visible security projection at the subscription
import boundary: a correctly typed top-level Trojan request to skip certificate
validation becomes `skip-cert-verify=false` in the executable node. The exact
original source remains in the encrypted catalog. The import result and node
details explain that certificate validation stays enabled and that an untrusted,
expired or incorrectly named certificate will still fail to connect.

This is a stricter Swirl policy, not an implementation of the provider's request
to disable validation. It does not change SNI, passwords, ALPN, transport or
certificate roots. Unsupported extensions, conflicting aliases and invalid
types remain errors. A manually constructed node or direct Rust request with
certificate validation disabled remains rejected. This scope is Trojan only;
other protocols keep their existing security policy.

The persistent notice is display data and grants no runtime permission. Actual
parameters must pass the ordinary Qt validation and Rust conversion on every
activation. A changed executable flag cannot use the notice to bypass checks.

The controlled Qt regression goes through source import, the Rust converter,
an explicit local Rust HTTP CONNECT listener and an independent TLS Trojan peer.
It verifies exact password-hash/destination framing and 65,537 echoed bytes for
URI, Base64 URI, INI, Quantumult X and Clash source forms. Separate connections
must fail for an unknown issuer and a wrong certificate name. The public fixture
CA is trusted only in those individual synthetic outbound configurations, never
installed in Windows or added to product settings. Private provider networking
and Codex acceptance remain assigned to the user.

Primary references checked on 2026-10-24:

- [Trojan client configuration](https://github.com/trojan-gfw/trojan/blob/master/docs/config.md): certificate and hostname verification are separately documented and strongly recommended.
- [Mihomo TLS fields](https://github.com/MetaCubeX/Meta-Docs/blob/main/docs/config/proxies/tls.en.md): `skip-cert-verify` bypasses verification; SNI and ALPN carry distinct semantics.

No upstream implementation was copied. This document describes Swirl's policy
and controlled test coverage; it does not claim the supplied provider's
certificates or nodes have been accepted.
