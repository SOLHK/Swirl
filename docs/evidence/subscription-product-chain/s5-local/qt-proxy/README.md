# Qt TLS close diagnostic through the actual Rust proxy path

## Scope and exact source identity

These are local Linux diagnostics, using PySide6 / Qt 6.10.3, the OpenSSL Qt
backend (OpenSSL 3.0.13), and Python 3.12.14. They verify QtNetwork behavior
through the real Rust inspector, Rust runtime, and independently listening
Python proxies and HTTPS target. They do not exercise C++ compilation,
EngineController, Windows DPAPI persistence, or the full GUI. Windows product
acceptance still requires the exact new commit's ProductQtIntegration CI gate.

The checkout HEAD when these runs were recorded was
`a066f7d4c8acb96f5d6a46cee5700b2590328b64`. The final fixture changes were
uncommitted during the run. The exact final
`tools/tests/test_product_subscription_chain.py` SHA-256 was
`842e4375437716a94e3ede0f9178eeb7b13472965dee49f860a003e61d80fa92`.
The JSON files record this fixture hash separately from the checkout HEAD;
neither the final results nor earlier diagnostic filenames imply a clean
checkout at a published commit. Rust binary hashes are recorded in result.json.

## Final-source result

`result.json` and `raw.log` record four successful cases, using the final source
fixture and the same explicit `QNetworkProxy::HttpProxy` method as the published
S4 C++ HTTPS helper. There is no runtime override or SSL monkeypatch in the
`source-client-first` mode used by this final run.

For each of HTTP CONNECT, authenticated SOCKS5, Shadowsocks AES-128-GCM, and plain
VLESS TCP:

- The real Rust inspector parsed the synthetic subscription and preserved its
  original document; its TCP candidate was accepted by the real Rust runtime.
- An independent relay received exactly two connections, to `localhost` and
  `wrong.fixture.invalid` at the independently listening HTTPS origin's port.
- The positive request verified the fixture CA and hostname, received HTTP 200
  and `product-origin-ok:/through-qt-proxy`, and disconnected normally.
- The negative request produced `SslHandshakeFailedError` with an explicit
  `HostNameMismatch`, and sent no HTTP request. The origin saw both expected SNI
  names and exactly one HTTP request in total.
- The origin counted exactly one successful TLS close, after observing the
  client's authenticated TLS EOF, completing `unwrap`, and observing raw TCP EOF.
  Origin errors, relay errors, and denied proxy authentications were empty.
- The Rust runtime reached zero active sessions before shutdown.

Reproduction command:

```sh
SWIRL_QT_CLOSE_DIRECTION=source-client-first SWIRL_QT_PROXY_MODE=qt-http-proxy python qt-proxy-diagnostic.py
```

The script's local paths point to this workspace and the temporary PySide6
dependency installation; it is diagnostic evidence, not a new product test host.

## Bare TCP truncation remains a hard failure

`tls-truncation-diagnostic.py`, `tls-truncation.log`, and
`tls-truncation-result.json` exercise an independently authenticated TLS client
through a real Rust HTTP CONNECT node and the independent HTTP relay. After
reading the complete authenticated HTTP response, the client deliberately
detaches the TLS socket and sends a raw TCP FIN without `close_notify`.

The actual source fixture rejects this: `SSLEOFError`, errno 8, at its strict
post-response TLS `recv`; `tls_closed` remains 0. Its unchanged `Origin.close`
also raises its assertion. The diagnostic explicitly expects and records that
failure. It does not suppress SSL errors or alter source assertions. Exactly one
HTTP request and one relay connection were observed.

## Why the fixture has a Qt-specific close initiator

The earlier archived experiments preserve failures and comparisons:

| Archive prefix | Client path and fixture close initiator | Observed result |
| --- | --- | --- |
| `qt-http-proxy-a066-` | Explicit Qt HttpProxy through Rust; server sends TLS close first | Correct positive HTTP response, then strict TLS close failure; full diagnostic fails |
| `explicit-connect-server-first-` | Same QSslSocket connects only to Rust; explicit CONNECT then TLS; server closes first | Same strict TLS close failure, excluding direct-origin bypass or the Qt HttpProxy adapter as the sole cause |
| `explicit-connect-client-first-pre-drain-` | Explicit CONNECT; diagnostic-only client-first SSL comparison | HTTP case succeeds; later SOCKS fixture cleanup exposes a cancellation timing issue before Rust sessions drain |
| `qt-http-proxy-client-first-override-` | Published Qt HttpProxy method; diagnostic-only client-first SSL comparison; drain Rust sessions | All four protocol cases pass |

The final source makes close ownership explicit only for the Qt product menu:
the client already calls `disconnectFromHost` after its complete response, so the
origin waits for its authenticated TLS EOF before replying with TLS shutdown.
`suppress_ragged_eofs=False` ensures that a bare TCP close is never accepted as
that TLS EOF. The portable Python menu retains its existing server-first close
direction. The C++ HTTPS helper remains unchanged by this correction.

## Portable regression on the final source

`portable/tests.log` and `portable/result.json` record 8 tests passed, 0 failures,
0 errors, 0 skips, in 4.606 seconds. The real Rust inspector/runtime and synthetic
loopback independent peers were used. This menu's JSON persistence remains a
test host; it is not Windows Qt/DPAPI persistence. The result records the dirty
worktree paths present during the run. `git diff --check` and Python compilation
of the modified fixture also succeeded.
