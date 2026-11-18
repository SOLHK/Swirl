# Native listener observation failure on d061c06

This directory preserves the failed Windows run, not a successful listener-release result.

- Development HEAD: `d061c061e86d0df611fdd5e2bf7911b0133b2741`.
- Actual Actions checkout: `efad550ce552c4cb64a530d0961d60fd157ac249`; identical source tree `8d5e39e327aa88fee97cb81dacdf771da0fbd3e0`.
- [Full Qt run 41499659849](https://github.com/SOLHK/Swirl/actions/runs/41499659849), job `125463553970`, Engine artifact `13168564433`.
- The ZIP SHA-256 is `4016e4cf95df2af0f8e24f915fc0c7982e8613b0924d4e08e4051ec8d0688b30`.

The first critical UI execution passed 10/10, including the original full-application policy test in 59.3931 seconds. Critical network passed 10/11; `swirl-system-proxy-app-exit` failed. Its XML contains 3 pass and 5 fail incidents: the known-closed control failed at line 220, and all four application rows failed at line 381. Production packaging and the remaining regression stage were not run.

The control opened an actual `QTcpServer`, closed it, and confirmed `isListening() == false`. Both the old 1500 ms observation and the new 3000 ms terminal-event observation ended in Qt `ConnectingState` (2), with `UnknownSocketError` (-1), no connection callback and no error callback. The new observation took 3005 ms. The four exited application ports produced the same observation in 3000–3015 ms. This demonstrates that these finite connection observations cannot establish that a listener remains active. No eventual refusal time, packet-filter cause or exact Windows retry sequence was observed; none is inferred as a measured result.

All four application rows had already verified real Rust HTTP/SOCKS5 traffic, normal child exit zero, the exact expected native proxy state (restored original or preserved later external edit), unchanged machine WinHTTP defaults, and removed journal/guard markers. The parent cleanup restored the runner's original state. These preceding checks do not turn the failed port gate or the overall workflow into a pass.

The next correction retains the original observations and all data rows, without increasing their budgets. Closure must instead have independent positive evidence: both native TCP tables must be readable and contain no listener for the synthetic port, and a new socket with `SO_EXCLUSIVEADDRUSE` must successfully bind and listen on exactly the same loopback address and port. A live control must actually accept a connection, appear in the TCP query, and reject the exclusive bind. Thus a deadline alone can never pass the release gate. The separate complete-traffic/EOF control and the production application's real traffic remain required.

Microsoft documents [exclusive address ownership](https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse), including the need to finish accepted connections before reclaiming an address. TCP states are recorded numerically; a `TIME_WAIT` row by itself is not described as a leaked listener. The new native checks still require actual Windows execution before acceptance.

`index.json` records the original bytes and hashes of all 16 raw XML/JSON files and the separate derived audit. No PAC, bypass, proxy credential or registry payload is included in these receipts.
