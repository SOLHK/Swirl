# Native exit probe failure at 1410ee9

This directory preserves the exact XML and twelve safe receipts from full Qt run
41491137276, job 125441364105, Engine artifact 13167097461. `index.json` pins the
downloaded ZIP, actual checkout, equal source tree, and individual captured bytes.

The original full-application critical UI suite passed 10/10, including
`swirl-policy-ui` in 56.57 seconds. Critical network passed 10/11. The sole failing
suite was `swirl-system-proxy-app-exit`: the empty-PAC representation regression
passed, and all four application rows failed at the final `listenerRefusesConnections`
assertion. They had already completed real HTTP/SOCKS5 forwarding, normal exit 0,
exact native PAC/bypass/registry restoration or later-edit preservation, and the
journal/guard-marker absence check. Ordinary rows restored while Rust was alive.
The saved overall results remain failures.

The old helper returns one boolean for three different observations: a connection
still pending after 1500 ms, a terminal error other than connection refusal, or a
successful connection. No state/error/timing receipt was captured. The assertion's
wording therefore does not establish that a Rust listener survived process exit.

Chromium's native Windows TCP implementation documents SYN retries before a
closed loopback port reports connection refusal, with about two seconds of delay:
<https://chromium.googlesource.com/chromium/src/+/refs/heads/main/net/socket/tcp_socket_win.cc>.
The inspected file blob was `d06a16058a6b812e391f6dcf30b1b6e388645030`.
This supports a timing hypothesis, not a measurement of this failed execution.

The follow-up test observes actual connected/error events and terminal socket
state within the existing successful-connection test budget of 3000 ms. Only an
explicit connection-refused event, matching final error and unconnected state,
with no connection event, satisfies closure. It records the numeric probe result
before asserting. Production timeouts and the 120-second suite limit are unchanged.

Native controls use a known closed port and a real live listener. They also record
an invocation of the exact old 1500 ms predicate on the closed fixture, without
requiring a particular operating-system delay forever. The follow-up Windows CI
must execute these controls, all four original application rows, and verify the
source-pinned control and per-row probe receipts. Linux Qt signal observations do
not satisfy that Windows gate. Packaging, remaining full regression, and physical
Windows 11 Codex/Clash acceptance were not completed by the failed run.
