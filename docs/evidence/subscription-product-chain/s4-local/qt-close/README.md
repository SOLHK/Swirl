# S4 Qt TLS shutdown diagnostic

This is a local Linux Qt 6.10.3 / PySide6 6.10.3 / OpenSSL diagnostic. It is not evidence that the Windows Qt/DPAPI product menu has passed. All endpoints and credentials are synthetic loopback fixtures.

The reproduced QNetworkAccessManager positive request returns the correct HTTP body and NoError, while the independently owned Python HTTPS server fails its strict TLS unwrap with SSLEOFError. Keeping the manager alive and continuing the event loop does not fix that case.

An explicitly owned QSslSocket with VerifyPeer and the fixture CA returns the correct body and completes both close_notify alerts (tls_closed=1). This exposed a second fixture boundary: a redundant raw shutdown after verified TLS shutdown can report ENOTCONN after the peer has already closed TCP. The correction accepts only that exact post-unwrap error (or Windows WSAENOTCONN) and still requires raw recv EOF. It does not ignore SSL errors or bypass TLS unwrap.

The after-fix log shows positive QSslSocket tls_closed=1, no fixture errors, and one HTTP request. The wrong-name connection returns SslHandshakeFailedError, no HTTP request and no origin errors. QNetworkAccessManager remains a deliberately failing comparison.

The script uses temporary PySide packages under /tmp and the repository fixture module. The JSON metadata records the base SHA; S4 source edits were not committed when this diagnostic was recorded. Windows product integration must be rerun on the resulting pushed SHA.
