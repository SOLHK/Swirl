"""Independent loopback DoT peers for the real Rust harness, never a proxy core.

Uses ephemeral certificates from the existing protocol fixtures. No OS trust,
DNS settings, private subscriptions or public resolver traffic are modified.
Run with SWIRL_RUST_HARNESS pointing to the matching compiled swirl-api binary.
"""
import copy
import json
import os
import socket
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest

from dns_peer import DnsPeer
from test_rust_core import Reference, Handler, certificates, exact, header


class DotPeer(DnsPeer):
    """Reuse the independent DNS response encoder, not its UDP/TCP listeners."""
    def __init__(self, context, mode='normal', ttl=30, ipv6=False):
        self.mode, self.ttl = mode, ttl
        self.queries, self.errors = [], []
        self.connections = 0
        owner = self

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            address_family = socket.AF_INET6 if ipv6 else socket.AF_INET

            def handle_error(self, request, address):
                owner.errors.append('DoT handler failed')

        class Request(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                try:
                    with context.wrap_socket(self.request, server_side=True) as stream:
                        owner.connections += 1
                        while True:
                            size = struct.unpack('!H', exact(stream, 2))[0]
                            data = exact(stream, size)
                            response = owner.respond(data, True)
                            if response is None:
                                # Keep the socket open to exercise a real deadline.
                                time.sleep(2)
                                return
                            if mode == 'bad-size':
                                stream.sendall(struct.pack('!H', 65535))
                                return
                            if mode == 'short-frame':
                                stream.sendall(struct.pack('!H', len(response)) + response[:7])
                                return
                            if mode == 'force-tc':
                                response = response[:2] + bytes([response[2] | 2]) + response[3:]
                            frame = struct.pack('!H', len(response)) + response
                            for at in range(0, len(frame), 3):
                                stream.sendall(frame[at:at+3])
                except (EOFError, OSError, ssl.SSLError):
                    # Certificate rejection, cancellation and close_notify are expected.
                    pass

        self.ipv6 = ipv6
        self.tcp = Server(('::1' if ipv6 else '127.0.0.1', 0), Request)
        self.port = self.tcp.server_address[1]
        threading.Thread(target=self.tcp.serve_forever, daemon=True).start()

    def close(self):
        self.tcp.shutdown()
        self.tcp.server_close()
        assert not self.errors, self.errors


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'set SWIRL_RUST_HARNESS')
class DnsTlsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.context, cls.ca, _ = certificates(cls.temp.name)
        cls.context.set_alpn_protocols(['dot'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.process = subprocess.Popen(
            [os.environ['SWIRL_RUST_HARNESS']], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close)
        self.peers = []
        self.origins = []
        self.handle = None

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        stderr = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        for peer in self.peers:
            peer.close()
        for server in self.origins:
            server.shutdown()
            server.server_close()
            self.assertEqual(server.errors, [])
        self.assertEqual(self.process.returncode, 0, stderr)
        self.assertNotIn(self.ca, stderr)

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def peer(self, **options):
        peer = DotPeer(self.context, **options)
        self.peers.append(peer)
        return peer

    def endpoint(self, peer, **tls):
        return {'address': peer.address, 'tls': {
            'server_name': 'localhost', 'alpn': ['dot'],
            'ca_der_base64': self.ca, **tls}}

    def config(self, dns):
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'd',
                'nodes': [{'id': 'd', 'outbound': {'type': 'direct'}}], 'dns': dns}

    def start(self, dns):
        result = self.command(op='start', config=self.config(dns))
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def stop(self):
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])
        self.handle = None

    def origin(self):
        server = Reference(('127.0.0.1', 0), Handler)
        server.protocol, server.tls = 'echo', None
        server.requests, server.errors, server.accepted = [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.origins.append(server)
        return server.server_address[1]

    def tunnel(self, target_port, name='dot.fixture.invalid'):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        try:
            stream.sendall(f'CONNECT {name}:{target_port} HTTP/1.1\r\nHost: {name}\r\n\r\n'.encode())
            result = header(stream)
        except BaseException:
            stream.close()
            raise
        return stream, result

    def assert_forward(self, target_port, name='dot.fixture.invalid'):
        stream, response = self.tunnel(target_port, name)
        with stream:
            self.assertIn(b' 200 ', response)
            stream.sendall(b'dot-native')
            self.assertEqual(exact(stream, 10), b'dot-native')

    def assert_denied(self, target_port, name='dot.fixture.invalid'):
        stream, response = self.tunnel(target_port, name)
        stream.close()
        self.assertIn(b' 502 ', response)

    def test_native_tls_partial_frames_and_ttl_cache(self):
        peer = self.peer()
        port = self.origin()
        self.start({'tls_servers': [self.endpoint(peer)], 'use_system_hosts': False})
        self.assert_forward(port)
        self.assert_forward(port)
        self.assertEqual(peer.queries, [('dot.fixture.invalid', 1, True), ('dot.fixture.invalid', 28, True)])
        self.assertEqual(peer.connections, 1, 'A/AAAA must reuse one authenticated connection')

    def test_cname_followups_stay_on_the_authenticated_stream(self):
        peer = self.peer(mode='cname')
        self.start({'tls_servers': [self.endpoint(peer)]})
        self.assert_forward(self.origin())
        self.assertEqual(len(peer.queries), 4)
        self.assertEqual(peer.connections, 1)
        self.assertTrue(all(tls for _, _, tls in peer.queries))

    def test_zero_ttl_is_not_cached(self):
        peer = self.peer(ttl=0)
        port = self.origin()
        self.start({'tls_servers': [self.endpoint(peer)]})
        self.assert_forward(port)
        self.assert_forward(port)
        self.assertEqual(len(peer.queries), 4)
        self.assertEqual(peer.connections, 2)

    def test_wrong_name_and_untrusted_certificate_send_no_dns_query(self):
        port = self.origin()
        for tls in ({'server_name': 'wrong.fixture.invalid'}, {'ca_der_base64': None}):
            with self.subTest(tls=list(tls)):
                peer = self.peer()
                self.start({'tls_servers': [self.endpoint(peer, **tls)], 'use_system_hosts': False})
                # localhost would succeed through the OS; it MUST NOT be retried there.
                self.assert_denied(port, 'localhost')
                self.assertEqual(peer.queries, [])
                self.stop()

    def test_malformed_tls_dns_is_rejected_not_retried_in_cleartext(self):
        port = self.origin()
        for mode in ('wrong-id', 'wrong-question', 'trailing', 'bad-size', 'short-frame', 'force-tc'):
            with self.subTest(mode=mode):
                peer = self.peer(mode=mode)
                self.start({'tls_servers': [self.endpoint(peer)], 'use_system_hosts': False})
                self.assert_denied(port, 'localhost')
                self.assertEqual(peer.connections, 1)
                self.stop()

    def test_silent_peer_deadline_is_bounded(self):
        peer = self.peer(mode='silent')
        self.start({'tls_servers': [self.endpoint(peer)], 'use_system_hosts': False})
        started = time.monotonic()
        self.assert_denied(self.origin(), 'localhost')
        self.assertLess(time.monotonic() - started, 4.5)

    def test_failover_is_only_between_explicit_tls_endpoints(self):
        bad, good = self.peer(mode='servfail'), self.peer()
        self.start({'tls_servers': [self.endpoint(bad), self.endpoint(good)]})
        self.assert_forward(self.origin())
        self.assertTrue(bad.queries)
        self.assertEqual(len(good.queries), 2)

    def test_nxdomain_does_not_fall_through_to_another_resolver(self):
        bad, unused = self.peer(mode='nxdomain'), self.peer()
        self.start({'tls_servers': [self.endpoint(bad), self.endpoint(unused)], 'use_system_hosts': False})
        self.assert_denied(self.origin(), 'localhost')
        self.assertEqual(unused.queries, [])
        self.assertEqual(unused.connections, 0)

    def test_mixed_plaintext_and_tls_config_fails_atomically(self):
        peer = self.peer()
        dns = {'tls_servers': [self.endpoint(peer)]}
        port = self.origin()
        self.start(dns)
        before = self.command(op='snapshot', handle=self.handle)['status']['generation']
        invalid = copy.deepcopy(dns)
        invalid['servers'] = ['127.0.0.1:53']
        result = self.command(op='configure', handle=self.handle, config=self.config(invalid))
        self.assertFalse(result['ok'])
        after = self.command(op='snapshot', handle=self.handle)['status']['generation']
        self.assertEqual(before, after)
        self.assert_forward(port)

    def test_generation_cache_isolation_preserves_existing_stream(self):
        peer = self.peer()
        dns = {'tls_servers': [self.endpoint(peer)]}
        port = self.origin()
        self.start(dns)
        stream, response = self.tunnel(port)
        with stream:
            self.assertIn(b' 200 ', response)
            updated = {'tls_servers': [self.endpoint(peer, server_name='wrong.fixture.invalid')]}
            self.assertTrue(self.command(op='configure', handle=self.handle, config=self.config(updated))['ok'])
            stream.sendall(b'old-stream')
            self.assertEqual(exact(stream, 10), b'old-stream')
            self.assert_denied(port)
        self.assertEqual(len(peer.queries), 2, 'new generation must not use the old DNS cache')

    def test_ipv6_bootstrap_uses_the_configured_authentication_name(self):
        try:
            peer = self.peer(ipv6=True)
        except OSError:
            self.skipTest('IPv6 loopback unavailable')
        self.start({'tls_servers': [self.endpoint(peer)]})
        self.assert_forward(self.origin())
        self.assertEqual(peer.connections, 1)


if __name__ == '__main__':
    unittest.main()
