"""Subscription syntax -> native IR -> independent SS/Trojan peers, synthetic data only.

References: Shadowsocks SIP002, the official Loon node examples, and Surge's SS
declaration syntax. The Python peer performs wire authentication independently.
"""
import base64
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import quote

from test_rust_core import Handler as ReferenceHandler, Reference, certificates, exact, header
from test_shadowsocks import Handler, PASSWORD, Peer, Reader, Writer, cipher_key


class IPv6Peer(Peer):
    address_family = socket.AF_INET6


class CredentialPeer(Handler):
    """Authenticate the exact independently specified password, including URL delimiters."""
    def handle(self):
        self.request.settimeout(5)
        reader = Reader(self.request, self.server.method)
        reader.cipher = cipher_key(self.server.method, reader.salt, self.server.password)
        host = b'origin.fixture.invalid'
        assert reader.chunk() == b'\x03' + bytes([len(host)]) + host + (443).to_bytes(2, 'big')
        self.server.targets.append((host.decode(), 443))
        writer = Writer(self.server.method)
        writer.cipher = cipher_key(self.server.method, writer.salt, self.server.password)
        self.request.sendall(writer.salt)
        try:
            while True:
                data = reader.chunk()
                self.server.received += len(data)
                self.request.sendall(writer.chunk(data))
        except EOFError:
            self.request.sendall(writer.chunk(b'tail-after-halfclose'))
            self.request.shutdown(socket.SHUT_WR)


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS') and os.environ.get('SWIRL_RUST_INSPECTOR'),
                     'compiled Rust harness and inspector required')
