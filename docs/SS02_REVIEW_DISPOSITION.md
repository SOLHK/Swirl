# SS-02 feedback verification

Review baseline: `b4ad6fc517f04b0b4dfdba2a22bac585fe311204`. Feedback was supplied by
the user and was a static review, not a compiled or network-tested patch. Codex
independently checked the implementation and reproduced the applicable failures.
The user subsequently ended routine Gemini handoffs; they are no longer a
dependency for implementation or verification.

| Finding | Disposition and evidence |
|---|---|
| ISS-SS02-001: first address-only chunk breaks HTTP obfs; byte reads lose tail | The framing/data-loss claim is not established. The official simple-obfs implementation strips the initial HTTP header and continues raw stream forwarding; Content-Length is not an aggregate length for the entire tunnel. Its status line matches the current check. Buffered `poll_write` acceptance retains owned ciphertext and partial offsets, and is permitted. Keep the bounded, flushed address handshake, which also supports server-first protocols. Improve header I/O with a 4096-byte BufReader. A new test sends HTTP header, salt and encrypted record together, verifies plaintext, and measures one underlying read. Existing large/fragmented writes and half-close tests remain. |
| ISS-SS02-002: one rejected/DNS/ICMP packet kills UDP; DNS blocks replies | Accepted for datagram failure isolation and DNS head-of-line blocking. Route/resolve/send failures now drop and count one datagram. Recoverable socket errors do not close the association. Four bounded preparation tasks permit DNS waits while replies are read; dropping the association cancels them. Reject, nonexistent-domain, closed-port, subsequent valid traffic, and configuration replacement are exercised in one real socket regression. The hot-update concern itself was not reproduced: the existing immutable Arc config snapshot already retains the association's original routes. |
| ISS-SS02-003: SIP002 plugin strings not mapped | Accepted. Parse percent-decoded SIP002/SIP003 plugin options including escaped delimiters, aliases and flags; enforce length/count limits, reject duplicate aliases and malformed escapes, retain unknown options and original bytes, and block unsupported plugin semantics. Candidate split-on-semicolon code was not copied because it loses escaped delimiters and duplicate flag detection. Tests cover supported aliases, unknown options, collisions and escaping. |
| ISS-SS02-004: capability and deployment mismatch | Accepted for SS-specific unknown-field counting and custom output directories. Share the SS field list between validation and reporting; report obfuscation separately while keeping actual transport TCP. Use the targets' actual file directories for DLL staging. The default directory/dependency chain already worked. A custom-directory build and an intentionally stale deployed DLL verify incremental refresh without relinking. |
| ISS-SS02-005: outdated DIRECT-only UDP sentence | Accepted and corrected to DIRECT or SS AEAD with explicit UDP enabled. |

Rejected datagrams keep the control connection alive even when UDP is disabled
on the chosen node; no upstream packet is sent. This replaces the older test's
control-connection-close expectation with explicit drop-counter and no-send
checks. It does not add any DIRECT fallback. Unknown options are never removed
to manufacture a passing network test.

References checked: [official simple-obfs HTTP implementation](https://github.com/shadowsocks/simple-obfs/blob/master/src/obfs_http.c),
[SIP002](https://shadowsocks.org/doc/sip002.html),
[SIP003](https://shadowsocks.org/doc/sip003.html).
No candidate code was accepted solely because the review marked it confirmed.
