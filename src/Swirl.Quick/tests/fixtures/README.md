# Test certificates

`test-ca.p12` is a deliberately public, test-only RSA CA fixture. Its password
is `swirl-test-only`; its private key is test data, not an application/user CA.
Capture integration tests import it into temporary DPAPI files and never
install it into the Windows trust store. Do not use or trust this fixture
outside isolated tests.