class SubscriptionImportTests(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.process = subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            self.fail('Rust did not stop')
        finally:
            for server in self.servers:
                server.shutdown()
                server.server_close()
            error = self.process.stderr.read()
            self.process.stdout.close()
            self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, error)
        self.assertNotIn(PASSWORD, error)
        for server in self.servers:
            self.assertEqual(server.errors, [])

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def inspect(self, document):
        result = subprocess.run([os.environ['SWIRL_RUST_INSPECTOR'], '--private-json'],
                                input=document, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def peer(self, ipv6=False, password=PASSWORD, method='aes-128-gcm'):
        if ipv6 and not socket.has_ipv6:
            self.skipTest('IPv6 loopback unavailable')
        try:
            handler = Handler if password == PASSWORD else CredentialPeer
            server = (IPv6Peer if ipv6 else Peer)(('::1' if ipv6 else '127.0.0.1', 0), handler)
        except OSError:
            if ipv6:
                self.skipTest('IPv6 loopback binding unavailable')
            raise
        server.method, server.obfs, server.mode, server.fixed_salt = method, False, 'echo', None
        server.password = password
        server.targets, server.headers, server.errors, server.received = [], [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server

    def trojan_peer(self, context):
        server = Reference(('127.0.0.1', 0), ReferenceHandler)
        server.protocol, server.tls = 'trojan', context
        server.requests, server.errors, server.accepted = [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server

    def forward(self, document, expected_host, expected_password=PASSWORD):
        result = self.inspect(document)
        self.assertTrue(result['report']['nodes'][0]['native_tcp_candidate'])
        self.assertFalse(result['report']['nodes'][0]['real_network_verified'])
        outbound = result['tcpCandidates'][0]
        self.assertEqual(outbound['type'], 'shadowsocks')
        self.assertEqual(outbound['host'], expected_host)
        self.assertEqual(outbound['password'], expected_password)
        started = self.command(op='start', config={'schema': 1, 'listen': '127.0.0.1:0',
                               'selected': 'imported', 'nodes': [{'id': 'imported', 'outbound': outbound}]})
        self.assertTrue(started['ok'], started)
        handle = started['handle']
        port = int(started['status']['address'].rsplit(':', 1)[1])
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=5) as stream:
                stream.sendall(b'CONNECT origin.fixture.invalid:443 HTTP/1.1\r\n'
                               b'Host: origin.fixture.invalid:443\r\n\r\n')
                self.assertIn(b' 200 ', header(stream))
                payload = b'imported-native-ss' * 2049
                stream.sendall(payload)
                self.assertEqual(exact(stream, len(payload)), payload)
                stream.shutdown(socket.SHUT_WR)
                self.assertEqual(exact(stream, 20), b'tail-after-halfclose')
                self.assertEqual(stream.recv(1), b'')
            deadline = time.monotonic() + 2
            while True:
                snapshot = self.command(op='snapshot', handle=handle)['status']
                if snapshot['active'] == 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            self.assertEqual(snapshot['accepted'], 1)
            self.assertEqual(snapshot['active'], 0)
            self.assertEqual(snapshot['failed'], 0)
            self.assertEqual(snapshot['last_error'], '')
            self.assertGreater(snapshot['upload'], 0)
            self.assertGreater(snapshot['download'], 0)
        finally:
            self.assertTrue(self.command(op='stop', handle=handle)['ok'])

    def test_ipv6_sip002_and_base64_forward_with_authenticated_close(self):
        server = self.peer(ipv6=True)
        authority = f'[::1]:{server.server_address[1]}'
        user = base64.urlsafe_b64encode(f'aes-128-gcm:{PASSWORD}'.encode()).decode().rstrip('=')
        uri = f'ss://{user}@{authority}#synthetic'
        for document in (uri, f'ss://aes-128-gcm:{quote(PASSWORD, safe="")}@{authority}',
                         base64.b64encode(uri.encode()).decode()):
            with self.subTest(format='base64' if not document.startswith('ss:') else 'uri'):
                self.forward(document, '::1')
        self.assertEqual(server.targets, [('origin.fixture.invalid', 443)] * 3)

    def test_valid_surge_and_loon_credentials_forward(self):
        server = self.peer()
        endpoint = f'127.0.0.1,{server.server_address[1]}'
        for declaration in (f'Shadowsocks,{endpoint},aes-128-gcm,"{PASSWORD}",fast-open=false',
                            f'ss,{endpoint},encrypt-method=aes-128-gcm,password={PASSWORD}'):
            self.forward(f'[Proxy]\nfixture = {declaration}\n', '127.0.0.1')
        self.assertEqual(server.targets, [('origin.fixture.invalid', 443)] * 2)

    def test_loon_http_obfs_exports_authenticate_forward_and_halfclose(self):
        for method in ('aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305'):
            server = self.peer(method=method)
            server.obfs = True
            endpoint = f'127.0.0.1,{server.server_address[1]}'
            for options in ('http,obfs.example', 'obfs-name=http,obfs-host=obfs.example'):
                document = (f'[Proxy]\nfixture = Shadowsocks,{endpoint},'
                            f'{method},"{PASSWORD}",{options}')
                self.forward(document, '127.0.0.1')
            self.assertEqual(server.targets, [('origin.fixture.invalid', 443)] * 2)
            self.assertEqual(len(server.headers), 2)
            self.assertTrue(all(f'Host: obfs.example:{server.server_address[1]}\r\n'.encode() in h for h in server.headers))

    def test_loon_http_obfs_corrupt_aead_never_releases_plaintext(self):
        for mode in ('tampered', 'bad-length-tag', 'truncated', 'bad-http'):
            server = self.peer()
            server.obfs, server.mode = True, mode
            document = (f'[Proxy]\nfixture = Shadowsocks,127.0.0.1,{server.server_address[1]},'
                        f'aes-128-gcm,"{PASSWORD}",http,obfs.example')
            outbound = self.inspect(document)['tcpCandidates'][0]
            self.assertIsNotNone(outbound)
            started = self.command(op='start', config={'schema': 1, 'listen': '127.0.0.1:0',
                                   'selected': 'imported', 'nodes': [{'id': 'imported', 'outbound': outbound}]})
            self.assertTrue(started['ok'])
            handle = started['handle']
            try:
                with socket.create_connection(('127.0.0.1', int(started['status']['address'].rsplit(':', 1)[1])), timeout=5) as stream:
                    stream.sendall(b'CONNECT origin.fixture.invalid:443 HTTP/1.1\r\nHost: origin.fixture.invalid:443\r\n\r\n')
                    self.assertIn(b' 200 ', header(stream))
                    self.assertEqual(stream.recv(100), b'')
            finally:
                self.assertTrue(self.command(op='stop', handle=handle)['ok'])

    def test_legacy_and_sip002_reserved_passwords_authenticate(self):
        method = 'chacha20-ietf-poly1305'
        for password in ('test/!@#:', 'literal%40/%2f?@#:%GG'):
            server = self.peer(password=password, method=method)
            raw = f'{method}:{password}@127.0.0.1:{server.server_address[1]}'
            uri = 'ss://' + base64.b64encode(raw.encode()).decode().rstrip('=') + '#operator@synthetic'
            sip002 = f'ss://{method}:{quote(password, safe="")}@127.0.0.1:{server.server_address[1]}'
            for document in (uri, base64.urlsafe_b64encode(uri.encode()).decode(), sip002):
                self.forward(document, '127.0.0.1', password)
            self.assertEqual(server.targets, [('origin.fixture.invalid', 443)] * 3)

    def test_equal_trojan_aliases_and_udp_false_forward_with_strict_tls(self):
        with tempfile.TemporaryDirectory() as folder:
            context, ca, _ = certificates(folder)
            server = self.trojan_peer(context)
            queries = ('allowInsecure=0&peer=local%68ost&sni=localhost&udp=0',
                       'udp=false&sni=localhost&peer=local%68ost&skip-cert-verify=false&allowInsecure=0')
            for query in queries:
                uri = f'trojan://fixture-password@127.0.0.1:{server.server_address[1]}?{query}'
                loon = (f'[Proxy]\nfixture = trojan,127.0.0.1,{server.server_address[1]},'
                        'fixture-password,tls-name:localhost,skip-cert-verify:false,udp:false')
                for document in (uri, base64.b64encode(uri.encode()).decode(), loon):
                    inspected = self.inspect(document)
                    capability = inspected['report']['nodes'][0]
                    self.assertTrue(capability['native_tcp_candidate'])
                    self.assertFalse(capability['real_network_verified'])
                    self.assertFalse(capability['udp_declared'])
                    self.assertFalse(capability['native_udp_supported'])
                    if document == loon:
                        self.assertEqual(inspected['nodes'][0]['raw-ini'], loon.splitlines()[1])
                    else:
                        self.assertEqual(inspected['nodes'][0]['raw-uri'], uri)
                    self.assertIs(inspected['nodes'][0]['skip-cert-verify'], False)
                    self.assertIs(inspected['nodes'][0]['udp'], False)
                    outbound = inspected['tcpCandidates'][0]
                    self.assertEqual(outbound['type'], 'trojan')
                    self.assertEqual(outbound['password'], 'fixture-password')
                    self.assertEqual(outbound['tls']['server_name'], 'localhost')
                    # Trust only the ephemeral synthetic CA; name verification remains active.
                    outbound['tls']['ca_der_base64'] = ca
                    started = self.command(op='start', config={'schema': 1, 'listen': '127.0.0.1:0',
                                           'selected': 'imported', 'nodes': [{'id': 'imported', 'outbound': outbound}]})
                    self.assertTrue(started['ok'], started)
                    handle = started['handle']
                    port = int(started['status']['address'].rsplit(':', 1)[1])
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=5) as stream:
                            stream.sendall(b'CONNECT origin.fixture.invalid:443 HTTP/1.1\r\n'
                                           b'Host: origin.fixture.invalid:443\r\n\r\n')
                            self.assertIn(b' 200 ', header(stream))
                            payload = b'imported-trojan-with-verified-name' * 2049
                            stream.sendall(payload)
                            self.assertEqual(exact(stream, len(payload)), payload)
                    finally:
                        self.assertTrue(self.command(op='stop', handle=handle)['ok'])
            self.assertEqual(server.accepted, 6)

    def test_equal_trojan_aliases_cannot_disable_certificate_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            context, ca, _ = certificates(folder)
            server = self.trojan_peer(context)
            for name, trust_ca in (('localhost', False), ('wrong.fixture.invalid', True)):
                uri = (f'trojan://fixture-password@127.0.0.1:{server.server_address[1]}'
                       f'?allowInsecure=0&peer={name}&sni={name}&udp=false')
                loon = (f'[Proxy]\nfixture = trojan,127.0.0.1,{server.server_address[1]},'
                        f'fixture-password,tls-name:{name},skip-cert-verify:false,udp:false')
                for document in (uri, loon):
                    outbound = self.inspect(document)['tcpCandidates'][0]
                    self.assertEqual(outbound['tls']['server_name'], name)
                    if trust_ca:
                        outbound['tls']['ca_der_base64'] = ca
                    started = self.command(op='start', config={'schema': 1, 'listen': '127.0.0.1:0',
                                           'selected': 'imported', 'nodes': [{'id': 'imported', 'outbound': outbound}]})
                    self.assertTrue(started['ok'], started)
                    handle = started['handle']
                    port = int(started['status']['address'].rsplit(':', 1)[1])
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=5) as stream:
                            stream.sendall(b'CONNECT origin.fixture.invalid:443 HTTP/1.1\r\n'
                                           b'Host: origin.fixture.invalid:443\r\n\r\n')
                            self.assertIn(b' 502 ', header(stream))
                    finally:
                        self.assertTrue(self.command(op='stop', handle=handle)['ok'])
            self.assertEqual(server.accepted, 0)
            for udp in ('1', 'true'):
                uri = (f'trojan://fixture-password@127.0.0.1:{server.server_address[1]}'
                       f'?allowInsecure=1&peer=localhost&sni=localhost&udp={udp}')
                inspected = self.inspect(uri)
                capability = inspected['report']['nodes'][0]
                self.assertTrue(inspected['report']['parsed'])
                self.assertTrue(capability['udp_declared'])
                self.assertFalse(capability['native_udp_supported'])
                self.assertFalse(capability['native_tcp_candidate'])
                self.assertEqual(capability['diagnostic'], 'CertificateVerificationDisabledUnsupported')
                self.assertEqual(inspected['nodes'][0]['raw-uri'], uri)
                self.assertIs(inspected['nodes'][0]['skip-cert-verify'], True)
                self.assertIs(inspected['nodes'][0]['udp'], True)
                self.assertEqual(inspected['tcpCandidates'], [None])

    def test_mixed_positional_and_named_credentials_are_rejected(self):
        for declaration in (
            'ss,example.invalid,443,encrypt-method=aes-256-gcm,aes-128-gcm,synthetic',
            'ss,example.invalid,443,aes-128-gcm,password=first-secret,second-secret',
            'ss,example.invalid,443,aes-128-gcm,first-secret,password=second-secret',
            'trojan,example.invalid,443,password=first-secret,second-secret',
            'trojan,example.invalid,443,first-secret,password=second-secret',
        ):
            inspected = self.inspect(f'[Proxy]\nfixture = {declaration}\n')
            self.assertFalse(inspected['report']['parsed'])
            self.assertEqual(inspected['report']['error'], 'DuplicateIniParameter')
            self.assertTrue(inspected['report']['original_preserved'])
            self.assertEqual(inspected['tcpCandidates'], [])
            report = json.dumps(inspected['report'])
            for private in ('example.invalid', 'first-secret', 'second-secret'):
                self.assertNotIn(private, report)

    def test_unknown_options_remain_preserved_and_unexecutable(self):
        user = base64.urlsafe_b64encode(f'aes-128-gcm:{PASSWORD}'.encode()).decode().rstrip('=')
        documents = (f'ss://{user}@[2001:db8::1]:443?future=synthetic-value',
                     '[Proxy]\nfixture = ss,example.invalid,443,aes-128-gcm,synthetic,future=synthetic-value')
        for document in documents:
            inspected = self.inspect(document)
            self.assertTrue(inspected['report']['parsed'])
            self.assertEqual(inspected['nodes'][0]['future'], 'synthetic-value')
            self.assertFalse(inspected['report']['nodes'][0]['native_tcp_candidate'])
            self.assertEqual(inspected['tcpCandidates'], [None])
            self.assertNotIn('synthetic-value', json.dumps(inspected['report']))


if __name__ == '__main__':
    unittest.main()
