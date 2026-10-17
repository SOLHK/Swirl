"""Independent loopback RFC 8484 peer; no public/private resolvers or OS edits."""
import copy
import json
import os
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from dns_peer import DnsPeer
from test_rust_core import Reference, Handler, certificates, exact, header


class DohPeer(DnsPeer):
    def __init__(self, context, mode='normal', ttl=30, cache='', age=0, ipv6=False):
        self.mode, self.ttl, self.ipv6 = mode, ttl, ipv6
        self.queries, self.errors, self.requests = [], [], []
        self.connections = 0
        owner = self

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            address_family = socket.AF_INET6 if ipv6 else socket.AF_INET
            def handle_error(self, request, address):
                owner.errors.append('HTTPS DNS peer assertion failed')

        class Request(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    with context.wrap_socket(self.request, server_side=True) as stream:
                        owner.connections += 1
                        head = header(stream)
                        assert head.startswith(b'POST /dns-query HTTP/1.1\r\n'), head[:60]
                        fields = {}
                        for row in head.split(b'\r\n')[1:]:
                            if row:
                                key, value = row.split(b':', 1)
                                fields[key.lower()] = value.strip()
                        assert fields[b'content-type'] == b'application/dns-message'
                        assert fields[b'accept'] == b'application/dns-message'
                        assert b'authorization' not in fields and b'cookie' not in fields
                        data = exact(stream, int(fields[b'content-length']))
                        assert data[:2] == b'\x00\x00'
                        owner.requests.append(head)
                        body = owner.respond(data, True)
                        if body is None:
                            time.sleep(2)
                            return
                        if mode == 'force-tc':
                            body = body[:2] + bytes([body[2] | 2]) + body[3:]
                        status = '302 Found' if mode == 'redirect' else '503 Busy' if mode == 'status' else '200 OK'
                        content_type = 'text/html' if mode == 'content-type' else 'application/dns-message'
                        response = f'HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nConnection: close\r\nAge: {age}\r\n'.encode()
                        if cache:
                            response += f'Cache-Control: {cache}\r\n'.encode()
                        if mode == 'redirect':
                            response += b'Location: http://127.0.0.1:9/leak\r\n'
                        if mode == 'encoding':
                            response += b'Content-Encoding: gzip\r\n'
                        if mode in ('chunked', 'bad-chunk', 'trailer', 'ambiguous'):
                            response += b'Transfer-Encoding: chunked\r\n'
                            if mode == 'ambiguous':
                                response += f'Content-Length: {len(body)}\r\n'.encode()
                            if mode == 'bad-chunk':
                                body = b'ffffffff\r\n'
                            else:
                                chunks = [body[:7], body[7:]]
                                body = b''.join(f'{len(x):x}\r\n'.encode() + x + b'\r\n' for x in chunks)
                                body += b'0\r\n' + (b'Age: 0\r\n' if mode == 'trailer' else b'X-Fixture: yes\r\n') + b'\r\n'
                        else:
                            length = 65535 if mode == 'oversize' else len(body)
                            response += f'Content-Length: {length}\r\n'.encode()
                            if mode == 'duplicate':
                                response += f'Content-Length: {length}\r\n'.encode()
                            if mode == 'short-body':
                                body = body[:7]
                        response += b'\r\n' + body
                        for at in range(0, len(response), 3):
                            stream.sendall(response[at:at+3])
                except (EOFError, OSError, ssl.SSLError):
                    pass

        self.tcp = Server(('::1' if ipv6 else '127.0.0.1', 0), Request)
        self.port = self.tcp.server_address[1]
        threading.Thread(target=self.tcp.serve_forever, daemon=True).start()

    def close(self):
        self.tcp.shutdown()
        self.tcp.server_close()
        assert not self.errors, self.errors


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'set SWIRL_RUST_HARNESS')
class DnsHttpsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.context, cls.ca, _ = certificates(cls.temp.name)
        cls.context.set_alpn_protocols(['http/1.1'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.peers, self.origins = [], []
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
            self.fail('Rust harness did not terminate')
        finally:
            for peer in self.peers:
                peer.close()
            for origin in self.origins:
                origin.shutdown()
                origin.server_close()
        stderr = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, stderr)
        self.assertNotIn(self.ca, stderr)

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def peer(self, **options):
        peer = DohPeer(self.context, **options)
        self.peers.append(peer)
        return peer

    def endpoint(self, peer, **tls):
        return {'address': peer.address, 'https_path': '/dns-query',
                'tls': {'server_name': 'localhost', 'alpn': ['http/1.1'], 'ca_der_base64': self.ca, **tls}}

    def config(self, endpoints):
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'd',
                'nodes': [{'id': 'd', 'outbound': {'type': 'direct'}}],
                'dns': {'tls_servers': endpoints, 'use_system_hosts': False}}

    def start(self, endpoints):
        result = self.command(op='start', config=self.config(endpoints))
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def stop(self):
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def origin(self):
        server = Reference(('127.0.0.1', 0), Handler)
        server.protocol, server.tls = 'echo', None
        server.requests, server.errors, server.accepted = [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.origins.append(server)
        return server.server_address[1]

    def tunnel(self, port, host='https.fixture.invalid'):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        try:
            stream.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode())
            return stream, header(stream)
        except BaseException:
            stream.close()
            raise

    def forward(self, port):
        stream, response = self.tunnel(port)
        with stream:
            self.assertIn(b' 200 ', response)
            stream.sendall(b'native-doh')
            self.assertEqual(exact(stream, 10), b'native-doh')

    def denied(self, port):
        # OS localhost would succeed: no implicit system DNS retry is allowed.
        stream, response = self.tunnel(port, 'localhost')
        stream.close()
        self.assertIn(b' 502 ', response)

    def test_authenticated_post_fragmentation_and_dns_cache(self):
        peer = self.peer()
        self.start([self.endpoint(peer)])
        port = self.origin()
        self.forward(port)
        self.forward(port)
        self.assertEqual(len(peer.queries), 2)
        self.assertEqual(peer.connections, 2)

    def test_chunked_body_and_cname_followups(self):
        port = self.origin()
        for mode in ('chunked', 'cname'):
            with self.subTest(mode=mode):
                peer = self.peer(mode=mode)
                self.start([self.endpoint(peer)])
                self.forward(port)
                self.assertEqual(len(peer.queries), 4 if mode == 'cname' else 2)
                self.stop()

    def test_cache_control_and_http_age_do_not_extend_dns_ttl(self):
        port = self.origin()
        for options in ({'ttl': 0}, {'cache': 'no-store'}, {'cache': 'no-cache'},
                        {'cache': 'max-age=0'}, {'ttl': 30, 'age': 30}, {'cache': 'max-age=10', 'age': 10}):
            with self.subTest(options=options):
                peer = self.peer(**options)
                self.start([self.endpoint(peer)])
                self.forward(port)
                self.forward(port)
                self.assertEqual(len(peer.queries), 4)
                self.stop()

    def test_http_and_dns_failures_never_become_success_or_plaintext_fallback(self):
        port = self.origin()
        for mode in ('redirect', 'status', 'content-type', 'encoding', 'ambiguous', 'duplicate',
                     'oversize', 'short-body', 'bad-chunk', 'trailer', 'wrong-id', 'wrong-question', 'trailing', 'force-tc'):
            with self.subTest(mode=mode):
                peer = self.peer(mode=mode)
                self.start([self.endpoint(peer)])
                self.denied(port)
                self.stop()
        self.assertEqual(self.origins[0].accepted, 0)

    def test_tls_name_and_trust_rejection_precedes_http_request(self):
        port = self.origin()
        for tls in ({'server_name': 'wrong.invalid'}, {'ca_der_base64': None}):
            peer = self.peer()
            self.start([self.endpoint(peer, **tls)])
            self.denied(port)
            self.assertEqual(peer.requests, [])
            self.stop()

    def test_declared_failover_and_terminal_nxdomain(self):
        port = self.origin()
        bad, good = self.peer(mode='servfail'), self.peer()
        self.start([self.endpoint(bad), self.endpoint(good)])
        self.forward(port)
        self.assertEqual(len(good.queries), 2)
        self.stop()
        negative, unused = self.peer(mode='nxdomain'), self.peer()
        self.start([self.endpoint(negative), self.endpoint(unused)])
        self.denied(port)
        self.assertEqual(unused.connections, 0)

    def test_silent_server_has_total_deadline(self):
        peer = self.peer(mode='silent')
        self.start([self.endpoint(peer)])
        started = time.monotonic()
        self.denied(self.origin())
        self.assertLess(time.monotonic() - started, 4.5)

    def test_configuration_update_is_atomic_and_old_stream_survives(self):
        peer = self.peer()
        endpoints = [self.endpoint(peer)]
        self.start(endpoints)
        port = self.origin()
        stream, response = self.tunnel(port)
        with stream:
            self.assertIn(b' 200 ', response)
            old = self.command(op='snapshot', handle=self.handle)['status']['generation']
            invalid = self.config(endpoints)
            invalid['dns']['servers'] = ['127.0.0.1:53']
            self.assertFalse(self.command(op='configure', handle=self.handle, config=invalid)['ok'])
            self.assertEqual(self.command(op='snapshot', handle=self.handle)['status']['generation'], old)
            updated = self.config([self.endpoint(peer, server_name='wrong.invalid')])
            self.assertTrue(self.command(op='configure', handle=self.handle, config=updated)['ok'])
            stream.sendall(b'old-alive')
            self.assertEqual(exact(stream, 9), b'old-alive')
            self.denied(port)

    def test_ipv6_bootstrap(self):
        try:
            peer = self.peer(ipv6=True)
        except OSError:
            self.skipTest('IPv6 loopback unavailable')
        self.start([self.endpoint(peer)])
        self.forward(self.origin())


if __name__ == '__main__':
    unittest.main(verbosity=2)
