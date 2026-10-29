# Test certificates

`test-ca.p12` is a deliberately public, test-only RSA CA fixture. Its password
is `swirl-test-only`; its private key is test data, not an application/user CA.
Capture integration tests import it into temporary DPAPI files and never
install it into the Windows trust store. Do not use or trust this fixture
outside isolated tests.

`xray-proxy-server-cert.pem` is a server-only leaf signed by the public
`localhost-cert.pem` fixture authority. It authenticates the reserved synthetic
name `subscription.example.invalid` and uses the existing public test key
`xray-download-server-key.pem`. `XrayDownloadTests` forwards HTTP CONNECT only
for that authority to a loopback TLS server; it does not resolve or contact the
name on the Internet. The client keeps certificate verification enabled and
trusts the fixture CA only inside the test process. Validity is 2026-10-23 to
2028-10-22, with CA:false and serverAuth EKU.
