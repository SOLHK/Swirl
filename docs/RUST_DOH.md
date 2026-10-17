# Rust DoH stage (HTTP/1.1 POST)

This stage continues the verified DoT implementation at `866c437`. It adds
Swirl-owned DoH HTTP transport in `core/crates/swirl-dns/src/doh.rs`, reusing
the existing DNS wire validation, TLS verification and immutable resolver plans.
It does not run a third-party DNS or proxy core. httparse parses HTTP headers;
rustls supplies TLS. No new third-party package is added to Cargo.lock.

## Configuration and existing UI

Typed IR has an additive `dns.https_servers` list, at most four endpoints:

```json
{"address":"127.0.0.1:8443","path":"/dns-query","tls":{"server_name":"dns.fixture.invalid","alpn":["http/1.1"]}}
```

The example is synthetic, not a working public resolver. `address` is an explicit
IP bootstrap socket address. `tls.server_name` is both certificate identity and
HTTP Host; the configured bootstrap port supplies the authority port. Extra DER
trust anchors are allowed through the existing local test/API TLS field. Qt has
no insecure or custom-CA bypass. Unknown fields, unsupported ALPN, unsafe paths,
fragments/templates, duplicate endpoints and combinations with plaintext/DoT
servers fail validation before activation.

The existing encrypted-DNS field accepts `https://host[:port]/path[?query]`.
Default port is 443; an omitted path means `/`. A domain host requires an existing
exact local IP mapping. IP literals including IPv6 work directly. System mode
and an empty traditional-server field are required, matching the strict DoT
bootstrap policy. Missing bootstrap fails explicitly; no OS DNS query is made
to discover the endpoint. No QML, page layout, system DNS, proxy or trust setting
changes. Existing DoT settings and plaintext custom DNS remain supported.

## Wire behavior and limits

Requests use POST, DNS ID zero, `application/dns-message` Content-Type/Accept,
and HTTP/1.1 over verified TLS. A response must be HTTP/1.1 200 with that exact
media type. Content-Length and chunked framing are supported; missing/duplicate
or conflicting framing, compressed bodies, unsupported chunk extensions or
trailers, oversized/short bodies and bad DNS messages fail. No redirects,
credentials, cookies, environment proxy discovery or plaintext downgrade occur.

Headers are bounded to 8 KiB/64 fields, DNS bodies to 16 KiB and chunk count to
256. The existing record/name/CNAME limits apply. Each exchange has its own TLS
connection with `Connection: close`; A/AAAA and CNAME follow-ups are sequential.
One configured endpoint has a 1.4-second budget; all endpoint attempts have the
existing total 3-second lookup budget, with the shared 8-lookup admission cap.
Failures may try only another explicitly configured HTTPS endpoint. NXDOMAIN
terminates lookup. Both families must complete (NODATA is allowed).

Positive cache TTL uses the minimum DNS/CNAME TTL and HTTP max-age, subtracts
Age and lookup time, and retains the existing 300-second cap. `no-store` and
`no-cache` prevent local caching. Zero/expired TTL is not cached. This is a DNS
result cache, not a general HTTP cache: Date/Expires, validators, authentication,
negative caching and shared-cache directives are not implemented.

HTTP/2/3, GET/URI templates, persistent connections, discovery, automatic DNS
bootstrap and proxy-routed resolver transport remain unfinished. HTTP/1.1-only
providers and strict response framing must be verified separately; this stage
does not claim complete DoH server compatibility or production performance.
Wire reference: [RFC 8484](https://www.rfc-editor.org/rfc/rfc8484.html).

## Validation

`tools/tests/test_dns_https.py` runs 11 independent synthetic HTTPS peer tests:
verified POST/fragmented framing, chunked bodies, CNAME, IPv6, TTL expiration,
Age/no-store/max-age/TTL-zero cache behavior, wrong certificate/name, redirects
and malformed HTTP/DNS, timeouts, configured failover, terminal NXDOMAIN,
atomic configuration updates and old TCP/UDP snapshot preservation.
No private subscriptions, public resolvers or OS certificate changes are used.
Qt tests validate the existing field-to-IR mapping and reject unsupported
bootstrap/URL options; HTTPS networking itself is exercised by the Rust harness.

Run with the built harness and Python cryptography 50.0.2:

```powershell
$env:SWIRL_RUST_HARNESS=(Resolve-Path build/rust-qt/rust-target/release/swirl-api.exe).Path
py -3 tools/tests/test_dns_https.py
py -3 tools/tests/test_dns_tls.py
```

CI runs both suites on Windows, Linux and macOS. Inspect the delivered commit's
Actions for status; adding a job does not establish that it passed.
