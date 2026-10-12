These certificate and RSA private key files are PUBLIC, TEST-ONLY fixtures.
They identify a localhost HTTP/TLS origin used exclusively by ControlledNetwork
when SWIRL_BUILD_UI_TESTS is enabled. They are not production credentials,
are never bundled into Swirl-Setup.exe, and are never installed in an OS trust
store. A test QNetworkRequest trusts the certificate explicitly. The SOCKS
relays forward encrypted TCP bytes without TLS interception.
