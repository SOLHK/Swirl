Exact implementation `5f1fd1347ba4f82854e3f773f90e093c3074ce40` verified: Rust CI39114652890 (Windows/Linux/macOS) and implementation39114652905 all successful. See `evidence/SUBSCRIPTION_TYPED_OPTIONS_20261018_VERIFIED.json`. The later INI REALITY/transport alias finding is handled separately in the INI profile stage; these CI results do not prove all dialect semantics equivalent.

# Subscription typed options and credential preservation, 2026-10-18

This stage fixes concrete disagreements between Qt import, native inspection and execution. It does not make every format, protocol or complete configuration executable.

## Implemented behavior

- Known URI aliases are compared after strict typing. Equal `peer`/`sni` and `allowInsecure`/`insecure`/`skip-cert-verify` remain valid, including `0` versus `false`. Repeated original keys and conflicting aliases fail. Unknown fields remain visible and block native execution.
- INI accepts case-insensitive `true`/`false`; URI accepts lowercase `true`/`false` and `1`/`0`. Invalid values cannot silently disable a feature. Quoted positional credentials retain equals signs, colons, commas, percent signs, spaces, escaped quotes and backslashes. Positional/named authentication and canonical INI aliases cannot overwrite each other in Qt.
- Legacy Loon Trojan `key:value` options are recognized after the password. Quoted credentials are never treated as options. The original source remains preserved.
- HTTPS, SOCKS5-TLS and Trojan keep their required TLS semantics. Explicit contradictory TLS fails. SIP002 plugin duplicate keys and alias collisions fail.
- Exact Boolean `tfo:false` maps to the same native configuration as omission for HTTP, SOCKS4/4a/5, Shadowsocks, Trojan and VLESS. True and non-Boolean forms remain rejected. This implements no TCP Fast Open.

## Evidence and scope

Rust fmt/check/clippy pass; workspace tests:142 passed. Native Qt:40 passed,0 failed,5 independent-peer hooks skipped in that invocation. Native and compatibility import boundary CTests both pass. Independent Shadowsocks suite:9 passed, including four Qt-to-Rust HTTP-obfs exchanges; one is Loon with `fast-open=false`. Native SOCKS5 forwarding with false TFO also passes. Python import tests:11 passed; capture:26 ran,1 existing skip; development checks:19 ran,1 existing symlink-privilege skip. Full Windows app builds. The compatibility moc failure and original red tests are retained in hashed logs; the fixture's raw string was respelled and both builds/tests rerun.

Offline native replay:18 old entries,1558 node records including duplicate sources,450 TCP candidates. No provider/node request. The `insecure` alias reduces unmapped-field counts in entries17/18 by59 each without enabling REALITY. Actual cache inventory contains90 equivalent peer/sni URI pairs and90 legacy Loon Trojan colon rows. Qt synthetic regressions cover these shapes; this is not full private-profile Qt execution or live connectivity proof.

The newly authorized unlimited test source was fetched once at09:10 UTC,HTTP200,5009 raw bytes/27280 decompressed bytes,DPAPI persisted and readback verified. The HTTP MIME says text/html, but strict complete-body inspection identifies Base64 containing59 VLESS/TCP/REALITY nodes;55 also declare Vision. It is a node-list encoding, not evidence of one exclusive client format. Current executable candidates:0; node attempts:0. No credentials, URLs, headers or plaintext configurations are included here. [New-source evidence](evidence/NEW_TEST_SUBSCRIPTION_20261018.json).

[Stage evidence](evidence/SUBSCRIPTION_TYPED_OPTIONS_20261018.json) binds source/log/binary hashes. Exact new-commit CI must be recorded after push. DNS baseline `f81eab6` has its own completed three-platform CI; that does not validate this later stage. Weighted full-goal acceptance stays10.83%.

## Primary references and independent design

Reviewed [subconverter proxy IR](https://github.com/tindy2013/subconverter/blob/master/src/parser/config/proxy.h), [Sub-Store proxy utilities](https://github.com/sub-store-org/Sub-Store/blob/master/backend/src/core/proxy-utils/index.js), [Loon rule documentation](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/rule.md), and [Quantumult X sample configuration](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf). Subconverter is GPL-3.0; Sub-Store is AGPL-3.0. No source or tests were copied and no dependency was added. Learn their separation of parsing, node IR, target capabilities and output; node conversion does not preserve complete profile semantics automatically.

Next complete-profile work should isolate static manual groups and ordered local domain rules with explicit FINAL. Loon domain-before-IP priority, remote rule sources, process/GEO rules and DNS must not be silently flattened. Quantumult X simple-obfs TLS and real TLS/ALPN encodings require distinct mappings. New source additionally requires a reviewed native REALITY TLS design and independent version-pinned interoperability before any node can be counted successful.
